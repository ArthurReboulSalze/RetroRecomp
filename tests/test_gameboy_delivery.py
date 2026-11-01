"""The liveness record and the packed replay of the Game Boy conversion (retrorecomp/gameboy_delivery.py), on synthetic data: no ROM,
no build, no compressor. The shared decisions are pinned by tests/test_delivery_evidence.py; these tests pin what is the Game Boy's
own: how a line of the per-frame trace is read, which route must move, and the replay of the comparison verdict."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import gameboy_delivery as delivery
from retrorecomp.core import ConversionError
from retrorecomp.delivery_evidence import LIVENESS_KEYS, DeliveredFile, FrameRow
from retrorecomp.gameboy_coverage import ProbeScenario, probe_scenarios

HEADER = 'frame,picture,sound,nonzero_samples,ram,pc\n'


def write_trace(directory: Path, name: str, lines: list[str]) -> Path:
    path = directory / name
    path.write_text(HEADER + ''.join(line + '\n' for line in lines), encoding='ascii')
    return path


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: [path.unlink() for path in self.directory.iterdir()] and self.directory.rmdir())

    def test_a_line_is_read_as_a_frame_row(self):
        path = write_trace(self.directory, 'a.csv', ['1,00000000000000aa,00000000000000f0,0,00000000000000c1,0150',
                                                      '2,00000000000000bb,00000000000000f1,12,00000000000000c1,0153'])
        self.assertEqual(delivery.read_frame_rows(path), [
            FrameRow(1, '00000000000000aa', '00000000000000f0', False, '00000000000000c1', '0150'),
            FrameRow(2, '00000000000000bb', '00000000000000f1', True, '00000000000000c1', '0153')])

    def test_the_record_carries_the_nine_common_keys(self):
        path = write_trace(self.directory, 'b.csv', ['1,aa,f0,0,c1,0150', '2,bb,f1,12,c2,0153', '3,bb,f1,0,c2,0153'])
        record = delivery.liveness_record(path)
        self.assertEqual(tuple(record), LIVENESS_KEYS)
        self.assertEqual((record['frames'], record['distinct_pictures'], record['picture_changes'],
                          record['last_picture_change_frame']), (3, 2, 1, 2))
        self.assertEqual((record['audible_frames'], record['last_audible_frame'], record['distinct_sound_blocks']), (1, 2, 2))
        self.assertEqual((record['distinct_ram_states'], record['distinct_program_counters']), (2, 2))

    def test_a_silent_trace_says_zero_audible_frames_not_none(self):
        path = write_trace(self.directory, 'c.csv', ['1,aa,f0,0,c1,0150', '2,bb,f0,0,c1,0150'])
        record = delivery.liveness_record(path)
        self.assertEqual(record['audible_frames'], 0)   # the trace does say that nothing was audible
        self.assertEqual(record['distinct_sound_blocks'], 1)


class MainRouteTests(unittest.TestCase):
    @staticmethod
    def check(name, pictures, frames=3600):
        return {'scenario': name, 'liveness': None if pictures is None else {'frames': frames, 'distinct_pictures': pictures}}

    def test_the_main_route_is_one_of_the_probe_scenarios(self):
        self.assertIn(delivery.MAIN_ROUTE, {scenario.name for scenario in probe_scenarios(3600)})

    def test_a_frozen_main_route_is_refused(self):
        with self.assertRaises(ConversionError) as caught:
            delivery.require_moving_main_route([self.check('boot', 40), self.check(delivery.MAIN_ROUTE, 1)])
        self.assertIn(delivery.MAIN_ROUTE, str(caught.exception))

    def test_a_route_with_no_picture_is_frozen_too(self):
        with self.assertRaises(ConversionError):
            delivery.require_moving_main_route([self.check(delivery.MAIN_ROUTE, 0)])

    def test_the_other_routes_may_stand_still(self):
        delivery.require_moving_main_route([self.check('boot', 1), self.check('play_r', 1), self.check('play_l', 1),
                                            self.check(delivery.MAIN_ROUTE, 2)])

    def test_a_probe_run_without_the_trace_is_not_judged(self):
        delivery.require_moving_main_route([self.check(delivery.MAIN_ROUTE, None)])


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.comparisons = [(ProbeScenario('boot'), 30), (ProbeScenario('varied', '180:S:4'), 240)]
        self.references = {'boot': 'Matched 30 frames', 'varied': 'Matched 240 frames'}
        self.calls = []

    def deliver(self, executable, packed, label, emit):
        emit(f'{label}: comparing the compressed executable with the fresh reference.')
        return DeliveredFile(Path('packed-game.exe'), None, 'ab' * 32)

    def run_replay(self, verdicts):
        def compare(executable, project, frames, scenario, tag):
            self.calls.append((Path(executable).name, frames, scenario.name, tag))
            return verdicts[scenario.name]
        messages = []
        with mock.patch.object(delivery, 'deliver_packed', self.deliver):
            delivered = delivery.replay_delivered(Path('game.exe'), Path('project'), self.comparisons, self.references,
                                                  compare, messages.append)
        return delivered, messages

    def test_every_route_is_replayed_on_the_compressed_copy_with_the_same_frames(self):
        delivered, messages = self.run_replay(dict(self.references))
        self.assertEqual(sorted(self.calls), [('packed-game.exe', 30, 'boot', 'packed'),
                                             ('packed-game.exe', 240, 'varied', 'packed')])
        self.assertEqual(delivered.validation_fields(), {'packed_reference_match': True})
        self.assertEqual(delivered.report_fields(), {'packed_candidate_sha256': 'ab' * 32})
        self.assertTrue(messages and 'compressed executable' in messages[0])

    def test_a_different_verdict_on_one_route_refuses_the_file(self):
        with self.assertRaises(ConversionError) as caught:
            self.run_replay({'boot': 'Matched 30 frames', 'varied': 'Matched 240 frames, 7 steps fewer'})
        self.assertIn("route 'varied'", str(caught.exception))
        self.assertEqual(len(self.calls), 2)   # every replay ran before the first difference was raised

    def test_a_file_that_was_not_replayed_cannot_claim_a_match(self):
        with self.assertRaises(ValueError):
            DeliveredFile(Path('packed-game.exe'), None, 'cd' * 32).validation_fields()


if __name__ == '__main__':
    unittest.main()
