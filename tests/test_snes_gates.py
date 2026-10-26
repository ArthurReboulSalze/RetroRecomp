"""Super FX qualification gates: device liveness, packing record, authored routes."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from retrorecomp import packing, snes_routes, supernintendo
from retrorecomp.core import ConversionError
from retrorecomp.random_routes import SNES_BITS, write_route


def device_check(frames=1200, picture=1200, device=1200, audible=1200, chip='superfx', mode='interpreted', **extra):
    return dict(scenario='demo', frames=frames, cartridge_chip=chip, coprocessor_mode=mode,
                last_picture_change_frame=picture, last_device_frame=device, last_audible_frame=audible, **extra)


class DeviceLiveness(unittest.TestCase):
    def test_the_stuck_prototype_is_refused(self):
        # Star Fox 2 (Japan) prototype: notice from frame ~60, device frozen, silent.
        stuck = device_check(picture=46, device=46, audible=0)
        with self.assertRaisesRegex(ConversionError, 'stopped doing anything.*after frame 46 of 1200'):
            supernintendo.validate_device_liveness([stuck])
        long_run = device_check(frames=18000, picture=60, device=60, audible=0)
        with self.assertRaises(ConversionError):
            supernintendo.validate_device_liveness([device_check(), long_run])

    def test_a_static_screen_that_keeps_its_music_is_accepted(self):
        supernintendo.validate_device_liveness([device_check(picture=46, device=46, audible=1199)])
        supernintendo.validate_device_liveness([device_check(frames=18000, picture=60, device=60, audible=17990)])

    def test_silence_with_a_moving_picture_or_device_is_accepted(self):
        supernintendo.validate_device_liveness([device_check(picture=1190, device=46, audible=0)])
        supernintendo.validate_device_liveness([device_check(picture=46, device=1100, audible=0)])

    def test_threshold_is_a_quarter_of_long_runs_and_600_frames_of_short_ones(self):
        # 12,000 frames: 3,000 quiet frames refuse, 2,999 do not.
        supernintendo.validate_device_liveness([device_check(frames=12000, picture=9001, device=0, audible=0)])
        with self.assertRaises(ConversionError):
            supernintendo.validate_device_liveness([device_check(frames=12000, picture=9000, device=0, audible=0)])
        supernintendo.validate_device_liveness([device_check(picture=601, device=0, audible=0)])
        with self.assertRaises(ConversionError):
            supernintendo.validate_device_liveness([device_check(picture=600, device=0, audible=0)])

    def test_other_cartridges_and_short_probes_are_not_checked(self):
        silent = dict(picture=0, device=0, audible=0)
        supernintendo.validate_device_liveness([device_check(chip='none', mode=None, **silent)])
        supernintendo.validate_device_liveness([device_check(chip='dsp1', mode='command_model', **silent)])
        supernintendo.validate_device_liveness([device_check(frames=1199, **silent)])
        supernintendo.validate_device_liveness([{'scenario': 'demo', 'frames': 12000}])  # ordinary game, no device fields

    def test_missing_or_malformed_evidence_never_validates(self):
        for field in supernintendo.LIVENESS_FIELDS:
            missing = device_check()
            del missing[field]
            with self.assertRaisesRegex(ConversionError, 'missing'):
                supernintendo.validate_device_liveness([missing])
            for bad in (None, True, '5', 1.5):
                with self.assertRaises(ConversionError):
                    supernintendo.validate_device_liveness([dict(device_check(), **{field: bad})])


class PackingRecord(unittest.TestCase):
    def test_records_both_identities_and_the_upx_header(self):
        with tempfile.TemporaryDirectory() as folder:
            unpacked, published = Path(folder, 'a.exe'), Path(folder, 'b.exe')
            unpacked.write_bytes(b'MZ' + b'x' * 1000)
            published.write_bytes(b'MZ' + b'UPX!' + b'y' * 100)
            record = packing.packing_record(packing.file_identity(unpacked), published)
            self.assertEqual(record['unpacked'], {'bytes': 1002, 'sha256': hashlib.sha256(unpacked.read_bytes()).hexdigest()})
            self.assertEqual(record['published']['bytes'], 106)
            self.assertEqual(record['published']['sha256'], hashlib.sha256(published.read_bytes()).hexdigest())
            self.assertTrue(record['packed'])
            self.assertEqual((record['packer'], record['version']), ('UPX', packing.UPX_VERSION))
            self.assertEqual(record['size_ratio'], round(106 / 1002, 4))
            self.assertEqual(record['compared_on'], 'unpacked build executable')
            published.write_bytes(unpacked.read_bytes())
            self.assertFalse(packing.packing_record(packing.file_identity(unpacked), published)['packed'])


class AuthoredRoutes(unittest.TestCase):
    def test_expansion_of_repeated_blocks(self):
        events = snes_routes.expand(((0, 0, 0), ('rep', 10, 20, 3, ((0, 8, 0), (4, 0, 0)))))
        self.assertEqual(events, ((0, 0, 0), (10, 8, 0), (14, 0, 0), (30, 8, 0), (34, 0, 0), (50, 8, 0), (54, 0, 0)))

    def test_invalid_events_are_rejected(self):
        for events in (((5, 0, 0), (5, 1, 0)), ((5, 0, 0), (4, 1, 0)), ((0, 70000, 0),), ((0, -1, 0),), ((0, 0.5, 0),),
                       ((True, 0, 0),), (), tuple((n, n & 1, 0) for n in range(snes_routes.LINE_LIMIT + 1))):
            with self.assertRaises(ValueError):
                snes_routes.expand(events)

    def test_the_table_is_exact_rom_data_and_valid(self):
        self.assertEqual(len(snes_routes.ROUTES), 6)
        titles = set()
        for sha, entry in snes_routes.ROUTES.items():
            self.assertRegex(sha, '^[0-9a-f]{64}$')
            (route,) = snes_routes.authored_routes(sha)
            titles.add(route.title)
            self.assertEqual((route.name, route.console, route.continues_from), ('authored', 'snes', None))
            self.assertLess(route.events[-1][0], route.frames)
            self.assertLessEqual(route.frames, 18000)
            self.assertEqual(route.events[0][:2], (0, 0))
            self.assertTrue(entry['reaches'])
            # Only the SNES pad bits are used, and the first frame releases everything.
            allowed = 0
            for bit in SNES_BITS.values():
                allowed |= bit
            self.assertTrue(all(p1 & ~allowed == 0 and p2 & ~allowed == 0 for _, p1, p2 in route.events))
        self.assertEqual(titles, {'Star Fox (USA)', 'Star Fox 2 (USA)', 'Stunt Race FX (USA)',
                                  "Super Mario World 2 - Yoshi's Island (USA)", 'Vortex (USA)', 'Dirt Racer (Europe)'})

    def test_the_prototype_and_unknown_roms_have_no_route(self):
        self.assertEqual(snes_routes.authored_routes('be4d3bd755ac6e5ac6061fa1c528f5ff5b1a1b539a44aadf4ee03168e1ff11f9'), ())
        self.assertEqual(snes_routes.authored_routes('0' * 64), ())

    def test_the_script_is_the_replay_format_and_hashes_stably(self):
        sha = 'c04d80b84514202ff319384ca20641eb0189e975eed5612915bd9c224b2ab30a'  # Stunt Race FX (USA)
        (route,) = snes_routes.authored_routes(sha)
        lines = route.script().splitlines()
        self.assertEqual(lines[0], '0 0 0')
        self.assertEqual(lines[-1], '3000 1 0')          # B held to the end: mask 1
        self.assertEqual(len(lines), 22)
        self.assertEqual(route.script_sha256(), hashlib.sha256(route.script().encode('ascii')).hexdigest())
        metadata = route.metadata()
        self.assertEqual((metadata['kind'], metadata['scenario'], metadata['frames']), ('authored', 'authored', 6000))
        self.assertEqual(metadata['script_sha256'], route.script_sha256())
        json.dumps(metadata)
        with tempfile.TemporaryDirectory() as folder:
            path = write_route(route, folder)
            self.assertEqual(path.name, 'authored-inputs.txt')
            self.assertEqual(path.read_bytes(), route.script().encode('ascii'))

    def test_a_replay_script_is_accepted_by_the_host_format_rules(self):
        # console16_main.c: strictly increasing frames, each below the scenario length.
        for sha in snes_routes.ROUTES:
            (route,) = snes_routes.authored_routes(sha)
            frames = [event[0] for event in route.events]
            self.assertEqual(frames, sorted(set(frames)))
            self.assertLess(frames[-1], route.frames)


class PackedCheckTool(unittest.TestCase):
    def test_routes_are_regenerated_from_the_report_and_must_match_it(self):
        from tools import snes_packed_check
        sha = 'c04d80b84514202ff319384ca20641eb0189e975eed5612915bd9c224b2ab30a'
        (route,) = snes_routes.authored_routes(sha)
        report = {'rom': {'sha256': sha}, 'advanced_scan': {'long_routes': [], 'authored_routes': [route.metadata()]}}
        with tempfile.TemporaryDirectory() as folder:
            scripts = snes_packed_check.route_scripts(report, Path(folder))
            self.assertEqual(Path(scripts['authored']).read_text(), route.script())
            report['advanced_scan']['authored_routes'][0]['script_sha256'] = '0' * 64
            with self.assertRaises(SystemExit):
                snes_packed_check.route_scripts(report, Path(folder))

    def test_random_route_seed_must_match(self):
        from tools import snes_packed_check
        from retrorecomp.random_routes import long_routes
        sha = '1' * 64
        (route,) = long_routes('snes', sha, count=1, frames=18000)
        entry = route.metadata()
        report = {'rom': {'sha256': sha}, 'advanced_scan': {'long_routes': [entry]}}
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(set(snes_packed_check.route_scripts(report, Path(folder))), {'long-1'})
            entry['seed'] = 'other'
            with self.assertRaises(SystemExit):
                snes_packed_check.route_scripts(report, Path(folder))

    def test_report_is_found_beside_the_executable(self):
        from tools import snes_packed_check
        with tempfile.TemporaryDirectory() as folder:
            reports = Path(folder, 'datas', 'reports', 'Game-1')
            reports.mkdir(parents=True)
            (reports / 'conversion-report.json').write_text('{}')
            self.assertEqual(snes_packed_check.find_report(Path(folder, 'Game.exe'), None),
                             reports / 'conversion-report.json')
            with self.assertRaises(SystemExit):
                snes_packed_check.find_report(Path(folder, 'x', 'Game.exe'), None)


if __name__ == '__main__':
    unittest.main()
