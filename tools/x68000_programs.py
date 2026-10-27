"""Read-only program provenance for the initial standard FAT12 disk profile.

Only a caller-selected image is inspected. Unsupported files are inventoried,
never rewritten or treated as a successful load. This is offline metadata;
Human68k, not this helper, still loads and relocates the actual guest code.
"""
from __future__ import annotations
from collections import defaultdict
import hashlib
from pathlib import Path
import struct
from retrorecomp.x68000_media import identify_disk
from retrorecomp.x68000_program import parse_x
from tools.x68000_fixture_disk import FixtureFat12


def disk_files(path:Path)->dict[str,bytes]:
    disk=identify_disk(path)
    if disk.sector_bytes!=1024 or disk.sectors_per_track!=8 or disk.present_tracks!=tuple(range(154)) or disk.overtrack:
        raise ValueError('Program inventory currently requires the standard FAT12 disk profile.')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=disk.sha256:raise ValueError('Disk changed during program inventory.')
    fs=FixtureFat12(raw[256:] if disk.format=='dim' else raw)
    result={};directories=set()
    def payload(first,size=None):
        chain=fs._chain(first)
        data=b''.join(bytes(fs.data[fs.data_offset+(c-2)*1024:fs.data_offset+(c-1)*1024]) for c in chain)
        if size is not None and size>len(data):raise ValueError('File exceeds its FAT12 chain.')
        return data if size is None else data[:size]
    def walk(data,prefix,depth):
        if depth>8:raise ValueError('Directory depth bound exceeded.')
        for offset in range(0,len(data),32):
            entry=data[offset:offset+32]
            if len(entry)!=32:raise ValueError('Partial directory entry.')
            if entry[0]==0:break
            if entry[0]==0xe5 or entry[11]&8 or entry[:1]==b'.':continue
            name=entry[:8].rstrip(b' ')+(b'.'+entry[8:11].rstrip(b' ') if entry[8:11].strip() else b'')
            name=name.decode('cp932',errors='strict')
            if any(c in name for c in '/\\\0'):raise ValueError('Unsafe guest filename.')
            first,size=struct.unpack_from('<HI',entry,26)
            if entry[11]&0x10:
                if first in directories:raise ValueError('Looping/cross-linked directory chain.')
                directories.add(first);walk(payload(first),prefix+name+'/',depth+1)
            else:
                if len(result)>=1024:raise ValueError('File inventory bound exceeded.')
                full=prefix+name
                if full in result:raise ValueError('Duplicate guest filename.')
                result[full]=payload(first,size) if size else b''
    walk(bytes(fs.data[fs.root_offset:fs.root_offset+fs.root_entries*32]),'',0)
    return result


def program_provenance(files:dict[str,bytes],samples:list[tuple[int,str]])->dict:
    modules=[];unparsed=[]
    samples=[(pc,bytes.fromhex(words)) for pc,words in samples if pc<0xc00000]
    for name,content in files.items():
        if not name.casefold().endswith('.x'):continue
        try:p=parse_x(content)
        except ValueError as exc:
            unparsed.append({'name':name,'sha256':hashlib.sha256(content).hexdigest(),'reason':str(exc)});continue
        candidates=[];entry=p.entry_offset;image=p.text+p.data
        # Entry PC + a full 16-byte live sample is a candidate. Confirm at
        # least three distinct matching instructions elsewhere in the image.
        # Multiple modules may reuse an address; never select by PC alone.
        for pc,words in samples:
            base=pc-entry
            if len(words)<16 or base<0 or base+len(image)+p.bss_bytes>0xc00000:continue
            if words[:2]!=image[entry:entry+2]:continue
            loaded=p.load_image(base)
            if loaded[entry:entry+len(words)]!=words:continue
            matched={address for address,data in samples if base<=address<base+len(p.text)
                and loaded[address-base:address-base+len(data)]==data}
            if len(matched)>=3:candidates.append({'load_base':base,'matching_pcs':len(matched),
                'text_range':[base,base+len(p.text)],'data_range':[base+len(p.text),base+len(image)]})
        unique={candidate['load_base']:candidate for candidate in candidates}
        modules.append({'name':name,**p.metadata(),'observed_load_candidates':list(unique.values())})
    return {'schema':1,'modules':modules,'unparsed':unparsed,
        'attribution':'Confirmed byte matches are provenance candidates, not exclusive ownership of a RAM address.'}
