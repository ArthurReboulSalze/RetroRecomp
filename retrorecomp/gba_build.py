"""Building the Game Boy Advance engine for one cartridge, and running its headless host.

Three programs come out of the staged engine (`gba_engine.py`):

* the recompiler `gba_recompile`, built once per engine revision and patch set and shared by every game;
* the generated code of the player's BIOS (`generate_bios`), which the engine runs as the real system ROM; it is derived
  from the player's file, so it lives in the conversion's private project folder and never leaves it;
* the **probe host** of one cartridge: the engine's own runtime and `run_game()` behind a three-line `main`, linked with
  that cartridge's generated shards. It has no window and no sound (the engine's SDL is absent from this build), and it is
  what the conversion runs to observe a game. It is not the player: the player is a host-kit adapter (a later stage).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import timings
from .conversion_common import probe_environment, spawn, write_if_changed
from .core import ConversionError, run
from .gba import KNOWN_BIOS_SHA1
from .paths import ROOT
from .platforms import build_executable, build_jobs, cmake_target_args

MAIN_CPP = '''// Headless probe host of a Retro-Recomp Game Boy Advance conversion: the engine's own run_game(), nothing else.
#include "runtime.h"

int main(int argc, char** argv) { return gbarecomp::run_game(argc, argv); }
'''
# The project that links one cartridge's generated code to the engine's runtime (the engine's own recipe, `runtime.cmake`).
PROJECT_CMAKE = '''cmake_minimum_required(VERSION 3.20)
project(gba_probe C CXX)
set(GBARECOMP_COMPILER_CACHE OFF CACHE STRING "")
set(GBARECOMP_GENERATED_BIOS_DIR "@BIOS@" CACHE PATH "")
add_subdirectory("@ENGINE@" engine EXCLUDE_FROM_ALL)
include("${CMAKE_CURRENT_BINARY_DIR}/engine/runtime.cmake")
gbarecomp_add_runtime_target(gba_probe GAME_GENERATED_DIR "@GAME@")
target_sources(gba_probe PRIVATE "${CMAKE_CURRENT_LIST_DIR}/main.cpp")
'''
HOST_NAME = 'gba_probe'
SHARD_COUNT = 8
RTC_EPOCH = '1767225600'      # 2026-01-01 00:00:00 UTC: the start of the guest-timed clock of the scenarios (seconds since 1970)


@dataclass(frozen=True)
class Run:
    """What one run of the probe host left behind."""
    scenario: str
    frames: int
    returncode: int
    output: str
    coverage: dict
    misses: str
    iwram: bytes | None
    aborted: str = ''
    frame_sha256: str = ''
    cycles: int | None = None        # the guest's cycle count at the common VBlank of the snapshot, not the engine's idle counter
    mem_hash: str = ''               # work RAM, IWRAM, VRAM, OAM, palette and I/O registers at that VBlank
    cpu_hash: str = ''               # the CPU registers there


def recompiler(stage: Path, key: str, cmake, generator: str, emit: Callable[[str], None]) -> Path:
    """`gba_recompile` of the staged engine, built once per `key` (engine revision and patch set)."""
    build = ROOT / '.deps' / f'gbarecomp-build-{key}'
    program = build_executable(build, 'gba_recompile')
    if program.is_file():
        return program
    emit('Building the Game Boy Advance recompiler…')
    run([cmake, '-S', stage / 'engine', '-B', build, '-G', generator, *cmake_target_args(),
         '-DGBARECOMP_COMPILER_CACHE=OFF'], log=build.with_suffix('.log'), timeout=900)
    with timings.phase('compile'):
        run([cmake, '--build', build, '--target', 'gba_recompile', '--parallel', build_jobs()],
            log=build.with_suffix('.log'), timeout=3600)
    if not program.is_file():
        raise ConversionError('The Game Boy Advance recompiler was not built.')
    return program


def generate_bios(recompile: Path, stage: Path, bios_path: Path, out: Path, emit: Callable[[str], None]) -> Path:
    """Generated code of the player's BIOS, from their own file. The recompiler checks its SHA-1 against the one the
    engine knows and refuses another image."""
    config = stage / 'engine' / 'bios' / 'gba_bios.toml'
    marker = out / 'bios_recompiled.cpp'
    stamp = out / 'bios.stamp'
    identity = json.dumps({'sha1': KNOWN_BIOS_SHA1, 'recompiler': recompile.stat().st_size,
                           'config': config.stat().st_size})
    if marker.is_file() and stamp.is_file() and stamp.read_text(encoding='utf-8') == identity:
        return out
    emit('Generating the BIOS code from your own system ROM (private, never exported)…')
    out.mkdir(parents=True, exist_ok=True)
    result = run([recompile, '--bios', bios_path, '--config', config, '--out', out], log=out.with_suffix('.log'),
                 timeout=600)
    if 'identity sha1' in result and '(verified)' not in result:
        raise ConversionError('The BIOS file is not the one the engine supports (SHA-1 mismatch).')
    if not marker.is_file():
        raise ConversionError('The BIOS code was not generated.')
    write_if_changed(stamp, identity.encode('utf-8'))
    return out


def generate_game(recompile: Path, rom_path: Path, config: Path, out: Path, emit: Callable[[str], None]) -> dict:
    """The cartridge's generated shards, sharded, from the engine's analysis plus our observations."""
    out.mkdir(parents=True, exist_ok=True)
    result = run([recompile, '--rom', rom_path, '--config', config, '--entry', '0x08000000',
                  '--codegen-shards', str(SHARD_COUNT), '--out', out], log=out.with_suffix('.log'), timeout=900)
    found = re.search(r'discovered (\d+) functions \(arm=(\d+) thumb=(\d+)', result)
    return {'functions': int(found[1]) if found else None, 'arm': int(found[2]) if found else None,
            'thumb': int(found[3]) if found else None,
            'shards': len(list(out.glob('recompiled_[0-9][0-9][0-9].cpp')))}


def host_project(project: Path, stage: Path, game: Path, bios: Path) -> Path:
    """The CMake project of the probe host (a few lines, rewritten only when its text changes)."""
    folder = project / 'host'
    text = (PROJECT_CMAKE.replace('@ENGINE@', (stage / 'engine').as_posix()).replace('@GAME@', game.as_posix())
            .replace('@BIOS@', bios.as_posix()))
    write_if_changed(folder / 'CMakeLists.txt', text.encode('utf-8'))
    write_if_changed(folder / 'main.cpp', MAIN_CPP.encode('utf-8'))
    return folder


def build_host(project: Path, cmake, generator: str, emit: Callable[[str], None]) -> Path:
    """Compile the probe host of one cartridge; returns the executable."""
    folder, build = project / 'host', project / 'host-build'
    run([cmake, '-S', folder, '-B', build, '-G', generator, *cmake_target_args()], log=project / 'build.log', timeout=900)
    with timings.phase('compile'):
        run([cmake, '--build', build, '--target', HOST_NAME, '--parallel', build_jobs()],
            log=project / 'build.log', timeout=7200)
    program = build_executable(build, HOST_NAME)
    if not program.is_file():
        raise ConversionError('The Game Boy Advance probe host was not built.')
    return program


def input_script(frames: int, kind: str) -> str:
    """A deterministic key script in the engine's own format (`frame,0xKEYS`, active low).

    `boot` presses nothing. `generic` is not play: it presses A and Start now and then, then holds Right and taps A and B
    for the second half, which reaches menus and first scenes of most games and proves nothing about gameplay."""
    if kind == 'boot':
        return '# frame,keyinput_active_low\n0,0x03ff\n'
    events, previous = [], None
    for frame in range(frames):
        keys = (1 if frame % 20 < 2 else 0) | (8 if frame % 97 < 2 else 0)
        if frame >= frames // 2:
            keys |= 0x10 | (1 if frame % 45 < 3 else 0) | (2 if frame % 70 < 3 else 0)
        value = 0x3ff & ~keys
        if value != previous:
            events.append((frame, value))
            previous = value
    return '# frame,keyinput_active_low\n' + ''.join(f'{frame},0x{value:04x}\n' for frame, value in events)


def run_scenario(host: Path, rom_path: Path, rom_sha1: str, bios_path: Path, folder: Path, scenario: str, frames: int,
                 script: Path | None, timeout: int = 900, reference: bool = False) -> Run:
    """Run the probe host headless for `frames` frames of one scenario and collect what it reports."""
    work = folder / (scenario + ('-reference' if reference else ''))
    for stale in work.glob('*') if work.is_dir() else ():
        if stale.is_file():
            stale.unlink()
    work.mkdir(parents=True, exist_ok=True)
    coverage, miss, dump = work / 'coverage.json', work / 'miss.toml.frag', work / 'iwram.bin'
    values = {'GBARECOMP_COVERAGE_JSON': str(coverage), 'GBARECOMP_MISS_FRAG': str(miss),
              'GBARECOMP_IWRAM_DUMP': str(dump), 'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy',
              # A clock cartridge reads the host's wall clock, and the interpreter replay lasts a hundred times longer than the native
              # run: unpinned, the two runs see different seconds and a game that shows the time differs by a frame. In every
              # scenario the clock starts from a fixed time and advances with the guest's cycles (an anchored patch of the engine);
              # the exported player played by a person keeps the host's clock.
              'GBARECOMP_RTC_GUEST_EPOCH': RTC_EPOCH, 'GBARECOMP_VBLANK_SNAPSHOT': '1'}
    if script is not None:
        values['GBARECOMP_INPUT_REPLAY'] = str(script)
    if reference:
        values['GBARECOMP_FORCE_INTERP'] = '1'          # the engine's own interpreter runs every instruction
    environment = probe_environment(remove=('GBARECOMP_INPUT_REPLAY', 'GBARECOMP_FORCE_INTERP', 'GBARECOMP_STRICT_STATIC'),
                                    **values)
    command = [host, '--rom', rom_path, '--rom-sha1', rom_sha1, '--bios', bios_path, '--frames', str(frames),
               '--no-window', '--uncapped', '--volume', '0', '--save', work / 'game.sav', '--dump-png', work / 'frame.png']
    result = spawn(command, cwd=work, timeout=timeout, env=environment, phase='native_runs', stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    try:
        data = json.loads(coverage.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = {}
    aborted = next((line.strip() for line in result.stdout.splitlines()
                    if 'overflow' in line or 'abort' in line.lower() or 'FATAL' in line), '') if result.returncode else ''
    (work / 'output.log').write_text(result.stdout, encoding='utf-8', errors='replace')
    picture = work / 'frame.png'
    # The engine's final line also prints `cycles=`: the cycles it spent in its idle pump, which stopped growing after the first
    # seconds of every cartridge seen (62,191,750 on three of them). The snapshot is taken at the first VBlank after the frame limit.
    snapshot = re.search(r'vblank_snapshot frame=\d+ cycles=(\d+) mem=([0-9a-f]+) cpu=([0-9a-f]+)', result.stdout)
    return Run(scenario, frames, result.returncode, result.stdout, data,
               miss.read_text(encoding='utf-8') if miss.is_file() else '',
               dump.read_bytes() if dump.is_file() else None, aborted,
               hashlib.sha256(picture.read_bytes()).hexdigest() if picture.is_file() else '',
               int(snapshot[1]) if snapshot else None, snapshot[2] if snapshot else '', snapshot[3] if snapshot else '')
