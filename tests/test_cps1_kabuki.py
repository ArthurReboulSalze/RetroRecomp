"""The Kabuki Z80 decryption of the CPS-1.5 (QSound) boards: keys, images, instruction fetches (compiler-free parts).

The decryption is compared with MAME byte for byte on real ROMs by `tools/cps1_kabuki_check.py`; the patched core and the
generator on two different images are run by `python -B tools/cps1_kabuki_selftest.py` (they need MAME, the ROMs, a compiler)."""
import hashlib
from pathlib import Path
import unittest

from retrorecomp import cps1_board, cps1_build, cps1_catalogue, cps1_kabuki
from retrorecomp.megadrive_z80 import opcode_key

ROOT = Path(__file__).resolve().parents[1]
GEOLITH = ROOT / '.deps/geolith-libretro'
FAMILIES = {'init_wof': ('wof', 'wofr1', 'wofu', 'wofa', 'wofj', 'wofch'),
            'init_dino': ('dino', 'dinou', 'dinoa', 'dinoj'),
            'init_punisher': ('punisher', 'punisheru', 'punisherh', 'punisherj'),
            'init_slammast': ('slammast', 'slammastu', 'mbomberj', 'mbombrd', 'mbombrdj')}
# sha256 (first 16 digits) of the two images of an all-zero sound ROM, which depend on the keys alone: a regression pin of
# the algorithm, checked against MAME on real ROMs by tools/cps1_kabuki_check.py (no ROM data here).
ZERO_ROM_PINS = {'init_wof': ('21059eeebd1ec686', '3a4abbdf1cc5ea8f'), 'init_dino': ('f320b0d47c1a5b29', 'a91754176de8269f'),
                 'init_punisher': ('ca88e36544fcb138', 'db9982b664f02a8b'), 'init_slammast': ('7cf9e73dc1309332', '8b63a522412b2539')}


class KeyTests(unittest.TestCase):
    def test_every_set_with_a_kabuki_names_its_keys(self):
        games = {game['set']: game for game in cps1_catalogue.games()}
        named = set()
        for init, sets in FAMILIES.items():
            for name in sets:
                self.assertEqual(games[name]['init'], init, name)
                self.assertIsNotNone(cps1_kabuki.keys_for(games[name]), name)
                named.add(name)
        # the QSound sets of the catalogue are exactly these (the CPS Changer cartridge wofch included), and no other set has keys
        self.assertEqual({game['set'] for game in games.values() if game['machine'] == 'qsound'}, named)
        for game in games.values():
            if game['set'] not in named:
                self.assertIsNone(cps1_kabuki.keys_for(game), game['set'])

    def test_the_keys_are_numbers_of_the_algorithm(self):
        for init, keys in cps1_catalogue.catalogue()['kabuki'].items():
            self.assertEqual(set(keys), {'swap_key1', 'swap_key2', 'addr_key', 'xor_key', 'base', 'length'}, init)
            self.assertTrue(all(type(value) is int for value in keys.values()), init)
            self.assertEqual((keys['base'], keys['length']), (0, 0x8000))
            for name in ('swap_key1', 'swap_key2'):
                # a key is a permutation of the eight bit positions, one nibble each
                self.assertEqual(sorted((keys[name] >> shift) & 15 for shift in range(0, 32, 4)), list(range(8)), (init, name))


class DecodeTests(unittest.TestCase):
    def test_images_of_a_zero_rom_are_pinned_per_family(self):
        for init, (opcodes_pin, data_pin) in ZERO_ROM_PINS.items():
            keys = cps1_catalogue.catalogue()['kabuki'][init]
            opcodes, data = cps1_kabuki.decode(bytes(0x9000), keys)
            self.assertEqual(hashlib.sha256(opcodes).hexdigest()[:16], opcodes_pin, init)
            self.assertEqual(hashlib.sha256(data).hexdigest()[:16], data_pin, init)

    def test_only_the_encrypted_range_changes(self):
        keys = cps1_catalogue.catalogue()['kabuki']['init_wof']
        rom = bytes(range(256)) * 160                      # 0xa000 bytes
        opcodes, data = cps1_kabuki.decode(rom, keys)
        self.assertEqual((len(opcodes), len(data)), (len(rom), len(rom)))
        self.assertEqual(opcodes[0x8000:], rom[0x8000:])
        self.assertEqual(data[0x8000:], rom[0x8000:])
        self.assertNotEqual(opcodes[:0x8000], rom[:0x8000])
        self.assertNotEqual(opcodes[:0x8000], data[:0x8000])

    def test_each_view_is_a_permutation_of_the_byte_values_at_every_address(self):
        for keys in cps1_catalogue.catalogue()['kabuki'].values():
            for address in (0x0000, 0x0001, 0x1fc0, 0x7fff):
                for view in range(2):
                    seen = {cps1_kabuki.decode_byte(value, keys['swap_key1'], keys['swap_key2'], keys['xor_key'],
                                                    (address + keys['addr_key'] + 0x100 * view) & 0xffff)
                            for value in range(256)}
                    self.assertEqual(len(seen), 256)

    def test_a_short_rom_is_decoded_as_far_as_it_goes(self):
        keys = cps1_catalogue.catalogue()['kabuki']['init_dino']
        opcodes, data = cps1_kabuki.decode(bytes(16), keys)
        self.assertEqual((len(opcodes), len(data)), (16, 16))


class FetchTests(unittest.TestCase):
    def test_which_bytes_of_an_instruction_are_fetches(self):
        self.assertEqual(cps1_kabuki.m1_positions(bytes([0x3e, 0x12, 0, 0])), (0,))
        self.assertEqual(cps1_kabuki.m1_positions(bytes([0xed, 0x44, 0, 0])), (0, 1))
        self.assertEqual(cps1_kabuki.m1_positions(bytes([0xcb, 0x46, 0, 0])), (0, 1))
        self.assertEqual(cps1_kabuki.m1_positions(bytes([0xdd, 0x21, 1, 2])), (0, 1))
        self.assertEqual(cps1_kabuki.m1_positions(bytes([0xdd, 0xcb, 5, 0x46])), (0, 1))     # d and the last byte are data
        self.assertEqual(cps1_kabuki.m1_positions(bytes([0xfd, 0xdd, 0x7e, 3])), (0, 1, 2))  # a chain of prefixes

    def test_window_takes_each_byte_from_its_view(self):
        opcodes = bytes([0xdd, 0xcb, 0x77, 0x77, 0x3e, 0xff, 0xed, 0x44])
        data = bytes([0x00, 0x00, 0x02, 0x46, 0x00, 0x42, 0x00, 0x00])
        self.assertEqual(cps1_kabuki.window(opcodes, data, 0), bytes([0xdd, 0xcb, 0x02, 0x46]))
        self.assertEqual(cps1_kabuki.window(opcodes, data, 4), bytes([0x3e, 0x42, 0x00, 0x00]))
        self.assertEqual(cps1_kabuki.window(opcodes, data, 6), bytes([0xed, 0x44, 0x00, 0x00]))
        # past the end the window wraps like the plain generator's
        self.assertEqual(cps1_kabuki.window(opcodes, data, 7)[:1], bytes([0x44]))

    def test_the_instruction_form_comes_from_the_opcode_view(self):
        opcodes = bytes([0xdd, 0xcb, 0x77, 0x77]) + bytes(8)
        data = bytes([0x00, 0x00, 0x02, 0x46]) + bytes(8)
        mask, raw = opcode_key(cps1_kabuki.window(opcodes, data, 0))
        self.assertEqual((mask, raw), (0b1011, bytes([0xdd, 0xcb, 0, 0x46])))                # the plain data view would see NOPs
        self.assertEqual(opcode_key(data[:4])[0], 0b0001)


@unittest.skipUnless((GEOLITH / 'src/z80/z80.c').is_file(), 'pinned Geolith sources are not cached')
class CoreTests(unittest.TestCase):
    def test_the_core_of_a_board_without_a_kabuki_is_the_pinned_one(self):
        plain = cps1_build.z80_core(GEOLITH, native=True)
        self.assertNotIn('nextop', plain)
        self.assertNotIn('code_byte_m1', plain)
        self.assertEqual(plain, cps1_build.z80_core(GEOLITH, native=True, kabuki=False))

    def test_the_kabuki_core_fetches_instruction_bytes_from_the_opcode_view(self):
        native = cps1_build.z80_core(GEOLITH, native=True, kabuki=True)
        reference = cps1_build.z80_core(GEOLITH, native=False)
        for text in (native, reference):
            self.assertEqual(text.count('nextop(z)'), 5)         # the step and the four prefix fetches
            self.assertIn('extern uint8_t rr_cps1_z80_read_op(uint16_t address);', text)
        self.assertIn('rr_cps1_z80_code_byte_m1(', native)
        self.assertNotIn('rr_cps1_z80_try', reference)
        self.assertNotIn('rr_cps1_z80_code_byte_m1(', reference)

    def test_a_changed_pin_is_refused(self):
        with self.assertRaises(ValueError):
            cps1_kabuki.patch_core('static inline uint8_t nextb(z80* const z) { return 0; }')


class BoardTests(unittest.TestCase):
    def test_the_opcode_image_travels_beside_the_board(self):
        self.assertIn('audiocpu-op', cps1_board.RUNTIME_REGIONS)
        self.assertIn('audiocpu-op.bin', cps1_build.PACK_REGIONS)


if __name__ == '__main__':
    unittest.main()
