"""Physical P/BIOS instruction AOT using our qualified MC68000 semantics.

Seeds and static successors are private conversion observations. All actual
instruction words and mappings are guarded, including observed RAM variants;
unknown code stays counted reference execution. Generated instructions are
never distributed as sources.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile

from .paths import ROOT, ASSETS
from .platforms import build_executable, cmake_target_args, build_jobs
from .core import run, toolchain, serialized_setup
from .library import atomic_json
from .m68000 import adapt_semantics, operation_bodies, mnemonic_names, instruction_literal
from .megadrive_codegen import write_changed


STRUCTURAL_FIELDS=('mnemonic','size','word_count','byte_length','src_ea','dst_ea',
                   'reg','has_target','dst_is_ea','predec_mem_form','mem_shift')


def canonical_instruction(ins, name):
    """Identical immutable words share data, with PC-relative targets rebased."""
    value=dict(ins)
    if name in ('MN_BRA','MN_BSR','MN_Bcc','MN_DBcc'):
        value['target_addr']=(ins['target_addr']-ins['addr'])&0xffffff
    value['addr']=0
    return value


def structural_key(ins):
    return (ins['words'][0],*(ins[field] for field in STRUCTURAL_FIELDS))


def structural_body(ins,name,body):
    """Preselect one decoded operation/operand form, never a runtime decoder.

    Extension words and immediates come from the offline immutable descriptor.
    The full live-word guard in the adapter remains mandatory, including RAM.
    """
    def literal(match):
        field,index=match[1],match[2]
        if field=='words' and index=='0':return str(ins['words'][0])
        if field in STRUCTURAL_FIELDS:return name if field=='mnemonic' else str(ins[field])
        return match[0]
    body=re.sub(r'ins->(\w+)(?:\[(\d+)\])?',literal,body)
    return ('    M68KInstr decoded=*compiled;\n'
        '    rr_ng_relocate_instruction(&decoded,g_cpu.PC & 0xffffffu);\n'
        '    const M68KInstr *ins=&decoded;\n    ExtR er;er_init(&er,ins);\n'
        f'    const uint32_t fall=ins->addr+{ins["byte_length"]}u;\n    *next_pc=fall;\n'
        f'    const M68KSize sz=(M68KSize){ins["size"]};\n'
        f'    const int dir={(ins["words"][0]>>8)&1},cc={(ins["words"][0]>>8)&15};\n'
        +body+'\n')


@serialized_setup
def decoder_tool(engine: Path) -> Path:
    from .megadrive_codegen import decoder_tool as md_decoder
    # Reuse exactly the qualified decoder and cycle header, but no SEGA ROM
    # header parser or SEGA-specific minimum PC in the Neo Geo frontend.
    md_decoder(engine)
    project=ROOT/'.build/neogeo-step-decoder'
    project.mkdir(parents=True,exist_ok=True)
    for name in ('md_cycle_estimate.h','md_exception_decode.h'):
        write_changed(project/name,(ROOT/'.build/megadrive-step-decoder'/name).read_text(encoding='utf-8'))
    write_changed(project/'neogeo_decode.c',(ASSETS/'native/neogeo_decode.c').read_text(encoding='utf-8'))
    write_changed(project/'CMakeLists.txt',f'''cmake_minimum_required(VERSION 3.20)
project(RetroNgDecode LANGUAGES C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(ng_decode neogeo_decode.c "{engine.as_posix()}/recompiler/src/m68k_decoder.c"
 "{engine.as_posix()}/recompiler/src/m68k_validator.c" "{engine.as_posix()}/recompiler/src/rom_parser.c")
target_include_directories(ng_decode PRIVATE . "{engine.as_posix()}/recompiler/src")
if(MSVC)
  target_compile_options(ng_decode PRIVATE /utf-8 /wd4996)
endif()
''')
    cmake,generator=toolchain()
    run([cmake,'-S',project,'-B',project/'build','-G',generator,*cmake_target_args()],log=project/'build.log')
    run([cmake,'--build',project/'build','--config','Release','--parallel',build_jobs()],log=project/'build.log')
    return build_executable(project/'build','ng_decode')


def code_entries(region: int,base: int,size: int,seeds: set[int],physical_entries=None) -> list[int]:
    """Logical banked/RAM PCs never imply a physical cartridge offset.

    Current mapping observations supply banked roots; legacy fixed/BIOS roots
    are safe even when an older receipt has no physical-code field.
    """
    if region==1:entries={pc for pc in seeds if type(pc) is int and 0<=pc<min(size,0x100000) and not pc&1}
    else:entries={(pc&0x1ffff)+base for pc in seeds if type(pc) is int and 0xc00000<=pc<0xd00000 and not pc&1}
    if physical_entries:
        entries.update(base+offset for offset in physical_entries.get('p' if region==1 else 'bios',())
                       if type(offset) is int and 0<=offset<size and not offset&1)
    return sorted(pc for pc in entries if base<=pc<base+size)


def ram_observations(records) -> list[tuple[int,bytes]]:
    """Bounded private samples; never infer RAM code from a cartridge PC."""
    unique=set()
    for record in records or ():
        if not isinstance(record,dict):continue
        offset=record.get('offset');words=record.get('words')
        if type(offset) is not int or offset<0 or offset>=0x10000 or offset&1:continue
        if not isinstance(words,str) or len(words)%4 or not re.fullmatch(r'[0-9a-fA-F]{4,32}',words):continue
        data=bytes.fromhex(words)
        if offset+len(data)>0x10000:continue
        unique.add((offset,data))
        if len(unique)>4096:raise ValueError('Neo Geo RAM observation bound exceeded.')
    return sorted(unique)


def generate(project: Path, seeds: set[int],physical_entries=None,ram_variants=None) -> dict:
    from .neogeo import parse_neo
    engine=ROOT/'.deps/segagenesisrecomp'
    if not (engine/'external/m68k-recomp-core/common/m68k_decoder.h').is_file():
        from .console16 import dependencies16
        engine,*_=dependencies16('md',print)
    # Validate the existing qualified CPU dependency instead of updating it.
    from .console16 import REPOSITORIES
    if run(['git','-C',engine,'rev-parse','HEAD']).strip()!=REPOSITORIES['md'][1]:
        raise ValueError('MC68000 translation dependency differs from its qualified pin.')
    names=mnemonic_names(engine)
    source=adapt_semantics((engine/'runner/m68k_interp.c').read_text(encoding='utf-8'),hook_prefix='rr_ng')
    bodies=operation_bodies(source)
    helper=source[source.index('static uint32_t szmask('):source.index('static uint8_t *s_exec_cov')]
    helper=helper[:helper.rfind('/* =====')]
    timing=source[source.index('static int interp_popcount16('):source.index('static void interp_account_cycles(')]
    timing=timing[:timing.rfind('/* The emit_cycle_accounting')]
    write_changed(project/'ng_step_semantics.h',
        '/* Qualified MC68000 helpers; see embedded GenesisRecomp notices. */\n'
        '#pragma once\n#include "neogeo_native.h"\n#include <stddef.h>\n'
        '#define s_illegal_ea rr_ng_illegal_ea\n'
        'static int interp_ea_read_cost(int ea,M68KSize sz);\n'
        # Mega Drive game-specific instruction hooks cannot apply to Neo Geo.
        'static int game_instruction_hook_site(uint32_t pc) {(void)pc;return 0;}\n'
        'static int genesis_game_instruction_hook(uint32_t pc) {(void)pc;return 0;}\n'
        'static void discover(uint32_t pc) {(void)pc;}\n'+helper+'\n'+timing)
    # Reuse our dynamic arithmetic clock implementation without importing
    # Mega Drive bus or scheduler state into this console.
    pf=(ASSETS/'native/md_prefetch.inc').read_text(encoding='utf-8')
    arithmetic=pf[pf.index('unsigned rr_md_multiply_clocks('):pf.index('void rr_md_arithmetic_phase(')]
    write_changed(project/'ng_arithmetic.c','#include "neogeo_native.h"\n'+arithmetic.replace('rr_md_','rr_ng_')+
        '\nvoid rr_ng_arithmetic_phase(unsigned base,unsigned ea,int multiply) {\n'
        ' (void)multiply;rr_ng_arithmetic_cycles=base+ea;\n}\n')
    write_changed(project/'m68k_decoder.h',(engine/'external/m68k-recomp-core/common/m68k_decoder.h').read_text(encoding='utf-8'))
    write_changed(project/'rom_parser.h',(engine/'recompiler/src/rom_parser.h').read_text(encoding='utf-8'))
    prepared=parse_neo(project/'cartridge.neo')
    p=next(r for r in prepared.members if r['region']=='p')
    with (project/'cartridge.neo').open('rb') as f:
        f.seek(p['offset']);raw_program=f.read(p['bytes'])
    program=bytearray(raw_program);program[0::2],program[1::2]=raw_program[1::2],raw_program[0::2]
    program=bytes(program)
    # The selected BIOS dump is word-swapped; Geolith normalizes it to big
    # endian at load. Cartridge P regions follow the NEO container's convention.
    with ZipFile(project/'bios.zip') as archive:raw_bios=archive.read('sp-s2.sp1')
    bios=bytearray(raw_bios);bios[0::2],bios[1::2]=raw_bios[1::2],raw_bios[0::2]
    bios=bytes(bios)
    aes = b''
    with ZipFile(project/'bios.zip') as archive:
        if 'neo-epo.bin' in archive.namelist():
            raw = archive.read('neo-epo.bin'); alternate = bytearray(raw)
            alternate[0::2], alternate[1::2] = raw[1::2], raw[0::2]; aes = bytes(alternate)
    decoder=decoder_tool(engine)
    all_instructions=[];regions=[]
    sources = [(1,0,program,'program'),(2,0xc00000,bios,'bios')]
    if aes: sources.append((4,0xc00000,aes,'aes-bios'))
    for region,base,data,label in sources:
        image=project/(label+'.bin');image.write_bytes(data)
        entries=code_entries(region,base,len(data),seeds,physical_entries)
        # Boot reset vector and exception vectors are legitimate code roots;
        # all later indirect entries come from observed execution.
        if region in (2,4):
            entries+= [int.from_bytes(data[n:n+4],'big') for n in range(4,128,4)
                       if base<=int.from_bytes(data[n:n+4],'big')<base+len(data)]
        listing=project/(label+'-pcs.txt');listing.write_text(''.join(f'{pc:06x}\n' for pc in entries),encoding='ascii')
        output=project/(label+'-instructions.json')
        # The fixed cartridge aperture and selected BIOS are fully scanned.
        # Banked windows retain exact observed physical roots; RAM is guarded
        # separately. Data that decodes legally is only a candidate, not proof
        # that it executes and never promoted as an observed knowledge root.
        sweep=min(len(data),0x100000) if region==1 else len(data)
        run([decoder,image,f'{base:x}',listing,output,f'{sweep:x}'],log=project/'decode.log')
        decoded=json.loads(output.read_text(encoding='utf-8'))
        accepted=[dict(ins,region=region,offset=ins['addr']-base) for ins in decoded
                  if names[ins['mnemonic']] in bodies and names[ins['mnemonic']]!='MN_RESET']
        all_instructions+=accepted
        regions.append({'region':label,'sha256':hashlib.sha256(data).hexdigest(),
                        'bytes':len(data),'translated':len(accepted),'decoded':len(decoded),
                        'static_scan_bytes':sweep})
    ram_samples=ram_observations(ram_variants);ram_keys=set();ram_refs=[];without_ref=0
    for offset,data in ram_samples:
        base=0x100000+offset
        image=project/'ram-variant.bin';image.write_bytes(data)
        listing=project/'ram-pcs.txt';listing.write_text(f'{base:06x}\n',encoding='ascii')
        output=project/'ram-instructions.json'
        run([decoder,image,f'{base:x}',listing,output],log=project/'decode.log')
        decoded=json.loads(output.read_text(encoding='utf-8'))
        ins=next((ins for ins in decoded if ins['addr']==base),None)
        if not ins or names[ins['mnemonic']] not in bodies or names[ins['mnemonic']]=='MN_RESET':continue
        key=(offset,tuple(ins['words'][:ins['word_count']]))
        if key in ram_keys:continue
        ram_keys.add(key);all_instructions.append(dict(ins,region=3,offset=offset))
        # Only reconstructible numeric locations may later enter a shared bank.
        raw=b''.join(word.to_bytes(2,'big') for word in key[1]);found=False
        for region,source_bytes in ((1,program),(2,bios)):
            location=source_bytes.find(raw)
            while location>=0 and location&1:location=source_bytes.find(raw,location+1)
            if location>=0:
                ram_refs.append({'ram_offset':offset,'region':region,'source_offset':location,'bytes':len(raw)})
                found=True;break
        if not found:without_ref+=1
    instructions=sorted(all_instructions,key=lambda ins:(ins['region'],ins['offset'],tuple(ins['words'])))
    chunks=[[] for _ in range(16)];declarations=[];table=[]
    descriptors={};forms={};position_indices=[];records=[]
    for index,ins in enumerate(instructions):
        name=names[ins['mnemonic']];canonical=canonical_instruction(ins,name)
        literal=instruction_literal(canonical,name)
        # RAM chains retain distinct nodes at each observed offset.
        key=(literal,ins['offset'] if ins['region']==3 else None)
        if key not in descriptors:
            form=structural_key(ins)
            if form not in forms:
                symbol=f'rr_ng_form_{len(forms)}';forms[form]=symbol
                body=structural_body(ins,name,bodies[name])
                chunks[(ins['words'][0]>>1)%len(chunks)].append(
                    f'M68kiStatus {symbol}(const M68KInstr *compiled,uint32_t *next_pc) {{\n{body}}}\n')
                declarations.append(f'extern M68kiStatus {symbol}(const M68KInstr*,uint32_t*);\n')
            descriptors[key]=len(table)+1;records.append(ins)
            table.append('{'+literal+f',{forms[form]}'+'}')
        position_indices.append(descriptors[key])
    steps=project/'steps';steps.mkdir(exist_ok=True)
    for index,chunk in enumerate(chunks):
        write_changed(steps/f'ng_step_part{index:02d}.c','#include "ng_step_semantics.h"\n'+'\n'.join(chunk))
    maps=[];lookups=[]
    for region in ((1,2,4) if aes else (1,2)):
        keys={ins['offset']>>1:position_indices[i] for i,ins in enumerate(instructions) if ins['region']==region}
        length=len(program if region==1 else bios)//2
        maps.append(f'static const uint32_t map{region}[{length}]={{'+','.join(str(keys.get(i,0)) for i in range(length))+'};\n')
        lookups.append(f'if(region=={region} && offset<{length*2}u) index=map{region}[offset>>1];')
    ram_heads={};ram_next=[0]*len(records)
    for index in range(len(records)-1,-1,-1):
        ins=records[index]
        if ins['region']==3:
            ram_next[index]=ram_heads.get(ins['offset']>>1,0);ram_heads[ins['offset']>>1]=index+1
    ram_index='static const uint32_t ram_map[32768]={'+','.join(str(ram_heads.get(i,0)) for i in range(32768))+'};\n'
    ram_index+='static const uint32_t ram_next[]={'+','.join(map(str,ram_next))+'};\n'
    write_changed(steps/'ng_step_index.c','#include "neogeo_native.h"\n#include "geo.h"\n#include <stddef.h>\n'+''.join(declarations)+
        'static const RrNgNativeStep entries[]={\n'+',\n'.join(table)+'\n};\n'+''.join(maps)+
        'const RrNgNativeStep *rr_ng_native_lookup(uint32_t region,uint32_t offset) {\n'
        'if(offset&1u)return NULL;unsigned index=0;if(region==2 && geo_get_system()==SYSTEM_AES)region=4;'+''.join(lookups)+'return index?&entries[index-1]:NULL;\n}\n'+ram_index+
        '''const RrNgNativeStep *rr_ng_ram_native_lookup(uint32_t pc,uint32_t offset,unsigned available) {
    if(offset>=65536u || (offset&1u))return NULL;
    for(unsigned index=ram_map[offset>>1];index;index=ram_next[index-1]) {
        const RrNgNativeStep *op=&entries[index-1];
        if(op->instruction.byte_length>available)continue;
        int match=1;
        for(unsigned n=0;n<(unsigned)op->instruction.word_count;++n) {
            uint16_t actual;
            if(!rr_ng_code_word(pc+n*2u,&actual) || actual!=op->instruction.words[n]) {match=0;break;}
        }
        if(match)return op;
    }
    return NULL;
}
''')
    result={'schema':1,'regions':regions,'translated_instructions':len(instructions),
            'unique_descriptors':len(table),'structural_bodies':len(forms),
            'requested_entries':len(seeds),'semantics_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'physical_entry_counts':{key:len(set(values)) for key,values in (physical_entries or {}).items()},
            'guarded_ram_variants':len(ram_keys),'ram_observed_snapshots':len(ram_samples),
            'ram_source_refs':ram_refs,'private_ram_variants_without_rom_ref':without_ref,
            'mutable_code_native':bool(ram_keys),'knowledge_promoted':False}
    atomic_json(project/'native-analysis.json',result)
    return result
