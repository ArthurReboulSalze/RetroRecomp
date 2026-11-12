"""The walk of a player's own record (retrorecomp/m68k_record_walk.py), shared by the Amiga and the Atari ST, and the Atari ST's use of it, ROM-free."""
import tempfile
import unittest
from pathlib import Path

from retrorecomp import atarist_codegen, atarist_conversion
from retrorecomp.feedback import Observation
from retrorecomp.m68k_record_walk import walk_windows
from retrorecomp.systems import get_profile

TWO_WORDS = {0x203c: 3, 0x4e75: 1, 0x4e71: 1, 0x7001: 1}


class Open:
    """Apertures that accept everything."""
    @staticmethod
    def check_sample(pc, text):
        if pc & 1:
            raise ValueError('odd')


class WalkTests(unittest.TestCase):
    def walk(self, records, whole=False):
        return walk_windows(records, observed=Open, words=lambda op: TWO_WORDS.get(op, 1), stops=lambda op: op >> 12 in (0xa, 0xf), whole=whole)

    def test_the_first_instruction_ran_and_the_rest_is_walked(self):
        started, walked = self.walk([(0x1000, bytes.fromhex('70014e754e71'))])
        self.assertEqual(started, [(0x1000, '7001')])
        self.assertEqual(walked, [(0x1002, '4e75'), (0x1004, '4e71')])

    def test_a_walk_stops_at_what_never_becomes_native_code(self):
        _, walked = self.walk([(0x1000, bytes.fromhex('7001a0004e75'))])
        self.assertEqual(walked, [])

    def test_a_cut_instruction_is_kept_cut_or_left_out(self):
        data = bytes.fromhex('7001203c0000')       # MOVE.L #imm,D0 needs 6 bytes, 4 are there
        self.assertEqual(self.walk([(0x1000, data)])[1], [(0x1002, '203c0000')])
        self.assertEqual(self.walk([(0x1000, data)], whole=True)[1], [])

    def test_what_another_window_started_is_not_counted_as_walked(self):
        started, walked = self.walk([(0x1000, bytes.fromhex('70014e75')), (0x1002, bytes.fromhex('4e75'))])
        self.assertEqual(started, [(0x1000, '7001'), (0x1002, '4e75')])
        self.assertEqual(walked, [])


class AtariStRecordTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        lengths = bytearray([1]) * 65536
        lengths[0x203c] = 3
        self.lengths = bytes(lengths)
        saved = atarist_codegen._MAP
        self.addCleanup(setattr, atarist_codegen, '_MAP', saved)
        atarist_codegen._MAP = {op: ('-' if op >> 12 in (0xa, 0xf) else 'op_handler') for op in range(65536)}

    def test_the_st_walk_uses_the_decoder_lengths_and_stops_at_a_cut_instruction(self):
        observed = get_profile('atarist').observed_code
        started, walked = atarist_codegen.walk_records([(0x1000, bytes.fromhex('203c000000014e754e71203c0000'))], observed=observed, lengths=self.lengths)
        self.assertEqual(started, [(0x1000, '203c00000001')])
        self.assertEqual(walked, [(0x1006, '4e75'), (0x1008, '4e71')])
        with self.assertRaises(ValueError):
            atarist_codegen.walk_records([], observed=observed, lengths=b'\0')

    def test_a_record_of_another_tos_or_a_changed_rom_is_not_used(self):
        tos = self.folder / 'tos.img'
        image = bytes(range(256)) * 768
        tos.write_bytes(image)
        tag = int(atarist_conversion.tos_tag(tos), 16)
        observed = get_profile('atarist').observed_code
        rom_pc = atarist_conversion.TOS_BASE + 0x100
        rows = [Observation(24, 0x2000, tag, bytes.fromhex('4e71') * 8),
                Observation(24, 0x2000, tag ^ 1, bytes.fromhex('4e71') * 8),
                Observation(24, rom_pc, tag, image[0x100:0x110]),
                Observation(24, rom_pc, tag, bytes(16)),
                Observation(24, 0xFA0000, tag, bytes.fromhex('4e71') * 8)]
        kept, counts = atarist_conversion.record_windows(rows, tos, observed)
        self.assertEqual([pc for pc, _ in kept], [0x2000, rom_pc])
        self.assertEqual((counts['records_read'], counts['kept'], counts['dropped_other_tos'], counts['dropped_rom_mismatch'], counts['dropped_outside_apertures']), (5, 2, 1, 1, 1))


if __name__ == '__main__':
    unittest.main()
