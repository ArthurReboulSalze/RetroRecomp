"""The memory card of a converted PlayStation game, in fresh processes of the delivered file (gate G7 evidence).

    python tools/psx_saves_check.py EXE --save ROUTE --save-frames N --load ROUTE --load-frames M [--out DIR]

ROUTE is an input script of the game ("frame p1 p2" lines, the pads' hex words, as the conversion's routes; tools/psx_routes/).
Every run is headless (no window, no sound out) with `--card`, the option that reads and writes a card file as the window does
its own `datas/saves` card:

1. the save route runs with no card file: the game must write one (the file is only written when the card changed);
2. a fresh process plays the load route with that card, and another with none: their traces must differ (the game read it),
   and each leaves its last picture for a person to read;
3. five unusable card files (empty, half, one byte short, one byte long, a folder) are each set aside whole as
   `<card>.unusable-1` and the game plays the load route as with no card (same trace).

Writes only under --out (default `.build/psx-saves/<exe name>`): the cards, traces, pictures and `saves.json`. Reads the game.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
CARD_BYTES = 128 * 1024


def run(exe: Path, folder: Path, name: str, frames: int, script: Path, card: Path, capture: bool = False) -> dict:
    """One headless run; returns its exit code, its trace rows (frame, ram, picture, sound, CPU) and its report."""
    folder.mkdir(parents=True, exist_ok=True)
    trace, report = folder / f'{name}.csv', folder / f'{name}.json'
    command = [str(exe), '--headless', '--frames', str(frames), '--script', str(script), '--card', str(card),
               '--trace', str(trace), '--report', str(report)]
    if capture:
        pictures = folder / f'{name}-pictures'
        pictures.mkdir(exist_ok=True)
        command += ['--capture', str(pictures), '--capture-every', str(frames)]
    environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    result = subprocess.run(command, cwd=folder, env=environment, capture_output=True, text=True, creationflags=NO_WINDOW,
                            timeout=max(900, frames // 3))
    rows = trace.read_text(encoding='ascii').splitlines()[1:] if trace.is_file() else []
    fields = json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {}
    return {'exit': result.returncode, 'rows': rows, 'frames': fields.get('frames'), 'stderr': result.stderr.strip()[-300:]}


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def saved_files(card: bytes) -> list[str]:
    """The files of a card's directory (frames 1 to 15: state 0x51 is the first block of a file, then its name)."""
    names = []
    for frame in range(1, 16):
        entry = card[frame * 128:(frame + 1) * 128]
        if entry[0] == 0x51:
            names.append(entry[10:30].split(b'\0')[0].decode('ascii', 'replace'))
    return names


def damaged(good: bytes) -> dict:
    return {'empty': b'', 'half': good[:len(good) // 2], 'one-byte-short': good[:-1], 'one-byte-long': good + b'\0',
            'folder': None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('exe', type=Path)
    parser.add_argument('--save', type=Path, required=True)
    parser.add_argument('--save-frames', type=int, required=True)
    parser.add_argument('--load', type=Path, required=True)
    parser.add_argument('--load-frames', type=int, required=True)
    parser.add_argument('--out', type=Path)
    arguments = parser.parse_args()
    exe = arguments.exe.resolve()
    out = (arguments.out or ROOT / '.build' / 'psx-saves' / exe.stem).resolve()
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    save, load = arguments.save.resolve(), arguments.load.resolve()
    result = {'exe': exe.name, 'exe_sha256': digest(exe), 'save_route': save.name, 'load_route': load.name,
              'save_route_sha256': digest(save), 'load_route_sha256': digest(load)}
    checks = {}

    card = out / 'saved' / 'card.mcr'
    saved = run(exe, out / 'saved', 'save', arguments.save_frames, save, card, capture=True)
    written = card.is_file() and card.stat().st_size == CARD_BYTES
    files = saved_files(card.read_bytes()) if written else []
    result['saved_files'] = files
    # The core gives a formatted card that the card file may record before any game save: a file in its directory is the save.
    checks['the save route writes a file on the card'] = saved['exit'] == 0 and bool(files)
    result['card_sha256'] = digest(card)
    if not files:
        result['checks'] = checks
        (out / 'saves.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(checks, indent=2))
        return 1

    kept = card.read_bytes()
    with_card = out / 'with-card' / 'card.mcr'
    with_card.parent.mkdir(parents=True)
    with_card.write_bytes(kept)
    loaded = run(exe, out / 'with-card', 'load', arguments.load_frames, load, with_card, capture=True)
    empty = run(exe, out / 'no-card', 'load', arguments.load_frames, load, out / 'no-card' / 'card.mcr', capture=True)
    difference = next((n for n, (a, b) in enumerate(zip(loaded['rows'], empty['rows'])) if a != b), None)
    checks['a fresh process with the card runs to its end'] = loaded['exit'] == 0 and loaded['frames'] == arguments.load_frames
    checks['the game read the card (its trace differs from the run with none)'] = difference is not None
    result['first_frame_that_differs_from_no_card'] = None if difference is None else difference + 1

    variants = {}
    for label, data in damaged(kept).items():
        folder = out / f'damaged-{label}'
        folder.mkdir()
        target = folder / 'card.mcr'
        if data is None:
            target.mkdir()
            (target / 'inside.txt').write_text('a folder where the card goes\n', encoding='ascii')
        else:
            target.write_bytes(data)
        before = None if data is None else hashlib.sha256(data).hexdigest()
        run_ = run(exe, folder, 'load', arguments.load_frames, load, target)
        aside = folder / 'card.mcr.unusable-1'
        kept_whole = aside.is_dir() and (aside / 'inside.txt').is_file() if data is None else digest(aside) == before
        same = run_['rows'] == empty['rows']
        variants[label] = {'exit': run_['exit'], 'set_aside_whole': kept_whole, 'plays_as_with_no_card': same,
                           'stderr': run_['stderr']}
    checks['every unusable card file is set aside whole and the game plays as with no card'] = all(
        v['exit'] == 0 and v['set_aside_whole'] and v['plays_as_with_no_card'] for v in variants.values())
    result['damaged'] = variants
    result['checks'] = checks
    (out / 'saves.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(checks, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
