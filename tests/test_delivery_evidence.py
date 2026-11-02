"""The shared evidence about the delivered file: liveness (gate G8) and the packed replay (gate G5).

Synthetic rows only: no ROM, no executable, no process. The conversions' own recorded behaviour is pinned elsewhere
(tests/test_x68000_common.py and tests/test_conversion_gates.py goldens, tests/test_cps1_liveness.py,
tests/test_x68000_liveness.py); this file pins the helper on its own and that both adapters agree on one route.
"""
import random
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from retrorecomp import cps1_conversion, delivery_evidence as evidence, x68000_conversion
from retrorecomp.delivery_evidence import (DeliveredFile, FrameRow, deliver_packed, frozen_route, liveness_summary,
                                           replay_packed, replay_routes, report_fields, require_moving_picture,
                                           same_trace)
from tools.x68000_reference_check import TRACE_COLUMNS

ROOT = Path(__file__).resolve().parents[1]


class Failure(Exception):
    pass


def rows(pictures, sounds=None, *, start=1):
    return [FrameRow(start + index, picture, audible=None if sounds is None else sounds[index])
            for index, picture in enumerate(pictures)]


class LivenessSummaryTests(unittest.TestCase):
    def test_a_moving_picture_and_a_late_sound(self):
        result = liveness_summary(rows([5, 5, 6, 6, 5, 5], [False, False, False, True, True, False]))
        self.assertEqual(result, {'frames': 6, 'distinct_pictures': 2, 'picture_changes': 2, 'last_picture_change_frame': 5,
                                  'audible_frames': 2, 'last_audible_frame': 5, 'distinct_sound_blocks': None,
                                  'distinct_ram_states': None, 'distinct_program_counters': None})

    def test_every_machine_gets_the_same_keys(self):
        for given in (rows([1]), rows([1, 2], [True, False]), []):
            self.assertEqual(tuple(liveness_summary(given)), evidence.LIVENESS_KEYS)

    def test_what_the_machine_cannot_tell_is_none_not_zero(self):
        result = liveness_summary(rows([1, 2, 3]))
        self.assertIsNone(result['audible_frames'])
        self.assertIsNone(result['last_audible_frame'])
        silent = liveness_summary(rows([1, 2, 3], [False] * 3))
        self.assertEqual((silent['audible_frames'], silent['last_audible_frame']), (0, 0))

    def test_sound_blocks_ram_states_and_counters_are_counted_when_given(self):
        given = [FrameRow(0, 'a', sound='1', ram='1', pc='10'), FrameRow(1, 'b', sound='1', ram='2', pc='20'),
                 FrameRow(2, 'b', sound='1', ram='3', pc='20')]
        result = liveness_summary(given)
        self.assertEqual((result['distinct_sound_blocks'], result['distinct_ram_states'], result['distinct_program_counters']),
                         (1, 3, 2))
        self.assertEqual((result['picture_changes'], result['last_picture_change_frame']), (1, 1))   # frames count from 0 here

    def test_the_first_row_is_not_a_change_and_a_route_of_one_frame_is_frozen(self):
        one = liveness_summary(rows([7]))
        self.assertEqual((one['frames'], one['distinct_pictures'], one['picture_changes']), (1, 1, 0))
        self.assertTrue(frozen_route(one))

    def test_an_empty_route_is_frozen_and_has_no_frames(self):
        empty = liveness_summary([])
        self.assertEqual((empty['frames'], empty['distinct_pictures'], empty['picture_changes']), (0, 0, 0))
        self.assertTrue(frozen_route(empty))

    def test_rows_may_come_from_a_generator(self):
        self.assertEqual(liveness_summary(iter(rows([1, 2, 2])))['picture_changes'], 1)

    def test_a_picture_that_comes_back_is_a_change_each_time_but_one_picture_more_only_once(self):
        result = liveness_summary(rows([1, 2, 1, 2]))
        self.assertEqual((result['distinct_pictures'], result['picture_changes']), (2, 3))


class FrozenRouteTests(unittest.TestCase):
    def test_one_picture_is_frozen_two_are_not(self):
        self.assertTrue(frozen_route({'distinct_pictures': 1}))
        self.assertTrue(frozen_route({'distinct_pictures': 0}))
        self.assertFalse(frozen_route({'distinct_pictures': 2}))

    def test_the_rule_is_the_one_cps1_and_the_x68000_each_stated(self):
        """CPS-1: "no picture change"; X68000: "no more than one distinct picture". They never disagree."""
        generator = random.Random(166)
        for _ in range(500):
            pictures = [generator.randrange(3) for _ in range(generator.randrange(0, 8))]
            result = liveness_summary(rows(pictures))
            self.assertEqual(frozen_route(result), not result['picture_changes'], pictures)
            self.assertEqual(frozen_route(result), not result['distinct_pictures'] > 1, pictures)

    def test_a_frozen_route_raises_the_machines_own_error(self):
        with self.assertRaises(Failure):
            require_moving_picture(liveness_summary(rows([4, 4, 4])), Failure)
        require_moving_picture(liveness_summary(rows([4, 4, 5])), Failure)

    def test_a_record_with_only_the_common_picture_count_is_enough(self):
        # The X68000 record has no picture_changes; the rule reads distinct_pictures, which every record carries.
        with self.assertRaises(Failure):
            require_moving_picture({'distinct_pictures': 1, 'frames': 9}, Failure)


class ReportFieldsTests(unittest.TestCase):
    def test_a_machine_selects_and_renames_in_its_own_order(self):
        summary = liveness_summary(rows([1, 2], [True, False]))
        self.assertEqual(report_fields(summary, {'pictures': 'distinct_pictures', 'frames': 'frames'}),
                         {'pictures': 2, 'frames': 2})
        self.assertEqual(list(report_fields(summary, {'b': 'frames', 'a': 'distinct_pictures'})), ['b', 'a'])

    def test_an_unknown_common_key_is_refused(self):
        with self.assertRaises(KeyError):
            report_fields(liveness_summary([]), {'x': 'picture_count'})


class AdaptersAgreeTests(unittest.TestCase):
    """CPS-1 and the X68000 read different traces; for the same route they give the same common record."""

    def cps1(self, pictures, loud):
        silent = cps1_conversion.silent_sound_hash(4)
        with tempfile.TemporaryDirectory() as folder:
            trace = Path(folder) / 'trace.csv'
            lines = ['frame,cpu,ram,image,sound,samples']
            for frame, (picture, heard) in enumerate(zip(pictures, loud), 1):
                sound = 0x1234 if heard else silent
                lines.append(f'{frame},{0:016x},{0:016x},{picture:016x},{sound:016x},4')
            trace.write_text('\n'.join(lines) + '\n', encoding='ascii')
            return list(cps1_conversion.trace_rows(trace)), cps1_conversion.route_liveness(trace)

    def x68000(self, pictures):
        with tempfile.TemporaryDirectory() as folder:
            trace = Path(folder) / 'trace.tsv'
            registers = ['00000000'] * 18
            lines = ['\t'.join(TRACE_COLUMNS)]
            for frame, picture in enumerate(pictures):
                lines.append('\t'.join([str(frame), f'{picture:016x}', f'{1:016x}', f'{frame:016x}', '735', '768', '512',
                                        *registers]))
            trace.write_text('\n'.join(lines) + '\n', encoding='ascii', newline='\n')
            return list(x68000_conversion.trace_rows(trace)), x68000_conversion.route_liveness(
                Path(folder), len(pictures), {'nonblack_frames': 1, 'nonzero_samples': 2})

    def test_the_same_route_is_judged_the_same_on_both(self):
        for pictures in ([1, 1, 1, 1], [1, 1, 2, 2], [3, 4, 3, 4]):
            given_cps1, from_cps1 = self.cps1(pictures, [False, False, True, False])
            given_x68, from_x68 = self.x68000(pictures)
            self.assertEqual(from_cps1['distinct_pictures'], from_x68['distinct_pictures'])
            self.assertEqual(frozen_route(from_cps1), frozen_route(from_x68))
            self.assertEqual(liveness_summary(given_cps1)['picture_changes'],
                             liveness_summary(given_x68)['picture_changes'])
            self.assertEqual(from_cps1['audible_frames'], 1)

    def test_each_machine_keeps_its_report_fields(self):
        _, from_cps1 = self.cps1([1, 2], [True, True])
        self.assertEqual(tuple(from_cps1), ('frames', 'distinct_pictures', 'picture_changes', 'last_picture_change_frame',
                                            'audible_frames', 'last_audible_frame'))
        _, from_x68 = self.x68000([1, 2])
        self.assertEqual(tuple(from_x68), ('frames', 'distinct_pictures', 'distinct_audio_blocks', 'distinct_ram_states',
                                           'distinct_program_counters', 'nonblack_frames', 'nonzero_samples'))


class PackedReplayTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.said = []
        # A failed replay of a compressed copy falls back to the build and registers it with packing (the process-wide state).
        from retrorecomp import packing
        self.addCleanup(packing._REPLAY_REFUSED.clear)
        self.addCleanup(packing._UNPACKED_REASONS.clear)

    def delivered(self, *, notice=None, content=b'packed'):
        built, packed = self.root / 'build.exe', self.root / 'packed.exe'
        built.write_bytes(b'built')

        def pack(executable, target, emit):
            self.assertEqual(Path(executable), built)
            Path(target).write_bytes(content)
            return notice
        with patch.object(evidence, 'pack_candidate', pack):
            return deliver_packed(built, packed, 'Test', self.said.append)

    def test_the_copy_is_announced_and_its_digest_is_the_copys(self):
        import hashlib
        delivered = self.delivered()
        self.assertEqual(self.said, ['Test: comparing the compressed executable with the fresh reference.'])
        self.assertEqual(delivered.sha256, hashlib.sha256(b'packed').hexdigest())
        self.assertEqual((delivered.kind, delivered.notice, delivered.path), ('packed', None, self.root / 'packed.exe'))
        self.assertEqual((self.root / 'build.exe').read_bytes(), b'built')   # the build is never touched

    def test_a_copy_that_stays_unpacked_says_so(self):
        delivered = self.delivered(notice={'notice': 'too large'})
        self.assertEqual(self.said, ['Test: comparing the unpacked executable with the fresh reference.'])
        self.assertEqual(delivered.kind, 'unpacked')

    def test_nothing_is_claimed_before_the_replay_matched(self):
        delivered = self.delivered()
        with self.assertRaises(ValueError):
            delivered.validation_fields()
        replay_packed(delivered, ['a', 'b'], lambda route: route.upper(), same=lambda route, result: result == route.upper(),
                      mismatch=Failure)
        self.assertEqual(delivered.validation_fields(), {'packed_reference_match': True})
        self.assertEqual(delivered.report_fields(), {'packed_candidate_sha256': delivered.sha256})
        self.assertEqual(delivered.routes, ('a', 'b'))

    def test_a_mismatch_raises_the_machines_error_for_the_first_route_and_claims_nothing(self):
        delivered = self.delivered()
        ran = []

        def replay(route):
            ran.append(route)
            return route
        with self.assertRaises(Failure) as caught:
            replay_packed(delivered, ['a', 'b', 'c'], replay, same=lambda route, result: route == 'a',
                          mismatch=lambda route: Failure('differs on ' + route))
        self.assertEqual(str(caught.exception), 'differs on b')
        # Every replay ran before the judgement; the copy was compressed, so all routes ran again on the build as built
        # (tests/test_packed_fallback.py), which differs on 'b' too: the first error stands.
        self.assertEqual(ran, ['a', 'b', 'c', 'a', 'b', 'c'])
        with self.assertRaises(ValueError):
            delivered.validation_fields()

    def test_a_replay_that_raises_ends_the_check_with_the_first_failure_in_route_order(self):
        delivered = self.delivered()

        def replay(route):
            if route in ('b', 'c'):
                raise Failure(route)
            return route
        for workers in (1, 3):
            with self.assertRaises(Failure) as caught:
                replay_packed(delivered, ['a', 'b', 'c'], replay, workers=workers)
            self.assertEqual(str(caught.exception), 'b')
        self.assertFalse(delivered.matched)

    def test_a_comparison_without_its_error_is_refused_and_so_is_a_replay_without_routes(self):
        delivered = self.delivered()
        with self.assertRaises(ValueError):
            replay_packed(delivered, ['a'], lambda route: route, same=lambda route, result: True)
        with self.assertRaises(ValueError):
            replay_packed(delivered, [], lambda route: route)

    def test_results_keep_the_route_order_and_replays_run_side_by_side_when_asked(self):
        barrier = threading.Barrier(3, timeout=10)

        def replay(route):
            barrier.wait()   # three routes must be running at once for this to pass
            return route * 2
        delivered = self.delivered()
        self.assertEqual(replay_packed(delivered, ['a', 'b', 'c'], replay, workers=3), ['aa', 'bb', 'cc'])
        self.assertEqual(replay_routes(iter([1, 2, 3]), lambda route: route + 1), [2, 3, 4])

    def test_one_route_runs_in_the_calling_thread(self):
        seen = []
        replay_routes(['a'], lambda route: seen.append(threading.current_thread()), workers=4)
        self.assertEqual(seen, [threading.current_thread()])

    def test_a_machine_whose_callback_compares_records_the_match_itself(self):
        delivered = self.delivered()
        delivered.record_match(['x'])
        self.assertTrue(delivered.matched)
        with self.assertRaises(ValueError):
            self.delivered().record_match([])

    def test_same_trace_compares_bytes(self):
        one, two, three = (self.root / name for name in ('one', 'two', 'three'))
        one.write_bytes(b'abc')
        two.write_bytes(b'abc')
        three.write_bytes(b'abd')
        self.assertTrue(same_trace(one, two))
        self.assertFalse(same_trace(one, three))

    def test_a_delivered_file_can_be_built_by_hand(self):
        delivered = DeliveredFile(self.root / 'x', None, 'f' * 64)
        self.assertFalse(delivered.matched)


class AdoptionTests(unittest.TestCase):
    """No machine keeps its own copy of these steps: the sources name the helper, and the old forms are gone."""

    def source(self, name):
        return (ROOT / 'retrorecomp' / (name + '.py')).read_text(encoding='utf-8')

    def test_the_converters_call_the_shared_helpers(self):
        for module, names in (('cps1_conversion', ('liveness_summary(', 'require_moving_picture(', 'deliver_packed(',
                                                   'replay_packed(')),
                              ('x68000_conversion', ('liveness_summary(', 'require_moving_picture(', 'deliver_packed(',
                                                     'replay_packed(')),
                              ('neogeo_conversion', ('deliver_packed(', 'replay_routes(', 'replay_packed(', 'record_match('))):
            for name in names:
                self.assertIn(name, self.source(module), f'{module} should call {name}')

    def test_the_old_copies_are_gone(self):
        for module in ('cps1_conversion', 'x68000_conversion', 'neogeo_conversion'):
            text = self.source(module)
            self.assertNotIn('comparison_notice', text, module)
            self.assertNotIn('pack_candidate', text, module)
        self.assertNotIn("['picture_changes']:", self.source('cps1_conversion'))
        self.assertNotIn("['distinct_pictures']>1", self.source('x68000_conversion'))

    def test_the_module_is_owned_by_the_machines_that_own_the_gates_it_calls(self):
        from retrorecomp import compilation_inputs as inputs
        gates = {system for system in inputs.SYSTEMS if 'retrorecomp.conversion_gates' in inputs.manifest_names(system)}
        owners = {system for system in inputs.SYSTEMS if 'retrorecomp.delivery_evidence' in inputs.manifest_names(system)}
        self.assertEqual(owners, gates)
        self.assertTrue({'ng', 'x68', 'cps1'} <= owners)

    def test_the_module_ships_with_its_test(self):
        from tools.prepare_publication import PUBLIC_FILES
        self.assertIn('retrorecomp/delivery_evidence.py', PUBLIC_FILES)
        self.assertIn('tests/test_delivery_evidence.py', PUBLIC_FILES)


if __name__ == '__main__':
    unittest.main()
