"""Check save/relaunch continuation on one generated NES EXE, without a window.

The check itself is `retrorecomp.nes_checks.check_states`, the one a conversion runs on the file it delivers."""
import argparse
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.nes_checks import check_states, resume_input  # noqa: E402,F401  (resume_input: kept for the callers of this tool)


def check(executable: Path, frames: int = 180, *, save_after: int | None = None, script: Path | None = None) -> dict:
    return check_states(executable, frames, save_after=save_after, script=script)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executables', nargs='+', type=Path)
    parser.add_argument('--frames', type=int, default=180)
    parser.add_argument('--save-after', type=int)
    parser.add_argument('--input', type=Path)
    args = parser.parse_args()
    for executable in args.executables:
        print(json.dumps(check(executable.resolve(), args.frames, save_after=args.save_after, script=args.input)), flush=True)
