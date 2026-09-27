"""Audit current exports with strict native/reference execution; no new binaries."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp import __version__
from smsrecomp.core import ROOT, probe, read_rom
from smsrecomp.paths import games_directory
from smsrecomp.validation import compare_execution


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=games_directory())
    parser.add_argument('--frames', type=int, default=18000)
    args = parser.parse_args()
    if not 1 <= args.frames <= 30000:
        parser.error('--frames must be between 1 and 30000')
    games = []
    for path in sorted((args.output / 'datas/reports').glob('*/conversion-report.json')):
        report = json.loads(path.read_text(encoding='utf-8'))
        if report['backend'] != 'banked':
            continue
        if report['version'] != __version__ or not report.get('native_validation', {}).get('passed'):
            raise RuntimeError(f'Regenerate this export before auditing it: {path}')
        original = ROOT / 'ROMS' / report['rom']['name']
        original_matches = read_rom(original).sha256 == report['rom']['sha256'] if original.exists() else None
        exe = args.output / report['executable']
        before = hashlib.sha256(exe.read_bytes()).hexdigest()
        comparisons = []
        for scenario in report['final_checks']:
            name = scenario['scenario']
            directory = Path(report['build_directory']) / f'checks/release-{args.frames}-{name}'
            native = probe(exe, directory / 'native', args.frames, strict=True, press=scenario['scripted_input'])
            reference = probe(exe, directory / 'reference', args.frames, reference=True, press=scenario['scripted_input'])
            result = compare_execution(native, reference, directory / 'native', directory / 'reference')
            result['checks']['zero_fallback'] = native.get('interpreter_cycles') == 0 and native.get('banked', {}).get('fallback_steps') == 0
            result['passed'] = all(result['checks'].values())
            result.update(scenario=name, native=native, reference=reference)
            comparisons.append(result)
            print(f'{exe.stem} / {name}: {"PASS" if result["passed"] else "FAIL"}, {args.frames} frames, fallback={native.get("interpreter_cycles")}', flush=True)
        games.append({'game': exe.stem, 'rom_sha256': report['rom']['sha256'], 'original_rom_unchanged': original_matches,
            'executable_sha256': before, 'executable_unchanged': before == hashlib.sha256(exe.read_bytes()).hexdigest(),
            'compiler_signature': report['compiler_signature'], 'native_coverage': report['native_coverage'],
            'comparisons': comparisons, 'passed': all(c['passed'] for c in comparisons) and original_matches is not False})
    matrix = {'version': __version__, 'checked_utc': datetime.now(timezone.utc).isoformat(), 'games': games,
              'frames_per_scenario': args.frames, 'passed': bool(games) and all(g['passed'] and g['executable_unchanged'] for g in games),
              'scope': 'Strict native execution versus corrected reference CPU on the same hardware runtime',
              'full_games_validated': False, 'physical_latency_ms': None, 'hardware_accuracy_validated': False}
    target = args.output / 'datas/Retro-Recomp-verification.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(matrix, indent=2), encoding='utf-8')
    print(target)
    if not matrix['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
