"""Compare two builds of one Mega Drive / SNES / Neo Geo / CPS-1 EXE, frame by frame.

    python tools/state16_cross.py A.exe B.exe [--warmup N] [--replay N] [--input-script FILE]

A and B are the Visual Studio and the portable-toolchain builds of one game.
Three things are checked, each separate from the others:

1. the per-frame guest trace of A and of B on the same input route is
   identical (video, audio, CPU and memory hashes);
2. a quick state written by A resumes in B, and the other way round, with the
   same trace and final guest state as an uninterrupted run;
3. the state files of A and B have the same size.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console16_state_selftest import GUEST_FIELDS, run
from state_checks import controls_text, route_controls


def route(exe: Path, output: Path, total: int, script: Path | None) -> Path:
    identified, _ = run(exe, output, 'identify', 1)
    md = 'console_version' in identified
    path = output / 'input.txt'
    if script:
        path.write_text(script.read_text(encoding='ascii'), encoding='ascii')
    else:
        path.write_text(controls_text(route_controls(total, md=md)), encoding='ascii')
    return path


def resume(writer: Path, reader: Path, output: Path, warmup: int, replay: int, script: Path, baseline, rows):
    """`writer` saves a state after `warmup` frames, `reader` resumes it."""
    lines = [line for line in script.read_text(encoding='ascii').splitlines() if line.strip()]
    prefix = output / 'prefix-input.txt'
    prefix.write_text(''.join(line + '\n' for line in lines if int(line.split()[0]) < warmup), encoding='ascii')
    state = output / 'saved.rrstate'
    state.unlink(missing_ok=True)
    run(writer, output, 'prefix', warmup, '--play', '--input-script', prefix, '--save-state', state)
    restored, future = run(reader, output, 'restored', replay, '--play', '--input-script', script,
                           '--frame-offset', warmup, '--load-state', state)
    columns = [key for key in rows[0] if key not in ('native', 'interpreted')]
    for number, (a, b) in enumerate(zip(rows[warmup:], future)):
        differing = [key for key in columns if a[key] != b[key]]
        if differing:
            raise AssertionError(f'{reader.name} diverges {number} frames after the state: {differing[:5]}')
    differing = [key for key in GUEST_FIELDS if key in baseline and baseline[key] != restored.get(key)]
    if differing:
        raise AssertionError(f'{reader.name}: final guest state differs: {differing}')
    return state.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('first', type=Path)
    parser.add_argument('second', type=Path)
    parser.add_argument('--warmup', type=int, default=1200)
    parser.add_argument('--replay', type=int, default=300)
    parser.add_argument('--input-script', type=Path)
    parser.add_argument('--one-way', action='store_true',
                        help='only a state written by A must resume in B (an earlier release against its upgraded export)')
    args = parser.parse_args()
    total = args.warmup + args.replay
    first, second = args.first.resolve(), args.second.resolve()
    result = {}
    with tempfile.TemporaryDirectory(prefix='state16-cross-') as temp:
        folders = {name: Path(temp) / name for name in ('a', 'b')}
        for folder in folders.values():
            folder.mkdir()
        script = route(first, folders['a'], total, args.input_script)
        (folders['b'] / 'input.txt').write_text(script.read_text(encoding='ascii'), encoding='ascii')
        baselines = {name: run(exe, folders[name], 'baseline', total, '--play', '--input-script', script)
                     for name, exe in (('a', first), ('b', second))}
        (report_a, rows_a), (report_b, rows_b) = baselines['a'], baselines['b']
        columns = [key for key in rows_a[0] if key not in ('native', 'interpreted')]
        mismatch = next((n for n, (x, y) in enumerate(zip(rows_a, rows_b)) if any(x[k] != y[k] for k in columns)), None)
        result['frames_compared'] = len(rows_a)
        result['same_trace_in_both_builds'] = mismatch is None and len(rows_a) == len(rows_b)
        result['first_trace_mismatch'] = mismatch
        result['same_final_guest_state'] = all(report_a.get(k) == report_b.get(k) for k in GUEST_FIELDS)
        sizes = {}
        for label, writer, reader, folder, base in (('a_to_b', first, second, folders['a'], baselines['a']),
                                                    ('b_to_a', second, first, folders['b'], baselines['b']))[:1 if args.one_way else 2]:
            sizes[label] = resume(writer, reader, folder, args.warmup, args.replay, script, *base)
        result['state_bytes'] = sizes
        result['states_resume_across_builds'] = True
        result['same_state_size'] = args.one_way or sizes['a_to_b'] == sizes['b_to_a']
    print(json.dumps(result, indent=2))
    return 0 if result['same_trace_in_both_builds'] and result['same_final_guest_state'] and result['same_state_size'] else 1


if __name__ == '__main__':
    sys.exit(main())
