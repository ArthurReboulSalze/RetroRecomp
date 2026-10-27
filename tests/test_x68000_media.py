"""X68000 source safety and identity tests using authored bytes only."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp.x68000_media import (
    CGROM_BYTES, IPL_BYTES, MAX_DISK_BYTES, XDF_BYTES, MachineConfig,
    build_manifest, identify_disk, validate_firmware,
)


class X68000MediaTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()   # the long form: Windows may spell a temporary folder short (RUNNER~1)
        self.ipl = self.write('iplrom.dat', b'I' * IPL_BYTES)
        self.cgrom = self.write('cgrom.dat', b'C' * CGROM_BYTES)

    def write(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def xdf(self, name='authored.xdf', value=0x45):
        return self.write(name, bytes([value]) * XDF_BYTES)

    def dim(self, name='authored.dim', tracks=tuple(range(154)), kind=0,
            overtrack=False, signature=True):
        sector, sectors = {0: (1024, 8), 1: (1024, 9), 2: (512, 15),
                           3: (1024, 9), 9: (512, 18)}[kind]
        header = bytearray(256)
        header[0] = kind
        for track in tracks:
            header[track + 1] = 1
        if signature:
            header[171:186] = b'DIFC HEADER\0\0\0\0'
        header[255] = int(overtrack)
        payload = bytes([0x81]) * (len(tracks) * sector * sectors)
        return self.write(name, bytes(header) + payload)

    def manifest(self, disks, **kwargs):
        return build_manifest(disks, self.ipl, self.cgrom, **kwargs)

    def test_standard_xdf_and_dim_have_explicit_geometry_and_exact_hashes(self):
        for path, format_name in ((self.xdf('UPPER.XDF'), 'xdf'), (self.dim(), 'dim')):
            image = identify_disk(path)
            self.assertEqual(image.format, format_name)
            self.assertEqual((image.sector_bytes, image.sectors_per_track), (1024, 8))
            self.assertEqual(image.present_tracks, tuple(range(154)))
            self.assertEqual(image.sha256, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(self.dim().stat().st_size, 1_261_824)

    def test_sparse_dim_tracks_keep_their_positions(self):
        image = identify_disk(self.dim(tracks=(0, 1, 98, 153)))
        self.assertEqual(image.present_tracks, (0, 1, 98, 153))
        self.assertEqual(image.size, 256 + 4 * 8192)

    def test_header_without_magic_is_accepted_only_with_matching_track_payload(self):
        path = self.dim(signature=False)
        self.assertEqual(identify_disk(path).format, 'dim')
        path.write_bytes(path.read_bytes() + b'extra')
        with self.assertRaisesRegex(ValueError, 'track map'):
            identify_disk(path)

    def test_dim_geometries_do_not_guess_payload_by_file_size_alone(self):
        for kind in (1, 2, 3, 9):
            image = identify_disk(self.dim(kind=kind, tracks=tuple(range(160))))
            self.assertEqual(image.dim_type, kind)
        path = self.dim()
        data = bytearray(path.read_bytes())
        data[0] = 4
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'media type'):
            identify_disk(path)

    def test_extra_tracks_follow_map_with_or_without_legacy_flag(self):
        path = self.dim(tracks=tuple(range(170)))
        image = identify_disk(path)
        self.assertEqual(image.present_tracks, tuple(range(170)))
        self.assertFalse(image.overtrack)
        path = self.dim(tracks=(0, 154), overtrack=True)
        self.assertEqual(identify_disk(path).present_tracks, (0, 154))
        path.write_bytes(path.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, 'track map'):
            identify_disk(path)

    def test_truncated_empty_and_wrong_size_images_fail(self):
        for name, data in (('short.xdf', b'x' * 256), ('short.dim', b'\0' * 255),
                           ('empty.dim', b'\0' * 256)):
            with self.subTest(name=name), self.assertRaises(ValueError):
                identify_disk(self.write(name, data))

    def test_oversized_disk_is_rejected_before_opening_or_hashing(self):
        path = self.root / 'oversized.dim'
        with path.open('wb') as target:
            target.truncate(MAX_DISK_BYTES + 1)
        with patch.object(Path, 'open', side_effect=AssertionError('read oversized data')):
            with self.assertRaisesRegex(ValueError, 'size limit'):
                identify_disk(path)

    def test_scripts_are_never_executed_or_interpreted_as_disks(self):
        path = self.write('disk.cmd', b'echo unexpected > should-not-exist')
        with self.assertRaisesRegex(ValueError, 'not executed'):
            self.manifest([path])
        self.assertFalse((self.root / 'should-not-exist').exists())

    def test_manifest_identity_survives_move_but_not_reordering_or_settings(self):
        first, second = self.xdf('first.xdf'), self.xdf('second.xdf', 0x22)
        manifest = self.manifest([first, second], initial_drives=(0, 1))
        moved = self.root / 'other computer'
        moved.mkdir()
        copied = []
        for path in (first, second, self.ipl, self.cgrom):
            target = moved / path.name
            shutil.copyfile(path, target)
            copied.append(target)
        renamed = build_manifest(copied[:2], copied[2], copied[3], initial_drives=(0, 1))
        self.assertEqual(manifest.sha256, renamed.sha256)
        self.assertNotEqual(manifest.sha256,
                            self.manifest([second, first], initial_drives=(0, 1)).sha256)
        self.assertNotEqual(manifest.sha256,
                            self.manifest([first, second], initial_drives=(1, 0)).sha256)
        config = replace(MachineConfig(), ram_bytes=4 * 1024 * 1024)
        self.assertNotEqual(manifest.sha256,
                            self.manifest([first, second], config=config).sha256)

    def test_firmware_identity_is_full_content_not_only_name_or_size(self):
        first = validate_firmware(self.ipl, self.cgrom)
        data = bytearray(self.ipl.read_bytes())
        data[-1] ^= 1
        self.ipl.write_bytes(data)
        self.assertNotEqual(first.ipl.sha256, validate_firmware(self.ipl, self.cgrom).ipl.sha256)
        self.cgrom.write_bytes(b'not a complete font ROM')
        with self.assertRaisesRegex(ValueError, 'exactly'):
            validate_firmware(self.ipl, self.cgrom)

    def test_public_record_has_no_paths_filenames_or_source_payload(self):
        manifest = self.manifest([self.xdf('private game name.xdf')])
        encoded = json.dumps(manifest.public_record())
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn('private game', encoded)
        self.assertNotIn('iplrom.dat', encoded)
        self.assertLess(len(encoded), 4000)
        self.assertEqual(Path(manifest.local_record()['media'][0]['path']).parent,
                         self.root)

    def test_build_and_reverification_leave_sources_and_folders_unchanged(self):
        disk = self.xdf()
        before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                  for path in self.root.iterdir()}
        manifest = self.manifest([disk])
        manifest.verify_sources()
        after = {path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                 for path in self.root.iterdir()}
        self.assertEqual(before, after)
        disk.write_bytes(bytes([0x44]) * XDF_BYTES)
        with self.assertRaisesRegex(ValueError, 'changed'):
            manifest.verify_sources()

    def test_invalid_drive_lists_and_profiles_fail_before_source_reads(self):
        disk = self.xdf()
        with patch('retrorecomp.x68000_media.identify_disk', side_effect=AssertionError('read')):
            for drives in ((None, None), (0,), (0, 1), (True, None), (0, -1)):
                with self.subTest(drives=drives), self.assertRaises(ValueError):
                    self.manifest([disk], initial_drives=drives)
        for setting in ({'cpu': 'm68030'}, {'clock_hz': 16_000_000},
                        {'ram_bytes': 1024}, {'ram_bytes': True}):
            with self.subTest(setting=setting), self.assertRaises(ValueError):
                MachineConfig(**setting)

    def test_directory_and_missing_sources_fail_cleanly(self):
        directory = self.root / 'folder.xdf'
        directory.mkdir()
        for path in (directory, self.root / 'missing.xdf'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                identify_disk(path)

    def test_source_changed_during_read_is_not_recorded(self):
        disk = self.xdf()
        original_open = Path.open

        class ChangingReader:
            def __init__(self, source):
                self.source = source
                self.changed = False

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.source.close()

            def fileno(self):
                return self.source.fileno()

            def read(self, length):
                chunk = self.source.read(length)
                if not self.changed:
                    self.changed = True
                    with original_open(disk, 'ab') as writer:
                        writer.write(b'changed')
                return chunk

        def opening(path, mode='r', *args, **kwargs):
            self.assertEqual(mode, 'rb')
            return ChangingReader(original_open(path, mode, *args, **kwargs))

        with patch.object(Path, 'open', opening):
            with self.assertRaisesRegex(ValueError, 'changed'):
                identify_disk(disk)


if __name__ == '__main__':
    unittest.main()
