"""The anchors of tools/z80_contention_loop_selftest.py, without a compiler: the step loop rendered for a machine with contention holds
each line the gate's mutations remove exactly once (so a change of the rendered text cannot leave a positive control mutating nothing), the
authored programs are what the gate says they are, and a machine without contention renders none of it."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

import z80_contention_loop_selftest as gate  # noqa: E402
from retrorecomp import z80_chain  # noqa: E402
from retrorecomp.paths import ASSETS  # noqa: E402


class AnchorTests(unittest.TestCase):
    def test_every_mutation_finds_its_line_exactly_once_in_the_loop_with_contention(self):
        loop = z80_chain.banked_runtime(gate.contention_machine(True), ASSETS)
        for name, (old, new) in gate.MUTATIONS.items():
            self.assertEqual(loop.count(old), 1, name)
            self.assertNotEqual(old, new, name)

    def test_the_loop_without_contention_holds_none_of_them(self):
        loop = z80_chain.banked_runtime(gate.contention_machine(False), ASSETS)
        for name, (old, _) in gate.MUTATIONS.items():
            self.assertEqual(loop.count(old), 0, name)
        self.assertNotIn('rr_timed', loop)

    def test_the_gate_machine_has_its_own_generator_and_the_converters_stays_as_it_is(self):
        on, off = gate.contention_machine(True), gate.contention_machine(False)
        self.assertTrue(on.contention)
        self.assertFalse(off.contention)
        self.assertNotEqual(on.generator_tag, off.generator_tag)
        from retrorecomp.systems.sg1000 import SG1000_MACHINE
        self.assertIs(off, SG1000_MACHINE)
        self.assertFalse(SG1000_MACHINE.contention)

    def test_the_expectations_name_every_mutation_for_both_programs(self):
        for mode, expected in gate.EXPECT.items():
            self.assertEqual(set(expected), set(gate.MUTATIONS), mode)
        self.assertTrue(gate.EXPECT['mode1']['im1'] and not gate.EXPECT['mode1']['im2'])
        self.assertTrue(gate.EXPECT['mode2']['im2'] and not gate.EXPECT['mode2']['im1'])


class ProgramTests(unittest.TestCase):
    def test_the_mode_two_program_loads_i_and_holds_the_vector(self):
        one, two = gate.mode1_cartridge(), gate.mode2_cartridge()
        self.assertEqual(len(one), len(two))
        self.assertEqual(two[0x100:0x102], bytes([0xED, 0x5E]))                       # IM 2
        self.assertEqual(two[0x300:0x307], bytes([0x3E, 0x03, 0xED, 0x47, 0xC3, 0x00, 0x01]))    # LD A,03h; LD I,A; JP 0100h
        self.assertEqual(two[0x3FF:0x401], bytes([0x00, 0x02]))                      # the vector at I:FFh points to 0200h
        self.assertEqual(one[0x100:0x102], bytes([0xED, 0x56]))                       # IM 1
        self.assertEqual(sum(a != b for a, b in zip(one, two)) > 0, True)

    def test_the_route_has_many_presses_of_pause_in_frame_order(self):
        frames = [int(event.split(':')[0]) for event in gate.ROUTE]
        self.assertEqual(frames, sorted(frames))
        self.assertGreaterEqual(sum(event.endswith(':pause') for event in gate.ROUTE), 12)
        self.assertLess(frames[-1], gate.FRAMES)

    def test_the_rom_table_covers_the_whole_cartridge_space(self):
        text = gate.rom_table(gate.mode1_cartridge())
        self.assertIn('rr_gate_rom[0xC000]', text)
        body = text.split('{', 1)[1].rsplit('}', 1)[0]
        values = [v for v in body.replace('\n', ',').split(',') if v.strip()]
        self.assertEqual(len(values), 0xC000)


if __name__ == '__main__':
    unittest.main()
