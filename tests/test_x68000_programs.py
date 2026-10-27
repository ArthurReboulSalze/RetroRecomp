from pathlib import Path
from tempfile import TemporaryDirectory
import struct
import unittest
from tools.x68000_fixture_disk import FixtureFat12
from tests.test_x68000_fixture_disk import synthetic_volume
from tools.x68000_fixtures import human68k_hello
from tools.x68000_programs import disk_files,program_provenance
from retrorecomp.x68000_program import parse_x


class DiskProgramTests(unittest.TestCase):
    def tree(self,loop=False):
        fs=FixtureFat12(synthetic_volume());fs.write('SUBDIR',bytes(1024));fs.write('RELOC.X',human68k_hello(relocated=True))
        directory=fs._find('SUBDIR');child=fs._find('RELOC.X')
        fs.data[directory+11]=0x10
        first=int.from_bytes(fs.data[directory+26:directory+28],'little')
        start=fs.data_offset+(first-2)*1024
        fs.data[start:start+32]=fs.data[directory:directory+32] if loop else fs.data[child:child+32]
        fs.data[child]=0xe5
        return bytes(fs.data)

    def test_nested_file_inventory_preserves_source_bytes(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'authored.xdf';content=self.tree();p.write_bytes(content)
            self.assertEqual(disk_files(p),{'SUBDIR/RELOC.X':human68k_hello(relocated=True)})
            self.assertEqual(p.read_bytes(),content)

    def test_looping_subdirectory_is_rejected(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'authored.xdf';p.write_bytes(self.tree(loop=True))
            with self.assertRaisesRegex(ValueError,'Looping'):disk_files(p)

    def test_same_module_reloaded_at_two_addresses_is_not_merged(self):
        source=human68k_hello(relocated=True);p=parse_x(source);samples=[]
        for base in (0x12340,0x23450):
            image=p.load_image(base)
            for off in (0,6,10):samples.append((base+off,image[off:off+16].hex()))
        result=program_provenance({'RELOC.X':source},samples)
        self.assertEqual({c['load_base'] for c in result['modules'][0]['observed_load_candidates']},{0x12340,0x23450})

if __name__=='__main__':unittest.main()
