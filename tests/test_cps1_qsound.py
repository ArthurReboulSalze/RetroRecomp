"""The QSound DSP ROM of the CPS-1.5 boards: found in a file or in a ZIP by its CRC and SHA-1, refused with a reason, never shipped.

The real dump is the player's own and is not in the repository: these tests make a synthetic file of the same size and stand it in by
patching the identity constants of `cps1_qsound`."""
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib
from zipfile import ZipFile

from retrorecomp import cps1_catalogue, cps1_qsound
from retrorecomp.paths import console_options, path_option_names
from retrorecomp.systems import get_profile

DUMP = bytes((n * 31 + (n >> 8)) & 0xff for n in range(cps1_qsound.SIZE))


def standing_in(data=DUMP):
    return patch.multiple(cps1_qsound, CRC32=zlib.crc32(data), SHA1=hashlib.sha1(data).hexdigest())


class DumpTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def test_the_real_identity_is_the_one_of_mames_dsp_rom(self):
        self.assertEqual((cps1_qsound.NAME, cps1_qsound.CRC32, cps1_qsound.SHA1, cps1_qsound.SIZE),
                         ('dl-1425.bin', 0xd6cf5ef5, '555f50fe5cdf127619da7d854c03f4a244a0c501', 0x6000))

    def test_a_file_with_the_right_identity_is_found_whatever_its_name(self):
        path = self.root / 'whatever.rom'
        path.write_bytes(DUMP)
        with standing_in():
            info = cps1_qsound.validate_dsp_rom(path)
            self.assertEqual((info['bytes'], info['sha256']), (len(DUMP), hashlib.sha256(DUMP).hexdigest()))
            self.assertEqual(cps1_qsound.internal_rom(path), DUMP[:cps1_qsound.INTERNAL_BYTES])

    def test_a_zip_is_searched_by_crc_not_by_name(self):
        path = self.root / 'qsound.zip'
        with ZipFile(path, 'w') as archive:
            archive.writestr('readme.txt', b'not it')
            archive.writestr('a_name_nobody_expects', DUMP)
        with standing_in():
            self.assertEqual(cps1_qsound.read_dump(path), DUMP)

    def test_a_wrong_or_missing_dump_is_refused_with_a_reason(self):
        with standing_in():
            for value, words in ((None, 'No QSound DSP ROM selected'), (self.root / 'absent.zip', 'cannot be read')):
                with self.assertRaises(ValueError) as caught:
                    cps1_qsound.read_dump(value)
                self.assertIn(words, str(caught.exception))
            other = self.root / 'other.bin'
            other.write_bytes(bytes(len(DUMP)))
            with self.assertRaises(ValueError) as caught:
                cps1_qsound.read_dump(other)
            self.assertIn('d6cf5ef5', str(caught.exception))
            short = self.root / 'short.bin'
            short.write_bytes(DUMP[:100])
            with self.assertRaises(ValueError):
                cps1_qsound.read_dump(short)
            empty = self.root / 'empty.zip'
            with ZipFile(empty, 'w') as archive:
                archive.writestr('x', b'x')
            with self.assertRaises(ValueError) as caught:
                cps1_qsound.read_dump(empty)
            self.assertIn('no file with the CRC', str(caught.exception))

    def test_only_the_qsound_boards_need_it(self):
        games = {game['set']: game for game in cps1_catalogue.games()}
        self.assertTrue(cps1_qsound.needs_dsp_rom(games['wof']))
        self.assertFalse(cps1_qsound.needs_dsp_rom(games['ffight']))
        self.assertFalse(cps1_qsound.path_needs_dsp_rom(self.root / 'nothing.zip'))


class OptionTests(unittest.TestCase):
    def test_the_option_is_declared_by_the_profile_like_the_neo_geo_bios(self):
        keys = {key.name: key for key in get_profile('cps1').option_keys}
        self.assertEqual((keys['qsound_rom'].kind, keys['qsound_rom'].signature), ('path', False))
        self.assertIn('qsound_rom', {key.name for _, key in console_options('path')})
        self.assertIn('qsound_rom', path_option_names())      # saved relative to the export folder, as the BIOS is

    def test_a_request_for_another_board_gets_no_firmware_identity(self):
        settings = {}
        item = SimpleNamespace(path=Path('missing.zip'), sha256='0' * 64)
        get_profile('cps1').request_identity(item, {'qsound_rom': 'x'}, settings)
        self.assertEqual(settings, {})

    def test_a_qsound_set_without_the_dsp_rom_is_refused_with_its_reason(self):
        from retrorecomp import cps1_conversion
        from retrorecomp.core import ConversionError
        found = SimpleNamespace(supported=True, set_name='wof', title='Warriors of Fate', reason='', sha256='0' * 64)
        with patch('retrorecomp.cps1.read_set', return_value=found), self.assertRaises(ConversionError) as caught:
            cps1_conversion.convert(Path('wof.zip'), qsound_rom=None)
        message = str(caught.exception)
        for words in ('dl-1425.bin', 'd6cf5ef5', '--qsound-rom', 'never shipped or downloaded'):
            self.assertIn(words, message)


if __name__ == '__main__':
    unittest.main()
