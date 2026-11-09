"""Atari ST saves on a real game (gate G7): `python -B tools/atarist_saves_game.py GAME.ipf TOS104.img [EMUTOS.img]`, disks and TOS the player's own, read in place, never copied here.

The Lurking Horror (Infocom) saves by GEMDOS on its own disk, under the player's file name. The route walks one room, saves, and a new process, given the file of the disk writes, restores: the
game must find the room it left, which a process without the file cannot. Run on the TOS 1.04 desktop (mouse) and, with EmuTOS, through the autostart: EmuTOS seeks without verifying, which is
what showed that a write after such a seek looked on the wrong track (the adaptation of `src/fdc.c`). What is compared is the picture at the end; a route is numbers, the game's bytes stay out.
This shows the saving path on one game on two TOSes. It says nothing of the machine's fidelity or of gameplay. No window: SDL dummy, headless.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WORK = ROOT / '.build' / 'atarist-saves-game'
SPACE, RETURN = 32, 13
KEY_FRAMES, KEY_GAP = 3, 7
SAVE_NAME = 'rrsave.sav'
# The disk's writes on the two TOSes: its directory sector, 24 data sectors, the two FATs' sectors.
EXPECTED_WRITES = 27
# From the TOS 1.04 desktop: the cursor to the corner, drive A, its window, the program. A route for this one disk.
DESKTOP = [(1300, 1306, 'mouse', 0, -25), (1300, 1306, 'mouse', 1, -16), (1310, 1311, 'mouse', 0, 36), (1310, 1311, 'mouse', 1, 24), (1320, 1323, 'mouse', 2, 1), (1326, 1329, 'mouse', 2, 1),
           (1400, 1401, 'mouse', 0, -2), (1400, 1401, 'mouse', 1, 54), (1420, 1423, 'mouse', 2, 1), (1426, 1429, 'mouse', 2, 1)]


def typed(start: int, text: str) -> list:
    """Key events for text, one key every few frames; `|` is Return."""
    events = []
    for n, character in enumerate(text):
        code = RETURN if character == '|' else ord(character)
        events.append((start + n * KEY_GAP, start + n * KEY_GAP + KEY_FRAMES, 'key', code, 0))
    return events


def save_route(start: int) -> tuple[list, int]:
    """From the moment the game shows its [MORE]: one room south, then save under our name. `start`: that moment. Returns the events and the frames to run."""
    return ([(start, start + KEY_FRAMES, 'key', SPACE, 0)] + typed(start + 60, 'south|') + typed(start + 220, 'save|') + typed(start + 330, SAVE_NAME + '|'), start + 900)


def restore_route(start: int) -> tuple[list, int]:
    """Restore under our name, then show the room."""
    return ([(start, start + KEY_FRAMES, 'key', SPACE, 0)] + typed(start + 60, 'restore|') + typed(start + 180, SAVE_NAME + '|') + typed(start + 400, 'look|'), start + 800)


def write_events(path: Path, events: list) -> Path:
    path.write_text(''.join(f'{begin} {end} {kind} {code} {value}\n' for begin, end, kind, code, value in sorted(events)), encoding='ascii', newline='\n')
    return path


def check_tos(player: Path, check, disk: Path, tos: Path, name: str, desktop: list, start: int, extra: tuple) -> list[str]:
    folder = WORK / name
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    failures = []

    def expect(condition, text):
        print(f'{name}: {"ok  " if condition else "FAIL"} {text}', flush=True)
        if not condition:
            failures.append(f'{name}: {text}')

    before = hashlib.sha256(disk.read_bytes()).hexdigest()
    writes = folder / 'writes.bin'
    events, frames = save_route(start)

    def run(run_name, route, count, with_writes):
        place = folder / run_name
        place.mkdir()
        done = check.run_once(player, tos, disk, place, '--input-events', str(write_events(place / 'events.txt', route)), '--capture', 'cap.ppm', *extra,
                              *(('--disk-writes', str(writes)) if with_writes else ()), frames=count)
        return done['report'], (place / 'cap.ppm').read_bytes()

    report, _ = run('save', desktop + events, frames, True)
    expect(report['disk_writes'] == EXPECTED_WRITES, f'the game saved: {report["disk_writes"]} sectors written, {EXPECTED_WRITES} expected')
    expect(writes.is_file(), 'the file of the disk writes exists')
    expect(hashlib.sha256(disk.read_bytes()).hexdigest() == before, 'the image itself is unchanged')
    written = writes.read_bytes() if writes.is_file() else b''
    events, frames = restore_route(start)
    report, restored = run('restore', desktop + events, frames, True)
    _, without = run('without', desktop + events, frames, False)
    expect(report['disk_writes'] == EXPECTED_WRITES, 'a new process finds the writes')
    expect(writes.read_bytes() == written, 'restoring writes nothing')
    expect(restored != without, 'the game restored: its picture differs from a process without the file')
    print(f'{name}: look at {folder / "restore" / "cap.ppm"} and {folder / "without" / "cap.ppm"}: the room of the save, against the first room')
    return failures


def main(arguments) -> int:
    if len(arguments) < 2:
        print(__doc__)
        return 2
    spec = importlib.util.spec_from_file_location('atarist_saves_check', ROOT / 'tools' / 'atarist_saves_check.py')
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    player = check.reference_player()
    disk, tos = Path(arguments[0]), Path(arguments[1])
    failures = check_tos(player, check, disk, tos, 'tos104', DESKTOP, 3500, ())
    if len(arguments) > 2:
        failures += check_tos(player, check, disk, Path(arguments[2]), 'emutos', [], 1500, ('--autostart', 'A:\\LURKING.PRG'))
    print('OK' if not failures else 'FAILED')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
