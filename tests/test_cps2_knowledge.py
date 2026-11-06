"""CPS-2 in the shared base: the CPS-1's logic with the board as a keyword (`cps1_knowledge`, `cps2_knowledge`), numbers only.

The CPS-2 is the experimental tier of the base like the CPS-1: its paths are tied to the engine that validated them, carry a format
number, and the sharing can be withdrawn with one line. A CPS-2 record points into the decrypted program image; no key, no ROM byte,
no RAM word and no code is in it.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp import cps1_knowledge, cps2_catalogue, cps2_knowledge, knowledge, path_profiles as pp
from tests.test_cps1_knowledge import IDENTITY, MOVE_D0, Z80_OP, fresh, images, lengths, window


class RecordTests(unittest.TestCase):
    def promoted(self):
        record, counts = cps2_knowledge.promote(IDENTITY, images(), fresh([window(MOVE_D0)], [{'address': 0xd010, 'bytes': Z80_OP.hex() + 'aaaa'}]),
                                                lengths())
        return record, counts

    def test_a_record_names_the_board_its_maps_and_its_engine(self):
        record, counts = self.promoted()
        self.assertEqual(record['game'], f'cps2:{IDENTITY}')
        self.assertEqual(record['identity']['system'], 'cps2')
        self.assertEqual((record['cpus']['m68k']['map'], record['cpus']['z80']['map']), ('cps2', 'cps2-sound'))
        self.assertEqual(counts['paths'], {'m68k_ram': 1, 'z80_ram': 1})
        self.assertEqual(cps2_knowledge.record_engine(record), cps2_knowledge.engine())
        self.assertNotEqual(cps2_knowledge.engine(), cps1_knowledge.engine())             # another board, another engine identity
        text = json.dumps(record)
        self.assertNotIn(MOVE_D0.hex(), text)                                               # numbers only: no instruction bytes
        self.assertEqual(cps2_knowledge.validate_record(record, IDENTITY), record)
        pp.validate_game(record)                                                           # the schema 3 validator accepts it

    def test_the_two_boards_do_not_read_each_others_records(self):
        record, _ = self.promoted()
        other, _ = cps1_knowledge.promote(IDENTITY, images(), fresh([window(MOVE_D0)]), lengths())
        with self.assertRaisesRegex(ValueError, 'Not a CPS-2 record'):
            cps2_knowledge.validate_record(other, IDENTITY)
        with self.assertRaisesRegex(ValueError, 'Not a CPS-1 record'):
            cps1_knowledge.validate_record(record, IDENTITY)
        self.assertIsNone(cps2_knowledge.salvaged_record(IDENTITY, other))
        self.assertEqual(cps2_knowledge.salvaged_record(IDENTITY, record), record)
        # an unknown format is skipped by name, never refused as a whole
        future = json.loads(json.dumps(record))
        future['identity']['layout']['format'] = 2
        with self.assertRaises(cps2_knowledge.UnknownFormat):
            cps2_knowledge.validate_record(future, IDENTITY)

    def test_the_rows_expand_only_for_the_images_they_were_made_from(self):
        record, _ = self.promoted()
        expanded = cps2_knowledge.expanded_rows(record, images())
        self.assertEqual(expanded['m68k_ram'][0]['words'], MOVE_D0.hex())
        changed = dict(images(), maincpu=bytes(len(images()['maincpu'])))
        with self.assertRaisesRegex(ValueError, 'CPS-2 hints are for other images'):
            cps2_knowledge.expanded_rows(record, changed)
        rows, info = cps2_knowledge.shared_rows(IDENTITY, images(), qualified=record, imported=None, library=record)
        self.assertEqual(info['qualified'], 2)
        self.assertEqual(len(rows['m68k_ram']), 2)                                          # the two sources give the same row twice, as for the CPS-1
        # a qualified record of another engine is ignored; the CPS-1's own record is not a CPS-2 record
        other_engine = json.loads(json.dumps(record))
        other_engine['cpus']['m68k']['core'] = 'f' * 40
        _, info = cps2_knowledge.shared_rows(IDENTITY, images(), qualified=other_engine)
        self.assertEqual(info['ignored'], {'qualified': 'another engine revision'})

    def test_a_union_of_two_records_of_one_romset_keeps_every_path(self):
        first, _ = self.promoted()
        second, _ = cps2_knowledge.promote(IDENTITY, images(), fresh([], [{'address': 0xd020, 'bytes': Z80_OP.hex() + 'bbbb'}]), lengths())
        both = cps2_knowledge.merged(IDENTITY, first, second)
        self.assertEqual(len(cps2_knowledge.entry_set(both)), 3)             # the 68000 row and the two sound rows

    def test_the_program_image_of_a_cps2_is_the_decrypted_one(self):
        game = cps2_catalogue.by_set()['ssf2']
        with tempfile.TemporaryDirectory() as folder:
            board = Path(folder)
            (board / 'maincpu.bin').write_bytes(b'\x11' * 64)
            (board / 'maincpu-op.bin').write_bytes(b'\x22' * 64)
            (board / 'audiocpu.bin').write_bytes(b'\x33' * 64)
            self.assertEqual(cps2_knowledge.images_from_board(board, game)['maincpu'], b'\x22' * 64)
            self.assertEqual(cps1_knowledge.images_from_board(board, game)['maincpu'], b'\x11' * 64)

    def test_the_library_record_is_read_from_the_cps2_folder(self):
        record, _ = self.promoted()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'RETRO_RECOMP_LIBRARY_DIR': folder}):
            from retrorecomp.library import library_root
            memory = library_root('cps2') / IDENTITY
            memory.mkdir(parents=True)
            (memory / 'compilation.json').write_text(json.dumps({'system': 'cps2', 'source_identity': IDENTITY, 'fresh_reference_passed': True,
                                                                 'record': record}), encoding='utf-8')
            self.assertEqual(cps2_knowledge.library_record(IDENTITY), record)
            self.assertIsNone(cps1_knowledge.library_record(IDENTITY))                      # the CPS-1 library holds nothing of the CPS-2


class SharingTests(unittest.TestCase):
    def test_the_machine_is_in_the_base_as_an_experimental_one_that_can_be_withdrawn(self):
        self.assertIn('cps2', pp.EXPERIMENTAL_SHARED)
        self.assertIn('cps2', pp.WITHDRAWABLE)
        self.assertIs(knowledge.schema3_module('cps2'), cps2_knowledge)
        self.assertTrue(pp.game_key().fullmatch(f'cps2:{IDENTITY}'))
        with patch.object(pp, 'SHARED_SYSTEMS', tuple(s for s in pp.SHARED_SYSTEMS if s != 'cps2')):
            self.assertIsNone(knowledge.schema3_module('cps2'))                             # the one-line switch


if __name__ == '__main__':
    unittest.main()
