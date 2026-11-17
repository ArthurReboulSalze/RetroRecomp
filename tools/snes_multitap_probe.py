"""Does a converted Super Nintendo game talk to a Super Multitap? Evidence for the converter's list (retrorecomp/snes_multitap.py).

    python -B tools/snes_multitap_probe.py GAME.exe [GAME.exe ...] [--frames 1800] [--out DIR]

Each game runs twice, hidden (SDL's dummy drivers), over the same pseudo-random route of its two pads: once as built and once with
`SNES_MULTITAP=port2` (the engine puts a tap in console port 2: the first pad of the tap is the second player's, as with no tap). A
game that does not look for a tap behaves the same both ways; one that detects the tap (it strobes and reads the second data line,
or reads the pads 3 and 4 registers) ends in another state. The probe says "tap aware" when the work RAM, the CPU or the sound state
differ at the end. It is evidence, not a proof of a number of players: the games' own menus decide how many pads they use, and
a route that never reaches the detection says "same", which is not a proof that the game ignores a tap.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

KEYS = ('ram_hash', 'cpu_hash', 'apu_ram_hash', 'dsp_state_hash', 'vram_hash')
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0


def run(game: Path, frames: int, folder: Path, tap: bool) -> dict:
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    report = folder / ('tap.json' if tap else 'plain.json')
    environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    environment.pop('SNES_MULTITAP', None)
    if tap:
        environment['SNES_MULTITAP'] = 'port2'
    done = subprocess.run([str(game.resolve()), '--frames', str(frames), '--report', str(report), '--play'], cwd=folder, env=environment,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WINDOW, timeout=1800)
    if done.returncode != 0 or not report.is_file():
        raise SystemExit(f'{game.name}: the run failed ({done.returncode})\n{done.stdout.decode(errors="replace")[-800:]}')
    return json.loads(report.read_text(encoding='utf-8'))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('games', nargs='+', type=Path)
    parser.add_argument('--frames', type=int, default=1800)
    parser.add_argument('--out', type=Path, default=Path('.build/snes-multitap-probe'))
    args = parser.parse_args()
    results = []
    for game in args.games:
        folder = args.out / game.stem
        plain, tapped = run(game, args.frames, folder, False), run(game, args.frames, folder, True)
        differ = [key for key in KEYS if plain.get(key) != tapped.get(key)]
        results.append({'game': game.stem, 'frames': args.frames, 'tap_aware': bool(differ), 'differs': differ})
        print(json.dumps(results[-1]), flush=True)
    (args.out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    sys.exit(main())
