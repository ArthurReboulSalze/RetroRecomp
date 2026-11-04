"""Liveness (G8) and the packed replay (G5) of the Super Nintendo, on synthetic traces and a fake delivered file."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp import delivery_evidence, snes_evidence as evidence
from retrorecomp.core import ConversionError
from retrorecomp.delivery_evidence import DeliveredFile


class SnesEvidenceTests(unittest.TestCase):
    HEADER = 'frame,frame_hash,native,interpreted,audio_hash'

    def trace(self, rows, header=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'play.trace.csv'
        path.write_text(chr(10).join([header or self.HEADER] + rows) + chr(10), encoding='ascii')
        return path

    def line(self, frame, picture, sound='aa'):
        return f'{frame},{picture},10,0,{sound}'

    def test_a_moving_route_has_its_record(self):
        record = evidence.route_liveness(self.trace([
            self.line(1, 'p1', 's1'), self.line(2, 'p1', 's1'), self.line(3, 'p2', 's2'), self.line(4, 'p2', 's2')]),
            {'pcm_nonzero': 1234, 'visible_frames': 4})
        self.assertEqual(record, {'frames': 4, 'distinct_pictures': 2, 'picture_changes': 1, 'last_picture_change_frame': 3,
                                  'audible_frames': 4, 'last_audible_frame': 4, 'distinct_sound_blocks': 2,
                                  'pcm_nonzero': 1234, 'visible_frames': 4})

    def test_a_frame_of_silence_is_not_audible(self):
        # The host's per-frame sound hash of n zero samples is the FNV basis times the prime n times; every even n a frame can
        # carry (NTSC 1,598, PAL 1,920, none) is a silent block, and a hash that is any other value is a frame with a sample.
        silent = lambda samples: f'{delivery_evidence.silent_sound_hash(samples):016x}'
        record = evidence.route_liveness(self.trace([
            self.line(1, 'p1', silent(1598)), self.line(2, 'p2', silent(1598)), self.line(3, 'p3', 'ffffffffffffffff'),
            self.line(4, 'p4', silent(1920)), self.line(5, 'p5', silent(0))]))
        self.assertEqual((record['audible_frames'], record['last_audible_frame']), (1, 3))
        self.assertEqual(len(evidence.silent_blocks()), evidence.MAX_FRAME_SAMPLES // 2 + 1)
        for samples in (0, 2, 1598, 1920, evidence.MAX_FRAME_SAMPLES):
            self.assertIn(silent(samples), evidence.silent_blocks(), samples)

    def test_what_the_host_does_not_write_is_none_not_zero(self):
        # A trace without a sound column says nothing about the sound: "no evidence", never "silent".
        record = evidence.route_liveness(self.trace(['1,pa', '2,pb', '3,pb'], header='frame,frame_hash'))
        self.assertEqual((record['distinct_pictures'], record['picture_changes']), (2, 1))
        for key in ('audible_frames', 'last_audible_frame', 'distinct_sound_blocks', 'pcm_nonzero', 'visible_frames'):
            self.assertIsNone(record[key], key)

    def test_a_trace_without_a_picture_column_is_refused(self):
        with self.assertRaises(ConversionError):
            evidence.route_liveness(self.trace(['1,x'], header='frame,native'))

    def test_only_a_frozen_play_route_is_refused(self):
        frozen = evidence.route_liveness(self.trace([self.line(n, 'same') for n in range(1, 6)]))
        moving = evidence.route_liveness(self.trace([self.line(1, 'a'), self.line(2, 'b')]))
        folder = Path('checks/packed')
        evidence.require_main_route_moving('play', moving, folder)
        for scenario in ('demo', 'advanced', 'early-start', 'menu-confirm', 'pseudo-random-1'):
            evidence.require_main_route_moving(scenario, frozen, folder)   # a still title, a menu: accepted
        with self.assertRaises(ConversionError) as error:
            evidence.require_main_route_moving('play', frozen, folder)
        self.assertIn('never changed', str(error.exception))

    def delivered(self, differences):
        """replay_delivered with the compression replaced by a fake delivered file and the replay by a synthetic trace."""
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        fake = DeliveredFile(root / 'packed-game.exe', None, 'f' * 64)
        checks = [{'scenario': 'demo', 'frames': 3}, {'scenario': 'play', 'frames': 3}]
        references = {check['scenario']: {'scenario': check['scenario']} for check in checks}
        runs = []

        def replay(candidate, directory, check):
            runs.append((candidate, check['scenario']))
            (directory / f"{check['scenario']}.trace.csv").write_text(
                chr(10).join([self.HEADER] + [self.line(n, f"p{n}") for n in (1, 2, 3)]) + chr(10), encoding='ascii')
            return {'scenario': check['scenario'], 'pcm_nonzero': 7, 'visible_frames': 3}

        with patch.object(evidence, 'deliver_packed', return_value=fake):
            outcome = evidence.replay_delivered(root / 'game.exe', root / 'packed-game.exe', root / 'packed', checks,
                                                references, replay, lambda result, reference: differences(result), print)
        return fake, outcome, runs

    def test_the_delivered_file_matches_on_every_route(self):
        fake, (delivered, results), runs = self.delivered(lambda result: [])
        self.assertIs(delivered, fake)
        self.assertEqual([scenario for _, scenario in runs], ['demo', 'play'])
        self.assertEqual(fake.validation_fields(), {'packed_reference_match': True})
        self.assertEqual(fake.report_fields(), {'packed_candidate_sha256': 'f' * 64})
        self.assertEqual(results['play']['liveness']['picture_changes'], 2)
        self.assertEqual(results['play']['liveness']['pcm_nonzero'], 7)

    def test_a_difference_refuses_the_delivered_file(self):
        with self.assertRaises(ConversionError) as error:
            self.delivered(lambda result: ['frame_hash'] if result['scenario'] == 'play' else [])
        self.assertIn('Super Nintendo play: the delivered (compressed) executable differs from the fresh reference', str(error.exception))
        self.assertIn('frame_hash', str(error.exception))
        fresh = DeliveredFile(Path('x.exe'), None, '0' * 64)
        with self.assertRaises(ValueError):
            fresh.validation_fields()   # a file nobody replayed cannot claim the match


    def test_the_conversion_picks_each_machines_own_evidence_and_the_mega_drive_path_is_the_one_it_was(self):
        from retrorecomp import console16, megadrive_evidence
        replay, machine = console16.delivery_evidence('md')
        self.assertIs(replay, megadrive_evidence.replay_delivered)
        self.assertEqual(machine, 'Mega Drive')   # the text of the Mega Drive conversion log is unchanged
        replay, machine = console16.delivery_evidence('snes')
        self.assertIs(replay, evidence.replay_delivered)
        self.assertEqual(machine, 'Super Nintendo')
        source = (Path(console16.__file__)).read_text(encoding='utf-8')
        self.assertIn("if system_id in ('md', 'snes'):", source)
        self.assertIn("emit(f'{machine}: the compressed executable matches the fresh reference on every route.')", source)

if __name__ == '__main__':
    unittest.main()
