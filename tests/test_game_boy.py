from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image

from smsrecomp.artwork import prepare_icon
from smsrecomp.batch import identify
from smsrecomp.core import ConversionError
from smsrecomp.gameboy import read_game_boy_rom
from smsrecomp.systems import profile_for_path


def cartridge(cgb_flag=0):
    data = bytearray(32768)
    data[0x134:0x13A] = b'SAMPLE'
    data[0x143] = cgb_flag
    return bytes(data)


class GameBoyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_direct_and_zip_identification_preserve_sources(self):
        direct = self.root / 'Sample.gb'
        direct.write_bytes(cartridge())
        archive_path = self.root / 'Sample.zip'
        with ZipFile(archive_path, 'w') as archive:
            archive.writestr('inside/Sample.gb', cartridge())
        sources = {p: p.read_bytes() for p in (direct, archive_path)}
        for path in sources:
            self.assertEqual(profile_for_path(path).id, 'gb')
            self.assertEqual(identify(path).system, 'gb')
            rom = read_game_boy_rom(path)
            self.assertEqual((rom.header_title, rom.system_id), ('SAMPLE', 'gb'))
        self.assertEqual(sources, {p: p.read_bytes() for p in sources})
        self.assertEqual(set(self.root.iterdir()), set(sources))

    def test_cgb_only_cartridge_rejected_by_dmg_profile(self):
        path = self.root / 'Color Only.gb'
        path.write_bytes(cartridge(0xC0))
        with self.assertRaisesRegex(ConversionError, 'requires Game Boy Color'):
            read_game_boy_rom(path)

    def test_game_boy_cover_uses_game_boy_catalogue(self):
        source = self.root / 'Sample.gb'
        build = self.root / 'build'
        build.mkdir()
        image = Image.new('RGB', (32, 32), 'blue')
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        with patch('smsrecomp.artwork._get', return_value=buffer.getvalue()) as get:
            result = prepare_icon(build, source, 'Sample', self.root / 'BoxArt', system_id='gb')
        self.assertTrue(result['embedded'])
        self.assertIn('Nintendo_-_Game_Boy', get.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
