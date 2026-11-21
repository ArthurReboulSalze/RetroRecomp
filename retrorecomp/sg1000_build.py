"""The SG-1000 on the banked Z80 chain: the generated bodies of a cartridge, the learning passes, the project (reference runner, headless
native check; the game later) and the comparison of the native run with the reference. Thin, on top of retrorecomp/z80_chain_build.py.

* The generator is the shared banked Z80 generator built for the SG-1000's own machine description (systems/sg1000.py, `SG1000_MACHINE`:
  eight 8 KiB regions, the cartridge as the only source, no wait state), in its own folders (`core.dependencies(emit, SG1000_MACHINE)`).
* The generator reads the cartridge as `rom.sms` beside `game.toml` (there is no further source: no BIOS) and keys positions modulo the
  image size, so it gets the cartridge padded to whole 8 KiB regions with FFh, exactly as the machine sees it.
* Code the interpreter ran from RAM is learned (`--learn`) and translated with byte guards on the next generation (`native.patterns`).
* The project builds `sg1000_reference` (the reference interpreter alone on the same machine) and `sg1000_check` (the headless native
  run); a `game` target (the player with the host kit) is added with `PLAYER_SOURCES` when the player exists.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import z80_chain_build

# The fields a native run must give exactly as the reference does (the keys both runners print, native/sg1000_machine/sg1000_headless.inc
# and sg_print_state): the CPU (main and shadow registers, I, R, IM, IFF, WZ), time and interrupts, RAM, VRAM, the picture of the last
# frame and a running hash of every frame, the VDP registers and status, the sound and the PSG, the watched bytes.
COMPARED = ('frames', 'cycles', 'interrupts', 'pc', 'sp', 'af', 'bc', 'de', 'hl', 'ix', 'iy', 'af2', 'bc2', 'de2', 'hl2', 'i', 'r', 'im',
            'iff1', 'iff2', 'wz', 'halted', 'vdp_regs', 'vdp_status', 'vram_fnv', 'ram_fnv', 'frame_fnv', 'frame_trace',
            'audio_samples', 'audio_fnv', 'psg', 'watch')
GAME_TOML = '''# SG-1000: the cartridge is source 0 of the region map; there is no other source (no BIOS).
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
# The machine's C sources, compiled into every program; the files they include, the mains and the glue (native/sg1000_machine).
MACHINE_SOURCES = ('sg1000_machine.c',)
MACHINE_FILES = (*MACHINE_SOURCES, 'sg1000_machine.h', 'sg1000_glue.inc', 'sg1000_headless.inc', 'sg1000_native_main.c',
                 'sg1000_reference_main.c')
# The modules shared with other machines (one folder of native/ each: (folder, sources compiled into every program, other files staged
# with them)): the TMS9918A of the MSX family and the SN76489A (native/sn76489, the SG-1000's own variant of the chip).
SHARED_MODULES = (('tms9918', ('tms9918.c',), ('tms9918.h', 'tms_tiles.inc')),
                  ('sn76489', ('sn76489.c',), ('sn76489.h',)))
SHARED_SOURCES = tuple(name for _, sources, _ in SHARED_MODULES for name in sources)      # in the work folder, flat
# The glue every machine on the banked Z80 chain shares (native/z80_chain_glue.inc), included by sg1000_glue.inc.
CHAIN_FILES = ('z80_chain_glue.inc', 'audio_box.h')
# The player (the host kit's game of this machine): empty until it is written; the game target of the project lists them.
PLAYER_SOURCES: tuple[str, ...] = ()
PLAYER_FILES: tuple[str, ...] = PLAYER_SOURCES


class Sg1000BuildError(RuntimeError):
    """The generator, the build or a run failed."""


def padded(image: bytes) -> bytes:
    """The cartridge as the machine sees it: whole 8 KiB regions padded with FFh; the same image feeds the generator, the checked runs and
    (later) the game."""
    from .systems.sg1000 import SG1000_MACHINE
    return SG1000_MACHINE.regions.image(image)


def generate(work: Path, cartridge: bytes, emit: Callable[[str], None] = print) -> None:
    """The bodies of `cartridge` (padded as the machine sees it) in `work/generated`, with the learned patterns."""
    from .systems.sg1000 import SG1000_MACHINE
    z80_chain_build.generate_bodies(work, SG1000_MACHINE, cartridge, (), GAME_TOML, emit, loop_name='sg1000_banked_loop.inc',
                                    accept='sg1000_reference_accept', error=Sg1000BuildError)


def stage_sources(work: Path) -> None:
    """The machine, the shared modules and the glue, copied beside the generated bodies (only what changed)."""
    from .paths import ASSETS
    native = ASSETS / 'native'
    z80_chain_build.stage_files(work, ((native / 'sg1000_machine', (*MACHINE_FILES, *PLAYER_FILES)),
                                       *((native / folder, (*sources, *files)) for folder, sources, files in SHARED_MODULES),
                                       (native, CHAIN_FILES)))


def project_cmake(game: bool = False, bodies: bool = True) -> str:
    """The project: the reference runner always; with `bodies` the generated bodies and the headless native check; `game` adds the player
    (it needs the bodies and `PLAYER_SOURCES`, which do not exist yet)."""
    if game and not PLAYER_SOURCES:
        raise Sg1000BuildError('The SG-1000 player is not written yet: only the reference and the native check are built.')
    machine = ' '.join((*MACHINE_SOURCES, *SHARED_SOURCES))
    programs = 'sg1000_reference sg1000_check' if bodies or game else 'sg1000_reference'
    lines = [
        'cmake_minimum_required(VERSION 3.20)', 'project(RetroSg1000 LANGUAGES C)', 'set(CMAKE_C_STANDARD 11)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'if(MSVC)', '  add_compile_options(/utf-8 /wd4996 /wd4244 /wd4267)', 'endif()',
        f'add_executable(sg1000_reference sg1000_reference_main.c {machine} runtime_reference.c)',
    ]
    if bodies or game:
        lines += [
            'file(GLOB bodies "generated/game_banked_ops_*.c")',
            'add_library(sg1000_bodies OBJECT generated/game_banked_index.c ${bodies})',
            'target_include_directories(sg1000_bodies PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
            'target_compile_definitions(sg1000_bodies PRIVATE SMSRECOMP_BANKED_AOT)',
            f'add_executable(sg1000_check sg1000_native_main.c {machine} runtime_reference.c $<TARGET_OBJECTS:sg1000_bodies>)',
        ]
    lines += [
        f'foreach(target {programs})',
        '  target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
        '  target_compile_definitions(${target} PRIVATE SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS)',
        '  if(NOT WIN32)', '    target_link_libraries(${target} PRIVATE m)', '  endif()',
        'endforeach()',
    ]
    if game:
        # The host kit's files (hostkit.sources, the resources, the version) are the player's own business: the lines are written with it.
        lines += [f'add_executable(game {" ".join(PLAYER_SOURCES)} {machine} runtime_reference.c $<TARGET_OBJECTS:sg1000_bodies>)']
    return '\n'.join(lines) + '\n'


def build(work: Path, targets: tuple[str, ...], emit: Callable[[str], None] = print) -> dict[str, Path]:
    """Configure and build `targets` of the project in `work`."""
    game = 'game' in targets
    bodies = game or 'sg1000_check' in targets or (work / 'generated' / 'game_banked_index.c').is_file()
    try:
        return z80_chain_build.build_project(work, targets, project_cmake(game, bodies), sdl=game, emit=emit)
    except Sg1000BuildError:
        raise
    except Exception as error:  # noqa: BLE001 - the build's own log names the cause
        raise Sg1000BuildError(f'The SG-1000 project did not build ({error}); see {work / "build.log"}.') from None


def build_reference(work: Path, emit: Callable[[str], None] = print) -> Path:
    """The reference runner alone, before any body is generated (the start of the play route is chosen on it)."""
    from .cpu import prepare_reference
    from .systems.sg1000 import SG1000_MACHINE
    _, engine = z80_chain_build.generator(SG1000_MACHINE, emit)
    work.mkdir(parents=True, exist_ok=True)
    prepare_reference(work, engine, m1_counter=SG1000_MACHINE.counts_m1, nmi=SG1000_MACHINE.nmi)
    z80_chain_build.instrument_reference(work / 'runtime_reference.c', 'sg1000_reference_accept', SG1000_MACHINE, Sg1000BuildError)
    stage_sources(work)
    return build(work, ('sg1000_reference',), emit)['sg1000_reference']


def run(exe: Path, args: list[str], image: bytes | None = None, timeout: int = 1800) -> dict:
    """One headless run; its JSON report. The cartridge, when given, reaches the program on its standard input."""
    return z80_chain_build.run_program(exe, args, image, timeout, Sg1000BuildError)


def differences(native: dict, reference: dict) -> dict:
    """The compared fields that differ (a field missing on either side differs)."""
    return z80_chain_build.differences(native, reference, COMPARED)


frame_rows = z80_chain_build.frame_rows


def learn(work: Path, cartridge: bytes, runs: list[list[str]], emit: Callable[[str], None] = print, *, passes: int = 3,
          workers: int = 1) -> tuple[Path, list[int]]:
    """Generate, build the headless check and run every route (`runs`: the options of each) with learning, at most `passes` times (see
    z80_chain_build.learn_passes). Returns the check program and the fallback steps of each pass, summed over the routes."""
    def build_check() -> Path:
        stage_sources(work)
        return build(work, ('sg1000_check', 'sg1000_reference'), emit)['sg1000_check']
    return z80_chain_build.learn_passes(work, runs, generate=lambda: generate(work, cartridge, emit), build_check=build_check,
                                        run_check=lambda check, args, _learned: run(check, args, cartridge)['fallback_steps'],
                                        passes=passes, workers=workers)
