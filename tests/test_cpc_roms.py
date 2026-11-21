"""The Amstrad CPC firmware from its pinned source (retrorecomp/cpc_roms.py), with no network and no ROM: the four checks a fetched
file passes, the player's own files before the pinned ones, a fetch that fails with one sentence, and the pin's records."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from retrorecomp import cpc_firmware, cpc_roms


class PinTests(unittest.TestCase):
    def test_the_pin_and_its_files(self):
        self.assertEqual(cpc_roms.SOURCE_REPOSITORY, 'ColinPitrat/caprice32')
        self.assertRegex(cpc_roms.SOURCE_COMMIT, r'^[0-9a-f]{40}$')
        self.assertIn(cpc_roms.SOURCE_COMMIT, cpc_roms.SOURCE_URL)
        self.assertEqual({name: (option, size) for name, (option, size, _, _) in cpc_roms.FILES.items()},
                         {'cpc6128.rom': ('cpc_system', 0x8000), 'amsdos.rom': ('cpc_amsdos', 0x4000)})
        for name, (_, _, blob, sha256) in cpc_roms.FILES.items():
            with self.subTest(name=name):
                self.assertRegex(blob, r'^[0-9a-f]{40}$')
                self.assertTrue(sha256 is None or len(sha256) == 64)
        self.assertTrue(str(cpc_roms.directory()).replace('\\', '/').split('/')[-2:][0] == '.deps')

    def test_git_blob_names(self):
        # Git's own names: the empty file and "hello\n".
        self.assertEqual(cpc_roms.git_blob_sha1(b''), 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391')
        self.assertEqual(cpc_roms.git_blob_sha1(b'hello\n'), 'ce013625030ba8dba906f756967f9e9ca394464a')

    def test_the_licence_notice_is_a_game_notice(self):
        from retrorecomp.systems.amstrad_cpc import AMSTRAD_CPC
        self.assertIn('licenses/amstrad-cpc-roms.md', AMSTRAD_CPC.notice_files)
        text = cpc_roms.licence_text()
        self.assertIn(cpc_roms.SOURCE_COMMIT, text)
        self.assertIn('Locomotive', text)
        self.assertIn('21 November 2026', text)


class CheckTests(unittest.TestCase):
    """Stand-in files and digests: the real ones are numbers in the code, never bytes in the repository."""

    def setUp(self):
        self.system, self.amsdos = bytes(range(256)) * 128, b'\x5A' * 0x4000
        self.saved_files, self.saved_digests = dict(cpc_roms.FILES), dict(cpc_firmware.DIGESTS)
        cpc_roms.FILES['cpc6128.rom'] = ('cpc_system', 0x8000, cpc_roms.git_blob_sha1(self.system),
                                         hashlib.sha256(self.system).hexdigest())
        cpc_roms.FILES['amsdos.rom'] = ('cpc_amsdos', 0x4000, cpc_roms.git_blob_sha1(self.amsdos),
                                        hashlib.sha256(self.amsdos).hexdigest())
        cpc_firmware.DIGESTS[hashlib.sha1(self.system).hexdigest()] = ('cpc_system', 'stand-in 6128', 0)
        cpc_firmware.DIGESTS[hashlib.sha1(self.amsdos).hexdigest()] = ('cpc_amsdos', 'stand-in AMSDOS', 0)
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)

    def tearDown(self):
        cpc_roms.FILES.clear(); cpc_roms.FILES.update(self.saved_files)
        cpc_firmware.DIGESTS.clear(); cpc_firmware.DIGESTS.update(self.saved_digests)
        self.folder.cleanup()

    def test_each_check_refuses_on_its_own(self):
        self.assertIsNone(cpc_roms.problem('cpc6128.rom', self.system))
        self.assertIn('bytes', cpc_roms.problem('cpc6128.rom', self.system[:-1]))
        changed = bytearray(self.system); changed[100] ^= 1
        self.assertIn('pinned commit', cpc_roms.problem('cpc6128.rom', bytes(changed)))
        del cpc_firmware.DIGESTS[hashlib.sha1(self.system).hexdigest()]
        self.assertIn('MAME', cpc_roms.problem('cpc6128.rom', self.system))
        cpc_firmware.DIGESTS[hashlib.sha1(self.system).hexdigest()] = ('cpc_system', 'stand-in 6128', 0)
        option, size, blob, _ = cpc_roms.FILES['cpc6128.rom']
        cpc_roms.FILES['cpc6128.rom'] = (option, size, blob, '0' * 64)
        self.assertIn('SHA-256', cpc_roms.problem('cpc6128.rom', self.system))
        cpc_roms.FILES['cpc6128.rom'] = (option, size, blob, None)
        self.assertIn('SHA-256', cpc_roms.problem('cpc6128.rom', self.system))          # no pinned SHA-256: never accepted

    def test_the_players_files_first_then_the_pinned_ones(self):
        pinned = self.root / 'pinned'
        pinned.mkdir()
        (pinned / 'cpc6128.rom').write_bytes(self.system)
        (pinned / 'amsdos.rom').write_bytes(self.amsdos)
        own = self.root / 'mine.rom'
        own.write_bytes(self.amsdos)
        with mock.patch.object(cpc_roms, 'fetch', return_value=pinned) as fetch:
            found = cpc_roms.firmware_for({'cpc_amsdos': str(own)}, emit=lambda text: None)
        fetch.assert_called_once()
        self.assertEqual((found.system, found.amsdos), (self.system, self.amsdos))
        self.assertEqual((found.record['cpc_system']['origin'], found.record['cpc_amsdos']['origin']), ('pinned', 'player'))
        with mock.patch.object(cpc_roms, 'fetch') as fetch:
            mine = self.root / 'sys.rom'
            mine.write_bytes(self.system)
            found = cpc_roms.firmware_for({'cpc_system': str(mine), 'cpc_amsdos': str(own)})
        fetch.assert_not_called()                                                         # nothing fetched when both are given
        self.assertEqual({part['origin'] for part in found.record.values()}, {'player'})
        bad = self.root / 'bad.rom'
        bad.write_bytes(b'\0' * 0x4000)
        with self.assertRaises(ValueError):
            cpc_roms.firmware_for({'cpc_system': str(mine), 'cpc_amsdos': str(bad)})

    def test_a_fetch_checks_what_it_received_and_fails_with_one_sentence(self):
        folder = self.root / 'cache'

        def wrong_download(url, partial, *args, **kwargs):
            partial.write_bytes(b'\0' * 0x8000 if url.endswith('cpc6128.rom') else self.amsdos)
        with mock.patch.object(cpc_roms, 'directory', return_value=folder), \
                mock.patch('retrorecomp.updater.download_pinned', side_effect=wrong_download):
            with self.assertRaisesRegex(ValueError, 'could not be fetched.*own system ROM and AMSDOS ROM in Options'):
                cpc_roms.fetch(emit=lambda text: None)
        self.assertFalse((folder / 'cpc6128.rom').exists())
        self.assertFalse(list(folder.glob('*.part')))

        def right_download(url, partial, *args, **kwargs):
            partial.write_bytes(self.system if url.endswith('cpc6128.rom') else self.amsdos)
        with mock.patch.object(cpc_roms, 'directory', return_value=folder), \
                mock.patch('retrorecomp.updater.download_pinned', side_effect=right_download) as download:
            self.assertEqual(cpc_roms.fetch(emit=lambda text: None), folder)
            self.assertEqual(download.call_count, 2)
            self.assertTrue(all(call.args[0].startswith(cpc_roms.SOURCE_URL) for call in download.call_args_list))
            cpc_roms.fetch(emit=lambda text: None)                                         # checked on disk: not fetched again
            self.assertEqual(download.call_count, 2)


if __name__ == '__main__':
    unittest.main()
