from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image

from retrorecomp.artwork import prepare_icon
from retrorecomp.batch import identify
from retrorecomp.core import ROOT, patched_generator_source, read_game_gear_rom
from retrorecomp.systems import profile_for_path


def cartridge(region=7):
    data = bytearray(32768)
    data[0x7ff0:0x7ff8] = b'TMR SEGA'
    data[0x7fff] = region << 4
    return bytes(data)


class GameGearTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_single_rom_zip_is_identified_without_extraction(self):
        source = self.root / 'Sample (Europe).zip'
        with ZipFile(source, 'w') as archive:
            archive.writestr('inside/Sample.gg', cartridge())
        before = source.read_bytes()
        self.assertEqual(profile_for_path(source).id, 'gg')
        rom = read_game_gear_rom(source)
        self.assertEqual((rom.system_id, rom.region), ('gg', 7))
        self.assertEqual(identify(source).system, 'gg')
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [source])

    def test_ambiguous_zip_does_not_guess_a_console(self):
        source = self.root / 'Mixed.zip'
        with ZipFile(source, 'w') as archive:
            archive.writestr('a.gg', cartridge())
            archive.writestr('b.sms', cartridge(region=4))
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            profile_for_path(source)

    def test_game_gear_cover_uses_game_gear_repository(self):
        source = self.root / 'Sample.gg'
        build = self.root / 'build'
        build.mkdir()
        image = Image.new('RGB', (32, 32), 'red')
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        with patch('retrorecomp.artwork._get', return_value=buffer.getvalue()) as get:
            result = prepare_icon(build, source, 'Sample', self.root / 'BoxArt', system_id='gg')
        self.assertTrue(result['embedded'])
        self.assertIn('Sega_-_Game_Gear', get.call_args.args[0])


class Z80GeneratorPatchTests(unittest.TestCase):
    """The patched Z80 generator never emits a direct C call to a paged address."""

    pinned = ROOT / '.deps/smsggrecomp/recompiler/src/code_generator.c'

    @unittest.skipUnless(pinned.is_file(), 'pinned smsggrecomp sources are not downloaded')
    def test_direct_calls_are_limited_to_the_fixed_first_kib(self):
        text = patched_generator_source(self.pinned.read_text(encoding='utf-8'))
        guard = 'if (T >= 0x0400) return NULL;'
        self.assertEqual(text.count(guard), 1)
        function = text.index('static const char *name_for_target(uint16_t T){')
        self.assertLess(function, text.index(guard))
        self.assertLess(text.index(guard) - function, 400)
        # The two call sites are the only users of name_for_target.
        self.assertEqual(text.count('name_for_target(T)'), 2)


if __name__ == '__main__':
    unittest.main()
