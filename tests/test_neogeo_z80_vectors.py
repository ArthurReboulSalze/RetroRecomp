"""Neo Geo independent Z80 vector replay (gate G10): the ROM-free, compiler-free parts of tools/neogeo_z80_vector_selftest.py.

The replay itself builds C and takes a few minutes: `python -B tools/neogeo_z80_vector_selftest.py` after `python -B tools/fetch_z80_vectors.py`
(BUILDING.md). The corpus, the vectors file, the report and the judging rules are the CPS-1 replay's (tests/test_cps1_z80_vectors.py)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('neogeo_z80_vector_selftest', ROOT / 'tools' / 'neogeo_z80_vector_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)

from retrorecomp.neogeo import parse_neo


def case(pc, code):
    ram = [[(pc + n) & 0xffff, byte] for n, byte in enumerate(code)]
    return {'initial': {'pc': pc, 'ram': ram}, 'family': code[0:1].hex()}


class PrepareTests(unittest.TestCase):
    def test_below_the_ram_window_one_slot_per_opcode_form_and_above_it_one_variant_per_address_and_bytes(self):
        cases = [case(0x0100, b'\x00'), case(0x2000, b'\x00'),               # the same form twice: one slot
                 case(0x0100, b'\x3e\x12'), case(0x7ffc, b'\x3e\x55'),       # LD A,n: the operand is read live, one slot
                 case(0xf800, b'\x00'), case(0xf800, b'\x00'), case(0xfffe, b'\x3e\x01'), case(0xfffe, b'\x3e\x02')]
        image, ram, slots, forms = selftest.prepare(cases)
        self.assertEqual(len(image), selftest.M1_BYTES)
        self.assertEqual(slots[0], slots[1])
        self.assertEqual(slots[2], slots[3])
        self.assertNotEqual(slots[0], slots[2])
        self.assertEqual(forms, 2)
        self.assertEqual(slots[4:], [selftest.NO_SLOT] * 4)                    # RAM-window vectors have no image slot
        self.assertEqual({(item['address'], item['bytes']) for item in ram},
                         {(0xf800, '00a5a5a5'), (0xfffe, '3e01a5a5'), (0xfffe, '3e02a5a5')})
        for slot in set(slots[:4]):
            self.assertEqual(slot % selftest.SLOT, 0)
        self.assertEqual(image[slots[0]], 0x00)
        self.assertEqual(image[slots[2]], 0x3e)

    def test_the_window_wraps_at_the_end_of_the_address_space(self):
        # a vector at 0xffff reads its next bytes from 0x0000: the vector's own memory list holds them
        item = {'initial': {'pc': 0xffff, 'ram': [[0xffff, 0x3e], [0x0000, 0x77]]}, 'family': '3e'}
        self.assertEqual(selftest.shared.window(item), bytes([0x3e, 0x77, 0xa5, 0xa5]))
        _, ram, slots, _ = selftest.prepare([item])
        self.assertEqual(slots, [selftest.NO_SLOT])
        self.assertEqual(ram, [{'address': 0xffff, 'bytes': '3e77a5a5'}])


class CartridgeTests(unittest.TestCase):
    def test_the_synthetic_cartridge_is_a_valid_container_whose_sound_program_is_the_image(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            image = bytes(range(256)) * (selftest.M1_BYTES // 256)
            selftest.write_cartridge(project, image)
            prepared = parse_neo(project / 'cartridge.neo')
            regions = {row['region']: row for row in prepared.members}
            self.assertEqual(regions['m']['bytes'], selftest.M1_BYTES)
            data = (project / 'cartridge.neo').read_bytes()
            self.assertEqual(data[regions['m']['offset']:regions['m']['offset'] + selftest.M1_BYTES], image)
            with ZipFile(project / 'bios.zip') as archive:
                self.assertEqual(archive.namelist(), ['sm1.sm1'])
                self.assertEqual(len(archive.read('sm1.sm1')), selftest.SM1_BYTES)

    def test_the_ram_window_is_the_one_the_generator_translates(self):
        text = (ROOT / 'retrorecomp' / 'neogeo_z80.py').read_text(encoding='utf-8')
        self.assertIn('0xf800<=pc<=0xffff', text)
        self.assertEqual(selftest.RAM_FIRST, 0xf800)


class SharedRulesTests(unittest.TestCase):
    def test_the_judging_rules_and_the_pinned_baseline_are_the_cps1_ones(self):
        self.assertEqual(selftest.shared.BASELINE['native_state'], 51260)
        self.assertEqual(selftest.shared.BASELINE['native_clock'], 51328)
        self.assertEqual(set(selftest.shared.BASELINE['families']), {'37', '3f', 'dd 37', 'dd 3f', 'fd 37', 'fd 3f'})


if __name__ == '__main__':
    unittest.main()
