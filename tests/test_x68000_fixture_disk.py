"""Private fixture disk editing tested exclusively with synthetic FAT media."""
import hashlib
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.x68000_fixture_disk import FixtureFat12, DISK_BYTES, AUTOEXEC
from tools import x68000_fixture_disk as disk_tool
from tools.x68000_fixtures import human68k_hello


def synthetic_volume():
    volume = bytearray(DISK_BYTES)
    struct.pack_into("<HBHBHHBHHH", volume, 11,
                     1024, 1, 1, 2, 192, 1232, 0xFE, 2, 8, 2)
    volume[0x36:0x3E] = b"FAT12   "
    for start in (1024, 3072):
        volume[start:start + 3] = bytes.fromhex("FEFFFF")
    return bytes(volume)


class X68000FixtureDiskTests(unittest.TestCase):
    def test_root_roundtrip_spans_clusters_and_preserves_shared_nibbles(self):
        volume = FixtureFat12(synthetic_volume())
        payload = bytes(range(256)) * 9
        volume.write("HELLO.X", payload)
        volume.write("NEXT.BIN", b"a different file")
        self.assertEqual(volume.read("HELLO.X"), payload)
        self.assertEqual(volume.read("NEXT.BIN"), b"a different file")
        self.assertEqual([volume._fat(n) for n in range(2, 6)], [3, 4, 0xFFF, 0xFFF])
        self.assertEqual(volume.data[1024:3072], volume.data[3072:5120])

    def test_stale_second_fat_is_not_repaired_or_allocated_over(self):
        volume = FixtureFat12(synthetic_volume())
        volume._set_fat(2, 0xFFF, 1)
        volume.write("RRHELLO.X", b"HU fixture")
        self.assertEqual(volume._fat(2, 0), 0)
        self.assertEqual(volume._fat(2, 1), 0xFFF)
        self.assertEqual(volume._fat(3, 0), 0xFFF)
        self.assertEqual(volume._fat(3, 1), 0xFFF)
        self.assertEqual(volume.read("RRHELLO.X"), b"HU fixture")

    def test_replacement_leaves_original_chain_and_other_files_intact(self):
        volume = FixtureFat12(synthetic_volume())
        volume.write("AUTOEXEC.BAT", b"original batch")
        volume.write("HUMAN.SYS", b"synthetic system marker")
        system_digest = hashlib.sha256(volume.read("HUMAN.SYS")).hexdigest()
        old_chain = volume._chain(2)
        volume.write("AUTOEXEC.BAT", AUTOEXEC)
        self.assertEqual(volume.read("AUTOEXEC.BAT"), AUTOEXEC)
        self.assertEqual(old_chain, volume._chain(2))
        self.assertEqual(system_digest,
                         hashlib.sha256(volume.read("HUMAN.SYS")).hexdigest())

    def test_invalid_geometry_and_invalid_chains_are_rejected(self):
        for size in (DISK_BYTES - 1, DISK_BYTES + 1):
            with self.assertRaises(ValueError):
                FixtureFat12(bytes(size))
        payload = bytearray(synthetic_volume())
        payload[13] = 0
        with self.assertRaises(ValueError):
            FixtureFat12(bytes(payload))
        volume = FixtureFat12(synthetic_volume())
        volume.write("BAD.X", b"x")
        volume._set_fat(2, 2, 0)
        with self.assertRaisesRegex(ValueError, "looping"):
            volume.read("BAD.X")

    def test_path_names_are_root_only_and_empty_files_do_not_claim_clusters(self):
        volume = FixtureFat12(synthetic_volume())
        for name in ("../test.x", "dir/test.x", "too-long-name.x", "name.long", "é.x", "ß.x"):
            with self.assertRaises(ValueError):
                volume.write(name, b"x")
        volume.write("EMPTY.TXT", b"")
        self.assertEqual(volume.read("EMPTY.TXT"), b"")
        self.assertEqual(volume._fat(2), 0)

    def test_private_disk_creation_preserves_source_and_checks_output_scope(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            volume = FixtureFat12(synthetic_volume())
            for name in ("HUMAN.SYS", "COMMAND.X", "CONFIG.SYS", "AUTOEXEC.BAT"):
                volume.write(name, b"synthetic " + name.encode("ascii"))
            source = root / "original.xdf"
            source.write_bytes(volume.data)
            before = source.read_bytes()
            output = root / ".build/private-test.xdf"
            with patch.object(disk_tool, "ROOT", root):
                with self.assertRaises(ValueError):
                    disk_tool.prepare_fixture_disk(source, root / "outside.xdf")
                report = disk_tool.prepare_fixture_disk(source, output)
                with self.assertRaises(FileExistsError):
                    disk_tool.prepare_fixture_disk(source, output)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(report["source_sha256_before"], report["source_sha256_after"])
            staged = FixtureFat12(output.read_bytes())
            self.assertEqual(staged.read("RRHELLO.X"), human68k_hello())
            self.assertEqual(staged.read("RRRELOC.X"), human68k_hello(relocated=True))
            self.assertEqual(staged.read("AUTOEXEC.BAT"), AUTOEXEC)
            for name in ("HUMAN.SYS", "COMMAND.X", "CONFIG.SYS"):
                self.assertEqual(staged.read(name), volume.read(name))


if __name__ == "__main__":
    unittest.main()
