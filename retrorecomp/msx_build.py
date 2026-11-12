"""The MSX on the banked Z80 chain: the generated bodies of a cartridge and its BIOS, the learning passes, the game project
(headless check, reference, game) and the comparison of the native run with the reference.

* The generator is the shared banked Z80 generator built for the MSX's own machine description (systems/msx.py,
  `MSX_MACHINE`: a region map, the cartridge as source 0 and the BIOS as source 1, one wait state per M1 cycle), in its own
  folders (`core.dependencies(emit, MSX_MACHINE)`).
* The generator reads the cartridge as `rom.sms` beside `game.toml` and the BIOS from `banked.sources`; it keys positions modulo
  the image size, so it gets the cartridge padded to whole banks with FFh, exactly as the machine sees it.
* Code the interpreter ran from RAM is learned (`--learn`) and translated with byte guards on the next generation
  (`native.patterns`), at most three passes.
* The project builds three programs from the same bodies and machine: `msx_check` (the headless native run), `msx_reference`
  (the reference interpreter alone on the same machine) and `game` (the player, with the host kit and SDL2).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Callable

# The fields a native run must give exactly as the reference does: the CPU (main and shadow registers, I, R, IM, IFF, WZ),
# time and interrupts, RAM, VRAM, the picture of the last frame and a running hash of every frame, the sound, the PSG, the
# slots and the cartridge banks, and the watched bytes.
COMPARED = ('frames', 'cycles', 'interrupts', 'pc', 'sp', 'af', 'bc', 'de', 'hl', 'ix', 'iy', 'af2', 'bc2', 'de2', 'hl2',
            'i', 'r', 'im', 'iff1', 'iff2', 'wz', 'halted', 'primary', 'secondary', 'vdp_regs', 'vdp_status', 'vram_fnv',
            'ram_fnv', 'frame_fnv', 'frame_trace', 'audio_samples', 'audio_fnv', 'psg', 'psg_latch', 'port_c', 'blocks',
            'watch')
GAME_TOML = '''# MSX: the cartridge is source 0 of the region map; the BIOS is named in banked.sources.
[game]
output_prefix = "game"
platform = "sms"
rom = "rom.sms"
crc32 = 0x00000000
[mapper]
kind = "sega"
[functions]
extra = []
blacklist = []
'''
# The machine and the glue, from native/msx_machine; the host kit's companions, from native/.
MACHINE_FILES = ('msx_machine.c', 'msx_machine.h', 'msx_video.c', 'msx_psg.c', 'msx_cart.c', 'msx_glue.inc',
                 'msx_native_main.c', 'msx_reference_main.c', 'msx_player.c')
KIT_FILES = ('retro_menu.c', 'retro_menu.h', 'font6x10.h', 'font10x20.h', 'runtime_i18n.h', 'runtime_catalog.inc',
             'retro_keyboard.h', 'display_settings.h', 'autofire.h', 'game_options.h', 'audio_filter.h', 'audio_cushion.h',
             'stereo_fir.h', 'audio_output.inc', 'scanline_sdl.h', 'scanlines.h', 'xbr_sdl.h', 'xbr_filter.h', 'scale2x.h',
             'platform_io.c', 'platform_io.h', 'embedded_resources.h', 'console16_video.h', 'runtime_feedback.h',
             'runtime_feedback.c', 'runtime_feedback_sdl.h')
BUILD_TIMEOUT = 2 * 3600


class MsxBuildError(RuntimeError):
    """The generator, the build or a run failed."""


def _flags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def padded(image: bytes, mapper: str | None) -> bytes:
    """The cartridge as the machine sees it: whole banks (16 KiB for ASCII 16, else 8 KiB), padded with FFh."""
    unit = 0x4000 if mapper == 'ascii16' else 0x2000
    return image + b'\xFF' * (-len(image) % unit)


def generator(emit: Callable[[str], None] = print) -> tuple[Path, Path]:
    """The MSX machine's own Z80 -> C generator (built once, in its own folders) and the engine checkout."""
    from . import core
    from .platforms import build_executable
    from .systems.msx import MSX_MACHINE
    from .toolchain import suffix
    engine, _, _, _ = core.dependencies(emit, MSX_MACHINE)
    return build_executable(core.ROOT / '.deps' / (MSX_MACHINE.generator_build + suffix()), 'SmsRecomp'), engine


def instrument_reference(path: Path) -> None:
    """The reference interpreter's own interrupt acceptance exported (behaviour unchanged): the reference runner reads /INT
    after each instruction, as the native loop does."""
    source = path.read_text(encoding='utf-8')
    if 'static inline void process_interrupts(z80* const z)' not in source:
        raise MsxBuildError('Pinned CPU source changed: process_interrupts')
    if 'msx_reference_accept' not in source:
        source += '\nvoid msx_reference_accept(z80* const z) { process_interrupts(z); }\n'
        path.write_text(source, encoding='utf-8', newline='\n')


def _write(path: Path, data: bytes) -> None:
    if not path.is_file() or path.read_bytes() != data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def generate(work: Path, cartridge: bytes, bios: bytes, emit: Callable[[str], None] = print, *, keep_rom: bool = True) -> None:
    """The bodies of `cartridge` (padded as the machine sees it) and `bios` in `work/generated`, with the learned patterns."""
    from .cpu import prepare_cpu_headers, prepare_reference
    from .paths import ASSETS
    from .systems.msx import MSX_MACHINE
    from .z80_chain import banked_runtime
    tool, engine = generator(emit)
    (work / 'generated').mkdir(parents=True, exist_ok=True)
    for stale in (work / 'generated').glob('game_banked_ops_*.c'):
        stale.unlink()
    _write(work / 'rom.sms', cartridge)
    _write(work / 'bios.rom', bios)
    (work / 'banked.sources').write_text(str((work / 'bios.rom').resolve()) + '\n', encoding='utf-8', newline='\n')
    (work / 'game.toml').write_text(GAME_TOML, encoding='utf-8', newline='\n')
    log = work / 'generate.log'
    with log.open('w', encoding='utf-8') as out:
        result = subprocess.run([str(tool), '--game', str(work / 'game.toml'), '--banked-step'], stdout=out,
                                stderr=subprocess.STDOUT, timeout=BUILD_TIMEOUT, creationflags=_flags())
    if not keep_rom:
        (work / 'rom.sms').unlink(missing_ok=True)
    if result.returncode:
        raise MsxBuildError(f'The Z80 generator failed (see {log}).')
    prepare_cpu_headers(work, engine)
    prepare_reference(work, engine, m1_counter=MSX_MACHINE.counts_m1)
    instrument_reference(work / 'runtime_reference.c')
    (work / 'msx_banked_loop.inc').write_text(banked_runtime(MSX_MACHINE, ASSETS), encoding='utf-8', newline='\n')


def stage_sources(work: Path) -> None:
    """The machine, the glue, the mains and the host kit's companions, copied beside the generated bodies."""
    from . import hostkit
    from .paths import ASSETS
    for name in MACHINE_FILES:
        _write(work / name, (ASSETS / 'native' / 'msx_machine' / name).read_bytes())
    for name in KIT_FILES:
        _write(work / name, (ASSETS / 'native' / name).read_bytes())
    hostkit.stage(work, 'msx')
    # What the computers' adapters share (the guest keyboard, the captured mouse), included by the MSX adapter.
    _write(work / 'hostkit' / 'adapters' / 'rrhk_computer.inc',
           (ASSETS / 'native' / 'hostkit' / 'adapters' / 'rrhk_computer.inc').read_bytes())


def project_cmake(version: str, game: bool) -> str:
    from . import hostkit
    machine = 'msx_machine.c msx_video.c msx_psg.c msx_cart.c'
    lines = [
        'cmake_minimum_required(VERSION 3.20)',
        'project(RetroMsx LANGUAGES C)',
        'set(CMAKE_C_STANDARD 11)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'if(MSVC)', '  add_compile_options(/utf-8 /wd4996 /wd4244 /wd4267)', 'endif()',
        'file(GLOB bodies "generated/game_banked_ops_*.c")',
        'add_library(msx_bodies OBJECT generated/game_banked_index.c ${bodies})',
        'target_include_directories(msx_bodies PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
        'target_compile_definitions(msx_bodies PRIVATE SMSRECOMP_BANKED_AOT)',
        f'add_executable(msx_check msx_native_main.c {machine} runtime_reference.c $<TARGET_OBJECTS:msx_bodies>)',
        f'add_executable(msx_reference msx_reference_main.c {machine} runtime_reference.c)',
        'foreach(target msx_check msx_reference)',
        '  target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
        '  target_compile_definitions(${target} PRIVATE SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS)',
        '  if(NOT WIN32)', '    target_link_libraries(${target} PRIVATE m)', '  endif()',
        'endforeach()',
    ]
    if game:
        kit = ' '.join(hostkit.sources('msx'))
        lines += [
            'if(WIN32)', '  enable_language(RC)', 'else()', '  enable_language(ASM)', 'endif()',
            'find_package(SDL2 CONFIG REQUIRED)',
            f'add_executable(game msx_player.c {machine} runtime_reference.c retro_menu.c platform_io.c runtime_feedback.c {kit}',
            '  $<TARGET_OBJECTS:msx_bodies>)',
            'target_include_directories(game PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
            'if(WIN32)', '  target_sources(game PRIVATE content.rc)',
            '  target_link_libraries(game PRIVATE shell32 user32 gdi32)',
            'else()', '  target_sources(game PRIVATE embedded_resources.c embedded_resources.S)',
            '  target_link_libraries(game PRIVATE m)', 'endif()',
            'target_link_libraries(game PRIVATE SDL2::SDL2-static)',
            f'target_compile_definitions(game PRIVATE SDL_MAIN_HANDLED SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS '
            f'[[RR_RECOMP_VERSION="{version}"]])',
            'if(MSVC)', '  target_link_options(game PRIVATE /SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup)', 'endif()',
            'if(WIN32 AND NOT MSVC)',
            '  target_link_options(game PRIVATE -Wl,--subsystem,windows -Wl,--entry,mainCRTStartup)', 'endif()',
        ]
    return '\n'.join(lines) + '\n'


def build(work: Path, targets: tuple[str, ...], emit: Callable[[str], None] = print) -> dict[str, Path]:
    """Configure and build `targets` of the project in `work` (the SDL2 of the converter for the game)."""
    from . import __version__, core
    from .platforms import build_executable, sdl_install
    game = 'game' in targets
    _write(work / 'CMakeLists.txt', project_cmake(__version__, game).encode('utf-8'))
    cmake, generator_kind = core.toolchain()
    log = work / 'build.log'
    extra = [f'-DCMAKE_PREFIX_PATH={Path(sdl_install()).as_posix()}'] if game else []
    core.run([cmake, '-S', work, '-B', work / 'build', '-G', generator_kind, *core.cmake_target_args(),
              '-DCMAKE_BUILD_TYPE=Release', *extra], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    for target in targets:
        core.run([cmake, '--build', work / 'build', '--config', 'Release', '--target', target, '--parallel',
                  core.build_jobs()], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    return {target: build_executable(work / 'build', target) for target in targets}


def run(exe: Path, args: list[str], image: bytes | None = None, timeout: int = 1800) -> dict:
    """One headless run; its JSON report. The cartridge, when given, reaches the program on its standard input."""
    result = subprocess.run([str(exe), *args, *(['--cart', '-'] if image is not None else [])], input=image,
                            capture_output=True, timeout=timeout, creationflags=_flags())
    if result.returncode:
        raise MsxBuildError(f'{exe.name} failed: {result.stderr.decode(errors="replace").strip()[-500:]}')
    return json.loads(result.stdout)


def differences(native: dict, reference: dict) -> dict:
    """The compared fields that differ (a field missing on either side differs)."""
    return {key: (native.get(key), reference.get(key)) for key in COMPARED
            if key not in native or key not in reference or native[key] != reference[key]}


def learn(work: Path, cartridge: bytes, bios: bytes, args: list[str], emit: Callable[[str], None] = print, *,
          passes: int = 3, keep_rom: bool = True, insert: bool = True) -> tuple[Path, list[int]]:
    """Generate, build the headless check and run it with learning, at most `passes` times: it stops when nothing fell back
    or nothing new was seen. Returns the check program and the fallback steps of each pass. `insert` False runs the machine
    with an empty cartridge slot (the bodies are still generated from `cartridge`)."""
    patterns = work / 'native.patterns'
    counts = []
    for _ in range(passes):
        generate(work, cartridge, bios, emit, keep_rom=keep_rom)
        stage_sources(work)
        check = build(work, ('msx_check', 'msx_reference'), emit)['msx_check']
        learned = work / 'learned.txt'
        learned.unlink(missing_ok=True)
        trial = run(check, [*args, '--learn', str(learned)], cartridge if insert else None)
        counts.append(trial['fallback_steps'])
        if not trial['fallback_steps'] or not learned.is_file():
            break
        known = set(patterns.read_text(encoding='utf-8').split()) if patterns.is_file() else set()
        seen = set(learned.read_text(encoding='utf-8').split())
        if seen <= known:
            break
        patterns.write_text(''.join(f'{line}\n' for line in sorted(known | seen)), encoding='utf-8', newline='\n')
    else:
        # The last pass still learned something: the bodies are generated once more, so the checked program (and the game
        # built beside it) hold every pattern the report counts.
        generate(work, cartridge, bios, emit, keep_rom=keep_rom)
        check = build(work, ('msx_check', 'msx_reference'), emit)['msx_check']
    return check, counts


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean(work: Path) -> None:
    shutil.rmtree(work, ignore_errors=True)
