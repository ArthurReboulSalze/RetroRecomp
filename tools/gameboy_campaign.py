"""A small campaign of chosen Game Boy games for the gates of liveness (G8) and route depth (G9).

Each game is converted by the converter at the extended level (one conversion at a time, from the library of the working tree) and the
delivered executable is then replayed on the reproducible pseudo-random route of the conversion for its whole length, with the per-frame
trace of the runtime (picture, sound, work RAM and program counter hashes) and six captures spread over the route. The captures are
put side by side on one sheet per game, which is looked at by a person; the numbers below are only a first filter and say nothing of
whether the game is played well.

    python tools/gameboy_campaign.py [--work FOLDER] [--only SLUG ...] [--reuse]

The ROMs are read in place from the player's folder (never copied into the repository); the sheets and the summary stay in the work
folder. Nothing here validates hardware fidelity or a complete game.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# slug -> (file name in the ROM folder, why this game)
GAMES = {
    'tetris': ('Tetris.zip', 'reference: ROM-only cartridge, waits for vertical blank in HALT'),
    'super_mario_land': ('Super Mario Land.zip', 'platformer, MBC1; an EI with an interrupt pending at boot'),
    'links_awakening': ("Legend of Zelda, The - Link's Awakening (USA, Europe).zip", 'MBC1 with battery RAM; STAT and window effects, large map'),
    'wario_land_ii': ('Wario Land II (USA, Europe).zip', 'MBC3 with battery RAM, 1 MiB; code run from RAM (CB prefix), guarded helpers'),
    'pokemon_red': ('Pokemon - Red Version.zip', 'MBC3 with battery RAM; menus and dialogue, a save'),
    'pokemon_yellow': ('Pokemon - Yellow Version - Special Pikachu Edition.zip', 'MBC5 with battery RAM; sampled sound'),
    'metroid_ii': ('Metroid II - Return of Samus.zip', 'MBC1 with battery RAM; scrolling and a large map'),
    'final_fantasy_legend_ii': ('Final Fantasy Legend II.zip', 'MBC1 with battery RAM; role-playing game driven by menus'),
    'mega_man_v': ('Mega Man V (USA).zip', 'MBC1, 512 KiB; dense sprites, so a longer pixel transfer'),
    'contra': ('Contra - The Alien Wars.zip', 'MBC1; the upstream issue 24 says Contra and Probotector do not start'),
    'exodus': ('Exodus - Journey to the Promised Land (Unl).zip', 'Wisdom Tree mapper (header says ROM only), added in 1.6.6'),
    'veediots': ('The Ren & Stimpy Show - Veediots!.zip', 'turns the screen off and waits (the frame rule of the LCD off)'),
}
ROM_FOLDER = Path(os.environ.get('RR_GB_ROMS', r'\\192.168.1.33\Batocera\roms\gb'))
CAPTURES = 6


def environment() -> dict:
    return dict(os.environ, PYTHONUTF8='1', SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYINSTALLER_SUPPRESS_SPLASH_SCREEN='1')


def extract(slug: str, work: Path) -> Path:
    archive = ROM_FOLDER / GAMES[slug][0]
    with zipfile.ZipFile(archive) as bundle:
        name = next(item for item in bundle.namelist() if item.lower().endswith('.gb'))
        target = work / 'roms' / f'{slug}.gb'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bundle.read(name))
    return target


def convert(rom: Path, out: Path) -> tuple[bool, float, str]:
    shutil.rmtree(out, ignore_errors=True)
    started = time.perf_counter()
    result = subprocess.run([sys.executable, '-B', str(ROOT / 'RetroRecomp.py'), 'convert', str(rom), '--system', 'gb', '--scan-level', 'extended',
                             '--no-online-cover', '--output', str(out)], env=environment(), capture_output=True, text=True, timeout=14400, cwd=ROOT)
    return result.returncode == 0, time.perf_counter() - started, (result.stdout + result.stderr)[-2500:]


def find_report(out: Path):
    reports = sorted(out.glob('**/datas/reports/*/conversion-report.json'))
    return reports[0] if reports else None


def route_of(report: dict):
    """The pseudo-random route of the conversion, rebuilt from the identity of the ROM (the report keeps only its name and size)."""
    from retrorecomp.random_routes import gameboy_script, long_routes
    routes = report.get('long_routes') or []
    if not routes:
        return None, ''
    built = long_routes('gb', report['rom']['sha256'], count=len(routes), frames=routes[0]['frames'], two_players=False)
    return built[0], gameboy_script(built[0])


def trace_metrics(path: Path) -> dict:
    rows = list(csv.DictReader(path.open(encoding='ascii')))
    pictures = [row['picture'] for row in rows]
    changes = [index + 1 for index in range(1, len(rows)) if pictures[index] != pictures[index - 1]]
    audible = [index + 1 for index, row in enumerate(rows) if int(row['nonzero_samples']) > 0]
    return {'frames': len(rows), 'distinct_pictures': len(set(pictures)), 'picture_changes': len(changes),
            'last_picture_change': changes[-1] if changes else None, 'audible_frames': len(audible),
            'last_audible_frame': audible[-1] if audible else None, 'distinct_ram': len({row['ram'] for row in rows}),
            'distinct_pc': len({row['pc'] for row in rows})}


def replay(executable: Path, script: str, frames: int, folder: Path) -> dict:
    """The delivered file on the route: trace, captures, final state."""
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    game = folder / executable.name
    shutil.copy2(executable, game)
    wanted = [max(1, frames * (index + 1) // CAPTURES - 20) for index in range(CAPTURES)]
    command = [str(game), '--headless', '--limit-frames', str(frames), '--frame-trace', str(folder / 'trace.csv'),
               '--dump-frames', ','.join(map(str, wanted)), '--screenshot-prefix', str(folder / 'shot'), '--dump-state', str(folder / 'state.json')]
    if script:
        command += ['--input', script]
    started = time.perf_counter()
    result = subprocess.run(command, cwd=folder, env=environment(), capture_output=True, text=True, timeout=7200)
    return {'exit': result.returncode, 'wall_seconds': round(time.perf_counter() - started, 1), 'captures_wanted': wanted,
            **(trace_metrics(folder / 'trace.csv') if (folder / 'trace.csv').is_file() else {})}


def sheet(folder: Path, name: str) -> Path | None:
    """The captures of a game on one sheet (three by two, doubled in size)."""
    from PIL import Image
    shots = sorted(folder.glob('shot*.ppm'))
    if not shots:
        return None
    images = [Image.open(path).convert('RGB') for path in shots]
    width, height = images[0].size
    cell = (width * 2, height * 2)
    columns = 3
    rows = (len(images) + columns - 1) // columns
    canvas = Image.new('RGB', (columns * (cell[0] + 6) + 6, rows * (cell[1] + 6) + 6), (40, 40, 40))
    for index, image in enumerate(images):
        canvas.paste(image.resize(cell, Image.NEAREST), (6 + (index % columns) * (cell[0] + 6), 6 + (index // columns) * (cell[1] + 6)))
    target = folder.parent / f'{name}-captures.png'
    canvas.save(target)
    return target


def summarise(report: dict) -> dict:
    checks = report.get('final_checks', [])
    validation = report.get('native_validation', {})
    return {'status': report.get('status'), 'scan_level': report.get('scan_level'),
            'cpu_validation': {'mode': validation.get('mode'), 'full_length': validation.get('full_length'),
                               'packed_reference_match': validation.get('packed_reference_match'),
                               'scenarios': [{'scenario': row['scenario'], 'frames': row['frames'], 'scenario_frames': row.get('scenario_frames'),
                                              'matched': 'Matched' in str(row.get('result'))} for row in validation.get('scenarios', [])]},
            'scenarios': [{'scenario': row['scenario'], 'frames': row['frames'], 'interpreter_cycles': row['interpreter_cycles'],
                           'ram_one_by_one_instructions': row['ram_stub_instructions'] + row['ram_single_step_instructions']
                           + row['highmem_stub_instructions'],
                           'guarded_helper_entries': sum(item['entries'] for item in row['guarded_helpers'].values()),
                           'liveness': row.get('liveness')} for row in checks],
            'states_verified': report.get('game_states', {}).get('fresh_process_verified'),
            'conversion_wall_seconds': report.get('conversion_wall_seconds')}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'gb-campaign')
    parser.add_argument('--only', action='append', choices=sorted(GAMES))
    parser.add_argument('--reuse', action='store_true', help='keep a conversion already done in the work folder')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    summary_path = work / 'summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.is_file() else {}
    for slug in args.only or list(GAMES):
        print(f'== {slug}: {GAMES[slug][1]}', flush=True)
        out = work / 'out' / slug
        row: dict = {'why': GAMES[slug][1]}
        report_path = find_report(out) if args.reuse else None
        if report_path is None:
            ok, seconds, tail = convert(extract(slug, work), out)
            row.update({'converted': ok, 'convert_wall_seconds': round(seconds, 1)})
            if not ok:
                row['failure_tail'] = tail
                summary[slug] = row
                summary_path.write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')
                print('  conversion FAILED', tail[-400:], flush=True)
                continue
            report_path = find_report(out)
        report = json.loads(report_path.read_text(encoding='utf-8'))
        row['converted'] = True
        row.update(summarise(report))
        route, script = route_of(report)
        executable = next((report_path.parents[3] / name for name in [report['executable']] if (report_path.parents[3] / name).is_file()), None)
        if route is not None and executable is not None:
            row['route'] = {'name': route.name, 'frames': route.frames}
            row['replay'] = replay(executable, script, route.frames, work / 'replay' / slug / 'run')
            image = sheet(work / 'replay' / slug / 'run', slug)
            row['sheet'] = str(image) if image else None
        summary[slug] = row
        summary_path.write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')
        print('  ' + json.dumps({key: row.get(key) for key in ('convert_wall_seconds', 'replay')}, default=str)[:400], flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
