"""The public Game Boy test ROMs (blargg and Mooneye) through the converter, with their own verdict (gates G10 and G11).

The ROMs are the player's downloads, kept outside the repository (for example `.build/gb-testroms/`); only names, hashes and verdicts
are written here. Each test is converted by the converter (`RetroRecomp.py batch`, quick level, two at a time at most), then the
delivered executable is run headless in an empty folder and judged by the protocol of its own suite:

* Mooneye: the six Fibonacci registers (3, 5, 8, 13, 21, 34) at the `LD B,B` sentinel, or the six serial bytes; 0x42 six times is a failure.
* blargg: the word "Passed" or "Failed" printed on the serial port, or the memory verdict of the newer ROMs ($A001-$A003 = `DE B0 61`, then
  0 at $A000 passes and 0x80 is not finished).
* the run is repeated in the lock-step mode against the pinned interpreter (`--differential`) for as many frames as the verdict needed.

    python tools/gameboy_testroms.py list ROOT
    python tools/gameboy_testroms.py convert ROOT --work FOLDER [--only TEXT ...]
    python tools/gameboy_testroms.py run ROOT --work FOLDER [--only TEXT ...] [--no-differential]
    python tools/gameboy_testroms.py report --work FOLDER

Add `--model cgb` to every command to run the tests of the Game Boy Color in the Color build (docs/GAME_BOY_COLOR.md): the applicable set changes (the tests of every model and those marked
for the Color; `cgb_sound` in, `dmg_sound` and `oam_bug` out) and each ROM, which carries no Color flag, is converted in-process with a variant that does not ask for it.

A test that does not apply to the original Game Boy (another model, a test of the boot ROM dump, a manual visual test) is listed as
"not applicable" with its reason, never counted as passed. Nothing here validates a complete game.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIBONACCI = bytes((3, 5, 8, 13, 21, 34))
FAILURE = bytes((0x42,)) * 6
MODEL_SUFFIX = re.compile(r'-([A-Za-z0-9]+)$')
APPLICABLE_SUFFIXES = {'GS', 'dmgABC', 'dmgABCmgb'}
# The Game Boy Color (revisions B to E, the reference of docs/GAME_BOY_COLOR.md): the tests of every model, and those marked for it.
COLOR_SUFFIXES = {'C', 'cgb', 'cgbABCDE'}
FOLDER = {'dmg': 'Game Boy', 'cgb': 'Game Boy Color'}
RUNTIME_PREFIXES = ('[', 'Frame limit')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment() -> dict:
    return dict(os.environ, PYTHONUTF8='1', SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYINSTALLER_SUPPRESS_SPLASH_SCREEN='1')


def mooneye_applicability(relative: str, model: str = 'dmg') -> str | None:
    """None when the test applies to the machine (`model`: dmg, the original Game Boy, or cgb, the Color), else the reason it does not."""
    folder, _, name = relative.rpartition('/')
    stem = name[:-3]
    if model == 'cgb':
        if folder.startswith('utils') or folder == 'madness':
            return 'tool or other model'
        if folder == 'manual-only':
            return 'visual test, no verdict'
        suffix = MODEL_SUFFIX.search(stem)
        if suffix and suffix.group(1) not in COLOR_SUFFIXES:
            return {'cgb0': 'Color revision 0 only', 'A': 'Game Boy Advance only'}.get(suffix.group(1), 'another model')
        return None
    if folder.startswith(('utils', 'misc')) or folder == 'madness':
        return 'tool or other model' if not folder.startswith('misc') else 'Game Boy Color or Advance'
    if folder == 'manual-only':
        return 'visual test, no verdict'
    suffix = MODEL_SUFFIX.search(stem)
    if suffix and suffix.group(1) not in APPLICABLE_SUFFIXES:
        return {'dmg0': 'DMG revision 0 only', 'S': 'Super Game Boy only', 'sgb': 'Super Game Boy only', 'sgb2': 'Super Game Boy 2 only',
                'mgb': 'Game Boy Pocket only'}.get(suffix.group(1), 'Game Boy Color or Advance')
    return None


def discover(root: Path, model: str = 'dmg') -> list[dict]:
    """Every test ROM under ROOT: id, suite, source path, hash, protocol, reason when not applicable."""
    tests: list[dict] = []
    mooneye = next(iter(sorted(root.glob('mooneye-*/x/mts-*'))), None)
    if mooneye:
        for path in sorted(mooneye.rglob('*.gb')):
            relative = path.relative_to(mooneye).as_posix()
            ident = 'mooneye-' + relative[:-3].replace('/', '-')
            tests.append(dict(id=ident, suite='mooneye', source=str(path), name=relative, protocol='mooneye',
                              frames=1200, sha256=sha256(path), not_applicable=mooneye_applicability(relative, model)))
    for archive in sorted(root.glob('blargg-archive-org/*/x/*')):
        group = archive.parent.parent.name
        for path in sorted(archive.rglob('*.gb')):
            relative = path.relative_to(archive).as_posix()
            if model == 'cgb' and group in ('dmg_sound', 'dmg_sound-2', 'oam_bug', 'oam_bug-2'):
                reason = 'original Game Boy only'
            elif group == 'cgb_sound' and model != 'cgb':
                reason = 'Game Boy Color only'
            elif relative.count('/') == 0 and group != 'instr_timing':
                reason = 'combined ROM: the single ROMs are run instead'
            else:
                reason = None
            ident = 'blargg-' + group + '-' + re.sub(r'[^A-Za-z0-9_]+', '_', relative[:-3]).strip('_')
            tests.append(dict(id=ident, suite='blargg', source=str(path), name=f'{group}/{relative}',
                              protocol='blargg',
                              frames=10800, sha256=sha256(path), not_applicable=reason))
    return tests


def select(tests: list[dict], only: list[str] | None) -> list[dict]:
    chosen = [test for test in tests if not test['not_applicable']]
    return [test for test in chosen if not only or any(text in test['id'] for text in only)]


def serial_text(raw: bytes) -> str:
    lines = [line for line in raw.decode('ascii', errors='replace').splitlines() if not line.startswith(RUNTIME_PREFIXES)]
    return '\n'.join(line.strip() for line in lines if line.strip())


def judge(protocol: str, raw: bytes, state: dict | None) -> tuple[str, str]:
    """(verdict, evidence): verdict is passed, failed or incomplete."""
    if protocol == 'mooneye':
        registers = bytes(state[key] for key in 'bcdehl') if state else b''
        if FIBONACCI in raw or registers == FIBONACCI:
            return 'passed', 'Fibonacci ' + ('serial and registers' if FIBONACCI in raw and registers == FIBONACCI else 'registers' if registers == FIBONACCI else 'serial')
        if FAILURE in raw or registers == FAILURE:
            return 'failed', '0x42 six times'
        return 'incomplete', 'no verdict before the frame limit' + (f' (BCDEHL = {registers.hex()})' if registers else '')
    text = serial_text(raw)
    if state:
        eram = state.get('eram_a000_a0ff') or []
        if len(eram) > 3 and eram[1:4] == [0xDE, 0xB0, 0x61]:
            if eram[0] == 0:
                return 'passed', 'memory verdict 00 DE B0 61'
            if eram[0] != 0x80:
                return 'failed', f'memory verdict {eram[0]:02X} DE B0 61'
    if re.search(r'\bPassed\b', text):
        return 'passed', text.replace('\n', ' | ')[-100:]
    # A line of two hexadecimal digits is how blargg's instruction tests list a failed opcode: a heuristic, not part of the protocol.
    if re.search(r'\bFailed\b', text) or re.search(r'(?m)^[0-9A-F]{2}$', text):
        return 'failed', text.replace('\n', ' | ')[-160:]
    return 'incomplete', ('serial: ' + text.replace('\n', ' | ')[-100:]) if text else 'no serial text before the frame limit'


def converted_executable(work: Path, test: dict, model: str = 'dmg') -> Path:
    return work / 'out' / FOLDER[model] / f"{test['id']}.exe"


def convert(tests: list[dict], work: Path, jobs: int, model: str = 'dmg') -> None:
    (work / 'roms').mkdir(parents=True, exist_ok=True)
    (work / 'lib').mkdir(parents=True, exist_ok=True)
    todo = []
    for test in tests:
        if converted_executable(work, test, model).exists():
            continue
        target = work / 'roms' / f"{test['id']}.gb"
        shutil.copyfile(test['source'], target)
        todo.append(str(target))
    if not todo:
        return
    if model == 'cgb':
        return convert_color(todo, work, jobs)
    command = [sys.executable, '-B', str(ROOT / 'RetroRecomp.py'), 'batch', *todo, '--output', str(work / 'out'), '--jobs', str(jobs),
               '--scan-level', 'quick', '--no-online-cover', '--no-cover', '--no-icon-tags']
    log = work / 'convert.log'
    with log.open('ab') as handle:
        code = subprocess.run(command, cwd=ROOT, env=dict(environment(), RETRO_RECOMP_LIBRARY_DIR=str(work / 'lib')),
                              stdout=handle, stderr=subprocess.STDOUT).returncode
    print(f'conversion of {len(todo)} ROM(s) ended with code {code}; log: {log}')


def convert_color(todo: list[str], work: Path, jobs: int) -> None:
    """The Color build of each ROM, which carries no Color flag: the converter is called with a variant that does not ask for it (one process each,
    `jobs` at a time), into the games folder `out`, in the scratch library of `work`."""
    from concurrent.futures import ThreadPoolExecutor
    log = work / 'convert.log'
    def one(rom: str) -> int:
        command = [sys.executable, '-B', str(Path(__file__).resolve()), 'convert-one', rom, '--work', str(work)]
        with log.open('ab') as handle:
            return subprocess.run(command, cwd=ROOT, env=dict(environment(), RETRO_RECOMP_LIBRARY_DIR=str(work / 'lib')),
                                  stdout=handle, stderr=subprocess.STDOUT).returncode
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        codes = list(pool.map(one, todo))
    print(f'conversion of {len(todo)} ROM(s) in the Color build ended with codes {sorted(set(codes))}; log: {log}')


def convert_one_color(rom: Path, work: Path) -> int:
    sys.path.insert(0, str(ROOT))
    import dataclasses
    from retrorecomp import gameboy
    variant = dataclasses.replace(gameboy.COLOR, requires_color_flag=False)
    # One folder for each test (the converter writes the game and its report into the folder it is given), then the executable goes where the
    # Game Boy's batch puts it.
    folder = work / 'games' / rom.stem
    game = gameboy.convert_game_boy(rom, output=folder, scan_level='quick', online_cover=False, use_cover=False, icon_tags=False, variant=variant)
    target = work / 'out' / FOLDER['cgb'] / (rom.stem + '.exe')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(game, target)
    return 0


def launch(executable: Path, folder: Path, *arguments: str, timeout: int) -> tuple[bytes, int]:
    """Runs the executable headless from its own empty folder; never opens a window."""
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    copy = folder / executable.name
    shutil.copyfile(executable, copy)
    try:
        done = subprocess.run([str(copy), '--headless', *arguments], cwd=folder, env=environment(), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as caught:
        return (caught.stdout or b'') + (caught.stderr or b''), -1
    return done.stdout + done.stderr, done.returncode


def run_one(test: dict, work: Path, differential: bool, model: str = 'dmg') -> dict:
    executable = converted_executable(work, test, model)
    result = dict(id=test['id'], name=test['name'], suite=test['suite'], sha256=test['sha256'])
    if not executable.exists():
        return dict(result, verdict='not converted', evidence='no executable')
    with tempfile.TemporaryDirectory(dir=work) as scratch:
        folder = Path(scratch) / 'run'
        state_file = Path(scratch) / 'state.json'
        raw, state, verdict, evidence = b'', None, 'incomplete', ''
        # The stop options of the runtime do not end a Mooneye run at its sentinel, and a blargg test that reports in memory does not print: the
        # frame limit grows until a verdict shows, so that the lock-step comparison below covers no more frames than the test needed.
        steps = (60, 150, 300, 600, 1200) if test['protocol'] == 'mooneye' else (150, 300, 600, 1200, 2400, 4800)
        limits = [*(limit for limit in steps if limit < test['frames']), test['frames']]
        for limit in limits:
            flags = ['--limit-frames', str(limit), '--serial-stdout', '--dump-state', str(state_file)]
            if test['protocol'] != 'mooneye':
                flags.append('--stop-on-serial-verdict')
            state_file.unlink(missing_ok=True)
            raw, code = launch(executable, folder, *flags, timeout=600)
            state = json.loads(state_file.read_text()) if state_file.exists() else None
            verdict, evidence = judge(test['protocol'], raw, state)
            if verdict != 'incomplete':
                break
        frames = state.get('completed_frames') if state else None
        result.update(verdict=verdict, evidence=evidence, frames=frames, exit_code=code,
                      dispatch_fallbacks=state.get('dispatch_fallbacks') if state else None)
        if differential and frames:
            output, code = launch(executable, folder, '--differential', '--differential-frames', str(min(frames + 2, test['frames'])),
                                  '--limit-frames', str(test['frames']), timeout=1800)
            match = re.search(r'Matched generated and interpreter execution for (\d+) steps / (\d+) frames', output.decode('ascii', errors='replace'))
            result['differential'] = f'{match.group(1)} steps / {match.group(2)} frames' if match else 'no completed match (exit %d)' % code
    return result


def run(tests: list[dict], work: Path, differential: bool, model: str = 'dmg') -> None:
    results_file = work / 'results.json'
    results = {item['id']: item for item in json.loads(results_file.read_text())} if results_file.exists() else {}
    for test in tests:
        results[test['id']] = run_one(test, work, differential, model)
        row = results[test['id']]
        print(f"{row['verdict']:<14}{row['id']:<62}{row.get('frames')}\t{row.get('differential', '')}", flush=True)
        results_file.write_text(json.dumps(sorted(results.values(), key=lambda item: item['id']), indent=1))


def report(tests: list[dict], work: Path) -> None:
    results = {item['id']: item for item in json.loads((work / 'results.json').read_text())}
    counts: dict[str, dict[str, int]] = {}
    for test in tests:
        row = results.get(test['id'])
        verdict = 'not applicable' if test['not_applicable'] else row['verdict'] if row else 'not run'
        counts.setdefault(test['suite'], {}).setdefault(verdict, 0)
        counts[test['suite']][verdict] += 1
    print(json.dumps(counts, indent=1))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('command', choices=('list', 'convert', 'convert-one', 'run', 'report'))
    parser.add_argument('root', type=Path, nargs='?', help='folder holding the downloaded archives')
    parser.add_argument('--work', type=Path, required=False)
    parser.add_argument('--only', nargs='*', help='keep the tests whose id contains one of these texts')
    parser.add_argument('--jobs', type=int, default=2, choices=(1, 2))
    parser.add_argument('--no-differential', action='store_true')
    parser.add_argument('--model', choices=('dmg', 'cgb'), default='dmg', help='the machine: the original Game Boy or the Game Boy Color')
    args = parser.parse_args(argv)
    if args.command == 'convert-one':
        return convert_one_color(Path(args.root), args.work)
    tests = discover(args.root, args.model) if args.root else []
    if args.command == 'list':
        for test in tests:
            print(f"{test['id']:<62}{test['sha256'][:12]}  {test['not_applicable'] or ''}")
        return 0
    if args.command == 'convert':
        convert(select(tests, args.only), args.work, args.jobs, args.model)
    elif args.command == 'run':
        run(select(tests, args.only), args.work, not args.no_differential, args.model)
    else:
        report(tests, args.work)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
