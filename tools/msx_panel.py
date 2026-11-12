"""The MSX and MSX2 panel: the player's own cartridges converted through the real batch, read back from their reports.

    python -B tools/msx_panel.py --group NAME --system msx|msx2 [--level extended] [--jobs 3] [--run DIR]
                                 [--batch-option OPTION ...] ROM [ROM ...]

Each call converts one group (the cartridges that share a system and the batch's options: a video standard, the player's
own BIOS) with `RetroRecomp.py batch --keep-build`, into `<run>/Games` (default run: `.build/msx-panel/<date>`), with an
empty scratch library (`RETRO_RECOMP_LIBRARY_DIR=<run>/library`), the portable toolchain, no window and no sound device. The
ROMs are read in place: nothing is copied and their addresses are arguments, never in a tracked file. It then reads each
`conversion-report.json`, makes the contact sheets of every route (tools/msx_route_captures.py, on the delivered game) and
rewrites `<run>/panel.json` and `<run>/panel.md` from every group run so far. A stop kills the batch's whole process tree.

The record is numbers about runs: native and interpreted steps per route, the mapper, the BIOS, the start chosen, liveness,
the packed delivery and the state check. What a sheet shows (title, menu, in play) is for a person to read and write.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0


def batch(run: Path, system: str, level: str, jobs: int, options: list[str], roms: list[Path], covers: bool = False) -> int:
    env = dict(os.environ, RETRO_RECOMP_LIBRARY_DIR=str(run / 'library'), RETRO_RECOMP_TOOLCHAIN='llvm',
               SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYINSTALLER_SUPPRESS_SPLASH_SCREEN='1')
    (run / 'library').mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-B', str(ROOT / 'RetroRecomp.py'), 'batch', *map(str, roms), '--system', system,
               '--output', str(run / 'Games'), '--jobs', str(jobs), '--scan-level', level, '--keep-build',
               *([] if covers else ['--no-cover', '--no-online-cover']), '--no-shared-base', *options]
    with (run / f'batch-{system}.log').open('a', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        try:
            return process.wait()
        except KeyboardInterrupt:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/T', '/F', '/PID', str(process.pid)], capture_output=True)
            else:
                process.kill()
            raise


def reports(run: Path) -> list[Path]:
    return sorted((run / 'Games').glob('*/datas/reports/*/conversion-report.json'))


def record(path: Path) -> dict:
    report = json.loads(path.read_text(encoding='utf-8'))
    checks = report.get('msx_checks') or {}
    routes = []
    for row in report.get('final_checks') or []:
        live = row.get('liveness') or {}
        routes.append({'name': row['name'], 'frames': row['frames'], 'native_steps': row['native_steps'],
                       'interpreted_steps': row['interpreted_steps'], 'guarded_steps': row['guarded_steps'],
                       'reference_match': row['reference_match'], 'distinct_pictures': live.get('distinct_pictures'),
                       'last_picture_change_frame': live.get('last_picture_change_frame'),
                       'audible_frames': live.get('audible_frames'), 'script_sha256': row.get('script_sha256')})
    start = report.get('route_start') or {}
    states = (report.get('game_states') or {}).get('validation') or {}
    return {'report': str(path), 'file': report['rom']['file'], 'sha256': report['rom']['sha256'], 'bytes': report['rom']['bytes'],
            'system': report['system']['id'], 'level': report.get('scan_level'), 'mapper': checks.get('mapper'),
            'mapper_static_guess': (checks.get('mapper_probe') or {}).get('static_guess'),
            'bios': (checks.get('bios') or {}).get('kind'), 'standard': checks.get('standard'),
            'start': {'presses': start.get('presses'), 'confirm': start.get('confirm')}, 'routes': routes,
            'native_coverage': report.get('native_coverage'), 'delivered_file': report.get('delivered_file'),
            'states': {key: states.get(key) for key in ('fresh_process_match', 'saved_at', 'state_bytes')},
            'learning_passes_fallback_steps': checks.get('learning_passes_fallback_steps'),
            'phases_seconds': report.get('conversion_phases_seconds'), 'executable': report.get('build_executable')}


def table(records: list[dict]) -> str:
    lines = ['| Game | System | Mapper | BIOS | Start | Route | Native steps | Interpreted | Distinct pictures | Audible frames |',
             '|---|---|---|---|---|---|---|---|---|---|']
    for entry in records:
        start = f"{entry['start']['presses']}{'+' + entry['start']['confirm'] if entry['start']['confirm'] else ''}"
        for index, route in enumerate(entry['routes']):
            head = (f"{entry['file']} | {entry['system']} | {entry['mapper']} | {entry['bios']} | {start}" if index == 0 else
                    ' | | | | ')
            lines.append(f"| {head} | {route['name']} | {route['native_steps']:,} | {route['interpreted_steps']:,} | "
                         f"{route['distinct_pictures']} | {route['audible_frames']} |")
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('roms', type=Path, nargs='+')
    parser.add_argument('--group', required=True)
    parser.add_argument('--system', choices=('msx', 'msx2'), required=True)
    parser.add_argument('--level', default='extended', choices=('quick', 'standard', 'extended', 'thorough'))
    parser.add_argument('--jobs', type=int, default=3)
    parser.add_argument('--run', type=Path, default=ROOT / '.build' / 'msx-panel' / date.today().isoformat())
    parser.add_argument('--batch-option', action='append', default=[], help='one more batch option, e.g. --video-standard=pal')
    parser.add_argument('--covers', action='store_true', help="find covers as a player's conversion does (the panel has none)")
    args = parser.parse_args()
    run = args.run.resolve()
    run.mkdir(parents=True, exist_ok=True)
    code = batch(run, args.system, args.level, max(1, min(args.jobs, 4)), args.batch_option, args.roms, args.covers)
    print(f'{args.group}: batch exit {code}')
    records = [record(path) for path in reports(run)]
    for entry in records:
        game = Path(entry['executable'] or '')
        packed = game.with_name('packed-' + game.name)
        exe = packed if packed.is_file() else game
        if exe.is_file():
            subprocess.run([sys.executable, '-B', str(ROOT / 'tools' / 'msx_route_captures.py'), str(exe), entry['report'],
                            '--out', str(run / 'captures')], cwd=ROOT, creationflags=NO_WINDOW)
            entry['captures'] = str(run / 'captures' / entry['sha256'][:12])
    (run / 'panel.json').write_text(json.dumps(records, indent=2), encoding='utf-8', newline='\n')
    (run / 'panel.md').write_text(table(records), encoding='utf-8', newline='\n')
    print(table(records))
    return code


if __name__ == '__main__':
    sys.exit(main())
