"""The Amstrad CPC's keyboard as the converter types it (retrorecomp/cpc_keys.py) against the adapter's table
(native/hostkit/adapters/rrhk_cpc_keys.h), and the boot key sequence it writes."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

from retrorecomp import cpc_keys

ROOT = Path(__file__).resolve().parents[1]


class KeyTableTests(unittest.TestCase):
    def test_the_converters_table_is_the_adapters(self):
        header = (ROOT / 'native/hostkit/adapters/rrhk_cpc_keys.h').read_text(encoding='utf-8')
        pairs = {int(scancode): name for scancode, name in re.findall(r'\{\s*(\d+),\s*CPC_KEY_(\w+)\s*\}', header)}
        self.assertEqual(pairs, cpc_keys.HOST_TO_CPC)
        keys = set(re.findall(r'CPC_KEY_(\w+)\s*=', (ROOT / 'native/cpc_machine/cpc_ppi.h').read_text(encoding='utf-8')))
        self.assertLessEqual(set(cpc_keys.HOST_TO_CPC.values()), keys)
        self.assertTrue(all(4 <= scancode <= 100 or 224 <= scancode <= 231 for scancode in cpc_keys.HOST_TO_CPC),
                        'only the keys of the session set (hostkit_session.h)')

    def test_every_character_is_typed_by_a_mapped_key(self):
        for character, (cpc_key, _) in cpc_keys.CHARACTERS.items():
            with self.subTest(character=character):
                self.assertIn(cpc_key, cpc_keys.HOST_TO_CPC.values())


class SequenceTests(unittest.TestCase):
    def test_bomb_jacks_start_command(self):
        text = cpc_keys.start_text('RUN"BOMB')
        self.assertEqual(text, 'RUN"BOMB\n')
        self.assertEqual(cpc_keys.boot_sequence(text), ((21, False), (24, False), (17, False), (31, True), (5, False),
                                                        (18, False), (16, False), (5, False), (40, False)))

    def test_cpm_and_undecided_disks(self):
        self.assertEqual(cpc_keys.boot_sequence(cpc_keys.start_text('|CPM'))[0], (47, True))   # | is Shift + @
        self.assertEqual(cpc_keys.start_text(None), '')
        self.assertIn('0, 0 };', cpc_keys.boot_keys_header(''))

    def test_a_character_with_no_key_is_refused(self):
        for character in ('é', '£', '~', '\t'):
            with self.subTest(character=character), self.assertRaises(ValueError):
                cpc_keys.boot_sequence('RUN"' + character)

    def test_the_header(self):
        header = cpc_keys.boot_keys_header('RUN"BOMB\n', start_frame=150)
        self.assertIn('#include "rrhk_boot_keys.h"', header)
        self.assertIn('{ 31, 1 }', header)
        self.assertIn('= { 150, 2, 2, 9, rr_boot_key_list };', header)
        self.assertIn('/* "RUN\\"BOMB\\n" */', header)
        with self.assertRaises(ValueError):
            cpc_keys.boot_keys_header('RUN', hold=0)


if __name__ == '__main__':
    unittest.main()
