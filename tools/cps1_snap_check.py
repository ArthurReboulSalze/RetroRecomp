"""The determinism probe of a converted CPS-1, CPS-1.5 or CPS-2 game for the multiplayer rollback tier (hostkit_session.h).

    python -B tools/cps1_snap_check.py GAME.exe [--timeout SECONDS]

Runs the game's own `--snapshot-check` (native/cps1_main.c) headless: a snapshot is saved, frames are run and their digests and
pictures recorded, the snapshot is loaded and the same frames run again; the digests and the first pictures must be equal (a snapshot
holds no picture: the first live frame after a load redraws it all), a snapshot of another size must be refused with the machine left
as it was, a save over other bytes must give the same bytes, and the digest must see a changed byte. It is done at four phases of the
game's run, with pseudo-random pads (coins and Start included). It needs a game the player converted (never in the repository) and
shows nothing of hardware fidelity or latency: it says the machine can be rolled back bit for bit.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def check(game: Path, timeout: int = 600) -> dict:
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    result = subprocess.run([str(game), '--snapshot-check'], capture_output=True, text=True, timeout=timeout, env=env,
                            cwd=str(game.parent))
    lines = [line for line in result.stdout.splitlines() if line.startswith('{')]
    summary = json.loads(lines[-1]) if lines else {}
    summary['exit_status'] = result.returncode
    summary['failures'] = [line for line in result.stderr.splitlines() if line.startswith('FAIL')]
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('game', type=Path)
    parser.add_argument('--timeout', type=int, default=600)
    arguments = parser.parse_args()
    summary = check(arguments.game.resolve(), arguments.timeout)
    print(json.dumps(summary))
    ok = summary.get('exit_status') == 0 and summary.get('failed') == 0 and summary.get('passed', 0) > 0
    print('PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
