"""The Game Boy Advance profile, stage 2: a synthetic cartridge (no ROM, no BIOS) through every entry point it has.

The cartridge is authored here: a header whose fixed byte and checksum are right, a few bytes of text, nothing from a game.
"""
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from retrorecomp import (batch, compilation_inputs, gba, gba_conversion, path_profiles, report_schema, scan_levels,
                         upstreams)
from retrorecomp.core import ConversionError
from retrorecomp.i18n import STRINGS, catalog
from retrorecomp.systems import (ALL_PROFILES, ConsoleMismatchError, UnsupportedConsoleError, find_profile,
                                 get_profile, profile_for_path, system_ids)


def synthetic_cartridge(size=0x400, save=b'', title=b'AUTHORED', code=b'ATSE') -> bytes:
    data = bytearray(size)
    data[0:4] = bytes((0x2E, 0x00, 0x00, 0xEA))
    data[0xA0:0xA0 + len(title)] = title
    data[0xAC:0xB0] = code
    data[0xB0:0xB2] = b'01'
    data[0xB2] = 0x96
    data[0xBD] = gba.complement_check(bytes(data))
    if save:
        data[0x200:0x200 + len(save)] = save
    return bytes(data)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def cartridge(self, name='Authored (World).gba', **options):
        path = self.root / name
        path.write_bytes(synthetic_cartridge(**options))
        return path

    def test_the_header_is_read_and_the_save_chip_named(self):
        for signature, expected in ((b'', 'none'), (b'SRAM_V113', 'sram'), (b'FLASH_V126', 'flash64'),
                                    (b'FLASH512_V131', 'flash64'), (b'FLASH1M_V103', 'flash128'),
                                    (b'EEPROM_V124', 'eeprom')):
            rom = gba.read_rom(self.cartridge(save=signature))
            self.assertEqual((rom.header_title, rom.game_code, rom.save_type), ('AUTHORED', 'ATSE', expected), signature)
        rom = gba.read_rom(self.cartridge())
        self.assertEqual(rom.size, 0x400)
        self.assertEqual(rom.metadata()['system_id'], 'gba')
        self.assertEqual(len(rom.sha256), 64)

    def test_flash_one_megabyte_is_not_read_as_flash_64(self):
        self.assertEqual(gba.save_type(b'xx FLASH1M_V103 xx')[0], 'flash128')

    def test_a_zip_with_one_cartridge_is_read_without_extracting_it(self):
        archive = self.root / 'Authored.zip'
        with zipfile.ZipFile(archive, 'w') as out:
            out.writestr('Authored (World).gba', synthetic_cartridge(save=b'SRAM_V113'))
        rom = gba.read_rom(archive)
        self.assertEqual(rom.save_type, 'sram')
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ['Authored.zip'])
        self.assertTrue(gba.zip_holds_cartridge(archive))
        two = self.root / 'Two.zip'
        with zipfile.ZipFile(two, 'w') as out:
            out.writestr('a.gba', synthetic_cartridge())
            out.writestr('b.gba', synthetic_cartridge())
        self.assertFalse(gba.zip_holds_cartridge(two))
        with self.assertRaises(ConversionError):
            gba.read_rom(two)

    def test_what_is_not_a_cartridge_is_refused(self):
        bad = bytearray(synthetic_cartridge())
        bad[0xBD] ^= 0xFF
        path = self.root / 'Bad.gba'
        path.write_bytes(bytes(bad))
        with self.assertRaises(ConversionError):
            gba.read_rom(path)
        path.write_bytes(b'not a cartridge' * 100)
        with self.assertRaises(ConversionError):
            gba.read_rom(path)
        path.write_bytes(b'\0' * 16)
        with self.assertRaises(ConversionError):
            gba.read_rom(path)

    def test_the_bios_is_only_hashed_and_a_stranger_is_unknown(self):
        missing = self.root / 'none.bin'
        self.assertEqual(gba.bios_status(str(missing)), 'missing')
        self.assertIsNone(gba.bios_identity(str(missing)))
        stranger = self.root / 'gba_bios.bin'
        stranger.write_bytes(bytes(gba.BIOS_BYTES))
        self.assertEqual(gba.bios_status(str(stranger)), 'unknown')
        self.assertEqual(len(gba.bios_identity(str(stranger))), 64)
        self.assertEqual(gba.KNOWN_BIOS_SHA1, '300c20df6731a33952ded8c436f7f186d25d3492')


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'Authored (World).gba'
        self.path.write_bytes(synthetic_cartridge(save=b'EEPROM_V124'))

    def test_the_profile_is_registered_experimental_and_developer_only(self):
        profile = get_profile('gba')
        self.assertIn(profile, ALL_PROFILES)
        self.assertEqual((profile.status, profile.developer_only, profile.linux), ('experimental', True, 'pending'))
        self.assertEqual([(cpu.arch, cpu.role, cpu.unit) for cpu in profile.cpus], [('arm7tdmi', 'main', 'instructions')])
        self.assertEqual(profile.firmware, ('bios',))
        self.assertFalse(profile.available())

    def test_an_installation_without_the_files_says_so_instead_of_unknown_console(self):
        with self.assertRaises(UnsupportedConsoleError) as caught:
            profile_for_path(self.path)
        self.assertIn('unavailable', str(caught.exception))
        item = batch.identify(self.path)
        self.assertTrue(item.error)

    def test_a_cartridge_is_identified_by_every_entry_point_when_the_machine_is_available(self):
        with patch('retrorecomp.gba.developer_available', return_value=True):
            self.assertEqual(profile_for_path(self.path).id, 'gba')
            self.assertEqual(profile_for_path(self.path, 'gba').id, 'gba')
            with self.assertRaises(ConsoleMismatchError):
                profile_for_path(self.path, 'sms')
            item = batch.identify(self.path)
            self.assertEqual((item.system, item.title, item.error), ('gba', 'Authored', ''))
            archive = self.path.with_suffix('.zip')
            with zipfile.ZipFile(archive, 'w') as out:
                out.writestr('Authored (World).gba', synthetic_cartridge())
            self.assertEqual(profile_for_path(archive).id, 'gba')
            # A ZIP of another machine is not claimed.
            other = self.path.parent / 'Other.zip'
            with zipfile.ZipFile(other, 'w') as out:
                out.writestr('readme.txt', b'no cartridge')
            with self.assertRaises(UnsupportedConsoleError):
                profile_for_path(other)

    def test_a_conversion_without_the_players_bios_says_what_is_missing(self):
        with self.assertRaises(ConversionError) as caught:
            get_profile('gba').convert(self.path)
        self.assertIn('needs your own BIOS', str(caught.exception))

    def test_the_request_identity_carries_the_bios_hash_not_its_path(self):
        profile = get_profile('gba')
        settings = {'gba_bios': 'secret/path.bin'}
        profile.request_identity(None, {'gba_bios': str(Path(self.folder.name) / 'absent.bin')}, settings)
        self.assertEqual(settings, {'bios': None})


class SharedPiecesTests(unittest.TestCase):
    def test_the_paths_section_is_keyed_by_cpu_and_validated(self):
        game = 'gba:' + 'ab' * 32
        entries = path_profiles.encode_table([[0x100], [0x201], [0x4000]], 1)
        spans = path_profiles.encode_table([[0x03000100, 0x400, 0x40]], 3)
        record = {'schema': 3, 'game': game,
                  'identity': {'system': 'gba', 'sources': {'rom': {'bytes': 0x400000, 'sha256': 'ab' * 32}}, 'layout': {}},
                  'cpus': {'arm7tdmi': {'map': 'gba', 'core': 'c' * 40,
                                        'paths': {'entries': [{'shape': 'phys', 'src': 'rom', 'table': entries}],
                                                  'spans': [{'shape': 'span', 'src': 'rom', 'table': spans}]}}},
                  'devices': {}}
        self.assertIs(path_profiles.validate_game(record), record)
        self.assertEqual(path_profiles.SYSTEM_SECTIONS['gba'], (('arm7tdmi', 'gba'),))
        self.assertNotIn('gba', path_profiles.SHARED_SYSTEMS)
        # A routine copied somewhere that is not IWRAM or EWRAM is refused.
        record['cpus']['arm7tdmi']['paths']['spans'][0]['table'] = path_profiles.encode_table([[0x04000000, 0x400, 0x40]], 3)
        with self.assertRaises(ValueError):
            path_profiles.validate_game(record)

    def test_the_report_goes_through_the_common_builder_and_claims_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Authored.gba'
            path.write_bytes(synthetic_cartridge(save=b'SRAM_V113'))
            source = gba.read_rom(path)
            written = gba_conversion.write_skeleton_report(Path(folder) / 'conversion-report.json', source,
                                                           [('boot', 600, 1000, 4)])
            report = report_schema.read_report(Path(folder) / 'conversion-report.json')
        self.assertEqual(written['schema'], {'name': 'retro-recomp-report', 'version': 2})
        self.assertEqual(report['system'], {'id': 'gba', 'name': 'Game Boy Advance', 'status': 'experimental'})
        self.assertEqual(report['cpus'][0]['arch'], 'arm7tdmi')
        self.assertEqual(report['cpus'][0]['scenarios'][0]['interpreted'], 4)
        self.assertEqual(report_schema.fallback_summary(report)['main_interpreted_opcodes'], 4)
        self.assertFalse(report['validation']['hardware_fidelity']['validated'])
        cpu = report['validation']['cpu_fidelity']
        self.assertIsNone(cpu['passed'])
        self.assertEqual((cpu['validated_flag'], cpu['claim']), (False, 'not reported'))

    def test_stamps_classify_the_new_files_and_no_other_console_owns_them(self):
        names = compilation_inputs.manifest_names('gba')
        for name in ('retrorecomp.gba', 'retrorecomp.gba_conversion', 'retrorecomp.systems.gba', 'licenses/gbarecomp.md'):
            self.assertIn(name, names)
        for other in ('sms', 'gb', 'nes', 'md', 'snes', 'ng', 'x68', 'cps1'):
            self.assertNotIn('retrorecomp.gba', compilation_inputs.manifest_names(other), other)
        self.assertEqual(compilation_inputs.role('retrorecomp.gba'), 'game')
        self.assertEqual(set(compilation_inputs.role_stamps('gba')), {'game', 'host', 'build'})

    def test_the_engine_is_pinned_and_declared(self):
        keys = {item.key for item in upstreams.MACHINE_UPSTREAMS['gba']}
        self.assertEqual(keys, {'gbarecomp', 'arm-recomp-core'})
        engine = next(item for item in upstreams.MACHINE_UPSTREAMS['gba'] if item.key == 'gbarecomp')
        self.assertEqual(upstreams.pin_of(engine), gba_conversion.ENGINE_REV)
        self.assertRegex(gba_conversion.ENGINE_REV, r'^[0-9a-f]{40}$')
        self.assertRegex(gba_conversion.ARM_CORE_REV, r'^[0-9a-f]{40}$')

    def test_scan_levels_and_translations_follow_the_profile(self):
        self.assertIn('gba', scan_levels.CONSOLES)
        self.assertEqual(scan_levels.DEFAULT_FRAMES['gba'], get_profile('gba').default_frames)
        for key in ('options_gba', 'options_gba_note', 'scan_note_gba', 'gba_bios'):
            self.assertIn(key, STRINGS)
            for code in ('it', 'es', 'de', 'zh', 'ja', 'ru'):
                self.assertIn(key, catalog(code)['ui'], (key, code))
        self.assertIn('gba', system_ids())
        self.assertIsNotNone(find_profile('gba'))


if __name__ == '__main__':
    unittest.main()
