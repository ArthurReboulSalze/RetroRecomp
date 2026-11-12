"""The walk of a player's own record (retrorecomp/m68k_record_walk.py), shared by the Amiga and the Atari ST, and the Atari ST's use of it, ROM-free."""
import tempfile
import unittest
from pathlib import Path

from retrorecomp import atarist_codegen, atarist_conversion
from retrorecomp.feedback import Observation
from retrorecomp.m68k_record_walk import falls_through, static_target, sweep_images, walk_windows
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


SWEEP_WORDS = {0x6000: 2, 0x6600: 2, 0x51c8: 2, 0x4eb9: 3, 0x4ef8: 2, 0x4efa: 2, 0x203c: 3}


class Low:
    """Apertures that accept an even address below $400."""
    @staticmethod
    def check_sample(pc, text):
        if pc & 1 or pc >= 0x400:
            raise ValueError('outside')


class SweepTests(unittest.TestCase):
    def image(self, **places):
        """One image: RAM of 0x1000 bytes with the given instructions (hex text) at the given addresses (keys 'at_<hex address>')."""
        ram = bytearray(0x1000)
        for key, text in places.items():
            data = bytes.fromhex(text)
            start = int(key[3:], 16)
            ram[start:start + len(data)] = data
        return [(0, bytes(ram))]

    def sweep(self, roots, images, **options):
        arguments = dict(observed=Open, words=lambda op: SWEEP_WORDS.get(op, 1), stops=lambda op: op == 0 or op >> 12 in (0xa, 0xf), target=static_target, falls=falls_through, limit=1000)
        arguments.update(options)
        return sweep_images(roots, images, **arguments)

    def test_each_kind_of_target_is_followed_and_what_does_not_fall_through_is_not(self):
        # BRA.S +4 -> $106 (no fall-through); Bcc.W -> $112 and on to $104; DBF -> $fe and on to $104; JSR (xxx).L -> $300 and on to $106; JMP (xxx).W -> $400; JMP (d16,PC) -> $112; RTS.
        cases = [('6004', {'at_102': '4e71', 'at_106': '7001'}, [(0x106, '7001')]),
                 ('66000010', {'at_104': '4e71', 'at_112': '7001'}, [(0x104, '4e71'), (0x112, '7001')]),
                 ('51c8fffc', {'at_fe': '7001', 'at_104': '4e71'}, [(0xfe, '7001'), (0x104, '4e71')]),
                 ('4eb900000300', {'at_300': '7001', 'at_106': '4e71'}, [(0x106, '4e71'), (0x300, '7001')]),
                 ('4ef80400', {'at_400': '7001', 'at_104': '4e71'}, [(0x400, '7001')]),
                 ('4efa0010', {'at_112': '7001', 'at_104': '4e71'}, [(0x112, '7001')]),
                 ('4e75', {'at_102': '4e71'}, [])]
        for text, places, expected in cases:
            with self.subTest(text=text):
                places['at_100'] = text
                found, info = self.sweep([(0x100, text)], [self.image(**places)])
                self.assertEqual(found, expected)
                self.assertEqual((info['roots'], info['stale_roots'], info['capped']), (1, 0, False))

    def test_an_odd_target_a_stop_and_an_aperture_end_a_path(self):
        found, _ = self.sweep([(0x100, '6003')], [self.image(at_100='6003', at_105='7001', at_102='4e71')])
        self.assertEqual(found, [])                                    # BRA.S to an odd address, and BRA does not fall through
        found, _ = self.sweep([(0x100, '4e71')], [self.image(at_100='4e71', at_102='a000', at_104='7001')])
        self.assertEqual(found, [])                                    # line A stops the path
        found, _ = self.sweep([(0x100, '4ef80800')], [self.image(at_100='4ef80800', at_800='7001')], observed=Low)
        self.assertEqual(found, [])                                    # the target is outside the apertures: not kept
        found, _ = self.sweep([(0x100, '4ef80200')], [self.image(at_100='4ef80200', at_200='7001')], observed=Low)
        self.assertEqual(found, [(0x200, '7001')])

    def test_a_root_is_used_only_where_the_image_still_holds_what_was_observed(self):
        found, info = self.sweep([(0x100, '6004'), (0x200, '4e71')], [self.image(at_100='4e71', at_106='7001', at_200='4e71', at_202='7001')])
        self.assertEqual(found, [(0x202, '7001')])
        self.assertEqual((info['roots'], info['stale_roots']), (1, 1))

    def test_what_is_observed_or_known_is_not_found_again_and_the_first_image_keeps_an_instruction(self):
        first, second = self.image(at_100='4e71', at_102='203c00000001'), self.image(at_100='4e71', at_102='203c00000002', at_108='7001')
        found, info = self.sweep([(0x100, '4e71')], [first, second], known=[(0x108, '7001')])
        self.assertEqual(found, [(0x102, '203c00000001')])
        self.assertEqual((info['images'], info['added']), (2, 1))
        found, _ = self.sweep([(0x100, '4e71'), (0x102, '203c00000009')], [first])
        self.assertEqual(found, [])                                    # same pc and opcode as an observed one: left out

    def test_the_cap_is_exact_and_told(self):
        image = self.image(at_100='4e71' * 40)
        found, info = self.sweep([(0x100, '4e71')], [image], limit=5)
        self.assertEqual(len(found), 5)
        self.assertEqual((info['added'], info['limit'], info['capped']), (5, 5, True))
        self.assertGreater(info['left_at_cap'], 0)
        found, info = self.sweep([(0x100, '4e71')], [image])           # 39 more NOPs follow the root, then zero words
        self.assertEqual((len(found), info['capped'], info['left_at_cap']), (39, False, 0))
        found, info = self.sweep([(0x100, '4e71')], [image], limit=39)
        self.assertEqual(len(found), 39)

    def test_a_sweep_is_deterministic(self):
        image = self.image(at_100='66000010', at_104='4e71', at_112='7001', at_114='4e75', at_200='4eb900000300', at_300='7001')
        roots = [(0x200, '4eb900000300'), (0x100, '66000010')]
        self.assertEqual(self.sweep(roots, [image]), self.sweep(list(reversed(roots)), [image]))

    def test_page_fill_only_when_asked_and_only_in_pages_where_code_ran(self):
        image = self.image(at_100='4e75', at_800='7001', at_802='4e71')
        roots = [(0x100, '4e75')]
        self.assertEqual(self.sweep(roots, [image], page_bits=11)[0], [])
        found, info = self.sweep(roots, [image], fill=True, page_bits=11)
        self.assertEqual((found, info['added_by_fill']), ([], 0))      # with 2 KiB pages the code at $800 is in a page nobody ran in
        found, info = self.sweep(roots, [image], fill=True, page_bits=12)
        self.assertEqual(found, [(0x800, '7001'), (0x802, '4e71')])
        self.assertEqual(info['added_by_fill'], 2)
        found, _ = self.sweep(roots, [image], fill=True, page_bits=12, fill_below=0x100)
        self.assertEqual(found, [])
        self.assertTrue(self.sweep(roots, [image], fill=True, page_bits=12, limit=1)[1]['capped'])

    def test_targets_and_fall_through_helpers(self):
        self.assertEqual(static_target(0x1000, [0x6000, 0x0010]), 0x1012)
        self.assertEqual(static_target(0x1000, [0x61fc]), 0xffe)
        self.assertIsNone(static_target(0x1000, [0x60ff]))             # displacement $ff is a long one only on the 68020
        self.assertIsNone(static_target(0x1000, [0x4e90]))             # JSR (A0): a register
        self.assertIsNone(static_target(0x1000, [0x6000]))             # the extension word is missing
        self.assertEqual(static_target(0x1000, [0x4eb9, 0x0001, 0x0002]), 0x10002)
        self.assertEqual([falls_through(op) for op in (0x6000, 0x6600, 0x4ef9, 0x4eb9, 0x4e75, 0x4e73, 0x4e77, 0x4e72, 0x4afc, 0x4e71)],
                         [False, True, False, True, False, False, False, False, False, True])


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

    def test_the_images_of_the_sweep_are_the_routes_ram_and_the_tos_and_the_memory_files_are_deleted_once_read(self):
        tos = self.folder / 'tos.img'
        tos.write_bytes(b'\x4e\x71' * 4)
        for name in ('one', 'two', 'none'):
            (self.folder / name).mkdir()
        (self.folder / 'one' / atarist_conversion.MEMORY_IMAGE).write_bytes(b'\x01' * 16)
        (self.folder / 'two' / atarist_conversion.MEMORY_IMAGE).write_bytes(b'\x02' * 16)
        images = atarist_conversion.sweep_images([self.folder / 'one', self.folder / 'none', self.folder / 'two'], tos)
        self.assertEqual([image[0][1][:1] for image in images], [b'\x01', b'\x02'])        # routes in order, a run without an image leaves none
        self.assertEqual([image[1] for image in images], [(atarist_conversion.TOS_BASE, b'\x4e\x71' * 4)] * 2)
        self.assertFalse(list(self.folder.glob('*/' + atarist_conversion.MEMORY_IMAGE)))   # nothing of the game's memory is kept

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
