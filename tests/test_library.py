import concurrent.futures
import dataclasses
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import os

from smsrecomp.core import default_config, read_rom, set_video_standard
from smsrecomp.library import GameMemory, atomic_json, classify, read_observations, read_code_patterns


def fnv(data):
    h = 2166136261
    for byte in data:
        h = ((h ^ byte) * 16777619) & 0xFFFFFFFF
    return h


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rom_path = self.root / "Same_name.sms"
        self.rom_path.write_bytes(bytes(16384) + bytes([1]) * 16384)
        self.rom = read_rom(self.rom_path)
        self.memory = GameMemory(self.rom, self.root / "library")
        # Bank 3 on a two-bank ROM must mirror physical bank 1.
        self.good = (0x4100, 0, 3, 2, fnv(bytes([1]) * 256))

    def test_bank_mirror_signature_and_stale_code(self):
        ram = (0xC100, 0, 3, 2, 0xDEADBEEF)
        spill = (0xBF80, 0, 3, 2, 0xDEADBEEF)
        stale = (*self.good[:4], self.good[4] ^ 1)
        self.assertEqual(classify(self.rom, self.good), "rom")
        result = self.memory.import_entries({self.good, stale, ram, spill})
        self.assertEqual(result, {"added": 3, "verified": 1, "ram": 2, "rejected": 1})
        self.assertEqual(self.memory.seeds(), {self.good})
        self.assertEqual(self.memory.import_entries({self.good})["added"], 0)

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing lock')
    def test_atomic_checkpoint_waits_for_a_brief_reader_lock(self):
        from tests.test_publishing import locked_file
        path = self.root / 'progress.json'
        atomic_json(path, {'completed': 128})
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            with locked_file(path):
                future = executor.submit(atomic_json, path, {'completed': 129})
                time.sleep(0.15)
                self.assertEqual(json.loads(path.read_text()), {'completed': 128})
            future.result(timeout=3)
        self.assertEqual(json.loads(path.read_text()), {'completed': 129})
        self.assertFalse(list(self.root.glob('progress.json.*.tmp')))

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing lock')
    def test_persistent_checkpoint_lock_keeps_the_previous_data_and_reports_failure(self):
        from tests.test_publishing import locked_file
        path = self.root / 'progress.json'
        atomic_json(path, {'completed': 128})
        with locked_file(path):
            with self.assertRaises(PermissionError):
                atomic_json(path, {'completed': 129})
            self.assertEqual(json.loads(path.read_text()), {'completed': 128})
        self.assertFalse(list(self.root.glob('progress.json.*.tmp')))

    def test_identity_does_not_depend_on_name_crc_or_build_folder(self):
        self.memory.import_entries({self.good})
        renamed = dataclasses.replace(self.rom, path=self.root / "renamed.sms")
        self.assertEqual(GameMemory(renamed, self.root / "library").seeds(), {self.good})
        # Simulate a CRC collision: a different SHA must still be isolated.
        changed_data = self.rom.data[:-1] + b"\x02"
        other = dataclasses.replace(self.rom, data=changed_data, sha256=hashlib.sha256(changed_data).hexdigest())
        self.assertEqual(other.crc32, self.rom.crc32)
        self.assertFalse(GameMemory(other, self.root / "library").summary()["known"])

    def test_corrupt_manifest_line_does_not_hide_later_valid_lines(self):
        path = self.root / "manifest.txt"
        path.write_text("broken\n100000 00 01 02 00000000\n4100 00 03 02 %08X\n" % self.good[4])
        self.assertEqual(read_observations(path), {self.good})

    def test_native_patterns_are_data_only_and_scoped_to_rom(self):
        path = self.root / "native-patterns.txt"
        path.write_text("garbage\nC3360000\nC3360000\nC3ZZ0000\nC3299B00\nC300010000\n")
        expected = {bytes.fromhex("C3360000"), bytes.fromhex("C3299B00")}
        self.assertEqual(read_code_patterns(path), expected)
        self.assertEqual(self.memory.import_code_patterns(path), 2)
        self.assertEqual(self.memory.import_code_patterns(path), 0)
        self.assertEqual(self.memory.code_patterns(), expected)
        self.assertEqual(self.memory.summary()["native_pattern_windows"], 2)
        other = dataclasses.replace(self.rom, sha256="0" * 64)
        self.assertFalse(GameMemory(other, self.root / "library").code_patterns())

    def test_concurrent_imports_accumulate_without_overwriting(self):
        entries = [(0x4100 + n, 0, 3, 2, self.good[4]) for n in range(8)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda entry: self.memory.import_entries({entry}), entries))
        self.assertEqual(self.memory.seeds(), set(entries))

    def test_old_pattern_journal_is_migrated_and_later_writes_are_merged(self):
        self.memory.directory.mkdir(parents=True)
        old = self.memory.directory / 'native-patterns.txt'
        content = b'C3360000\nC3299B00\n'
        old.write_bytes(content)
        migrated = GameMemory(self.rom, self.root / 'library')
        self.assertFalse(old.exists())
        self.assertEqual(migrated.code_journal.name, 'native.patterns')
        self.assertEqual(migrated.code_journal.read_bytes(), content)
        # An older running executable can still append its original filename.
        old.write_bytes(b'C3360000\n00000000\n')
        merged = GameMemory(self.rom, self.root / 'library')
        self.assertFalse(old.exists())
        self.assertEqual(merged.code_patterns(), {bytes.fromhex(value) for value in
                         ('C3360000', 'C3299B00', '00000000')})
        self.assertEqual(merged.code_journal.read_bytes().count(b'C3360000'), 1)

    def test_pattern_migration_keeps_entries_beyond_the_compilation_limit(self):
        self.memory.directory.mkdir(parents=True)
        current = {value.to_bytes(4, 'big') for value in range(4096)}
        self.memory.code_journal.write_text(''.join(value.hex()+'\n' for value in sorted(current)), encoding='ascii')
        old = self.memory.directory / 'native-patterns.txt'
        old.write_text('C3360000\n', encoding='ascii')
        migrated = GameMemory(self.rom, self.root / 'library')
        self.assertFalse(old.exists())
        self.assertEqual(read_code_patterns(migrated.code_journal, limit=None), current | {bytes.fromhex('C3360000')})
        self.assertEqual(len(migrated.code_patterns()), 4096)

    def test_legacy_appdata_is_copied_and_rom_entries_rechecked(self):
        legacy_base = self.root / 'old-appdata'
        legacy = legacy_base / 'SMSRecomp/library' / self.rom.sha256
        legacy.mkdir(parents=True)
        source = legacy / 'observations.log'
        source.write_text('4100 00 03 02 %08X\n4100 00 03 02 00000000\n' % self.good[4])
        original = source.read_bytes()
        with patch.dict(os.environ, {'LOCALAPPDATA': str(legacy_base)}, clear=True), patch('smsrecomp.library.data_directory', return_value=self.root/'portable/datas'):
            imported = GameMemory(self.rom)
            self.assertEqual(imported.seeds(), {self.good})
            self.assertTrue(imported.directory.name.startswith('Same_name-'))
            self.assertEqual(GameMemory(self.rom).seeds(), {self.good})
        self.assertEqual(source.read_bytes(), original)

    def test_recipe_integrity_engine_scope_and_generation_history(self):
        report = {"created_utc": "test", "version": "0.3.0", "engine_revision": "engine1", "executable": "game.exe",
                  "final_checks": [], "strict_checks": [], "learning": {}, "reference_vdp_trace_match": False}
        config = "[game]\nrom='rom.sms'\n"
        self.memory.remember("Same name", config, report, "compiler1")
        self.assertEqual(self.memory.recipe("engine1"), config)
        self.assertIsNone(self.memory.recipe("engine2"))
        self.memory.remember("Same name", config, report, "compiler2")
        self.assertEqual(self.memory.summary()["generations"], 2)
        metadata = json.loads(self.memory.record.read_text(encoding="utf-8"))
        metadata["recipe"]["toml"] += "corrupted"
        self.memory.record.write_text(json.dumps(metadata), encoding="utf-8")
        self.assertIsNone(self.memory.recipe("engine1"))

    def test_explicit_video_choice_survives_engine_changes_and_rom_rename(self):
        report = {"created_utc": "test", "version": "0.10.17", "engine_revision": "old-engine",
                  "executable": "game.exe", "final_checks": [], "strict_checks": [],
                  "learning": {}, "reference_vdp_trace_match": False,
                  "system": {"id": "sms"}, "video_model": {"standard": "ntsc"}}
        config = set_video_standard(default_config(self.rom), "ntsc")
        self.memory.remember("Same name", config, report, "compiler1")
        self.assertIsNone(self.memory.recipe("new-engine"))
        self.assertEqual(self.memory.video_standard(), "ntsc")
        renamed = dataclasses.replace(self.rom, path=self.root / "Same_name (Europe).sms")
        self.assertEqual(GameMemory(renamed, self.root / "library").video_standard(), "ntsc")
        changed = self.rom.data[:-1] + b"\x02"
        other = dataclasses.replace(self.rom, data=changed, sha256=hashlib.sha256(changed).hexdigest())
        self.assertIsNone(GameMemory(other, self.root / "library").video_standard())
        metadata = self.memory.metadata()
        metadata["recipe"]["toml"] += "\n# stale compiler recipe"
        self.memory.record.write_text(json.dumps(metadata), encoding="utf-8")
        self.assertEqual(self.memory.video_standard(), "ntsc")

    def test_legacy_video_choice_requires_an_intact_rom_matched_recipe(self):
        report = {"created_utc": "test", "version": "0.10.16", "engine_revision": "old-engine",
                  "executable": "game.exe", "final_checks": [], "strict_checks": [],
                  "learning": {}, "reference_vdp_trace_match": False}
        config = set_video_standard(default_config(self.rom), "pal")
        self.memory.remember("Same name", config, report, "compiler1")
        self.assertIsNone(self.memory.recipe("new-engine"))
        self.assertEqual(self.memory.video_standard(), "pal")
        metadata = self.memory.metadata()
        self.assertNotIn("video_selection", metadata)
        metadata["recipe"]["toml"] += "\n# changed"
        self.memory.record.write_text(json.dumps(metadata), encoding="utf-8")
        self.assertIsNone(self.memory.video_standard())
        metadata["recipe"]["toml"] = metadata["recipe"]["toml"].replace(
            f"crc32 = 0x{self.rom.crc32:08X}", "crc32 = 0x00000000")
        metadata["recipe"]["sha256"] = hashlib.sha256(metadata["recipe"]["toml"].encode()).hexdigest()
        self.memory.record.write_text(json.dumps(metadata), encoding="utf-8")
        self.assertIsNone(self.memory.video_standard())


if __name__ == "__main__":
    unittest.main()
