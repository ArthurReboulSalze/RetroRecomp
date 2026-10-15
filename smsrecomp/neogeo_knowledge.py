"""Exact cartridge/BIOS numeric hints; no firmware, RAM words or game code.

Hints add roots and reconstruct guards from the user's verified inputs. Fresh
reference, packed and state validation are mandatory even when hints exist.
"""
import hashlib
import json
from pathlib import Path
import os
import re
import zlib
from zipfile import ZipFile

from .neogeo import parse_neo, validate_bios
from .neogeo_build import GEOLITH_REV, LITHOGEN_REV
from .library import atomic_json, entry_lock, library_root

FIELDS={'rom_entries':(2,262144),'ram_refs':(4,4096),'z80_refs':(4,32768)}
IDENTITY_FIELDS={'engine','loader','cart','bios','rom_bytes','p_bytes','bios_bytes','m1_bytes','sm1_bytes'}


def key(cart: str,bios: str) -> str:
    return hashlib.sha256(json.dumps({'cart':cart,'bios':bios,'system':'mvs','region':'eu'},sort_keys=True).encode()).hexdigest()


def validate_record(identity: str,record: dict) -> dict:
    if not isinstance(record,dict) or set(record)!=IDENTITY_FIELDS|FIELDS.keys():
        raise ValueError('Invalid Neo Geo compilation fields.')
    for name in ('engine','loader','cart','bios'):
        length=40 if name in ('engine','loader') else 64
        if not isinstance(record[name],str) or not re.fullmatch('[0-9a-f]{'+str(length)+'}',record[name]):
            raise ValueError('Invalid Neo Geo compilation identity.')
    if identity!=key(record['cart'],record['bios']):
        raise ValueError('Neo Geo hints do not match their cart/BIOS key.')
    for name,minimum,maximum in (('rom_bytes',4096,512<<20),('p_bytes',512,16<<20),
            ('bios_bytes',0x20000,0x20000),('m1_bytes',0x10000,512<<10),('sm1_bytes',0x20000,0x20000)):
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
    return record


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


def hints(project: Path) -> tuple[dict,list[dict],list[dict],dict]:
    identity,current,sources=context(project)
    records=[];counts={'shared':0,'local':0}
    if not (os.environ.get('RETRO_RECOMP_LIBRARY_DIR') or os.environ.get('SMSRECOMP_LIBRARY_DIR') or
            os.environ.get('RETRO_RECOMP_BUNDLED_KNOWLEDGE')=='0'):
        from .knowledge import load,RESOURCE
        from .paths import ASSETS
        try:
            record=load(ASSETS/RESOURCE)['consoles'].get('ng',{}).get(identity,{})
            if _matching(identity,record,current):records.append(record);counts['shared']=len(record['rom_entries'])+len(record['ram_refs'])+len(record['z80_refs'])
        except (OSError,ValueError,TypeError,KeyError,EOFError,zlib.error):pass
    path=library_root('ng')/identity/'compilation.json'
    try:
        with path.open('rb') as f:raw=f.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise ValueError('Neo Geo local memory is too large.')
        record=json.loads(raw)['record']
        if _matching(identity,record,current):records.append(record);counts['local']=len(record['rom_entries'])+len(record['ram_refs'])+len(record['z80_refs'])
    except (OSError,ValueError,TypeError,KeyError):pass
    combined={name:sorted(set(tuple(r) for record in records for r in record[name])) for name in FIELDS}
    physical={'p':set(),'bios':set()}
    for region,offset in combined['rom_entries']:physical['p' if region==1 else 'bios'].add(offset)
    ram=[{'offset':pc,'words':sources[region][offset:offset+size].hex()} for pc,region,offset,size in combined['ram_refs']]
    z80=[{'address':pc,'bytes':sources[region][offset:offset+4].hex()} for pc,region,offset,mask in combined['z80_refs']]
    from .feedback import records as feedback_records
    feedback=feedback_records('ng',identity)
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
    physical={1:set(),2:set()}
    # Reused build folders can retain older developer routes. Promote only
    # the fresh reference routes named by the completed current validation.
    validation=json.loads((project/'native-validation.json').read_text(encoding='utf-8'))
    for row in validation['routes']:
        path=project/'native-discovery'/(row['route']+'-reference.json')
        report=json.loads(path.read_text(encoding='utf-8'))
        for region,name in ((1,'p'),(2,'bios')):physical[region].update(report.get('reached_physical',{}).get(name,[]))
    record['rom_entries']=sorted([region,offset] for region,offsets in physical.items() for offset in offsets)
    main=json.loads((project/'native-analysis.json').read_text(encoding='utf-8'))
    record['ram_refs']=sorted({(r['ram_offset'],r['region'],r['source_offset'],r['bytes']) for r in main['ram_source_refs']})
    record['ram_refs']=[list(r) for r in record['ram_refs']]
    from .megadrive_z80 import opcode_key
    sound=json.loads((project/'z80-analysis.json').read_text(encoding='utf-8'))
    refs=set()
    for variant in sound['ram_variants']:
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
    if not all(c['reference_match'] for c in checks) or not all(r['fresh_process_match'] for r in states['routes']):
        raise ValueError('Unverified Neo Geo observations cannot enter memory.')
    identity,record=numeric_record(project)
    directory=library_root('ng')/identity
    with entry_lock(directory):
        path=directory/'compilation.json'
        try:
            old=json.loads(path.read_text(encoding='utf-8'))['record']
            if _matching(identity,old,record):
                for name in FIELDS:record[name]=[list(r) for r in sorted(set(map(tuple,record[name]+old[name])))]
        except (OSError,ValueError,TypeError,KeyError):pass
        validate_record(identity,record)
        atomic_json(path,{'schema':1,'identity':identity,'title':title,'source':source,
            'record':record,'packed_reference_passed':True,'states_passed':True,
            'zero_fallback':all(not c['interpreted_opcodes'] and not c['audio_interpreted_opcodes'] for c in checks)})
    counts={name:len(record[name]) for name in FIELDS}
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
