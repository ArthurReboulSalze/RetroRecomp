"""Replay sound regressions on locally supplied Mega Drive exports, without a GUI.

No ROM, game memory patches, screenshots or audio devices are used. The SOR2
sequence follows the original game's Options/BGM controls (Sega manual).
"""
from pathlib import Path
import argparse
import csv
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.console16 import reference_differences


def music_inputs():
    events = []
    def press(frame, mask):
        events.extend(((frame, mask, 0), (frame + 3, 0, 0)))
    for frame in (300, 620, 1000):
        press(frame, 128)  # Skip intro, open main menu.
    for frame in (1200, 1250, 1300):
        press(frame, 2)
    press(1400, 128)  # Options
    for frame in (1700, 1750):
        press(frame, 2)  # BGM
    selections = []
    for track in range(28):
        frame = 1900 + track * 180
        press(frame, 64)  # A plays the selected track; B/C adjust it.
        press(frame + 150, 8)
        selections.append(frame + 150)
    press(7100, 2)  # Move to SE after the music sweep.
    press(7200, 8)
    return sorted(events), selections + [7200]


def check(executable, scenario, output):
    output.mkdir(parents=True, exist_ok=True)
    events, selections = music_inputs()
    script = output / 'sound-test.inputs'
    script.write_text(''.join(f'{frame} {p1} {p2}\n' for frame, p1, p2 in events), encoding='ascii')
    frames = 7300 if scenario == 'sor2-music' else 3600
    reports = []
    for reference in (False, True):
        label = 'reference' if reference else 'native'
        report, trace = output / f'{label}.json', output / f'{label}.csv'
        args = [str(executable.resolve()), '--frames', str(frames), '--report', str(report.resolve())]
        args += (['--input-script', str(script.resolve()), '--trace', str(trace.resolve())]
                 if scenario == 'sor2-music' else ['--play'])
        env = os.environ.copy()
        env.pop('GENESIS_FORCE_INTERP', None)
        if reference:
            env['GENESIS_FORCE_INTERP'] = '1'
        result = subprocess.run(args, cwd=output, env=env, capture_output=True,
                                timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
        (output / f'{label}.log').write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f'{label} probe failed: {result.returncode}; see {output}')
        data = json.loads(report.read_text(encoding='utf-8'))
        if data['frames'] != frames or data['execution_fault']:
            raise AssertionError('Game stopped before the end of the scenario')
        # An FM DAC DC offset can be nonzero while the game remains silent.
        if data['fm_active_frames'] < frames // 5:
            raise AssertionError('FM output lacks sustained changing samples')
        if scenario == 'sor2-music':
            with trace.open(encoding='ascii') as stream:
                rows = list(csv.DictReader(stream))
            for frame in selections:
                if rows[frame - 2]['frame_hash'] == rows[frame + 20]['frame_hash']:
                    raise AssertionError(f'Options stopped responding near frame {frame}')
        reports.append(data)
    differences = reference_differences('md', *reports)
    if differences:
        raise AssertionError(f'Native/reference mismatch: {differences}')
    summary = {'scenario': scenario, 'frames': frames, 'passed': True,
               'selection_changes_checked': len(selections) if scenario == 'sor2-music' else 0,
               'interpreted_68000_opcodes': reports[0]['interpreted_opcodes'],
               'fm_active_frames': reports[0]['fm_active_frames'],
               'interpreted_z80_opcodes': reports[0]['audio_interpreted_opcodes'],
               'pcm_reference_match': True, 'sound_cpu': reports[0]['audio_cpu'],
               'hardware_fidelity_validated': False, 'physical_latency_measured': False}
    (output / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--scenario', required=True, choices=('sor2-music', 'aladdin-audio'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.executable, args.scenario, args.output.resolve())))
