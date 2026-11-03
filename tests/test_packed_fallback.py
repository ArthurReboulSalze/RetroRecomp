"""The unpacked fallback of the packed replay (gate G5): a compressed copy that fails its replay on the system that converts
is replaced by the build as built, and every route is replayed again on it.

Fake replay callbacks and fake packing only: no ROM, no compiler, no UPX, no game process. The shared mechanism is
`delivery_evidence.replay_packed` / `_fall_back`; the registry that makes the publication leave the
build unpacked is `packing.refuse_compression`; the Neo Geo path goes through `neogeo_conversion.check_routes(delivered=...)`.
"""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retrorecomp import delivery_evidence as evidence, neogeo_conversion, packing
from retrorecomp.core import ConversionError, StopRequested
from retrorecomp.delivery_evidence import DeliveredFile, deliver_packed, replay_packed

BUILT, PACKED = b'built executable', b'packed executable'
SHA_BUILT = hashlib.sha256(BUILT).hexdigest()


class Failure(Exception):
    pass


class FallbackBase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.said = []
        self.addCleanup(packing.set_compression, packing.compression_enabled())
        self.addCleanup(packing._REPLAY_REFUSED.clear)
        self.addCleanup(packing._UNPACKED_REASONS.clear)
        packing.set_compression(True)

    def delivered(self, *, notice=None):
        """`deliver_packed` with a fake packer: the copy holds PACKED bytes (or BUILT when it stays unpacked)."""
        self.built, self.packed = self.root / 'build.exe', self.root / 'packed.exe'
        self.built.write_bytes(BUILT)

        def pack(executable, target, emit):
            Path(target).write_bytes(BUILT if notice else PACKED)
            return notice
        with patch.object(evidence, 'pack_candidate', pack):
            return deliver_packed(self.built, self.packed, 'Test', self.said.append)

    def replay_that_crashes_when_compressed(self, calls):
        """The machine's replay: it starts the delivered path; the compressed bytes stop at start, the build runs."""
        def replay(route):
            calls.append((route, self.packed.read_bytes()))
            if self.packed.read_bytes() == PACKED:
                raise Failure('exit 133 (SIGTRAP) at start')
            return route.upper()
        return replay


class FallbackTests(FallbackBase):
    def test_a_compressed_copy_that_crashes_is_replaced_by_the_build_and_all_routes_are_replayed_again(self):
        delivered, calls = self.delivered(), []
        results = replay_packed(delivered, ['a', 'b'], self.replay_that_crashes_when_compressed(calls),
                                same=lambda route, result: result == route.upper(), mismatch=Failure)
        self.assertEqual(results, ['A', 'B'])
        # One replay at a time stops at the first route that fails ('a' on the compressed copy); then every route runs
        # again, from the first, on the build; then the compressed copy is replayed once more on 'a' (it fails again: the
        # compression is at fault) and 'a' runs once more on the build so that its outputs are the build's.
        self.assertEqual(calls, [('a', PACKED), ('a', BUILT), ('b', BUILT), ('a', PACKED), ('a', BUILT)])
        self.assertFalse(delivered.aside.exists())
        self.assertEqual((delivered.kind, delivered.path.read_bytes(), delivered.sha256), ('unpacked', BUILT, SHA_BUILT))
        self.assertEqual(self.built.read_bytes(), BUILT)
        self.assertTrue(delivered.matched)
        self.assertEqual(delivered.routes, ('a', 'b'))
        self.assertEqual(delivered.validation_fields(), {'packed_reference_match': True})
        self.assertEqual(delivered.report_fields(), {'packed_candidate_sha256': SHA_BUILT})

    def test_the_notice_and_the_log_line(self):
        delivered = self.delivered()
        replay_packed(delivered, ['a'], self.replay_that_crashes_when_compressed([]))
        self.assertEqual(delivered.notice, {'notice': (
            f'The compressed copy (UPX {packing.UPX_VERSION}) did not replay correctly on this system, twice '
            '(exit 133 (SIGTRAP) at start). It is published unpacked, exactly as built and validated: a larger file, '
            'the same program.')})
        self.assertEqual(self.said, [
            'Test: comparing the compressed executable with the fresh reference.',
            'Test: the compressed copy failed its replay on this system (exit 133 (SIGTRAP) at start); '
            'replaying the unpacked build instead.'])

    def test_the_reason_is_the_first_line_of_the_error(self):
        delivered = self.delivered()

        def replay(route):
            if self.packed.read_bytes() == PACKED:
                raise Failure('first line.\nsecond line of the probe output')
        replay_packed(delivered, ['a'], replay)
        self.assertIn('(first line)', delivered.notice['notice'])
        self.assertNotIn('second line', ''.join(self.said))

    def test_a_mismatch_of_the_compressed_copy_is_retried_like_a_crash(self):
        delivered, calls = self.delivered(), []

        def replay(route):
            calls.append(self.packed.read_bytes())
            return self.packed.read_bytes()
        results = replay_packed(delivered, ['a'], replay, same=lambda route, result: result == BUILT,
                                mismatch=lambda route: Failure('differs on ' + route))
        self.assertEqual((results, calls), ([BUILT], [PACKED, BUILT, PACKED, BUILT]))
        self.assertEqual(delivered.kind, 'unpacked')
        self.assertIn('did not replay correctly', delivered.notice['notice'])

    def test_the_replays_may_run_side_by_side(self):
        delivered, calls = self.delivered(), []
        results = replay_packed(delivered, ['a', 'b', 'c'], self.replay_that_crashes_when_compressed(calls), workers=3)
        self.assertEqual(results, ['A', 'B', 'C'])
        self.assertEqual(sorted(calls), sorted([(route, PACKED) for route in 'abc'] + [(route, BUILT) for route in 'abc'] +
                                               [('a', PACKED), ('a', BUILT)]))
        self.assertEqual(delivered.kind, 'unpacked')

    def test_the_report_says_unpacked_with_the_reason(self):
        delivered = self.delivered()
        replay_packed(delivered, ['a'], self.replay_that_crashes_when_compressed([]))
        record = packing.packing_record(packing.file_identity(self.built), delivered.path, packed_replayed=True)
        self.assertFalse(record['packed'])
        self.assertEqual(record['unpacked_reason'], delivered.notice['notice'])
        self.assertIn('also unpacked', record['compared_on'])

    def test_the_publication_leaves_the_same_build_unpacked(self):
        delivered = self.delivered()
        replay_packed(delivered, ['a'], self.replay_that_crashes_when_compressed([]))
        staged, announced = self.root / 'staged.exe', []
        staged.write_bytes(BUILT)
        with patch.object(packing, 'compact_windows', side_effect=AssertionError('UPX ran')), \
                patch.object(packing, 'compact_linux', side_effect=AssertionError('UPX ran')):
            outcome = packing.compact_executable(staged, announced.append)
        self.assertEqual(outcome, delivered.notice)
        self.assertEqual(announced, [delivered.notice['notice']])
        self.assertEqual(staged.read_bytes(), BUILT)

    def test_another_build_is_still_compressed_by_the_publication(self):
        delivered = self.delivered()
        replay_packed(delivered, ['a'], self.replay_that_crashes_when_compressed([]))
        other = self.root / 'other.exe'
        other.write_bytes(b'another game')
        which = 'compact_windows' if packing.os.name == 'nt' else 'compact_linux'
        with patch.object(packing, which, return_value=None) as packer:
            self.assertIsNone(packing.compact_executable(other, lambda text: None))
        packer.assert_called_once_with(other)


class NotReproducedTests(FallbackBase):
    """A failure that is not reproduced is not blamed on the compression, and no refusal is registered."""

    def flaky(self, calls, fails=1):
        """A replay of the compressed copy that fails its first `fails` runs and then passes; the build always passes."""
        seen = []

        def replay(route):
            calls.append((route, self.packed.read_bytes()))
            if self.packed.read_bytes() == PACKED:
                seen.append(route)
                if len(seen) <= fails:
                    raise Failure('flaky host')
            return route.upper()
        return replay

    def test_a_compressed_copy_that_passes_the_second_time_raises_the_original_error_and_delivers_nothing(self):
        delivered, calls = self.delivered(), []
        with self.assertRaises(Failure) as caught:
            replay_packed(delivered, ['a', 'b'], self.flaky(calls))
        self.assertEqual(str(caught.exception), 'flaky host')
        self.assertTrue(any('could not be reproduced' in note for note in caught.exception.__notes__))
        # compressed 'a' fails; the build runs 'a' and 'b'; the compressed copy runs 'a' again and passes.
        self.assertEqual(calls, [('a', PACKED), ('a', BUILT), ('b', BUILT), ('a', PACKED)])
        self.assertIn('could not be reproduced', self.said[-1])
        self.assertIn('(non-deterministic)', self.said[-1])
        # Nothing delivered, nothing claimed, nothing registered; the compressed copy is the delivered path as before.
        self.assertEqual((delivered.kind, delivered.notice, delivered.matched), ('packed', None, False))
        self.assertEqual((delivered.path.read_bytes(), delivered.aside.exists(), delivered.sha256),
                         (PACKED, False, hashlib.sha256(PACKED).hexdigest()))
        self.assertEqual((packing._REPLAY_REFUSED, packing._UNPACKED_REASONS), ({}, {}))
        with self.assertRaises(ValueError):
            delivered.validation_fields()

    def test_the_publication_still_compresses_a_build_whose_first_failure_was_a_fluke(self):
        delivered = self.delivered()
        with self.assertRaises(Failure):
            replay_packed(delivered, ['a'], self.flaky([]))
        staged = self.root / 'staged.exe'
        staged.write_bytes(BUILT)
        which = 'compact_windows' if packing.os.name == 'nt' else 'compact_linux'
        with patch.object(packing, which, return_value=None) as packer:
            self.assertIsNone(packing.compact_executable(staged, lambda text: None))
        packer.assert_called_once_with(staged)

    def test_nothing_is_registered_before_the_confirmation(self):
        # The refusal exists only after the confirmation: during the second attempt nothing is registered yet.
        delivered, seen = self.delivered(), []

        def replay(route):
            seen.append((self.packed.read_bytes(), dict(packing._REPLAY_REFUSED)))
            if self.packed.read_bytes() == PACKED:
                raise Failure('compressed')
            return route
        replay_packed(delivered, ['a'], replay)
        self.assertEqual([refused for _, refused in seen], [{}, {}, {}, {}])
        self.assertEqual(list(packing._REPLAY_REFUSED), [SHA_BUILT])

    def test_the_first_route_that_failed_is_the_one_replayed_again(self):
        delivered, calls = self.delivered(), []

        def replay(route):
            calls.append((route, self.packed.read_bytes()))
            if self.packed.read_bytes() == PACKED and route in ('b', 'c'):
                raise Failure(route)
            return route
        for workers in (1, 3):
            packing._REPLAY_REFUSED.clear()
            packing._UNPACKED_REASONS.clear()
            delivered, calls[:] = self.delivered(), []
            replay_packed(delivered, ['a', 'b', 'c'], replay, workers=workers)
            self.assertEqual(calls[-2:], [('b', PACKED), ('b', BUILT)], workers)
            self.assertEqual(delivered.kind, 'unpacked')

    def test_a_build_that_fails_when_one_route_is_replayed_again_is_not_delivered(self):
        delivered, runs = self.delivered(), []

        def replay(route):
            if self.packed.read_bytes() == BUILT:
                runs.append(route)
                if len(runs) > 1:
                    raise Failure('build, third replay')
            if self.packed.read_bytes() == PACKED:
                raise Failure('compressed')
            return route
        with self.assertRaises(Failure) as caught:
            replay_packed(delivered, ['a'], replay)
        self.assertEqual(str(caught.exception), 'compressed')
        self.assertEqual(str(caught.exception.__cause__), 'build, third replay')
        self.assertEqual((delivered.kind, delivered.path.read_bytes(), delivered.aside.exists(), packing._REPLAY_REFUSED),
                         ('packed', PACKED, False, {}))

    def test_a_stop_while_the_compressed_copy_is_replayed_again_is_raised_as_it_is(self):
        delivered, runs = self.delivered(), []

        def replay(route):
            runs.append(self.packed.read_bytes())
            if self.packed.read_bytes() == PACKED:
                raise Failure('compressed') if runs.count(PACKED) == 1 else StopRequested('stop')
            return route
        with self.assertRaises(StopRequested):
            replay_packed(delivered, ['a'], replay)
        self.assertEqual((delivered.kind, delivered.path.read_bytes(), delivered.aside.exists(), packing._REPLAY_REFUSED),
                         ('packed', PACKED, False, {}))


class NoFallbackTests(FallbackBase):
    def test_both_copies_failing_raises_the_first_error_chained_to_the_second_and_marks_nothing_matched(self):
        delivered, calls = self.delivered(), []

        def replay(route):
            calls.append(self.packed.read_bytes())
            raise Failure('compressed' if self.packed.read_bytes() == PACKED else 'unpacked')
        with self.assertRaises(Failure) as caught:
            replay_packed(delivered, ['a', 'b'], replay)
        self.assertEqual(str(caught.exception), 'compressed')
        self.assertEqual(str(caught.exception.__cause__), 'unpacked')
        self.assertEqual(calls, [PACKED, BUILT])
        self.assertFalse(delivered.matched)
        # Nothing was claimed: the compressed copy is the delivered path again, no refusal is registered.
        self.assertEqual((delivered.kind, delivered.path.read_bytes(), delivered.aside.exists()), ('packed', PACKED, False))
        self.assertEqual((packing._REPLAY_REFUSED, packing._UNPACKED_REASONS), ({}, {}))
        with self.assertRaises(ValueError):
            delivered.validation_fields()

    def test_a_comparison_that_fails_on_both_raises_the_machines_first_error(self):
        delivered = self.delivered()
        errors = []

        def mismatch(route):
            errors.append(route)
            return Failure(f'differs on {route} #{len(errors)}')
        with self.assertRaises(Failure) as caught:
            replay_packed(delivered, ['a'], lambda route: route, same=lambda route, result: False, mismatch=mismatch)
        self.assertEqual(str(caught.exception), 'differs on a #1')
        self.assertEqual(str(caught.exception.__cause__), 'differs on a #2')
        self.assertFalse(delivered.matched)
        self.assertEqual((delivered.kind, packing._REPLAY_REFUSED), ('packed', {}))

    def test_a_compressed_copy_that_passes_is_delivered_as_it_is(self):
        delivered, calls = self.delivered(), []
        replay_packed(delivered, ['a', 'b'], lambda route: calls.append(route) or route)
        self.assertEqual(calls, ['a', 'b'])
        self.assertEqual((delivered.kind, delivered.notice, delivered.path.read_bytes()), ('packed', None, PACKED))
        self.assertEqual(self.said, ['Test: comparing the compressed executable with the fresh reference.'])
        self.assertEqual(packing._REPLAY_REFUSED, {})
        self.assertTrue(delivered.matched)

    def test_a_file_that_was_not_compressed_is_not_retried(self):
        delivered, calls = self.delivered(notice={'notice': 'UPX could not pack it'}), []

        def replay(route):
            calls.append(route)
            raise Failure('real failure')
        with self.assertRaises(Failure):
            replay_packed(delivered, ['a'], replay)
        self.assertEqual(calls, ['a'])
        self.assertEqual(delivered.notice, {'notice': 'UPX could not pack it'})
        self.assertEqual(packing._REPLAY_REFUSED, {})

    def test_with_the_option_off_nothing_is_retried(self):
        packing.set_compression(False)
        built, copy, calls = self.root / 'b.exe', self.root / 'c.exe', []
        built.write_bytes(BUILT)
        delivered = deliver_packed(built, copy, 'Test', self.said.append)
        self.assertEqual((delivered.kind, delivered.notice), ('unpacked', {'notice': packing.UNCOMPRESSED_NOTICE}))

        def replay(route):
            calls.append(route)
            raise Failure('real failure')
        with self.assertRaises(Failure):
            replay_packed(delivered, ['a'], replay)
        self.assertEqual(calls, ['a'])
        self.assertEqual(delivered.notice, {'notice': packing.UNCOMPRESSED_NOTICE})

    def test_a_delivered_file_without_its_build_is_not_retried(self):
        copy, calls = self.root / 'c.exe', []
        copy.write_bytes(PACKED)
        delivered = DeliveredFile(copy, None, 'ab' * 32)
        self.assertFalse(delivered.keep_compressed_aside(Failure('x')))

        def replay(route):
            calls.append(route)
            raise Failure('real failure')
        with self.assertRaises(Failure):
            replay_packed(delivered, ['a'], replay)
        self.assertEqual((calls, copy.read_bytes()), (['a'], PACKED))

    def test_a_stop_asked_by_the_user_is_never_retried(self):
        delivered, calls = self.delivered(), []

        def replay(route):
            calls.append(route)
            raise StopRequested('stop')
        with self.assertRaises(StopRequested):
            replay_packed(delivered, ['a'], replay)
        self.assertEqual((calls, delivered.kind, self.packed.read_bytes()), (['a'], 'packed', PACKED))

    def test_a_stop_during_the_second_attempt_is_raised_as_it_is(self):
        delivered = self.delivered()

        def replay(route):
            raise Failure('compressed') if self.packed.read_bytes() == PACKED else StopRequested('stop')
        with self.assertRaises(StopRequested):
            replay_packed(delivered, ['a'], replay)

    def test_a_copy_that_cannot_be_replaced_leaves_the_original_failure(self):
        delivered = self.delivered()

        def replay(route):
            raise Failure('compressed')
        with patch.object(evidence.shutil, 'copy2', side_effect=PermissionError('in use')):
            with self.assertRaises(Failure) as caught:
                replay_packed(delivered, ['a'], replay)
        self.assertEqual(str(caught.exception), 'compressed')
        self.assertEqual((delivered.kind, packing._REPLAY_REFUSED), ('packed', {}))


class NeoGeoPathTests(FallbackBase):
    """`check_routes(delivered=...)`: the Neo Geo packed replay goes through `replay_packed` like the other machines."""

    def project(self):
        from retrorecomp.neogeo_validation import extended_routes
        self.project_folder = self.root / 'project'
        (self.project_folder / 'native-discovery').mkdir(parents=True)
        self.routes = extended_routes('gururin', None)
        for name, (frames, _) in self.routes.items():
            (self.project_folder / 'native-discovery' / (name + '-reference.json')).write_text(
                json.dumps(self.report(frames)), encoding='utf-8')

    def write_route(self, argv, frames):
        """What a game run leaves: the report, and the per-frame trace (a moving picture, some sound) the liveness reads."""
        Path(argv[argv.index('--report') + 1]).write_text(json.dumps(self.report(frames)), encoding='utf-8')
        rows = ['frame,cpu,hardware,z80,image,pcm,samples'] + [f'{n},c,h,z,{n % 3:016x},{n % 5:016x},800' for n in range(1, 8)]
        Path(argv[argv.index('--trace') + 1]).write_text('\n'.join(rows) + '\n', encoding='ascii')

    @staticmethod
    def report(frames):
        from retrorecomp.neogeo_validation import FIELDS
        body = {'frames': frames, 'native_68000': 900, 'interpreted_68000': 12, 'native_z80': 400, 'interpreted_z80': 3,
                'nonzero_samples': 700, 'nonuniform_frames': frames, 'cpu_hash': 'c', 'ram_hash': 'r',
                'extended_hardware_hash': 'h', 'z80_hash': 'z', 'image_hash': 'i', 'pcm_hash': 'p'}
        for field in FIELDS:
            body.setdefault(field, f'v-{field}')
        return body

    def spawner(self, started):
        def spawn(argv, **kwargs):
            game = Path(argv[0])
            started.append(game.read_bytes())
            if game.read_bytes() == PACKED:
                return subprocess.CompletedProcess(argv, 133, b'', b'Trace/breakpoint trap')
            frames = int(argv[argv.index('--frames') + 1])
            self.write_route(argv, frames)
            return subprocess.CompletedProcess(argv, 0, b'', b'')
        return spawn

    def test_a_compressed_game_that_stops_at_start_is_replaced_by_the_build_and_every_route_replayed_again(self):
        self.project()
        delivered, started = self.delivered(), []
        with patch.object(neogeo_conversion, 'spawn', self.spawner(started)), \
                patch.object(neogeo_conversion, 'aes_available', lambda project: False):
            checks = neogeo_conversion.check_routes(delivered.path, self.project_folder, 'gururin', None, workers=1,
                                                    delivered=delivered)
        names = list(self.routes)
        self.assertEqual([row['name'] for row in checks], names)
        self.assertTrue(all(row['reference_match'] for row in checks))
        # One replay at a time: the compressed copy stopped on the first route; then every route ran on the build; the
        # compressed copy stopped on the first route again; the first route ran once more on the build.
        self.assertEqual(started, [PACKED] + [BUILT] * len(names) + [PACKED, BUILT])
        self.assertEqual((delivered.kind, delivered.matched), ('unpacked', True))
        self.assertEqual(delivered.path.read_bytes(), BUILT)
        self.assertIn('the compressed copy failed its replay on this system', self.said[-1])
        self.assertIn('did not replay correctly on this system', delivered.notice['notice'])
        # The conversion reads the notice after the replay and writes it into native-validation.json.
        (self.project_folder / 'native-validation.json').write_text('{}', encoding='utf-8')
        validation = neogeo_conversion.record_candidate_validation(self.project_folder, delivered.path, delivered.notice,
                                                                   checks)
        self.assertEqual((validation['validated_candidate'], validation['unpacked_sha256']), ('unpacked', SHA_BUILT))
        self.assertEqual(validation['unpacked_reason'], delivered.notice['notice'])

    def test_a_compressed_game_that_passes_is_delivered_compressed(self):
        self.project()
        delivered, started = self.delivered(), []

        def spawn(argv, **kwargs):
            started.append(Path(argv[0]).read_bytes())
            frames = int(argv[argv.index('--frames') + 1])
            self.write_route(argv, frames)
            return subprocess.CompletedProcess(argv, 0, b'', b'')
        with patch.object(neogeo_conversion, 'spawn', spawn), \
                patch.object(neogeo_conversion, 'aes_available', lambda project: False):
            checks = neogeo_conversion.check_routes(delivered.path, self.project_folder, 'gururin', None, workers=1,
                                                    delivered=delivered)
        self.assertEqual(started, [PACKED] * len(self.routes))
        self.assertEqual((delivered.kind, delivered.matched, len(checks)), ('packed', True, len(self.routes)))

    def test_a_game_that_fails_on_both_copies_raises_the_first_error(self):
        self.project()
        delivered = self.delivered()

        def spawn(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 133 if Path(argv[0]).read_bytes() == PACKED else 7, b'', b'x')
        with patch.object(neogeo_conversion, 'spawn', spawn), \
                patch.object(neogeo_conversion, 'aes_available', lambda project: False):
            with self.assertRaises(ConversionError) as caught:
                neogeo_conversion.check_routes(delivered.path, self.project_folder, 'gururin', None, workers=1,
                                               delivered=delivered)
        self.assertIsInstance(caught.exception.__cause__, ConversionError)
        self.assertNotEqual(str(caught.exception), str(caught.exception.__cause__))
        self.assertFalse(delivered.matched)

    def test_without_a_delivered_file_the_routes_are_replayed_once_as_before(self):
        self.project()
        game, started = self.root / 'game.exe', []
        game.write_bytes(PACKED)
        with patch.object(neogeo_conversion, 'spawn', self.spawner(started)), \
                patch.object(neogeo_conversion, 'aes_available', lambda project: False):
            with self.assertRaises(ConversionError):
                neogeo_conversion.check_routes(game, self.project_folder, 'gururin', None, workers=1)
        self.assertEqual(started, [PACKED])
        self.assertEqual(game.read_bytes(), PACKED)


if __name__ == '__main__':
    unittest.main()
