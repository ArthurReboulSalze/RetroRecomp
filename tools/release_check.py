"""Console-independent release check for Retro-Recomp conversions (developer tool).

Converts the given romsets with the converter about to be published, through the
same ``batch`` command line as a player, and checks the receipts:

    python tools/release_check.py CONVERTER ROM.zip [ROM.zip ...]
        [--console ID] [--work DIR] [--level standard] [--max-fallback 0]
        [--max-device N] [--require-packed] [--require-states]
        [--jobs N] [--app DIR] [--batch-args "..."]

CONVERTER is the frozen ``Retro-Recomp.exe`` (copied into DIR/app, which then
holds its own workspace: the first run fetches the pinned sources and tools,
later runs reuse them) or a source checkout's ``RetroRecomp.py``. Games go to
DIR/Games, the result to DIR/release-check.json. The console comes from the
converter's own detection (the ``batch`` command line's ``--system auto``) or
from --console. The consoles, their report writers and their CPUs come from the
profiles (``retrorecomp/systems``) and every report is read through
``retrorecomp.report_schema.read_report``, whatever its writer; a report that is
not of the shape the profile's writer produces is reported, never guessed. Per game, the tool checks what a report can prove today: the
conversion level, native/reference agreement on every final scenario, the
interpreted main-CPU and audio-CPU counts against --max-fallback, cartridge
device instructions against --max-device (only when given), and the packed
executable comparison plus the fresh-process F8/F9 check when the report
carries them. Exit status 0 only when every required gate passes. ROM folders
are only read. Conversions are heavy: run this on the Windows build PC.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from retrorecomp.report_schema import ReportShapeError, read_report  # noqa: E402
from retrorecomp.systems import ALL_PROFILES  # noqa: E402

CONSOLES = tuple(profile.id for profile in ALL_PROFILES)
LEVELS = ('quick', 'standard', 'extended', 'thorough')


def command_for(converter: Path, app: Path) -> list[str]:
    if converter.suffix.lower() == '.py':
        return [sys.executable, str(converter)]
    app.mkdir(parents=True, exist_ok=True)
    target = app / converter.name
    shutil.copy2(converter, target)
    return [str(target)]


def batch_problems(record: dict, requested: int, expected_system: str | None = None) -> list[str]:
    """What the batch record itself proves, before the reports are read."""
    problems = []
    if record.get('succeeded') != requested or record.get('failed'):
        problems.append(f"batch: {record.get('succeeded')} of {requested} succeeded, {record.get('failed')} failed")
    for game in record.get('games', []):
        if game.get('status') != 'success':
            problems.append(f"{game.get('rom')}: {game.get('status')} {game.get('error', '')}".rstrip())
        elif expected_system and game.get('system') != expected_system:
            problems.append(f"{game.get('rom')}: detected as {game.get('system')!r}")
    return problems


# Report writers whose CPU differential runs once, on a short boot, not on every final scenario (Game Boy).
COMPARES_ONCE = ('gameboy',)


# The wording the messages of three writers have always used for their opcode counts (tests pin it). A writer
# that is not listed is named from the profile's ``fallback_display``.
UNIT_WORDING = {'console16': 'main/audio CPU opcodes', 'neogeo_conversion': '68000/Z80 opcodes',
                'cps1_conversion': '68000/Z80 opcodes'}


def _unit_label(profile) -> str:
    """How a fallback count is named in a message."""
    if profile.report_shape.writer in UNIT_WORDING:
        return UNIT_WORDING[profile.report_shape.writer]
    return {'cycles': 'CPU cycles', 'opcodes': 'opcodes'}.get(profile.fallback_display, profile.fallback_display)


def _fresh_process(states: dict) -> bool | None:
    """Whether F8/F9 continued identically in a fresh process, as the report states it (None when it does not)."""
    validation = states.get('validation') if isinstance(states.get('validation'), dict) else {}
    fresh = validation.get('fresh_process_match')
    routes = validation.get('routes')
    # Neo Geo writes one row per route.
    if fresh is None and isinstance(routes, list) and routes:
        matches = [route.get('fresh_process_match') if isinstance(route, dict) else None for route in routes]
        fresh = all(match is True for match in matches)
    return fresh if fresh is not None else states.get('fresh_process_verified')


def read_gate_data(report: dict, profile) -> dict | None:
    """What the gates need from one conversion report of ``profile``'s machine, read through report_schema.

    The one reader of every console: ``read_report`` turns the report of any writer into the schema-2 document
    and this function takes the counts and verdicts the gates compare from it. None when the report is not of
    the shape the profile's writer produces, or lacks a figure a gate needs: it is reported, never guessed.
    """
    if profile.report_shape is None:
        return None
    try:
        document = read_report(report, lenient=True)
    except ReportShapeError:
        return None
    if document['read_from']['writer'] != profile.report_shape.writer:
        return None
    main = next((cpu for cpu in document['cpus'] if cpu['role'] == 'main'), None)
    audio = next((cpu for cpu in document['cpus'] if cpu['role'] == 'audio'), None)
    if main is None:
        return None
    # A CPU is counted in one unit: instructions, or cycles when its writer only counted those.
    cycles = main['original_unit'] == 'cycles'
    fidelity = document['validation']['cpu_fidelity']
    compared = {row['name']: row for row in fidelity['scenarios']}
    sound = any(cpu.role == 'sound' for cpu in profile.cpus)
    once = document['read_from']['writer'] in COMPARES_ONCE
    scenarios, agreement_problems = [], []
    for index, row in enumerate(main['scenarios']):
        figure = (row['cycles'] or {}).get('interpreted') if cycles else row['interpreted']
        name = row['name'] or ('main' if index == 0 else None)
        if figure is None or not name:
            return None
        audio_row = audio['scenarios'][index] if audio and index < len(audio['scenarios']) else None
        scenarios.append({'name': name, 'main_interpreted': int(figure),
                          'audio_interpreted': int((audio_row or {}).get('interpreted') or 0) if sound else None})
        if once:
            continue
        verdict = compared.get(row['name'])
        if verdict is None:
            agreement_problems.append(f"{name}: no native/reference comparison in the report")
        elif verdict['match'] is not True:
            agreement_problems.append(f"{name}: native and reference differ")
    if once:
        rows = fidelity['scenarios']
        if not any(row['match'] is True for row in rows):
            agreement_problems.append('no native/reference CPU comparison in the report')
        agreement_problems += [f"{row['name']}: native and reference differ" for row in rows if row['match'] is False]
    if not scenarios:
        agreement_problems.append('no final checks')
    if fidelity['passed'] is not True:
        agreement_problems.append('native validation did not pass')
    device = document['devices'][0] if document['devices'] else None
    replay = (document['packed'] or {}).get('replay')
    states = document['states'] or {}
    validation = states.get('validation') if isinstance(states.get('validation'), dict) else {}
    damaged = validation.get('truncated_state_rejected')
    rejected = validation.get('invalid_states_rejected')
    if damaged is None and isinstance(rejected, int):
        damaged = rejected > 0
    flags = {}
    if validation or states.get('fresh_process_verified') is not None:
        flags = {'fresh_process': _fresh_process(states)}
        if damaged is not None:
            flags['damaged_refused'] = damaged
    return {'shape': document['read_from']['writer'], 'unit': _unit_label(profile), 'level': document['scan']['level'],
            'scenarios': scenarios, 'agreement': not agreement_problems, 'agreement_problems': agreement_problems,
            'packed': replay['match'] if replay else None, 'states': flags,
            'device': _device_totals(device)}


def _reader(profile):
    return lambda report: read_gate_data(report, profile)


READERS = {profile.id: _reader(profile) for profile in ALL_PROFILES}


def _device_totals(device) -> dict | None:
    """Cartridge-device instructions, kept apart from the CPUs' counts."""
    if not device:
        return None
    rows = [row for row in device['scenarios'] if isinstance(row.get('interpreted'), int)]
    return {'chip': device['id'], 'total_instructions': sum(row['interpreted'] for row in rows),
            'failed': bool(device['failed'])}


def _states_gate(flags: dict) -> tuple[str, list[str]]:
    """Fresh-process F8/F9 evidence, with each reported flag on its own."""
    problems = []
    fresh, damaged = flags.get('fresh_process'), flags.get('damaged_refused')
    if fresh is False:
        problems.append('F8/F9 did not continue identically in a fresh process')
    if damaged is False:
        problems.append('a damaged quick state was not rejected')
    if problems:
        return 'fail', problems
    if fresh is None and damaged is None:
        return 'absent', []
    return 'pass', []


def check_report(report: dict, console: str | None, level: str, max_fallback: int, max_device: int | None = None,
                 require_packed: bool = False, require_states: bool = False) -> dict:
    """Gates, counts and problem strings proven by one conversion report."""
    gates = {name: {'status': 'absent', 'problems': []}
             for name in ('conversion', 'native_reference', 'fallback', 'device', 'packed', 'states')}
    found = (report.get('system') or {}).get('id') if isinstance(report.get('system'), dict) else None
    reader = READERS.get(console or '') if console else None
    if reader is None:
        return {'shape': None, 'gates': gates, 'counts': {}, 'problems': ['unknown console']}
    data = reader(report)
    problems = []
    if found != console:
        problems.append(f"system is {found!r}, not {console!r}")
    if data is None:
        problems.append('unknown report shape')
        return {'shape': None, 'gates': gates, 'counts': {}, 'problems': problems}
    counts = {'fallback_limit': max_fallback,
              'scenarios': [{'name': scenario['name'], 'main_interpreted': scenario['main_interpreted'],
                             'audio_interpreted': scenario['audio_interpreted']} for scenario in data['scenarios']],
              'device': data['device'], 'device_limit': max_device,
              'packed_match': data['packed'], 'states': data['states']}
    if data['level'] is None:
        gates['conversion'] = {'status': 'fail', 'problems': ['the report does not state its scan level']}
    elif data['level'] != level:
        gates['conversion'] = {'status': 'fail',
                               'problems': [f"scan level is {data['level']!r}, not {level!r}"]}
    else:
        gates['conversion'] = {'status': 'pass', 'problems': []}
    gates['native_reference'] = {'status': 'pass' if data['agreement'] else 'fail',
                                 'problems': data['agreement_problems']}
    fallback_problems = []
    for scenario in data['scenarios']:
        total = scenario['main_interpreted'] + (scenario['audio_interpreted'] or 0)
        if total > max_fallback:
            fallback_problems.append(f"{scenario['name']}: {total:,} interpreted {data['unit']} "
                                     f"(limit {max_fallback:,})")
    gates['fallback'] = {'status': 'fail' if fallback_problems else 'pass', 'problems': fallback_problems}
    device = data['device']
    if device is None:
        gates['device'] = {'status': 'absent', 'problems': []}
    elif device['failed']:
        gates['device'] = {'status': 'fail', 'problems': ['the cartridge device reported a failed command']}
    elif max_device is None:
        gates['device'] = {'status': 'unchecked', 'problems': []}
    else:
        over = device['total_instructions'] > max_device
        gates['device'] = {'status': 'fail' if over else 'pass',
                           'problems': [f"{device['chip']}: {device['total_instructions']:,} interpreted device "
                                        f"instructions (limit {max_device:,})"] if over else []}
    if data['packed'] is False:
        gates['packed'] = {'status': 'fail',
                           'problems': ['the packed executable was not compared with the reference']}
    elif data['packed'] is None:
        absent = 'the packed executable comparison is not in the report'
        gates['packed'] = {'status': 'fail' if require_packed else 'absent',
                           'problems': [absent] if require_packed else []}
    else:
        gates['packed'] = {'status': 'pass', 'problems': []}
    status, state_problems = _states_gate(data['states'])
    if status == 'absent' and require_states:
        absent = 'the fresh-process F8/F9 check is not in the report'
        gates['states'] = {'status': 'fail', 'problems': [absent]}
        problems.append(absent)
    else:
        gates['states'] = {'status': status, 'problems': state_problems}
    problems += [problem for gate in gates.values() for problem in gate['problems']]
    return {'shape': data['shape'], 'gates': gates, 'counts': counts, 'problems': problems}


def report_problems(report: dict, level: str, max_fallback: int, console: str = 'cps1', **options) -> list[str]:
    """What one conversion report lacks for the release check."""
    return check_report(report, console, level, max_fallback, **options)['problems']


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('converter', type=Path)
    parser.add_argument('roms', type=Path, nargs='+')
    parser.add_argument('--console', choices=CONSOLES, default=None,
                        help='Force the console instead of the converter detection')
    parser.add_argument('--work', type=Path, default=ROOT / '.build/release-check')
    parser.add_argument('--level', choices=LEVELS, default='standard')
    parser.add_argument('--max-fallback', type=int, default=0)
    parser.add_argument('--max-device', type=int, default=None)
    parser.add_argument('--require-packed', action='store_true')
    parser.add_argument('--require-states', action='store_true')
    parser.add_argument('--jobs', type=int, default=1, choices=range(1, 9), metavar='1-8',
                        help='Conversions at once inside the one batch (default 1)')
    parser.add_argument('--app', type=Path, default=None,
                        help='Where the frozen converter is copied and keeps its workspace (default WORK/app); '
                             'campaigns share one to fetch the pinned tools once')
    parser.add_argument('--batch-args', default='',
                        help='Extra command-line words for the converter batch command, one quoted string '
                             '(for example the Neo Geo BIOS or the X68000 IPL)')
    args = parser.parse_args(argv)

    work = args.work.resolve()
    games = work / 'Games'
    command = command_for(args.converter.resolve(), (args.app or work / 'app').resolve())
    command += ['batch', *map(str, args.roms), '--system', args.console or 'auto',
                '--scan-level', args.level, '--jobs', str(args.jobs), '--force', '--no-online-cover',
                '--output', str(games), *shlex.split(args.batch_args)]
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
        problems += batch_problems(record, len(args.roms), args.console)
        for game in record.get('games', []):
            report_path = Path(game['report']) if game.get('report') else None
            if game.get('status') != 'success' or not report_path or not report_path.is_file():
                continue
            console = args.console or game.get('system')
            checked = check_report(json.loads(report_path.read_text(encoding='utf-8')), console,
                                   args.level, args.max_fallback, args.max_device,
                                   args.require_packed, args.require_states)
            problems += [f"{game.get('title')}: {problem}" for problem in checked['problems']]
            gates = {name: gate['status'] for name, gate in checked['gates'].items()}
            games_checked.append({'title': game.get('title'), 'console': console, 'rom': game.get('rom'),
                                  'sha256': game.get('sha256'), 'report': str(report_path), 'shape': checked['shape'],
                                  'level': args.level, 'gates': gates, 'counts': checked['counts'],
                                  'problems': checked['problems']})
            summary = 'PASS' if not checked['problems'] else 'FAIL'
            detail = '; '.join(checked['problems'])
            print(f"{summary} {game.get('title')} ({console}): " + (detail or 'all report gates passed'))
    result = {'converter': str(args.converter), 'console': args.console, 'level': args.level,
              'roms': list(map(str, args.roms)), 'seconds': elapsed, 'games': games_checked,
              'problems': problems, 'passed': not problems}
    (work / 'release-check.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    for problem in problems:
        print('FAIL', problem)
    print(('PASS' if not problems else 'FAIL') + f': {len(games_checked)} game(s), {args.level}, {elapsed} s')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
