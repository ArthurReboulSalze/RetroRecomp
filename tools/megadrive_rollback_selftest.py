"""Mega Drive multiplayer rollback: the determinism probe of native/md_rollback_checks.c, linked with a game build.

`python -B tools/megadrive_rollback_selftest.py PROJECT --output DIR [--game-frames N]` links the checks with the objects
of a kept Mega Drive build (a conversion with --keep-build) and runs them twice: `authored` (an authored program in work
RAM, no game code: frames end with the 68000 inside an instruction under DMA, with the sound CPU inside a bus read and
with a bus request pending, each a rollback that must replay exactly, plus negative controls) and `game` (that build's own
game from power-on with changing pads). The game's dump stays where the player's build put it; nothing of it is kept here.
"""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
from retrorecomp.core import run
from megadrive_bus_selftest import native_executable


def check(project, output, game_frames=1800):
    harness = (ROOT / 'native/md_rollback_checks.c').read_text(encoding='utf-8')
    exe = native_executable(project, output, harness)
    result = {}
    for mode, extra in (('authored', []), ('game', [str(game_frames)])):
        text = run([exe, mode, *extra], timeout=1800).strip().splitlines()[-1]
        result[mode] = json.loads(text)
    (output / 'rollback.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('project', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--game-frames', type=int, default=1800)
    args = parser.parse_args()
    print(json.dumps(check(args.project.resolve(), args.output.resolve(), args.game_frames)))
