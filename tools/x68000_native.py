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
from retrorecomp.core import run,toolchain
from retrorecomp.platforms import build_executable,cmake_target_args,sdl_install
from retrorecomp.m68000 import adapt_semantics,operation_bodies,mnemonic_names,instruction_literal
from retrorecomp.neogeo_codegen import canonical_instruction,structural_key,structural_body
from retrorecomp.megadrive_codegen import write_changed


def private_path(path:Path)->Path:
    path=path.absolute()
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (path,*path.parents)):
        raise ValueError('Private CPU work must not use linked directories.')
    path=path.resolve()
    if not path.is_relative_to((ROOT/'.build').resolve()):
        raise ValueError('Generated CPU data must stay in project .build.')
    return path


# ---- IPL spans (standardization 6b) ----------------------------------------------------------------------------
# The IPL window (0xFC0000-0xFFFFFD) holds the player's own 128 KiB IPL, mapped twice. Every code variant observed
# there equals the IPL bytes at its address (checked on every local identity), so an observation file keeps only
# where instructions start: a span (address, offset in the IPL, length) with its entries [position in the span,
# length in words]. The words are read from the player's IPL when the file is read; none is stored. The fold is
# exact and reversible (expanding the entries gives back the same variants, minus their hit counts), and a file
# without spans (schema 1) reads as before. Other windows (RAM, text VRAM, the SCSI stub built into the machine)
# stay variants.
IPL_BYTES=128*1024
IPL_SPANS=((0xfc0000,0,IPL_BYTES),(0xfe0000,0,IPL_BYTES))
IPL_CODE_END=0xfffffe  # the last word of the window is not fetchable as code (rr_x68k_code_word)


def ipl_view(data:bytes)->bytes|None:
    """The 128 KiB the machine maps at 0xFC0000, or None when it does not map this file as it is.

    native/x68000_machine/machine.c replaces an IPL that carries the SCSI boot marker (0x00FC0000 at file offsets
    0x10600-0x10C00) with a small stub of its own, so the file's bytes are not what executes there."""
    if len(data)!=IPL_BYTES:return None
    if any(data[n:n+4]==b'\x00\xfc\x00\x00' for n in range(0x10600,0x10c00,2)):return None
    return bytes(data)


def span_variants(spans,ipl:bytes|None)->list[tuple[int,str]]:
    """Expand span entries into (pc, words hex) with the IPL they were observed with."""
    result=[]
    for span in spans:
        if not isinstance(span,dict) or span.get('source')!='ipl':raise ValueError('Unknown observation span.')
        address,offset,length=span.get('address'),span.get('offset'),span.get('length')
        if (address,offset,length) not in IPL_SPANS:raise ValueError('Unsupported observation span.')
        view=ipl_view(ipl) if ipl is not None else None
        if view is None:raise ValueError('Observation spans need the IPL they were observed with.')
        if span.get('sha256')!=hashlib.sha256(ipl).hexdigest():
            raise ValueError('Observation spans belong to another IPL.')
        entries=span.get('entries')
        if not isinstance(entries,list):raise ValueError('Invalid observation span entries.')
        for entry in entries:
            if (not isinstance(entry,list) or len(entry)!=2 or any(type(n) is not int for n in entry)
                    or entry[0]&1 or not 0<=entry[0]<length or not 1<=entry[1]<=8):
                raise ValueError('Invalid observation span entry.')
            position,count=entry
            if address+position+count*2>IPL_CODE_END:raise ValueError('Span entry crosses the code window.')
            result.append((address+position,bytes(view[(offset+position+n)%IPL_BYTES] for n in range(count*2)).hex()))
    return result


def fold_ipl(variants,ipl:bytes|None,spans=())->tuple[list[dict],list[dict]]:
    """Move the variants that equal the player's IPL into span entries, merged with `spans`.

    Returns (remaining variants, spans). A variant that differs from the IPL stays a variant, and so does every
    variant when this IPL is not mapped as it is (SCSI-marked file) or no IPL is given: nothing is guessed."""
    view=ipl_view(ipl) if ipl is not None else None
    digests={span.get('sha256') for span in spans}
    if ipl is not None:digests.add(hashlib.sha256(ipl).hexdigest())
    if len(digests)>1:raise ValueError('Observation spans belong to another IPL.')
    entries={}
    for span in spans:
        if not isinstance(span,dict) or (span.get('address'),span.get('offset'),span.get('length')) not in IPL_SPANS:
            raise ValueError('Unsupported observation span.')
        entries.setdefault(span['address'],set()).update((position,count) for position,count in span['entries'])
    rest=[]
    for row in variants:
        pc=row['pc'];raw=bytes.fromhex(row['words'])
        span=next((s for s in IPL_SPANS if view is not None and s[0]<=pc<s[0]+s[2]),None)
        if (span is None or pc&1 or len(raw)%2 or len(raw)>16 or pc+len(raw)>IPL_CODE_END or
                raw!=bytes(view[(span[1]+pc-span[0]+n)%IPL_BYTES] for n in range(len(raw)))):
            rest.append(row);continue
        entries.setdefault(span[0],set()).add((pc-span[0],len(raw)//2))
    digest=next(iter(digests),None)
    return rest,[{'source':'ipl','sha256':digest,'address':a,'offset':o,'length':n,
                  'entries':[list(e) for e in sorted(entries[a])]} for a,o,n in IPL_SPANS if entries.get(a)]


def span_count(record)->int:
    return sum(len(span['entries']) for span in record.get('spans',()))


def observations(paths,ipl:bytes|None=None)->list[tuple[int,str]]:
    """Every (pc, words) a file set names: its variants, and its spans expanded with `ipl`."""
    result=set()
    for path in paths:
        if path.stat().st_size>128*1024*1024:raise ValueError('CPU observation file exceeds its bound.')
        record=json.loads(path.read_text(encoding='utf-8'))
        if (record.get('schema') not in (1,2) or record.get('truncated') is not False
                or (record['schema']==1 and 'spans' in record)):
            raise ValueError('CPU observations are incomplete or unknown.')
        samples=[(item.get('pc'),item.get('words')) for item in record.get('variants',[])]
        samples+=span_variants(record.get('spans',[]),ipl)
        for pc,words in samples:
            if type(pc) is not int or pc&1 or not (0<=pc<0xc00000 or 0xe00000<=pc<0xe80000 or 0xea0000<=pc<0xea2000 or 0xfc0000<=pc<0xfffffe):
                raise ValueError('Unsupported observed code aperture.')
            if not isinstance(words,str) or not re.fullmatch('[0-9a-f]{4,32}',words) or len(words)%4:
                raise ValueError('Invalid bounded CPU words.')
            if pc+len(words)//2> (0xc00000 if pc<0xc00000 else 0xe80000 if pc<0xe80000 else 0xea2000 if pc<0xea2000 else 0x1000000):
                raise ValueError('CPU sample crosses a mapping boundary.')
            result.add((pc,words))
            if len(result)>1048576:raise ValueError('Combined CPU observation bound exceeded.')
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
    from retrorecomp.neogeo_codegen import decoder_tool
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
 target_compile_options(x68_decode PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8;/wd4996>")
endif()
''')
    cmake,generator=toolchain()
    run([cmake,'-S',directory,'-B',directory/'build','-G',generator,*cmake_target_args()],log=project/'build.log')
    run([cmake,'--build',directory/'build','--config','Release','--parallel','4'],log=project/'build.log')
    return build_executable(directory/'build','x68_decode')


# Machine sources under the native CPU: 'hissorii' (default since phase 4) or
# 'current' (pinned px68k-libretro, comparison only); docs/history/x68000/X68000_GPL_FREE_PLAN.md.
MACHINE_BASE=os.environ.get('RR_X68000_MACHINE_BASE','hissorii')
if MACHINE_BASE not in ('current','hissorii'):raise ValueError('RR_X68000_MACHINE_BASE must be current or hissorii.')


# Original RetroRecomp chained native run (MIT). Appended to the generated
# cpu.c on the hissorii base; the single-step rr_x68k_native_execute above it
# stays for the authored guard checks.
NATIVE_RUN=r'''
/* Consecutive guarded instructions run in one call while the system byte of
 * SR is unchanged. Between two instructions Musashi's loop only latches T1
 * (clear for a chain) and REG_PPC; interrupts are still sampled at slice ends
 * and after privileged SR changes, as before. The status register stays in
 * g_cpu during the run: no board device reads it, the trace receives it. */
static uint32_t rr_x68k_miss_pc=UINT32_MAX;
int rr_x68k_native_run(void) {
    uint32_t pc=REG_PC;
    /* A run that stopped on an unguarded successor already looked it up. */
    if(pc==rr_x68k_miss_pc){rr_x68k_miss_pc=UINT32_MAX;return 0;}
    rr_x68k_miss_pc=UINT32_MAX;
    if(rr_x68k_force_reference)return 0;
    const RrX68NativeStep *op=rr_x68k_lookup(pc);
    if(!op)return 0;
    const int chain=!FLAG_T1,tracing=rr_x68k_trace_active();
    const uint16_t mask=(uint16_t)CPU_SR_MASK;
    g_cpu.SR=(uint16_t)m68ki_get_sr();
    const uint16_t system=g_cpu.SR&0xff00u;
    uint32_t *other=FLAG_S?&REG_USP:&REG_ISP;
    g_cpu.USP=*other;
    unsigned ram=0,ipl=0;
    for(;;) {
        g_cpu.PC=pc;
        rr_x68k_cpu_stopped=0;rr_x68k_exception_cycles=rr_x68k_trace_suppressed=rr_x68k_arithmetic_cycles=0;
        rr_x68k_illegal_ea=g_rte_pending=0;
        unsigned cost=dynamic_cycles(&op->instruction);
        BusErrFlag=0;REG_IR=op->instruction.words[0];
        uint32_t next_pc=pc+op->instruction.byte_length;
        M68kiStatus status=op->execute(&op->instruction,&next_pc);
        if(status!=M68KI_OK || rr_x68k_illegal_ea) {
            fprintf(stderr,"Native MC68000 failed at %06x / %04x: %u\n",pc,REG_IR,(unsigned)status);exit(4);
        }
        if((pc&0xffffffu)>=0xfc0000u)++ipl;else ++ram;
        const int mn=op->instruction.mnemonic;
        if(rr_x68k_exception_cycles || rr_x68k_cpu_stopped || rr_x68k_trace_suppressed ||
           (g_cpu.SR&0xff00u)!=system || mn==MN_MOVE_SR || mn==MN_RTE || mn==MN_STOP ||
           mn==MN_ORI_TO_SR || mn==MN_ANDI_TO_SR || mn==MN_EORI_TO_SR) {
            /* The single-instruction exit, unchanged; it ends the run. */
            m68ki_set_sr_noint_nosp(g_cpu.SR);
            if(FLAG_S)REG_USP=g_cpu.USP;else REG_ISP=g_cpu.USP;
            REG_PC=next_pc;
            if(rr_x68k_cpu_stopped)CPU_STOPPED|=STOP_LEVEL_STOP;
            if(rr_x68k_trace_suppressed)m68ki_clear_trace();
            unsigned clocks=rr_x68k_exception_cycles?rr_x68k_exception_cycles:rr_x68k_arithmetic_cycles?rr_x68k_arithmetic_cycles:cost;
            switch(mn) {
            case MN_MOVE_SR:if(!op->instruction.dst_is_ea)m68ki_check_interrupts();break;
            case MN_RTE:case MN_STOP:case MN_ORI_TO_SR:case MN_ANDI_TO_SR:case MN_EORI_TO_SR:
                m68ki_check_interrupts();break;
            default:break;
            }
            if(!rr_x68k_exception_cycles && REG_PC==pc && (mn==MN_BRA || mn==MN_JMP))USE_ALL_CYCLES();
            if(rr_x68k_cpu_stopped) {
                if(m68ki_remaining_cycles>=CYC_INSTRUCTION[REG_IR])m68ki_remaining_cycles=CYC_INSTRUCTION[REG_IR];
                else USE_ALL_CYCLES();
            }
            USE_CYCLES(clocks);
            break;
        }
        /* Musashi keeps only the implemented SR bits between instructions. */
        g_cpu.SR&=mask;
        *other=g_cpu.USP;
        REG_PC=next_pc;
        /* Preserve the reference self-branch slice/IRQ boundary. */
        if(REG_PC==pc && (mn==MN_BRA || mn==MN_JMP))USE_ALL_CYCLES();
        USE_CYCLES(rr_x68k_arithmetic_cycles?rr_x68k_arithmetic_cycles:cost);
        if(!chain || GET_CYCLES()<=0) {m68ki_set_sr_noint_nosp(g_cpu.SR);break;}
        pc=next_pc;
        op=rr_x68k_lookup_next(op,pc);
        if(!op) {m68ki_set_sr_noint_nosp(g_cpu.SR);rr_x68k_miss_pc=pc;break;}
        REG_PPC=pc;
        if(tracing)rr_x68k_before_sr(pc,g_cpu.SR);
    }
    rr_x68k_note_native(ram,ipl);
    return 1;
}
'''

LOOKUP_NEXT='''/* The next instruction of a native run: a fallthrough or static target uses
 * the entry's link, anything else the page table. */
const RrX68NativeStep *rr_x68k_lookup_next(const RrX68NativeStep *previous,uint32_t pc) {
    const M68KInstr *ins=&previous->instruction;
    const uint32_t *link=links[previous-entries];
    pc&=0xffffffu;
    if(pc==((ins->addr+(uint32_t)ins->byte_length)&0xffffffu))return link[0]?guarded(link[0]-1u,pc):NULL;
    if(ins->has_target && pc==(ins->target_addr&0xffffffu) && !(pc&1u))return link[1]?guarded(link[1]-1u,pc):NULL;
    return rr_x68k_lookup(pc);
}
'''

# Forms on the hissorii base read their own absolute descriptor: every step
# is keyed by its exact 24-bit address, so relocating a copy is an identity.
# Only a PC whose high byte carries a flag (a JMP through such a pointer)
# needs the copy, as on the Neo Geo since 84ebeec: the fallthrough, branch
# targets and return addresses then keep the reference's upper PC byte.
FORM_COPY=('    M68KInstr decoded=*compiled;\n'
           '    rr_x68k_relocate_instruction(&decoded,g_cpu.PC);\n'
           '    const M68KInstr *ins=&decoded;\n')
FORM_ABSOLUTE=('    M68KInstr decoded;\n'
               '    const M68KInstr *ins=compiled;\n'
               '    if(g_cpu.PC>0xffffffu){decoded=*compiled;rr_x68k_relocate_instruction(&decoded,g_cpu.PC);ins=&decoded;}\n')


def shared_registers(text:str)->str:
    """Native steps use Musashi's register file directly: no per-instruction
    copy of D0-D7/A0-A7. The active stack pointer stays Musashi's A7 (dar[15])."""
    return text.replace('g_cpu.D[','REG_D[').replace('g_cpu.A[','REG_A[')


def generate(project:Path,samples:list[tuple[int,str]],px:Path,receipts=(),machine_base:str|None=None)->dict:
    machine_base=machine_base or MACHINE_BASE
    alias=shared_registers
    project=private_path(project);project.mkdir(parents=True,exist_ok=True)
    engine=ROOT/'.deps/segagenesisrecomp'
    geo=ROOT/'.deps/geolith-libretro'
    from retrorecomp.neogeo_build import GEOLITH_REV
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
    from retrorecomp.console16 import REPOSITORIES
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
    write_changed(project/'step_semantics.h','#pragma once\n#include "m68kcpu.h"\n'
        '#include "cpu.h"\n#include <stddef.h>\n'
        '#define s_illegal_ea rr_x68k_illegal_ea\nstatic int interp_ea_read_cost(int,M68KSize);\n'
        'static int game_instruction_hook_site(uint32_t pc){(void)pc;return 0;}\n'
        'static int genesis_game_instruction_hook(uint32_t pc){(void)pc;return 0;}\n'
        'static void discover(uint32_t pc){(void)pc;}\n'+alias(helper+'\n'+timing))
    for name,path in [('m68k_decoder.h',engine/'external/m68k-recomp-core/common/m68k_decoder.h'),
                      ('rom_parser.h',engine/'recompiler/src/rom_parser.h')]:
        write_changed(project/name,path.read_text(encoding='utf-8'))
    header=(SDK/'native/neogeo_native.h').read_text(encoding='utf-8')
    header=header.replace('RR_NEOGEO_NATIVE_H','RR_X68000_NATIVE_CPU_H').replace('rr_ng_','rr_x68k_').replace('RrNgNativeStep','RrX68NativeStep')
    header=header.replace('/* Called before opcode fetch.', 'const RrX68NativeStep *rr_x68k_lookup(uint32_t pc);\n'
        'const RrX68NativeStep *rr_x68k_lookup_next(const RrX68NativeStep *previous,uint32_t pc);\n/* Called before opcode fetch.')
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
    end=cpu.index('    g_cpu.PC=pc;',begin)
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
    if machine_base=='hissorii':
        refetch=('    for(unsigned n=0;n<(unsigned)op->instruction.word_count;++n) {\n'
                 '        unsigned word=m68ki_read_imm_16();if(!n)REG_IR=word;\n    }\n')
        if cpu.count(refetch)!=1:raise ValueError('Pinned native fetch replay changed.')
        cpu=cpu.replace(refetch,'    /* The words are already guarded; a code fetch on this machine only\n'
                        '     * clears the bus-error latch (cpu_readmem24_word). */\n'
                        '    BusErrFlag=0;REG_IR=op->instruction.words[0];\n')
        cpu='#include <stdint.h>\nextern uint32_t BusErrFlag;\n'+cpu
    if 'g_cpu.D[n]=' in cpu or 'REG_D[n]=g_cpu' in cpu:raise ValueError('Native template copies registers again.')
    cpu=alias(cpu)
    cpu=cpu[:cpu.index('void rr_x68k_native_bind(void)')]
    cpu+='\nvoid rr_x68k_reset_instruction(void) {m68ki_output_reset();rr_x68k_exception_cycles=CYC_RESET+CYC_INSTRUCTION[0x4e70];}\n'
    if machine_base=='hissorii':cpu+=NATIVE_RUN
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
    if machine_base=='hissorii':
        adapted='#include "observe.h"\nextern int rr_x68k_native_run(void);\n'+original.replace(anchor,'''
            /* A native run consumes its own cycles, possibly for several instructions. */
            rr_x68k_before(REG_PC);
            if(!rr_x68k_native_run()) {
                rr_x68k_note(REG_PC,0);
                REG_IR=m68ki_read_imm_16();
                m68ki_instruction_jump_table[REG_IR]();
                USE_CYCLES(CYC_INSTRUCTION[REG_IR]);
            }''')
    else:adapted='#include "observe.h"\nextern int rr_x68k_native_execute(uint32_t,unsigned*);\n'+original.replace(anchor,'''
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
            if machine_base=='hissorii':
                if body.count(FORM_COPY)!=1:raise ValueError('Pinned native form prologue changed.')
                body=body.replace(FORM_COPY,FORM_ABSOLUTE)
            chunks[(ins['words'][0]>>1)%16].append(f'M68kiStatus {symbol}(const M68KInstr *compiled,uint32_t *next_pc) {{\n{body}}}\n')
            declarations.append(f'extern M68kiStatus {symbol}(const M68KInstr*,uint32_t*);\n')
        descriptor=ins if machine_base=='hissorii' else canonical_instruction(ins,name)
        entries.append('{'+instruction_literal(descriptor,name)+f',{forms[key]}'+'}')
    steps=project/'steps';steps.mkdir(exist_ok=True)
    for n,chunk in enumerate(chunks):write_changed(steps/f'part{n:02}.c','#include "step_semantics.h"\n'+alias(''.join(chunk)))
    groups=[];last=None
    for index,ins in enumerate(instructions):
        if ins['addr']!=last:groups.append([ins['addr'],index,1]);last=ins['addr']
        else:groups[-1][2]+=1
    # Direct page table: 4 KiB pages of the 24-bit space, one 16-bit slot per
    # even address giving the group within the page. One lookup per fetch
    # instead of a binary search; the live-word guard is a single compare.
    # Successor links: the group at each entry's fallthrough and static
    # target address (0: no compiled variant there). The live-word guard of
    # the successor is still compared; only the page-table walk is skipped.
    group_of={pc:index for index,(pc,start,count) in enumerate(groups)}
    links=[]
    for ins in instructions:
        fall=(ins['addr']+ins['byte_length'])&0xffffff
        taken=ins['target_addr']&0xffffff if ins['has_target'] else None
        links.append((group_of.get(fall,-1)+1,group_of.get(taken,-1)+1 if taken is not None else 0))
    pages={}
    for index,(pc,start,count) in enumerate(groups):
        page=pages.setdefault(pc>>12,{'base':index,'slots':{}})
        page['slots'][(pc&0xfff)>>1]=index-page['base']+1
    index_source='#include "cpu.h"\n#include "observe.h"\n#include <stddef.h>\n#include <string.h>\n'
    index_source+='#ifdef RR_X68000_BASE74\n#include "memory.h"\n#else\n#include "x68k/x68kmemory.h"\n#endif\n'
    index_source+=''.join(declarations)
    index_source+='static const RrX68NativeStep entries[]={'+(',\n'.join(entries) if entries else '{0}')+'};\n'
    index_source+='static const struct {uint32_t pc,start,count;} groups[]={'+(','.join('{%d,%d,%d}'%tuple(g) for g in groups) if groups else '{0}')+'};\n'
    for number,page in sorted(pages.items()):
        index_source+=f'static const uint16_t page_{number:x}[2048]={{'+','.join(f'[{slot}]={value}' for slot,value in sorted(page['slots'].items()))+'};\n'
    index_source+='static const struct {uint32_t base;const uint16_t *slots;} pages[4096]={'+','.join(
        f'[{number}]={{{page["base"]},page_{number:x}}}' for number,page in sorted(pages.items()))+'};\n'
    index_source+='''/* Host bytes of a code aperture, as the guards read them (never I/O). */
static const uint8_t *code_view(uint32_t pc,uint32_t *available) {
    if(pc<0xc00000u){*available=0xc00000u-pc;return MEM?MEM+pc:NULL;}
    if(pc>=0xe00000u&&pc<0xe80000u){*available=0xe80000u-pc;return TVRAM+(pc-0xe00000u);}
    if(pc>=0xea0000u&&pc<0xea2000u){*available=0xea2000u-pc;return SCSIIPL+(pc-0xea0000u);}
    if(pc>=0xfc0000u&&pc<0x1000000u){*available=0x1000000u-pc;return IPL?IPL+(pc-0xfc0000u):NULL;}
    return NULL;
}
/* The live-word guard of one address group: the first variant whose words
 * all match the current code bytes. */
static const RrX68NativeStep *guarded(unsigned group,uint32_t pc) {
#ifndef MSB_FIRST
    /* Little-endian hosts keep each 68000 word as a host 16-bit value. */
    uint32_t available;
    const uint8_t *code=code_view(pc,&available);
    if(!code)return NULL;
    for(unsigned k=0;k<groups[group].count;++k) {
        const RrX68NativeStep *s=&entries[groups[group].start+k];
        unsigned count=(unsigned)s->instruction.word_count,n=0;
        if(count*2u>available)continue;
        for(;n<count;++n) {uint16_t word;memcpy(&word,code+n*2u,2);if(word!=s->instruction.words[n])break;}
        if(n==count)return s;
    }
#else
    for(unsigned k=0;k<groups[group].count;++k) {
        const RrX68NativeStep *s=&entries[groups[group].start+k];int same=1;
        for(unsigned n=0;n<(unsigned)s->instruction.word_count;++n) {
            uint16_t word;
            if(!rr_x68k_code_word(pc+n*2,&word) || word!=s->instruction.words[n]){same=0;break;}
        }
        if(same)return s;
    }
#endif
    return NULL;
}
const RrX68NativeStep *rr_x68k_lookup(uint32_t pc) {
    pc&=0xffffffu;
    if(pc&1u)return NULL;
    const uint16_t *slots=pages[pc>>12].slots;
    if(!slots)return NULL;
    unsigned slot=slots[(pc&0xfffu)>>1];
    if(!slot)return NULL;
    return guarded(pages[pc>>12].base+slot-1u,pc);
}
'''
    if machine_base=='hissorii':
        # Absolute descriptors (see FORM_COPY) give each entry its own address.
        index_source+='static const uint32_t links[][2]={'+(','.join('{%d,%d}'%link for link in links) if links else '{0}')+'};\n'
        index_source+=LOOKUP_NEXT
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


def fresh_cache(build_dir:Path,source:Path)->None:
    """Drop a CMake build folder configured from another source location."""
    cache=build_dir/'CMakeCache.txt'
    if cache.is_file():
        for line in cache.read_text(encoding='utf-8',errors='replace').splitlines():
            if line.startswith('CMAKE_HOME_DIRECTORY:INTERNAL='):
                if Path(line.split('=',1)[1]).resolve()!=source.resolve():shutil.rmtree(build_dir)
                break


def build(work:Path,px:Path,sdl:Path,jobs:int=8,machine_base:str|None=None,extra=()):
    """Configure and build; `extra` carries machine-source settings (see the converter)."""
    cmake,generator=toolchain()
    fresh_cache(work/'build',SDK/'native/x68000_native')
    run([cmake,'-S',SDK/'native/x68000_native','-B',work/'build','-G',generator,*cmake_target_args(),
         f'-DPX68K_DIR={px.as_posix()}',f'-DCMAKE_PREFIX_PATH={sdl.resolve().as_posix()}',
         f'-DRR_X68000_GENERATED={work.as_posix()}',
         f'-DRR_X68000_MACHINE_BASE={machine_base or MACHINE_BASE}',*extra],log=work/'build.log')
    run([cmake,'--build',work/'build','--config','Release','--parallel',str(jobs)],log=work/'build.log')
    return build_executable(work/'build/reference','RetroRecomp-X68000-Native')


def prepare_native(output,disks,ipl,cgrom,executable,generation,ram_mib=2):
    from retrorecomp.x68000_media import build_manifest,MachineConfig
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
    parser.add_argument('--sdl',type=Path,default=sdl_install())
    parser.add_argument('--jobs',type=int,default=8)
    parser.add_argument('--prepare',type=Path)
    parser.add_argument('--disk',type=Path,action='append',default=[])
    parser.add_argument('--ipl',type=Path);parser.add_argument('--cgrom',type=Path)
    args=parser.parse_args()
    if not 1<=args.jobs<=8:parser.error('Use one to eight build jobs.')
    if args.prepare and not (args.disk and args.ipl and args.cgrom):parser.error('--prepare requires --disk, --ipl and --cgrom.')
    work=private_path(args.work);px=ensure_sources(args.source)
    generation=generate(work,observations(args.observations,args.ipl.read_bytes() if args.ipl else None),px,source_receipts(args.observations))
    print(json.dumps(generation),flush=True)
    executable=build(work,px,args.sdl,args.jobs);print(executable,flush=True)
    if args.prepare:print(prepare_native(args.prepare,args.disk,args.ipl,args.cgrom,executable,generation),flush=True)

if __name__=='__main__':main()
