"""Two Game Boy consoles on a link cable in one process, on a converted game, with scripted pads, no window.

Runs the delivered game twice, headless, in an empty scratch folder each time: once showing console 0 and once showing console 1 (the view is the
only difference), with the test hooks of the adapter (RETRO_RECOMP_GB_LINK=2, RETRO_RECOMP_GB_LINK_VIEW, RETRO_RECOMP_GB_LINK_SCRIPT for the second
console; `--input` for the first). The digest of the pair is logged every 60 frames: the two runs must print the same lines (the run is
deterministic and the view does not move it), and the cable must have exchanged bytes. The pictures of the chosen frames are written as PPM files of
both runs, for a person to look at (the game screens are never kept in the repository).

    python -B tools/gameboy_link_play.py GAME.exe --frames 1500 --script0 "450:S:4,..." --script1 "450:S:4,..." --dump 1000,1499 --out .build/gb-link-play/x

The scripts are the format of `--input` (frame:buttons:duration; U D L R A B S=Start T=Select). Writes <out>/result.json; exit code 1 when the two runs differ.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile


def run_view(game: Path, view: int, frames: int, script0: str, script1: str, dump: str, out: Path) -> dict:
    folder = out / f'view{view}'
    folder.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, RETRO_RECOMP_GB_LINK='2', RETRO_RECOMP_GB_LINK_VIEW=str(view), RETRO_RECOMP_GB_LINK_LOG='1',
               RETRO_RECOMP_GB_LINK_SCRIPT=script1)
    with tempfile.TemporaryDirectory() as scratch:                       # an empty folder, and a copy of the game in it: a cartridge save is written beside the executable
        copy = Path(scratch) / game.name
        shutil.copy2(game, copy)
        command = [str(copy), '--headless', '--limit-frames', str(frames), '--input', script0]
        if dump:
            command += ['--dump-frames', dump, '--screenshot-prefix', str(folder / 'frame')]
        done = subprocess.run(command, cwd=scratch, env=env, capture_output=True, text=True, timeout=900,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    lines = [line for line in (done.stderr + done.stdout).splitlines() if line.startswith('[link] frame')]
    (folder / 'output.log').write_text(done.stderr + done.stdout, encoding='utf-8')
    exchanges = int(lines[-1].rsplit(' ', 1)[1]) if lines else 0
    return {'view': view, 'exit_code': done.returncode, 'lines': lines, 'exchanges': exchanges}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('game', type=Path)
    parser.add_argument('--frames', type=int, default=1500)
    parser.add_argument('--script0', default='')
    parser.add_argument('--script1', default='')
    parser.add_argument('--dump', default='')
    parser.add_argument('--out', type=Path, default=Path('.build/gb-link-play/run'))
    args = parser.parse_args()
    args.out = args.out.resolve()                                          # the game runs in another folder: absolute paths only
    args.game = args.game.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    first = run_view(args.game, 0, args.frames, args.script0 or '0:A:1', args.script1 or '0:A:1', args.dump, args.out)
    second = run_view(args.game, 1, args.frames, args.script0 or '0:A:1', args.script1 or '0:A:1', args.dump, args.out)
    same = bool(first['lines']) and first['lines'] == second['lines']
    result = {'game': args.game.name, 'frames': args.frames, 'digest_lines': len(first['lines']), 'identical_between_processes': same,
              'exchanges': first['exchanges'], 'exit_codes': [first['exit_code'], second['exit_code']],
              'last_line': first['lines'][-1] if first['lines'] else ''}
    (args.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)
    return 0 if same and first['exchanges'] > 0 and first['exit_code'] == 0 and second['exit_code'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
