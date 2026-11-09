"""Atari ST saves and states (gates G7 and G6): the ROM-free, compiler-free parts of tools/atarist_saves_check.py and of the routes.

The check itself builds the machine and runs it in separate processes: `python -B tools/atarist_saves_check.py` (BUILDING.md)."""
import importlib.util
from pathlib import Path
import unittest

from retrorecomp import atarist_conversion, atarist_disk

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('atarist_saves_check', ROOT / 'tools' / 'atarist_saves_check.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class AuthoredDiskTests(unittest.TestCase):
    def test_the_ipf_written_for_the_check_holds_the_sectors_the_program_reads(self):
        sectors = atarist_disk.ipf_sectors(check.ipf_image())
        self.assertEqual(sorted(k[2] for k in sectors if k[:2] == (0, 0)), list(range(1, 10)))
        self.assertEqual(sectors[(check.SECTOR_TRACK, 0, check.SECTOR_NUMBER)][0], check.ORIGINAL)
        self.assertEqual(sectors[(1, 1, 1)], check._sector_data(200, 1))

    def test_every_track_of_the_ipf_is_a_full_revolution(self):
        for track in range(2):
            cells = sum(check._cells(block) for block in check._track_blocks(track, 0))
            self.assertEqual(cells, 100000)

    def test_the_st_image_gives_the_same_sector(self):
        self.assertEqual(atarist_disk.st_sectors(check.st_image())[(0, 0, check.SECTOR_NUMBER)][0], check.ORIGINAL)

    def test_the_authored_tos_starts_the_program(self):
        tos = check.authored_tos()
        self.assertEqual(len(tos), check.TOS_BYTES)
        self.assertEqual(tos[2:4], b'\x01\x04')
        self.assertEqual(int.from_bytes(tos[4:8], 'big'), 0xfc0020)
        self.assertEqual(tos[0x20:0x28], check.move_b(0x05, 0xff8001))


class RealGameRouteTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('atarist_saves_game', ROOT / 'tools' / 'atarist_saves_game.py')
        self.game = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.game)

    def test_a_typed_text_is_one_short_key_after_another_and_return_ends_it(self):
        events = self.game.typed(100, 'ab|')
        self.assertEqual([e[3] for e in events], [ord('a'), ord('b'), 13])
        self.assertEqual(events[1][0] - events[0][0], self.game.KEY_GAP)
        self.assertTrue(all(begin < end and kind == 'key' for begin, end, kind, _, _ in events))

    def test_the_routes_stay_inside_their_frames_and_keep_no_game_byte(self):
        for route in (self.game.save_route(1500), self.game.restore_route(1500)):
            events, frames = route
            self.assertLessEqual(max(end for _, end, _, _, _ in events), frames)
            self.assertTrue(all(isinstance(value, int) for event in events for value in (event[0], event[1], event[3], event[4])))


class LongRouteTests(unittest.TestCase):
    def test_a_route_is_fixed_by_the_exact_game_and_changes_with_it(self):
        self.assertEqual(atarist_conversion.long_route('a' * 64, 0, 18000, 1), atarist_conversion.long_route('a' * 64, 0, 18000, 1))
        self.assertNotEqual(atarist_conversion.long_route('a' * 64, 0, 18000, 1), atarist_conversion.long_route('b' * 64, 0, 18000, 1))
        self.assertNotEqual(atarist_conversion.long_route('a' * 64, 0, 18000, 1), atarist_conversion.long_route('a' * 64, 1, 18000, 1))

    def test_a_route_stays_inside_what_the_player_reads(self):
        for disks in (1, 3):
            events = atarist_conversion.long_route('c' * 64, 1, 18000, disks)
            self.assertLessEqual(len(events), 4096)
            for begin, end, kind, code, value in events:
                self.assertLess(begin, end)
                self.assertLessEqual(end, 18000 + 200)
                self.assertIn(kind, ('joy', 'mouse', 'key', 'disk'))
                if kind == 'joy':
                    self.assertIn(code, range(5))
                if kind == 'mouse':
                    self.assertIn(code, range(4))
                if kind == 'disk':
                    self.assertIn(code, range(disks))

    def test_only_the_second_route_of_a_game_of_several_disks_changes_disk_once(self):
        self.assertFalse([e for e in atarist_conversion.long_route('d' * 64, 0, 18000, 1) if e[2] == 'disk'])
        self.assertFalse([e for e in atarist_conversion.long_route('d' * 64, 1, 18000, 1) if e[2] == 'disk'])
        self.assertFalse([e for e in atarist_conversion.long_route('d' * 64, 0, 18000, 2) if e[2] == 'disk'])
        changes = [e for e in atarist_conversion.long_route('d' * 64, 1, 18000, 2) if e[2] == 'disk']
        self.assertEqual(len(changes), 1)
        self.assertEqual((changes[0][0] >= 9000, changes[0][3]), (True, 1))


class ContinuationTests(unittest.TestCase):
    def test_a_state_is_compared_on_every_column_sound_included(self):
        self.assertEqual(atarist_conversion.CONTINUATION_IGNORED, ())


if __name__ == '__main__':
    unittest.main()
