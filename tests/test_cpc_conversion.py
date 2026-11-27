"""The Amstrad CPC conversion (retrorecomp/cpc_conversion.py) and the envelope's damaged states (retrorecomp/state_envelope.py), with no
ROM: what is refused before anything is built, and the list of states a game must refuse."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from retrorecomp import cpc_conversion, state_envelope
from retrorecomp.core import ConversionError
from retrorecomp.systems.amstrad_cpc import AMSTRAD_CPC
from tests.test_cpc_disk import image


class EnvelopeTests(unittest.TestCase):
    def test_every_header_field_the_binding_cuts_and_noise(self):
        state = bytes(range(256)) * 4
        variants = state_envelope.damaged_states(state)
        self.assertEqual(sorted(variants), ['binding', 'body-cut', 'crc', 'empty', 'header-cut', 'identity', 'length', 'machine',
                                            'magic', 'not-a-state', 'one-byte-short', 'payload', 'schema'])
        for label, offset in state_envelope.OFFSETS.items():
            with self.subTest(label=label):
                changed = [i for i, (a, b) in enumerate(zip(state, variants[label])) if a != b]
                self.assertEqual(changed, [offset])
        self.assertEqual(variants['one-byte-short'], state[:-1])
        self.assertEqual(state_envelope.HEADER, 88)

    def test_the_msx_list_has_the_same_labels(self):
        from retrorecomp import msx_conversion
        state = bytes(range(256)) * 4
        self.assertEqual(sorted(msx_conversion.damaged_states(state)), sorted(state_envelope.damaged_states(state)))


class ConversionRefusalTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def disk(self, files) -> Path:
        path = self.root / 'game.dsk'
        path.write_bytes(image(files=files))
        return path

    def test_a_disk_that_does_not_say_how_it_starts_is_refused(self):
        path = self.disk((('ONE', 'BIN', 2, False), ('TWO', 'BIN', 2, False)))
        with self.assertRaisesRegex(ConversionError, 'which program starts the game'):
            cpc_conversion.convert(path, output=self.root / 'out')
        self.assertFalse((self.root / 'out').exists())

    def test_the_firmware_is_fetched_when_the_player_gives_none_and_refused_when_wrong(self):
        from retrorecomp import cpc_roms
        path = self.disk((('DISC', 'BAS', 0, False),))
        with mock.patch.object(cpc_roms, 'fetch', side_effect=ValueError('The Amstrad CPC firmware could not be fetched')) as fetch:
            with self.assertRaisesRegex(ConversionError, 'could not be fetched'):
                cpc_conversion.convert(path, output=self.root / 'out')
        fetch.assert_called_once()
        wrong = self.root / 'wrong.rom'
        wrong.write_bytes(bytes(0x8000))
        with self.assertRaisesRegex(ConversionError, 'is not a CPC 6128 or 664 system ROM'):
            cpc_conversion.convert(path, output=self.root / 'out', cpc_system=wrong, cpc_amsdos=wrong)

    def test_a_route_too_short_for_the_quick_state_check_is_refused(self):
        path = self.disk((('DISC', 'BAS', 0, False),))
        with self.assertRaisesRegex(ConversionError, f'at least {cpc_conversion.MIN_FRAMES} frames'):
            cpc_conversion.convert(path, output=self.root / 'out', frames=300, firmware=(bytes(0x8000), bytes(0x4000)))

    def test_the_profile_hands_a_conversion_to_the_module(self):
        with mock.patch.object(cpc_conversion, 'convert', return_value=Path('game.exe')) as convert:
            self.assertEqual(AMSTRAD_CPC.convert(Path('x.dsk'), frames=900), Path('game.exe'))
        convert.assert_called_once_with(Path('x.dsk'), frames=900)
        self.assertTrue(AMSTRAD_CPC.available())                     # a development tree
        with mock.patch.object(sys, 'frozen', True, create=True):
            self.assertTrue(AMSTRAD_CPC.available())                 # and the packaged converter (supported)

    def test_the_firmware_record_is_one_the_lobby_compares(self):
        from retrorecomp.netplay import lobby_check
        system, amsdos = b'\x01' * 0x8000, b'\x02' * 0x4000
        record = cpc_conversion.firmware_identity(system, amsdos, {'cpc_system': {'origin': 'pinned'}, 'cpc_amsdos': {'origin': 'player'}})
        self.assertIn('firmware', lobby_check.FIRMWARE_KEYS)
        self.assertEqual(record['model'], 'cpc6128')
        self.assertEqual([(rom['name'], rom['bytes'], rom['origin']) for rom in record['roms']],
                         [('os', 0x4000, 'pinned'), ('basic', 0x4000, 'pinned'), ('amsdos', 0x4000, 'player')])
        import hashlib
        self.assertEqual(record['sha256'], hashlib.sha256(system + amsdos).hexdigest())   # OS, BASIC, AMSDOS concatenated
        one = lobby_check.firmware_digest({'firmware': record})
        other = lobby_check.firmware_digest({'firmware': cpc_conversion.firmware_identity(system, b'\x03' * 0x4000, {})})
        self.assertNotEqual(one, lobby_check.ZERO)
        self.assertNotEqual(one, other)                    # another AMSDOS: another firmware for the room
        self.assertEqual(one, lobby_check.firmware_digest({'firmware': cpc_conversion.firmware_identity(system, amsdos, {})}))
        source = Path(cpc_conversion.__file__).read_text(encoding='utf-8')
        self.assertIn("'firmware': firmware_identity(system, amsdos, firmware_record)", source)

    def test_the_report_keeps_the_five_measures_apart(self):
        source = Path(cpc_conversion.__file__).read_text(encoding='utf-8')
        for claim in ("'hardware_fidelity_validated': False", "'physical_latency_measured': False", "'full_game_validated': False",
                      "'cpu_fidelity_validated': False", "'universal_zero_fallback_claim': False"):
            self.assertIn(claim, source)


class DiskCopyTests(unittest.TestCase):
    """check_disk_copies on a fake game: what the --disk-copies runs would do, as the player does it (a copy of the disk's size is
    read at the start; drive A's bytes are written to the copy at the end when the game wrote)."""
    EMBEDDED, WRITTEN = 111, 222

    def fake_game(self, writes: bool, keeps: bool = True):
        def run_game(game, options, report):
            copies = Path(options[options.index('--disk-copies') + 1]) if '--disk-copies' in options else None
            copy = copies / 'disk-1.dsk' if copies else None
            start = self.WRITTEN if copy and copy.is_file() and copy.read_bytes() == b'disk' else self.EMBEDDED
            disk = start
            if writes and '--script' in options:
                disk = self.WRITTEN
                if copy:
                    copy.write_bytes(b'disk' if keeps else b'disc')
            return {'disk_start_fnv': start, 'disk_fnv': disk}
        return mock.patch('retrorecomp.cpc_build.run_game', side_effect=run_game)

    def check(self):
        with tempfile.TemporaryDirectory() as folder:
            return cpc_conversion.check_disk_copies(Path('game.exe'), Path(folder) / 'disk', 3600, ['--script', 'play.inputs'])

    def test_a_game_that_writes_leaves_a_copy_a_fresh_process_starts_from(self):
        with self.fake_game(writes=True):
            result = self.check()
        self.assertEqual((result['game_wrote'], result['copies_written'], result['written_data_survives_a_fresh_process']),
                         (True, ['disk-1.dsk'], True))

    def test_a_game_that_writes_nothing_leaves_no_copy(self):
        with self.fake_game(writes=False):
            result = self.check()
        self.assertEqual((result['game_wrote'], result['copies_written'], result['written_data_survives_a_fresh_process']),
                         (False, [], None))

    def test_a_copy_that_does_not_come_back_is_refused(self):
        with self.fake_game(writes=True, keeps=False), self.assertRaises(ConversionError):
            self.check()


if __name__ == '__main__':
    unittest.main()
