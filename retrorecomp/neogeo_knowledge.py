"""Exact cartridge/BIOS numeric hints; no firmware, RAM words or game code.

Hints add roots and reconstruct guards from the user's verified inputs. Fresh
reference, packed and state validation are mandatory even when hints exist.

Three banks guide a conversion: the bundled snapshot, this player's own
library (only the routes a fresh reference run reached, see `remember`) and the
imported bank that other players' shared files and the shared base fill. The
imported hints are counted apart and never enter the library: they are not
exported again unless this player's own conversion reaches them.
"""
import hashlib
import json
from pathlib import Path
import os
import re
import threading
import zlib
from zipfile import ZipFile

from .neogeo import parse_neo, validate_bios
from .neogeo_build import GEOLITH_REV, LITHOGEN_REV
from .library import atomic_json, entry_lock, library_root

FIELDS={'rom_entries':(2,262144),'ram_refs':(4,4096),'z80_refs':(4,32768)}
# Imported RAM rows a conversion takes at most (the generator's bound is 4,096 samples in all).
IMPORTED_RAM_LIMIT=2048
IDENTITY_FIELDS={'engine','loader','cart','bios','rom_bytes','p_bytes','bios_bytes','m1_bytes','sm1_bytes'}
# Bounds of a record, also generated into the online service's validator
# (tools/build_web_limits.py of the site): hexadecimal lengths, region sizes
# (inclusive) and the number of `rom_deltas` blocks.
HEX_LENGTHS={'engine':40,'loader':40,'cart':64,'bios':64}
SIZE_BOUNDS={'rom_bytes':(4096,512<<20),'p_bytes':(512,16<<20),'bios_bytes':(0x20000,0x20000),
             'm1_bytes':(0x10000,512<<10),'sm1_bytes':(0x20000,0x20000)}
DELTA_BLOCKS=2


def key(cart: str,bios: str) -> str:
    return hashlib.sha256(json.dumps({'cart':cart,'bios':bios,'system':'mvs','region':'eu'},sort_keys=True).encode()).hexdigest()


def validate_record(identity: str,record: dict) -> dict:
    required=IDENTITY_FIELDS|FIELDS.keys()
    if not isinstance(record,dict) or not required<=set(record)<=required|{'rom_deltas'}:
        raise ValueError('Invalid Neo Geo compilation fields.')
    for name,length in HEX_LENGTHS.items():
        if not isinstance(record[name],str) or not re.fullmatch('[0-9a-f]{'+str(length)+'}',record[name]):
            raise ValueError('Invalid Neo Geo compilation identity.')
    if identity!=key(record['cart'],record['bios']):
        raise ValueError('Neo Geo hints do not match their cart/BIOS key.')
    for name,(minimum,maximum) in SIZE_BOUNDS.items():
        value=record[name]
        if type(value) is not int or not minimum<=value<=maximum:
            raise ValueError('Invalid Neo Geo compilation region size.')
    if record['p_bytes']&1 or record['m1_bytes']&(record['m1_bytes']-1) or record['p_bytes']+record['m1_bytes']>record['rom_bytes']:
        raise ValueError('Inconsistent Neo Geo compilation region sizes.')
    for name,(width,limit) in FIELDS.items():
        entries=record[name]
        if not isinstance(entries,list) or len(entries)>limit or any(not isinstance(e,list) or len(e)!=width or
                any(type(n) is not int or n<0 or n>0xffffffff for n in e) for e in entries):
            raise ValueError('Invalid Neo Geo compilation entries.')
        for row in entries:
            if name=='rom_entries':
                region,offset=row;bound=record['p_bytes'] if region==1 else record['bios_bytes']
                valid=region in (1,2) and not offset&1 and offset+2<=bound
            elif name=='ram_refs':
                pc,region,offset,size=row;bound=record['p_bytes'] if region==1 else record['bios_bytes']
                valid=region in (1,2) and not (pc|offset|size)&1 and 2<=size<=16 and pc+size<=65536 and offset+size<=bound
            else:
                pc,region,offset,mask=row;bound=record['m1_bytes'] if region==3 else record['sm1_bytes']
                valid=region in (3,4) and 0xf800<=pc<=0xffff and 1<=mask<=15 and bool(mask&1) and offset+4<=bound
            if not valid:raise ValueError('Neo Geo compilation reference outside its region.')
    deltas=record.get('rom_deltas',[])
    if not isinstance(deltas,list) or len(deltas)>DELTA_BLOCKS:
        raise ValueError('Invalid Neo Geo ROM delta blocks.')
    count=len(record['rom_entries']);seen=set()
    for block in deltas:
        if (not isinstance(block,list) or len(block)<2 or
                any(type(n) is not int or not 0<=n<=0xffffffff for n in block)):
            raise ValueError('Invalid Neo Geo ROM delta block.')
        region,offset,*gaps=block
        count+=len(block)-1
        if region not in (1,2) or region in seen or count>FIELDS['rom_entries'][1]:
            raise ValueError('Invalid Neo Geo ROM delta region/count.')
        seen.add(region);bound=record['p_bytes'] if region==1 else record['bios_bytes']
        if offset&1 or offset+2>bound or any(gap<2 or gap&1 for gap in gaps):
            raise ValueError('Invalid Neo Geo ROM delta offset.')
        if offset+sum(gaps)+2>bound:
            raise ValueError('Neo Geo ROM delta reference outside its region.')
    return record


def expanded_record(identity: str,record: dict) -> dict:
    """Recover exact physical roots before merging or reconstructing guards."""
    validate_record(identity,record)
    roots=set(map(tuple,record['rom_entries']))
    for region,offset,*gaps in record.get('rom_deltas',[]):
        roots.add((region,offset))
        for gap in gaps:
            offset+=gap;roots.add((region,offset))
    return {**{name:record[name] for name in IDENTITY_FIELDS|FIELDS.keys()},
            'rom_entries':[list(row) for row in sorted(roots)]}


def compact_record(identity: str,record: dict) -> dict:
    """Lossless numeric gaps between sorted roots; no instruction bytes."""
    expanded=expanded_record(identity,record);blocks=[]
    for region in (1,2):
        offsets=[offset for r,offset in expanded['rom_entries'] if r==region]
        if offsets:blocks.append([region,offsets[0],*(b-a for a,b in zip(offsets,offsets[1:]))])
    packed={**expanded,'rom_entries':[],'rom_deltas':blocks}
    validate_record(identity,packed)
    return packed


def entry_set(record: dict) -> set:
    """Every hint of a record, as comparable tuples; compact ROM roots are
    expanded. Used to tell what a received record adds to a known one."""
    found=set()
    if not isinstance(record,dict):return found
    for name in FIELDS:
        if name!='rom_entries':
            found |= {(name,tuple(row)) for row in record.get(name,[])}
    found |= {('rom_entries',tuple(row)) for row in record.get('rom_entries',[])}
    for region,offset,*gaps in record.get('rom_deltas',[]):
        found.add(('rom_entries',(region,offset)))
        for gap in gaps:
            offset+=gap;found.add(('rom_entries',(region,offset)))
    return found


def merged_record(identity: str,first: dict,second: dict) -> dict:
    """Union of two records of one identity, in compact form. Records found by
    another compiler revision never mix: the one built by the current revision
    is kept, else the first. ValueError when the union exceeds a bound."""
    if not second:return first
    if not first:return second
    one=expanded_record(identity,first);two=expanded_record(identity,second)
    if any(one[name]!=two[name] for name in IDENTITY_FIELDS):
        current=lambda record:record['engine']==GEOLITH_REV and record['loader']==LITHOGEN_REV
        return second if current(two) and not current(one) else first
    merged={**one}
    for name in FIELDS:
        merged[name]=[list(row) for row in sorted(set(map(tuple,one[name]))|set(map(tuple,two[name])))]
    return compact_record(identity,merged)


def salvaged_record(identity: str,record) -> dict | None:
    """A received record without the rows that fail the checks: one malformed
    row is left out alone, never the record's other hints. None when its
    identity fields are not valid (an identity is all or nothing)."""
    try:return validate_record(identity,record)
    except (ValueError,TypeError,KeyError,AttributeError):pass
    if not isinstance(record,dict):return None
    base={name:record.get(name) for name in IDENTITY_FIELDS}
    empty={**base,'rom_entries':[],'ram_refs':[],'z80_refs':[]}
    try:validate_record(identity,empty)
    except (ValueError,TypeError,KeyError,AttributeError):return None
    kept=dict(empty)
    for name,(_,limit) in FIELDS.items():
        rows=record.get(name)
        if not isinstance(rows,list):continue
        good=[]
        for row in rows[:limit]:
            try:validate_record(identity,{**empty,name:[row]})
            except (ValueError,TypeError,KeyError,AttributeError):continue
            good.append(row)
        kept[name]=good
    if 'rom_deltas' in record:
        try:validate_record(identity,{**kept,'rom_deltas':record['rom_deltas']});kept['rom_deltas']=record['rom_deltas']
        except (ValueError,TypeError,KeyError,AttributeError):pass
    try:return validate_record(identity,kept)
    except (ValueError,TypeError,KeyError,AttributeError):return None


def context(project: Path) -> tuple[str,dict,dict[int,bytes]]:
    cart=parse_neo(project/'cartridge.neo');bios=validate_bios(project/'bios.zip')
    parts={r['region']:r for r in cart.members}
    with (project/'cartridge.neo').open('rb') as f:
        f.seek(parts['p']['offset']);p=f.read(parts['p']['bytes'])
        f.seek(parts['m']['offset']);m=f.read(parts['m']['bytes'])
    with ZipFile(project/'bios.zip') as z:b=z.read('sp-s2.sp1');sm=z.read('sm1.sm1')
    def swapped(raw):
        out=bytearray(raw);out[0::2],out[1::2]=raw[1::2],raw[0::2];return bytes(out)
    sources={1:swapped(p),2:swapped(b),3:m,4:sm}
    record={'engine':GEOLITH_REV,'loader':LITHOGEN_REV,'cart':cart.sha256,'bios':bios['sha256'],
            'rom_bytes':cart.size,'p_bytes':len(p),'bios_bytes':len(b),'m1_bytes':len(m),'sm1_bytes':len(sm),
            'rom_entries':[],'ram_refs':[],'z80_refs':[]}
    return key(cart.sha256,bios['sha256']),record,sources


def _matching(identity,record,current):
    validate_record(identity,record)
    return all(record[n]==current[n] for n in IDENTITY_FIELDS)


# The interface installs a function here for the length of a batch so that a
# conversion which has just prepared a cartridge (its identity is not known
# before) can ask the shared base for it. Nothing is set for a command-line or
# offline conversion. It receives the identity and may do nothing.
SHARED_SOURCE = None
_IN_USE = threading.local()


def imported_in_use() -> str | None:
    """The identity whose imported hints guided this thread's latest `hints`
    call (None when none did): what a failed conversion has to set aside."""
    return getattr(_IN_USE,'identity',None)


def forget_imported_use() -> None:
    _IN_USE.identity = None


def hints(project: Path) -> tuple[dict,list[dict],list[dict],dict]:
    identity,current,sources=context(project)
    records=[];counts={'shared':0,'local':0,'imported':0}
    forget_imported_use()
    if not (os.environ.get('RETRO_RECOMP_LIBRARY_DIR') or os.environ.get('SMSRECOMP_LIBRARY_DIR') or
            os.environ.get('RETRO_RECOMP_BUNDLED_KNOWLEDGE')=='0'):
        from .knowledge import load,RESOURCE
        from .paths import ASSETS
        try:
            record=load(ASSETS/RESOURCE)['consoles'].get('ng',{}).get(identity,{})
            if _matching(identity,record,current):
                record=expanded_record(identity,record);records.append(record)
                counts['shared']=sum(len(record[name]) for name in FIELDS)
        except (OSError,ValueError,TypeError,KeyError,EOFError,zlib.error):pass
    path=library_root('ng')/identity/'compilation.json'
    try:
        with path.open('rb') as f:raw=f.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise ValueError('Neo Geo local memory is too large.')
        record=json.loads(raw)['record']
        if _matching(identity,record,current):
            record=expanded_record(identity,record);records.append(record)
            counts['local']=sum(len(record[name]) for name in FIELDS)
    except (OSError,ValueError,TypeError,KeyError):pass
    from .knowledge import disabled,imported_record
    if not disabled():
        source=SHARED_SOURCE
        if source is not None:
            try:source(identity)
            except Exception:pass   # the shared base never stops a conversion
        # Other players' hints, from a shared file or the shared base. They
        # guide this conversion only; the local library never receives them.
        record=imported_record('ng',identity)
        try:
            if record and _matching(identity,record,current):
                record=expanded_record(identity,record)
                # The generator keeps at most 4,096 RAM samples, this
                # conversion's own included: imported rows only fill part of
                # that room, in address order (phase 6 audit, Metal Slug X).
                record['ram_refs']=record['ram_refs'][:IMPORTED_RAM_LIMIT];records.append(record)
                counts['imported']=sum(len(record[name]) for name in FIELDS)
                _IN_USE.identity=identity
        except (ValueError,TypeError,KeyError):pass
    combined={name:sorted(set(tuple(r) for record in records for r in record[name])) for name in FIELDS}
    physical={'p':set(),'bios':set()}
    for region,offset in combined['rom_entries']:physical['p' if region==1 else 'bios'].add(offset)
    ram=[{'offset':pc,'words':sources[region][offset:offset+size].hex()} for pc,region,offset,size in combined['ram_refs']]
    z80=[{'address':pc,'bytes':sources[region][offset:offset+4].hex()} for pc,region,offset,mask in combined['z80_refs']]
    from .feedback import records as feedback_records
    feedback=feedback_records('ng',identity)
    from .neogeo_build import aes_identity
    firmware = validate_bios(project/'bios.zip')
    if 'aes' in firmware:
        feedback += [row for row in feedback_records('ng',aes_identity(current['cart'],firmware))
                     if row.kind != 10 or row.auxiliary == 1]
    for row in feedback:
        if row.kind==10 and row.auxiliary in (1,2) and not row.address&1 and len(row.data)==2:
            image=sources[row.auxiliary]
            if image[row.address:row.address+2]==row.data:
                physical['p' if row.auxiliary==1 else 'bios'].add(row.address)
        elif row.kind==11 and not row.address&1 and len(row.data)%2==0 and row.address+len(row.data)<=65536:
            ram.append({'offset':row.address,'words':row.data.hex()})
        elif row.kind==12 and 0xf800<=row.address<=0xffff and len(row.data)==4:
            z80.append({'address':row.address,'bytes':row.data.hex()})
    return physical,ram,z80,{'identity':identity,**counts,'fresh_validation_required':True}


def numeric_record(project: Path) -> tuple[str,dict]:
    identity,record,sources=context(project)
    physical={1:set(),2:set()};observed_ram=[];observed_sound=[]
    # Reused build folders can retain older developer routes. Promote only
    # the fresh reference routes named by the completed current validation.
    validation=json.loads((project/'native-validation.json').read_text(encoding='utf-8'))
    for row in validation['routes']:
        if row['route'].startswith('aes-'):continue
        path=project/'native-discovery'/(row['route']+'-reference.json')
        report=json.loads(path.read_text(encoding='utf-8'))
        observed_ram += report.get('m68k_ram_variants',[])
        observed_sound += report.get('z80_variants',[])
        for region,name in ((1,'p'),(2,'bios')):physical[region].update(report.get('reached_physical',{}).get(name,[]))
    record['rom_entries']=sorted([region,offset] for region,offsets in physical.items() for offset in offsets)
    main=json.loads((project/'native-analysis.json').read_text(encoding='utf-8'))
    record['ram_refs']=sorted({(r['ram_offset'],r['region'],r['source_offset'],r['bytes'])
        for r in main['ram_source_refs'] if any(v['offset']==r['ram_offset'] and
            bytes.fromhex(v['words']).startswith(sources[r['region']][r['source_offset']:r['source_offset']+r['bytes']])
            for v in observed_ram)})
    record['ram_refs']=[list(r) for r in record['ram_refs']]
    from .megadrive_z80 import opcode_key
    sound=json.loads((project/'z80-analysis.json').read_text(encoding='utf-8'))
    refs=set()
    for variant in observed_sound:
        mask,raw=opcode_key(bytes.fromhex(variant['bytes']))
        first=next(n for n in range(4) if mask&(1<<n));found=False
        for region in (3,4):
            image=sources[region];pos=image.find(bytes([raw[first]]))
            while pos>=0:
                offset=pos-first
                if offset>=0 and offset+4<=len(image) and all(not mask&(1<<n) or image[offset+n]==raw[n] for n in range(4)):
                    refs.add((variant['address'],region,offset,mask));found=True;break
                pos=image.find(bytes([raw[first]]),pos+1)
            if found:break
    record['z80_refs']=[list(r) for r in sorted(refs)]
    validate_record(identity,record)
    return identity,record


def remember(project: Path,checks: list[dict],states: dict,*,title: str,source: dict) -> dict:
    validation=json.loads((project/'native-validation.json').read_text(encoding='utf-8'))
    if (not checks or not states['routes'] or not validation.get('passed') or validation.get('awaiting_packed_validation') or
            not all(c['reference_match'] for c in checks) or not all(r['fresh_process_match'] for r in states['routes'])):
        raise ValueError('Unverified Neo Geo observations cannot enter memory.')
    identity,record=numeric_record(project)
    directory=library_root('ng')/identity
    with entry_lock(directory):
        path=directory/'compilation.json'
        try:
            old=json.loads(path.read_text(encoding='utf-8'))['record']
            if _matching(identity,old,record):
                old=expanded_record(identity,old)
                for name in FIELDS:record[name]=[list(r) for r in sorted(set(map(tuple,record[name]+old[name])))]
        except (OSError,ValueError,TypeError,KeyError):pass
        validate_record(identity,record)
        atomic_json(path,{'schema':1,'identity':identity,'title':title,'source':source,
            'record':record,'packed_reference_passed':True,'states_passed':True,
            'zero_fallback':all(not c['interpreted_opcodes'] and not c['audio_interpreted_opcodes'] for c in checks)})
    counts={name:len(record[name]) for name in FIELDS}
    remember_prepared(source.get('sha256'),record['cart'])
    return {'identity':identity,'path':str(directory/'compilation.json'),'numeric_entries':counts,
            'raw_ram_words_stored':False,'fresh_validation_required':True}


def list_memory() -> list[dict]:
    rows=[]
    for path in library_root('ng').glob('*/compilation.json'):
        try:
            data=json.loads(path.read_text(encoding='utf-8'));validate_record(data['identity'],data['record'])
            rows.append({'title':data['title'],'sha256':data['identity'],
                'source_sha256':data['source']['sha256'],'bios_sha256':data['record']['bios'],
                'entries':sum(len(data['record'][name]) for name in FIELDS)})
        except (OSError,ValueError,TypeError,KeyError):pass
    return rows


def library_record(identity: str) -> dict | None:
    """This player's own record for an identity: the routes that fresh,
    verified conversions reached (see `remember`), or None."""
    path=library_root('ng')/identity/'compilation.json'
    try:
        with path.open('rb') as f:raw=f.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:return None
        data=json.loads(raw)
        if data.get('identity')!=identity or not data.get('packed_reference_passed') or not data.get('states_passed'):
            return None
        return validate_record(identity,data['record'])
    except (OSError,ValueError,TypeError,KeyError,AttributeError):return None


# --- Which identity a cartridge file will have --------------------------------
#
# The shared base names a game by key(cartridge, BIOS), where the cartridge is
# the prepared NEO container. A `.neo` file is its own container. A ZIP set is
# assembled by the preparation tool during the conversion, so its container is
# only known after a first preparation: it is then remembered here (and found
# again in the library's entries), and a set never prepared has no identity
# before its conversion.

CACHE_NAME='prepared-cartridges.json'
CACHE_LIMIT=65536


def _cache_path() -> Path:
    return library_root('ng')/CACHE_NAME


def _read_cache() -> dict:
    try:
        data=json.loads(_cache_path().read_text(encoding='utf-8'))
        sets=data['sets'];scanned=data.get('scanned',-1)
        if (isinstance(sets,dict) and type(scanned) is int and
                all(isinstance(k,str) and re.fullmatch('[0-9a-f]{64}',k) and isinstance(v,str) and
                    re.fullmatch('[0-9a-f]{64}',v) for k,v in sets.items())):
            return {'sets':sets,'scanned':scanned}
    except (OSError,ValueError,TypeError,KeyError,AttributeError):pass
    return {'sets':{},'scanned':-1}


def _write_cache(cache: dict) -> None:
    if len(cache['sets'])>CACHE_LIMIT:
        cache={**cache,'sets':dict(list(sorted(cache['sets'].items()))[-CACHE_LIMIT:])}
    directory=_cache_path().parent
    with entry_lock(directory/'.prepared-cartridges'):
        atomic_json(_cache_path(),{'schema':1,**cache})


def remember_prepared(source_sha,cart_sha) -> None:
    """The prepared container of a set, found by a preparation or a conversion."""
    if not all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in (source_sha,cart_sha)):return
    cache=_read_cache()
    if cache['sets'].get(source_sha)==cart_sha:return
    cache['sets'][source_sha]=cart_sha
    try:_write_cache(cache)
    except (OSError,TimeoutError):pass


def _library_entries() -> int:
    try:return sum(1 for _ in library_root('ng').glob('*/compilation.json'))
    except OSError:return 0


def prepared_cartridge(source_sha: str) -> str | None:
    """The prepared container of a ZIP set already prepared on this computer:
    from the cache, else from the library's entries (read once per change)."""
    cache=_read_cache()
    if source_sha in cache['sets']:return cache['sets'][source_sha]
    count=_library_entries()
    if count==cache['scanned']:return None
    for path in library_root('ng').glob('*/compilation.json'):
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            source,cart=data['source']['sha256'],data['record']['cart']
            if (re.fullmatch('[0-9a-f]{64}',source) and re.fullmatch('[0-9a-f]{64}',cart) and
                    data['identity']==key(cart,data['record']['bios'])):cache['sets'][source]=cart
        except (OSError,ValueError,TypeError,KeyError,AttributeError):continue
    cache['scanned']=count
    try:_write_cache(cache)
    except (OSError,TimeoutError):pass
    return cache['sets'].get(source_sha)


def shared_identity(path: Path,source_sha: str,bios_sha: str) -> str | None:
    """key(cartridge, BIOS) of a cartridge file with the BIOS a conversion will
    use, or None when its prepared container is not known yet."""
    if Path(path).suffix.casefold()=='.neo':cart=source_sha
    else:cart=prepared_cartridge(source_sha)
    return key(cart,bios_sha) if cart and bios_sha else None
