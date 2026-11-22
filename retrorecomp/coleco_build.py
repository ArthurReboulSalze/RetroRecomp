"""The ColecoVision on the banked Z80 chain: the generated bodies of a cartridge and of the BIOS, the learning passes, the project (reference runner, headless
native check and the game) and the comparison of the native run with the reference. Thin, on top of retrorecomp/z80_chain_build.py.

* The generator is the shared banked Z80 generator built for the ColecoVision's own machine description (systems/coleco.py, `COLECO_MACHINE`:
  eight 8 KiB regions, the cartridge as source 0 and the player's BIOS as source 1, one wait state on every M1 cycle), in its own folders
  (`core.dependencies(emit, COLECO_MACHINE)`).
* The generator reads the cartridge as `rom.sms` beside `game.toml` and the BIOS as `bios.rom` (named in `banked.sources`), and keys positions
  modulo the image size, so it gets the cartridge padded to whole 8 KiB regions with FFh, exactly as the machine sees it.
* Code the interpreter ran from RAM is learned (`--learn`) and translated with byte guards on the next generation (`native.patterns`).
* The project builds `coleco_reference` (the reference interpreter alone on the same machine), `coleco_check` (the headless native
  run) and `game` (the player, native/coleco_machine/coleco_player.c, with the host kit and SDL2: the file the player receives).
* The game's header (`coleco_game.h`: title, identity, standard, the quick state's build binding) is written by `game_header`; the
  resources and the notices by retrorecomp/coleco_conversion.py (`prepare_game`).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from . import z80_chain_build

# The fields a native run must give exactly as the reference does (the keys both runners print, native/coleco_machine/coleco_headless.inc
# and cv_print_state): the CPU (main and shadow registers, I, R, IM, IFF, WZ), time and interrupts, RAM, VRAM, the picture of the last
# frame and a running hash of every frame, the VDP registers and status, the sound and the PSG, the watched bytes.
COMPARED = ('frames', 'cycles', 'interrupts', 'nmi', 'pc', 'sp', 'af', 'bc', 'de', 'hl', 'ix', 'iy', 'af2', 'bc2', 'de2', 'hl2', 'i', 'r', 'im',
            'iff1', 'iff2', 'wz', 'halted', 'vdp_regs', 'vdp_status', 'vram_fnv', 'ram_fnv', 'frame_fnv', 'frame_trace',
            'audio_samples', 'audio_fnv', 'audio_dropped', 'psg', 'watch')
GAME_TOML = '''# ColecoVision: the cartridge is source 0 of the region map, the player's BIOS source 1 (banked.sources).
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
# The machine's C sources, compiled into every program; the files they include, the mains and the glue (native/coleco_machine).
MACHINE_SOURCES = ('coleco_machine.c',)
MACHINE_FILES = (*MACHINE_SOURCES, 'coleco_machine.h', 'coleco_glue.inc', 'coleco_headless.inc', 'coleco_native_main.c',
                 'coleco_reference_main.c')
# The modules shared with other machines (one folder of native/ each: (folder, sources compiled into every program, other files staged
# with them)): the TMS9918A of the MSX family and the SN76489A (native/sn76489, the ColecoVision's own variant of the chip).
SHARED_MODULES = (('tms9918', ('tms9918.c',), ('tms9918.h', 'tms_tiles.inc')),
                  ('sn76489', ('sn76489.c',), ('sn76489.h',)))
SHARED_SOURCES = tuple(name for _, sources, _ in SHARED_MODULES for name in sources)      # in the work folder, flat
# The glue every machine on the banked Z80 chain shares (native/z80_chain_glue.inc), included by coleco_glue.inc.
CHAIN_FILES = ('z80_chain_glue.inc', 'audio_box.h', 'z80_chain_state.inc', 'state_file.h')
# The player (the host kit's game of this machine): its source and what it includes; the game target of the project lists the source.
PLAYER_SOURCES: tuple[str, ...] = ('coleco_player.c',)
PLAYER_FILES: tuple[str, ...] = (*PLAYER_SOURCES, 'coleco_state_file.inc')
# The host kit's companions the game includes (native/): the menu, the fonts, the filters, the platform files, the quick-state envelope. The
# MSX's list without the media request and the cartridge save files: an ColecoVision cartridge has no media to change and no battery.
KIT_FILES = ('retro_menu.c', 'retro_menu.h', 'font6x10.h', 'font10x20.h', 'runtime_i18n.h', 'runtime_catalog.inc',
             'retro_keyboard.h', 'display_settings.h', 'autofire.h', 'game_options.h', 'audio_filter.h', 'audio_cushion.h',
             'stereo_fir.h', 'audio_output.inc', 'scanline_sdl.h', 'scanlines.h', 'xbr_sdl.h', 'xbr_filter.h', 'scale2x.h',
             'platform_io.c', 'platform_io.h', 'embedded_resources.h', 'console16_video.h', 'runtime_feedback.h',
             'runtime_feedback.c', 'runtime_feedback_sdl.h', 'state_io.h', 'state_envelope.h', 'gamestate.h')
# The quick state's layout name (native/coleco_machine/coleco_state_file.inc): raised whenever the body it writes changes.
STATE_LAYOUT = 'coleco-state-1'


class ColecoBuildError(RuntimeError):
    """The generator, the build or a run failed."""


def padded(image: bytes) -> bytes:
    """The cartridge as the machine sees it: whole 8 KiB regions padded with FFh; the same image feeds the generator, the checked runs and
    (later) the game."""
    from .systems.coleco import COLECO_MACHINE
    return COLECO_MACHINE.regions.image(image)


def generate(work: Path, cartridge: bytes, bios: bytes, emit: Callable[[str], None] = print) -> None:
    """The bodies of `cartridge` (padded as the machine sees it) and of `bios` in `work/generated`, with the learned patterns."""
    from .systems.coleco import COLECO_MACHINE
    z80_chain_build.generate_bodies(work, COLECO_MACHINE, cartridge, (('bios.rom', bios),), GAME_TOML, emit, loop_name='coleco_banked_loop.inc',
                                    accept='coleco_reference_accept', error=ColecoBuildError)


def stage_sources(work: Path) -> None:
    """The machine, the player, the shared modules, the glue and the host kit, copied beside the generated bodies (only what changed)."""
    from . import hostkit
    from .paths import ASSETS
    native = ASSETS / 'native'
    z80_chain_build.stage_files(work, ((native / 'coleco_machine', (*MACHINE_FILES, *PLAYER_FILES)),
                                       *((native / folder, (*sources, *files)) for folder, sources, files in SHARED_MODULES),
                                       (native, (*CHAIN_FILES, *KIT_FILES))))
    hostkit.stage(work, 'coleco')
    # The on-screen keypad the adapter includes, and the five-language text it reads (the kit stages only its shell and the adapter: the
    # computers' adapter file is staged the same way by the MSX's and the ZX Spectrum's builds).
    for name in ('rrhk_keypad.inc', 'rrhk_text.h'):
        z80_chain_build.write_if_changed(work / 'hostkit' / 'adapters' / name, (native / 'hostkit' / 'adapters' / name).read_bytes())


def state_binding(standard: str, rom_size: int, bios_sha256: str) -> bytes:
    """The quick state's build binding (RR_CV_STATE_ABI, 32 bytes): the SHA-256 of the layout name, the standard, the cartridge's size as the
    machine sees it (whole 8 KiB regions) and the BIOS's SHA-256. A state of another layout, standard, size or BIOS is refused as incompatible."""
    return hashlib.sha256(f'{STATE_LAYOUT}\n{standard}\n{rom_size}\n{bios_sha256}'.encode('ascii')).digest()


def _c_string(text: str) -> str:
    """A C string literal of `text` as UTF-8 bytes (octal escapes for everything outside printable ASCII)."""
    out = []
    for byte in text.encode('utf-8'):
        char = chr(byte)
        out.append('\\' + char if char in '"\\' else char if 32 <= byte < 127 and char != '?' else f'\\{byte:03o}')
    return '"' + ''.join(out) + '"'


def game_header(title: str, identity: str, standard: str, rom_size: int, bios_sha256: str) -> str:
    """`coleco_game.h`, what the player reads (native/coleco_machine/coleco_player.c): the title, the cartridge file's SHA-256, the standard,
    the quick state's build binding. `rom_size`: the padded cartridge's size."""
    abi = ', '.join(f'0x{b:02X}' for b in state_binding(standard, rom_size, bios_sha256))
    return ('#pragma once\n'
            f'#define RR_CV_TITLE {_c_string(title)}\n#define RR_CV_IDENTITY "{identity}"\n'
            f'#define RR_CV_PAL {int(standard == "pal")}\n#define RR_CV_STATE_ABI {{{abi}}}\n')


def project_cmake(game: bool = False, bodies: bool = True, version: str = '') -> str:
    """The project: the reference runner always; with `bodies` the generated bodies and the headless native check; `game` adds the player
    (it needs the bodies, the generated header and the resources `prepare_game` writes). `version`: the converter's, named in the game.
    The common part is `z80_chain_build.chain_project_cmake`; what is here is the player's lines."""
    from . import hostkit
    machine = ' '.join((*MACHINE_SOURCES, *SHARED_SOURCES))
    lines = []
    if game:
        # The game: the player, the machine, the fallback interpreter, the kit's menu and platform files, the kit's shell, the bodies.
        kit = ' '.join(hostkit.sources('coleco'))
        lines = [
            'if(WIN32)', '  enable_language(RC)', 'else()', '  enable_language(ASM)', 'endif()',
            'find_package(SDL2 CONFIG REQUIRED)',
            f'add_executable(game {" ".join(PLAYER_SOURCES)} {machine} runtime_reference.c retro_menu.c platform_io.c runtime_feedback.c {kit}',
            '  $<TARGET_OBJECTS:coleco_bodies>)',
            'target_include_directories(game PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
            'if(WIN32)', '  target_sources(game PRIVATE content.rc)', '  target_link_libraries(game PRIVATE shell32 user32 gdi32)',
            'else()', '  target_sources(game PRIVATE embedded_resources.c embedded_resources.S)', '  target_link_libraries(game PRIVATE m)', 'endif()',
            'target_link_libraries(game PRIVATE SDL2::SDL2-static)',
            'target_compile_definitions(game PRIVATE SDL_MAIN_HANDLED SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS '
            f'[[RR_RECOMP_VERSION="{version}"]])',
            'if(MSVC)', '  target_link_options(game PRIVATE /SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup)', 'endif()',
            'if(WIN32 AND NOT MSVC)', '  target_link_options(game PRIVATE -Wl,--subsystem,windows -Wl,--entry,mainCRTStartup)', 'endif()',
        ]
    return z80_chain_build.chain_project_cmake(
        'coleco', 'RetroColeco', reference_main='coleco_reference_main.c', native_main='coleco_native_main.c',
        machine_sources=(*MACHINE_SOURCES, *SHARED_SOURCES), bodies=bodies or game, game_lines=lines)


def build(work: Path, targets: tuple[str, ...], emit: Callable[[str], None] = print) -> dict[str, Path]:
    """Configure and build `targets` of the project in `work`."""
    from . import __version__
    game = 'game' in targets
    bodies = game or 'coleco_check' in targets or (work / 'generated' / 'game_banked_index.c').is_file()
    try:
        return z80_chain_build.build_project(work, targets, project_cmake(game, bodies, __version__), sdl=game, emit=emit)
    except ColecoBuildError:
        raise
    except Exception as error:  # noqa: BLE001 - the build's own log names the cause
        raise ColecoBuildError(f'The ColecoVision project did not build ({error}); see {work / "build.log"}.') from None


def build_reference(work: Path, emit: Callable[[str], None] = print) -> Path:
    """The reference runner alone, before any body is generated (the start of the play route is chosen on it)."""
    from .systems.coleco import COLECO_MACHINE
    return z80_chain_build.build_reference_runner(work, COLECO_MACHINE, accept='coleco_reference_accept', stage=stage_sources, build=build,
                                                  target='coleco_reference', emit=emit, error=ColecoBuildError)


def run(exe: Path, args: list[str], image: bytes | None = None, timeout: int = 1800) -> dict:
    """One headless run; its JSON report. The cartridge, when given, reaches the program on its standard input."""
    return z80_chain_build.run_program(exe, args, image, timeout, ColecoBuildError)


def run_game(game: Path, options: list[str], report: Path) -> dict:
    """The game's headless replay (`--headless`, from its own resources): its report, read from `report`."""
    return z80_chain_build.run_game(game, options, report, error=ColecoBuildError)


def game_exit_code(game: Path, options: list[str]) -> int:
    """The exit code of a headless run of the game (a refused quick state ends it with 4)."""
    return z80_chain_build.game_exit_code(game, options)


def differences(native: dict, reference: dict) -> dict:
    """The compared fields that differ (a field missing on either side differs)."""
    return z80_chain_build.differences(native, reference, COMPARED)


frame_rows = z80_chain_build.frame_rows


def learn(work: Path, cartridge: bytes, bios: bytes, runs: list[list[str]], emit: Callable[[str], None] = print, *, passes: int = 3,
          workers: int = 1) -> tuple[Path, list[int]]:
    """Generate, build the headless check and run every route (`runs`: the options of each) with learning, at most `passes` times (see
    z80_chain_build.learn_passes). Returns the check program and the fallback steps of each pass, summed over the routes."""
    def build_check() -> Path:
        stage_sources(work)
        return build(work, ('coleco_check', 'coleco_reference'), emit)['coleco_check']
    return z80_chain_build.learn_passes(work, runs, generate=lambda: generate(work, cartridge, bios, emit), build_check=build_check,
                                        run_check=lambda check, args, _learned: run(check, args, cartridge)['fallback_steps'],
                                        passes=passes, workers=workers)
