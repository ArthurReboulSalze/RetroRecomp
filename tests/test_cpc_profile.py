"""The Amstrad CPC profile (in development): recognition of its disks before the MSX2+, its firmware, its refusal."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from retrorecomp import cpc_firmware
from retrorecomp.systems import ConsoleMismatchError, UnsupportedConsoleError, get_profile, profile_for_path
from tests.test_cpc_disk import image


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def test_the_profile(self):
        profile = get_profile('cpc')
        self.assertEqual((profile.name, profile.status, profile.linux, profile.developer_only, profile.available()),
                         ('Amstrad CPC', 'experimental', 'pending', True, False))
        self.assertEqual(profile.option_key_names, {'cpc_system', 'cpc_amsdos'})

    def test_a_cpc_disk_is_the_cpcs_and_refused_while_in_development(self):
        disk = self.root / 'Game.dsk'
        disk.write_bytes(image((('DISC', 'BAS', 0, False),)))
        with self.assertRaisesRegex(UnsupportedConsoleError, 'Amstrad CPC'):
            profile_for_path(disk)
        with self.assertRaises(ConsoleMismatchError):
            profile_for_path(disk, 'msx2plus')
        self.assertEqual(get_profile('cpc').read_rom(disk).run_command, 'RUN"DISC')

    def test_a_zipped_cpc_disk_too(self):
        archive = self.root / 'Game (Europe).zip'
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('Game (E).dsk', image())
        with self.assertRaisesRegex(UnsupportedConsoleError, 'Amstrad CPC'):
            profile_for_path(archive)

    def test_an_msx_disk_is_left_to_the_msx2plus(self):
        disk = self.root / 'msx.dsk'
        disk.write_bytes(bytes(368640))
        self.assertEqual(profile_for_path(disk).id, 'msx2plus')

    def test_the_firmware_is_known_by_its_digest_only(self):
        unknown = self.root / 'os.rom'
        unknown.write_bytes(bytes(0x8000))
        self.assertIsNone(cpc_firmware.identify(unknown))
        with self.assertRaisesRegex(ValueError, 'system ROM'):
            cpc_firmware.own_firmware('cpc_system', unknown)
        with self.assertRaisesRegex(ValueError, 'your own'):
            cpc_firmware.own_firmware('cpc_system', None)
        self.assertEqual({option for option, _, _ in cpc_firmware.DIGESTS.values()}, {'cpc_system', 'cpc_amsdos'})
        self.assertTrue(all(len(digest) == 40 for digest in cpc_firmware.DIGESTS))

    def test_a_known_digest_is_recognised(self):
        # The table is keyed by SHA-1: a file whose digest is in it (here a stand-in entry) is recognised with its option.
        data = b'\x01' * 0x4000
        digest = hashlib.sha1(data).hexdigest()
        path = self.root / 'amsdos.rom'
        path.write_bytes(data)
        saved = dict(cpc_firmware.DIGESTS)
        try:
            cpc_firmware.DIGESTS[digest] = ('cpc_amsdos', 'test', 0)
            found = cpc_firmware.own_firmware('cpc_amsdos', path)
            self.assertEqual((found.option, found.sha256), ('cpc_amsdos', hashlib.sha256(data).hexdigest()))
            with self.assertRaises(ValueError):
                cpc_firmware.own_firmware('cpc_system', path)
            from retrorecomp import firmware_search
            self.assertEqual([hit[0] for hit in firmware_search._cpc(path)], ['cpc_amsdos'])
        finally:
            cpc_firmware.DIGESTS.clear()
            cpc_firmware.DIGESTS.update(saved)

    def test_the_system_rom_in_two_halves_beside_each_other(self):
        # Clock Signal's layout (os6128.rom, basic6128.rom) and any other names: the OS half followed by a 16 KiB neighbour gives
        # a system ROM of the table (here a stand-in entry). The option names the OS half; its data is the whole 32 KiB.
        os_half, basic_half = bytes(range(256)) * 64, b'\x80' * 0x4000
        folder = self.root / 'AmstradCPC'
        folder.mkdir()
        (folder / 'os6128.rom').write_bytes(os_half)
        (folder / 'basic6128.rom').write_bytes(basic_half)
        (folder / 'other.rom').write_bytes(b'\x55' * 0x4000)                 # a 16 KiB neighbour that is not BASIC
        lone = self.root / 'lone'
        lone.mkdir()
        (lone / 'os6128.rom').write_bytes(os_half)                          # an OS half with no BASIC half beside it
        saved = dict(cpc_firmware.DIGESTS)
        try:
            cpc_firmware.DIGESTS[hashlib.sha1(os_half + basic_half).hexdigest()] = ('cpc_system', 'test 6128', 0)
            found = cpc_firmware.own_firmware('cpc_system', folder / 'os6128.rom')
            self.assertEqual((found.option, found.data, found.sha256),
                             ('cpc_system', os_half + basic_half, hashlib.sha256(os_half + basic_half).hexdigest()))
            self.assertIn('basic6128.rom', found.label)
            self.assertIsNone(cpc_firmware.identify(folder / 'basic6128.rom'))     # the BASIC half alone is no system ROM
            self.assertIsNone(cpc_firmware.identify(lone / 'os6128.rom'))
            renamed = self.root / 'renamed'
            renamed.mkdir()
            (renamed / 'a.bin').write_bytes(os_half)
            (renamed / 'b.bin').write_bytes(basic_half)
            self.assertIsNotNone(cpc_firmware.identify(renamed / 'a.bin'))       # by content, whatever the names
            from retrorecomp import firmware_search
            result = firmware_search.search(self.root)
            self.assertEqual(sorted(hit.path.name for hit in result.hits.get('cpc_system', [])), ['a.bin', 'os6128.rom'])
            self.assertEqual({hit.digest for hit in result.hits['cpc_system']}, {found.sha256})
        finally:
            cpc_firmware.DIGESTS.clear()
            cpc_firmware.DIGESTS.update(saved)
            cpc_firmware._folder_halves.cache_clear()


if __name__ == '__main__':
    unittest.main()
