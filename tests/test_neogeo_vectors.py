"""Neo Geo independent MC68000 vector replay (gate G10): the ROM-free, compiler-free parts of tools/neogeo_vector_selftest.py.

The replay itself builds C and takes a few minutes: `python -B tools/neogeo_vector_selftest.py` (BUILDING.md). The fixtures and their
reading are shared with the CPS-1 replay (tests/test_cps1_vectors.py checks the header)."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('neogeo_vector_selftest', ROOT / 'tools' / 'neogeo_vector_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)

from retrorecomp.neogeo import parse_neo


class VectorCartridgeTests(unittest.TestCase):
    def test_every_fixture_makes_a_valid_synthetic_cartridge_whose_program_is_the_vector_image(self):
        for name in selftest.FIXTURES:
            with self.subTest(fixture=name), tempfile.TemporaryDirectory() as folder:
                project = Path(folder)
                _, program, _ = selftest.shared.cases_header(name)
                selftest.write_cartridge(project, program)
                prepared = parse_neo(project / 'cartridge.neo')               # the container the generator reads
                regions = {row['region']: row['bytes'] for row in prepared.members}
                self.assertEqual(regions['p'], selftest.PROGRAM_BYTES)
                data = (project / 'cartridge.neo').read_bytes()
                self.assertEqual(struct.unpack_from('<6I', data, 4)[0], selftest.PROGRAM_BYTES)
                body = data[4096:4096 + selftest.PROGRAM_BYTES]               # stored byte-swapped, as the generator expects
                self.assertEqual(selftest.swapped(body), program)
                with ZipFile(project / 'bios.zip') as archive:
                    self.assertEqual(archive.namelist(), ['sp-s2.sp1'])
                    self.assertEqual(len(archive.read('sp-s2.sp1')), 131072)

    def test_entries_are_even_distinct_and_inside_the_program(self):
        for name in selftest.FIXTURES:
            with self.subTest(fixture=name):
                entries = selftest.entry_offsets(name)
                self.assertEqual(len(entries), len(set(entries)))
                self.assertTrue(all(0 <= offset < selftest.PROGRAM_BYTES and not offset & 1 for offset in entries))
                self.assertGreater(len(entries), 100)

    def test_swapping_is_its_own_inverse(self):
        data = bytes(range(256))
        self.assertEqual(selftest.swapped(selftest.swapped(data)), data)
        self.assertEqual(selftest.swapped(b'\x01\x02\x03\x04'), b'\x02\x01\x04\x03')

    def test_the_replay_judges_with_the_shared_rules(self):
        self.assertIs(selftest.shared.problems, selftest.shared.problems)
        good = {'groups': [{'group': 'ADD.w', 'cases': 10, 'native_executed': 10, 'native_state': 10, 'reference_state': 10,
                            'native_clock': 10, 'reference_clock': 10, 'paths_equal': 10, 'paths_clock_equal': 10}]}
        self.assertEqual(selftest.shared.problems(good), [])
        bad = {'groups': [dict(good['groups'][0], native_executed=9, native_state=9)]}
        self.assertEqual(len(selftest.shared.problems(bad)), 2)


if __name__ == '__main__':
    unittest.main()
