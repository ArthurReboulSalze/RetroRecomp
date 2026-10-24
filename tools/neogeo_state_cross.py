"""Neo Geo: two builds of one game, frame by frame, and quick states across them.

    python tools/neogeo_state_cross.py A.exe B.exe [--warmup N] [--replay N] [--input-script FILE]

A and B are the Visual Studio and the portable-toolchain builds of one game.
The per-frame trace of A and of B on the same exact input route must be
identical; a state written by A resumes in B with the continuation of an
uninterrupted run, and the other way round.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import csv
import subprocess
from retrorecomp.neogeo_validation import ROUTES


def probe(exe, output, name, frames, script, *extra, rtc=True):
    """Same command line as retrorecomp.neogeo_state_checks.probe; CPS-1 has no RTC seed."""
    report, trace = output / (name + '.json'), output / (name + '.csv')
    args = [str(exe), '--headless', '--frames', str(frames), *(['--rtc-seed', '1760000000'] if rtc else []),
            '--report', str(report), '--trace', str(trace), '--script', str(script), *map(str, extra)]
    result = subprocess.run(args, capture_output=True, timeout=max(240, frames / 60 * 4))
    if result.returncode:
        raise RuntimeError(f'{name}: exit {result.returncode}: {result.stderr[-2000:]!r}')
    return json.loads(report.read_text(encoding='utf-8')), list(csv.DictReader(trace.open(newline='')))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first', type=Path)
    parser.add_argument('second', type=Path)
    parser.add_argument('--warmup', type=int, default=2600)
    parser.add_argument('--replay', type=int, default=300)
    parser.add_argument('--input-script', type=Path)
    parser.add_argument('--cps1', action='store_true', help='CPS-1 games take no RTC seed')
    parser.add_argument('--one-way', action='store_true',
                        help='only a state written by A must resume in B (an earlier release against its upgraded export)')
    args = parser.parse_args()
    exes = {'a': args.first.resolve(), 'b': args.second.resolve()}
    result = {}
    with tempfile.TemporaryDirectory(prefix='neogeo-cross-') as temp:
        folders = {name: Path(temp) / name for name in exes}
        script = Path(temp) / 'play.inputs'
        script.write_text(args.input_script.read_text(encoding='ascii') if args.input_script else ROUTES['play'][1],
                          encoding='ascii')
        traces = {}
        for name, exe in exes.items():
            folders[name].mkdir()
            state = folders[name] / 'frame.rrstate'
            report, rows = probe(exe, folders[name], 'continuous', args.warmup + args.replay, script,
                                 '--checkpoint', args.warmup, state, rtc=not args.cps1)
            traces[name] = (report, rows)
        rows_a, rows_b = traces['a'][1], traces['b'][1]
        mismatch = next((n for n, (x, y) in enumerate(zip(rows_a, rows_b)) if x != y), None)
        result['frames_compared'] = len(rows_a)
        result['same_trace_in_both_builds'] = mismatch is None and len(rows_a) == len(rows_b)
        result['first_trace_mismatch'] = mismatch
        result['state_bytes'] = {}
        result['states_resume_across_builds'] = True
        for label, writer, reader in (('a_to_b', 'a', 'b'), ('b_to_a', 'b', 'a'))[:1 if args.one_way else 2]:
            state = folders[writer] / 'frame.rrstate'
            restored, rows = probe(exes[reader], folders[reader], f'restored-{label}', args.replay, script,
                                   '--load-state', state, rtc=not args.cps1)
            ok = restored['state_loaded'] and len(rows) == args.replay and \
                traces[writer][1][args.warmup:args.warmup + args.replay] == rows
            result['states_resume_across_builds'] &= bool(ok)
            result['state_bytes'][label] = state.stat().st_size
        result['same_state_size'] = args.one_way or result['state_bytes']['a_to_b'] == result['state_bytes']['b_to_a']
    print(json.dumps(result, indent=2))
    good = result['same_trace_in_both_builds'] and result['states_resume_across_builds'] and result['same_state_size']
    return 0 if good else 1


if __name__ == '__main__':
    sys.exit(main())
