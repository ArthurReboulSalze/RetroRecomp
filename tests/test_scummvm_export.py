"""The adventure export (retrorecomp/scummvm_export.py, scummvm_build.py) on authored data only: no game, no ScummVM run."""
import os
import tempfile
import unittest
from pathlib import Path

from retrorecomp import scummvm_build, scummvm_export as sx


class PackFormat(unittest.TestCase):
    def test_pack_round_trip_is_byte_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            program = root / 'program.bin'
            program.write_bytes(b'MZ' + bytes(range(256)) * 4)
            game = root / 'game'
            (game / 'sub').mkdir(parents=True)
            (game / 'A.DAT').write_bytes(bytes(range(200)))
            (game / 'sub' / 'b.bin').write_bytes(b'\x00\xff' * 1000)
            (game / 'empty.txt').write_bytes(b'')
            (game / 'stub.scummvm').write_bytes(b'')
            out = root / 'out' / 'Game.exe'
            files, data = sx.write_pack(program, game, out, sx.manifest_text('target', 'Name', '0123456789ab'),
                                        extra=(('.rr/selftest.bin', bytes(range(256))),))
            self.assertEqual((files, data), (3, 200 + 2000))
            blob = out.read_bytes()
            self.assertTrue(blob.startswith(program.read_bytes()))
            index = {name: (start, size) for name, start, size in sx.read_pack_index(out)}
            self.assertEqual(sorted(index), ['.rr/launch.ini', '.rr/selftest.bin', 'A.DAT', 'empty.txt', 'sub/b.bin'])
            for name, path in (('A.DAT', game / 'A.DAT'), ('sub/b.bin', game / 'sub' / 'b.bin')):
                start, size = index[name]
                self.assertEqual(blob[start:start + size], path.read_bytes())
            start, size = index['.rr/launch.ini']
            self.assertIn(b'target=target\nname=Name\nid=0123456789ab\n', blob[start:start + size])
            self.assertFalse(out.with_name('Game.exe.part').exists())

    def test_an_exe_without_pack_has_no_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / 'plain.exe'
            plain.write_bytes(b'MZ' + b'\0' * 100)
            self.assertEqual(sx.read_pack_index(plain), [])


class Names(unittest.TestCase):
    def test_titles_follow_the_export_convention(self):
        self.assertEqual(sx.exe_title('The Example Game'), 'Example Game, The')
        self.assertEqual(sx.exe_title('Example II: The Subtitle'), 'Example II - The Subtitle')
        self.assertEqual(sx.exe_title('Odd <name>?'), 'Odd name')
        self.assertEqual(sx.datas_name("Example's Game: Part 2!"), 'Example_s_Game_Part_2')

    def test_id_depends_on_names_and_sizes_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            (game / 'x.dat').write_bytes(b'abc')
            first = sx.folder_id(game)
            (game / 'x.dat').write_bytes(b'xyz')            # same size, other bytes
            self.assertEqual(sx.folder_id(game), first)
            (game / 'x.dat').write_bytes(b'abcd')
            self.assertNotEqual(sx.folder_id(game), first)
            self.assertRegex(first, r'^[0-9a-f]{12}$')


class Detection(unittest.TestCase):
    # ScummVM prints the paths of the platform it runs on (a drive and backslashes on Windows, a rooted path on Linux),
    # with a trailing separator on Windows: the fake output is built from the native form of one base folder.
    BASE = Path(os.path.abspath(os.sep + 'games'))
    OUTPUT = ('GameID     Description     Full Path\n'
              '---------- --------------- ---------\n'
              f'eng1:gamea                     Game A (CD/DOS/French)                  {BASE / "a"}{os.sep}\n'
              f'eng1:gamea                     Game A (DOS/German)                     {BASE / "a"}{os.sep}\n'
              f'eng2:gameb                     Game B: Sub (Windows/English)           {BASE / "a" / "sub"}{os.sep}\n'
              f'eng3:gamec                     Game Part V: The End (DOS/French) {BASE / "c"}{os.sep}\n')

    def test_a_colon_in_the_title_is_not_a_drive(self):
        found = sx.parse_detection(self.OUTPUT, self.BASE / 'c')
        self.assertEqual([(c.gameid, c.title, c.language) for c in found], [('gamec', 'Game Part V: The End', 'French')])

    def test_candidates_of_the_folder_only(self):
        found = sx.parse_detection(self.OUTPUT, self.BASE / 'a')
        self.assertEqual([(c.engine, c.gameid, c.language, c.platform) for c in found],
                         [('eng1', 'gamea', 'French', 'CD/DOS'), ('eng1', 'gamea', 'German', 'DOS')])
        self.assertEqual(found[0].title, 'Game A')


class ToolsMissing(unittest.TestCase):
    """Without the build tools (and no runtime built yet) nothing starts a build: discovery and the interface say why."""

    def folder(self, tmp):
        game = Path(tmp) / 'Some Game'
        game.mkdir()
        (game / 'DATA.001').write_bytes(b'x' * 64)         # passes the cheap pre-filter, so detection is asked for
        return game

    def refuse(self):
        from unittest import mock
        return mock.patch.object(sx, '_detect_runtime', side_effect=scummvm_build.ScummvmToolsMissing('tools are missing'))

    def test_discovery_refuses_with_a_sentence_instead_of_raising(self):
        from retrorecomp.systems import registry
        sx._DETECTED.clear()
        with tempfile.TemporaryDirectory() as tmp, self.refuse():
            game = self.folder(tmp)
            unavailable = []
            self.assertEqual(registry.discover_folders(Path(tmp), unavailable), [])
            self.assertEqual([exc.key for exc in unavailable], ['scummvm_tools_missing'])
            self.assertEqual(registry.discover_folders(Path(tmp)), [])      # a caller that gives no list is spared too
            del game

    def test_a_folder_given_directly_becomes_an_error_on_its_item(self):
        from retrorecomp.batch import identify
        sx._DETECTED.clear()
        with tempfile.TemporaryDirectory() as tmp, self.refuse():
            item = identify(self.folder(tmp), 'scummvm')
            self.assertIn('tools are missing', item.error)

    def test_the_window_logs_the_sentence_once(self):
        from types import SimpleNamespace
        from retrorecomp.gui_queue import QueueMixin
        sx._DETECTED.clear()
        window = SimpleNamespace(tr=lambda key, **values: key)
        with tempfile.TemporaryDirectory() as tmp, self.refuse():
            self.folder(tmp)
            files, logs = QueueMixin._expand_paths(window, [Path(tmp)])
            self.assertEqual(files, [])
            self.assertEqual(logs, ['scummvm_tools_missing'])

    def test_the_sentence_exists_in_every_language(self):
        from retrorecomp.i18n import LANGUAGES, catalog, tr
        for code in LANGUAGES:
            self.assertNotEqual(tr('scummvm_tools_missing', code), 'scummvm_tools_missing', code)
        self.assertTrue(all(catalog(code)['ui'].get('scummvm_tools_missing') for code in LANGUAGES[2:]))


class OptionsPage(unittest.TestCase):
    """Patch 0002: the Retro-Recomp page of the in-game options and the settings shared through datas/Retro-Recomp.ini
    (checked headless with the real runtime: .build/scummvm-step2/ui_cases.py; here, the text of the patch)."""

    def setUp(self):
        self.patch = (scummvm_build.PATCH_DIRECTORY / '0002-retrorecomp-options-page.patch').read_text(encoding='utf-8')

    def test_the_series_has_both_patches_in_order(self):
        names = sorted(path.name for path in scummvm_build.PATCH_DIRECTORY.glob('*.patch'))
        self.assertEqual(names, ['0001-retrorecomp-pack-launch-nodialog.patch', '0002-retrorecomp-options-page.patch'])

    def test_the_page_replaces_the_backend_tab_of_a_packed_exe_only(self):
        self.assertIn('packedModeActive() ? retroRecompOptionsTabTitle()', self.patch)
        self.assertIn('if (!packedModeActive())\n+\t\treturn nullptr;', self.patch)

    def test_the_settings_are_shared_both_ways(self):
        for key in ('fullscreen', 'stretch_mode', 'aspect_ratio', 'music_volume', 'sfx_volume', 'speech_volume', 'mute'):
            self.assertIn(f'"{key}"', self.patch)
        self.assertIn('void packedSyncSettings()', self.patch)
        self.assertIn('packedSyncSettings();', self.patch)

    def test_every_text_of_the_page_has_the_five_languages(self):
        rows = [line for line in self.patch.splitlines() if line.startswith('+\t/* k') and '*/' in line]
        self.assertGreaterEqual(len(rows), 10)
        for row in rows:
            if row.rstrip().endswith('},'):
                self.assertEqual(row.count('", "') + 1, 5, row)

    def test_the_menu_key_is_hinted_at_the_start_in_five_languages(self):
        # ticked on the main thread only (a timer thread crashed some quits), at every event poll and every delay
        self.assertIn('g_system->displayMessageOnOSD(retroRecompMenuHint())', self.patch)
        self.assertIn('packedMainThreadTick(true);', self.patch)
        self.assertIn('packedMainThreadTick();      // Retro-Recomp: the menu hint also appears while an engine waits', self.patch)
        self.assertNotIn('installTimerProc(hintDriver', self.patch)
        for text in ('"Help: Ctrl+F1 · Menu: Ctrl+F2"', '"Aide : Ctrl+F1 · Menu : Ctrl+F2"', '"Hilfe: Strg+F1 · Menü: Strg+F2"',
                     '"Ayuda: Ctrl+F1 · Menú: Ctrl+F2"', '"Aiuto: Ctrl+F1 · Menu: Ctrl+F2"'):
            self.assertIn(text, self.patch)
        # shown for seven seconds, again later, and once more on the first mouse move (an OSD message lasts about two seconds)
        self.assertIn('g_hintBurst = 8;', self.patch)
        self.assertIn('mouse != g_hintMouse', self.patch)

    def test_the_help_tab_lists_the_shortcuts_in_five_languages(self):
        self.assertIn('retroRecompHelpTabTitle()', self.patch)
        for number in range(1, 12):
            self.assertIn(f'/* kHelp{number} ', self.patch)
        for shortcut in ('Ctrl+F1', 'Ctrl+F2', 'Ctrl+F5', 'Alt+Enter', 'Ctrl+F4', 'Ctrl+F3', 'Ctrl+U', 'Alt+F4', 'Alt+S'):
            self.assertIn(shortcut, self.patch)
        self.assertIn('static const int kLines = 11;', self.patch)

    def test_ctrl_f1_and_ctrl_f2_open_the_options_dialog_on_their_tab(self):
        self.assertIn('addDefaultInputMapping("C+F1")', self.patch)
        self.assertIn('addDefaultInputMapping("C+F2")', self.patch)
        self.assertIn('retroRecompRequestOptions(1);', self.patch)      # Ctrl+F1: the Help
        self.assertIn('retroRecompRequestOptions(0);', self.patch)      # Ctrl+F2: the Retro-Recomp page
        self.assertIn('retroRecompTakeOptionsRequest(rrTab)', self.patch)
        self.assertIn('configDialog.selectRetroRecompTab(rrTab);', self.patch)
        self.assertNotIn('"C+F5"', self.patch)       # Ctrl+F5 stays ScummVM's own menu

    def test_the_osd_uses_retro_recomps_palette_in_a_packed_exe(self):
        from retrorecomp.branding import COLORS
        header, gold = COLORS['header'], COLORS['gold_hover']
        self.assertEqual((int(header[1:3], 16), int(header[3:5], 16), int(header[5:7], 16)), (24, 24, 24))
        self.assertEqual((int(gold[1:3], 16), int(gold[3:5], 16), int(gold[5:7], 16)), (239, 198, 79))
        self.assertIn('rrPalette ? 24 : 64', self.patch)
        self.assertIn('rrPalette ? 239 : 255', self.patch)
        self.assertIn('rrPalette ? 198 : 255', self.patch)
        self.assertIn('rrPalette ? 79 : 255', self.patch)

    def test_the_scanlines_are_the_host_kits_mask_drawn_after_the_scaling(self):
        # same arithmetic as native/scanlines.h: 85/255 on the last third of every source row, nothing under twice the rows
        scanlines = (scummvm_build.ROOT / 'native' / 'scanlines.h').read_text(encoding='utf-8')
        self.assertIn('(85 * (end - begin) + step / 2) / step', scanlines)
        self.assertIn('(85 * (end - begin) + step / 2) / step', self.patch)
        self.assertIn('(uint64)height < 2 * (uint64)sourceRows', self.patch)
        self.assertIn('rrDrawScanlines(_renderer, viewport, _videoMode.screenHeight);', self.patch)
        self.assertIn('packedScanlinesOn() && !_overlayVisible', self.patch)      # never over the menus
        self.assertNotIn('"tv"', self.patch)
        self.assertIn('{"Help", "Aide", "Hilfe", "Ayuda", "Aiuto"}', self.patch)

    def test_ctrl_f3_cycles_the_host_kit_filters_and_ctrl_f4_toggles_pixel_perfect(self):
        self.assertIn('addDefaultInputMapping("C+F3")', self.patch)
        self.assertIn('addDefaultInputMapping("C+F4")', self.patch)
        # the order of the host kit's F3: sharp pixels, xBR (HQ2x here), Scale2x, scanlines
        import re
        effects = re.findall(r'^\+\t\{"(normal|hq|advmame)",\s+\{"([^"]+)"', self.patch, re.M)
        self.assertEqual([(scaler, name) for scaler, name in effects],
                         [('normal', 'Sharp pixels'), ('hq', 'HQ2x (like xBR)'), ('advmame', 'Scale2x'), ('normal', 'Scanlines')])
        self.assertIn('"rr_scanlines"', self.patch)
        self.assertIn('"pixel-perfect"', self.patch)
        self.assertIn('ConfMan.flushToDisk();', self.patch)
        for key in ('"scaler"', '"scale_factor"'):
            self.assertIn(key, self.patch)

    def test_the_text_table_follows_the_order_of_its_enum(self):
        import re
        enum = re.search(r'\+\s+(kTitle,[^\n]*?), kTextCount', self.patch)
        self.assertIsNotNone(enum)
        names = [name.strip() for name in enum.group(1).split(',')]
        rows = list(dict.fromkeys(re.findall(r'^\+\t/\* (k\w+)\s*\*/\s+\{', self.patch, re.M)))     # one row may exist per platform
        self.assertEqual(rows, names)

    def test_screenshots_stay_in_the_games_folder(self):
        self.assertIn('"screenshotpath"', self.patch)


class NoModalWindow(unittest.TestCase):
    """The patch keeps every route to a modal window closed in a packed executable (checked headless on an invisible desktop
    with the real runtime; here, the text of the patch)."""

    def setUp(self):
        self.patch = (scummvm_build.PATCH_DIRECTORY / '0001-retrorecomp-pack-launch-nodialog.patch').read_text(encoding='utf-8')

    def test_the_native_message_box_is_closed(self):
        self.assertIn('if (packedModeActive() || getenv("RR_NO_DIALOGS"))', self.patch)

    def test_scummvms_own_error_window_goes_to_the_log(self):
        self.assertIn('logInsteadOfDialog', self.patch)
        self.assertIn('g_system->logMessage(LogMessageType::kError', self.patch)

    def test_a_failed_run_never_falls_back_to_the_launcher(self):
        self.assertIn('rrExitCode = 1;', self.patch)
        self.assertIn('return rrExitCode;', self.patch)
        self.assertIn('&& !packedModeActive())', self.patch)

    def test_a_crash_leaves_a_line_in_crash_log(self):
        self.assertIn('installCrashLog(gameDir + kNativeSep + "crash.log");', self.patch)
        self.assertIn('SetUnhandledExceptionFilter', self.patch)


class PackedData(unittest.TestCase):
    """Platforms without embedded resources (Linux) carry the engine data and the GUI themes in the pack."""

    def test_collect_data_follows_the_resource_lists_of_the_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, family = Path(tmp) / 'tree', Path(tmp) / 'family'
            (tree / 'gui/themes').mkdir(parents=True)
            (tree / 'dists/engine-data').mkdir(parents=True)
            for name in ('scummremastered.zip', 'gui-icons.dat', 'shaders.dat'):
                (tree / 'gui/themes' / name).write_bytes(b'x')
            (tree / 'dists/engine-data/alpha.dat').write_bytes(b'a')
            (tree / 'dists/engine-data/fonts.dat').write_bytes(b'f')
            (tree / 'dists/engine-data/core.dat').write_bytes(b'c')
            (tree / 'dists/engine-data/beta.dat').write_bytes(b'b')
            (tree / 'dists/engine-data/engine_data_core.mk').write_text(
                'DIST_FILES_LIST += dists/engine-data/core.dat\n', encoding='utf-8')
            (tree / 'dists/engine-data/engine_data.mk').write_text(
                'ifdef ENABLE_ALPHA\nDIST_FILES_LIST += dists/engine-data/alpha.dat\nendif\n'
                'ifdef ENABLE_BETA\nDIST_FILES_LIST += dists/engine-data/beta.dat\nendif\n'
                'ifdef USE_FREETYPE2\nDIST_FILES_LIST += dists/engine-data/fonts.dat\nendif\n'
                'ifdef ENABLE_ALPHA\nDIST_FILES_LIST += dists/engine-data/missing.dat\nendif\n', encoding='utf-8')
            self.assertEqual(scummvm_build.collect_data(tree, family, ('alpha',)),
                             ['alpha.dat', 'core.dat', 'fonts.dat', 'gui-icons.dat', 'scummremastered.zip'])

    def test_a_runtime_with_data_beside_it_packs_it_and_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / 'scummvm-runtime'
            runtime.write_bytes(b'ELF')
            self.assertEqual(sx.data_members(runtime), ())
            (Path(tmp) / 'data').mkdir()
            (Path(tmp) / 'data' / 'lure.dat').write_bytes(b'LURE')
            self.assertEqual(sx.data_members(runtime), (('.rr/data/lure.dat', b'LURE'),))
        self.assertNotIn('data=1', sx.manifest_text('t', 'N', 'i'))
        self.assertTrue(sx.manifest_text('t', 'N', 'i', data=True).endswith('data=1\n'))


class SharedPreparation(unittest.TestCase):
    """batch._needs_shared: a batch of emulated games alone does not build the Z80 translator or the shared SDL2."""

    def items(self, *systems, **flags):
        from retrorecomp.batch import BatchItem
        return [BatchItem(Path(f'g{i}'), f'g{i}', system, **flags) for i, system in enumerate(systems)]

    def test_emulated_only_batch_skips_the_preparation(self):
        from retrorecomp.batch import _needs_shared
        items = self.items('scummvm', 'scummvm')
        self.assertFalse(_needs_shared(items, [0, 1]))

    def test_a_mixed_batch_or_an_empty_one_prepares(self):
        from retrorecomp.batch import _needs_shared
        items = self.items('scummvm', 'sms')
        self.assertTrue(_needs_shared(items, [0, 1]))
        self.assertFalse(_needs_shared(items, [0]))
        self.assertTrue(_needs_shared(items, []))            # nothing queued: as before

    def test_skipped_unknown_or_failed_items_do_not_count(self):
        from retrorecomp.batch import BatchItem, _needs_shared
        items = [BatchItem(Path('a'), 'a', 'scummvm'), BatchItem(Path('b'), 'b', 'sms', skipped=True),
                 BatchItem(Path('c'), 'c', 'nes', error='unreadable'), BatchItem(Path('d'), 'd', '', unknown=True)]
        self.assertFalse(_needs_shared(items, [0, 1, 2, 3]))


class RelativeFolder(unittest.TestCase):
    def test_a_relative_folder_matches_the_absolute_path_scummvm_prints(self):
        import os
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp).resolve()
            (parent / 'game').mkdir()
            line = f'eng1:gamea                     Game A (DOS/English)                  {parent / "game"}\n'
            before = os.getcwd()
            os.chdir(parent)
            try:
                with mock.patch.object(sx.subprocess, 'run', return_value=mock.Mock(stdout=line)):
                    found = sx.detect(Path('game'), Path('runtime'))
            finally:
                os.chdir(before)
            self.assertEqual([(c.gameid, c.language) for c in found], [('gamea', 'English')])


class Families(unittest.TestCase):
    def test_family_rule_is_generic(self):
        self.assertEqual(scummvm_build.family_for('anyengine'), 'anyengine')
        self.assertEqual(scummvm_build.engines_for('anyengine'), ('anyengine',))
        self.assertIn('scumm_7_8', scummvm_build.engines_for(scummvm_build.family_for('scumm')))
        self.assertTrue(scummvm_build.engines_for(scummvm_build.DETECT_FAMILY))

    def test_fallback_engines_are_read_from_the_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            for engine, text in (('alpha', 'ADDetectedGame fallbackDetectExtern(uint md5Bytes) const;'), ('beta', 'nothing')):
                (tree / 'engines' / engine).mkdir(parents=True)
                (tree / 'engines' / engine / 'metaengine.cpp').write_text(text, encoding='utf-8')
            self.assertEqual(scummvm_build.fallback_engines(tree), ('alpha',))

    def test_static_sdl_system_libraries_follow_its_pkg_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            self.assertEqual(scummvm_build.static_system_libraries(prefix), ['m', 'dl', 'pthread'])     # no file: the default
            (prefix / 'lib' / 'pkgconfig').mkdir(parents=True)
            (prefix / 'lib' / 'pkgconfig' / 'sdl2.pc').write_text(
                'Libs: -L${libdir} -lSDL2\nLibs.private: -lm -ldl -lpthread -lrt -lm -Wl,--no-undefined\n', encoding='utf-8')
            self.assertEqual(scummvm_build.static_system_libraries(prefix), ['m', 'dl', 'pthread', 'rt'])

    def test_runtime_identity_names_the_pins(self):
        identity = scummvm_build.runtime_identity('scumm')
        self.assertEqual(identity['scummvm_commit'], scummvm_build.SCUMMVM_REV)
        self.assertEqual(identity['gui_languages'], ['en', 'fr', 'de', 'es', 'it'])
        self.assertRegex(identity['patch_sha256'], r'^[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()
