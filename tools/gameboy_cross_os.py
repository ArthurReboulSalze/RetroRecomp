"""Game Boy: one game built on two systems, frame by frame (gate G13, the cross-OS witness).

    python tools/gameboy_cross_os.py trace EXE --out DIR
    python tools/gameboy_cross_os.py compare DIR_A DIR_B

`trace` reads the routes the conversion of EXE played from the report beside it (`datas/reports/*/conversion-report.json`: each final
scenario with its frames and input script) and adds one pseudo-random route of 18,000 frames when the scan level made none. It runs the
delivered executable on each route headless, from a private copy and an empty folder so that no battery file of an earlier run is read,
and keeps, in DIR, the per-frame trace of the runtime (picture, sound, work RAM and program counter hashes, `--frame-trace`), the
final state dump and a `summary.json` with their SHA-256. Run it once on Windows and once on Debian, each on the game that system's
converter built from the same source with an empty library; `compare` then says, route by route, whether the two are identical and, if
not, the first frame and the columns that differ. Only hashes and counters are kept: no ROM byte and no picture.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
LONG_FRAMES = 18000


def sha256(path: Path) -> str:
    """The SHA-256 of a text file as if it had Unix line ends: Windows writes the traces with CR LF."""
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def routes_of(executable: Path) -> dict[str, tuple[str, int]]:
    """The routes of the conversion that made `executable`: name -> (input script, frames)."""
    reports = sorted((executable.parent / 'datas' / 'reports').glob('*/conversion-report.json'))
    if not reports:
        raise SystemExit(f'no conversion report beside {executable}')
    # A folder may hold several games (a batch): take the report of this executable, not the first one.
    loaded = [json.loads(path.read_text(encoding='utf-8')) for path in reports]
    report = next((item for item in loaded if item.get('executable') == executable.name), loaded[0])
    plan = {check['scenario']: (check.get('input_script') or '', int(check['frames'])) for check in report.get('final_checks', [])}
    if not any(name.startswith('long') for name in plan):
        from retrorecomp.random_routes import gameboy_script, long_routes
        built = long_routes('gb', report['rom']['sha256'], count=1, frames=LONG_FRAMES, two_players=False)[0]
        plan['long'] = (gameboy_script(built), LONG_FRAMES)
    return plan


def trace_command(args) -> int:
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = routes_of(args.exe.resolve())
    environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    summary = {'schema': 1, 'system': sys.platform, 'executable': args.exe.name, 'routes': {}}
    for name, (script, frames) in plan.items():
        with tempfile.TemporaryDirectory(dir=out) as scratch:
            game = Path(scratch) / args.exe.name
            shutil.copy2(args.exe, game)
            game.chmod(0o755)
            trace, state = Path(scratch) / 'trace.csv', Path(scratch) / 'state.json'
            command = [str(game), '--headless', '--limit-frames', str(frames), '--frame-trace', str(trace), '--dump-state', str(state)]
            if script:
                command += ['--input', script]
            done = subprocess.run(command, cwd=scratch, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  creationflags=NO_WINDOW, timeout=3600)
            if done.returncode or not trace.is_file():
                raise SystemExit(f'{name}: the game exited with {done.returncode}: {done.stdout[-400:]!r}')
            shutil.copy2(trace, out / f'{name}.csv')
            summary['routes'][name] = {'frames': frames, 'trace_sha256': sha256(trace), 'script_sha256': hashlib.sha256(script.encode()).hexdigest(),
                                       'state_sha256': hashlib.sha256(json.dumps(json.loads(state.read_text(encoding='utf-8')), sort_keys=True).encode()).hexdigest()}
            print(f'{name}: {frames} frames, trace {summary["routes"][name]["trace_sha256"][:16]}', flush=True)
    (out / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8', newline='\n')
    return 0


def first_difference(left: Path, right: Path) -> str:
    """Where two per-frame traces first differ: the frame and the columns, or the lengths when they agree as far as the shorter one."""
    rows_a, rows_b = (list(csv.DictReader(path.open(newline='', encoding='ascii'))) for path in (left, right))
    for one, two in zip(rows_a, rows_b):
        if one != two:
            return f'frame {one["frame"]}: ' + ', '.join(f'{key} ({one[key]} / {two[key]})' for key in one if one[key] != two[key])
    return f'the traces agree on {min(len(rows_a), len(rows_b))} frames but have {len(rows_a)} and {len(rows_b)} rows'


def compare_command(args) -> int:
    first, second = (json.loads((folder / 'summary.json').read_text(encoding='utf-8')) for folder in (args.a, args.b))
    status = 0
    print(f'A: {first["system"]} {first["executable"]}   B: {second["system"]} {second["executable"]}')
    for name in sorted(set(first['routes']) | set(second['routes'])):
        one, two = first['routes'].get(name), second['routes'].get(name)
        if not one or not two:
            print(f'{name}: on one side only, not compared')
            continue
        if one['script_sha256'] != two['script_sha256'] or one['frames'] != two['frames']:
            print(f'{name}: the input scripts or the lengths differ (not comparable)')
            status = 1
            continue
        same_trace = sha256(args.a / f'{name}.csv') == sha256(args.b / f'{name}.csv')
        same_state = one['state_sha256'] == two['state_sha256']
        print(f'{name}: {one["frames"]} frames: trace {"=" if same_trace else "!="}, final state {"=" if same_state else "!="}  '
              f'{"same" if same_trace and same_state else "DIFFERENT"}')
        if not same_trace:
            status = 1
            print('    first difference at ' + first_difference(args.a / f'{name}.csv', args.b / f'{name}.csv'))
        elif not same_state:
            status = 1
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    trace = sub.add_parser('trace', help='replay the routes of a conversion on its executable and keep the per-frame traces')
    trace.add_argument('exe', type=Path)
    trace.add_argument('--out', type=Path, required=True)
    trace.set_defaults(run=trace_command)
    compare = sub.add_parser('compare', help='compare two trace folders route by route')
    compare.add_argument('a', type=Path)
    compare.add_argument('b', type=Path)
    compare.set_defaults(run=compare_command)
    args = parser.parse_args()
    return args.run(args)


if __name__ == '__main__':
    raise SystemExit(main())
