import json
from pathlib import Path
import tempfile
from threading import Barrier, Event
import unittest
from unittest.mock import patch

from smsrecomp.batch import identify, convert_batch, system_output
from smsrecomp.systems import discover_roms
from smsrecomp.core import ConversionError, executable_name
from smsrecomp.library import atomic_json


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Synthetic fixture bytes are not PE files; exercise publication
        # compression separately with a real Windows executable.
        packer = patch('smsrecomp.publishing.compact_executable')
        packer.start()
        self.addCleanup(packer.stop)
        # Match production path resolution even when TEMP uses a Windows 8.3 alias.
        self.root = Path(self.temp.name).resolve()
        self.games_root = self.root / "jeux partagés"
        self.output = self.games_root / "Master System"

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
            "rom": {"name": path.name},
            "video_model": {"standard": options.get('standard_override') or 'pal'},
            "final_checks": [{"interpreter_percent": 0}], "reference_vdp_trace_match": True}))
        return exe

    def test_console_folder_isolates_same_title_editions_and_deduplicates_exact_rom(self):
        first, second, alias = self.item("one", 1), self.item("two", 2), self.item("alias", 1)
        with patch("smsrecomp.systems.master_system.MasterSystemProfile.convert", side_effect=self.compiler) as compiler:
            record = convert_batch([first, second, alias], self.games_root, emit=lambda text: None)
        self.assertEqual((record["succeeded"], record["duplicates"]), (2, 1))
        self.assertEqual(compiler.call_count, 2)
        self.assertFalse(compiler.call_args.kwargs['publish_result'])
        self.assertFalse(list(self.output.rglob('*.txt')))
        names = {item.sha256: f'Same title (Europe, version {letter}).exe'
                 for letter, item in zip('AB', sorted((first, second), key=lambda game: game.sha256))}
        self.assertEqual({p.name for p in self.output.iterdir()}, {*names.values(), 'datas'})
        for item in (first, second):
            report = self.output / "datas/reports" / item.key / "conversion-report.json"
            self.assertEqual(json.loads(report.read_text())["executable"], names[item.sha256])
        # Reversed order in a later conversion must preserve revision/name pairing.
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler):
            repeated = convert_batch([second, first], self.games_root, emit=lambda text: None)
        self.assertEqual([Path(game['executable']).name for game in repeated['games']],
                         [names[second.sha256], names[first.sha256]])
        # Regenerating only one edition must not discard its region/version label.
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler):
            alone = convert_batch([first], self.games_root, emit=lambda text: None)
        self.assertEqual(Path(alone['games'][0]['executable']).name, names[first.sha256])
        self.assertEqual({path.name for path in self.output.glob('*.exe')}, set(names.values()))

    def test_failure_preserves_previous_executable_and_next_rom_still_runs(self):
        first, second = self.item("one", 1), self.item("two", 2)
        self.output.mkdir(parents=True)
        old = self.output / (first.key+".exe")
        old.write_bytes(b"previous good executable")
        def compile(path, **options):
            if path == first.path:
                raise ConversionError("Invalid encoding")
            return self.compiler(path, **options)
        with patch("smsrecomp.systems.master_system.MasterSystemProfile.convert", side_effect=compile):
            result = convert_batch([first, second], self.games_root, emit=lambda text: None)
        self.assertEqual((result["failed"], result["succeeded"]), (1, 1))
        self.assertEqual(old.read_bytes(), b"previous good executable")

    def test_stop_waits_for_current_game_and_changed_rom_is_refused(self):
        first, second = self.item("one", 1), self.item("two", 2)
        stop = Event()
        def event(kind, index, value):
            if kind == "result":
                stop.set()
        with patch("smsrecomp.systems.master_system.MasterSystemProfile.convert", side_effect=self.compiler) as compiler:
            result = convert_batch([first, second], self.games_root, cancel=stop, on_event=event, emit=lambda text: None)
        self.assertEqual(compiler.call_count, 1)
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["pending"], 1)
        first.path.write_bytes(bytes([9])*8192)
        with patch("smsrecomp.systems.master_system.MasterSystemProfile.convert", side_effect=AssertionError("modified ROM must not compile")):
            result = convert_batch([first], self.games_root, emit=lambda text: None)
        self.assertEqual(result["failed"], 1)

    def test_parallel_batch_overlaps_mixed_consoles_and_reserves_same_title_names(self):
        first, second = self.item('one', 1), self.item('two', 2)
        gear = self.root / 'Same title.gg'
        gear.write_bytes(bytes(32768))
        third = identify(gear)
        rendezvous = Barrier(3)

        def compile(path, **options):
            rendezvous.wait(timeout=5)  # All three conversions must overlap.
            return self.compiler(path, **options)

        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=compile), \
                patch('smsrecomp.systems.game_gear.GameGearProfile.convert', side_effect=compile):
            record = convert_batch([first, second, third], self.games_root,
                                   jobs=3, emit=lambda text: None)
        self.assertEqual(record['succeeded'], 3)
        self.assertEqual(record['jobs'], 3)
        self.assertEqual([game['sha256'] for game in record['games']],
                         [first.sha256, second.sha256, third.sha256])
        self.assertEqual([Path(game['executable']).name for game in record['games']],
                         [f'Same title (Europe, version {"A" if first.sha256 < second.sha256 else "B"}).exe',
                          f'Same title (Europe, version {"A" if second.sha256 < first.sha256 else "B"}).exe',
                          'Same title.exe'])
        self.assertEqual({Path(game['executable']).parent.name for game in record['games']},
                         {'Master System', 'Game Gear'})

    def test_parallel_stop_finishes_started_games_without_launching_next(self):
        items = [self.item(str(index), index) for index in range(1, 4)]
        stop = Event()
        rendezvous = Barrier(2)
        starts = []

        def event(kind, index, value):
            if kind == 'start':
                starts.append(index)
                if len(starts) == 2:
                    stop.set()

        def compile(path, **options):
            rendezvous.wait(timeout=5)
            return self.compiler(path, **options)

        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=compile) as compiler:
            record = convert_batch(items, self.games_root, jobs=2, cancel=stop,
                                   on_event=event, emit=lambda text: None)
        self.assertEqual(compiler.call_count, 2)
        self.assertEqual(starts, [0, 1])
        self.assertEqual((record['succeeded'], record['pending'], record['cancelled']), (2, 1, True))

    def test_identical_bytes_under_a_sequel_name_reports_the_actual_source(self):
        first_path = self.root / 'Strider.sms'
        sequel_path = self.root / 'Strider II.sms'
        first_path.write_bytes(bytes([7]) * 8192)
        sequel_path.write_bytes(first_path.read_bytes())
        first, sequel = identify(first_path), identify(sequel_path)
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler) as compiler:
            record = convert_batch([first, sequel], self.games_root, jobs=2,
                                   emit=lambda message: None)
        self.assertEqual(compiler.call_count, 1)
        self.assertEqual((record['succeeded'], record['duplicates']), (1, 1))
        self.assertEqual(record['games'][1]['duplicate_of'], 'Strider')
        self.assertEqual({path.name for path in self.output.glob('*.exe')}, {'Strider.exe'})
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert',
                   side_effect=AssertionError('Do not relabel identical ROM bytes')):
            again = convert_batch([sequel], self.games_root, emit=lambda message: None)
        self.assertEqual(again['games'][0]['duplicate_of'], 'Strider')

    def test_distinct_region_editions_use_their_source_labels(self):
        paths = [self.root / f'Game ({region}).sms' for region in ('USA', 'Europe')]
        for value, path in enumerate(paths, 1):
            path.write_bytes(bytes([value]) * 8192)
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler):
            record = convert_batch([identify(path) for path in paths], self.games_root,
                                   jobs=2, emit=lambda message: None)
        self.assertEqual([Path(game['executable']).name for game in record['games']],
                         ['Game (USA).exe', 'Game (Europe).exe'])

    def test_disabling_overwrite_skips_a_finished_game_without_touching_its_executable(self):
        item = self.item('one', 1)
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler):
            first = convert_batch([item], self.games_root, emit=lambda message: None)
        executable = Path(first['games'][0]['executable'])
        before = executable.read_bytes()
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert',
                   side_effect=AssertionError('Existing game must not be recompiled')):
            record = convert_batch([item], self.games_root, overwrite=False,
                                   emit=lambda message: None)
        self.assertEqual((record['existing'], record['succeeded'], record['failed']), (1, 0, 0))
        self.assertEqual(record['games'][0]['executable'], str(executable))
        self.assertEqual(executable.read_bytes(), before)

    def test_report_write_failure_does_not_replace_a_working_game(self):
        item = self.item("one", 1)
        self.output.mkdir(parents=True)
        old = self.output / (item.key+".exe")
        old.write_bytes(b"previous good executable")
        def write_report(path, value):
            if path.name == "conversion-report.json":
                raise PermissionError("report is locked")
            return atomic_json(path, value)
        with patch("smsrecomp.systems.master_system.MasterSystemProfile.convert", side_effect=self.compiler), patch("smsrecomp.batch.atomic_json", side_effect=write_report):
            result = convert_batch([item], self.games_root, emit=lambda text: None)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(old.read_bytes(), b"previous good executable")

    def test_readable_names_preserve_unicode_and_obey_windows_rules(self):
        self.assertEqual(executable_name('Buggy Run'), 'Buggy Run.exe')
        self.assertEqual(executable_name('Été : test? '), 'Été _ test_.exe')
        self.assertEqual(executable_name('CON'), '_CON.exe')
        self.assertEqual(executable_name('LPT1.foo'), '_LPT1.foo.exe')

    def test_unknown_file_is_preserved_and_legacy_export_is_removed_without_archive(self):
        item = self.item('one', 1)
        self.output.mkdir(parents=True)
        unrelated = self.output / 'Same title.exe'
        unrelated.write_bytes(b'unrelated program')
        legacy = self.output / (item.key + '.exe')
        legacy.write_bytes(b'old generated version')
        reports = self.output / 'datas/reports' / item.key
        reports.mkdir(parents=True)
        (reports / 'conversion-report.json').write_text(json.dumps({
            'executable': legacy.name, 'rom': {'sha256': item.sha256}}))
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler):
            result = convert_batch([item], self.games_root, emit=lambda text: None)
        self.assertEqual(result['succeeded'], 1)
        self.assertEqual(Path(result['games'][0]['executable']).name, 'Same title (2).exe')
        self.assertEqual(unrelated.read_bytes(), b'unrelated program')
        self.assertFalse(legacy.exists())
        self.assertFalse((self.output / 'datas/previous-executables').exists())

    def test_renamed_game_replaces_its_previous_export_without_keeping_copies(self):
        item = self.item('one', 1)
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler):
            convert_batch([item], self.games_root, emit=lambda text: None)
            item.title = 'New game title'
            result = convert_batch([item], self.games_root, emit=lambda text: None)
        self.assertEqual(result['succeeded'], 1)
        self.assertEqual({p.name for p in self.output.glob('*.exe')}, {'New game title.exe'})
        self.assertFalse((self.output / 'datas/previous-executables').exists())

    def test_missing_reports_recover_embedded_rom_identity_and_retire_duplicate(self):
        first, second = self.item('one', 1), self.item('two', 2)
        self.output.mkdir(parents=True)
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
            result = convert_batch([second, first], self.games_root, emit=lambda text: None)
        names = {item.sha256: f'Same title (Europe, version {letter}).exe'
                 for letter, item in zip('AB', sorted((first, second), key=lambda game: game.sha256))}
        self.assertEqual([Path(game['executable']).name for game in result['games']],
                         [names[second.sha256], names[first.sha256]])
        self.assertEqual(result['succeeded'], 2)
        self.assertFalse(duplicate.exists())
        self.assertEqual({p.name for p in self.output.glob('*.exe')}, set(names.values()))

    def test_embedded_hash_without_runtime_brand_does_not_claim_an_unknown_file(self):
        item = self.item('one', 1)
        self.output.mkdir(parents=True)
        unknown = self.output / 'Same title.exe'
        original = b'MZ\x00' + item.sha256.encode('ascii') + b'\x00'
        unknown.write_bytes(original)
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler):
            result = convert_batch([item], self.games_root, emit=lambda text: None)
        self.assertEqual(Path(result['games'][0]['executable']).name, 'Same title (2).exe')
        self.assertEqual(unknown.read_bytes(), original)

    def test_single_rom_default_uses_the_shared_folder_and_keeps_custom_options(self):
        item = self.item('one', 1)
        import smsrecomp.core as core
        with patch('smsrecomp.core.games_root', return_value=self.games_root), \
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
            record = convert_batch([first, second], self.games_root, emit=lambda text: None)
        self.assertEqual(record['succeeded'], 2)
        self.assertEqual([game['video_standard'] for game in record['games']], ['ntsc', 'pal'])
        self.assertEqual(compiler.call_args_list[0].kwargs['standard_override'], 'ntsc')
        self.assertNotIn('standard_override', compiler.call_args_list[1].kwargs)

    def test_deep_game_boy_validation_only_reaches_its_console(self):
        sms = self.item('sms', 1)
        gg = self.root / 'Authored.gg'
        gg.write_bytes(bytes(32768))
        gb = self.root / 'Authored.gb'
        gb.write_bytes(bytes(32768))
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler) as sms_compiler, \
                patch('smsrecomp.systems.game_gear.GameGearProfile.convert', side_effect=self.compiler) as gg_compiler, \
                patch('smsrecomp.systems.game_boy.GameBoyProfile.convert', side_effect=self.compiler) as gb_compiler:
            record = convert_batch([sms, identify(gg), identify(gb)], self.games_root,
                                   gb_deep_validation=True, emit=lambda text: None)
        self.assertEqual(record['succeeded'], 3)
        self.assertNotIn('gb_deep_validation', sms_compiler.call_args.kwargs)
        self.assertNotIn('gb_deep_validation', gg_compiler.call_args.kwargs)
        self.assertTrue(gb_compiler.call_args.kwargs['gb_deep_validation'])
        self.assertNotIn('gb_parallel_games', sms_compiler.call_args.kwargs)
        self.assertNotIn('gb_parallel_games', gg_compiler.call_args.kwargs)
        self.assertEqual(gb_compiler.call_args.kwargs['gb_parallel_games'], 1)

    def test_mixed_folders_route_by_console_and_report_unknown_without_touching_sources(self):
        source = self.root / 'incoming'
        source.mkdir()
        sms = source / 'Same title.sms'
        sms.write_bytes(bytes(8192))
        gg = source / 'Same title.gg'
        game_gear = bytearray(32768)
        game_gear[0x7ff0:0x7ff8] = b'TMR SEGA'
        game_gear[0x7fff] = 0x70
        gg.write_bytes(game_gear)
        other = source / 'Other game.gba'
        other.write_bytes(b'GBA' + bytes(100))
        (source / 'notes.txt').write_text('Ignore this documentation.')
        (source / 'README.md').write_text('Also ignore this Markdown file.')
        before = {path: path.read_bytes() for path in (sms, gg, other)}
        paths = discover_roms(source)
        self.assertEqual(paths, [other, gg, sms])
        with patch('smsrecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler), \
                patch('smsrecomp.systems.game_gear.GameGearProfile.convert', side_effect=self.compiler):
            record = convert_batch([identify(path) for path in paths], self.games_root,
                                   emit=lambda text: None)
        self.assertEqual((record['succeeded'], record['unrecognized'], record['failed']), (2, 1, 0))
        self.assertEqual({path.parent.name for path in self.games_root.rglob('Same title.exe')},
                         {'Master System', 'Game Gear'})
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_ambiguous_bin_requires_explicit_console_choice(self):
        path = self.root / 'Headerless.bin'
        path.write_bytes(bytes(8192))
        self.assertTrue(identify(path).unknown)
        item = identify(path, 'sms')
        self.assertEqual((item.system, item.selected_system, item.error), ('sms', 'sms', ''))
        self.assertEqual(system_output(self.games_root, 'gb'), self.games_root / 'Game Boy')

        identified = bytearray(32768)
        identified[0x7ff0:0x7ff8] = b'TMR SEGA'
        identified[0x7fff] = 0x70
        path.write_bytes(identified)
        self.assertEqual(identify(path).system, 'gg')
        self.assertTrue(identify(path, 'sms').skipped)

        named = self.root / 'Clearly Game Gear.gg'
        named.write_bytes(identified)
        mismatch = identify(named, 'sms')
        self.assertEqual((mismatch.system, mismatch.skipped, mismatch.unknown), ('gg', True, False))

        game_boy = bytearray(32768)
        game_boy[0x134:0x13a] = b'SAMPLE'
        checksum = 0
        for value in game_boy[0x134:0x14d]:
            checksum = (checksum - value - 1) & 0xff
        game_boy[0x14d] = checksum
        path.write_bytes(game_boy)
        self.assertEqual(identify(path).system, 'gb')
