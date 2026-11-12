"""The MSX mapper guess (tools/msx_rom.py) on synthetic images: no ROM."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module():
    spec = importlib.util.spec_from_file_location('msx_rom', ROOT / 'tools' / 'msx_rom.py')
    loaded = importlib.util.module_from_spec(spec)
    sys.modules['msx_rom'] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def header(init=0x4010, statement=0, device=0, text=0) -> bytes:
    return b'AB' + b''.join(p.to_bytes(2, 'little') for p in (init, statement, device, text)) + bytes(6)


def writes(*addresses, through_hl=False) -> bytes:
    code = b''
    for address in addresses:
        if through_hl:
            code += bytes([0x21, address & 0xFF, address >> 8, 0x77])          # LD HL,nn; LD (HL),A
        else:
            code += bytes([0x3E, 1, 0x32, address & 0xFF, address >> 8])      # LD A,1; LD (nn),A
    return code


def image(size: int, code: bytes = b'', init=0x4010, text=0) -> bytes:
    data = bytearray(b'\xFF' * size)
    data[0:16] = header(init, text=text)
    data[16:16 + len(code)] = code
    return bytes(data)


class PlainTests(unittest.TestCase):
    def setUp(self):
        self.rom = module()

    def test_a_16k_image_with_init_in_page_1_sits_at_4000h(self):
        g = self.rom.guess(image(0x4000))
        self.assertEqual((g.mapper, g.base, g.mirrored), ('plain', 0x4000, True))
        self.assertEqual(g.arguments(), ['--mapper', 'plain', '--cart-base', '4000', '--mirrored'])

    def test_a_basic_text_pointer_in_page_2_sits_at_8000h(self):
        g = self.rom.guess(image(0x4000, init=0, text=0x8010))
        self.assertEqual((g.mapper, g.base), ('plain', 0x8000))

    def test_a_32k_image_is_plain_whatever_it_writes(self):
        self.assertEqual(self.rom.guess(image(0x8000, writes(0x9000, 0xB000))).mapper, 'plain')

    def test_a_64k_image_with_an_init_in_page_0_sits_at_0000h(self):
        self.assertEqual(self.rom.guess(image(0x10000, init=0x0010)).base, 0x0000)

    def test_a_64k_image_that_writes_mapper_registers_is_a_mapper(self):
        g = self.rom.guess(image(0x10000, writes(0x6000, 0x6800, 0x7000, 0x7800)))
        self.assertEqual(g.mapper, 'ascii8')


class MapperTests(unittest.TestCase):
    def setUp(self):
        self.rom = module()

    def guess(self, *addresses, through_hl=False):
        return self.rom.guess(image(0x20000, writes(*addresses, through_hl=through_hl))).mapper

    def test_each_mapper_by_its_registers(self):
        self.assertEqual(self.guess(0x6000, 0x8000, 0xA000), 'konami')
        scc = image(0x20000, writes(0x5000, 0x7000, 0x9000, 0xB000) + bytes([0x21, 0x00, 0x98]))   # LD HL,9800h
        self.assertEqual(self.rom.guess(scc).mapper, 'konami-scc')
        self.assertEqual(self.guess(0x5000, 0x7000, 0x9000, 0xB000), 'ascii16')   # without the SCC: 7000h only counts
        self.assertEqual(self.guess(0x6000, 0x6800, 0x7000, 0x7800), 'ascii8')
        self.assertEqual(self.guess(0x6000, 0x77FF), 'ascii16')

    def test_shared_addresses_alone_are_ascii_16(self):
        self.assertEqual(self.guess(0x7000), 'ascii16')                    # page 2 switching only
        self.assertEqual(self.guess(0x6000, 0x7000), 'ascii16')

    def test_writes_through_hl_count(self):
        self.assertEqual(self.guess(0x6000, 0x8000, 0xA000, through_hl=True), 'konami')

    def test_no_register_write_gives_no_guess(self):
        g = self.rom.guess(image(0x20000))
        self.assertIsNone(g.mapper)
        with self.assertRaises(ValueError):
            g.arguments()


if __name__ == '__main__':
    unittest.main()


class FirstReadTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        spec = importlib.util.spec_from_file_location('msx_first_read', ROOT / 'tools' / 'msx_first_read.py')
        self.tool = importlib.util.module_from_spec(spec)
        sys.modules['msx_first_read'] = self.tool
        spec.loader.exec_module(self.tool)

    def test_a_zip_member_is_read_into_memory(self):
        import tempfile
        import zipfile
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'game.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('game.rom', image(0x4000))
                bundle.writestr('readme.txt', 'not a cartridge')
            self.assertEqual(self.tool.read_rom(archive), image(0x4000))

    def test_output_folders_are_named_from_the_file_names(self):
        self.assertEqual(self.tool.slug('msx1/Road Fighter (Japan).zip'), 'road-fighter-japan')
