"""Original X68000 inputs: loader-facing sections and address invariants.

These checks establish file structure and expected instruction operands. Actual
Human68k and MC68000 execution is a separate reference-runner validation.
"""
import hashlib
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from tools import x68000_fixtures as fixture


class X68000FixtureTests(unittest.TestCase):
    def test_hu_sections_have_exact_sizes_and_reserved_header_is_zero(self):
        for name in ("RRHELLO.X", "RRRELOC.X"):
            blob = fixture.fixtures()[name]
            self.assertEqual(blob[:4], b"HU\0\0")
            base, entry, text, data, bss, reloc, sym = struct.unpack_from(
                ">7I", blob, 4)
            self.assertEqual((base, entry, bss, sym), (0, 0, 0, 0))
            self.assertEqual(len(blob), 64 + text + data + reloc)
            self.assertEqual(blob[0x20:0x40], bytes(32))
            self.assertEqual(text, 18 if name == "RRRELOC.X" else 16)
            self.assertEqual(reloc, 2 if name == "RRRELOC.X" else 0)
            self.assertEqual(blob[64 + text:64 + text + data].split(b"\0")[0],
                             b"RETRORECOMP X68000 FIXTURE OK\r\n")

    def test_pc_relative_pointer_reaches_message_at_multiple_load_bases(self):
        blob = fixture.human68k_hello()
        self.assertEqual(blob[64:66], bytes.fromhex("487A"))
        displacement = struct.unpack_from(">h", blob, 66)[0]
        text_size = struct.unpack_from(">I", blob, 12)[0]
        for base in (0x1000, 0x20000, 0xBE000, 0x1F0000):
            self.assertEqual(base + 2 + displacement, base + text_size)
        # F-line calls must be followed by the stack adjustment / exit code,
        # not fall through into message bytes after a failed exit.
        self.assertEqual(blob[68:80], bytes.fromhex("FF09 588F 3F3C 0000 FF4C 60FE"))

    def test_relocation_delta_targets_long_operand_not_the_opcode(self):
        blob = fixture.human68k_hello(relocated=True)
        text_size, data_size = struct.unpack_from(">II", blob, 12)
        reloc_offset = 64 + text_size + data_size
        patch_offset = struct.unpack_from(">H", blob, reloc_offset)[0]
        self.assertEqual(patch_offset, 2)
        self.assertEqual(blob[64:66], bytes.fromhex("4879"))
        for base in (0x1000, 0x20000, 0x1F0000):
            loaded = bytearray(blob[64:reloc_offset])
            value = struct.unpack_from(">I", loaded, patch_offset)[0] + base
            struct.pack_into(">I", loaded, patch_offset, value)
            self.assertEqual(value - base, text_size)
            self.assertTrue(loaded[value - base:].startswith(fixture.MARKER))

    def test_cpu_reset_irq_vectors_and_loop_targets_are_valid(self):
        image = fixture.cpu_stop_irq()
        self.assertEqual(len(image), 512)
        self.assertEqual(struct.unpack_from(">II", image), (0x80000, 0x100))
        self.assertEqual(struct.unpack_from(">I", image, 25 * 4)[0], 0x120)
        for vector in tuple(range(2, 25)) + tuple(range(26, 64)):
            self.assertEqual(struct.unpack_from(">I", image, vector * 4)[0], 0x130)
        self.assertEqual(image[0x100:0x108], bytes.fromhex("7000 7200 5280 23C0"))
        self.assertEqual(struct.unpack_from(">I", image, 0x108)[0], 0x40000)
        self.assertEqual(image[0x10C:0x112], bytes.fromhex("4E72 2000 60F2"))
        self.assertEqual(0x112 + struct.unpack_from("b", image, 0x111)[0], 0x104)
        self.assertEqual(image[0x120:0x124], bytes.fromhex("5281 4E73"))
        self.assertEqual(image[0x130:0x136], bytes.fromhex("4E72 2700 60FA"))

    def test_outputs_are_deterministic_and_manifest_covers_every_payload(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = fixture.write_fixtures(root)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            self.assertEqual(manifest, fixture.write_fixtures(root))
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            self.assertEqual(set(manifest["files"]), set(before) - {"manifest.json"})
            for name, description in manifest["files"].items():
                self.assertEqual(description["size"], len(before[name]))
                self.assertEqual(description["sha256"], hashlib.sha256(before[name]).hexdigest())
            expected = json.loads(before["expected.json"])
            self.assertFalse(expected["bundled_firmware"])
            self.assertEqual(expected["human68k"]["exit_status"], 0)
            self.assertEqual(expected["cpu"]["after_irq1"]["counter"], 2)

    def test_existing_different_files_are_preserved_before_any_write(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "RRRELOC.X").write_bytes(b"keep me")
            with self.assertRaises(FileExistsError):
                fixture.write_fixtures(root)
            self.assertEqual([p.name for p in root.iterdir()], ["RRRELOC.X"])
            self.assertEqual((root / "RRRELOC.X").read_bytes(), b"keep me")


if __name__ == "__main__":
    unittest.main()
