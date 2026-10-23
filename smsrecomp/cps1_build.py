"""Build the CPS-1 runtimes from pinned sources.

The board itself is Retro-Recomp code adapted from MAME (BSD-3-Clause);
Musashi and the Z80 core come from the Geolith copy the Neo Geo already pins;
the YM2151 is ymfm (BSD-3-Clause), pinned here. Pinned checkouts are only
read: every compiled file is copied into the project folder first, and each
adaptation checks the exact upstream text it replaces.

Targets: cps1_probe (reference), cps1_trace_probe (per-instruction trace),
and, in a game's native project, cps1_native_probe (translated 68000/Z80).
"""
from __future__ import annotations
from pathlib import Path

from .paths import ROOT, ASSETS
from .platforms import build_executable, cmake_target_args, build_jobs

YMFM_REPOSITORY = 'https://github.com/aaronsgiles/ymfm.git'
YMFM_REVISION = '81aec25ccbb98f4873a255f7551ac4dadac59b4a'
NATIVE_FILES = ('cps1_machine.c', 'cps1_machine.h', 'cps1_oki.c', 'cps1_oki.h',
                'cps1_opm.cpp', 'cps1_opm.h', 'cps1_probe.c')
AOT_FILES = ('cps1_native.c', 'cps1_native.h', 'cps1_z80_native.h', 'm68000_state_helpers.h')
MUSASHI_FILES = ('m68k.h', 'm68kcpu.c', 'm68kcpu.h', 'm68kops.c', 'm68kops.h', 'm68kfpu.c', 'm68kmmu.h')
YMFM_FILES = ('ymfm.h', 'ymfm_fm.h', 'ymfm_fm.ipp', 'ymfm_opm.h', 'ymfm_opm.cpp')
MUSASHI_DISPATCH = ('\t\t\tREG_IR = m68ki_read_imm_16();\n\t\t\tm68ki_instruction_jump_table[REG_IR]();\n'
                    '\t\t\tUSE_CYCLES(CYC_INSTRUCTION[REG_IR]);')
Z80_DISPATCH = '    const uint8_t opcode = nextb(z);\n    cyc += exec_opcode(z, opcode);'


def sources() -> tuple[Path, Path]:
    from .neogeo_build import pinned_dependency, GEOLITH_REV
    geolith = pinned_dependency('geolith-libretro', 'https://github.com/libretro/geolith-libretro.git', GEOLITH_REV)
    ymfm = pinned_dependency('ymfm', YMFM_REPOSITORY, YMFM_REVISION)
    return geolith, ymfm


def _write(target: Path, text: str) -> None:
    from .megadrive_codegen import write_changed
    target.parent.mkdir(parents=True, exist_ok=True)
    write_changed(target, text)


def _replace_once(text: str, old: str, new: str, what: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f'Pinned {what} changed; CPS-1 adaptation refused.')
    return text.replace(old, new)


def musashi_core(geolith: Path, *, native: bool) -> str:
    core = (geolith / 'src/m68k/m68kcpu.c').read_text(encoding='utf-8')
    # Interrupts pending at a slice start are taken between instructions.
    core = 'extern int cps1_m68k_entry;\n' + _replace_once(
        core, '\t/* See if interrupts came in */\n\tm68ki_check_interrupts();\n',
        '\t/* See if interrupts came in */\n\tcps1_m68k_entry = 1;\n\tm68ki_check_interrupts();\n\tcps1_m68k_entry = 0;\n',
        'Musashi interrupt entry')
    if native:
        core = _replace_once(core, MUSASHI_DISPATCH, '''            extern int rr_cps1_native_run(void);
            extern void rr_cps1_note_instruction(uint32_t,int);
            /* A native run retires one or more guarded instructions and
             * charges the same clocks as the table below. */
            if(!rr_cps1_native_run()) {
                rr_cps1_note_instruction(REG_PC,0);
                REG_IR=m68ki_read_imm_16();
                m68ki_instruction_jump_table[REG_IR]();
                USE_CYCLES(CYC_INSTRUCTION[REG_IR]);
            }''', 'Musashi dispatch')
    # Bus waits outside an instruction's own timing (VPA autovector sync), and
    # the clocks of an SR write that unmasks an interrupt inside its handler.
    return (core + '\nvoid cps1_m68k_use_cycles(int cycles) { USE_CYCLES(cycles); }\n'
            'int cps1_m68k_instruction_cycles(void) { return CYC_INSTRUCTION[REG_IR]; }\n')


def z80_core(geolith: Path, *, native: bool) -> str:
    from .neogeo_z80 import adapt_source
    source = adapt_source((geolith / 'src/z80/z80.c').read_text(encoding='utf-8'))
    if not native:
        return source
    source = _replace_once(source, Z80_DISPATCH, '''    if(!rr_cps1_z80_try(z,&cyc)) {
        rr_cps1_z80_note_fallback(z->pc);
        const uint8_t opcode=nextb(z);cyc+=exec_opcode(z,opcode);
    }''', 'Z80 dispatch')
    source = _replace_once(source, 'static unsigned exec_opcode(z80* const z, uint8_t opcode);',
        '#include "cps1_z80_native.h"\nstatic int rr_cps1_z80_try(z80*,unsigned*);\n'
        'static unsigned exec_opcode(z80* const z, uint8_t opcode);', 'Z80 declarations')
    return _replace_once(source, '#undef GET_BIT', '''#include "cps1_z80_steps.inc"
static int rr_cps1_z80_try(z80 *z,unsigned *cycles) {
    if(rr_cps1_force_reference || rr_cps1_force_z80_reference)return 0;
    uint32_t offset;const RrCps1Z80Step *op=NULL;
    if(rr_cps1_z80_code_location(z->pc,&offset))op=rr_cps1_z80_native_lookup(offset);
    else if(z->pc>=0xd000u && z->pc<0xd800u)op=rr_cps1_z80_ram_lookup(z->pc);
    if(!op)return 0;
    for(unsigned n=0;n<4;++n)if(op->mask&(1u<<n)) {
        uint8_t actual;if(!rr_cps1_z80_code_byte((uint16_t)(z->pc+n),&actual) || actual!=op->bytes[n])return 0;
    }
    ++rr_cps1_native_z80;*cycles=op->execute(z);return 1;
}
#undef GET_BIT''', 'Z80 helpers end')


def _engine(project: Path, *, native: bool) -> None:
    geolith, ymfm = sources()
    for name in NATIVE_FILES + (AOT_FILES if native else ()):
        _write(project / name, (ASSETS / 'native' / name).read_text(encoding='utf-8'))
    for name in MUSASHI_FILES:
        _write(project / 'engine/m68k' / name, (geolith / 'src/m68k' / name).read_text(encoding='utf-8'))
    _write(project / 'engine/m68k/m68kconf.h', (ASSETS / 'native/cps1_m68kconf.h').read_text(encoding='utf-8'))
    _write(project / 'engine/m68k/m68kcpu.c', musashi_core(geolith, native=native))
    _write(project / 'engine/z80/z80.h', (geolith / 'src/z80/z80.h').read_text(encoding='utf-8'))
    _write(project / 'engine/z80/z80.c', z80_core(geolith, native=native))
    for name in YMFM_FILES:
        _write(project / 'engine/ymfm' / name, (ymfm / 'src' / name).read_text(encoding='utf-8'))


CMAKE_HEAD = '''cmake_minimum_required(VERSION 3.20)
project(RetroCps1 LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
if(MSVC)
  add_compile_options(/utf-8 /wd4996 /wd4244 /wd4267)
endif()
set(CPS1_BOARD cps1_machine.c cps1_oki.c cps1_opm.cpp
  engine/m68k/m68kcpu.c engine/m68k/m68kops.c engine/z80/z80.c engine/ymfm/ymfm_opm.cpp)
function(cps1_library name)
  add_library(${name} STATIC ${CPS1_BOARD} ${ARGN})
  target_include_directories(${name} PUBLIC . engine/m68k engine/z80 engine/ymfm)
  if(MSVC)
    target_compile_definitions(${name} PUBLIC __BYTE_ORDER__=1234 __ORDER_LITTLE_ENDIAN__=1234)
  endif()
endfunction()
'''


def prepare_reference(project: Path) -> Path:
    _engine(project, native=False)
    _write(project / 'CMakeLists.txt', CMAKE_HEAD + '''cps1_library(cps1_reference)
add_executable(cps1_probe cps1_probe.c)
target_link_libraries(cps1_probe PRIVATE cps1_reference)
# Diagnostic variant: per-instruction PC and cycle trace (--cpu-trace).
cps1_library(cps1_reference_trace)
target_compile_definitions(cps1_reference_trace PUBLIC CPS1_TRACE=1)
add_executable(cps1_trace_probe cps1_probe.c)
target_link_libraries(cps1_trace_probe PRIVATE cps1_reference_trace)
''')
    return project


def prepare_native(project: Path, board: Path, game: dict, observations: dict | None = None) -> dict:
    """Generate the game's translated code and its native CMake project."""
    from .cps1_codegen import generate
    _engine(project, native=True)
    geolith, _ = sources()
    from .neogeo_z80 import adapt_source
    analysis = generate(project, board, game, adapt_source((geolith / 'src/z80/z80.c').read_text(encoding='utf-8')),
                        observations)
    _write(project / 'CMakeLists.txt', CMAKE_HEAD + '''file(GLOB CPS1_STEPS "${CMAKE_CURRENT_SOURCE_DIR}/steps/cps1_step_*.c")
cps1_library(cps1_native cps1_native.c cps1_arithmetic.c ${CPS1_STEPS})
target_compile_definitions(cps1_native PUBLIC CPS1_NATIVE=1)
add_executable(cps1_native_probe cps1_probe.c)
target_link_libraries(cps1_native_probe PRIVATE cps1_native)
''')
    return analysis


def _build(project: Path, target: str) -> Path:
    from .core import run, toolchain
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()],
        log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--target', target,
         '--parallel', build_jobs()], log=project / 'build.log', timeout=3600)
    return build_executable(project / 'build', target)


def build_reference(project: Path | None = None, target: str = 'cps1_probe') -> Path:
    project = project or ROOT / '.build' / 'cps1-reference'
    prepare_reference(project)
    return _build(project, target)


def build_native(board: Path, game: dict, observations: dict | None = None,
                 project: Path | None = None) -> tuple[Path, dict]:
    project = project or ROOT / '.build' / 'cps1-native' / game['set']
    analysis = prepare_native(project, board, game, observations)
    return _build(project, 'cps1_native_probe'), analysis
