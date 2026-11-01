"""The cartridge authored by tools/gameboy_states_check.py (gate G6) and its small helpers, without converting anything."""
import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location('gameboy_states_check', TOOLS / 'gameboy_states_check.py')
states = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(states)


class AuthoredStateCartridgeTests(unittest.TestCase):
    def setUp(self):
        self.rom = states.authored_rom()

    def test_the_header_is_valid(self):
        self.assertEqual(len(self.rom), 0x8000)
        self.assertEqual((self.rom[0x147], self.rom[0x148], self.rom[0x149]), (0, 0, 0))
        checksum = 0
        for index in range(0x134, 0x14D):
            checksum = (checksum - self.rom[index] - 1) & 0xFF
        self.assertEqual(self.rom[0x14D], checksum)

    def test_the_interrupt_vectors_jump_to_their_handlers(self):
        self.assertEqual(self.rom[0x40:0x43], bytes.fromhex('c30002'))          # vertical blank
        self.assertEqual(self.rom[0x50:0x53], bytes.fromhex('c31002'))          # timer
        self.assertEqual(self.rom[0x200:0x20C], bytes.fromhex('f5fa10c13cea10c1e013f1d9'))
        self.assertEqual(self.rom[0x210:0x21A], bytes.fromhex('f5fa11c13cea11c1f1d9'))   # both handlers end in POP AF ; RETI

    def test_the_foreground_fits_before_the_handlers_and_loops(self):
        code = self.rom[0x150:0x200]
        end = code.rstrip(b'\0')
        self.assertLess(len(end), 0xB0)
        self.assertEqual(end[-2], 0x18)                                           # JR back to the counter loop

    def test_the_game_turns_the_screen_off_to_write_its_tile(self):
        self.assertEqual(self.rom[0x153:0x157], bytes.fromhex('3e00e040'))      # LD A,0 ; LDH ($40),A after LD SP

    def test_the_state_header_layout_matches_the_runtime(self):
        self.assertEqual(states.HEADER_FIELDS.size, 16)
        self.assertEqual(struct.calcsize('<II'), 8)


class TraceReadingTests(unittest.TestCase):
    def test_a_trace_is_read_without_its_frame_number(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a.csv'
            path.write_text('frame,picture,sound,nonzero_samples,ram,pc\n1,aa,bb,3,cc,0150\n2,ab,bc,4,cd,0151\n', encoding='ascii')
            self.assertEqual(states.trace_rows(path), [['aa', 'bb', '3', 'cc', '0150'], ['ab', 'bc', '4', 'cd', '0151']])
            self.assertEqual(states.trace_rows(Path(folder) / 'missing.csv'), [])

    def test_differences_name_the_fields_that_differ(self):
        self.assertEqual(states.differences({'a': 1, 'b': 2}, {'a': 1, 'b': 3, 'c': 4}), ['b', 'c'])


if __name__ == '__main__':
    unittest.main()
