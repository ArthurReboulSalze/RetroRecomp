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
    # Quick states keep the register block only: the cycle tables and host
    # callbacks after it are this process's addresses, never the saved ones.
    return (core + '\nvoid cps1_m68k_use_cycles(int cycles) { USE_CYCLES(cycles); }\n'
            'int cps1_m68k_instruction_cycles(void) { return CYC_INSTRUCTION[REG_IR]; }\n'
            '#include <stddef.h>\n#include <string.h>\n'
            'unsigned cps1_m68k_state_bytes(void) { return (unsigned)offsetof(m68ki_cpu_core, cyc_instruction); }\n'
            'void cps1_m68k_state_get(void *dst) { memcpy(dst, &m68ki_cpu, cps1_m68k_state_bytes()); }\n'
            'void cps1_m68k_state_set(const void *src) { memcpy(&m68ki_cpu, src, cps1_m68k_state_bytes()); }\n')


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


def _build(project: Path, target: str, prefix: Path | None = None) -> Path:
    from .core import run, toolchain
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args(),
         *([f'-DCMAKE_PREFIX_PATH={prefix.as_posix()}'] if prefix else [])],
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


# ------------------------------------------------------------------ game build

HOST_FILES = ('cps1_host.c', 'cps1_host.h', 'cps1_main.c', 'console16_host_ui.c', 'console16_state.c',
              'console16_state.h', 'console16_video.h', 'platform_io.c', 'platform_io.h',
              'embedded_resources.h', 'retro_console16.h', 'retro_menu.c', 'retro_menu.h', 'font6x10.h',
              'font10x20.h', 'runtime_i18n.h', 'runtime_catalog.inc', 'retro_keyboard.h',
              'display_settings.h', 'autofire.h', 'game_options.h', 'audio_filter.h', 'audio_cushion.h',
              'scanline_sdl.h', 'scanlines.h', 'xbr_sdl.h', 'xbr_filter.h', 'scale2x.h', 'gun16.h')
NOTICE_FILES = ('LICENSE', 'licenses/cps1-machine.md', 'licenses/cps1-ymfm.md', 'licenses/musashi.md',
                'licenses/superzazu-z80.md', 'licenses/segagenesisrecomp.md', 'licenses/SDL2.md',
                'licenses/xbr.md', 'licenses/Noto.md', 'licenses/UPX.md')
PACK_REGIONS = ('board.txt', 'maincpu.bin', 'audiocpu.bin', 'gfx.bin', 'oki.bin', 'stars.bin')
# Host pad bits (native/cps1_host.h): buttons 1-6, Start, Coin, Up, Down, Left, Right.
ACTIONS = {**{f'button{n}': n - 1 for n in range(1, 7)}, 'start': 6, 'coin': 7,
           'joystick_up': 8, 'joystick_down': 9, 'joystick_left': 10, 'joystick_right': 11}


def input_table(game: dict) -> list[tuple[int, int, int, int]]:
    """(port, mask, action, player) for players 1 and 2; other controls stay released."""
    rows = []
    for index, port in enumerate(('IN0', 'IN1', 'IN2', 'IN3')):
        for mask, name, player in game['inputs'].get(port, {}).get('inputs', ()):
            if name[:-1] in ('start', 'coin') and name[-1:].isdigit():
                name, player = name[:-1], int(name[-1])
            if name in ACTIONS and player in (1, 2):
                rows.append((index, mask, ACTIONS[name], player))
    if not rows:
        raise ValueError('CPS-1 set ' + game['set'] + ' has no mapped player controls.')
    return rows


def pack(board: Path) -> bytes:
    """The board folder as resource 201: "CPZ1", size, zlib(CPS1PACK table + regions)."""
    import zlib
    entries = [(name, (board / name).read_bytes()) for name in PACK_REGIONS if (board / name).is_file()]
    raw = b'CPS1PACK' + len(entries).to_bytes(4, 'little')
    raw += b''.join(name.encode('ascii').ljust(16, b'\0') + len(data).to_bytes(4, 'little') for name, data in entries)
    raw += b''.join(data for _, data in entries)
    return b'CPZ1' + len(raw).to_bytes(4, 'little') + zlib.compress(raw, 9)


def state_config(game_set, title: str) -> str:
    """Quick states load only into the same romset and the same board/runtime sources."""
    import hashlib, importlib, json, os
    from .core import executable_name, module_fingerprint
    abi = hashlib.sha256(b'CPS1-frame-state-v1:' + YMFM_REVISION.encode())
    for name in ('cps1_machine.c', 'cps1_machine.h', 'cps1_oki.c', 'cps1_oki.h', 'cps1_opm.cpp',
                 'cps1_host.c', 'cps1_native.c'):
        abi.update((ASSETS / 'native' / name).read_bytes())
    for name in ('smsrecomp.cps1_build', 'smsrecomp.cps1_codegen'):
        importlib.import_module(name); abi.update(name.encode()); abi.update(module_fingerprint(name).encode())
    if os.name != 'nt':
        from .platforms import target_id
        abi.update(target_id().encode())
    stem = Path(executable_name(title)).stem if os.name == 'nt' else executable_name(title)
    return ('#pragma once\n#define RR16_STATE_SYSTEM 4\n#define RR16_STATE_PAL 0\n'
            f'#define RR16_STATE_ROM {json.dumps(game_set.sha256)}\n#define RR16_STATE_ABI {json.dumps(abi.hexdigest())}\n'
            f'#define RR16_STATE_NAME {json.dumps(stem)}\n')


def prepare_game(project: Path, game_set, game: dict, *, title: str, observations: dict | None = None,
                 presentation: dict | None = None) -> dict:
    """A playable game project: native board, shared 16-bit host and embedded regions."""
    import hashlib, json
    from . import __version__
    from .cps1_board import write_board
    from .megadrive_codegen import write_changed
    board = project / 'board'
    write_board(board, game_set, game)
    analysis = prepare_native(project, board, game, observations)
    for name in HOST_FILES:
        _write(project / name, (ASSETS / 'native' / name).read_text(encoding='utf-8'))
    geolith, ymfm = sources()
    notices = [(ASSETS / name).read_text(encoding='utf-8') for name in NOTICE_FILES if (ASSETS / name).is_file()]
    recomp = ROOT / '.deps/segagenesisrecomp/external/m68k-recomp-core/LICENSE'
    for file in (ymfm / 'LICENSE', geolith / 'src/m68k/readme.txt', recomp):
        if file.is_file():
            notices.append(file.read_text(encoding='utf-8'))
    for file in (geolith / 'src/z80/z80.c', geolith / 'deps/miniz/miniz.c'):
        notices.append(file.read_text(encoding='utf-8').split('*/', 1)[0] + '*/')
    write_changed(project / 'notices.txt', '\n\n'.join(notices))
    packed = project / 'board.pack'
    payload = pack(board)
    if not packed.is_file() or packed.read_bytes() != payload:
        packed.write_bytes(payload)
    from .core import executable_name
    from .metadata import write_game_metadata
    icon, artwork = False, {'embedded': False, 'source': 'disabled'}
    if presentation is not None:
        from .artwork import prepare_icon
        from .paths import boxart_cache_directory
        artwork = prepare_icon(project, presentation['rom_path'], title,
            presentation.get('boxart_dir') or ROOT / 'BoxArt', explicit=presentation.get('cover'),
            online=presentation.get('online_cover', True), enabled=presentation.get('use_cover', True),
            cache_directory=boxart_cache_directory('cps1'), system_id='cps1', emit=presentation.get('emit', print))
        icon = artwork['embedded']
    (project / 'artwork.json').write_text(json.dumps(artwork, indent=2), encoding='utf-8')
    metadata = write_game_metadata(project, title, executable_name(title), light_phaser=False, icon=icon,
                                   standard='arcade', system_id='cps1')
    (project / 'export-identity.bin').write_bytes(b'[Retro-Recomp]\0' + game_set.sha256.encode('ascii') + b'\0')
    write_changed(project / 'content.rc', '#pragma code_page(65001)\n'
                  f'201 RCDATA "{packed.as_posix()}"\n203 RCDATA "notices.txt"\n'
                  '205 RCDATA "export-identity.bin"\n#include "game_resources.rc"\n')
    from .resources import embed_resources
    embed_resources(project, {201: packed, 203: project / 'notices.txt', 205: project / 'export-identity.bin'})
    table = ','.join('{%d,%d,%d,%d}' % row for row in input_table(game))
    write_changed(project / 'cps1_game.h', '#pragma once\n#define RR_CPS1_TITLE ' + json.dumps(title) +
                  '\n#define RR_CPS1_VERSION ' + json.dumps(__version__) +
                  f'\n#define RR_CPS1_ROTATION {int(game["rotation"])}\n#define RR_CPS1_INPUT_TABLE {table}\n')
    write_changed(project / 'retro_gun_game.h', '#pragma once\n#define RR16_GUN 0\n')
    write_changed(project / 'retro16_state_config.h', state_config(game_set, title))
    cmake = (project / 'CMakeLists.txt').read_text(encoding='utf-8')
    cmake = cmake[:cmake.index('add_executable(cps1_native_probe')] + f'''if(WIN32)
  enable_language(RC)
else()
  enable_language(ASM)
endif()
target_compile_definitions(cps1_native PUBLIC CPS1_FEEDBACK=1)
set(GEO "{geolith.as_posix()}")
find_package(SDL2 CONFIG REQUIRED)
add_executable(game cps1_main.c cps1_host.c console16_host_ui.c console16_state.c retro_menu.c
  "${{GEO}}/deps/miniz/miniz.c")
target_include_directories(game PRIVATE "${{GEO}}/deps/miniz")
if(WIN32)
  target_sources(game PRIVATE content.rc)
  target_link_libraries(game PRIVATE shell32 user32 gdi32)
else()
  target_sources(game PRIVATE embedded_resources.c embedded_resources.S)
  target_link_libraries(game PRIVATE m)
endif()
target_link_libraries(game PRIVATE cps1_native SDL2::SDL2-static)
target_compile_definitions(game PRIVATE SDL_MAIN_HANDLED RR16_CPS1=1 [[RR_RECOMP_VERSION="{__version__}"]])
if(MSVC)
  target_link_options(game PRIVATE /SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup)
endif()
'''
    write_changed(project / 'CMakeLists.txt', cmake)
    from .feedback import stage
    stage(project, 'cps1', game_set.sha256)
    return {'analysis': analysis, 'artwork': artwork, 'windows_metadata': metadata,
            'packed_sha256': hashlib.sha256(payload).hexdigest()}


def build_game(project: Path) -> Path:
    sdl = ROOT / '.deps/SDL/install'
    if not (sdl / 'cmake/SDL2/SDL2Config.cmake').exists():
        from .core import dependencies
        _, sdl, _, _ = dependencies()
    return _build(project, 'game', sdl)
