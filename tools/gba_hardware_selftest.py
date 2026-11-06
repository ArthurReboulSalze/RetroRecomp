"""The authored Game Boy Advance test ROMs (jsmolka gba-tests, MIT) through the converter, with their own verdict (gate G11).

The ROMs are the maintainer's downloads of authored test programs, kept outside the repository (for example a local clone of
`jsmolka/gba-tests`); only names, hashes and verdicts are written here, and no ROM byte is copied into the repository. Each judged
test is converted by the repository's own pipeline (`retrorecomp.gba_conversion.convert`: the pinned engine, the probe host, headless,
no player, one conversion at a time). The player's own BIOS file is given by `--bios` (or the environment variable
`RETRORECOMP_GBA_BIOS`) and is never stored or copied anywhere.

These suites draw one message screen when every check passes, and "Failed test NNN" at the first check that does not. The passing
screen is deterministic, so the verdict compares the SHA-256 of the pixel data (RGB bytes, not the PNG file) of the probe's final
picture of the boot scenario with `EXPECTED_PASS_PICTURE`. Any other picture is a failure, and its hash stays in the report.

    python tools/gba_hardware_selftest.py list ROOT
    python tools/gba_hardware_selftest.py run ROOT --work FOLDER --bios FILE [--only TEXT ...] [--frames N]
    python tools/gba_hardware_selftest.py report --work FOLDER

Verdicts: pass, fail, not run (a judged ROM no run has reached yet), not judged (a visual test or a ROM outside this proof, with its
reason) and not applicable. The exit code is 0 only when at least one ROM is judged and every judged ROM passed. What is measured
here is the agreement of the converted game with the authored test's own checks on the boot scenario: it says nothing about
complete games, gameplay validation, hardware fidelity beyond those checks, or physical latency; the interpreted instruction count of the
conversion is reported next to each verdict, never hidden.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REPORT_NAME = 'gba-hardware-report.json'
BIOS_ENVIRONMENT = 'RETRORECOMP_GBA_BIOS'
DEFAULT_FRAMES = 400
SCENARIO = 'boot'
# The relative paths (inside ROOT, with `/`) of the self-checking suites: each prints one message screen at the end.
JUDGED = ('arm/arm.gba', 'thumb/thumb.gba', 'memory/memory.gba', 'bios/bios.gba',
          'save/none.gba', 'save/sram.gba', 'save/flash64.gba', 'save/flash128.gba')
# The SHA-256 of the RGB pixels of the screen every passing suite draws ("All tests passed"), recorded on the first run of
# arm.gba through this tool on 5 Nov 2026 and checked on the other seven suites.
EXPECTED_PASS_PICTURE = 'e33384104712250daf9c599ef59680eadf88c9e111f81a4d4de8d7a6b15be21b'
# One entry per suite when a suite does not draw the common screen (relative path -> hash); none was needed.
EXPECTED_BY_SUITE: dict[str, str] = {}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def picture_hash(path: Path) -> str:
    """SHA-256 of the decoded RGB pixel data of a picture file (the PNG container is not part of it)."""
    from PIL import Image
    with Image.open(path) as image:
        return hashlib.sha256(image.convert('RGB').tobytes()).hexdigest()


def classify(relative: str) -> tuple[bool, str | None]:
    """(judged, reason it is not judged) for a ROM path relative to the root."""
    if relative in JUDGED:
        return True, None
    if relative.startswith('ppu/'):
        return False, 'visual test, no on-screen verdict to compare'
    return False, 'not one of the self-checking suites of this proof'


def discover(root: Path) -> list[dict]:
    """Every `.gba` under ROOT: id, relative name, source, ROM hash, judged or not and why not."""
    tests = []
    for path in sorted(root.rglob('*.gba'), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        judged, reason = classify(relative)
        tests.append(dict(id=relative[:-4].replace('/', '-'), name=relative, source=str(path), sha256=sha256_of(path),
                          judged=judged, not_judged=reason))
    return tests


def select(tests: list[dict], only: list[str] | None) -> list[dict]:
    return [test for test in tests if not only or any(text in test['id'] for text in only)]


def expected_picture(name: str) -> str:
    return EXPECTED_BY_SUITE.get(name, EXPECTED_PASS_PICTURE)


def judge(name: str, picture: str | None, *, exit_code: int = 0, aborted: str | None = None) -> tuple[str, str]:
    """(verdict, reason) of one judged ROM from the hash of its final picture and how the probe ended."""
    if exit_code:
        return 'fail', f'the probe host stopped with code {exit_code}' + (f' ({aborted})' if aborted else '')
    if not picture:
        return 'fail', 'no final picture was left by the probe host'
    if picture == expected_picture(name):
        return 'pass', 'the final picture is the suite\'s passing screen'
    return 'fail', 'the final picture is not the passing screen (a failed check, or no verdict yet)'


def aggregate(rows: list[dict]) -> dict:
    """Counts per verdict and the exit code rule: 0 only if something is judged and every judged ROM passed."""
    counts: dict[str, int] = {}
    for row in rows:
        counts[row['verdict']] = counts.get(row['verdict'], 0) + 1
    judged = [row for row in rows if row['verdict'] in ('pass', 'fail', 'not run')]
    return {'counts': counts, 'judged': len(judged), 'all_judged_pass': bool(judged) and all(row['verdict'] == 'pass' for row in judged)}


def exit_code(rows: list[dict]) -> int:
    return 0 if aggregate(rows)['all_judged_pass'] else 1


def row_of(test: dict) -> dict:
    """The row of a ROM no run has reached: judged ones wait, the others carry their reason."""
    base = dict(id=test['id'], name=test['name'], sha256=test['sha256'])
    if test['judged']:
        return dict(base, verdict='not run', reason='no conversion has run for it yet', picture_sha256=None,
                    interpreted_instructions=None)
    return dict(base, verdict='not judged', reason=test['not_judged'], picture_sha256=None, interpreted_instructions=None)


def merge_rows(tests: list[dict], stored: list[dict]) -> list[dict]:
    """One row per ROM listed: the stored result when its ROM hash is unchanged, else a fresh waiting row."""
    kept = {row['id']: row for row in stored}
    rows = []
    for test in tests:
        old = kept.get(test['id'])
        rows.append(old if old and old.get('sha256') == test['sha256'] and old['verdict'] != 'not run' else row_of(test))
    return rows


def environment(work: Path) -> None:
    """Headless, UTF-8, and a library of its own so that no observation of a test ROM reaches the player's library."""
    os.environ.update(PYTHONUTF8='1', SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYINSTALLER_SUPPRESS_SPLASH_SCREEN='1',
                      RETRO_RECOMP_LIBRARY_DIR=str(work / 'lib'))


def run_one(test: dict, work: Path, bios: Path, frames: int) -> dict:
    from retrorecomp.gba_conversion import convert
    row = row_of(test)
    (work / 'roms').mkdir(parents=True, exist_ok=True)
    (work / 'pictures').mkdir(parents=True, exist_ok=True)
    target = work / 'roms' / f"{test['id']}.gba"
    shutil.copyfile(test['source'], target)
    output = work / 'out' / test['id']
    started = time.perf_counter()
    try:
        convert(target, output=output, gba_bios=str(bios), player=False, passes=1, frames=frames, emit=lambda text: None)
        document = json.loads((output / 'conversion-report.json').read_text(encoding='utf-8'))
    except Exception as caught:                       # a conversion that fails is a failure of the proof, never a pass
        return dict(row, verdict='fail', reason=f'conversion failed: {type(caught).__name__}: {caught}'[:400])
    scenarios = {item['scenario']: item for item in document.get('final_checks', [])}
    boot = scenarios.get(SCENARIO, {})
    picture, copied = None, work / 'pictures' / f"{test['id']}.png"
    source = Path(document.get('build_directory', '')) / 'runs' / SCENARIO / 'frame.png'
    if source.is_file():
        shutil.copyfile(source, copied)
        picture = picture_hash(copied)
    verdict, reason = judge(test['name'], picture, exit_code=boot.get('exit_code') or 0, aborted=boot.get('aborted'))
    other = scenarios.get('generic', {})
    return dict(row, verdict=verdict, reason=reason, picture_sha256=picture, frames=boot.get('frames'),
                interpreted_instructions=boot.get('interpreted_opcodes'),
                interpreted_by_scenario={name: item.get('interpreted_opcodes') for name, item in scenarios.items()},
                coverage=boot.get('coverage'), reference_match=boot.get('reference_match'),
                generic_picture_sha256=other.get('picture_sha256'), seconds=round(time.perf_counter() - started, 1))


def load_rows(work: Path) -> list[dict]:
    try:
        return json.loads((work / REPORT_NAME).read_text(encoding='utf-8'))['roms']
    except (OSError, ValueError, KeyError):
        return []


def write_report(work: Path, rows: list[dict]) -> None:
    work.mkdir(parents=True, exist_ok=True)
    document = {'tool': 'gba_hardware_selftest', 'gate': 'G11', 'scenario': SCENARIO, 'expected_pass_picture': EXPECTED_PASS_PICTURE,
                'summary': aggregate(rows),
                'measures': {'native_code': 'interpreted instruction count of the conversion, per ROM',
                             'cpu_fidelity': 'agreement with the authored suite\'s own checks on the boot scenario only',
                             'hardware_fidelity': 'not claimed', 'gameplay_validation': 'not claimed: no complete game is run here',
                             'physical_latency': 'not measured'},
                'roms': rows}
    (work / REPORT_NAME).write_text(json.dumps(document, indent=1) + '\n', encoding='utf-8')


def table(rows: list[dict]) -> str:
    lines = [f"{'verdict':<13}{'rom':<22}{'interpreted':<13}{'picture':<14}reason"]
    for row in rows:
        count = row.get('interpreted_instructions')
        lines.append(f"{row['verdict']:<13}{row['name']:<22}{'' if count is None else count:<13}"
                     f"{(row.get('picture_sha256') or '')[:12]:<14}{row.get('reason') or ''}")
    return '\n'.join(lines)


def run(tests: list[dict], chosen: list[dict], work: Path, bios: Path, frames: int) -> list[dict]:
    environment(work)
    rows = merge_rows(tests, load_rows(work))
    write_report(work, rows)
    by_id = {row['id']: index for index, row in enumerate(rows)}
    for test in chosen:
        if not test['judged']:
            continue
        rows[by_id[test['id']]] = run_one(test, work, bios, frames)
        write_report(work, rows)
        row = rows[by_id[test['id']]]
        print(f"{row['verdict']:<8}{row['name']:<22}interpreted={row.get('interpreted_instructions')}  {(row.get('picture_sha256') or '')[:12]}",
              flush=True)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('command', choices=('list', 'run', 'report'))
    parser.add_argument('root', type=Path, nargs='?', help='folder holding the authored test ROMs')
    parser.add_argument('--work', type=Path, help='work folder (outside the repository tree, for example under .build)')
    parser.add_argument('--bios', type=Path, default=os.environ.get(BIOS_ENVIRONMENT) or None, help=f'your own GBA BIOS file (default: ${BIOS_ENVIRONMENT})')
    parser.add_argument('--only', nargs='*', help='keep the tests whose id contains one of these texts')
    parser.add_argument('--frames', type=int, default=DEFAULT_FRAMES)
    args = parser.parse_args(argv)
    if args.command == 'report':
        if not args.work:
            parser.error('report needs --work')
        rows = load_rows(args.work)
        print(table(rows))
        print(json.dumps(aggregate(rows), indent=1))
        return exit_code(rows)
    if not args.root:
        parser.error(f'{args.command} needs ROOT')
    tests = discover(args.root)
    if args.command == 'list':
        for test in tests:
            print(f"{test['id']:<24}{test['sha256'][:12]}  {'judged' if test['judged'] else 'not judged: ' + test['not_judged']}")
        return 0
    if not args.work or not args.bios:
        parser.error(f'run needs --work and --bios (or ${BIOS_ENVIRONMENT})')
    rows = run(tests, select(tests, args.only), args.work, args.bios, args.frames)
    print(table(rows))
    return exit_code(rows)


if __name__ == '__main__':
    raise SystemExit(main())
