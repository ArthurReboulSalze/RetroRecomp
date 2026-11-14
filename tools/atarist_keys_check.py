"""Atari ST quick states with an input held across F8 (gate G6): `python -B tools/atarist_keys_check.py [--pad GAME.exe] [--keys TEXT_GAME.exe]`, executables a conversion delivered (their disks and TOS inside them).

A state is saved while an input is held and a fresh process loads it and continues; the continuation (CPU registers, RAM, picture and sound of every frame) is compared with the unbroken timeline.

  --pad GAME.exe   a game that reads the joystick (Bomb Jack): the fire button, a direction and the mouse's left button are held from frame 900 to 1300 on top of the standard main route, and the state
                   is saved at frame 1000. Four timelines: a control (the holds change the timeline), held at F8 and still held at F9, held at F8 and released before F9, pressed after F8.
                   The pad and the mouse buttons are read again every frame, so they come back right by construction; this shows it.
  --keys GAME.exe  a text game on EmuTOS (The Lurking Horror): the key `n` is held from frame 1700 and the state is saved at 1800 while it is held; the resumed run, whose script holds nothing after 1800,
                   must continue the timeline in which `n` was released at 1800. The keyboard sends changes only: before 1.7.5 the key stayed down in the guest after the load (the whole continuation
                   differed); the adapted Hatari now releases the keys a snapshot holds down (`atarist_hatari`), and the adapter presses again the keys still held once the restore is over.

It runs the game's own executable headless (SDL dummy), no window, nothing kept but a scratch folder under `.build/atarist-keys-check`. It says nothing of the machine's fidelity or of gameplay.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WORK = ROOT / '.build' / 'atarist-keys-check'
FRAMES, PAD_SAVE = 1300, 1000
KEY_FRAMES, KEY_SAVE, KEY_FIRST = 2300, 1800, 1500
SPACE, KEY_N = 32, ord('n')
FIRE, RIGHT, LEFT_BUTTON = 4, 3, 2


def pad_holds(begin: int, end: int) -> list:
    """The fire button, the right direction and the mouse's left button held from `begin` to `end`."""
    return [(begin, end, 'joy', FIRE, 1), (begin, end, 'joy', RIGHT, 1), (begin, end, 'mouse', LEFT_BUTTON, 1)]


def key_script(held_until: int) -> list:
    """Space at the first prompt of The Lurking Horror, then the key `n` held from 1700 to `held_until`."""
    return [(KEY_FIRST, KEY_FIRST + 3, 'key', SPACE, 1), (1700, held_until, 'key', KEY_N, 1)]


def _run(ac, exe: Path, folder: Path, events: list, frames: int, extra=()) -> Path:
    folder.mkdir(parents=True)
    script = ac.write_events(folder / 'events.txt', sorted(events))
    copy = folder / exe.name
    shutil.copy2(exe, copy)
    ac.replay(copy, folder, frames, script, extra=list(extra), timer_d='patched')
    copy.unlink(missing_ok=True)
    return folder / 'trace.tsv'


def check_pad(exe: Path) -> list[str]:
    from retrorecomp import atarist_conversion as ac
    failures = []
    base = WORK / 'pad'
    shutil.rmtree(base, ignore_errors=True)
    route = ac.main_route(FRAMES)

    def expect(condition, text):
        print(f'pad: {"ok  " if condition else "FAIL"} {text}', flush=True)
        if not condition:
            failures.append(text)

    plain = _run(ac, exe, base / 'plain', route, FRAMES)
    held = _run(ac, exe, base / 'held', route + pad_holds(900, 1300), FRAMES)
    expect(not ac.continuation(plain, held)['matches'], 'control: the holds change the timeline')
    cases = (('held at F8 and still held at F9', pad_holds(900, 1300), pad_holds(900, 1300)),
             ('held at F8, released before F9', pad_holds(900, 1300), pad_holds(900, 1000)),
             ('pressed after F8', pad_holds(1000, 1300), pad_holds(1000, 1300)))
    for number, (name, saved, resumed) in enumerate(cases, 1):
        slot = base / f'case{number}.rrstate'
        _run(ac, exe, base / f'save{number}', route + saved, FRAMES, ['--state-save-at', str(PAD_SAVE), '--state-slot', str(slot)])
        line = _run(ac, exe, base / f'line{number}', route + resumed, FRAMES)
        back = _run(ac, exe, base / f'back{number}', route + resumed, FRAMES - PAD_SAVE, ['--state-load-start', '--state-slot', str(slot)])
        result = ac.continuation(line, back)
        expect(result['matches'], f"{name}: {result['equal_frames']} of {result['frames']} frames equal the timeline")
    return failures


def check_keys(exe: Path) -> list[str]:
    from retrorecomp import atarist_conversion as ac
    failures = []
    base = WORK / 'keys'
    shutil.rmtree(base, ignore_errors=True)

    def expect(condition, text):
        print(f'keys: {"ok  " if condition else "FAIL"} {text}', flush=True)
        if not condition:
            failures.append(text)

    none = _run(ac, exe, base / 'none', [(KEY_FIRST, KEY_FIRST + 3, 'key', SPACE, 1)], KEY_FRAMES)
    held = _run(ac, exe, base / 'held', key_script(2100), KEY_FRAMES)
    expect(not ac.continuation(none, held)['matches'], 'control: the held key changes the timeline')
    slot = base / 'k.rrstate'
    _run(ac, exe, base / 'save', key_script(2100), KEY_FRAMES, ['--state-save-at', str(KEY_SAVE), '--state-slot', str(slot)])
    line = _run(ac, exe, base / 'line', key_script(KEY_SAVE), KEY_FRAMES)
    back = _run(ac, exe, base / 'back', key_script(KEY_SAVE), KEY_FRAMES - KEY_SAVE, ['--state-load-start', '--state-slot', str(slot)])
    result = ac.continuation(line, back)
    expect(result['matches'], f"held at F8, released before F9: {result['equal_frames']} of {result['frames']} frames equal the timeline")
    return failures


def main(arguments) -> int:
    pad = keys = None
    rest = list(arguments)
    while rest:
        flag = rest.pop(0)
        if flag in ('--pad', '--keys') and rest:
            if flag == '--pad':
                pad = Path(rest.pop(0))
            else:
                keys = Path(rest.pop(0))
        else:
            print(__doc__)
            return 2
    if pad is None and keys is None:
        print(__doc__)
        return 2
    failures = []
    if pad is not None:
        failures += check_pad(pad)
    if keys is not None:
        failures += check_keys(keys)
    print('OK' if not failures else 'FAILED')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
