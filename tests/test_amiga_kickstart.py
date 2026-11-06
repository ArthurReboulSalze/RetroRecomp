"""The player's Kickstart: normalisation, identification, matching, the install's request and the texts, on images authored by
the test (pseudo-random bytes behind a Kickstart-like start: no Commodore code, no real Kickstart, no game). Nothing here
reads the converter's settings or a file outside the temporary folders."""
import hashlib
import random
import struct
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from retrorecomp import amiga_kickstart as K
from retrorecomp import amiga_lha
from retrorecomp.i18n import tr
from retrorecomp.systems import get_profile
from tests.test_amiga_lha import level1
from tests.test_amiga_whdload import hunk_file, slave_code

START = bytes.fromhex('11114ef900fc00d2')       # $1111, jmp $00FC00D2: what the start of a 1.x Kickstart looks like
START_31 = bytes.fromhex('11144ef900f800d2')    # $1114, jmp $00F800D2


def image(seed, size=K.SIZES[0], start=START):
    return start + random.Random(seed).randbytes(size - len(start))


def swapped(data):
    out = bytearray(data)
    out[0::2], out[1::2] = data[1::2], data[0::2]
    return bytes(out)


def cloanto(data, key):
    stream = (key * (len(data) // len(key) + 1))[:len(data)]
    return K.CLOANTO_TAG + bytes(a ^ b for a, b in zip(data, stream))


KEY = bytes(random.Random(99).randbytes(37))     # an authored key, nothing of Amiga Forever's
PLAIN = image(1)
FAKE_13 = {'version': '34.005', 'os': '1.3', 'model': 'A500', 'name': 'kick34005.A500'}


def knows(data, info=FAKE_13):
    """Register the authored image as a known version for the duration of a test (the real table lists real images)."""
    return patch.dict(K.KNOWN, {(len(data), zlib.crc32(data) & 0xFFFFFFFF): info})


class NormaliseTests(unittest.TestCase):
    def test_a_plain_image_is_left_alone(self):
        self.assertEqual(K.normalise(PLAIN), (PLAIN, []))
        big = image(2, K.SIZES[1], START_31)
        self.assertEqual(K.normalise(big), (big, []))

    def test_a_256_kib_image_doubled_in_a_512_kib_file_is_undoubled(self):
        self.assertEqual(K.normalise(PLAIN + PLAIN), (PLAIN, [K.UNDOUBLED]))

    def test_a_512_kib_image_whose_halves_differ_stays_whole(self):
        data = image(3, K.SIZES[1], START_31)
        self.assertNotEqual(data[:K.SIZES[0]], data[K.SIZES[0]:])
        self.assertEqual(K.normalise(data)[1], [])

    def test_a_byte_swapped_dump_is_recognised_by_its_swapped_start(self):
        self.assertEqual(K.normalise(swapped(PLAIN)), (PLAIN, [K.SWAPPED]))
        big = image(4, K.SIZES[1], START_31)
        self.assertEqual(K.normalise(swapped(big)), (big, [K.SWAPPED]))
        self.assertEqual(K.normalise(swapped(PLAIN + PLAIN)), (PLAIN, [K.SWAPPED, K.UNDOUBLED]))

    def test_a_cloanto_file_needs_its_key_and_is_decrypted_in_memory(self):
        sealed = cloanto(PLAIN, KEY)
        self.assertEqual(len(sealed), K.SIZES[0] + 11)
        self.assertEqual(K.normalise(sealed, KEY), (PLAIN, [K.CLOANTO]))
        with self.assertRaises(K.KickstartError) as caught:
            K.normalise(sealed)
        self.assertEqual(caught.exception.code, 'cloanto_key_missing')
        with self.assertRaises(K.KickstartError) as caught:
            K.normalise(sealed, bytes(reversed(KEY)))
        self.assertEqual(caught.exception.code, 'cloanto_key_wrong')

    def test_what_is_no_kickstart_is_refused_with_its_size(self):
        for data in (b'', b'\x00' * 1000, bytes(K.SIZES[0]), b'\x4e\xf9' + bytes(K.SIZES[0] - 2)):
            with self.subTest(size=len(data)):
                with self.assertRaises(K.KickstartError) as caught:
                    K.normalise(data)
                self.assertEqual((caught.exception.code, caught.exception.params), ('not_kickstart', {'size': len(data)}))

    def test_the_crc16_is_the_lha_one(self):
        self.assertIs(K.crc16, amiga_lha.crc16)
        self.assertEqual(K.crc16(b'123456789'), 0xBB3D)    # the published check value of CRC-16/ARC


class FolderCase(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def put(self, name, data):
        path = self.folder / name
        path.write_bytes(data)
        return path


class IdentifyTests(FolderCase):
    def test_a_file_gives_one_record_with_its_hashes(self):
        path = self.put('whatever.name', PLAIN)
        with knows(PLAIN):
            (record,) = K.identify(path)
        self.assertEqual((record.path, record.file_name, record.size), (path, 'whatever.name', K.SIZES[0]))
        self.assertEqual((record.sha256, record.crc16), (hashlib.sha256(PLAIN).hexdigest(), amiga_lha.crc16(PLAIN)))
        self.assertEqual(record.crc32, zlib.crc32(PLAIN))
        self.assertEqual(record.version, FAKE_13)
        self.assertEqual(record.normalisations, ())

    def test_an_unknown_version_is_a_record_without_version_info(self):
        (record,) = K.identify(self.put('k.rom', PLAIN))
        self.assertIsNone(record.version)
        self.assertEqual(record.label(), '256 KiB')

    def test_a_folder_is_read_by_content_not_by_name(self):
        other, third = image(5), image(6, K.SIZES[1], START_31)
        self.put('notes.txt', swapped(other))                  # a Kickstart under a name that says nothing
        self.put('kick.rom', PLAIN)
        self.put('amiga-os-310.rom', cloanto(third, KEY))
        self.put('ROM.KEY', KEY)                               # the key is found whatever its case, and is no candidate
        self.put('tiny.bin', b'\x00' * 100)                    # not a candidate size: not mentioned
        self.put('noise.rom', bytes(K.SIZES[0]))               # a candidate size, no Kickstart start: refused
        (self.folder / 'sub').mkdir()
        (self.folder / 'sub' / 'deep.rom').write_bytes(image(7))   # not recursive
        scan = K.scan(self.folder)
        by_name = {r.file_name: r for r in scan.records}
        self.assertEqual(sorted(by_name), ['amiga-os-310.rom', 'kick.rom', 'notes.txt'])
        self.assertEqual(by_name['notes.txt'].sha256, hashlib.sha256(other).hexdigest())
        self.assertEqual(by_name['notes.txt'].normalisations, (K.SWAPPED,))
        self.assertEqual(by_name['amiga-os-310.rom'].normalisations, (K.CLOANTO,))
        self.assertEqual(by_name['amiga-os-310.rom'].size, K.SIZES[1])
        self.assertEqual(by_name['amiga-os-310.rom'].sha256, hashlib.sha256(third).hexdigest())
        self.assertEqual([(r.file_name, r.code) for r in scan.rejected], [('noise.rom', 'not_kickstart')])
        self.assertEqual(K.identify(self.folder), list(scan.records))

    def test_a_cloanto_file_without_its_key_is_reported(self):
        self.put('sealed.rom', cloanto(PLAIN, KEY))
        scan = K.scan(self.folder)
        self.assertEqual(scan.records, ())
        self.assertEqual([(r.file_name, r.code) for r in scan.rejected], [('sealed.rom', 'cloanto_key_missing')])
        self.put('rom.key', KEY)
        (record,) = K.scan(self.folder).records
        self.assertEqual(record.sha256, hashlib.sha256(PLAIN).hexdigest())

    def test_a_single_file_that_is_no_kickstart_says_why(self):
        small = self.put('small.bin', b'abc')
        (refused,) = K.scan(small).rejected
        self.assertEqual((refused.code, refused.params), ('not_kickstart', {'size': 3}))
        with self.assertRaises(OSError):
            K.scan(self.folder / 'missing.rom')

    def test_the_image_is_read_again_and_checked(self):
        path = self.put('sealed.rom', cloanto(PLAIN, KEY))
        self.put('rom.key', KEY)
        (record,) = K.identify(path)
        self.assertEqual(K.read_image(record), PLAIN)
        path.write_bytes(cloanto(image(8), KEY))
        with self.assertRaises(K.KickstartError):
            K.read_image(record)


class MatchTests(FolderCase):
    def test_a_request_is_matched_by_size_and_crc16(self):
        path = self.put('a.rom', PLAIN)
        records = K.identify(path) + K.identify(self.put('b.rom', image(9, K.SIZES[1], START_31)))
        crc = amiga_lha.crc16(PLAIN)
        self.assertIs(K.match(records, K.SIZES[0], crc), records[0])
        self.assertIsNone(K.match(records, K.SIZES[1], crc))
        self.assertIsNone(K.match(records, K.SIZES[0], crc ^ 1))
        self.assertIsNone(K.match([], K.SIZES[0], crc))

    def test_the_first_accepted_entry_the_player_can_satisfy_wins(self):
        (record,) = K.identify(self.put('a.rom', PLAIN))
        crc = amiga_lha.crc16(PLAIN)
        wanted = [{'name': 'kick33180.A500', 'size': K.SIZES[0], 'crc16': crc ^ 7},
                  {'name': 'kick34005.A500', 'size': K.SIZES[0], 'crc16': crc}]
        self.assertEqual(K.request_for(wanted, [record]), (wanted[1], record))
        self.assertIsNone(K.request_for(wanted[:1], [record]))


def patched_slave(version=17, kick=None, crc=None, call=None, odd=False):
    """The code of an authored slave. `crc` replaces ws_kickcrc of a single-name header; `call` appends the two words of a
    jsr/jmp d16(An) with d16 = $68 (at an odd offset when `odd`, where it is no instruction)."""
    code = bytearray(slave_code(version=version, kick=kick))
    if crc is not None:
        struct.pack_into('>H', code, 48, crc)
    if call is not None:
        code += (b'\x00' if odd else b'') + struct.pack('>HH', call, 0x68) + (b'\x00' * 3 if odd else b'')
    return bytes(code)


class RequestTests(unittest.TestCase):
    def test_a_header_request_with_one_image(self):
        request = K.request_of_slave(hunk_file(slave_code(kick=('kick34005.A500',))))
        self.assertEqual((request.mode, request.title, request.ws_version), ('header', 'Synthetic Game', 17))
        self.assertEqual(request.accepted, ({'name': 'kick34005.A500', 'size': 0x40000, 'crc16': 0x1234},))

    def test_a_header_request_with_a_table_of_images(self):
        request = K.request_of_slave(hunk_file(slave_code(kick=('kick33180.A500', 'kick34005.A500'))))
        self.assertEqual(request.mode, 'header')
        self.assertEqual([(e['name'], e['crc16']) for e in request.accepted],
                         [('kick33180.A500', 0x1111), ('kick34005.A500', 0x2222)])

    def test_no_request_without_header_or_call(self):
        self.assertEqual(K.request_of_slave(hunk_file(slave_code())).mode, '')

    def test_a_loadkick_call_is_found_by_its_pattern(self):
        for call in (0x4EA8 + 5, 0x4EA8, 0x4EE8 + 1):      # jsr $68(a5), jsr $68(a0), jmp $68(a1)
            with self.subTest(call=hex(call)):
                request = K.request_of_slave(hunk_file(patched_slave(call=call)))
                self.assertEqual((request.mode, request.accepted), ('resload_LoadKick', ()))
        both = K.request_of_slave(hunk_file(patched_slave(kick=('kick34005.A500',), call=0x4EAD)))
        self.assertEqual(both.mode, 'both')

    def test_other_displacements_odd_offsets_and_old_slaves_are_not_calls(self):
        self.assertEqual(K.request_of_slave(hunk_file(patched_slave(call=0x4EAD, odd=True))).mode, '')
        self.assertEqual(K.request_of_slave(hunk_file(patched_slave(version=10, call=0x4EAD))).mode, '')
        other = bytearray(patched_slave(call=0x4EAD))
        other[-1] = 0x6C                                   # jsr $6C(a5) is another call
        self.assertEqual(K.request_of_slave(hunk_file(bytes(other))).mode, '')


class InstallCase(FolderCase):
    def archive(self, code, name='Synthetic.lha', slaves=('Game/Game.Slave',)):
        blob = b''.join(level1(slave, hunk_file(code)) for slave in slaves) + level1('Game/data/Disk.1', b'\x01' * 64) + b'\x00'
        path = self.folder / name
        path.write_bytes(blob)
        return path

    def kicks(self, *images):
        folder = self.folder / 'kicks'
        folder.mkdir(exist_ok=True)
        for number, data in enumerate(images):
            (folder / f'k{number}.rom').write_bytes(data)
        return folder


class NeedsTests(InstallCase):
    def test_header_and_call_installs_need_one_the_others_do_not(self):
        self.assertTrue(K.path_needs_kickstart(self.archive(slave_code(kick=('kick34005.A500',)), 'header.lha')))
        self.assertTrue(K.path_needs_kickstart(self.archive(patched_slave(call=0x4EAD), 'call.lha')))
        self.assertFalse(K.path_needs_kickstart(self.archive(slave_code(), 'none.lha')))

    def test_everything_that_cannot_be_read_needs_none(self):
        self.assertFalse(K.path_needs_kickstart(self.folder / 'missing.lha'))
        (self.folder / 'text.lha').write_bytes(b'not an archive')
        self.assertFalse(K.path_needs_kickstart(self.folder / 'text.lha'))
        # several slaves: the profile refuses them, so no request is read
        two = self.archive(slave_code(kick=('kick34005.A500',)), 'two.lha', slaves=('A/A.Slave', 'B/B.Slave'))
        self.assertFalse(K.path_needs_kickstart(two))
        self.assertIsNone(K.kickstart_request(two))

    def test_the_request_of_an_archive_names_the_game(self):
        request = K.kickstart_request(self.archive(slave_code(kick=('kick34005.A500',))))
        self.assertEqual((request.title, request.mode), ('Synthetic Game', 'header'))


class RequireTests(InstallCase):
    def install_for(self, data, name='Synthetic.lha'):
        """An install whose header accepts exactly the authored image `data`."""
        return self.archive(patched_slave(kick=('kick34005.A500',), crc=amiga_lha.crc16(data)), name)

    def test_an_install_without_a_request_needs_nothing(self):
        self.assertIsNone(K.require(None, self.archive(slave_code())))
        self.assertIsNone(K.require('', self.archive(slave_code(), 'b.lha')))

    def test_the_blocked_message_names_the_image(self):
        archive = self.install_for(PLAIN)
        wanted = '1.3 (34.005, 256 KiB, kick34005.A500)'
        for option in (None, '', str(self.folder / 'nowhere'), str(self.kicks(image(10)))):
            with self.subTest(option=option):
                with self.assertRaises(ValueError) as caught:
                    K.require(option, archive)
                self.assertEqual(str(caught.exception), tr('amiga_kickstart_required', 'en', game='Synthetic Game', wanted=wanted))
        self.assertIn(wanted, str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            K.require(None, archive, 'fr')
        self.assertEqual(str(caught.exception), tr('amiga_kickstart_required', 'fr', game='Synthetic Game', wanted=wanted))

    def test_the_matching_image_in_a_folder_unlocks_the_install(self):
        archive = self.install_for(PLAIN)
        folder = self.kicks(image(11), swapped(PLAIN), image(12, K.SIZES[1], START_31))
        record = K.require(str(folder), archive)
        self.assertEqual((record.file_name, record.sha256, record.normalisations),
                         ('k1.rom', hashlib.sha256(PLAIN).hexdigest(), (K.SWAPPED,)))
        self.assertEqual(K.require(str(folder / 'k1.rom'), archive).sha256, record.sha256)

    def test_a_loadkick_install_wants_a_recognised_kickstart(self):
        archive = self.archive(patched_slave(call=0x4EAD), 'call.lha')
        with self.assertRaises(ValueError) as caught:
            K.require(None, archive)
        self.assertEqual(str(caught.exception), tr('amiga_kickstart_required_unnamed', 'en', game='Synthetic Game'))
        folder = self.kicks(PLAIN)
        with self.assertRaises(ValueError):                  # an image of an unknown version is not enough
            K.require(str(folder), archive)
        with knows(PLAIN):
            self.assertEqual(K.require(str(folder), archive).sha256, hashlib.sha256(PLAIN).hexdigest())

    def test_a_relative_option_is_resolved_like_the_other_firmware_paths(self):
        archive = self.install_for(PLAIN)
        folder = self.kicks(PLAIN)
        with patch('retrorecomp.paths.export_directory', return_value=self.folder):
            self.assertEqual(K.require('kicks', archive).file_name, 'k0.rom')


class TextTests(FolderCase):
    def test_a_good_folder_lists_what_was_found_and_what_was_not(self):
        self.put('a.rom', PLAIN)
        with knows(PLAIN):
            text = K.validate_kickstarts(self.folder)
        self.assertEqual(text, tr('amiga_kickstart_valid', 'en', found='1.3 (34.005, 256 KiB, A500)',
                                  missing='1.2 (33.180, 256 KiB, A500); 3.1 (40.063, 512 KiB, A500/A600/A2000); '
                                          '3.1 (40.068, 512 KiB, A1200); 3.1 (40.068, 512 KiB, A4000)'))
        with knows(PLAIN):
            self.assertIn('Non trouvé', K.validate_kickstarts(self.folder, 'fr'))

    def test_nothing_missing_says_so(self):
        entries = {}
        for number, ((size, _), info) in enumerate(K.KNOWN.items()):
            data = image(40 + number, size, START if size == K.SIZES[0] else START_31)
            self.put(f'k{number}.rom', data)
            entries[(size, zlib.crc32(data) & 0xFFFFFFFF)] = dict(info)
        with patch.dict(K.KNOWN, entries):
            text = K.validate_kickstarts(self.folder)
        self.assertTrue(text.endswith('Not found: –.'), text)

    def test_unknown_unreadable_and_empty_cases(self):
        self.assertEqual(K.validate_kickstarts(self.folder), tr('amiga_kickstart_none_found', 'en', name=self.folder.name))
        self.put('odd.rom', PLAIN)
        self.assertEqual(K.validate_kickstarts(self.folder), tr('amiga_kickstart_unknown_version', 'en', name='odd.rom'))
        self.assertTrue(K.validate_kickstarts(self.folder / 'missing').startswith('Kickstart unavailable or incompatible: '))
        self.put('sealed.rom', cloanto(image(13), KEY))
        text = K.validate_kickstarts(self.folder)
        self.assertIn(tr('amiga_kickstart_cloanto_key_missing', 'en', name='sealed.rom'), text)
        self.assertIn(tr('amiga_kickstart_unknown_version', 'en', name='odd.rom'), text)

    def test_a_wrong_file_and_a_wrong_key_have_their_sentences(self):
        small = self.put('small.bin', b'abc')
        self.assertEqual(K.validate_kickstarts(small), tr('amiga_kickstart_not_kickstart', 'en', name='small.bin', size=3))
        self.put('sealed.rom', cloanto(PLAIN, KEY))
        self.put('rom.key', bytes(reversed(KEY)))
        self.assertEqual(K.validate_kickstarts(self.folder), tr('amiga_kickstart_cloanto_key_wrong', 'en', name='sealed.rom'))

    def test_the_known_table_keeps_its_published_identifiers(self):
        self.assertEqual({(size, hex(crc)): (info['os'], info['version'], info['name']) for (size, crc), info in K.KNOWN.items()},
                         {(262144, '0xa6ce1636'): ('1.2', '33.180', 'kick33180.A500'),
                          (262144, '0xc4f0f55f'): ('1.3', '34.005', 'kick34005.A500'),
                          (524288, '0xfc24ae0d'): ('3.1', '40.063', 'kick40063.A600'),
                          (524288, '0x1483a091'): ('3.1', '40.068', 'kick40068.A1200'),
                          (524288, '0xd6bae334'): ('3.1', '40.068', 'kick40068.A4000')})


class ProfileAndWindowTests(unittest.TestCase):
    def test_the_profile_declares_an_optional_kickstart_path(self):
        profile = get_profile('amiga')
        self.assertEqual(profile.firmware, ('kickstart',))
        (key,) = profile.option_keys
        self.assertEqual((key.name, key.kind, key.signature, key.label), ('amiga_kickstart', 'path', False, 'amiga_kickstart_label'))

    def test_the_options_row_takes_a_file_or_a_folder_and_has_a_check(self):
        from retrorecomp.gui_options import FIRMWARE_ROWS
        import importlib
        row = FIRMWARE_ROWS['amiga_kickstart']
        self.assertTrue(row['folder'] and row['text'] and row['resolve'])
        module, function = row['check']
        self.assertTrue(callable(getattr(importlib.import_module('retrorecomp.' + module), function)))
        from retrorecomp.i18n import STRINGS
        for suffix in ('label', 'check', 'missing', 'not_checked', 'required', 'valid', 'invalid', 'cloanto_key_missing',
                       'not_kickstart', 'unknown_version'):
            self.assertIn('amiga_kickstart_' + suffix, STRINGS)
        self.assertIn('browse_folder', STRINGS)

    def test_the_command_line_has_the_flag(self):
        import argparse
        import RetroRecomp
        parser = argparse.ArgumentParser()
        RetroRecomp.add_machine_options(parser)
        self.assertIn('--amiga-kickstart', parser._option_string_actions)


if __name__ == '__main__':
    unittest.main()
