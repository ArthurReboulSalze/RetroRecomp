"""The Commodore Amiga profile recognises a WHDLoad install and refuses the rest, on a synthetic archive written by the test
(authored words, no game, no ROM, no Kickstart). Nothing here reads or writes the converter's settings."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from retrorecomp import amiga
from retrorecomp.core import ConversionError
from retrorecomp.systems import ConsoleMismatchError, UnsupportedConsoleError, get_profile, profile_for_path
from tests.test_amiga_lha import level0, level1, level2
from tests.test_amiga_whdload import hunk_file, slave_code


def install(*slaves, data=(('Game/data/Disk.1', b'\x01' * 64),), kick=None):
    """An archive of an install: each slave is a hunk file with a `WHDLOADS` header, then the data files."""
    blob = b''.join(level1(name, hunk_file(slave_code(kick=kick))) for name in slaves)
    return blob + b''.join(level1(name, content) for name, content in data) + b'\x00'


class ProfileTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        available = patch('retrorecomp.amiga.converter_available', return_value=True)
        available.start()
        self.addCleanup(available.stop)

    def write(self, blob, name='Synthetic.lha'):
        path = self.folder / name
        path.write_bytes(blob)
        return path

    def test_the_profile_says_what_it_is(self):
        profile = get_profile('amiga')
        self.assertEqual((profile.name, profile.status, profile.linux, profile.developer_only),
                         ('Commodore Amiga', 'experimental', 'witnessed', False))
        self.assertEqual(profile.extensions, ('.lha',))
        self.assertEqual([cpu.arch for cpu in profile.cpus], ['m68000'])

    def test_an_install_with_one_slave_is_the_amigas(self):
        path = self.write(install('Game/Game.Slave'))
        self.assertIs(profile_for_path(path), get_profile('amiga'))
        self.assertIs(profile_for_path(path, 'amiga'), get_profile('amiga'))
        self.assertEqual(amiga.slave_member(path), 'Game/Game.Slave')

    def test_another_header_level_and_the_extension_case_do_not_matter(self):
        for name, blob in (('level0.LHA', level0('Game.Slave', hunk_file(slave_code())) + b'\x00'),
                           ('level2.lha', level2('Game.Slave', hunk_file(slave_code()), 'Game') + b'\x00')):
            with self.subTest(name):
                self.assertIs(profile_for_path(self.write(blob, name)), get_profile('amiga'))

    def test_choosing_another_console_is_a_mismatch(self):
        path = self.write(install('Game/Game.Slave'))
        with self.assertRaises(ConsoleMismatchError) as caught:
            profile_for_path(path, 'x68')
        self.assertEqual(caught.exception.detected_system, 'amiga')

    def test_the_input_carries_the_identity_of_the_archive(self):
        blob = install('Game/Game.Slave')
        path = self.write(blob)
        read = get_profile('amiga').read_rom(path)
        self.assertEqual(read.sha256, hashlib.sha256(blob).hexdigest())
        self.assertEqual((read.size, read.title, read.slave_path), (len(blob), 'Synthetic Game', 'Game/Game.Slave'))
        self.assertEqual((read.slave_version, read.kickemu, read.base_mem, read.exp_mem), (17, False, 0x80000, 0x1000))
        self.assertEqual(read.game_key, read.sha256)
        self.assertEqual(read.data(), blob)
        self.assertEqual(read.metadata()['format'], 'whdload-lha')
        self.assertEqual(read.metadata()['slave'], 'Game/Game.Slave')

    def test_an_install_that_wants_a_kickstart_is_read_and_flagged(self):
        read = amiga.read_input(self.write(install('Game/Game.Slave', kick=('kick34005.A500',))))
        self.assertTrue(read.kickemu)

    def test_the_archive_is_checked_again_when_its_bytes_are_asked_for(self):
        path = self.write(install('Game/Game.Slave'))
        read = amiga.read_input(path)
        path.write_bytes(install('Game/Game.Slave', data=(('Game/data/Disk.1', b'\x02' * 64),)))
        with self.assertRaises(ConversionError):
            read.data()

    def test_an_archive_without_a_slave_is_not_an_amiga_install(self):
        path = self.write(install(data=(('Game/data/Disk.1', b'\x01' * 64), ('Game/ReadMe', b'text'))))
        self.assertIsNone(amiga.slave_member(path))
        with self.assertRaisesRegex(UnsupportedConsoleError, 'no WHDLoad slave'):
            profile_for_path(path)

    def test_two_slaves_are_refused_not_guessed(self):
        path = self.write(install('Game/Game.Slave', 'Game/GameNTSC.Slave'))
        self.assertIsNone(amiga.slave_member(path))
        with self.assertRaises(UnsupportedConsoleError):
            profile_for_path(path)
        with self.assertRaises(ConversionError):
            amiga.read_input(path)

    def test_a_file_that_is_not_an_archive_is_refused(self):
        path = self.write(b'not an LHA archive at all')
        self.assertIsNone(amiga.slave_member(path))
        with self.assertRaises(UnsupportedConsoleError):
            profile_for_path(path)

    def test_an_installation_without_the_amiga_files_refuses_the_extension(self):
        path = self.write(install('Game/Game.Slave'))
        with patch('retrorecomp.amiga.converter_available', return_value=False):
            with self.assertRaisesRegex(UnsupportedConsoleError, 'unavailable'):
                profile_for_path(path)


class AvailabilityTests(unittest.TestCase):
    def test_the_profile_is_offered_only_when_its_converter_files_are_installed(self):
        needed = ('native/amiga_machine/CMakeLists.txt', 'native/amiga_whdload/rr_resload.c',
                  'native/hostkit/adapters/rrhk_amiga.inc')
        with TemporaryDirectory() as folder, patch('retrorecomp.amiga.ASSETS', Path(folder)):
            self.assertFalse(amiga.converter_available())
            for name in needed:
                path = Path(folder, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('synthetic marker')
                self.assertEqual(amiga.converter_available(), name == needed[-1])


    def test_the_slave_name_is_cleaned_into_a_name_for_its_box(self):
        from retrorecomp.amiga import cover_title
        self.assertEqual(cover_title('-* S P E E D B A L L  2 *-'), 'SPEEDBALL 2')
        self.assertEqual(cover_title('--> Pinball Dreams <--'), 'Pinball Dreams')
        self.assertEqual(cover_title('Lotus Turbo Challenge II'), 'Lotus Turbo Challenge II')
        self.assertEqual(cover_title('Dungeon Master (V3.6)'), 'Dungeon Master (V3.6)')
        self.assertEqual(cover_title(''), '')


class PackagedConverterTests(unittest.TestCase):
    def test_the_decoder_reads_the_generated_folder_of_the_working_root_not_the_unpacked_assets(self):
        # A packaged converter unpacks its files to a temporary ASSETS folder; the shared decoder folder
        # (.build/megadrive-step-decoder, written by megadrive_codegen.decoder_tool) is under ROOT, as for the X68000.
        source = Path(amiga.__file__).with_name('amiga_conversion.py').read_text(encoding='utf-8')
        call = source[source.index('m68k_observed.build_decoder('):]
        call = call[:call.index(')\n')]
        self.assertIn('root=ROOT', call)
        self.assertNotIn('root=ASSETS', call)


if __name__ == '__main__':
    unittest.main()
