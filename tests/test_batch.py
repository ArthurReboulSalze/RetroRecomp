import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from smsrecomp.batch import identify, convert_batch
from smsrecomp.core import ConversionError, executable_name
from smsrecomp.library import atomic_json


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Match production path resolution even when TEMP uses a Windows 8.3 alias.
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / "jeux partagés"

    def item(self, directory, value):
        folder = self.root / directory
        folder.mkdir(exist_ok=True)
        path = folder / "Same title (Europe).sms"
        path.write_bytes(bytes([value]) * 8192)
        return identify(path)

    def compiler(self, path, *, output, title, **options):
        output.mkdir(parents=True, exist_ok=True)
        exe = output / "Same_title.exe"
        exe.write_bytes(path.read_bytes())
        (output / "conversion-report.json").write_text(json.dumps({"executable": exe.name,
            "video_model": {"standard": options.get('standard_override') or 'pal'},
            "final_checks": [{"interpreter_percent": 0}], "reference_vdp_trace_match": True}))
        return exe

    def test_flat_folder_isolates_same_title_editions_and_deduplicates_exact_rom(self):
        first, second, alias = self.item("one", 1), self.item("two", 2), self.item("alias", 1)
        with patch("smsrecomp.systems.master_system.MasterSystemProfile.convert", side_effect=self.compiler) as compiler:
            record = convert_batch([first, second, alias], self.output, emit=lambda text: None)
        self.assertEqual((record["succeeded"], record["duplicates"]), (2, 1))
        self.assertEqual(compiler.call_count, 2)
        self.assertFalse(list(self.output.rglob('*.txt')))
        self.assertEqual({p.name for p in self.output.iterdir()}, {'Same title.exe', 'Same title (2).exe', 'datas'})
        for item, filename in ((first, 'Same title.exe'), (second, 'Same title (2).exe')):
            report = self.output / "datas/reports" / item.key / "conversion-report.json"
            self.assertEqual(json.loads(report.read_text())["executable"], filename)
        # Reversed order in a later conversion must preserve revision/name pairing.
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler):
            repeated = convert_batch([second, first], self.output, emit=lambda text: None)
        self.assertEqual([Path(game['executable']).name for game in repeated['games']],
                         ['Same title (2).exe', 'Same title.exe'])

    def test_failure_preserves_previous_executable_and_next_rom_still_runs(self):
        first, second = self.item("one", 1), self.item("two", 2)
        self.output.mkdir()
        old = self.output / (first.key+".exe")
        old.write_bytes(b"previous good executable")
        def compile(path, **options):
            if path == first.path:
                raise ConversionError("Invalid encoding")
            return self.compiler(path, **options)
        with patch("smsrecomp.systems.master_system.MasterSystemProfile.convert", side_effect=compile):
            result = convert_batch([first, second], self.output, emit=lambda text: None)
        self.assertEqual((result["failed"], result["succeeded"]), (1, 1))
        self.assertEqual(old.read_bytes(), b"previous good executable")

    def test_stop_waits_for_current_game_and_changed_rom_is_refused(self):
        first, second = self.item("one", 1), self.item("two", 2)
        stop = Event()
        def event(kind, index, value):
            if kind == "result":
                stop.set()
        with patch("smsrecomp.systems.master_system.MasterSystemProfile.convert", side_effect=self.compiler) as compiler:
            result = convert_batch([first, second], self.output, cancel=stop, on_event=event, emit=lambda text: None)
        self.assertEqual(compiler.call_count, 1)
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["pending"], 1)
        first.path.write_bytes(bytes([9])*8192)
        with patch("smsrecomp.systems.master_system.MasterSystemProfile.convert", side_effect=AssertionError("modified ROM must not compile")):
            result = convert_batch([first], self.output, emit=lambda text: None)
        self.assertEqual(result["failed"], 1)

    def test_report_write_failure_does_not_replace_a_working_game(self):
        item = self.item("one", 1)
        self.output.mkdir()
        old = self.output / (item.key+".exe")
        old.write_bytes(b"previous good executable")
        def write_report(path, value):
            if path.name == "conversion-report.json":
                raise PermissionError("report is locked")
            return atomic_json(path, value)
        with patch("smsrecomp.systems.master_system.MasterSystemProfile.convert", side_effect=self.compiler), patch("smsrecomp.batch.atomic_json", side_effect=write_report):
            result = convert_batch([item], self.output, emit=lambda text: None)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(old.read_bytes(), b"previous good executable")

    def test_readable_names_preserve_unicode_and_obey_windows_rules(self):
        self.assertEqual(executable_name('Buggy Run'), 'Buggy Run.exe')
        self.assertEqual(executable_name('Été : test? '), 'Été _ test_.exe')
        self.assertEqual(executable_name('CON'), '_CON.exe')
        self.assertEqual(executable_name('LPT1.foo'), '_LPT1.foo.exe')

    def test_unknown_file_is_preserved_and_legacy_export_is_removed_without_archive(self):
        item = self.item('one', 1)
        self.output.mkdir()
        unrelated = self.output / 'Same title.exe'
        unrelated.write_bytes(b'unrelated program')
        legacy = self.output / (item.key + '.exe')
        legacy.write_bytes(b'old generated version')
        reports = self.output / 'datas/reports' / item.key
        reports.mkdir(parents=True)
        (reports / 'conversion-report.json').write_text(json.dumps({
            'executable': legacy.name, 'rom': {'sha256': item.sha256}}))
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler):
            result = convert_batch([item], self.output, emit=lambda text: None)
        self.assertEqual(result['succeeded'], 1)
        self.assertEqual(Path(result['games'][0]['executable']).name, 'Same title (2).exe')
        self.assertEqual(unrelated.read_bytes(), b'unrelated program')
        self.assertFalse(legacy.exists())
        self.assertFalse((self.output / 'datas/previous-executables').exists())

    def test_renamed_game_replaces_its_previous_export_without_keeping_copies(self):
        item = self.item('one', 1)
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler):
            convert_batch([item], self.output, emit=lambda text: None)
            item.title = 'New game title'
            result = convert_batch([item], self.output, emit=lambda text: None)
        self.assertEqual(result['succeeded'], 1)
        self.assertEqual({p.name for p in self.output.glob('*.exe')}, {'New game title.exe'})
        self.assertFalse((self.output / 'datas/previous-executables').exists())

    def test_missing_reports_recover_embedded_rom_identity_and_retire_duplicate(self):
        first, second = self.item('one', 1), self.item('two', 2)
        self.output.mkdir()
        # Authored binary fixtures model the runtime's brand/identity strings.
        def generated(item):
            return b'MZ\x00[Retro-Recomp]\x00' + item.sha256.encode('ascii') + b'\x00'
        base = self.output / 'Same title.exe'
        base.write_bytes(generated(first))
        revision = self.output / 'Same title (2).exe'
        revision.write_bytes(generated(second))
        duplicate = self.output / 'Same title (3).exe'
        duplicate.write_bytes(generated(first))
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler):
            result = convert_batch([second, first], self.output, emit=lambda text: None)
        self.assertEqual([Path(game['executable']).name for game in result['games']],
                         ['Same title (2).exe', 'Same title.exe'])
        self.assertEqual(result['succeeded'], 2)
        self.assertFalse(duplicate.exists())

    def test_embedded_hash_without_runtime_brand_does_not_claim_an_unknown_file(self):
        item = self.item('one', 1)
        self.output.mkdir()
        unknown = self.output / 'Same title.exe'
        original = b'MZ\x00' + item.sha256.encode('ascii') + b'\x00'
        unknown.write_bytes(original)
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler):
            result = convert_batch([item], self.output, emit=lambda text: None)
        self.assertEqual(Path(result['games'][0]['executable']).name, 'Same title (2).exe')
        self.assertEqual(unknown.read_bytes(), original)

    def test_single_rom_default_uses_the_shared_folder_and_keeps_custom_options(self):
        item = self.item('one', 1)
        import smsrecomp.core as core
        with patch('smsrecomp.core.games_directory', return_value=self.output), \
                patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler) as compiler:
            executable = core.convert(item.path, title='Custom title', frames=5, passes=2,
                                      online_cover=False, use_cover=False, icon_tags=False)
        self.assertEqual(executable, self.output / 'Custom title.exe')
        self.assertEqual(compiler.call_args.kwargs['frames'], 5)
        self.assertEqual(compiler.call_args.kwargs['passes'], 2)
        self.assertFalse(compiler.call_args.kwargs['icon_tags'])
        self.assertEqual({p.name for p in self.output.iterdir()}, {'Custom title.exe', 'datas'})

    def test_each_rom_keeps_its_own_video_override_in_a_mixed_batch(self):
        first, second = self.item('one', 1), self.item('two', 2)
        self.assertEqual((first.system, first.video_hint), ('sms', 'pal'))
        first.standard_override = 'ntsc'
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert',
                   side_effect=self.compiler) as compiler:
            record = convert_batch([first, second], self.output, emit=lambda text: None)
        self.assertEqual(record['succeeded'], 2)
        self.assertEqual([game['video_standard'] for game in record['games']], ['ntsc', 'pal'])
        self.assertEqual(compiler.call_args_list[0].kwargs['standard_override'], 'ntsc')
        self.assertNotIn('standard_override', compiler.call_args_list[1].kwargs)
