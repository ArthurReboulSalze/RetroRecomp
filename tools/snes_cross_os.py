"""Super Nintendo: one game built on two systems, frame by frame (gate G13, the cross-OS witness).

    python tools/snes_cross_os.py trace EXE --out DIR
    python tools/snes_cross_os.py compare DIR_A DIR_B

`trace` reads the routes the conversion of EXE played from the report beside it (`datas/reports/*/conversion-report.json`: each final
scenario with its frames and, for a pseudo-random or authored route, how it was made), writes the input scripts again the same way
(`random_routes.write_route`) and runs the delivered executable on each route headless, from a private copy in an empty folder so
that no battery file of an earlier run is read. It keeps, in DIR, the per-frame trace of the runtime (`--trace`: picture, counters
and sound hashes of every frame), the hashes of the route's report (CPU, RAM, video memory, colour memory, sprite memory, sound
RAM, PCM, final PC and cycles) and a `summary.json` with their SHA-256. A chained route (one that continues from the saved end
state of the one before) is replayed the same way, in order, with the state its own system wrote. Run it once on Windows and once
on Debian, each on the game that system's converter built from the same source with an empty library; `compare` then says, route by
route, whether the two are identical and, if not, the first frame and the columns that differ. Only hashes and counters are kept:
no ROM byte and no picture.
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
# What a route's report says about the machine at its last frame, besides the frame count.
REPORT_HASHES = ('frame_hash', 'sequence_hash', 'cpu_hash', 'ram_hash', 'vram_hash', 'cram_hash', 'oam_hash', 'high_oam_hash',
                 'apu_ram_hash', 'cpu_pc', 'cpu_cycles', 'master_cycles', 'apu_cycles', 'pcm_hash', 'audio_fingerprint',
                 'pcm_samples', 'pcm_nonzero', 'sram_hash', 'coprocessor_state_hash')


def sha256(path: Path) -> str:
    """The SHA-256 of a text file as if it had Unix line ends: Windows writes the traces with CR LF."""
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def routes_of(executable: Path, scratch: Path) -> list[dict]:
    """The routes of the conversion that made `executable`, in the order it played them: name, frames, script, state files."""
    reports = sorted((executable.parent / 'datas' / 'reports').glob('*/conversion-report.json'))
    if not reports:
        raise SystemExit(f'no conversion report beside {executable}')
    loaded = [json.loads(path.read_text(encoding='utf-8')) for path in reports]
    report = next((item for item in loaded if Path(item.get('executable') or '').stem == executable.stem), None)
    if report is None:
        raise SystemExit(f'no conversion report beside {executable} names it as its executable (found {len(loaded)} for other executables)')
    from retrorecomp.random_routes import long_routes, write_route
    sha = report['rom']['sha256']
    chain = {check['scenario']: (check.get('input_route') or {}) for check in report['final_checks']}
    count = 1 + max([int(meta['index']) for meta in chain.values() if meta.get('generator') == 'random_routes.long_route'] or [-1])
    frames = next((meta['frames'] for meta in chain.values() if meta.get('generator') == 'random_routes.long_route'), 0)
    generated = {}
    if count:
        generated = {route.name: route for route in long_routes('snes', sha, count=count, frames=frames,
                                                                 chain=any(meta.get('continues_from') for meta in chain.values()))}
    from retrorecomp.snes_routes import authored_routes
    generated.update({route.name: route for route in authored_routes(sha)})
    plan = []
    for check in report['final_checks']:
        name = check['scenario']
        route = generated.get(name)
        if name not in ('demo', 'play') and route is None:
            raise SystemExit(f'{name}: this route cannot be written again from the report')
        plan.append({'name': name, 'frames': int(check['frames']), 'play': name != 'demo',
                     'script': write_route(route, scratch) if route is not None else None,
                     'continues_from': getattr(route, 'continues_from', None) if route is not None else None})
    continued = {item['continues_from'] for item in plan if item['continues_from']}
    for item in plan:
        item['save_state'] = item['name'] in continued
    return plan


def trace_command(args) -> int:
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    summary = {'schema': 1, 'system': sys.platform, 'executable': args.exe.name, 'routes': {}}
    with tempfile.TemporaryDirectory(dir=out) as folder:
        folder = Path(folder)
        plan = routes_of(args.exe.resolve(), folder)
        game = folder / args.exe.name
        shutil.copy2(args.exe, game)
        game.chmod(0o755)
        for item in plan:
            name = item['name']
            run = folder / name
            run.mkdir()
            trace, report = run / 'trace.csv', run / 'report.json'
            command = [str(game), '--frames', str(item['frames']), '--report', str(report), '--trace', str(trace)]
            if item['script']:
                command += ['--input-script', str(item['script'])]
            if item['play']:
                command.append('--play')
            if item['continues_from']:
                command += ['--load-state', str(folder / f"{item['continues_from']}.state")]
            if item['save_state']:
                command += ['--save-state', str(folder / f'{name}.state')]
            done = subprocess.run(command, cwd=run, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  creationflags=NO_WINDOW, timeout=7200)
            if done.returncode or not trace.is_file() or not report.is_file():
                raise SystemExit(f'{name}: the game exited with {done.returncode}: {done.stdout[-400:]!r}')
            data = json.loads(report.read_text(encoding='utf-8'))
            shutil.copy2(trace, out / f'{name}.csv')
            script_hash = sha256(Path(item['script'])) if item['script'] else ''
            summary['routes'][name] = {'frames': item['frames'], 'trace_sha256': sha256(trace), 'script_sha256': script_hash,
                                       'report': {key: data[key] for key in REPORT_HASHES if key in data}}
            print(f'{name}: {item["frames"]} frames, trace {summary["routes"][name]["trace_sha256"][:16]}', flush=True)
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
        differing = [key for key in sorted(set(one['report']) | set(two['report'])) if one['report'].get(key) != two['report'].get(key)]
        print(f'{name}: {one["frames"]} frames: trace {"=" if same_trace else "!="}, report hashes '
              f'{"=" if not differing else "!= (" + ", ".join(differing) + ")"}  {"same" if same_trace and not differing else "DIFFERENT"}')
        if not same_trace:
            status = 1
            print('    first difference at ' + first_difference(args.a / f'{name}.csv', args.b / f'{name}.csv'))
        elif differing:
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
