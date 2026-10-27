"""Release check for Capcom CPS-1 conversions at the Standard level (developer tool).

Release 1.5.2 shipped a converter whose Standard batch stopped every CPS-1 game
before it started (a KeyError in the shared-knowledge lookup); the release
checks only converted at the quick level, which skips that lookup. This tool
converts the given CPS-1 romsets with the converter about to be published,
through the same ``batch`` command line as a player, and checks the receipts:

    python tools/cps1_release_check.py CONVERTER ROM.zip [ROM.zip ...]
        [--work DIR] [--level standard] [--max-fallback 0]

CONVERTER is the frozen ``Retro-Recomp.exe`` (copied into DIR/app, which then
holds its own workspace: the first run fetches the pinned sources and tools,
later runs reuse them) or a source checkout's ``RetroRecomp.py``. Games go to
DIR/Games, the result to DIR/cps1-release-check.json. Exit status 0 only when
every romset converts at the requested level with native/reference agreement,
the packed executable comparison, the fresh-process F8/F9 check and at most
--max-fallback interpreted 68000 and Z80 opcodes. ROM folders are only read.
Conversions are heavy: run this on the Windows build PC.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def command_for(converter: Path, app: Path) -> list[str]:
    if converter.suffix.lower() == '.py':
        return [sys.executable, str(converter)]
    app.mkdir(parents=True, exist_ok=True)
    target = app / converter.name
    shutil.copy2(converter, target)
    return [str(target)]


def report_problems(report: dict, level: str, max_fallback: int) -> list[str]:
    """What a CPS-1 conversion report lacks for the release check."""
    problems = []
    system = (report.get('system') or {}).get('id')
    if system != 'cps1':
        problems.append(f"system is {system!r}, not 'cps1'")
    if report.get('scan_level') != level:
        problems.append(f"scan level is {report.get('scan_level')!r}, not {level!r}")
    validation = report.get('native_validation') or {}
    if not validation.get('passed'):
        problems.append('native validation did not pass')
    if not validation.get('packed_reference_match'):
        problems.append('the packed executable was not compared with the reference')
    checks = report.get('final_checks') or []
    if not checks:
        problems.append('no final checks')
    for check in checks:
        name = check.get('name', '?')
        if not check.get('reference_match'):
            problems.append(f'{name}: native and reference differ')
        interpreted = int(check.get('interpreted_opcodes', 0)) + int(check.get('audio_interpreted_opcodes', 0))
        if interpreted > max_fallback:
            problems.append(f'{name}: {interpreted:,} interpreted 68000/Z80 opcodes (limit {max_fallback:,})')
    state = ((report.get('game_states') or {}).get('validation')) or {}
    if not state.get('fresh_process_match'):
        problems.append('F8/F9 did not continue identically in a fresh process')
    if not state.get('truncated_state_rejected'):
        problems.append('a damaged quick state was not rejected')
    return problems


def batch_problems(record: dict, requested: int) -> list[str]:
    problems = []
    if record.get('succeeded') != requested or record.get('failed'):
        problems.append(f"batch: {record.get('succeeded')} of {requested} succeeded, {record.get('failed')} failed")
    for game in record.get('games', []):
        if game.get('status') != 'success':
            problems.append(f"{game.get('rom')}: {game.get('status')} {game.get('error', '')}".rstrip())
        elif game.get('system') != 'cps1':
            problems.append(f"{game.get('rom')}: detected as {game.get('system')!r}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('converter', type=Path)
    parser.add_argument('roms', type=Path, nargs='+')
    parser.add_argument('--work', type=Path, default=ROOT / '.build/cps1-release-check')
    parser.add_argument('--level', choices=('quick', 'standard', 'extended', 'thorough'), default='standard')
    parser.add_argument('--max-fallback', type=int, default=0)
    args = parser.parse_args(argv)

    work = args.work.resolve()
    games = work / 'Games'
    command = command_for(args.converter.resolve(), work / 'app')
    command += ['batch', *map(str, args.roms), '--system', 'cps1', '--scan-level', args.level,
                '--jobs', '1', '--force', '--no-online-cover', '--output', str(games)]
    work.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with (work / 'batch.log').open('w', encoding='utf-8') as log:
        completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                   env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    elapsed = round(time.perf_counter() - started, 1)

    problems = [] if completed.returncode == 0 else [f'converter exit status {completed.returncode}']
    record_path = games / 'datas' / 'Retro-Recomp-batch.json'
    games_checked = []
    if not record_path.is_file():
        problems.append(f'no batch record at {record_path}')
    else:
        record = json.loads(record_path.read_text(encoding='utf-8'))
        problems += batch_problems(record, len(args.roms))
        for game in record.get('games', []):
            report_path = Path(game['report']) if game.get('report') else None
            if game.get('status') != 'success' or not report_path or not report_path.is_file():
                continue
            found = report_problems(json.loads(report_path.read_text(encoding='utf-8')),
                                    args.level, args.max_fallback)
            problems += [f"{game.get('title')}: {problem}" for problem in found]
            games_checked.append({'title': game.get('title'), 'report': str(report_path), 'problems': found})
    result = {'converter': str(args.converter), 'level': args.level, 'roms': list(map(str, args.roms)),
              'seconds': elapsed, 'games': games_checked, 'problems': problems, 'passed': not problems}
    (work / 'cps1-release-check.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    for problem in problems:
        print('FAIL', problem)
    print(('PASS' if not problems else 'FAIL') + f': {len(games_checked)} CPS-1 game(s), {args.level}, {elapsed} s')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
