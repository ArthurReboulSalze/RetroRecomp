"""Z80 AOT with Neo Geo's canonical CPU ABI and 16-bit port callbacks.

Reuse our Mega Drive structural-key/extraction strategy, rather than swapping
its different Z80 state ABI into Geolith. Constants remove all opcode decoding
from native bodies; immediate operands and data remain real live bus reads.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
from zipfile import ZipFile
from .megadrive_z80 import opcode_key, _clean, _cases
from .megadrive_codegen import write_changed
from .neogeo import parse_neo
from .library import atomic_json


def adapt_source(source: str) -> str:
    """Sequence architectural word reads independently of C evaluation order."""
    from .gun16_runtime import replace
    return replace(source,'  return (Z80_READ_BYTE(z->userdata, addr + 1) << 8) |\n'
        '         Z80_READ_BYTE(z->userdata, addr);',
        '  uint8_t low=Z80_READ_BYTE(z->userdata,addr);\n'
        '  uint8_t high=Z80_READ_BYTE(z->userdata,(uint16_t)(addr+1));\n'
        '  return ((uint16_t)high<<8)|low;')


def function_body(source: str,name: str) -> str:
    match=re.search(r'static unsigned '+name+r'\([^;]*?\)\s*\{',source)
    if not match:raise ValueError('Pinned Neo Geo Z80 function changed: '+name)
    begin=match.end();depth=1
    for pos in range(begin,len(source)):
        depth+=(source[pos]=='{')-(source[pos]=='}')
        if not depth:return source[begin:pos]
    raise ValueError('Unclosed Neo Geo Z80 function: '+name)


class Emitter:
    def __init__(self,source: str):
        clean=_clean(source)
        self.bodies={family:function_body(clean,'exec_opcode'+suffix) for family,suffix in
            (('base',''),('index','_ddfd'),('ed','_ed'),('cb','_cb'),('dcb','_dcb'))}
        self.cases={family:_cases(self.bodies[family]) for family in ('base','index','ed')}

    def emit(self,raw: bytes,pos=0,family='base') -> str:
        if pos>=4:raise ValueError('Z80 prefix chain exceeds guard window.')
        op=raw[pos]
        if family=='base':
            head='(void)nextb(z);inc_r(z);\n'
            if op in (0xcb,0xed):return head+self.emit(raw,pos+1,'cb' if op==0xcb else 'ed')
            if op in (0xdd,0xfd):return head+'{uint16_t *const iz=&z->'+('ix' if op==0xdd else 'iy')+';\n'+self.emit(raw,pos+1,'index')+'}\n'
            return head+self.cases['base'][op]+'\n'
        if family=='index':
            head='(void)nextb(z);inc_r(z);\n'
            if op==0xcb:
                return head+'{uint16_t addr=displace(z,*iz,nextb(z));\n'+self.emit(raw,pos+2,'dcb')+'}\n'
            code=self.cases['index'].get(op)
            if code is None:
                # The fetched ignored-prefix opcode is already consumed. The
                # recursive base body must not read it again.
                nested=self.emit(raw,pos,'base').replace('(void)nextb(z);','',1)
                return head+'cyc+=4;\n'+nested+'z->r=(z->r&0x80)|((z->r-1)&0x7f);\n'
            code=code.replace('IZH','(*iz>>8)').replace('IZL','(*iz&255)').replace('IZD','displace(z,*iz,nextb(z))')
            return head+code+'\n'
        if family=='ed':
            return '(void)nextb(z);inc_r(z);\n'+self.cases['ed'].get(op,self.cases['ed'][None])+'\n'
        body=self.bodies[family]
        body=re.sub(r'\bopcode\b',str(op),body)
        body=body.replace('unsigned cyc = 8;','cyc += 8;').replace('unsigned cyc = 0;','')
        body=body.replace('return cyc;','')
        return '(void)nextb(z);\n{\n'+body+'\n}\n'


def generate(project: Path,geolith: Path,ram_variants=()) -> dict:
    source=adapt_source((geolith/'src/z80/z80.c').read_text(encoding='utf-8'));emitter=Emitter(source)
    prepared=parse_neo(project/'cartridge.neo');m=next(r for r in prepared.members if r['region']=='m')
    with (project/'cartridge.neo').open('rb') as f:f.seek(m['offset']);m1=f.read(m['bytes'])
    with ZipFile(project/'bios.zip') as archive:sm1=archive.read('sm1.sm1')
    keys=set();maps=[]
    for image in (m1,sm1):
        window=image+image[:3];mapping=[]
        for offset in range(len(image)):
            key=opcode_key(window[offset:offset+4]);mapping.append(key)
            if key is not None:keys.add(key)
        maps.append(mapping)
    ram=set()
    for item in ram_variants:
        pc,raw=item.get('address'),item.get('bytes')
        if type(pc) is int and 0xf800<=pc<=0xffff and isinstance(raw,str) and re.fullmatch('[0-9a-fA-F]{8}',raw):
            key=opcode_key(bytes.fromhex(raw))
            if key is not None:ram.add((pc,key));keys.add(key)
    ordered=sorted(keys);indices={key:index+1 for index,key in enumerate(ordered)}
    functions=[];entries=[]
    for index,(mask,raw) in enumerate(ordered):
        code=emitter.emit(raw)
        # No native body may call any runtime opcode executor, including ignored
        # or repeated prefixes. Reject a changed upstream semantic shape.
        if 'exec_opcode' in code:raise ValueError('Runtime Z80 opcode dispatch leaked into AOT.')
        symbol=f'rr_ng_z80_op_{index}'
        functions.append(f'static unsigned {symbol}(z80 *z) {{unsigned cyc=0;\n{code}\nreturn cyc;}}\n')
        entries.append('{'+str(mask)+',{'+','.join(map(str,raw))+'},'+symbol+'}')
    generated=('/* Generated static Z80 bodies; upstream notices are embedded. */\n'+''.join(functions)+
        'static const RrNgZ80Step rr_ng_z80_entries[]={\n'+',\n'.join(entries)+'\n};\n')
    for region,mapping in enumerate(maps,1):
        generated+=f'static const uint16_t rr_ng_z80_map{region}[{len(mapping)}]={{'+','.join(str(indices.get(key,0)) for key in mapping)+'};\n'
    generated+='''const RrNgZ80Step *rr_ng_z80_native_lookup(unsigned region,uint32_t offset) {
    unsigned index=0;
'''
    for region,mapping in enumerate(maps,1):
        generated+=f'if(region=={region} && offset<{len(mapping)}u)index=rr_ng_z80_map{region}[offset];\n'
    generated+='return index?&rr_ng_z80_entries[index-1]:NULL;\n}\n'
    generated+='const RrNgZ80Step *rr_ng_z80_ram_lookup(uint16_t pc) {\n'
    for pc,key in sorted(ram):
        generated+=f'''if(pc=={pc}) {{
    const RrNgZ80Step *op=&rr_ng_z80_entries[{indices[key]-1}];int match=1;
    for(unsigned n=0;n<4;++n)if(op->mask&(1u<<n)) {{
        uint8_t actual;if(!rr_ng_z80_code_byte((uint16_t)(pc+n),&actual) || actual!=op->bytes[n])match=0;
    }}
    if(match)return op;
}}
'''
    generated+='return NULL;\n}\n'
    write_changed(project/'ng_z80_steps.inc',generated)
    result={'schema':1,'structural_bodies':len(ordered),'regions':[
        {'region':label,'bytes':len(image),'sha256':hashlib.sha256(image).hexdigest(),
         'translated_positions':sum(key is not None for key in mapping)} for label,image,mapping in zip(('m1','sm1'),(m1,sm1),maps)],
        'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'guarded_ram_variants':len(ram),
        'ram_variants':[{'address':pc,'bytes':key[1].hex()} for pc,key in sorted(ram)]}
    atomic_json(project/'z80-analysis.json',result);return result
