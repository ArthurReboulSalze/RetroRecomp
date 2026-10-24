"""X68000: two builds of one exported game, frame by frame, and a quick state across them.

    python tools/x68000_cross.py A.exe B.exe [--frames N] [--save-at N] [--resume N] [--events FILE]

A and B are the Visual Studio and the portable-toolchain builds of one game.
Both run headless from a cold start (with the same optional input events);
their per-frame traces (CPU, memory, image and sound hashes) must be identical.
Each build writes a quick state and resumes it in a fresh process on its own
timeline. A state of the other compiler is refused: the X68000 state key
includes the compiler, by design.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def replay(exe: Path, folder: Path, frames: int, *extra) -> list[str]:
    folder.mkdir(parents=True, exist_ok=True)
    game = folder / exe.name
    if not game.exists():
        shutil.copy2(exe, game)
    trace = folder / f'trace-{len(list(folder.glob("trace-*.tsv")))}.tsv'
    command = [str(game), '--headless', '--mute', '--frames', str(frames), '--trace', str(trace), *map(str, extra)]
    result = subprocess.run(command, cwd=folder, capture_output=True, timeout=1800)
    if result.returncode:
        raise RuntimeError(f'{exe.name}: exit {result.returncode}: {result.stderr[-1500:]!r}')
    return trace.read_text(encoding='utf-8').splitlines()


def columns(rows: list[str]) -> list[list[str]]:
    return [row.split('\t')[1:] for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first', type=Path)
    parser.add_argument('second', type=Path)
    parser.add_argument('--frames', type=int, default=1200)
    parser.add_argument('--save-at', type=int, default=800)
    parser.add_argument('--resume', type=int, default=300)
    parser.add_argument('--events', type=Path, help='input events file, as written by the converter')
    args = parser.parse_args()
    events = ['--input-events', args.events.resolve()] if args.events else []
    exes = {'a': args.first.resolve(), 'b': args.second.resolve()}
    result = {}
    with tempfile.TemporaryDirectory(prefix='x68000-cross-') as temp:
        folders = {name: Path(temp) / name for name in exes}
        slots = {name: folders[name] / 'quick.rrstate' for name in exes}
        rows = {name: replay(exe, folders[name], args.frames, '--state-save-at', args.save_at,
                             '--state-slot', slots[name], *events) for name, exe in exes.items()}
        a, b = columns(rows['a']), columns(rows['b'])
        mismatch = next((n for n, (x, y) in enumerate(zip(a, b)) if x != y), None)
        result['frames_compared'] = len(a)
        result['same_trace_in_both_builds'] = mismatch is None and len(a) == len(b)
        result['first_trace_mismatch'] = mismatch
        # The state key includes the compiler's identity (x68000_reference/CMakeLists.txt): a build
        # resumes its own states, and refuses another compiler's, by design.
        result['own_states_resume'] = True
        result['other_compiler_state_refused'] = True
        result['state_bytes'] = {}
        for name, exe in exes.items():
            resumed = replay(exe, folders[name] / 'resume', args.resume, '--state-load-start', '--state-slot', slots[name], *events)
            own = columns(rows[name])[args.save_at + 2:args.save_at + 1 + args.resume]
            result['own_states_resume'] &= bool(own) and own == columns(resumed)[2:2 + len(own)]
            result['state_bytes'][name] = slots[name].stat().st_size
        for name, other in (('a', 'b'), ('b', 'a')):
            try:
                replay(exes[name], folders[name] / 'foreign', 20, '--state-load-start', '--state-slot', slots[other], *events)
            except RuntimeError as error:
                result['other_compiler_state_refused'] &= 'rejected' in str(error)
            else:
                result['other_compiler_state_refused'] = False
        result['same_state_size'] = result['state_bytes']['a'] == result['state_bytes']['b']
    import json
    print(json.dumps(result, indent=2))
    good = result['same_trace_in_both_builds'] and result['own_states_resume'] and result['same_state_size']
    return 0 if good else 1


if __name__ == '__main__':
    sys.exit(main())
