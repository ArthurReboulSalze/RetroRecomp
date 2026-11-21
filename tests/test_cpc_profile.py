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


if __name__ == '__main__':
    unittest.main()
