"""The Agnus and Denise self-test, the parts that need neither a compiler nor a ROM: the 68000 forms its scenarios use, that a scenario
is the same for the same seed and stays inside its own memory, the boot ROM, and that the comparison of two records finds and places a
difference. `tools/amiga_display_selftest.py` builds `native/amiga_machine/amiga_display_checks.cpp` and runs the scenarios."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import amiga_display_selftest as selftest  # noqa: E402


class AssemblerTests(unittest.TestCase):
    def test_the_forms_encode_as_the_68000_reads_them(self):
        a = selftest.Assembler(0x1000)
        a.move_w_imm_abs(0x1234, 0xDFF180)
        a.moveq(5, 7)
        top = a.here
        a.dbra(7, top)
        a.wait_line(0x40)
        a.wait_blitter()
        a.bra_w(0x1000)
        a.move_w_abs_d(0xDFF006, 2)
        a.move_l_imm_abs(0x12345678, 0x20)
        self.assertEqual(' '.join(f'{w:04x}' for w in a.words),
                         '33fc 1234 00df f180 7e05 51cf fffe 3c39 00df f006 e04e 0c46 0040 65f2 0839 0006 00df f002 66f6 6000 ffd8 '
                         '3439 00df f006 23fc 1234 5678 0000 0020')

    def test_the_boot_rom_quiets_the_machine_then_enters_the_program(self):
        rom = selftest.boot_rom()
        self.assertEqual(len(rom), 512 * 1024)
        self.assertEqual(struct.unpack('>4H', rom[:8]), (0x1114, 0x4EF9, 0x00F8, 0x00D2))
        self.assertIn(struct.pack('>HI', 0x4EF9, selftest.PROGRAM), rom[0xD2:0x200])


class ScenarioTests(unittest.TestCase):
    def test_a_seed_gives_the_same_scenario(self):
        self.assertEqual(selftest.generate(7).regions, selftest.generate(7).regions)
        self.assertNotEqual(selftest.generate(7).regions, selftest.generate(8).regions)

    def test_every_region_lies_inside_chip_ram_and_none_overlaps(self):
        for seed in range(20):
            spans = sorted((address, address + len(data)) for address, data in selftest.generate(seed).regions)
            self.assertLessEqual(spans[-1][1], selftest.CHIP_KB * 1024)
            for (_, end), (start, _) in zip(spans, spans[1:]):
                self.assertLessEqual(end, start, f'seed {seed}')

    def test_the_scenarios_cover_the_display_modes(self):
        summaries = [selftest.generate(seed).summary for seed in range(40)]
        for key in ('ntsc', 'hires', 'dual', 'ham', 'blitter'):
            self.assertTrue(any(s[key] for s in summaries), key)
        self.assertEqual({s['planes'] for s in summaries}, set(range(1, 7)))

    def test_the_scenario_file_has_its_header_rom_and_regions(self):
        scenario = selftest.generate(3, frames=2)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 's.bin'
            scenario.write(path)
            data = path.read_bytes()
        self.assertEqual(data[:4], b'RRDS')
        version, flags, chip_kb, frames, _, rom = struct.unpack_from('<6I', data, 4)
        self.assertEqual((version, flags & 1, chip_kb, frames, rom), (1, int(scenario.ntsc), selftest.CHIP_KB, 2, 512 * 1024))
        (regions,) = struct.unpack_from('<I', data, 28 + rom)
        self.assertEqual(regions, len(scenario.regions))


def record(steps, frames):
    out = bytearray(b'RRDR') + struct.pack('<3I', 1, len(frames), 3)
    for fields, rows in frames:
        out += struct.pack('<12Q', *fields) + struct.pack('<3Q', *rows)
    out += struct.pack('<Q', len(steps)) + struct.pack(f'<{len(steps)}Q', *steps)
    return bytes(out)


class CompareTests(unittest.TestCase):
    def read(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'r.rec'
            path.write_bytes(data)
            return selftest.read_record(path)

    def test_equal_records_have_no_difference(self):
        a = self.read(record([1, 2, 3, 4], [([2] + [0] * 11, [5, 6, 7]), ([4] + [0] * 11, [5, 6, 7])]))
        self.assertIsNone(selftest.compare(a, a))

    def test_the_first_differing_instruction_and_its_frame_are_named(self):
        a = self.read(record([1, 2, 3, 4], [([2] + [0] * 11, [5, 6, 7]), ([4] + [0] * 11, [5, 6, 7])]))
        b = self.read(record([1, 2, 9, 4], [([2] + [0] * 11, [5, 6, 7]), ([4] + [0] * 11, [5, 6, 7])]))
        self.assertEqual(selftest.compare(a, b), {'at': 'instruction', 'index': 2, 'frame': 1})

    def test_a_difference_the_cpu_never_saw_is_placed_by_frame_part_and_row(self):
        a = self.read(record([1, 2], [([2] + [0] * 11, [5, 6, 7])]))
        b = self.read(record([1, 2], [([2, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0], [5, 8, 7])]))
        self.assertEqual(selftest.compare(a, b), {'at': 'frame', 'frame': 0, 'parts': ['chip'], 'rows': [1], 'row_count': 1})


class ReportCountTests(unittest.TestCase):
    """The counters a session writes (rr_amiga_write_display) as the report names them; a run without the idle disk and sprite counters reads 0."""
    def test_the_counters_are_named_in_the_report(self):
        sys.path.insert(0, str(ROOT))
        from retrorecomp.amiga_conversion import display_counts
        run = {'agnus_denise': {'bitplane_lines': [10, 2, 1], 'bitplane_words': [400, 8], 'line_pass': [9, 3], 'disk_idle': [5, 3, 2, 120],
                                'sprite_slots_left_out': 77}}
        counts = display_counts(run)
        self.assertEqual((counts['bitplane_lines_given_back'], counts['visible_lines_general_pass']), (1, 3))
        self.assertEqual((counts['disk_idle_batches'], counts['disk_idle_batches_at_event'], counts['disk_idle_batches_at_barrier'],
                          counts['disk_events_held_back'], counts['sprite_slot_events_left_out']), (5, 3, 2, 120, 77))
        older = display_counts({'agnus_denise': {'bitplane_lines': [1, 0, 0], 'bitplane_words': [1, 0], 'line_pass': [1, 0]}})
        self.assertEqual((older['disk_idle_batches'], older['disk_events_held_back'], older['sprite_slot_events_left_out']), (0, 0, 0))


if __name__ == '__main__':
    unittest.main()
