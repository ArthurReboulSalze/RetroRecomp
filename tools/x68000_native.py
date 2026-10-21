"""Private step-3 CPU experiment: offline MC68000 AOT and exact RAM guards.

No public converter profile or distribution permission is implied. The machine
remains PX68k for these comparisons; only a covered CPU instruction bypasses
its interpreter. All decoded words and generated bodies stay under .build.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
# Bundled sources (native/, licences). The converter points ROOT at its
# workspace (.deps, .build); SDK stays with the application's own files.
SDK=ROOT
NO_WINDOW=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
sys.path.insert(0,str(ROOT))
from tools.x68000_reference import ensure_sources, PX68K_REV,prepare_bundle,_atomic_text
from smsrecomp.core import run,toolchain
from smsrecomp.platforms import build_executable,cmake_target_args
from smsrecomp.m68000 import adapt_semantics,operation_bodies,mnemonic_names,instruction_literal
from smsrecomp.neogeo_codegen import canonical_instruction,structural_key,structural_body
from smsrecomp.megadrive_codegen import write_changed


def private_path(path:Path)->Path:
    path=path.absolute()
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (path,*path.parents)):
        raise ValueError('Private CPU work must not use linked directories.')
    path=path.resolve()
    if not path.is_relative_to((ROOT/'.build').resolve()):
        raise ValueError('Generated CPU data must stay in project .build.')
    return path


def observations(paths)->list[tuple[int,str]]:
    result=set()
    for path in paths:
        if path.stat().st_size>32*1024*1024:raise ValueError('CPU observation file exceeds its bound.')
        record=json.loads(path.read_text(encoding='utf-8'))
        if record.get('schema')!=1 or record.get('truncated') is not False:
            raise ValueError('CPU observations are incomplete or unknown.')
        for item in record.get('variants',[]):
            pc,words=item.get('pc'),item.get('words')
            if type(pc) is not int or pc&1 or not (0<=pc<0xc00000 or 0xe00000<=pc<0xe80000 or 0xea0000<=pc<0xea2000 or 0xfc0000<=pc<0xfffffe):
                raise ValueError('Unsupported observed code aperture.')
            if not isinstance(words,str) or not re.fullmatch('[0-9a-f]{4,32}',words) or len(words)%4:
                raise ValueError('Invalid bounded CPU words.')
            if pc+len(words)//2> (0xc00000 if pc<0xc00000 else 0xe80000 if pc<0xe80000 else 0xea2000 if pc<0xea2000 else 0x1000000):
                raise ValueError('CPU sample crosses a mapping boundary.')
            result.add((pc,words))
            if len(result)>262144:raise ValueError('Combined CPU observation bound exceeded.')
    return sorted(result)


def source_receipts(paths)->list[dict]:
    result=[]
    for path in paths:
        record=json.loads(path.read_text(encoding='utf-8'))
        identity=record.get('source_identity')
        manifest=path.parent/'datas/source-manifest.json'
        if manifest.is_file():
            actual=json.loads(manifest.read_text(encoding='utf-8')).get('sha256')
            if identity is not None and identity!=actual:raise ValueError('CPU observation/source manifest mismatch.')
            identity=actual
        if not isinstance(identity,str) or not re.fullmatch('[0-9a-f]{64}',identity):
            raise ValueError('Each CPU observation requires its exact media/firmware/configuration identity.')
        result.append({'identity':identity,'observations_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return result


def decoder(project:Path,engine:Path)->Path:
    from smsrecomp.neogeo_codegen import decoder_tool
    decoder_tool(engine) # Qualified decoder, exception normalizer and cycle helpers.
    directory=project/'decoder';directory.mkdir(exist_ok=True)
    write_changed(directory/'CMakeLists.txt',f'''cmake_minimum_required(VERSION 3.20)
project(RetroX68Decode LANGUAGES C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(x68_decode "{SDK.as_posix()}/native/x68000_native/decode.c"
 "{engine.as_posix()}/recompiler/src/m68k_decoder.c"
 "{engine.as_posix()}/recompiler/src/m68k_validator.c"
 "{engine.as_posix()}/recompiler/src/rom_parser.c")
target_include_directories(x68_decode PRIVATE "{(ROOT/'.build/megadrive-step-decoder').as_posix()}"
 "{engine.as_posix()}/recompiler/src")
if(MSVC)
 target_compile_options(x68_decode PRIVATE /utf-8 /wd4996)
endif()
''')
    cmake,generator=toolchain()
    run([cmake,'-S',directory,'-B',directory/'build','-G',generator,*cmake_target_args()],log=project/'build.log')
    run([cmake,'--build',directory/'build','--config','Release','--parallel','4'],log=project/'build.log')
    return build_executable(directory/'build','x68_decode')


# Machine sources under the native CPU: 'hissorii' (default since phase 4) or
# 'current' (pinned px68k-libretro, comparison only); docs/X68000_GPL_FREE_PLAN.md.
MACHINE_BASE=os.environ.get('RR_X68000_MACHINE_BASE','hissorii')
if MACHINE_BASE not in ('current','hissorii'):raise ValueError('RR_X68000_MACHINE_BASE must be current or hissorii.')


def generate(project:Path,samples:list[tuple[int,str]],px:Path,receipts=(),machine_base:str|None=None)->dict:
    machine_base=machine_base or MACHINE_BASE
    project=private_path(project);project.mkdir(parents=True,exist_ok=True)
    engine=ROOT/'.deps/segagenesisrecomp'
    geo=ROOT/'.deps/geolith-libretro'
    from smsrecomp.neogeo_build import GEOLITH_REV
    if subprocess.check_output(['git','-C',str(geo),'rev-parse','HEAD'],text=True,creationflags=NO_WINDOW).strip()!=GEOLITH_REV:
        raise ValueError('Qualified reference MC68000 dependency changed.')
    if subprocess.check_output(['git','-C',str(geo),'status','--porcelain','--untracked-files=no'],text=True,creationflags=NO_WINDOW).strip():
        raise ValueError('Reference MC68000 source has local modifications.')
    # Reuse the already qualified reference CPU too. PX68k's bundled old
    # Musashi double-counts immediate shift distance and lacks the known
    # operand-dependent bit/multiply/divide timing repairs. Keep X68000 IRQ,
    # trace and address-error settings, not Neo Geo board callbacks.
    for source in (geo/'src/m68k').rglob('*'):
        if source.is_file() and source.name!='m68kconf.h':
            target=project/'musashi'/source.relative_to(geo/'src/m68k')
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.is_file() or target.read_bytes()!=source.read_bytes():shutil.copyfile(source,target)
    if machine_base=='hissorii':
        # Our MIT configuration and CPU binding (native/x68000_machine/base74);
        # no PX68k m68000 file is copied.
        write_changed(project/'musashi/m68kconf.h',
                      (SDK/'native/x68000_machine/base74/musashi/m68kconf.h').read_text(encoding='utf-8'))
        for filename in ('m68000.h','m68000.c'):(project/filename).unlink(missing_ok=True)
    else:
        config=(px/'m68000/musashi/m68kconf.h').read_text(encoding='utf-8')
        config='int my_irqh_callback(int level);\n#define M68K_EMULATE_TRACE 1\n'+config
        write_changed(project/'musashi/m68kconf.h',config)
    for filename in (('m68000.h','m68000.c') if machine_base!='hissorii' else ()):
        source=(px/'m68000'/filename).read_text(encoding='utf-8',errors='surrogateescape')
        source=source.replace('"musashi/m68k.h"','"m68k.h"').replace('"musashi/m68kcpu.h"','"m68kcpu.h"')
        # The descriptive Japanese header is not needed for compilation;
        # retain its source bytes exactly, including the original encoding.
        data=source.encode('utf-8',errors='surrogateescape');target=project/filename
        if not target.is_file() or target.read_bytes()!=data:target.write_bytes(data)
    from smsrecomp.console16 import REPOSITORIES
    if subprocess.check_output(['git','-C',str(engine),'rev-parse','HEAD'],text=True,creationflags=NO_WINDOW).strip()!=REPOSITORIES['md'][1]:
        raise ValueError('Qualified MC68000 dependency changed.')
    decode_tool=decoder(project,engine)
    lengths=project/'opcode-lengths.bin'
    run([decode_tool,'--lengths',lengths],log=project/'decode.log')
    sizes=lengths.read_bytes()
    if len(sizes)!=65536 or any(not 1<=n<=8 for n in sizes):raise ValueError('Invalid MC68000 opcode length table.')
    write_changed(project/'opcode_lengths.h','static const unsigned char rr_x68k_word_counts[65536]={\n'+
        '\n'.join(','.join(map(str,sizes[n:n+128]))+',' for n in range(0,65536,128))+'\n};\n')
    names=mnemonic_names(engine)
    semantics=adapt_semantics((engine/'runner/m68k_interp.c').read_text(encoding='utf-8'),hook_prefix='rr_x68k')
    bodies=operation_bodies(semantics)
    bodies['MN_RESET']='''if(!(g_cpu.SR&SR_S))return rr_x68k_instruction_exception(next_pc,8,ins->addr,34);
        rr_x68k_reset_instruction();return M68KI_OK;'''
    helper=semantics[semantics.index('static uint32_t szmask('):semantics.index('static uint8_t *s_exec_cov')]
    helper=helper[:helper.rfind('/* =====')]
    timing=semantics[semantics.index('static int interp_popcount16('):semantics.index('static void interp_account_cycles(')]
    timing=timing[:timing.rfind('/* The emit_cycle_accounting')]
    write_changed(project/'step_semantics.h','#pragma once\n#include "cpu.h"\n#include <stddef.h>\n'
        '#define s_illegal_ea rr_x68k_illegal_ea\nstatic int interp_ea_read_cost(int,M68KSize);\n'
        'static int game_instruction_hook_site(uint32_t pc){(void)pc;return 0;}\n'
        'static int genesis_game_instruction_hook(uint32_t pc){(void)pc;return 0;}\n'
        'static void discover(uint32_t pc){(void)pc;}\n'+helper+'\n'+timing)
    for name,path in [('m68k_decoder.h',engine/'external/m68k-recomp-core/common/m68k_decoder.h'),
                      ('rom_parser.h',engine/'recompiler/src/rom_parser.h')]:
        write_changed(project/name,path.read_text(encoding='utf-8'))
    header=(SDK/'native/neogeo_native.h').read_text(encoding='utf-8')
    header=header.replace('RR_NEOGEO_NATIVE_H','RR_X68000_NATIVE_CPU_H').replace('rr_ng_','rr_x68k_').replace('RrNgNativeStep','RrX68NativeStep')
    header=header.replace('/* Called before opcode fetch.', 'const RrX68NativeStep *rr_x68k_lookup(uint32_t pc);\n/* Called before opcode fetch.')
    header+='\nvoid rr_x68k_reset_instruction(void);\n'
    write_changed(project/'cpu.h',header)
    cpu=(SDK/'native/neogeo_native.c').read_text(encoding='utf-8')
    cpu=cpu.replace('"m68k/m68kcpu.h"','"m68kcpu.h"').replace('"neogeo_reference.h"','"observe.h"').replace('"ng_step_semantics.h"','"step_semantics.h"')
    cpu=cpu.replace('rr_ng_','rr_x68k_').replace('RrNgNativeStep','RrX68NativeStep')
    cpu=cpu.replace('int rr_x68k_force_reference;','')
    cpu=cpu.replace('void rr_x68k_set_sr(uint16_t value) {',
        'void rr_x68k_set_sr(uint16_t value) {\n'
        '    REG_SP_BASE[(g_cpu.SR&SR_S)?4:0]=g_cpu.A[7];')
    begin=cpu.index('    RrM68000CodeLocation location;',cpu.index('int rr_x68k_native_execute('))
    end=cpu.index('    for(unsigned n=0;n<8;++n)',begin)
    cpu=cpu[:begin]+'''    if(rr_x68k_force_reference)return 0;
    const RrX68NativeStep *op=rr_x68k_lookup(pc);
    if(!op)return 0;
'''+cpu[end:]
    cpu=cpu.replace('rr_x68k_note_instruction(pc,1)','rr_x68k_note(pc,1)')
    cpu=cpu.replace('    rr_x68k_note(pc,1);return 1;',
        '    /* Preserve the reference self-branch slice/IRQ boundary. */\n'
        '    if(!rr_x68k_exception_cycles && REG_PC==pc &&\n'
        '       (op->instruction.mnemonic==MN_BRA || op->instruction.mnemonic==MN_JMP))USE_ALL_CYCLES();\n'
        '    if(rr_x68k_cpu_stopped) {\n'
        '        if(m68ki_remaining_cycles>=CYC_INSTRUCTION[REG_IR])m68ki_remaining_cycles=CYC_INSTRUCTION[REG_IR];\n'
        '        else USE_ALL_CYCLES();\n    }\n'
        '    rr_x68k_note(pc,1);return 1;')
    cpu=cpu[:cpu.index('void rr_x68k_native_bind(void)')]
    cpu+='\nvoid rr_x68k_reset_instruction(void) {m68ki_output_reset();rr_x68k_exception_cycles=CYC_RESET+CYC_INSTRUCTION[0x4e70];}\n'
    write_changed(project/'cpu.c',cpu)
    math=(SDK/'native/md_prefetch.inc').read_text(encoding='utf-8')
    math=math[math.index('unsigned rr_md_multiply_clocks('):math.index('void rr_md_arithmetic_phase(')]
    write_changed(project/'arithmetic.c','#include "cpu.h"\n'+math.replace('rr_md_','rr_x68k_')+
        '\nvoid rr_x68k_arithmetic_phase(unsigned base,unsigned ea,int multiply){(void)multiply;rr_x68k_arithmetic_cycles=base+ea;}\n')
    original=(geo/'src/m68k/m68kcpu.c').read_text(encoding='utf-8')
    anchor='''\t\t\tREG_IR = m68ki_read_imm_16();
\t\t\tm68ki_instruction_jump_table[REG_IR]();
\t\t\tUSE_CYCLES(CYC_INSTRUCTION[REG_IR]);'''
    if original.count(anchor)!=1:raise ValueError('Pinned interpreter dispatch changed.')
    adapted='#include "observe.h"\nextern int rr_x68k_native_execute(uint32_t,unsigned*);\n'+original.replace(anchor,'''
            { unsigned native_clocks;
              rr_x68k_before(REG_PC);
              if(rr_x68k_native_execute(REG_PC,&native_clocks)) { USE_CYCLES(native_clocks); }
              else {
                rr_x68k_note(REG_PC,0);
                REG_IR=m68ki_read_imm_16();
                m68ki_instruction_jump_table[REG_IR]();
                USE_CYCLES(CYC_INSTRUCTION[REG_IR]);
              }
            }''')
    write_changed(project/'m68kcpu.c',adapted)
    decoded=[]
    # Authored guard fixtures occupy a reserved diagnostic address outside
    # the initial 2/4 MiB profile. They are executed only by --guard-checks.
    diagnostic=[(0xbffe00,'303c12344e75'),(0xbffe00,'303c56784e75'),
                (0xbffe00,'70014e75'),(0xbffe20,'303c12344e75'),
                (0xbffe40,'4e7227007001'),(0xbffe60,'4e404e71'),
                (0xbffe80,'4e73'),(0xbffea0,'ff004e71'),(0xbffeb0,'4e71'),
                (0xbffe90,'60fe'),(0xbffe94,'6000fffe'),(0xbffe9a,'4ef900bffe9a'),
                (0xe7ffc0,'303c12344e75'),(0xe7ffc0,'303c56784e75'),
                (0xea1fc0,'303c12344e75'),(0xea1fc0,'303c56784e75')]
    if samples:
        decode_samples=sorted(set(samples+diagnostic))
        listing=project/'snapshots.txt'
        listing.write_text(''.join(f'{pc:06x} {words}\n' for pc,words in decode_samples),encoding='ascii')
        run([decode_tool,listing,project/'decoded.json'],log=project/'decode.log')
        decoded=json.loads((project/'decoded.json').read_text(encoding='utf-8'))
    unique={}
    for ins in decoded:
        name=names[ins['mnemonic']]
        if name not in bodies:continue
        unique[(ins['addr'],tuple(ins['words'][:ins['word_count']]))]=ins
    instructions=sorted(unique.values(),key=lambda s:(s['addr'],tuple(s['words'])))
    # Reuse existing structural specialization; source/extension descriptors
    # and full live words remain guarded, including multiple versions per PC.
    forms={};entries=[];chunks=[[] for _ in range(16)];declarations=[]
    for ins in instructions:
        name=names[ins['mnemonic']];key=structural_key(ins)
        if key not in forms:
            symbol=f'rr_x68k_form_{len(forms)}';forms[key]=symbol
            body=structural_body(ins,name,bodies[name]).replace('rr_ng_','rr_x68k_')
            chunks[(ins['words'][0]>>1)%16].append(f'M68kiStatus {symbol}(const M68KInstr *compiled,uint32_t *next_pc) {{\n{body}}}\n')
            declarations.append(f'extern M68kiStatus {symbol}(const M68KInstr*,uint32_t*);\n')
        entries.append('{'+instruction_literal(canonical_instruction(ins,name),name)+f',{forms[key]}'+'}')
    steps=project/'steps';steps.mkdir(exist_ok=True)
    for n,chunk in enumerate(chunks):write_changed(steps/f'part{n:02}.c','#include "step_semantics.h"\n'+''.join(chunk))
    groups=[];last=None
    for index,ins in enumerate(instructions):
        if ins['addr']!=last:groups.append([ins['addr'],index,1]);last=ins['addr']
        else:groups[-1][2]+=1
    index_source='#include "cpu.h"\n#include "observe.h"\n#include <stddef.h>\n'+''.join(declarations)
    index_source+='static const RrX68NativeStep entries[]={'+(',\n'.join(entries) if entries else '{0}')+'};\n'
    index_source+='static const struct {uint32_t pc,start,count;} groups[]={'+(','.join('{%d,%d,%d}'%tuple(g) for g in groups) if groups else '{0}')+'};\n'
    index_source+=f'''const RrX68NativeStep *rr_x68k_lookup(uint32_t pc) {{
    if(pc&1u)return NULL;
    unsigned lo=0,hi={len(groups)}u;
    while(lo<hi) {{unsigned mid=lo+(hi-lo)/2;if(groups[mid].pc<pc)lo=mid+1;else hi=mid;}}
    if(lo=={len(groups)}u || groups[lo].pc!=pc)return NULL;
    for(unsigned k=0;k<groups[lo].count;++k) {{
        const RrX68NativeStep *s=&entries[groups[lo].start+k];int same=1;
        for(unsigned n=0;n<(unsigned)s->instruction.word_count;++n) {{
            uint16_t word;
            if(!rr_x68k_code_word(pc+n*2,&word) || word!=s->instruction.words[n]){{same=0;break;}}
        }}
        if(same)return s;
    }}
    return NULL;
}}
'''
    write_changed(steps/'index.c',index_source)
    result={'schema':1,'machine_base':machine_base,'reference_pin':PX68K_REV,'reference_cpu_pin':GEOLITH_REV,'samples':len(samples),'instructions':len(instructions),
        'forms':len(forms),'pcs':len(groups),'semantics_sha256':hashlib.sha256(semantics.encode()).hexdigest(),
        'ram_variants':sum(i['addr']<0xc00000 for i in instructions),
        'text_vram_variants':sum(0xe00000<=i['addr']<0xe80000 for i in instructions),
        'scsi_rom_variants':sum(0xea0000<=i['addr']<0xea2000 for i in instructions),
        'ipl_variants':sum(i['addr']>=0xfc0000 for i in instructions),
        'cpu_source_sha256':hashlib.sha256(original.encode()).hexdigest(),'private_only':True,
        'observation_sources':list(receipts)}
    (project/'generation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


def build(work:Path,px:Path,sdl:Path,jobs:int=8,machine_base:str|None=None,extra=()):
    """Configure and build; `extra` carries machine-source settings (see the converter)."""
    cmake,generator=toolchain()
    run([cmake,'-S',SDK/'native/x68000_native','-B',work/'build','-G',generator,*cmake_target_args(),
         f'-DPX68K_DIR={px.as_posix()}',f'-DCMAKE_PREFIX_PATH={sdl.resolve().as_posix()}',
         f'-DRR_X68000_GENERATED={work.as_posix()}',
         f'-DRR_X68000_MACHINE_BASE={machine_base or MACHINE_BASE}',*extra],log=work/'build.log')
    run([cmake,'--build',work/'build','--config','Release','--parallel',str(jobs)],log=work/'build.log')
    return build_executable(work/'build/reference','RetroRecomp-X68000-Native')


def prepare_native(output,disks,ipl,cgrom,executable,generation,ram_mib=2):
    from smsrecomp.x68000_media import build_manifest,MachineConfig
    manifest=build_manifest(disks,ipl,cgrom,config=MachineConfig(ram_bytes=ram_mib*1024*1024),
                            initial_drives=(0,1 if len(disks)>1 else None))
    allowed={item['identity'] for item in generation['observation_sources']}
    if manifest.sha256 not in allowed:
        raise ValueError('No qualified private CPU observation matches this exact media/firmware/configuration set.')
    target=prepare_bundle(output,disks,ipl,cgrom,executable,title='Cho Ren Sha 68k - Native',ram_mib=ram_mib)
    receipt=output/'datas/reference-build.json'
    data=json.loads(receipt.read_text(encoding='utf-8'))
    data.update(stage='x68000-guarded-native-prototype',native_cpu=True,cpu_generation=generation,
        coverage='See the run report: counts describe observed paths only.',private_development_only=True)
    _atomic_text(receipt,json.dumps(data,indent=2)+'\n')
    _atomic_text(output/'README-NATIVE.txt',
        'RetroRecomp X68000 native CPU prototype, private development only.\n'
        'The game and OS load from your disks; covered MC68000 instructions are offline native code.\n'
        'Unknown or changed code uses the counted interpreter fallback.\n'
        'Controls: arrows / gamepad direction, W/X / gamepad A/B; Start sends Enter.\n'
        'F1: help; F11: pause; Shift+F1: confirm restart. H and P are guest keys.\n'
        'F8: save state; F9: load state.\n'
        'Ctrl+Alt+K: full guest keyboard, including guest F8/F9 instead of save shortcuts.\n'
        'Ctrl+Alt+M: capture/release mouse; Ctrl+Alt+F: rapid fire while button 1 is held.\n'
        'Click the active game to capture its mouse. Mouse profiles also accept keyboard/pad movement.\n'
        'Automatic loading acceleration is disabled. Original disk timing is preserved.\n'
        'Holding F5 fast-forwards manually; release it to return to normal cadence.\n'
        'Ctrl+Alt+Page Up/Down: previous/next disk in FDD0; add Shift for FDD1.\n'
        'Ctrl+Alt+Backspace: eject (add Shift for FDD1).\n'
        'Standalone cold starts and restarts use the initial disks; F9 restores the saved disks.\n'
        'Ctrl+Alt+Enter: fullscreen; Ctrl+Alt+Q: quit. Stick clicks are unassigned.\n'
        'States, settings, SRAM and writable disk copies stay under datas. Originals are preserved.\n'
        'State files require this exact media/firmware/RAM identity and a compatible runtime build.\n'
        'No cross-platform snapshot compatibility is promised. Keep this entire folder.\n'
        'Automatic disk changes use qualified exact-set rules only; other requests remain manual.\n'
        'This developer build and its game data must not be redistributed.\n')
    _atomic_text(output/'README-REFERENCE.txt','This private folder runs the guarded native CPU prototype. See README-NATIVE.txt.\n')
    notices={
        'RetroRecomp-LICENSE.txt':SDK/'LICENSE',
        'GenesisRecomp-LICENSE.md':ROOT/'.deps/segagenesisrecomp/LICENSE.md',
        'GenesisRecomp-LICENSE-recompiler.txt':ROOT/'.deps/segagenesisrecomp/LICENSE-recompiler',
        'GenesisRecomp-THIRD-PARTY-LICENSES.md':ROOT/'.deps/segagenesisrecomp/THIRD-PARTY-LICENSES.md',
        'm68k-recomp-core-LICENSE.txt':ROOT/'.deps/segagenesisrecomp/external/m68k-recomp-core/LICENSE',
        'Geolith-LICENSE.txt':ROOT/'.deps/geolith-libretro/LICENSE',
        'Musashi-header-notice.txt':ROOT/'.deps/geolith-libretro/src/m68k/m68k.h',
    }
    for name,source in notices.items():
        if not source.is_file():raise ValueError('Required CPU notice is missing: '+str(source))
        _atomic_text(output/'reference-notices'/name,source.read_text(encoding='utf-8'))
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--observations',type=Path,action='append',default=[])
    parser.add_argument('--source',type=Path,default=ROOT/'.deps/px68k-reference')
    parser.add_argument('--sdl',type=Path,default=ROOT/'.deps/SDL/install')
    parser.add_argument('--jobs',type=int,default=8)
    parser.add_argument('--prepare',type=Path)
    parser.add_argument('--disk',type=Path,action='append',default=[])
    parser.add_argument('--ipl',type=Path);parser.add_argument('--cgrom',type=Path)
    args=parser.parse_args()
    if not 1<=args.jobs<=8:parser.error('Use one to eight build jobs.')
    if args.prepare and not (args.disk and args.ipl and args.cgrom):parser.error('--prepare requires --disk, --ipl and --cgrom.')
    work=private_path(args.work);px=ensure_sources(args.source)
    generation=generate(work,observations(args.observations),px,source_receipts(args.observations))
    print(json.dumps(generation),flush=True)
    executable=build(work,px,args.sdl,args.jobs);print(executable,flush=True)
    if args.prepare:print(prepare_native(args.prepare,args.disk,args.ipl,args.cgrom,executable,generation),flush=True)

if __name__=='__main__':main()
