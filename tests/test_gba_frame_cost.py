"""tools/gba_frame_cost.py with a fake probe: no ROM, no probe executable, no compiler, no game.

The fake probe is a small Python script that prints the engine's `bounded_run` and `vblank_snapshot` lines, is started
through a one-line launcher (.bat on Windows, shell script elsewhere) and logs each call, so the order of the runs, the
best-of-N rule, the JSON, the refusal on a differing hash and the dry run can be checked without any cartridge.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from retrorecomp import gba_build
from tools import gba_frame_cost, toolchain_compare

FAKE = '''
import json, os, sys
label, per_frame, variant = sys.argv[1], float(sys.argv[2]), sys.argv[3]
args = sys.argv[4:]
frames = int(args[args.index('--frames') + 1])
log = os.environ['FAKE_LOG']
try:
    seen = sum(1 for line in open(log) if line.split()[0] == label)
except OSError:
    seen = 0
with open(log, 'a') as handle:
    handle.write('%s %d %s %s\\n' % (label, frames, os.environ.get('SDL_VIDEODRIVER'), os.environ.get('GBARECOMP_VBLANK_SNAPSHOT')))
if variant == 'fail':
    print('FATAL: fake failure')
    sys.exit(3)
factor = [1.3, 1.0, 1.2][seen % 3]
seconds = per_frame * (frames + 1) / 1000 * factor
if variant != 'none':
    print('vblank_snapshot frame=%d cycles=%d mem=%08x cpu=%08x' % (100 + frames + 1, 1000 * frames, int(variant), int(variant) + 1))
print('bounded_run start_frame=100 end_frame=%d presented=0 view_width=240 uncapped=1 seconds=%.6f guest_fps=1.000 present_fps=0.000'
      % (100 + frames + 1, seconds))
with open(os.environ['GBARECOMP_COVERAGE_JSON'], 'w') as handle:
    json.dump({'interpreted_insns': 7, 'coverage': 'fake'}, handle)
'''


class FakeProbeCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gba-frame-cost-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'fake_probe.py').write_text(FAKE, encoding='utf-8', newline='\n')
        self.log = self.root / 'calls.log'
        self.rom = self.root / 'authored.gba'
        self.rom.write_bytes(b'authored test bytes, not a cartridge')
        self.bios = self.root / 'bios.bin'
        self.bios.write_bytes(b'authored test bios bytes')
        previous = os.environ.get('FAKE_LOG')
        os.environ['FAKE_LOG'] = str(self.log)
        self.addCleanup(lambda: os.environ.__setitem__('FAKE_LOG', previous) if previous is not None else os.environ.pop('FAKE_LOG', None))

    def launcher(self, name: str, per_frame: float = 1.0, variant: str = '1') -> Path:
        """A one-line launcher of the fake probe: label `name`, milliseconds per frame, variant of the snapshot."""
        fake = self.root / 'fake_probe.py'
        arguments = f'"{sys.executable}" "{fake}" {name} {per_frame} {variant}'
        if os.name == 'nt':
            path = self.root / f'probe_{name}.bat'
            path.write_bytes(f'@echo off\r\n{arguments} %*\r\n'.encode('ascii'))
        else:
            path = self.root / f'probe_{name}.sh'
            path.write_bytes(f'#!/bin/sh\nexec {arguments} "$@"\n'.encode('ascii'))
            path.chmod(0o755)
        return path

    def sides(self, a_variant='1', b_variant='1', b_cost=1.5):
        return (gba_frame_cost.Side('A', (str(self.launcher('A', 1.0, a_variant)),)),
                gba_frame_cost.Side('B', (str(self.launcher('B', b_cost, b_variant)),)))

    def context(self, frames=10):
        script = self.root / 'work' / 'scripts' / 'generic.txt'
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(gba_build.input_script(frames, 'generic'), encoding='ascii', newline='\n')
        return gba_frame_cost.Context(self.rom, 'a' * 40, self.bios, script, None, 60)

    def calls(self):
        return [line.split() for line in self.log.read_text(encoding='ascii').splitlines()]

    def cli(self, *arguments):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gba_frame_cost.main(list(arguments))
        return code, out.getvalue()

    def run_args(self, a: Path, b: Path, *extra):
        return ['run', '--a', str(a), '--b', str(b), '--rom', str(self.rom), '--bios', str(self.bios), '--frames', '10',
                '--runs', '3', '--work', str(self.root / 'work'), '--results', str(self.root / 'result.json'), *extra]


class ParsingTests(unittest.TestCase):
    def test_bounded_run_line(self):
        text = ('noise\nbounded_run start_frame=7 end_frame=3608 presented=0 view_width=240 uncapped=1 seconds=1.234567 '
                'guest_fps=2917.0 present_fps=0.000\nmore\n')
        self.assertEqual(gba_frame_cost.parse_bounded(text),
                         {'start_frame': 7, 'end_frame': 3608, 'frames': 3601, 'seconds': 1.234567})
        self.assertIsNone(gba_frame_cost.parse_bounded('bounded_window start_frame=1 end_frame=2 presented=1 seconds=1.0'))
        self.assertIsNone(gba_frame_cost.parse_bounded(''))

    def test_snapshot_line(self):
        text = 'vblank_snapshot frame=3601 cycles=1022 mem=00ab12cd cpu=ffee0011\n'
        self.assertEqual(gba_frame_cost.parse_snapshot(text), {'cycles': 1022, 'mem': '00ab12cd', 'cpu': 'ffee0011'})
        self.assertIsNone(gba_frame_cost.parse_snapshot('nothing here'))

    def test_pin_is_the_shared_helper(self):
        self.assertIs(gba_frame_cost.pin, toolchain_compare.pin)


class MeasureTests(FakeProbeCase):
    def test_order_best_of_n_and_fields(self):
        result = gba_frame_cost.measure(self.sides(), self.context(), 10, 3, self.root / 'work', emit=lambda text: None)
        self.assertEqual([call[0] for call in self.calls()], ['A', 'B', 'A', 'B', 'A', 'B', 'A', 'B', 'A', 'B'])
        self.assertEqual([call[1] for call in self.calls()], ['10', '10', '0', '0'] + ['10'] * 6)   # warm-ups, 0-frame runs, rounds
        self.assertEqual(result['order'], ['warmup A', 'warmup B', 'startup A', 'startup B', 'A', 'B', 'A', 'B', 'A', 'B'])
        self.assertTrue(all(call[2:] == ['dummy', '1'] for call in self.calls()))                   # no window, snapshot asked
        a, b = result['sides']['A'], result['sides']['B']
        self.assertEqual(len(a['raw_ms_per_frame']), 3)                  # the warm-up is dropped, three timed runs are kept
        self.assertEqual(sorted(a['raw_ms_per_frame']), [1.0, 1.2, 1.3])
        self.assertEqual((a['best'], a['median']), (1.0, 1.2))
        self.assertEqual((b['best'], b['median']), (1.5, 1.8))
        self.assertEqual(a['frames'], [11, 11, 11])                      # the extra frame up to the next VBlank is counted
        self.assertEqual(a['interpreted_insns'], 7)
        self.assertEqual((a['cycles'], a['mem_hash'], a['cpu_hash']), (10000, '00000001', '00000002'))
        self.assertTrue(a['work_identical'] and b['work_identical'])
        self.assertEqual(len(a['wall_seconds']), 3)
        self.assertIsNotNone(a['startup_wall_seconds'])
        self.assertEqual(len(a['wall_minus_startup_ms_per_frame']), 3)
        comparison = result['comparison']
        self.assertTrue(comparison['work_identical'])
        self.assertFalse(comparison['refused'])
        self.assertEqual(comparison['ratio_best_b_over_a'], 1.5)
        self.assertEqual(comparison['delta_best_ms_per_frame'], 0.5)

    def test_differing_work_refuses_the_comparison(self):
        result = gba_frame_cost.measure(self.sides(b_variant='2'), self.context(), 10, 2, self.root / 'work', emit=lambda t: None)
        self.assertTrue(result['sides']['A']['work_identical'])
        self.assertFalse(result['sides']['B']['work_identical'])
        comparison = result['comparison']
        self.assertTrue(comparison['refused'])
        self.assertFalse(comparison['work_identical'])
        self.assertIsNone(comparison['ratio_best_b_over_a'])
        self.assertIn('did not do the same work', comparison['reason'])
        self.assertIn('COMPARISON REFUSED', gba_frame_cost.render(result))

    def test_missing_snapshot_cannot_be_checked(self):
        result = gba_frame_cost.measure(self.sides(a_variant='none'), self.context(), 10, 1, self.root / 'work', emit=lambda t: None)
        self.assertTrue(result['comparison']['refused'])
        self.assertIn('no vblank_snapshot', result['comparison']['reason'])
        self.assertFalse(result['sides']['A']['work_identical'])

    def test_failed_run_is_an_error(self):
        with self.assertRaises(gba_frame_cost.FrameCostError) as caught:
            gba_frame_cost.measure(self.sides(a_variant='fail'), self.context(), 10, 1, self.root / 'work', emit=lambda t: None)
        self.assertIn('exit code 3', str(caught.exception))


class CommandLineTests(FakeProbeCase):
    def test_run_writes_the_json_and_the_banner(self):
        code, output = self.cli(*self.run_args(self.launcher('A', 1.0), self.launcher('B', 2.0)))
        self.assertEqual(code, 0)
        self.assertIn('VALID ONLY ON A QUIET PC', output)
        self.assertIn('QUIET PC NOT CONFIRMED', output)
        data = json.loads((self.root / 'result.json').read_text(encoding='utf-8'))
        for key in ('core', 'machine', 'measure', 'honesty', 'not_measured', 'python', 'os', 'cpu', 'quiet_pc_confirmed',
                    'sides', 'comparison', 'scenario', 'frames_requested', 'runs'):
            self.assertIn(key, data)
        self.assertEqual((data['machine'], data['measure'], data['quiet_pc_confirmed']), ('gba', 'host_time_only', False))
        for side in data['sides'].values():
            for key in ('raw_ms_per_frame', 'best', 'median', 'frames', 'seconds', 'wall_seconds', 'interpreted_insns',
                        'cycles', 'mem_hash', 'cpu_hash', 'work_identical'):
                self.assertIn(key, side)
        self.assertEqual(data['comparison']['ratio_best_b_over_a'], 2.0)
        # the converter's own key script was written, and a report prints the saved file again
        self.assertEqual((self.root / 'work' / 'scripts' / 'generic.txt').read_text(encoding='ascii'),
                         gba_build.input_script(10, 'generic'))
        code, again = self.cli('report', str(self.root / 'result.json'))
        self.assertEqual(code, 0)
        self.assertIn('B / A: 2.0', again)

    def test_quiet_confirmed_is_recorded(self):
        code, output = self.cli(*self.run_args(self.launcher('A'), self.launcher('B'), '--quiet-confirmed'))
        self.assertEqual(code, 0)
        self.assertTrue(json.loads((self.root / 'result.json').read_text(encoding='utf-8'))['quiet_pc_confirmed'])
        self.assertNotIn('QUIET PC NOT CONFIRMED', output)

    def test_differing_hash_exits_2_and_keeps_the_raw_values(self):
        code, output = self.cli(*self.run_args(self.launcher('A', variant='1'), self.launcher('B', variant='5')))
        self.assertEqual(code, 2)
        self.assertIn('COMPARISON REFUSED', output)
        data = json.loads((self.root / 'result.json').read_text(encoding='utf-8'))
        self.assertTrue(data['comparison']['refused'])
        self.assertEqual(len(data['sides']['B']['raw_ms_per_frame']), 3)

    def test_dry_run_runs_nothing(self):
        a, b = self.launcher('A'), self.launcher('B')
        code, output = self.cli(*self.run_args(a, b, '--dry-run', '--core', '3'))
        self.assertEqual(code, 0)
        self.assertFalse(self.log.exists())                                   # the fake probe was never started
        self.assertFalse((self.root / 'result.json').exists())
        self.assertIn('DRY RUN - NOT A MEASUREMENT', output)
        self.assertIn('VALID ONLY ON A QUIET PC', output)
        # The launchers by name: Windows CI spells its temporary folder short (RUNNER~1) and the tool prints it long.
        for needle in (a.name, b.name, '--no-window', '--frames 10', '--frames 0', 'GBARECOMP_VBLANK_SNAPSHOT=1', 'core 3'):
            self.assertIn(needle, output)


class HonestyTests(FakeProbeCase):
    def test_no_five_measure_claim(self):
        result = gba_frame_cost.measure(self.sides(), self.context(), 10, 1, self.root / 'work', emit=lambda t: None)
        self.assertEqual(result['measure'], 'host_time_only')
        for measure in ('native code share', 'CPU fidelity', 'hardware fidelity', 'gameplay validation', 'physical latency'):
            self.assertIn(measure, result['not_measured'])
        text = (json.dumps(result) + gba_frame_cost.render(result) + gba_frame_cost.QUIET_BANNER + gba_frame_cost.HONESTY
                + gba_frame_cost.__doc__).lower()
        for word in ('exact', 'zero latency', 'zero-latency', 'cycle-accurate', 'bit-perfect'):
            self.assertNotIn(word, text)
        self.assertIn('says nothing about native code share', gba_frame_cost.HONESTY)


if __name__ == '__main__':
    unittest.main()
