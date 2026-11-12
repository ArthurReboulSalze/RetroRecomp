"""MSX stage 1 (no ROM, no compiler): the authored test cartridges, the C-BIOS pin and the skeleton's place in the stamps.

The machine itself is checked by `tools/msx_reference.py`, which builds it with the reference interpreter and boots
C-BIOS (fetched and pinned on first use)."""
import importlib.util
from pathlib import Path
import re
import unittest

from retrorecomp import stamp_inputs

ROOT = Path(__file__).resolve().parents[1]


def tool():
    spec = importlib.util.spec_from_file_location('msx_reference', ROOT / 'tools' / 'msx_reference.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AuthoredCartridgeTests(unittest.TestCase):
    def setUp(self):
        self.tool = tool()

    def check_common(self, image: bytes, size: int) -> int:
        self.assertEqual(len(image), size)
        self.assertEqual(image[0:2], b'AB')
        self.assertEqual(int.from_bytes(image[2:4], 'little'), 0x4010)
        self.assertEqual(image[4:16], bytes(12))           # no STATEMENT, DEVICE or TEXT: not a BASIC cartridge
        # The tail: JP handler written on H.TIMI, EI, then HALT and JR back to the HALT.
        tail = image.index(bytes([0x3E, 0xC3, 0x32, 0x9F, 0xFD]))
        handler = int.from_bytes(image[tail + 6:tail + 8], 'little')
        halt = tail + 12
        self.assertEqual(image[halt:halt + 3], bytes([0x76, 0x18, 0xFD]))
        self.assertEqual(halt + 3 + (0xFD - 256), halt)     # the JR lands on the HALT
        self.assertEqual(handler - 0x4000, halt + 3)          # the handler follows the loop
        self.assertEqual(image[handler - 0x4000:handler - 0x4000 + 8],
                         bytes([0x2A, 0x01, 0xE0, 0x23, 0x22, 0x01, 0xE0, 0xC9]))
        return handler

    def test_the_16k_cartridge_marks_init_and_counts_frames(self):
        image = self.tool.cartridge_16k()
        self.check_common(image, 0x4000)
        self.assertEqual(image[0x10:0x15], bytes([0x3E, 0x5A, 0x32, 0x00, 0xE0]))

    def test_the_32k_cartridge_selects_page_2_through_the_bios(self):
        image = self.tool.cartridge_32k()
        self.check_common(image, 0x8000)
        self.assertEqual(image[0x10:0x13], bytes([0xCD, 0x38, 0x01]))            # RSLREG
        jump = image.index(bytes([0xF2]), 0x10)                                  # jp p: page 1's slot not expanded
        self.assertEqual(int.from_bytes(image[jump + 1:jump + 3], 'little') - 0x4000, 0x2F)
        self.assertEqual(image[0x2F:0x32], bytes([0x79, 0x26, 0x80]))            # ld a,c; ld h,80h
        self.assertEqual(image[0x32:0x35], bytes([0xCD, 0x24, 0x00]))            # ENASLT
        self.assertEqual((image[0x4000], image[0x7FFF]), (0xA5, 0x3C))
        self.assertNotEqual(image[0x4000:0x4002], b'AB')                          # page 2 is no second header


    def test_the_polling_cartridge_loops_on_the_vdp_status(self):
        image = self.tool.cartridge_polling()
        self.assertEqual(image[0:4], b'AB\x10\x40')
        self.assertEqual(image[0x10:0x15], bytes([0xFB, 0xDB, 0x99, 0x18, 0xFC]))   # EI; IN A,(99h); JR -4
        self.assertEqual(0x13 + 2 + (0xFC - 256), 0x11)                              # the JR lands on the IN


    def test_the_input_cartridge_reads_through_the_bios_every_frame(self):
        image = self.tool.cartridge_input()
        self.assertEqual(image[0:4], b'AB\x10\x40')
        code = image[0x10:0x2C]
        for call in (bytes([0xCD, 0x41, 0x01]), bytes([0xCD, 0xD5, 0x00]), bytes([0xCD, 0xD8, 0x00])):
            self.assertIn(call, code)                                      # SNSMAT, GTSTCK, GTTRIG
        self.assertEqual(code[-2:], bytes([0x18, 0xE5]))
        self.assertEqual(0x2C + (0xE5 - 256), 0x11)                         # the JR lands on the HALT
        self.assertEqual(image[0x11], 0x76)

    def test_the_sound_cartridge_sets_tone_a_through_wrtpsg(self):
        image = self.tool.cartridge_sound()
        for register, value in ((0, 254), (1, 0), (7, 0xBE), (8, 15)):
            self.assertIn(bytes([0x3E, register, 0x1E, value, 0xCD, 0x93, 0x00]), image[0x10:0x40])


class PictureTests(unittest.TestCase):
    def test_a_frame_dump_becomes_a_bordered_png(self):
        import tempfile
        module = tool()
        with tempfile.TemporaryDirectory() as folder:
            dump = Path(folder) / 'frame.bin'
            dump.write_bytes(bytes([15]) * (192 * 256) + bytes([4]) * 192)
            target = Path(folder) / 'frame.png'
            module.png(dump, target)
            data = target.read_bytes()
            self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(int.from_bytes(data[16:20], 'big'), 272)
            self.assertEqual(int.from_bytes(data[20:24], 'big'), 208)


class M1ProgramTests(unittest.TestCase):
    """The authored timing program: each MSX cost is the standard cost plus one per M1 fetch (openMSX's table)."""

    @staticmethod
    def fetches(code: bytes) -> int:
        count, i = 0, 0
        while i < len(code) and code[i] in (0xDD, 0xFD) and code[i + 1] in (0xDD, 0xFD, 0xED):
            count, i = count + 1, i + 1            # a discarded prefix
        if code[i] in (0xCB, 0xED, 0xDD, 0xFD):
            return count + 2                        # prefix + opcode; DD CB d op fetches its last byte as data
        return count + 1

    def test_every_entry_adds_one_wait_per_m1_fetch(self):
        module = tool()
        for code, msx, z80 in module.M1_PROGRAM:
            repeats = 3 if code == bytes([0xED, 0xB0]) else 1     # LDIR over three bytes
            self.assertEqual(msx - z80, self.fetches(code) * repeats, code.hex())
        program = module.m1_program()
        self.assertEqual(program[0], 0xF3)
        self.assertEqual(program[-1], 0x76)


class PinTests(unittest.TestCase):
    def test_the_c_bios_pin_is_complete(self):
        module = tool()
        name, size, digest = module.ARCHIVE
        self.assertEqual(name, f'cbios-{module.VERSION}.zip')
        self.assertTrue(size > 0 and re.fullmatch(r'[0-9a-f]{64}', digest))
        for member, (length, sha) in module.MEMBERS.items():
            self.assertTrue(member.startswith('cbios_') and member.endswith('.rom'))
            self.assertIn(length, (16384, 32768))
            self.assertRegex(sha, r'^[0-9a-f]{64}$')
        self.assertTrue(module.URL.endswith('/' + name))


class StampTests(unittest.TestCase):
    def test_the_machine_is_the_msx_game_files_and_the_hardware_checks_move_no_stamp(self):
        msx = stamp_inputs.INPUTS[('msx', 'msx2')]
        for name in ('msx_machine.h', 'msx_machine.c', 'msx_reference_main.c', 'msx_video.c', 'msx_psg.c', 'msx_cart.c',
                     'msx_native_main.c', 'msx_glue.inc', 'msx_player.c'):
            path = 'native/msx_machine/' + name
            self.assertTrue((ROOT / path).is_file(), path)
            self.assertIn(path, msx)
        self.assertIn('native/msx_machine/msx_hardware_checks.c', stamp_inputs.NOT_INPUTS)


if __name__ == '__main__':
    unittest.main()
