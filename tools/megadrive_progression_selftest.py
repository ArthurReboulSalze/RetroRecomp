"""Long controller replays with strict CPU comparison and fresh-process states.

This exercises real inputs, not scripted guest-memory patches. It does not
prove that a level was completed or replace visual, listening or board tests.
All reports, traces and temporary snapshots stay in the chosen local output.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.console16 import reference_differences
from retrorecomp.library import atomic_json


class ProbeFailure(RuntimeError):
    def __init__(self, name, returncode, output):
        self.returncode = returncode
        super().__init__(f'{name}: exit {returncode}; see {output}')


def controller_script(frames):
    events = {0: (0, 0)}
    # Several real Start/confirm presses allow for different original menus.
    for frame, key in ((180, 128), (300, 128), (480, 128), (660, 128),
                       (800, 16), (900, 64), (1000, 32), (1100, 128)):
        if frame < frames:
            events[frame] = (key, 0)
        if frame + 2 < frames:
            events[frame + 2] = (0, 0)
    # Exercise both ports, changing directions and all three ordinary buttons.
    # Inputs last long enough to produce actual edges and held-button behavior.
    for frame in range(1200, frames, 30):
        n = (frame - 1200) // 30
        direction = (8, 8, 0, 4, 1, 2, 8, 0)[(n // 8) % 8]
        fire = (0, 16, 0, 32, 0, 64, 16 | 32, 0)[n % 8]
        p2 = (0, 4, 32, 4 | 16, 0, 8, 64, 0)[(n // 3) % 8]
        # Occasional Start edges also traverse pauses/dialogues without leaving
        # the game permanently paused. No inference about level progress follows.
        if n % 240 in (100, 104):
            direction, fire = 0, 128
        events[frame] = (direction | fire, p2)
    assert len(events) <= 4096, 'Host replay capacity exceeded.'
    return events


def script_text(events, limit=None):
    return ''.join(f'{frame} {p1} {p2}\n' for frame, (p1, p2) in sorted(events.items())
                   if limit is None or frame < limit)


def run(executable, output, name, frames, script, *, reference=False, extra=()):
    report, trace = output / f'{name}.json', output / f'{name}.csv'
    command = [str(executable), '--frames', str(frames), '--report', str(report),
               '--trace', str(trace), '--input-script', str(script), *map(str, extra)]
    env = os.environ.copy()
    env.pop('GENESIS_FORCE_INTERP', None)
    if reference:
        env['GENESIS_FORCE_INTERP'] = '1'
    start = time.monotonic()
    completed = subprocess.run(command, cwd=output, env=env, capture_output=True,
        text=True, encoding='utf-8', errors='replace', timeout=1800,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (output / f'{name}.log').write_text(completed.stdout + completed.stderr, encoding='utf-8')
    if completed.returncode:
        raise ProbeFailure(name, completed.returncode, output)
    data = json.loads(report.read_text(encoding='utf-8'))
    with trace.open(newline='', encoding='utf-8') as file:
        rows = list(csv.DictReader(file))
    assert data['frames'] == frames and len(rows) == frames
    assert data['execution_fault'] is False
    for key in ('bus_budget_misses', 'z80_timing_misses'):
        assert data[key] == 0, f'{name}: {key}'
    return data, rows, round(time.monotonic() - start, 3)


def trace_difference(left, right):
    assert left and right
    keys = set(left[0]) - {'native', 'interpreted'}
    assert keys == set(right[0]) - {'native', 'interpreted'}
    if len(left) != len(right):
        return {'lengths': [len(left), len(right)]}
    for a, b in zip(left, right):
        different = {key: [a[key], b[key]] for key in sorted(keys) if a[key] != b[key]}
        if different:
            return {'frame': a['frame'], 'fields': different}
    return None


def check(executable, output, frames, replay, *, gameplay_events=None):
    executable, output = executable.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    original_sha = hashlib.sha256(executable.read_bytes()).hexdigest()
    summary = {'exe': str(executable), 'sha256': original_sha, 'frames_per_route': frames,
        'replay_frames': replay,
        'evidence_axes': {'cpu': 'Internal independently decoded CPU; hardware is shared',
            'gameplay': 'Original controller traffic; no claim of level completion',
            'physical_latency_measured': False}, 'routes': [], 'passed': False}
    atomic_json(output / 'result.json', summary)
    if gameplay_events is not None:
        assert gameplay_events and len(gameplay_events) <= 4096
        assert all(isinstance(frame, int) and 0 <= frame < frames + replay
                   and len(buttons) == 2
                   and all(isinstance(value, int) and 0 <= value <= 0xfff for value in buttons)
                   for frame, buttons in gameplay_events.items()), 'Invalid gameplay replay.'
    gameplay = ('gameplay', gameplay_events) if gameplay_events is not None else (
        'two-port', controller_script(frames + replay))
    for name, events in (('attract', {0: (0, 0)}), gameplay):
        script = output / f'{name}-inputs.txt'
        script.write_text(script_text(events), encoding='ascii')
        prefix = output / f'{name}-prefix-inputs.txt'
        # These read-only evaluations have separate processes and output files.
        # A three-game qualification runs at most six probes simultaneously.
        with ThreadPoolExecutor(max_workers=2) as pool:
            native_run = pool.submit(run, executable, output, name, frames + replay, script)
            reference_run = pool.submit(run, executable, output, name + '-reference',
                frames + replay, script, reference=True)
            baseline, rows, seconds = native_run.result()
            reference, other, ref_seconds = reference_run.result()
        differences = reference_differences('md', baseline, reference)
        first_difference = trace_difference(rows, other)
        # Verify that the reference route truly used the decoder in its own
        # fresh process; toggling the cached mode within a process is invalid.
        assert reference['native_entries'] == 0 and reference['retired_interpreted_opcodes'] > 0
        state = output / f'{name}.rrstate'
        checkpoint_attempts = []
        # Disk states deliberately exclude live C/fiber continuations. F8 in
        # the player waits for a safe boundary; the headless probe returns 8.
        # Retry nearby frame boundaries and compare their actual continuation,
        # never relax capture checks or pretend the requested frame was saved.
        for delay in (0, 1, 2, 4, 8, 16, 32):
            if delay >= replay:
                break
            checkpoint = frames + delay
            prefix.write_text(script_text(events, checkpoint), encoding='ascii')
            try:
                saved, saved_rows, _ = run(executable, output, name + f'-prefix-{delay}',
                    checkpoint, prefix, extra=('--save-state', state))
            except ProbeFailure as error:
                if error.returncode != 8:
                    raise
                checkpoint_attempts.append({'frame': checkpoint, 'save_exit': 8})
                continue
            checkpoint_attempts.append({'frame': checkpoint, 'save_exit': 0})
            assert trace_difference(rows[:checkpoint], saved_rows) is None
            break
        else:
            raise RuntimeError(f'{name}: no safe state boundary; see {output}')
        if not checkpoint_attempts or checkpoint_attempts[-1]['save_exit']:
            raise RuntimeError(f'{name}: no safe state boundary; see {output}')
        remaining = frames + replay - checkpoint
        restored, future, _ = run(executable, output, name + '-restored', remaining, script,
            extra=('--frame-offset', checkpoint, '--load-state', state))
        replay_difference = trace_difference(rows[checkpoint:], future)
        # Hash/state diagnostics are cumulative only inside one invocation;
        # the full final guest fields compare through the shared state helper.
        from tools.console16_state_selftest import GUEST_FIELDS
        state_fields = [key for key in GUEST_FIELDS if key in baseline]
        state_differences = [key for key in state_fields if baseline[key] != restored[key]]
        native = all(data['interpreted_opcodes'] == data['audio_interpreted_opcodes'] == 0
                     for data in (baseline, saved, restored))
        route = {'name': name, 'native_fallback': baseline['interpreted_opcodes'],
            'sound_fallback': baseline['audio_interpreted_opcodes'],
            'restored_main_fallback': restored['interpreted_opcodes'],
            'restored_sound_fallback': restored['audio_interpreted_opcodes'],
            'first_main_fallback_frame': next((r['frame'] for r in rows if int(r['interpreted'])), None),
            'reference_differences': differences, 'first_trace_difference': first_difference,
            'state_differences': state_differences, 'first_state_replay_difference': replay_difference,
            'native_seconds': seconds, 'reference_seconds': ref_seconds,
            'unique_frame_hashes': len({r['frame_hash'] for r in rows}),
            'native_report': str(output / f'{name}.json'),
            'state_checkpoint_frame': checkpoint, 'state_replay_frames': remaining,
            'checkpoint_attempts': checkpoint_attempts,
            'passed': native and not differences and first_difference is None
                and not state_differences and replay_difference is None}
        summary['routes'].append(route)
        atomic_json(output / 'result.json', summary)
        print(json.dumps(route, ensure_ascii=False), flush=True)
    assert hashlib.sha256(executable.read_bytes()).hexdigest() == original_sha
    summary['passed'] = all(route['passed'] for route in summary['routes'])
    summary['executable_unchanged'] = True
    atomic_json(output / 'result.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=18000)
    parser.add_argument('--replay', type=int, default=600)
    args = parser.parse_args()
    if not 1200 <= args.frames <= 60000 or not 1 <= args.replay <= 1800:
        parser.error('Use 1200–60000 frames and 1–1800 replay frames.')
    assert check(args.executable, args.output, args.frames, args.replay)['passed']


if __name__ == '__main__':
    main()
