"""Bounded Human68k HU sections and relocations; no host execution or HLE.

The real OS still chooses a load address, loads the program and clears BSS.
This model reconstructs bytes for offline attribution/guard generation only.
Format reference: erique/ghidra-human68k, commit
608cab76bbd650119ca5b1e2396e3a4485ba64da, Human68kXFileHeader/Relocation.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import struct

RAM_LIMIT=12*1024*1024

@dataclass(frozen=True)
class XProgram:
    sha256:str
    mode:int
    original_base:int
    entry_offset:int
    text:bytes
    data:bytes
    bss_bytes:int
    relocations:tuple[tuple[int,int],...]

    def load_image(self,base:int,*,include_bss:bool=False)->bytes:
        length=len(self.text)+len(self.data)+self.bss_bytes
        if type(base) is not int or base&1 or not 0<=base<=RAM_LIMIT-length:
            raise ValueError('HU load range is outside X68000 RAM.')
        image=bytearray(self.text+self.data)
        delta=base-self.original_base
        for offset,size in self.relocations:
            value=(int.from_bytes(image[offset:offset+size],'big')+delta)&((1<<(8*size))-1)
            image[offset:offset+size]=value.to_bytes(size,'big')
        if include_bss:image.extend(bytes(self.bss_bytes))
        return bytes(image)

    def metadata(self)->dict:
        return {'sha256':self.sha256,'load_mode':self.mode,'original_base':self.original_base,
            'entry_offset':self.entry_offset,'text_bytes':len(self.text),'data_bytes':len(self.data),
            'bss_bytes':self.bss_bytes,'relocations':[list(item) for item in self.relocations]}


def parse_x(content:bytes)->XProgram:
    if not isinstance(content,bytes) or not 64<=len(content)<=RAM_LIMIT+1024*1024:
        raise ValueError('Invalid bounded HU file size.')
    if content[:3]!=b'HU\0' or content[3] not in (0,1,2):
        raise ValueError('Unsupported HU header/load mode.')
    fields=struct.unpack_from('>15I',content,4)
    base,entry,text,data,bss,reloc,symbol,line,symdebug,strings=fields[:10]
    if fields[14]:raise ValueError('Bound HU containers are not qualified yet; do not guess their layout.')
    if any(fields[10:14]):raise ValueError('Nonzero reserved HU header fields.')
    if base&1 or text<2 or entry&1 or not entry<text or text+data+bss>RAM_LIMIT or base+text+data+bss>RAM_LIMIT:
        raise ValueError('Invalid HU sections/entry range.')
    end=64+text+data
    if end+reloc+symbol+line+symdebug+strings!=len(content) or reloc&1:
        raise ValueError('HU sections exceed file bounds or have trailing bytes.')
    table=content[end:end+reloc];pos=offset=0;entries=[];last_end=0
    while pos<len(table):
        distance=int.from_bytes(table[pos:pos+2],'big');pos+=2
        if distance==0:
            if any(table[pos:]):raise ValueError('Nonzero bytes after HU relocation terminator.')
            break
        if distance==1:
            if pos+4>len(table):raise ValueError('Truncated extended HU relocation.')
            distance=int.from_bytes(table[pos:pos+4],'big');pos+=4;size=4
        else:
            size=2 if distance&1 else 4
            distance&=~1
        offset+=distance
        if offset&1 or offset<last_end or offset+size>text+data:
            raise ValueError('HU relocation is overlapping, unaligned or outside initialized sections.')
        entries.append((offset,size));last_end=offset+size
    return XProgram(hashlib.sha256(content).hexdigest(),content[3],base,entry,
                    content[64:64+text],content[64+text:end],bss,tuple(entries))
