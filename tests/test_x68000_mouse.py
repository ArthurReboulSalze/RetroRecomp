"""X68000 mouse games: a reviewed list, then the IOCS mouse reads their code makes."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retrorecomp.x68000 import MOUSE_LIST, listed_mouse, mouse_reads


def record(*rows):
    return {'schema': 1, 'truncated': False,
            'variants': [{'pc': pc, 'words': words, 'hits': hits} for pc, words, hits in rows]}


class MouseReadTests(unittest.TestCase):
    def test_executed_mouse_reads_are_counted_on_the_trap(self):
        # moveq #_MS_GETDT,d0 ; trap #15, run 40 times.
        self.assertEqual(mouse_reads(record((0x8000, '7074', 40), (0x8002, '4e4f', 40))), (True, 40))
        # _MS_CURGT and _MS_ONTM read the mouse too.
        self.assertEqual(mouse_reads(record((0x8000, '7075', 3), (0x8002, '4e4f', 3),
                                            (0x9000, '7079', 1), (0x9002, '4e4f', 1))), (True, 4))

    def test_a_games_own_driver_on_the_mouse_serial_channel_counts(self):
        # lea $E98001,a0 in RAM, as Cameltry does, and move.b $E98003,d0.
        self.assertEqual(mouse_reads(record((0x8bfd2, '41f900e98001', 70), (0x8c000, '103900e98003', 5))), (True, 75))
        # Word accesses, as Lemmings and Populous: move.w $E98002,d0 and
        # move.w #$38,$E98000.
        self.assertEqual(mouse_reads(record((0x35428, '303900e98002', 12), (0x35450, '33fc003800e98000', 12))), (True, 24))
        # The IPL's own handler in ROM, the RS-232C channel A and digits that
        # only line up across word boundaries are not a game reading the mouse.
        self.assertEqual(mouse_reads(record((0xff1000, '41f900e98001', 9))), (False, 0))
        self.assertEqual(mouse_reads(record((0x8000, '41f900e98005', 9), (0x9000, '103900e98007', 9))), (False, 0))
        self.assertEqual(mouse_reads(record((0x8000, '4e700e98001e', 9))), (False, 0))

    def test_loaded_code_that_has_not_run_is_only_present(self):
        # Static expansion records reachable code with no hits.
        self.assertEqual(mouse_reads(record((0x8000, '7074', 0), (0x8002, '4e4f', 0))), (True, 0))

    def test_hiding_the_pointer_or_other_calls_is_not_a_mouse_game(self):
        # _MS_INIT and _MS_CUROF hide the pointer in most games; _JOYGET is the joystick.
        for call in ('7070', '7072', '703b', '7174'):
            self.assertEqual(mouse_reads(record((0x8000, call, 9), (0x8002, '4e4f', 9))), (False, 0), call)
        # A mouse call number not followed by the IOCS trap is ordinary data movement.
        self.assertEqual(mouse_reads(record((0x8000, '7074', 9), (0x8002, '4e75', 9))), (False, 0))


class MouseListTests(unittest.TestCase):
    def test_the_shipped_list_names_exact_sets_and_no_paths(self):
        from retrorecomp.paths import ASSETS
        data = json.loads((ASSETS / MOUSE_LIST).read_text(encoding='utf-8'))
        self.assertEqual(data['schema'], 1)
        for identity, entry in data['games'].items():
            self.assertRegex(identity, r'^[0-9a-f]{64}$')
            self.assertEqual(set(entry), {'title', 'mouse'})
            self.assertIsInstance(entry['mouse'], bool)
            self.assertTrue(entry['title'] and '/' not in entry['title'] and '\\' not in entry['title'])
        games = data['games']
        # The two sets the former exact-hash rule covered keep their controls.
        self.assertTrue(games['24bf876f9d31a622313c4e6fb0f4c8134259c11e1dd0fea28124a44498c797e3']['mouse'])
        self.assertTrue(games['06ae8a805f2826bf049febf54aa2734760ac893f95620ee30dcb6c7a60271215']['mouse'])
        sight = [entry for entry in games.values() if entry['title'] == 'Metal Sight']
        self.assertEqual(sight, [{'title': 'Metal Sight', 'mouse': False}])


    def test_only_reviewed_exact_sets_are_listed(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            set_of = lambda value: SimpleNamespace(sha256=value * 64)
            with patch('retrorecomp.x68000.ASSETS', root):
                self.assertIsNone(listed_mouse(set_of('a')))
                path = root / MOUSE_LIST
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({'schema': 1, 'games': {
                    'a' * 64: {'title': 'Pointer', 'mouse': True},
                    'b' * 64: {'title': 'Shooter', 'mouse': False},
                    'c' * 64: {'title': 'Unclear', 'mouse': 'yes'}}}), encoding='utf-8')
                self.assertIs(listed_mouse(set_of('a')), True)
                self.assertIs(listed_mouse(set_of('b')), False)
                self.assertIsNone(listed_mouse(set_of('c')))
                self.assertIsNone(listed_mouse(set_of('d')))
                path.write_text('not json', encoding='utf-8')
                self.assertIsNone(listed_mouse(set_of('a')))


if __name__ == '__main__':
    unittest.main()
