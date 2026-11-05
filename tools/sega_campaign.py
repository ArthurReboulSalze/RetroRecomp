"""A small campaign of chosen Master System and Game Gear games for the gates of liveness (G8) and route depth (G9).

Each game is converted by the converter at the extended level (two conversions at a time, banked engine, from an empty private library)
and the delivered executable is then replayed on its three routes (demo, play and the reproducible pseudo-random route of 18,000
frames) with the per-frame trace of the runtime (picture, sound, RAM) and captures spread over the play and the pseudo-random routes.
The captures are put side by side on one sheet per game, which is looked at by a person; the numbers are only a first filter and say
nothing of whether the game is played well.

    python tools/sega_campaign.py [--work FOLDER] [--roms FOLDER] [--only SLUG ...] [--reuse]

The ROMs are read in place from the player's folder (never copied); the sheets and the summary stay in the work folder. Nothing here
validates hardware fidelity or a complete game.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# slug -> (console, file in the console's folder of the ROM root, why this game)
GAMES = {
    'alex_kidd_miracle_world': ('sms', 'Alex Kidd in Miracle World (USA, Europe).sms', 'regression baseline of every release; Sega mapper, action platformer'),
    'operation_wolf': ('sms', 'Operation Wolf (Europe).sms', 'Light Phaser catalogue (the pad routes do not drive the gun); a Europe label, so PAL timing'),
    'phantasy_star': ('sms', 'Phantasy Star (USA, Europe).sms', 'battery cartridge RAM (not modelled); a role-playing game driven by menus, so route depth is the question'),
    'micro_machines': ('sms', 'Micro Machines (Europe).sms', 'Codemasters header: the report names a mapper the runtime does not model; PAL'),
    'sonic_the_hedgehog_sms': ('sms', 'Sonic The Hedgehog (USA, Europe).sms', 'line interrupts and palette changes mid-frame (water), fast scrolling'),
    'space_harrier': ('sms', 'Space Harrier (USA, Europe).sms', 'many sprites per line (scaled objects): the sprite limit and its flags'),
    'sonic_the_hedgehog_gg': ('gg', 'Sonic The Hedgehog (World).zip', 'Game Gear baseline: 160 x 144 window of the 256 x 192 picture, stereo ports'),
    'factory_panic': ('gg', 'Factory Panic (Europe).zip', 'compilation-library reference; its interrupt loop caught two defects of the functions engine'),
    'streets_of_rage': ('gg', 'Streets of Rage (World).zip', 'beat-em-up with horizontal scrolling and many sprites on a small window'),
    'gunstar_heroes': ('gg', 'Gunstar Heroes (Japan).zip', 'dense sprites and fast action in a Japanese-region cartridge'),
    'shining_force_ii': ('gg', 'Shining Force II - The Sword of Hajya (USA, Europe).zip', 'battery cartridge RAM (not modelled); menu-driven tactics game'),
    'sonic_spinball_gg': ('gg', 'Sonic Spinball (USA, Europe).zip', 'the Game Gear game that exposed a general defect of the functions engine (a RET to another address)'),
}
ROM_ROOT = Path('//192.168.1.33/Batocera/roms')
FOLDERS = {'sms': 'mastersystem', 'gg': 'gamegear'}
SHOTS = 4                    # captures per sheet row; two rows (the play route and the pseudo-random route)


def environment(library: Path) -> dict:
    return dict(os.environ, PYTHONUTF8='1', SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYINSTALLER_SUPPRESS_SPLASH_SCREEN='1',
                RETRO_RECOMP_LIBRARY_DIR=str(library))


def convert(slugs: list, roms: Path, out: Path, library: Path, jobs: int, backend: str) -> tuple[int, float, str]:
    """One batch of all the chosen games: `jobs` conversions at a time, extended level, empty library, no network."""
    command = [sys.executable, '-B', str(ROOT / 'RetroRecomp.py'), 'batch', '--scan-level', 'extended', '--no-online-cover', '--no-shared-base',
               '--keep-build', '--jobs', str(jobs), '--backend', backend, '--output', str(out)]
    command += [str(roms / FOLDERS[GAMES[slug][0]] / GAMES[slug][1]) for slug in slugs]
    started = time.perf_counter()
    result = subprocess.run(command, env=environment(library), capture_output=True, text=True, timeout=4 * 3600, cwd=ROOT)
    return result.returncode, time.perf_counter() - started, (result.stdout + result.stderr)[-3000:]


def reports(out: Path) -> dict:
    """The reports of the batch by the stem of the ROM name (a ZIP holds a file of the same stem)."""
    found = {}
    for path in sorted(out.glob('**/datas/reports/*/conversion-report.json')):
        report = json.loads(path.read_text(encoding='utf-8'))
        found[Path(report['rom']['name']).stem] = (path, report)
    return found


def run(executable: Path, folder: Path, frames: int, press: list, *, capture: int | None = None, trace: bool = False) -> int:
    """The delivered file on a route, as far as `frames`, with the per-frame trace or one capture of its last picture."""
    folder.mkdir(parents=True, exist_ok=True)
    command = [str(executable), '--headless', '--frames', str(frames), '--log', str(folder / 'run.log')]
    if trace:
        command += ['--vdp-trace', str(folder / 'vdp.csv')]
    if capture:
        command += ['--dump-frame', str(capture), '--dump-out', str(folder / f'shot-{capture:05d}.png')]
    for value in press:
        command += ['--press', value]
    return subprocess.run(command, cwd=folder, env=environment(folder / 'library'), capture_output=True, timeout=1800).returncode


def sheet(shots: list, target: Path) -> Path | None:
    """The captures on one sheet: one row per route (the play route above, the pseudo-random route below), doubled in size."""
    from PIL import Image
    rows = [[Image.open(path).convert('RGB') for path in row if path.is_file()] for row in shots]
    rows = [row for row in rows if row]
    if not rows:
        return None
    width, height = rows[0][0].size
    cell = (width * 2, height * 2)
    canvas = Image.new('RGB', (SHOTS * (cell[0] + 6) + 6, len(rows) * (cell[1] + 6) + 6), (40, 40, 40))
    for y, row in enumerate(rows):
        for x, image in enumerate(row):
            canvas.paste(image.resize(cell, Image.NEAREST), (6 + x * (cell[0] + 6), 6 + y * (cell[1] + 6)))
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target)
    return target


def replay(slug: str, report_path: Path, report: dict, work: Path) -> dict:
    """The delivered file on every final route of the conversion: liveness numbers, and the sheet of captures."""
    from retrorecomp.sega_evidence import route_liveness
    # The banked engine stores the folder it published to; the "functions" engine does not: the console folder of the export is the
    # fourth parent of the report (<console>/datas/reports/<game>/conversion-report.json).
    executable = Path(report.get('published_directory') or report_path.parents[3]) / report['executable']
    result = {'executable': str(executable), 'routes': {}}
    folder = work / 'replay' / slug
    shot_rows = []
    for check in report['final_checks']:
        name, frames, press = check['scenario'], check['requested_frames'], check.get('scripted_input') or []
        started = time.perf_counter()
        code = run(executable, folder / name, frames, press, trace=True)
        row = {'frames': frames, 'exit': code, 'wall_seconds': round(time.perf_counter() - started, 1), 'presses': len(press)}
        if (folder / name / 'vdp.csv').is_file():
            row['liveness'] = route_liveness(folder / name / 'vdp.csv')
        result['routes'][name] = row
        if name in ('play', next((c['scenario'] for c in report['final_checks'] if c['scenario'] not in ('demo', 'play')), None)):
            wanted = [max(1, frames * (index + 1) // SHOTS - 10) for index in range(SHOTS)]
            for frame in wanted:
                run(executable, folder / f'{name}-shots', frame, press, capture=frame)
            shot_rows.append([folder / f'{name}-shots' / f'shot-{frame:05d}.png' for frame in wanted])
    image = sheet(shot_rows, work / 'sheets' / f'{slug}.png') if shot_rows else None
    result['sheet'] = str(image) if image else None
    return result


def summarise(report: dict) -> dict:
    return {'backend': report.get('backend'), 'scan_level': report.get('scan_level'), 'video': report.get('video_model', {}).get('standard'),
            'mapper': next((d['id'] for d in report.get('hardware_devices') or () if d['kind'] == 'cartridge_mapper'), None),
            'native_validation_passed': (report.get('native_validation') or {}).get('passed'),
            'packed_reference_match': (report.get('native_validation') or {}).get('packed_reference_match'),
            'packed_replay': report.get('packed_replay'), 'reference_vdp_trace_match': report.get('reference_vdp_trace_match'),
            'states': (report.get('game_states') or {}).get('supported'),
            'scenarios': [{'scenario': c['scenario'], 'frames': c['requested_frames'], 'interpreter_cycles': c.get('interpreter_cycles'),
                           'interpreter_percent': c.get('interpreter_percent'), 'native_instructions': c.get('native_instructions'),
                           'dispatch_misses': c.get('dispatch_misses')} for c in report['final_checks']],
            'conversion_wall_seconds': report.get('conversion_wall_seconds')}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--roms', type=Path, default=ROM_ROOT, help='the ROM root with one folder per console (mastersystem, gamegear)')
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'sega-campaign')
    parser.add_argument('--only', action='append', choices=sorted(GAMES))
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--backend', choices=('banked', 'functions'), default='banked')
    parser.add_argument('--reuse', action='store_true', help='keep the conversions already done in the work folder')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    slugs = args.only or list(GAMES)
    out = work / 'out'
    summary_path = work / 'summary.json'
    summary = {'games': {}}
    if not args.reuse or not reports(out):
        code, seconds, tail = convert(slugs, args.roms, out, work / 'library', args.jobs, args.backend)
        summary['batch'] = {'exit': code, 'wall_seconds': round(seconds, 1)}
        if code:
            summary['batch']['tail'] = tail
    found = reports(out)
    for slug in slugs:
        console, name, why = GAMES[slug]
        row = {'console': console, 'why': why}
        if Path(name).stem not in found:
            row['converted'] = False
        else:
            path, report = found[Path(name).stem]
            row.update(converted=True, report=str(path), **summarise(report))
            published = Path(report.get('published_directory') or path.parents[3]) / report['executable']
            if published.is_file():
                row['replay'] = replay(slug, path, report, work)
            else:
                # The "functions" engine refuses an export that differs from the interpreter: the report stays, the game does not.
                row['refused'] = {'reference_vdp_trace_match': report.get('reference_vdp_trace_match'),
                                  'first_mismatched_frames': (report.get('reference_vdp_mismatched_frames') or [])[:3]}
        summary['games'][slug] = row
        print(f'== {slug}: ' + json.dumps({key: row.get(key) for key in ('converted', 'mapper', 'video')}), flush=True)
    summary_path.write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
