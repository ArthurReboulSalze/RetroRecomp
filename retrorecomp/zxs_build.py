"""The ZX Spectrum on the banked Z80 chain: the machine image a converted snapshot starts from (docs/ZX_SPECTRUM.md).

The image is what native/zxs_machine/zxs_machine.c loads (`zxs_load_image`): a 64-byte header (the model, the ports, the
CPU's registers, the T-state within the frame) and the eight RAM banks of 16 KiB. It is built from the snapshot alone; the ROM
is the machine's other input (retrorecomp/zxs_roms.py). Then the generated bodies, the project, the headless runs (reference,
native check, the game) and the learning of the RAM code, for retrorecomp/zxs_conversion.py.
"""
from __future__ import annotations

import struct
from pathlib import Path

from . import resource_rebuild
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


# ---- the build ----------------------------------------------------------------------------------------------------------------
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
# The chain's contention evaluator, rendered beside the reference copy (Z80Machine.contention, retrorecomp/z80_timed.py).
GENERATED_SOURCES = ('banked_timed.c',)
CHAIN_FILES = ('z80_chain_glue.inc', 'banked_reference_state.inc', 'audio_box.h', 'z80_chain_state.inc', 'state_file.h')   # native/, staged flat
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


class ZxsBuildError(RuntimeError):
    """The generator, the build or a run failed."""


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
    """The project (z80_chain_build.chain_project_cmake): the reference runner always; with `bodies` the generated bodies and the
    headless native check; with `game` the player too (it needs the bodies; `version` is the converter's, RR_RECOMP_VERSION)."""
    from . import hostkit
    from .z80_chain_build import chain_project_cmake
    machine = ' '.join((*MACHINE_SOURCES, *SHARED_SOURCES, *GENERATED_SOURCES))
    game_lines = []
    if game:
        kit = ' '.join(hostkit.sources('zxs'))
        game_lines = [
            'if(WIN32)', '  enable_language(RC)', 'else()', '  enable_language(ASM)', 'endif()',
            'find_package(SDL2 CONFIG REQUIRED)',
            f'add_executable(game zxs_player.c {machine} runtime_reference.c retro_menu.c platform_io.c runtime_feedback.c {kit}',
            '  $<TARGET_OBJECTS:zxs_bodies>)',
            'target_include_directories(game PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
            'if(WIN32)', '  target_sources(game PRIVATE content.rc)',
            '  target_link_libraries(game PRIVATE shell32 user32 gdi32)',
            'else()', '  target_sources(game PRIVATE embedded_resources.c embedded_resources.S)',
            '  target_link_libraries(game PRIVATE m)', 'endif()',
            *resource_rebuild.CMAKE_LINES,
            'target_link_libraries(game PRIVATE SDL2::SDL2-static)',
            f'target_compile_definitions(game PRIVATE SDL_MAIN_HANDLED SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS '
            f'[[RR_RECOMP_VERSION="{version}"]])',
            'if(MSVC)', '  target_link_options(game PRIVATE /SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup)', 'endif()',
            'if(WIN32 AND NOT MSVC)',
            '  target_link_options(game PRIVATE -Wl,--subsystem,windows -Wl,--entry,mainCRTStartup)', 'endif()',
        ]
    return chain_project_cmake('zxs', 'RetroZxs', reference_main='zxs_reference_main.c', native_main='zxs_native_main.c',
                               machine_sources=(*MACHINE_SOURCES, *SHARED_SOURCES, *GENERATED_SOURCES), bodies=bodies or game,
                               game_lines=game_lines)


def build(work, targets: tuple, emit=print) -> dict:
    """Configure and build `targets` of the project in `work` (z80_chain_build.build_project; the SDL2 of the converter for the
    game)."""
    from . import __version__, z80_chain_build
    game = 'game' in targets
    bodies = game or 'zxs_check' in targets or (work / 'generated' / 'game_banked_index.c').is_file()
    return z80_chain_build.build_project(work, targets, project_cmake(bodies, game, __version__), sdl=game, emit=emit)


def build_reference(work, emit=print) -> Path:
    """The reference runner alone, before any body is generated (the start of the play route is chosen on it;
    z80_chain_build.build_reference_runner: the reference CPU prepared for the Spectrum's 16-bit ports, and, the reference main
    keeping the translated register file, the CPU headers written before any body)."""
    from . import z80_chain_build
    from .systems.zx_spectrum import ZXS_MACHINE
    return z80_chain_build.build_reference_runner(work, ZXS_MACHINE, accept='zxs_reference_accept', stage=stage_sources, build=build,
                                                  target='zxs_reference', emit=emit, error=ZxsBuildError)


def run(exe, rom_path, image: bytes, args: list, timeout: int = 1800) -> dict:
    """One headless run; its JSON report. The ROM is read from `rom_path`; the machine image reaches the program on its standard
    input (`--cart -`, z80_chain_build.run_program)."""
    from . import z80_chain_build
    return z80_chain_build.run_program(exe, ['--rom', str(rom_path), *args], image, timeout, ZxsBuildError)


def differences(native: dict, reference: dict) -> dict:
    """The compared fields that differ (a field missing on either side differs)."""
    from . import z80_chain_build
    return z80_chain_build.differences(native, reference, COMPARED)


def learn(work, rom: bytes, image: bytes, runs: list, emit=print, *, passes: int = 3) -> tuple:
    """The shared learn loop (z80_chain_build.learn_passes) on the Spectrum: generate and stage, build the native check (and the
    reference beside it), run every route with learning. Returns the check program and the fallback steps of each pass."""
    from . import z80_chain_build
    rom_path = work / 'rom.bin'
    z80_chain_build.write_if_changed(rom_path, rom)

    def generate_and_stage():
        generate(work, rom, emit)
        stage_sources(work)
    return z80_chain_build.learn_passes(
        work, runs, generate=generate_and_stage,
        build_check=lambda: build(work, ('zxs_check', 'zxs_reference'), emit)['zxs_check'],
        run_check=lambda check, args, _learned: run(check, rom_path, image, args)['fallback_steps'], passes=passes)


def frame_rows(path) -> list:
    """The rows of a --rows file (native/zxs_machine/zxs_headless.inc), as every machine on the chain writes them."""
    from . import z80_chain_build
    return z80_chain_build.frame_rows(path)


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
    embedded = {'game-rom.bin': rom, 'game-image.bin': image, 'notices.txt': notice_text('zxs').encode('utf-8'),
                'export-identity.bin': b'[Retro-Recomp]\0' + identity.encode('ascii') + b'\0'}
    # The build tracks these files itself (retrorecomp/resource_rebuild.py, in the project's CMake).
    for name, data in embedded.items():
        write(work / name, data)
    write(work / 'runtime_feedback_config.h',
          f'#define RR_FEEDBACK_SYSTEM "zxs"\n#define RR_FEEDBACK_IDENTITY "{identity}"\n'.encode('ascii'))
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
    """The game's headless replay (`--headless`, from its own resources; z80_chain_build.run_game)."""
    from . import z80_chain_build
    return z80_chain_build.run_game(game, options, report, timeout, ZxsBuildError)


def game_exit_code(game, options: list, timeout: int = 120) -> int:
    """The exit code of a headless run of the game (a refused quick state ends it with 4)."""
    from . import z80_chain_build
    return z80_chain_build.game_exit_code(game, options, timeout)
