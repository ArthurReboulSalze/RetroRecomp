"""Private reference staging is bounded and never overwrites supplied media."""
import configparser
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retrorecomp.linux_desktop import _argument, _value
from retrorecomp.x68000_media import CGROM_BYTES, IPL_BYTES, XDF_BYTES
from tools import x68000_reference as reference


class X68000ReferenceStagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sources = self.root / 'sources'
        self.sources.mkdir()
        self.disks = [self.write(self.sources / 'disk.xdf', b'A' * XDF_BYTES)]
        self.ipl = self.write(self.sources / 'iplrom.dat', b'I' * IPL_BYTES)
        self.cgrom = self.write(self.sources / 'cgrom.dat', b'C' * CGROM_BYTES)
        self.binaries = self.root / 'build'
        self.binaries.mkdir()
        self.exe = self.write(self.binaries / 'Reference.exe', b'authored executable fixture')
        self.write(self.binaries / 'rr_px68k_reference.dll', b'authored module fixture')
        self.write(self.binaries / 'rr_px68k_reference.so', b'authored Linux module fixture')
        self.module = self.binaries / ('rr_px68k_reference.dll' if os.name == 'nt'
                                      else 'rr_px68k_reference.so')
        self.output = self.root / 'output'

    @staticmethod
    def write(path, data):
        path.write_bytes(data)
        return path

    def prepare(self, **kwargs):
        return reference.prepare_bundle(self.output, self.disks, self.ipl,
                                        self.cgrom, self.exe, **kwargs)

    @staticmethod
    def contents(folder):
        return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in folder.rglob('*') if path.is_file()}

    def symlink(self, link, target, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except OSError as exc:
            self.skipTest(f'Symlink creation unavailable: {exc}')

    def test_real_staging_keeps_originals_and_separates_mutable_working_disks(self):
        originals = self.contents(self.sources)
        target = self.prepare()
        self.assertEqual(target.read_bytes(), self.exe.read_bytes())
        self.assertEqual(self.contents(self.sources), originals)
        receipt = json.loads((self.output / 'datas/source-manifest.json').read_text())
        self.assertEqual(receipt['initial_drives'], [0, None])
        self.assertEqual(receipt['media'][0]['path'], str(self.disks[0].resolve()))
        copy = self.output / 'datas/media/disk-01.xdf'
        immutable = self.output / 'datas/original-media/disk-01.xdf'
        self.assertEqual(copy.read_bytes(), self.disks[0].read_bytes())
        self.assertEqual(immutable.read_bytes(), self.disks[0].read_bytes())
        self.assertFalse(os.path.samefile(copy, self.disks[0]))
        self.assertFalse(os.path.samefile(copy, immutable))
        copy.write_bytes(b'guest writes' + copy.read_bytes()[12:])
        save = self.output / 'datas/saves/user-save'
        save.write_bytes(b'keep my progress')
        guest_before = copy.read_bytes()
        self.prepare()
        self.assertEqual(copy.read_bytes(), guest_before)
        self.assertEqual(save.read_bytes(), b'keep my progress')
        self.assertEqual(self.contents(self.sources), originals)

    def test_ordered_disks_are_one_bundle_and_two_separate_drives(self):
        self.disks += [self.write(self.sources / 'second.xdf', b'B' * XDF_BYTES),
                       self.write(self.sources / 'third.xdf', b'D' * XDF_BYTES)]
        self.prepare(ram_mib=4)
        receipt = json.loads((self.output / 'datas/source-manifest.json').read_text())
        self.assertEqual(receipt['initial_drives'], [0, 1])
        self.assertEqual(len(receipt['media']), 3)
        self.assertEqual((self.output / 'datas/media/game.m3u').read_text().splitlines(),
                         ['disk-01.xdf', 'disk-02.xdf', 'disk-03.xdf'])
        self.assertIn('4 MiB RAM', (self.output / 'README-REFERENCE.txt').read_text(encoding='utf-8'))
        self.assertEqual((self.output / 'datas/reference.cfg').read_text(), 'ram_mib=4\n')

    def test_changed_identity_and_machine_configuration_preserve_entire_existing_bundle(self):
        self.prepare()
        before = self.contents(self.output)
        with self.assertRaisesRegex(ValueError, 'another exact media'):
            self.prepare(ram_mib=4)
        self.assertEqual(self.contents(self.output), before)
        self.disks[0].write_bytes(b'B' * XDF_BYTES)
        with self.assertRaisesRegex(ValueError, 'another exact media'):
            self.prepare()
        self.assertEqual(self.contents(self.output), before)

    def test_source_directory_cannot_be_used_as_output(self):
        originals = self.contents(self.sources)
        self.output = self.sources
        with self.assertRaisesRegex(ValueError, 'Sources must be outside'):
            self.prepare()
        self.assertEqual(self.contents(self.sources), originals)

    def test_missing_binary_and_invalid_drive_layout_create_no_bundle(self):
        self.module.unlink()
        with self.assertRaisesRegex(ValueError, 'executable and core module'):
            self.prepare()
        self.assertFalse(self.output.exists())
        self.module.write_bytes(b'module')
        with self.assertRaisesRegex(ValueError, 'FDD0'):
            self.prepare(initial_drives=(None, 0))
        self.assertFalse(self.output.exists())

    def test_more_than_ten_disks_fail_before_source_reads_or_staging(self):
        self.disks *= 11
        originals = self.contents(self.sources)
        with patch.object(reference, 'build_manifest', side_effect=AssertionError('source read')):
            with self.assertRaisesRegex(ValueError, 'at most 10 disks'):
                self.prepare()
        self.assertFalse(self.output.exists())
        self.assertEqual(self.contents(self.sources), originals)

    def test_existing_unowned_data_is_not_adopted(self):
        data = self.output / 'datas'
        data.mkdir(parents=True)
        user_file = data / 'unrelated data'
        user_file.write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError, 'no source manifest'):
            self.prepare()
        self.assertEqual(self.contents(self.output), {'datas/unrelated data':
                         hashlib.sha256(b'preserve').hexdigest()})

    def test_symlink_output_or_data_parent_is_rejected_before_writes(self):
        outside = self.root / 'outside'
        outside.mkdir()
        self.symlink(self.output, outside, directory=True)
        with self.assertRaisesRegex(ValueError, 'linked'):
            self.prepare()
        self.assertFalse(any(outside.iterdir()))
        self.output.unlink()
        self.output.mkdir()
        self.symlink(self.output / 'datas', outside, directory=True)
        with self.assertRaisesRegex(ValueError, 'linked'):
            self.prepare()
        self.assertFalse(any(outside.iterdir()))

    def test_symlink_working_disk_cannot_redirect_guest_writes_to_source(self):
        self.prepare()
        disk = self.output / 'datas/media/disk-01.xdf'
        disk.unlink()
        self.symlink(disk, self.disks[0])
        before = self.contents(self.sources)
        with self.assertRaisesRegex(ValueError, 'linked'):
            self.prepare()
        self.assertEqual(self.contents(self.sources), before)

    def test_hardlinked_working_disk_cannot_redirect_guest_writes_to_source(self):
        self.prepare()
        disk = self.output / 'datas/media/disk-01.xdf'
        disk.unlink()
        try:
            os.link(self.disks[0], disk)
        except OSError as exc:
            self.skipTest(f'Hard links unavailable: {exc}')
        before = self.contents(self.sources)
        with self.assertRaisesRegex(ValueError, 'hard-linked'):
            self.prepare()
        self.assertEqual(self.contents(self.sources), before)

    def test_fixed_pending_symlink_cannot_overwrite_an_external_file(self):
        self.output.mkdir()
        outside = self.write(self.root / 'outside-user-file', b'user content')
        self.symlink(self.output / (self.exe.name + '.pending'), outside)
        self.prepare()
        self.assertEqual(outside.read_bytes(), b'user content')

    def test_bad_title_cannot_escape_output_or_inject_desktop_fields(self):
        for title in ('../elsewhere', 'bad\nExec=anything', 'bad\\child', ''):
            with self.subTest(title=title), self.assertRaisesRegex(ValueError, 'title'):
                self.prepare(title=title)
        self.assertFalse(self.output.exists())

    def test_linux_launcher_uses_existing_escaping_and_marks_program_executable(self):
        self.output = self.root / ('output 100% $dollars `ticks`' if os.name == 'nt'
                                   else 'output 100% $dollars "quoted"')
        # Patch only this module's OS view, preserving Windows pathlib and I/O.
        linux = SimpleNamespace(name='posix', fdopen=os.fdopen)
        with patch.object(reference, 'os', linux):
            target = self.prepare(title='Cho Ren Sha 68k')
        desktop = self.output / 'Cho Ren Sha 68k.desktop'
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(desktop, encoding='utf-8')
        entry = parser['Desktop Entry']
        self.assertEqual(entry['Exec'], _argument(target))
        self.assertEqual(entry['Path'], _value(self.output))
        self.assertEqual(entry['Terminal'], 'false')
        self.assertIn('%%', entry['Exec'])
        if os.name != 'nt':
            self.assertTrue(target.stat().st_mode & 0o111)
            self.assertTrue(desktop.stat().st_mode & 0o111)


if __name__ == '__main__':
    unittest.main()
