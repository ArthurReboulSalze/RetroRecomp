"""The Amiga 1200's CPU, Moira's 68EC020 as vAmiga builds it, against Musashi's 68EC020 on random instructions (gate G10, an independent model).

    python -B tools/amiga_m68020_vectors.py [--workspace DIR] [--cases N] [--seed S]
        (needs a compiler, a first build of vAmiga's Core and the workspace's copy of Musashi; no ROM, no Kickstart)

Musashi (Karl Stenerud, MIT) is the oracle: another author's model of the 68EC020, taken from the copy the workspace already holds
(`.deps/px68k-reference/m68000/musashi`), copied into the work folder with its configuration set for a 68EC020, compiled for this check only
and never into a game. The code under test is the Moira that vAmiga's Core compiles, adapted by `retrorecomp/amiga_vamiga.py`, set to the
68EC020 (`native/amiga_machine/m68020_vector_checks.cpp`). Both run one random instruction from one random state over one random memory;
registers, SR, PC and the bytes written are compared, not the clocks. Every difference is put in a family with a written reason (`FAMILIES`): a
difference in no family fails. It shows agreement between two models of the CPU, not the silicon, and nothing about the Amiga's chips.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MUSASHI = Path('.deps/px68k-reference/m68000/musashi')
MUSASHI_FILES = ('m68k.h', 'm68kcpu.c', 'm68kcpu.h', 'm68kops.c', 'm68kops.h', 'm68kfpu.c', 'm68kmmu.h', 'softfloat')

# The configuration of the copy: a 68EC020, no callback of the host, no prefetch or trace model (the cases set T clear).
CONFIG = """#ifndef M68KCONF__HEADER
#define M68KCONF__HEADER
#define OPT_OFF 0
#define OPT_ON 1
#define OPT_SPECIFY_HANDLER 2
#define M68K_COMPILE_FOR_MAME OPT_OFF
#define M68K_EMULATE_010 OPT_ON
#define M68K_EMULATE_EC020 OPT_ON
#define M68K_EMULATE_020 OPT_ON
#define M68K_EMULATE_030 OPT_OFF
#define M68K_EMULATE_040 OPT_OFF
#define M68K_SEPARATE_READS OPT_OFF
#define M68K_SIMULATE_PD_WRITES OPT_OFF
#define M68K_EMULATE_INT_ACK OPT_OFF
#define M68K_INT_ACK_CALLBACK(A) your_int_ack_handler_function(A)
#define M68K_EMULATE_BKPT_ACK OPT_OFF
#define M68K_BKPT_ACK_CALLBACK() your_bkpt_ack_handler_function()
#define M68K_EMULATE_TRACE OPT_OFF
#define M68K_EMULATE_RESET OPT_OFF
#define M68K_RESET_CALLBACK() your_reset_handler_function()
#define M68K_CMPILD_HAS_CALLBACK OPT_OFF
#define M68K_CMPILD_CALLBACK(v,r) your_cmpild_handler_function(v,r)
#define M68K_RTE_HAS_CALLBACK OPT_OFF
#define M68K_RTE_CALLBACK() your_rte_handler_function()
#define M68K_TAS_HAS_CALLBACK OPT_OFF
#define M68K_TAS_CALLBACK() your_tas_handler_function()
#define M68K_ILLG_HAS_CALLBACK OPT_OFF
#define M68K_ILLG_CALLBACK(opcode) op_illg(opcode)
#define M68K_EMULATE_FC OPT_OFF
#define M68K_SET_FC_CALLBACK(A) your_set_fc_handler_function(A)
#define M68K_MONITOR_PC OPT_OFF
#define M68K_SET_PC_CALLBACK(A) your_pc_changed_handler_function(A)
#define M68K_INSTRUCTION_HOOK OPT_OFF
#define M68K_INSTRUCTION_CALLBACK(pc) your_instruction_hook_function(pc)
#define M68K_EMULATE_PREFETCH OPT_OFF
#define M68K_EMULATE_ADDRESS_ERROR OPT_OFF
#define M68K_LOG_ENABLE OPT_OFF
#define M68K_LOG_1010_1111_A_LINE OPT_OFF
#define M68K_LOG_FILEHANDLE some_file_handle
#define M68K_EMULATE_PMMU OPT_OFF
#define M68K_USE_64_BIT OPT_ON
#endif
"""

# Families, by Moira's handler: the fields a difference may touch, its kind and why (16 November 2026, 200,000 cases, seed 1). A difference
# outside its family fails. Kinds: no-fpu (the A1200 has none), undefined (the manual leaves it undefined), oracle (the manual sides with
# Moira, this copy of Musashi is wrong), referee (the two models disagree and a third model or the hardware must say which is right).
_FRAME = {'isp', 'usp', 'sr', 'pc', 'memory'}
_REGS = {f'd{i}' for i in range(8)} | {f'a{i}' for i in range(7)}
_NO_FPU = ('The Amiga 1200 has no floating-point unit: Moira takes the line-F exception for a coprocessor instruction, Musashi models a 68881 '
           'and runs it. Moira is the A1200.')
FAMILIES: dict[str, tuple[set, str, str]] = {
    'CpBcc': (_FRAME, 'no-fpu', _NO_FPU), 'CpGen': (_FRAME | _REGS, 'no-fpu', _NO_FPU), 'CpScc': (_FRAME, 'no-fpu', _NO_FPU),
    'CpDbcc': (_FRAME, 'no-fpu', _NO_FPU), 'CpTrapcc': (_FRAME, 'no-fpu', _NO_FPU), 'CpSave': (_FRAME, 'no-fpu', _NO_FPU),
    'CpRestore': (_FRAME, 'no-fpu', _NO_FPU),
    'Chk': ({'sr', 'memory'}, 'undefined', 'CHK: Z, V and C are undefined (MC68020 manual); the SR stacked by the exception carries them.'),
    'ChkCmp2': (_FRAME, 'undefined', 'CHK2/CMP2: N and V are undefined; the exception frame carries the SR.'),
    'Divs': ({'sr', 'memory'}, 'undefined', 'DIVS: N and Z are undefined on overflow; a division by zero stacks the SR.'),
    'Divu': ({'sr', 'memory'}, 'undefined', 'DIVU: N and Z are undefined on overflow; a division by zero stacks the SR.'),
    'Divl': ({'sr', 'memory'}, 'undefined', 'DIVx.L: N and Z are undefined on overflow; a division by zero stacks the SR.'),
    'Mull': (_REGS, 'undefined', 'MULx.L with Dh equal to Dl: the result in that register is undefined.'),
    'AbcdRg': (_REGS | {'sr'}, 'undefined', 'ABCD: N and V undefined, and the result of digits that are not BCD is undefined.'),
    'AbcdEa': ({'sr', 'memory'}, 'undefined', 'ABCD: N and V undefined, and the result of digits that are not BCD is undefined.'),
    'NbcdRg': ({'sr'}, 'undefined', 'NBCD: N and V undefined.'),
    'NbcdEa': ({'sr', 'memory'}, 'undefined', 'NBCD: N and V undefined, and the result of digits that are not BCD is undefined.'),
    'PackPd': ({'isp', 'usp', 'memory'}, 'oracle', 'PACK -(Ax),-(Ay): this copy of Musashi takes the first byte read (the higher address) as the '
               'high digit; the manual makes it the low one, as Moira and UAE do; also the byte step of -(A7).'),
    'UnpkPd': ({'isp', 'usp', 'memory'}, 'oracle', 'UNPK -(Ax),-(Ay): the same byte order as PACK, written; also the byte step of -(A7).'),
    'Rte': ({'memory'}, 'oracle', 'RTE with a frame format the 68EC020 does not know: the format error stacks the address of the RTE (Moira, the '
            'manual); this Musashi stacks the next one.'),
    'Link': ({'memory'}, 'referee', 'LINK A7: the value of A7 pushed. The manual pushes the decremented A7 (Musashi, UAE); Moira pushes the value '
             'before. Real code does not link A7; to check with a third model.'),
    'MovemRgEa': ({'memory'}, 'referee', 'MOVEM to -(An) with An in the list: the value of An written; to check with a third model.'),
    'BitFieldEa': (_REGS | {'memory', 'sr'}, 'referee', 'Bit-field instructions in memory: the bytes written for a field across bytes; to check '
                   'with a third model.'),
    'BitFieldDn': (_REGS | {'sr'}, 'referee', 'Bit-field instructions on a register (BFFFO, BFEXTS): the result; to check with a third model.'),
    'Cas2': (_REGS | {'sr'}, 'referee', 'CAS2 when a comparison fails: which value is loaded into the compare registers; to check with a third model.'),
}


def write_cmake(work: Path, core: Path, musashi: Path) -> Path:
    machine = (ROOT / 'native' / 'amiga_machine').as_posix()
    folder = work / 'cmake'
    folder.mkdir(parents=True, exist_ok=True)
    m = musashi.as_posix()
    (folder / 'CMakeLists.txt').write_text(f"""cmake_minimum_required(VERSION 3.20)
project(RetroAmiga020Vectors LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_subdirectory("{core.as_posix()}" vacore)
foreach(RR_TARGET VACore rvlib utlib)
    if(TARGET ${{RR_TARGET}})
        set_property(TARGET ${{RR_TARGET}} PROPERTY INTERFACE_COMPILE_OPTIONS "")
    endif()
endforeach()
add_library(musashi STATIC "{m}/m68kcpu.c" "{m}/m68kops.c" "{m}/softfloat/softfloat.c")
target_include_directories(musashi PUBLIC "{m}")
if(NOT MSVC)
    target_compile_options(musashi PRIVATE -w)
endif()
add_executable(m68020_vector_checks "{machine}/m68020_vector_checks.cpp")
target_link_libraries(m68020_vector_checks PRIVATE VACore musashi)
if(MSVC)
    target_link_options(m68020_vector_checks PRIVATE /FORCE:MULTIPLE)
else()
    target_link_options(m68020_vector_checks PRIVATE -Wl,--allow-multiple-definition)
endif()
if(WIN32)
    target_link_libraries(m68020_vector_checks PRIVATE ws2_32)
endif()
""", encoding='utf-8', newline='\n')
    return folder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--workspace', type=Path, default=ROOT, help='where .deps and .build live')
    parser.add_argument('--cases', type=int, default=200000)
    parser.add_argument('--seed', type=int, default=1)
    arguments = parser.parse_args()
    from retrorecomp import amiga_vamiga, paths
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args
    paths.ROOT = amiga_vamiga.ROOT = arguments.workspace.resolve()
    work = paths.ROOT / '.build' / 'amiga-m68020-vectors'
    work.mkdir(parents=True, exist_ok=True)
    source = paths.ROOT / MUSASHI
    if not (source / 'm68kops.c').is_file():
        print(f'Musashi is not in this workspace ({MUSASHI}).', file=sys.stderr)
        return 2
    musashi = work / 'musashi'
    shutil.rmtree(musashi, ignore_errors=True)
    musashi.mkdir()
    for name in MUSASHI_FILES:
        (shutil.copytree if (source / name).is_dir() else shutil.copy2)(source / name, musashi / name)
    (musashi / 'm68kconf.h').write_text(CONFIG, encoding='ascii', newline='\n')
    core = amiga_vamiga.adapt(amiga_vamiga.source(), work / 'vamiga')
    folder = write_cmake(work, core, musashi)
    build = work / 'build'
    cmake, generator = toolchain()
    run([cmake, '-S', folder, '-B', build, '-G', generator, *cmake_target_args(), '-DCMAKE_BUILD_TYPE=Release'], log=work / 'build.log', cwd=work)
    run([cmake, '--build', build, '--parallel', build_jobs(), '--target', 'm68020_vector_checks'], log=work / 'build.log', timeout=7200, cwd=work)
    program = build_executable(build, 'm68020_vector_checks')
    import subprocess
    done = subprocess.run([str(program), str(arguments.cases), str(arguments.seed)], capture_output=True, text=True, timeout=7200)
    lines = [json.loads(line) for line in done.stdout.splitlines() if line.startswith('{')]
    (work / 'differences.jsonl').write_text(done.stdout, encoding='utf-8')
    if not lines or 'cases' not in lines[-1]:
        print('The check did not finish:', done.returncode, done.stderr[-400:], file=sys.stderr)
        return 1
    totals, cases = lines[-1], lines[:-1]
    def family(case):
        entry = FAMILIES.get(case['handler'])
        return case['handler'] if entry and set(case['fields'].split(',')) <= entry[0] else None
    counts = Counter(family(c) for c in cases)
    unknown = [c for c in cases if family(c) is None]
    kinds = Counter()
    for name, n in counts.items():
        if name:
            kinds[FAMILIES[name][1]] += n
    summary = {'cases': totals['cases'], 'equal': totals['equal'], 'differ': totals['differ'], 'stopped': totals['stopped'],
               'by_kind': dict(kinds), 'unclassified': len(unknown),
               'families': [{'handler': h, 'count': n, 'kind': FAMILIES[h][1], 'reason': FAMILIES[h][2]} for h, n in counts.most_common() if h]}
    (work / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'families'}))
    for item in summary['families']:
        print(f"  {item['count']:7d}  {item['handler']:<12} {item['kind']:<9} {item['reason'][:110]}")
    for case in unknown[:20]:
        print('  unclassified:', json.dumps(case))
    return 0 if not unknown else 1


if __name__ == '__main__':
    sys.exit(main())
