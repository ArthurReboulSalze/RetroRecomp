"""Master System and Game Gear: one game built on two systems, frame by frame (gate G13, the cross-OS witness).

    python tools/sega_cross_os.py trace EXE --out DIR
    python tools/sega_cross_os.py compare DIR_A DIR_B

`trace` reads the routes the conversion of EXE played from the report beside it (`datas/reports/*/conversion-report.json`: each final
scenario with its frames and its scripted input) and runs the delivered executable on each, headless, from a private copy and an empty
folder, keeping in DIR the per-frame trace of the runtime (`--vdp-trace`: picture, sound, RAM and VDP hashes), the RAM at the last
frame (`--dump-frame`), the final CPU registers the log prints (banked engine) and a `summary.json` with their SHA-256. Run it once on
Windows and once on Debian, each on the game that system's converter built from the same commit with an empty library; `compare` then
says, route by route, whether the two are identical and, if not, the first frame and the columns that differ. Only hashes and counters
are kept: no ROM byte and no picture. The `sp` column (the stack pointer of the generated code, which the interpreter does not keep) is
part of the trace like the others, since both sides run the same engine.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0


def sha256(path: Path, text: bool = False) -> str:
    """The SHA-256 of a file; a text file is read as if it had Unix line ends (Windows writes the traces with CR LF)."""
    data = Path(path).read_bytes()
    return hashlib.sha256(data.replace(b'\r\n', b'\n') if text else data).hexdigest()


def routes_of(executable: Path) -> tuple[dict, dict]:
    """The report of the conversion that made `executable` and its routes: name -> (list of --press values, frames)."""
    reports = sorted((executable.parent / 'datas' / 'reports').glob('*/conversion-report.json'))
    loaded = [json.loads(path.read_text(encoding='utf-8')) for path in reports]
    report = next((item for item in loaded if Path(item.get('executable') or '').stem == executable.stem), None)   # 'game.exe' or 'game' on Linux
    if report is None:
        raise SystemExit(f'no conversion report beside {executable} names it as its executable (found {len(loaded)})')
    plan = {check['scenario']: (list(check.get('scripted_input') or []), int(check['requested_frames'])) for check in report['final_checks']}
    return report, plan


def trace_command(args) -> int:
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    report, plan = routes_of(args.exe.resolve())
    environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    summary = {'schema': 1, 'system': sys.platform, 'executable': args.exe.name, 'rom_sha256': report['rom']['sha256'],
               'backend': report.get('backend'), 'engine_revision': report.get('engine_revision'), 'routes': {}}
    for name, (presses, frames) in plan.items():
        with tempfile.TemporaryDirectory(dir=out) as scratch:
            folder = Path(scratch)
            game = folder / args.exe.name
            shutil.copy2(args.exe, game)
            game.chmod(0o755)
            command = [str(game), '--headless', '--frames', str(frames), '--log', str(folder / 'run.log'),
                       '--vdp-trace', str(folder / 'vdp.csv'), '--dump-frame', str(frames), '--dump-out', str(folder / 'frame.png')]
            for value in presses:
                command += ['--press', value]
            code = subprocess.run(command, cwd=folder, env=environment, capture_output=True, timeout=3600, creationflags=NO_WINDOW).returncode
            log = (folder / 'run.log').read_text(encoding='utf-8', errors='replace') if (folder / 'run.log').is_file() else ''
            cpu = re.search(r'\[cpu\] (\{[^\n]+\})', log)
            row = {'frames': frames, 'presses': len(presses), 'exit': code}
            if (folder / 'vdp.csv').is_file():
                shutil.copy2(folder / 'vdp.csv', out / f'{name}.csv')
                row['trace_sha256'] = sha256(folder / 'vdp.csv', text=True)
                row['trace_rows'] = sum(1 for _ in (folder / 'vdp.csv').open(encoding='utf-8')) - 1
            if (folder / 'frame.png.ram').is_file():
                row['final_ram_sha256'] = sha256(folder / 'frame.png.ram')
            if cpu:
                row['final_cpu'] = json.loads(cpu[1])
            summary['routes'][name] = row
    (out / 'summary.json').write_text(json.dumps(summary, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({name: {key: row.get(key) for key in ('frames', 'exit', 'trace_rows')} for name, row in summary['routes'].items()}))
    return 0 if all(row['exit'] == 0 for row in summary['routes'].values()) else 1


def first_difference(path_a: Path, path_b: Path) -> dict:
    with path_a.open(newline='', encoding='utf-8') as a, path_b.open(newline='', encoding='utf-8') as b:
        rows_a, rows_b = list(csv.DictReader(a)), list(csv.DictReader(b))
    for index, (x, y) in enumerate(zip(rows_a, rows_b)):
        columns = [key for key in x if x[key] != y.get(key)]
        if columns:
            return {'frame': index + 1, 'columns': columns}
    return {'frame': None, 'columns': [], 'lengths': [len(rows_a), len(rows_b)]}


def compare_command(args) -> int:
    first = json.loads((args.a / 'summary.json').read_text(encoding='utf-8'))
    second = json.loads((args.b / 'summary.json').read_text(encoding='utf-8'))
    ok = first['rom_sha256'] == second['rom_sha256'] and set(first['routes']) == set(second['routes'])
    if not ok:
        print('not the same game or not the same routes')
        return 1
    identical = True
    for name in first['routes']:
        a, b = first['routes'][name], second['routes'][name]
        same_trace = a.get('trace_sha256') == b.get('trace_sha256') and a.get('trace_sha256') is not None
        same_ram = a.get('final_ram_sha256') == b.get('final_ram_sha256') and a.get('final_ram_sha256') is not None
        same_cpu = a.get('final_cpu') == b.get('final_cpu')
        line = f'{name}: {a["frames"]} frames, trace {"equal" if same_trace else "DIFFERENT"}, final RAM {"equal" if same_ram else "DIFFERENT"}, final CPU {"equal" if same_cpu else "DIFFERENT"}'
        if not same_trace and (args.a / f'{name}.csv').is_file() and (args.b / f'{name}.csv').is_file():
            line += ' ' + json.dumps(first_difference(args.a / f'{name}.csv', args.b / f'{name}.csv'))
        print(line)
        identical = identical and same_trace and same_ram and same_cpu and a['exit'] == 0 and b['exit'] == 0
    print('IDENTICAL' if identical else 'DIFFERENT')
    return 0 if identical else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    trace = sub.add_parser('trace')
    trace.add_argument('exe', type=Path)
    trace.add_argument('--out', type=Path, required=True)
    trace.set_defaults(handler=trace_command)
    compare = sub.add_parser('compare')
    compare.add_argument('a', type=Path)
    compare.add_argument('b', type=Path)
    compare.set_defaults(handler=compare_command)
    args = parser.parse_args()
    return args.handler(args)


if __name__ == '__main__':
    raise SystemExit(main())
