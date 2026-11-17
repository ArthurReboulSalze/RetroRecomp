"""The Atari ST's in-process snapshot, proved without a ROM (multiplayer rollback): `python -B tools/atarist_snapshot_check.py [program ...]`.

Needs a compiler and the pinned Hatari tree (the adapted one is built when missing, like `tools/atarist_hardware_check.py`, whose authored programs this uses: tiny 68000 programs booted as
the TOS image of a session, no firmware, no game, no disk but an authored one). For each program and each save frame, `native/atarist_machine/atarist_snapshot_checks.c` runs the contract
of `docs/HOST_KIT.md` (multiplayer) on the functions a match calls (`native/atarist_machine/atarist_snapshot.h`): save at a frame, run N frames, load, run the same N frames, every
digest equal; the load complete at once (the digest and a save right after it, before any frame), a save over other bytes equal to a clean one, a wrong size, a damaged header and
another disk refused with the machine untouched, and the table of sectors a game wrote restored.

Programs: timers (the MFP's timers A and B and their interrupts, the frame counter), picture (the Shifter's palette and video base), psg (the YM2149 at a tone), ikbd (the keyboard
controller with joystick events from the frames of the run), floppy (the WD1772's seeks and DMA reads of an authored disk: the save lands in the middle of controller commands).
The save frames are several, some inside an interrupt's or a command's activity. It measures no time and says nothing of fidelity or gameplay; the size of a snapshot is printed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

import atarist_hardware_check as hw   # noqa: E402

WORK = Path(os.environ.get('RR_ATARIST_SNAPSHOT_WORK') or ROOT / '.build' / 'atarist-snapshot-check')
JOYSTICK_EVENTS = ['80 joy 1 8', '90 joy 1 0', '100 joy 0 1', '110 joy 0 0', '120 joy 1 6', '130 joy 1 0', '160 joy 1 16', '170 joy 1 0', '180 joy 0 16', '190 joy 0 0']


def programs() -> dict:
    """name -> (TOS image, frames, disk, events, save frames, span): the authored programs of the hardware check, with the frames at which a state is saved."""
    return {
        'timers': (hw.timer_program(2, 3, 0x40, 240, 100), 260, None, [], (37, 61, 100, 151), 60),
        'picture': (hw.picture_program(), 120, None, [], (5, 6, 31), 40),
        'psg': (hw.psg_program(254), 150, None, [], (20, 47, 90), 50),
        'ikbd': (hw.ikbd_program([0x12, 0x14]), 260, None, JOYSTICK_EVENTS, (85, 105, 125, 165), 50),
        'floppy': (hw.wd_program(), 700, hw.disk_image(), [], (60, 150, 233, 411), 120),
    }


def build_driver() -> Path:
    """The driver linked with the session and the adapted Hatari."""
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args
    tree, build = hw.ensure_hatari()
    machine = (ROOT / 'native' / 'atarist_machine').as_posix()
    folder = WORK / 'driver'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'CMakeLists.txt').write_text(f"""cmake_minimum_required(VERSION 3.20)
project(RetroAtariSTSnapshot C)
set(CMAKE_C_STANDARD 11)
set(RR_HATARI_TREE "{tree.as_posix()}")
set(RR_HATARI_BUILD "{build.as_posix()}")
find_library(RR_HATARI_CORE NAMES retro-hatari libretro-hatari PATHS "${{RR_HATARI_BUILD}}/src" NO_DEFAULT_PATH REQUIRED)
add_executable(checks "{machine}/atarist_snapshot_checks.c" "{machine}/atarist_session.c")
target_include_directories(checks PRIVATE "{machine}" "{machine}/libretro" "${{RR_HATARI_BUILD}}"
    "${{RR_HATARI_TREE}}/src/includes" "${{RR_HATARI_TREE}}/src/cpu" "${{RR_HATARI_TREE}}/src/cpu/softfloat" "${{RR_HATARI_TREE}}/src/debug"
    "${{RR_HATARI_TREE}}/src/falcon" "${{RR_HATARI_TREE}}/src" "${{RR_HATARI_TREE}}" "${{RR_HATARI_BUILD}}/src/cpu")
target_link_libraries(checks PRIVATE "${{RR_HATARI_CORE}}")
if(NOT WIN32)
  target_link_libraries(checks PRIVATE m)
else()
  target_link_libraries(checks PRIVATE ws2_32)
endif()
target_compile_options(checks PRIVATE -O2 -g -fno-fast-math)
""", encoding='utf-8', newline='\n')
    cmake, generator = toolchain()
    run([cmake, '-S', folder, '-B', folder / 'build', '-G', generator, *cmake_target_args(), '-DCMAKE_BUILD_TYPE=Release'], log=folder / 'build.log')
    run([cmake, '--build', folder / 'build', '--parallel', build_jobs()], log=folder / 'build.log', timeout=1800)
    return build_executable(folder / 'build', 'checks')


def run_one(driver: Path, name: str, image: bytes, frames: int, disk: bytes | None, events: list[str], save_at: int, span: int, writes: bool) -> dict:
    folder = WORK / 'runs'
    folder.mkdir(parents=True, exist_ok=True)
    stem = f'{name}-{save_at}{"-w" if writes else ""}'
    (folder / f'{stem}.tos').write_bytes(image)
    command = [str(driver), '--tos', str(folder / f'{stem}.tos'), '--frames', str(frames), '--save-at', str(save_at), '--span', str(span)]
    if disk is not None:
        (folder / f'{stem}.st').write_bytes(disk)
        command += ['--disk', str(folder / f'{stem}.st')]
    if events:
        (folder / f'{stem}.events').write_text('\n'.join(events) + '\n', encoding='ascii', newline='\n')
        command += ['--events', str(folder / f'{stem}.events')]
    if writes:
        command.append('--writes')
    done = subprocess.run(command, cwd=folder, capture_output=True, text=True, timeout=600, env=dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy'))
    line = next((entry for entry in done.stdout.splitlines() if entry.startswith('{')), None)
    if line is None:
        return {'ok': False, 'failed': f'no result (exit {done.returncode}): {done.stderr.strip()[-200:]}'}
    return json.loads(line)


def main(arguments) -> int:
    wanted = set(arguments)
    catalog = programs()
    if wanted - set(catalog):
        print('programs:', ', '.join(catalog))
        return 2
    driver = build_driver()
    failures = []
    for name, (image, frames, disk, events, saves, span) in catalog.items():
        if wanted and name not in wanted:
            continue
        for save_at in saves:
            result = run_one(driver, name, image, frames, disk, events, save_at, span, False)
            ok = result.get('ok') is True
            print(f"{name:8} save at {save_at:4} span {span}: {'ok  ' if ok else 'FAIL'} snapshot {result.get('snapshot_bytes', '?')} bytes (bound {result.get('bound', '?')})"
                  + ('' if ok else f" {result.get('failed')}"), flush=True)
            if not ok:
                failures.append(f'{name}@{save_at}: {result.get("failed")}')
    # the table of sectors a game wrote: on the floppy program (the session's disk is in drive A)
    image, frames, disk, events, saves, span = catalog['floppy']
    result = run_one(driver, 'floppy', image, frames, disk, events, 150, span, True)
    ok = result.get('ok') is True
    print(f"floppy   save at  150 with a table of writes: {'ok  ' if ok else 'FAIL'}" + ('' if ok else f" {result.get('failed')}"), flush=True)
    if not ok:
        failures.append(f'writes: {result.get("failed")}')
    print('OK' if not failures else 'FAILED: ' + '; '.join(failures))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
