"""The Atari ST profile recognises floppy images and ZIPs that hold only them, and a TOS image by its header, on synthetic files
written by the test (a few authored bytes: no game, no disk, no TOS, no ROM). Nothing here reads or writes the converter's
settings."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from retrorecomp import atarist, atarist_tos
from retrorecomp.core import ConversionError
from retrorecomp.systems import get_profile, profile_for_path


def tos_like(version=0x0104, country_byte=0x07, base=0x00FC0000, size=atarist_tos.TOS_SIZE):
    """A buffer with the header fields of a TOS image (the branch at 0, the version at 2, the base at 8, the country at $1D) and
    nothing else: authored zeros, not a TOS."""
    blob = bytearray(size)
    blob[0] = 0x60
    blob[2:4] = version.to_bytes(2, 'big')
    blob[8:12] = base.to_bytes(4, 'big')
    blob[0x1D] = country_byte
    return bytes(blob)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        # The profile is offered only where the converter's native files are; the test does not depend on that.
        available = patch('retrorecomp.atarist.converter_available', return_value=True)
        available.start()
        self.addCleanup(available.stop)

    def archive(self, members, name='Synthetic.zip'):
        path = self.folder / name
        with zipfile.ZipFile(path, 'w') as out:
            for member, data in members:
                out.writestr(member, data)
        return path

    def test_the_profile_says_what_it_is(self):
        profile = get_profile('atarist')
        self.assertEqual((profile.name, profile.status, profile.linux), ('Atari ST', 'supported', 'witnessed'))
        self.assertEqual([cpu.arch for cpu in profile.cpus], ['m68000'])
        self.assertEqual(profile.identify.path_order, 35)

    def test_a_zip_of_two_disks_is_the_sts(self):
        path = self.archive([('x (Disk 2).ipf', b'IPF2' * 8), ('x (Disk 1).ipf', b'IPF1' * 8)])
        self.assertIs(profile_for_path(path), get_profile('atarist'))
        self.assertIs(profile_for_path(path, 'atarist'), get_profile('atarist'))
        self.assertEqual(atarist.disk_members(path), ['x (Disk 1).ipf', 'x (Disk 2).ipf'])

    def test_a_single_disk_image_of_each_format_is_the_sts(self):
        for suffix in ('.ipf', '.stx', '.msa', '.st', '.IPF'):
            path = self.folder / f'Game{suffix}'
            path.write_bytes(b'\x01' * 32)
            with self.subTest(suffix):
                self.assertIs(profile_for_path(path), get_profile('atarist'))

    def test_a_zip_with_a_disk_and_a_text_file_is_not_the_sts(self):
        path = self.archive([('x.ipf', b'IPF' * 8), ('readme.txt', b'hello')])
        self.assertIsNone(atarist.disk_members(path))
        try:
            found = profile_for_path(path)
        except Exception:   # an unknown console is a sentence, not a guess
            found = None
        self.assertIsNot(found, get_profile('atarist'))

    def test_a_zip_with_a_folder_or_nothing_is_not_the_sts(self):
        self.assertIsNone(atarist.disk_members(self.archive([('sub/x.ipf', b'I' * 8)], 'folder.zip')))
        self.assertIsNone(atarist.disk_members(self.archive([], 'empty.zip')))
        self.assertIsNone(atarist.disk_members(self.archive([(f'd{n}.st', b'S' * 8) for n in range(atarist.MAX_DISKS + 1)], 'many.zip')))
        broken = self.folder / 'broken.zip'
        broken.write_bytes(b'not a zip')
        self.assertIsNone(atarist.disk_members(broken))

    def test_the_input_keeps_the_disk_order_and_a_clean_title(self):
        path = self.archive([('Turrican (Disk 2).st', b'B' * 16), ('Turrican (Disk 1).st', b'A' * 16)], 'Turrican (Europe) (Kixx).zip')
        source = atarist.read_input(path)
        self.assertEqual([disk.name for disk in source.disks], ['Turrican (Disk 1).st', 'Turrican (Disk 2).st'])
        self.assertEqual(source.disk_data(), [b'A' * 16, b'B' * 16])
        self.assertEqual(source.title, 'Turrican')
        self.assertEqual(source.metadata()['format'], 'atarist-zip')
        self.assertEqual(len(source.sha256), 64)

    def test_a_foreign_file_and_an_empty_image_are_refused(self):
        other = self.folder / 'notes.txt'
        other.write_bytes(b'hello')
        with self.assertRaises(ConversionError):
            atarist.read_input(other)
        empty = self.folder / 'empty.msa'
        empty.write_bytes(b'')
        with self.assertRaises(ConversionError):
            atarist.read_input(empty)

    def test_clean_title(self):
        self.assertEqual(atarist.clean_title('Turrican II - The Final Fight (Europe) (Budget - Kixx).ipf'),
                         'Turrican II - The Final Fight')
        self.assertEqual(atarist.clean_title('Dungeon Master [a1].msa'), 'Dungeon Master')
        self.assertEqual(atarist.clean_title('(Only Tags).st'), '(Only Tags)')
        self.assertLessEqual(len(atarist.clean_title('N' * 400 + '.st')), 160)


class TosTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def write(self, blob, name):
        path = self.folder / name
        path.write_bytes(blob)
        return path

    def test_a_header_like_tos_104_is_recognised(self):
        image = atarist_tos.identify(self.write(tos_like(), 'tos.img'))
        self.assertIsNotNone(image)
        self.assertEqual((image.version, image.country, image.pal, image.size), (0x0104, 3, True, atarist_tos.TOS_SIZE))
        self.assertEqual(image.label(), 'TOS 1.04 (United Kingdom)')
        self.assertEqual(len(image.sha256), 64)
        self.assertEqual(image.data(), tos_like())

    def test_the_name_means_nothing_and_the_header_everything(self):
        self.assertIsNotNone(atarist_tos.identify(self.write(tos_like(0x0100, country_byte=0), 'notes.txt')))
        self.assertIsNone(atarist_tos.identify(self.write(tos_like(size=atarist_tos.TOS_SIZE - 1), 'tos104.img')))
        self.assertIsNone(atarist_tos.identify(self.write(tos_like(version=0x0206), 'tos206.img')))      # a later model's TOS
        self.assertIsNone(atarist_tos.identify(self.write(tos_like(base=0x00E00000), 'ste.img')))
        self.assertIsNone(atarist_tos.identify(self.folder / 'missing.img'))
        bad_branch = bytearray(tos_like())
        bad_branch[0] = 0x00
        self.assertIsNone(atarist_tos.identify(self.write(bytes(bad_branch), 'branch.img')))

    def test_a_folder_prefers_the_latest_version_then_the_united_kingdom(self):
        self.write(tos_like(0x0102, country_byte=0x07), 'a.img')
        self.write(tos_like(0x0104, country_byte=0x05), 'b.img')    # country code 2: France (the low bit is PAL)
        self.write(tos_like(0x0104, country_byte=0x07), 'c.img')    # country code 3: the United Kingdom
        self.write(b'not a tos', 'd.txt')
        found = atarist_tos.candidates(self.folder)
        self.assertEqual([item.path.name for item in found], ['c.img', 'b.img', 'a.img'])
        self.assertEqual(atarist_tos.require(self.folder).path.name, 'c.img')
        self.assertEqual(atarist_tos.require(self.folder / 'a.img').path.name, 'a.img')

    def test_no_path_means_emutos_and_a_folder_without_a_tos_is_a_sentence(self):
        self.assertIsNone(atarist_tos.require(None))
        self.assertIsNone(atarist_tos.require(''))
        self.write(b'nothing', 'x.txt')
        with self.assertRaises(ValueError) as caught:
            atarist_tos.require(self.folder)
        self.assertIn('no Atari ST TOS', str(caught.exception))

    def test_an_emutos_image_is_not_taken_for_the_players_tos(self):
        blob = bytearray(tos_like())
        blob[0x2C:0x30] = b'ETOS'
        self.assertIsNone(atarist_tos.identify(self.write(bytes(blob), 'etos192uk.img')))


class EmuTosTests(unittest.TestCase):
    """EmuTOS is fetched once, checked by size and SHA-256 on every use, and refused when it is not the pinned file. The release
    files are authored stand-ins here (a zip holding a buffer with the EmuTOS magic, a few bytes for the source); nothing is
    downloaded."""

    def setUp(self):
        import hashlib
        import io
        from retrorecomp import atarist_emutos
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.emutos = atarist_emutos
        image = bytearray(tos_like())
        image[0x2C:0x30] = b'ETOS'
        member = 'emutos-192k-test/etos192uk.img'
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr(member, bytes(image))
        self.files = {'binary.zip': stream.getvalue(), 'source.tar.gz': b'authored source stand-in'}
        sha = lambda data: hashlib.sha256(data).hexdigest()  # noqa: E731
        for name, value in (('BINARY', ('binary.zip', len(self.files['binary.zip']), sha(self.files['binary.zip']))),
                            ('SOURCE', ('source.tar.gz', len(self.files['source.tar.gz']), sha(self.files['source.tar.gz']))),
                            ('IMAGE', (member, len(image), sha(bytes(image))))):
            patcher = patch.object(atarist_emutos, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(atarist_emutos, 'directory', lambda: self.folder)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.downloads = []

    def fake_download(self, url, destination, size, digest, limit, mismatch):
        self.downloads.append(url.rsplit('/', 1)[-1])
        Path(destination).write_bytes(self.files[url.rsplit('/', 1)[-1]])

    def test_fetched_once_then_checked_on_every_use(self):
        with patch('retrorecomp.updater._download_verified', self.fake_download):
            tos = self.emutos.require(emit=lambda text: None)
            self.emutos.require(emit=lambda text: None)
        self.assertEqual(self.downloads, ['binary.zip', 'source.tar.gz'])
        self.assertFalse(tos.player_supplied)
        self.assertEqual((tos.key, tos.pal, tos.version_text()), ('emutos-' + self.emutos.VERSION, True, 'EmuTOS ' + self.emutos.VERSION))
        self.assertEqual(tos.data()[0x2C:0x30], b'ETOS')
        self.assertEqual(tos.sha256, self.emutos.IMAGE[2])
        self.assertEqual(tos.source.read_bytes(), self.files['source.tar.gz'])

    def test_a_changed_file_is_fetched_again_and_a_failed_fetch_is_a_sentence(self):
        with patch('retrorecomp.updater._download_verified', self.fake_download):
            self.emutos.require(emit=lambda text: None)
        (self.folder / 'source.tar.gz').write_bytes(b'changed')
        with patch('retrorecomp.updater._download_verified', self.fake_download):
            self.emutos.require(emit=lambda text: None)
        self.assertEqual(self.downloads, ['binary.zip', 'source.tar.gz', 'source.tar.gz'])
        (self.folder / 'binary.zip').unlink()

        def offline(*args):
            raise OSError('offline')
        with patch('retrorecomp.updater._download_verified', offline), self.assertRaises(ValueError) as caught:
            self.emutos.require(emit=lambda text: None)
        self.assertIn('choose your own TOS', str(caught.exception))
        self.assertFalse(list(self.folder.glob('*.part')))

    def test_a_mirror_that_refuses_once_is_tried_again(self):
        from retrorecomp.updater import UpdateConnectionError
        refused = []

        def once(url, destination, *args):
            if not refused:
                refused.append(url)
                raise UpdateConnectionError()
            self.fake_download(url, destination, *args)
        with patch('retrorecomp.updater._download_verified', once), patch.object(self.emutos, 'RETRY_SECONDS', 0):
            self.emutos.require(emit=lambda text: None)
        self.assertEqual(len(refused), 1)
        self.assertEqual(self.downloads, ['binary.zip', 'source.tar.gz'])


if __name__ == '__main__':
    unittest.main()
