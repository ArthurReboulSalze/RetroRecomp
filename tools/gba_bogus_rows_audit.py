"""Audit of the Game Boy Advance shared paths against invented rows (docs/COMPILATION_LIBRARY.md, the CPS-1's audit adapted).

    python -B tools/gba_bogus_rows_audit.py plan SOURCE [--seed N] [--count 2000]
    python -B tools/gba_bogus_rows_audit.py run SOURCE --bios BIOS [--seed N] [--count 2000] [--scratch DIR] [--passes 3] [--frames 3600]
                                              [--clean-report conversion-report.json]

SOURCE is a cartridge (.gba) or the project folder of a converted game (`.build/gba_<title>_<sha12>_<engine8>/`, which holds `rom.gba`);
BIOS is your own `gba_bios.bin`. Both are only read.

What it does. It invents COUNT ROM roots and as many RAM copies (at most the schema's 4,096) that are valid in the schema and in the rules of
`gba_knowledge` but random: roots anywhere inside the cartridge (a multiple of 4 for ARM, Thumb flag in bit 0), copies from anywhere in the cartridge
to anywhere in IWRAM or EWRAM. They are written as the imported side bank of a SCRATCH data folder (the player's real `Export/datas` is never touched:
`retrorecomp.paths.data_directory` and `retrorecomp.library.library_root` are redirected to the scratch folder for the whole run), then
`gba_conversion.convert` converts the cartridge there, as a player who received a hostile record would. The conversion's own project folder is separate
from the player's (the title is prefixed `audit-<seed>`), so it does not collide with a conversion of the same cartridge.

What it reports (JSON in the scratch folder, summary on the screen):
  * `passed`: the conversion ended and every scenario of the generated code equals the engine's interpreter alone (the report's `native_validation`);
    a conversion that raised is `passed: false` with its message (the batch would then convert again without the imported rows);
  * `interpreted_instructions`: per scenario, from the final pass, and with `--clean-report` the same figures of a clean conversion beside them;
  * `functions`: the generator's count of discovered functions, and with `--clean-report` the clean one (a bogus root the generator accepted is a function);
  * `bogus_roots_named_in_generator_log` and `bogus_roots_named_in_generated_code`: how many of the invented ROM roots' addresses the generator's log and
    its generated sources mention. An indication, not a proof: an address can also appear as a literal;
  * `shared_paths`: the converter's own counters (received, used, left out by the cap, qualified by this converter: always 0);
  * `bogus_rows_in_players_paths` and `bogus_rows_in_promoted_record`: invented rows found in the scratch library's `paths.json` and in the record the
    conversion would share. Both MUST be 0: received rows are never saved nor shared.
It says nothing about CPU fidelity, hardware fidelity, gameplay validation or physical latency. No window is opened; the long builds run as the
converter runs them (the toolchain's own processes, waited for with timeouts). Run it when no other conversion of the cartridge is running and no timing
is being taken.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp import gba_analysis, gba_knowledge  # noqa: E402

DEFAULT_COUNT = 2000
_ENV = ('RETRO_RECOMP_LIBRARY_DIR', 'SMSRECOMP_LIBRARY_DIR', 'RETRO_RECOMP_BUNDLED_KNOWLEDGE')


def bogus_rows(size: int, seed: int, count: int = DEFAULT_COUNT) -> tuple[list, list]:
    """(roots, spans) invented from `seed` for a cartridge of `size` bytes: every row valid in the schema and in `gba_knowledge`, none meaningful.
    At most `count` roots (fewer when the cartridge is too small for that many distinct ones) and `min(count, SPAN_LIMIT)` RAM copies."""
    rng = random.Random(f'gba-bogus-rows:{seed}:{size}')
    roots, attempts = set(), 0
    while len(roots) < count and attempts < count * 20:
        attempts += 1
        offset = rng.randrange(0, max(1, size - 1))
        value = (offset & ~1) | 1 if rng.random() < 0.5 else offset & ~3
        if gba_knowledge.root_valid(value, size):
            roots.add(value)
    spans, attempts = set(), 0
    wanted = min(count, gba_knowledge.SPAN_LIMIT)
    while len(spans) < wanted and attempts < wanted * 20:
        attempts += 1
        length = rng.randrange(2, 129) * 2
        if length > size:
            continue
        offset = rng.randrange(0, (size - length) // 2 + 1) * 2
        low, high = rng.choice(gba_knowledge._PROFILE.windows)
        address = rng.randrange(low, high - length) & ~1
        row = (address | rng.randrange(2), offset, length)
        if gba_knowledge.span_valid(row, size):
            spans.add(row)
    return sorted(roots), sorted(spans)


def bogus_record(rom: bytes, seed: int, count: int = DEFAULT_COUNT) -> dict:
    """The record of those rows for this exact cartridge, with the current `cores`: what a hostile sender would upload."""
    roots, spans = bogus_rows(len(rom), seed, count)
    return gba_knowledge.make_record(hashlib.sha256(rom).hexdigest(), rom, roots, spans)


def install(record: dict, datas: Path) -> Path:
    """Write `record` as the imported side bank of the scratch data folder `datas`."""
    from retrorecomp import knowledge
    path = datas / 'knowledge' / 'imported-v3.json.gz'
    knowledge.write_side_bank(path, {record['game']: record})
    return path


def resolve_source(source: Path) -> Path:
    source = Path(source)
    if source.is_dir():
        for name in ('rom.gba',):
            if (source / name).is_file():
                return source / name
        raise SystemExit(f'{source} holds no rom.gba: give the cartridge or a converted game\'s project folder.')
    if not source.is_file():
        raise SystemExit(f'{source} is not a file.')
    return source


def _scenario_figures(report: dict) -> dict:
    """{scenario: interpreted instructions} of the final pass of a report."""
    return {row.get('scenario'): row.get('interpreted_opcodes') for row in report.get('final_checks', ()) if isinstance(row, dict)}


def summarize(report: dict | None, error: str, bogus: tuple, records: dict, clean: dict | None = None, *, generator_log: str = '', generated_text: str = '') -> dict:
    """The audit's verdict from the report a conversion wrote (None when it raised) and the files it left. Pure: no conversion, no file name."""
    roots, spans = bogus
    own = records.get('players_paths') or {'roots': set(), 'spans': set()}
    promoted = records.get('promoted') or {'roots': set(), 'spans': set()}
    named = lambda text: sum(1 for root in roots if f'{gba_analysis.ROM_BASE + (root & ~1):08X}' in text.upper())
    summary = {'invented': {'roots': len(roots), 'ram_copies': len(spans)}, 'error': error or None,
               'passed': bool(report and not error and (report.get('native_validation') or {}).get('passed') is True)}
    if report:
        coverage = report.get('native_coverage') or {}
        summary |= {'interpreted_instructions': _scenario_figures(report), 'functions': (coverage.get('generated') or {}).get('functions'),
                    'shared_paths': coverage.get('shared_paths'), 'unresolved_misses': coverage.get('unresolved_misses'),
                    'scenarios_match': {row.get('scenario'): row.get('match') for row in (report.get('native_validation') or {}).get('scenarios', ())}}
    summary |= {'bogus_roots_named_in_generator_log': named(generator_log), 'bogus_roots_named_in_generated_code': named(generated_text),
                'bogus_rows_in_players_paths': len(own['roots'] & set(roots)) + len(own['spans'] & set(spans)),
                'bogus_rows_in_promoted_record': len(promoted['roots'] & set(roots)) + len(promoted['spans'] & set(spans))}
    if clean:
        clean_coverage = clean.get('native_coverage') or {}
        summary['clean'] = {'interpreted_instructions': _scenario_figures(clean), 'functions': (clean_coverage.get('generated') or {}).get('functions'),
                            'passed': (clean.get('native_validation') or {}).get('passed')}
        if report and summary.get('functions') is not None and summary['clean']['functions'] is not None:
            summary['extra_functions_over_the_clean_conversion'] = summary['functions'] - summary['clean']['functions']
    summary['ok'] = bool(summary['passed'] and not summary['bogus_rows_in_players_paths'] and not summary['bogus_rows_in_promoted_record'])
    return summary


def _rows_of(record: dict | None) -> dict:
    if not record:
        return {'roots': set(), 'spans': set()}
    roots, spans = gba_knowledge.rows(record)
    return {'roots': set(roots), 'spans': {tuple(row) for row in spans}}


def run(source: Path, bios: Path, seed: int, count: int, scratch: Path, passes: int, frames: int, clean_report: Path | None) -> dict:
    """Convert `source` once in the scratch folder with the invented record received, and judge it."""
    from retrorecomp import gba_conversion, knowledge
    from retrorecomp.core import ConversionError, slug
    path = resolve_source(source)
    rom = path.read_bytes()
    sha256 = hashlib.sha256(rom).hexdigest()
    bogus = bogus_rows(len(rom), seed, count)
    record = bogus_record(rom, seed, count)
    scratch = Path(scratch).resolve()
    datas = scratch / 'datas'
    install(record, datas)
    title = f"audit-{seed}-{path.stem.split(' (')[0].strip() or path.stem}"
    project = ROOT / '.build' / f'gba_{slug(title)}_{sha256[:12]}_{gba_conversion.ENGINE_REV[:8]}'
    environment = {name: value for name, value in os.environ.items() if name not in _ENV}
    report, error, records = None, '', {}
    knowledge._side_games.cache_clear()
    with mock.patch.dict(os.environ, environment, clear=True), mock.patch('retrorecomp.paths.data_directory', return_value=datas), \
            mock.patch('retrorecomp.library.library_root', side_effect=lambda system='sms': scratch / 'library' / system):
        try:
            gba_conversion.convert(path, title=title, passes=passes, frames=frames, gba_bios=str(bios), player=False, emit=lambda text: print(text, flush=True))
        except ConversionError as failure:
            error = str(failure)
        store = scratch / 'library' / 'gba' / sha256 / gba_conversion.ENGINE_REV / 'paths.json'
        try:
            records['players_paths'] = gba_analysis.observations_of(json.loads(store.read_text(encoding='utf-8')))
            records['players_paths'] = {'roots': set(records['players_paths'].roots), 'spans': set(records['players_paths'].spans)}
        except (OSError, ValueError):
            records['players_paths'] = None
        records['promoted'] = _rows_of(gba_knowledge.library_record(sha256))
    knowledge._side_games.cache_clear()
    destination = project / 'conversion-report.json'
    if not error and destination.is_file():
        report = json.loads(destination.read_text(encoding='utf-8'))
    log = project / 'generated.log'
    generated = '\n'.join(item.read_text(encoding='utf-8', errors='replace') for item in sorted((project / 'generated').glob('recompiled_*.cpp')))
    clean = json.loads(Path(clean_report).read_text(encoding='utf-8')) if clean_report else None
    summary = summarize(report, error, bogus, records, clean, generator_log=log.read_text(encoding='utf-8', errors='replace') if log.is_file() else '',
                        generated_text=generated)
    summary['seed'], summary['cartridge_sha256'], summary['project'] = seed, sha256, str(project)
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / f'audit-{seed}.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('command', choices=('plan', 'run'))
    parser.add_argument('source', type=Path)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--count', type=int, default=DEFAULT_COUNT)
    parser.add_argument('--bios', type=Path)
    parser.add_argument('--scratch', type=Path, default=ROOT / '.build' / 'gba-bogus-audit')
    parser.add_argument('--passes', type=int, default=3)
    parser.add_argument('--frames', type=int, default=3600)
    parser.add_argument('--clean-report', type=Path)
    args = parser.parse_args(argv)
    if args.command == 'plan':
        rom = resolve_source(args.source).read_bytes()
        roots, spans = bogus_rows(len(rom), args.seed, args.count)
        record = bogus_record(rom, args.seed, args.count)
        print(json.dumps({'cartridge_bytes': len(rom), 'roots': len(roots), 'ram_copies': len(spans), 'cores': gba_knowledge.engine(),
                          'record_sha256': gba_knowledge.record_digest(record)}, indent=2))
        return 0
    if not args.bios:
        parser.error('run needs --bios')
    summary = run(args.source, args.bios, args.seed, args.count, args.scratch, args.passes, args.frames, args.clean_report)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
