"""Determinism probe of the Neo Geo multiplayer snapshot, on a game the player converted (never in the repository).

    python -B tools/neogeo_snapshot_probe.py GAME.exe [--warm 300,2500,3001,4700] [--run 120] [--output DIR]

For each warm-up frame the game runs headless with its own `--snapshot-probe WARM RUN` (native/neogeo_main.c): it plays WARM
frames of the standard play route, saves a snapshot, plays RUN frames noting every digest, saves again, loads the first snapshot and
plays the same RUN frames. Passing means every digest and the last snapshot, byte for byte, are the same; a save over a buffer of
other bytes is identical; a snapshot saved right after a load is the one loaded; a buffer that is too small is not written; a wrong
size or a buffer of zeros is refused and changes nothing. Exit 0 when every warm-up point passes. No timing is taken.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp.neogeo_validation import ROUTES   # noqa: E402

HIDDEN = {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'}


def probe(exe: Path, warm: int, run: int, script: Path) -> dict:
    result = subprocess.run([str(exe), '--headless', '--frames', '1', '--standard', '--rtc-seed', '1760000000', '--script', str(script),
                             '--snapshot-probe', str(warm), str(run)], cwd=exe.parent, capture_output=True, text=True,
                            timeout=600, env={**os.environ, **HIDDEN})
    try:
        row = json.loads(result.stdout.strip().splitlines()[-1])['snapshot_probe']
    except (IndexError, KeyError, ValueError):
        row = {'passed': False, 'error': result.stderr.strip()[:300] or 'no result'}
    row['exit_code'] = result.returncode
    row['passed'] = bool(row.get('passed')) and result.returncode == 0
    row['log'] = (result.stdout + result.stderr).strip()
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('game', type=Path)
    parser.add_argument('--warm', default='300,2500,3001,4700', help='comma-separated warm-up frames')
    parser.add_argument('--run', type=int, default=120)
    parser.add_argument('--output', type=Path, default=ROOT / '.build' / 'neogeo-snapshot-probe')
    options = parser.parse_args()
    exe = options.game.resolve()
    options.output.mkdir(parents=True, exist_ok=True)
    script = (options.output / 'play.inputs').resolve()
    script.write_text(ROUTES['play'][1], encoding='ascii')
    passed = True
    for warm in (int(item) for item in options.warm.split(',')):
        row = probe(exe, warm, options.run, script)
        (options.output / f'probe-{warm}.json').write_text(json.dumps(row, indent=1), encoding='utf-8')
        passed &= row['passed']
        print(warm, 'PASS' if row['passed'] else 'FAIL', {key: value for key, value in row.items() if key != 'log'})
    print('PASS' if passed else 'FAILED')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
