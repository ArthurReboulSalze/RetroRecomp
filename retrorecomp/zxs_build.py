"""The ZX Spectrum on the banked Z80 chain: the machine image a converted snapshot starts from (docs/ZX_SPECTRUM.md).

The image is what native/zxs_machine/zxs_machine.c loads (`zxs_load_image`): a 64-byte header (the model, the ports, the
CPU's registers, the T-state within the frame) and the eight RAM banks of 16 KiB. It is built from the snapshot alone; the ROM
is the machine's other input (retrorecomp/zxs_roms.py). The generated bodies, the project and the runs come with the
conversion of stage 2.
"""
from __future__ import annotations

import struct

from .zxs_snapshot import JOYSTICKS, PAGE, Snapshot

IMAGE_HEADER = 64
IMAGE_BYTES = IMAGE_HEADER + 8 * PAGE
# The T-state a snapshot that does not say starts at: the end of the /INT pulse (32 T on the 48K, 36 T on the 128K), so that a
# snapshot taken in its interrupt handler is not interrupted again at once.
INT_END = {'16k': 32, '48k': 32, '128k': 36}
MODEL_BYTE = {'16k': 0, '48k': 0, '128k': 1}
REGISTERS = ('af', 'bc', 'de', 'hl', 'af_', 'bc_', 'de_', 'hl_', 'ix', 'iy', 'sp', 'pc')


def zxs_image(snapshot: Snapshot) -> bytes:
    """The machine image of `snapshot` (IMAGE_BYTES), as zxs_load_image reads it."""
    regs = snapshot.registers
    joystick = JOYSTICKS.index(snapshot.joystick) if snapshot.joystick in JOYSTICKS else 0xFF
    ay = snapshot.ay_registers or (0,) * 16
    header = bytearray(IMAGE_HEADER)
    header[0:4] = b'ZXS1'
    header[4] = MODEL_BYTE[snapshot.model]
    header[5] = 1 if snapshot.model == '16k' else 0
    header[6] = joystick
    header[7] = snapshot.border & 7
    header[8] = snapshot.port_7ffd or 0
    header[9] = (snapshot.ay_select or 0) & 15
    header[10:26] = bytes(value & 0xFF for value in ay)
    header[26:31] = bytes((regs['im'] & 3, regs['iff1'] & 1, regs['iff2'] & 1, regs['i'] & 0xFF, regs['r'] & 0xFF))
    header[32:56] = struct.pack('<12H', *(regs[name] & 0xFFFF for name in REGISTERS))
    tstates = snapshot.tstates if snapshot.tstates is not None else INT_END[snapshot.model]
    header[56:60] = struct.pack('<I', tstates)
    banks = b''.join(snapshot.banks.get(bank, bytes(PAGE)) for bank in range(8))
    return bytes(header) + banks


# ---- the build (stage 2) -------------------------------------------------------------------------------------------------------
# The fields a native run must give exactly as the reference does: the CPU (main and shadow registers, I, R, IM, IFF, WZ, HALT),
# time and interrupts, the RAM, the picture of the last frame and a running hash of every frame, the sound, the ports and the AY.
COMPARED = ('frames', 'cycles', 'interrupts', 'af', 'bc', 'de', 'hl', 'ix', 'iy', 'sp', 'pc', 'af2', 'bc2', 'de2', 'hl2', 'i', 'r',
            'im', 'iff1', 'iff2', 'halted', 'wz', 'port_7ffd', 'border', 'out_fe', 'ay_latch', 'ay', 'ram_fnv', 'frame_fnv',
            'frame_trace', 'audio_samples', 'audio_fnv', 'rows')
GAME_TOML = '''# ZX Spectrum: the ROM is source 0 of the region map (game.toml's rom); there is no other source.
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
MACHINE_SOURCES = ('zxs_machine.c',)
MACHINE_FILES = (*MACHINE_SOURCES, 'zxs_machine.h', 'zxs_glue.inc', 'zxs_headless.inc', 'zxs_cpu_start.inc', 'zxs_native_main.c',
                 'zxs_reference_main.c')
SHARED_MODULES = (('ay38910', ('ay38910.c',), ('ay38910.h',)),)
SHARED_SOURCES = tuple(name for _, sources, _ in SHARED_MODULES for name in sources)
CHAIN_FILES = ('z80_chain_glue.inc', 'banked_reference_state.inc', 'audio_box.h')   # native/, staged flat
# The player (the `game` target) and the companions of the host kit it is built with (the MSX's list, less its cartridge saves).
GAME_FILES = ('zxs_player.c',)
KIT_FILES = ('retro_menu.c', 'retro_menu.h', 'font6x10.h', 'font10x20.h', 'runtime_i18n.h', 'runtime_catalog.inc',
             'retro_keyboard.h', 'display_settings.h', 'autofire.h', 'game_options.h', 'audio_filter.h', 'audio_cushion.h',
             'stereo_fir.h', 'audio_output.inc', 'scanline_sdl.h', 'scanlines.h', 'xbr_sdl.h', 'xbr_filter.h', 'scale2x.h',
             'platform_io.c', 'platform_io.h', 'embedded_resources.h', 'console16_video.h', 'runtime_feedback.h',
             'runtime_feedback.c', 'runtime_feedback_sdl.h', 'state_io.h', 'state_envelope.h', 'gamestate.h')
# The game's resources, named here only: prepare_game writes them into content.rc (and the Linux embedding) and their ids into
# zxs_game.h, which the player reads (RR_ZXS_ROM_RESOURCE, RR_ZXS_IMAGE_RESOURCE).
ROM_RESOURCE, IMAGE_RESOURCE, NOTICES_RESOURCE, IDENTITY_RESOURCE = 103, 104, 203, 205
# The quick state's layout (native/zxs_machine/zxs_player.c): part of its build binding, raised when the body changes.
STATE_LAYOUT = 'zxs-state-1'
BUILD_TIMEOUT = 2 * 3600


class ZxsBuildError(RuntimeError):
    """The generator, the build or a run failed."""


def _flags() -> int:
    import os
    import subprocess
    return subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def generate(work, rom: bytes, emit=print, *, keep_rom: bool = True) -> None:
    """The bodies of the ROM in `work/generated`, with the learned patterns (`native.patterns`)."""
    from . import z80_chain_build
    from .systems.zx_spectrum import ZXS_MACHINE
    z80_chain_build.generate_bodies(work, ZXS_MACHINE, ZXS_MACHINE.regions.image(rom), (), GAME_TOML, emit,
                                    loop_name='zxs_banked_loop.inc', accept='zxs_reference_accept', keep_rom=keep_rom,
                                    error=ZxsBuildError)


def stage_sources(work) -> None:
    """The machine, the glue, the mains, the player, the shared files and the host kit's, copied beside the generated bodies."""
    from . import hostkit, z80_chain_build
    from .paths import ASSETS
    z80_chain_build.stage_files(work, ((ASSETS / 'native' / 'zxs_machine', (*MACHINE_FILES, *GAME_FILES)),
                                       *((ASSETS / 'native' / folder, (*sources, *files)) for folder, sources, files in SHARED_MODULES),
                                       (ASSETS / 'native', (*CHAIN_FILES, *KIT_FILES))))
    hostkit.stage(work, 'zxs')
    # What the computers' adapters share (the guest keyboard and its chords), included by the Spectrum adapter.
    z80_chain_build.write_if_changed(work / 'hostkit' / 'adapters' / 'rrhk_computer.inc',
                                     (ASSETS / 'native' / 'hostkit' / 'adapters' / 'rrhk_computer.inc').read_bytes())


def project_cmake(bodies: bool = True, game: bool = False, version: str = '') -> str:
    """The project: the reference runner always; with `bodies` the generated bodies and the headless native check; with `game`
    the player too (it needs the bodies; `version` is the converter's, RR_RECOMP_VERSION)."""
    from . import hostkit
    machine = ' '.join((*MACHINE_SOURCES, *SHARED_SOURCES))
    bodies = bodies or game
    lines = [
        'cmake_minimum_required(VERSION 3.20)',
        'project(RetroZxs LANGUAGES C)',
        'set(CMAKE_C_STANDARD 11)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'if(MSVC)', '  add_compile_options(/utf-8 /wd4996 /wd4244 /wd4267)', 'endif()',
        f'add_executable(zxs_reference zxs_reference_main.c {machine} runtime_reference.c)',
    ]
    if bodies:
        lines += [
            'file(GLOB bodies "generated/game_banked_ops_*.c")',
            'add_library(zxs_bodies OBJECT generated/game_banked_index.c ${bodies})',
            'target_include_directories(zxs_bodies PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
            'target_compile_definitions(zxs_bodies PRIVATE SMSRECOMP_BANKED_AOT)',
            f'add_executable(zxs_check zxs_native_main.c {machine} runtime_reference.c $<TARGET_OBJECTS:zxs_bodies>)',
        ]
    lines += [
        f'foreach(target zxs_reference{" zxs_check" if bodies else ""})',
        '  target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
        '  target_compile_definitions(${target} PRIVATE SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS)',
        '  if(NOT WIN32)', '    target_link_libraries(${target} PRIVATE m)', '  endif()',
        'endforeach()',
    ]
    if game:
        kit = ' '.join(hostkit.sources('zxs'))
        lines += [
            'if(WIN32)', '  enable_language(RC)', 'else()', '  enable_language(ASM)', 'endif()',
            'find_package(SDL2 CONFIG REQUIRED)',
            f'add_executable(game zxs_player.c {machine} runtime_reference.c retro_menu.c platform_io.c runtime_feedback.c {kit}',
            '  $<TARGET_OBJECTS:zxs_bodies>)',
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


def build(work, targets: tuple, emit=print) -> dict:
    """Configure and build `targets` of the project in `work` (the SDL2 of the converter for the game)."""
    from . import __version__, core, z80_chain_build
    from .platforms import build_executable, sdl_install
    from pathlib import Path
    game = 'game' in targets
    bodies = game or 'zxs_check' in targets or (work / 'generated' / 'game_banked_index.c').is_file()
    z80_chain_build.write_if_changed(work / 'CMakeLists.txt', project_cmake(bodies, game, __version__).encode('utf-8'))
    cmake, generator_kind = core.toolchain()
    log = work / 'build.log'
    extra = [f'-DCMAKE_PREFIX_PATH={Path(sdl_install()).as_posix()}'] if game else []
    core.run([cmake, '-S', work, '-B', work / 'build', '-G', generator_kind, *core.cmake_target_args(),
              '-DCMAKE_BUILD_TYPE=Release', *extra], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    for target in targets:
        core.run([cmake, '--build', work / 'build', '--config', 'Release', '--target', target, '--parallel',
                  core.build_jobs()], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    return {target: build_executable(work / 'build', target) for target in targets}


def run(exe, rom_path, image: bytes, args: list, timeout: int = 1800) -> dict:
    """One headless run; its JSON report. The machine image reaches the program on its standard input."""
    import json
    import subprocess
    result = subprocess.run([str(exe), '--rom', str(rom_path), '--image', '-', *args], input=image, capture_output=True,
                            timeout=timeout, creationflags=_flags())
    if result.returncode:
        raise ZxsBuildError(f'{exe.name} failed: {result.stderr.decode(errors="replace").strip()[-500:]}')
    return json.loads(result.stdout)


def differences(native: dict, reference: dict) -> dict:
    """The compared fields that differ (a field missing on either side differs)."""
    return {key: (native.get(key), reference.get(key)) for key in COMPARED
            if key not in native or key not in reference or native[key] != reference[key]}


def learn(work, rom: bytes, image: bytes, runs: list, emit=print, *, passes: int = 3) -> tuple:
    """Generate, build the native check and run it with learning on every route, at most `passes` times: it stops when nothing
    fell back or nothing new was seen. Returns the check program and the fallback steps of each pass (summed over the routes)."""
    rom_path = work / 'rom.bin'
    from . import z80_chain_build
    z80_chain_build.write_if_changed(rom_path, rom)
    patterns = work / 'native.patterns'
    counts = []
    check = None
    for _ in range(passes):
        generate(work, rom, emit)
        stage_sources(work)
        check = build(work, ('zxs_check', 'zxs_reference'), emit)['zxs_check']
        seen, steps = set(), 0
        for index, args in enumerate(runs):
            learned = work / f'learned-{index}.txt'
            learned.unlink(missing_ok=True)
            result = run(check, rom_path, image, [*args, '--learn', str(learned)])
            steps += result['fallback_steps']
            if learned.is_file():
                seen |= set(learned.read_text(encoding='utf-8').split())
        counts.append(steps)
        if not steps or not seen:
            break
        known = set(patterns.read_text(encoding='utf-8').split()) if patterns.is_file() else set()
        if seen <= known:
            break
        patterns.write_text(''.join(f'{line}\n' for line in sorted(known | seen)), encoding='utf-8', newline='\n')
    else:
        generate(work, rom, emit)
        check = build(work, ('zxs_check', 'zxs_reference'), emit)['zxs_check']
    return check, counts


def frame_rows(path) -> list:
    """The rows of a --rows file (native/zxs_machine/zxs_headless.inc) as delivery_evidence.FrameRow (frame, picture, sound, audible,
    ram, pc)."""
    from .delivery_evidence import FrameRow
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines()[1:]:
        frame, _cpu, ram, picture, sound, _samples, audible, pc = line.split(',')
        rows.append(FrameRow(int(frame), picture, sound=sound, audible=audible == '1', ram=ram, pc=pc))
    return rows


def write_rom(path, data: bytes) -> None:
    """The ROM beside the bodies, written only when it changed (the runners read it with --rom)."""
    from . import z80_chain_build
    z80_chain_build.write_if_changed(path, data)


# ---- the game (the `game` target: native/zxs_machine/zxs_player.c on the host kit) ---------------------------------------------
def _c_string(text: str) -> str:
    """A C string literal of `text` as UTF-8 bytes (octal escapes outside printable ASCII), as msx_conversion writes the title."""
    out = []
    for byte in text.encode('utf-8'):
        char = chr(byte)
        out.append('\\' + char if char in '"\\' else char if 32 <= byte < 127 and char != '?' else f'\\{byte:03o}')
    return '"' + ''.join(out) + '"'


def state_binding(rom: bytes, image: bytes) -> bytes:
    """The quick state's build binding (RR_ZXS_STATE_ABI, 32 bytes): a state of another layout, ROM or model is refused as
    incompatible."""
    import hashlib
    text = '\n'.join([STATE_LAYOUT, hashlib.sha256(rom).hexdigest(), str(image[4]), str(image[5])])
    return hashlib.sha256(text.encode('ascii')).digest()


def prepare_game(work, title: str, identity: str, rom: bytes, image: bytes, emit=print, *, presentation: dict | None = None) -> dict:
    """The game's resources beside the project: the ROM (ROM_RESOURCE) and the machine image (IMAGE_RESOURCE) as the checked runs
    saw them, the notices, the identity, the Windows metadata and icon, and zxs_game.h (the title, the identity, the resource ids,
    the quick state's binding). `identity` is the snapshot's SHA-256 (64 hex digits). `presentation` (the player's cover options:
    rom_path, cover, use_cover, online_cover, boxart_dir) gives the icon its cover, as on the MSX (artwork.prepare_icon)."""
    import json
    from . import z80_chain_build
    from .core import executable_name
    from .metadata import write_game_metadata
    from .notices import notice_text
    from .resources import embed_resources
    if len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
        raise ZxsBuildError('the game identity is not a SHA-256')
    if len(image) != IMAGE_BYTES or len(rom) != (0x8000 if image[4] else 0x4000):
        raise ZxsBuildError('the ROM does not fit the machine image')
    write = z80_chain_build.write_if_changed
    write(work / 'game-rom.bin', rom)
    write(work / 'game-image.bin', image)
    write(work / 'notices.txt', notice_text('zxs').encode('utf-8'))
    write(work / 'runtime_feedback_config.h',
          f'#define RR_FEEDBACK_SYSTEM "zxs"\n#define RR_FEEDBACK_IDENTITY "{identity}"\n'.encode('ascii'))
    write(work / 'export-identity.bin', b'[Retro-Recomp]\0' + identity.encode('ascii') + b'\0')
    artwork = {'embedded': False, 'source': 'disabled'}
    if presentation is not None:
        from .artwork import prepare_icon
        from .core import ROOT
        from .paths import boxart_cache_directory
        artwork = prepare_icon(work, presentation['rom_path'], title, presentation.get('boxart_dir') or ROOT / 'BoxArt',
                               explicit=presentation.get('cover'), online=presentation.get('online_cover', True),
                               enabled=presentation.get('use_cover', True), cache_directory=boxart_cache_directory('zxs'),
                               system_id='zxs', emit=emit)
    write(work / 'artwork.json', json.dumps(artwork, indent=2).encode('utf-8'))
    metadata = write_game_metadata(work, title, executable_name(title), light_phaser=False, icon=bool(artwork['embedded']),
                                   system_id='zxs')
    resources = {ROM_RESOURCE: 'game-rom.bin', IMAGE_RESOURCE: 'game-image.bin', NOTICES_RESOURCE: 'notices.txt',
                 IDENTITY_RESOURCE: 'export-identity.bin'}
    write(work / 'content.rc', ('#pragma code_page(65001)\n'
                                + ''.join(f'{number} RCDATA "{name}"\n' for number, name in resources.items())
                                + '#include "game_resources.rc"\n').encode('utf-8'))
    embed_resources(work, {number: work / name for number, name in resources.items()})
    binding = ', '.join(f'0x{b:02X}' for b in state_binding(rom, image))
    write(work / 'zxs_game.h', (f'#pragma once\n#define RR_ZXS_TITLE {_c_string(title)}\n#define RR_ZXS_IDENTITY "{identity}"\n'
                                f'#define RR_ZXS_ROM_RESOURCE {ROM_RESOURCE}\n#define RR_ZXS_IMAGE_RESOURCE {IMAGE_RESOURCE}\n'
                                f'#define RR_ZXS_STATE_ABI {{{binding}}}\n').encode('utf-8'))
    return {'artwork': artwork, 'windows_metadata': metadata}


def run_game(game, options: list, report, timeout: int = 1800) -> dict:
    """The game's headless replay (`--headless`, from its own resources): its report, read from `report` (the game is linked for
    the Windows subsystem, so its standard output is not relied on)."""
    import json
    import subprocess
    report.unlink(missing_ok=True)
    result = subprocess.run([str(game), '--headless', *options, '--report', str(report)], capture_output=True, timeout=timeout,
                            creationflags=_flags())
    if result.returncode or not report.is_file():
        raise ZxsBuildError(f'{game.name} --headless failed (exit {result.returncode}): '
                            f'{result.stderr.decode(errors="replace").strip()[-300:]}')
    return json.loads(report.read_text(encoding='utf-8'))


def game_exit_code(game, options: list, timeout: int = 120) -> int:
    """The exit code of a headless run of the game (a refused quick state ends it with 4)."""
    import subprocess
    return subprocess.run([str(game), '--headless', *options], capture_output=True, timeout=timeout,
                          creationflags=_flags()).returncode
