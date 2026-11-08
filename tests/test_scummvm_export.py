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


class WindowFolderImport(unittest.TestCase):
    """The window's folder import (gui_queue: choose_directory -> import_paths -> _expand_paths -> identify) on authored
    folders, with ScummVM's detection replaced by a fake that recognises a folder holding GAME.DAT. A game folder that
    also holds `.bin` files was the case that left the window empty (the `.bin` data was queued as cartridges)."""

    def setUp(self):
        from unittest import mock
        sx._DETECTED.clear()
        candidate = sx.Candidate('eng1', 'gamea', 'Game A (DOS/English)', 'Game A', 'English', 'DOS')
        self.patches = [
            mock.patch.object(sx, '_detect_runtime', return_value=Path('fake-runtime')),
            mock.patch.object(sx, 'detect', side_effect=lambda folder, runtime: [candidate]
                              if (Path(folder) / 'GAME.DAT').is_file() else [])]
        for patcher in self.patches:
            patcher.start()
        self.addCleanup(lambda: [patcher.stop() for patcher in self.patches])
        self.addCleanup(sx._DETECTED.clear)

    def games(self, tmp, with_bin=True):
        """Authored folders: `Game A` (a game whose data has .bin files), `Other` (a plain cartridge dump beside it)."""
        root = Path(tmp)
        game = root / 'Game A'
        game.mkdir()
        (game / 'GAME.DAT').write_bytes(b'x' * 64)
        if with_bin:
            (game / 'LEVEL1.BIN').write_bytes(b'\1' * 64)
            (game / 'LEVEL2.BIN').write_bytes(b'\2' * 64)
        return root, game

    def expand(self, paths):
        from types import SimpleNamespace
        from retrorecomp.gui_queue import QueueMixin
        window = SimpleNamespace(tr=lambda key, **values: key)
        return QueueMixin._expand_paths(window, paths)

    def prepare(self, path, mode):
        from types import SimpleNamespace
        from retrorecomp.gui_queue import QueueMixin
        return QueueMixin._prepare_path(SimpleNamespace(), path, mode, Path('Games'))

    def test_the_data_files_of_a_game_folder_are_not_queued_as_cartridges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, game = self.games(tmp)
            for given in (game, root):               # the folder that is the game, and its parent
                files, logs = self.expand([given])
                self.assertEqual([Path(path) for path in files], [game], given)
                self.assertEqual(logs, [])

    def test_both_system_modes_give_the_game_one_row_and_no_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, game = self.games(tmp)
            files, _ = self.expand([root])
            for mode in ('auto', 'scummvm'):
                rows = [self.prepare(path, mode) for path in files]
                self.assertEqual([(row['item'].system, row['item'].title, row['status']) for row in rows],
                                 [('scummvm', 'Game A', 'waiting')], mode)

    def test_a_loose_file_in_the_adventure_mode_is_an_item_error_not_a_dead_scan(self):
        # "Adventure (ScummVM)" hands every queued file to the profile: an adventure is a folder, never a file.
        with tempfile.TemporaryDirectory() as tmp:
            loose = Path(tmp) / 'LOOSE.BIN'
            loose.write_bytes(b'\3' * 64)
            row = self.prepare(loose, 'scummvm')
            self.assertEqual(row['status'], 'invalid')
            self.assertIn('is a folder', row['item'].error)

    def test_a_folder_scummvm_does_not_recognise_is_an_item_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, game = self.games(tmp)
            (game / 'GAME.DAT').unlink()
            row = self.prepare(game, 'scummvm')
            self.assertIn(row['status'], ('invalid', 'unrecognized'))      # a row with its reason, in the queue
            self.assertTrue(row['item'].error)

    def test_whatever_the_reader_raises_the_scan_goes_on(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            root, game = self.games(tmp)
            with mock.patch('retrorecomp.gui_queue.identify', side_effect=RuntimeError('boom')):
                row = self.prepare(game, 'auto')
            self.assertEqual(row['status'], 'invalid')
            self.assertIn('boom', row['item'].error)

    def test_a_detection_that_fails_to_build_is_a_sentence_not_a_traceback(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            self.games(tmp, with_bin=False)
            sx._DETECTED.clear()
            with mock.patch.object(sx, '_detect_runtime', side_effect=scummvm_build.ScummvmBuildError('cmake failed')):
                files, logs = self.expand([Path(tmp)])
                self.assertEqual((files, logs), ([], ['scummvm_detect_failed']))
                self.assertEqual(self.prepare(Path(tmp) / 'Game A', 'auto')['status'], 'invalid')

    def test_a_folder_that_adds_nothing_says_so(self):
        # What the player saw ("no ROM found") with a folder ScummVM does not recognise: now a sentence says why.
        with tempfile.TemporaryDirectory() as tmp:
            root, game = self.games(tmp, with_bin=False)
            (game / 'GAME.DAT').unlink()
            files, logs = self.expand([game])
            self.assertEqual([Path(path) for path in files], [])
            self.assertEqual(logs, ['import_folder_empty'])
            files, logs = self.expand([root])                       # the parent holds nothing recognised either
            self.assertIn('import_folder_empty', logs)

    def test_a_folder_with_a_game_does_not_say_it_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, game = self.games(tmp)
            self.assertNotIn('import_folder_empty', self.expand([game])[1])

    def test_the_empty_folder_sentence_exists_in_every_language(self):
        from retrorecomp.i18n import LANGUAGES, catalog, tr
        for code in LANGUAGES:
            self.assertIn('Game', tr('import_folder_empty', code, folder='Game'), code)
        self.assertTrue(all(catalog(code)['ui'].get('import_folder_empty') for code in LANGUAGES[2:]))

    def test_the_command_line_discovers_the_same_games(self):
        from retrorecomp.systems.registry import discover_games
        with tempfile.TemporaryDirectory() as tmp:
            root, game = self.games(tmp)
            (root / 'cartridge.sms').write_bytes(bytes(8192))
            roms, folders = discover_games(root)
            self.assertEqual(folders, [game])
            self.assertEqual([Path(rom).name for rom in roms], ['cartridge.sms'])

    def test_the_failure_sentence_exists_in_every_language(self):
        from retrorecomp.i18n import LANGUAGES, catalog, tr
        for code in LANGUAGES:
            self.assertNotEqual(tr('scummvm_detect_failed', code), 'scummvm_detect_failed', code)
        self.assertTrue(all(catalog(code)['ui'].get('scummvm_detect_failed') for code in LANGUAGES[2:]))
        for code in LANGUAGES[:2]:
            self.assertNotEqual(tr('scummvm_preparing', code), 'scummvm_preparing', code)
        self.assertTrue(all(catalog(code)['ui'].get('scummvm_preparing') for code in LANGUAGES[2:]))

    def test_the_scan_says_when_the_detection_has_to_be_built(self):
        from types import SimpleNamespace
        from unittest import mock
        from retrorecomp.gui_queue import QueueMixin
        window = SimpleNamespace(tr=lambda key, **values: key)

        def building(started=None, emit=None):
            started()
            return Path('fake-runtime')

        with tempfile.TemporaryDirectory() as tmp:
            _root, game = self.games(tmp)
            said = []
            with mock.patch.object(sx, '_detect_runtime', side_effect=building):
                files, _logs = QueueMixin._expand_paths(window, [game], notice=said.append)
            self.assertEqual((files, said), ([game], ['scummvm_preparing']))
            # A runtime already built: nothing to say.
            sx._DETECTED.clear()
            said = []
            files, _logs = QueueMixin._expand_paths(window, [game], notice=said.append)
            self.assertEqual((files, said), ([game], []))


class PackagedExe(unittest.TestCase):
    """A packaged exe runs its modules from a temporary folder removed when it closes (PyInstaller's _MEIPASS). A root read
    from __file__ put .deps there: every first drop of a folder cloned and compiled ScummVM again in that folder, in silence."""

    SIMULATION = (
        'import json, sys\n'
        'sys.frozen, sys._MEIPASS, sys.executable = True, sys.argv[1], sys.argv[2]\n'
        'from retrorecomp import scummvm_build as build\n'
        'print(json.dumps([str(build.deps_directory()), str(build.runtime_path("detect")), str(build.PATCH_DIRECTORY)]))\n')

    def paths_of(self, unpacked, exe):
        import json
        import subprocess
        import sys
        repository = Path(__file__).resolve().parents[1]
        output = subprocess.run([sys.executable, '-B', '-c', self.SIMULATION, str(unpacked), str(exe)], cwd=repository,
                                capture_output=True, text=True, check=True).stdout
        return [Path(item) for item in json.loads(output)]

    def test_the_build_lives_beside_the_exe_and_the_patches_inside_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            unpacked = base / 'unpacked'
            deps, runtime, patches = self.paths_of(unpacked, base / 'Games' / 'Retro-Recomp.exe')
            self.assertEqual(deps, base / 'Games' / '.deps')
            self.assertEqual(runtime.parents[2], deps)
            self.assertEqual(patches, unpacked / 'native' / 'scummvm' / 'patches')

    def test_an_exe_in_export_uses_the_deps_of_its_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp).resolve()
            (project / 'retrorecomp').mkdir()
            (project / 'RetroRecomp.py').touch()
            (project / 'retrorecomp' / 'core.py').touch()
            deps, _runtime, _patches = self.paths_of(project / 'unpacked', project / 'Export' / 'Retro-Recomp.exe')
            self.assertEqual(deps, project / '.deps')

    def test_no_module_of_the_exe_reads_a_folder_from_its_own_file(self):
        """Each exception says why it is safe; a new module takes its root from retrorecomp.paths."""
        allowed = {'paths.py',       # the one place that decides, and only outside a packaged exe
                   'core.py',        # hashes the __file__ of modules, never a folder to work in
                   'publishing.py',  # the branch that runs from the sources
                   'upstreams.py'}   # read by tools/check_upstreams.py, from the sources
        package = Path(__file__).resolve().parents[1] / 'retrorecomp'
        found = {source.name for source in package.rglob('*.py') if '__file__' in source.read_text(encoding='utf-8')}
        self.assertEqual(found - allowed, set())


class FirstBuild(unittest.TestCase):
    """A first use of the detection family, with every build step replaced: what it leaves and what it says."""

    def setUp(self):
        from unittest import mock
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.steps = []

        def prepare(log, emit):
            tree = scummvm_build.scummvm_checkout()
            (tree / 'engines' / 'sci').mkdir(parents=True)
            (tree / 'engines' / 'sci' / 'metaengine.cpp').write_text('fallbackDetectExtern', encoding='utf-8')
            (tree / 'dists').mkdir()
            return tree

        def run(command, cwd, log, timeout=3600):
            self.steps.append(Path(str(command[0])).name)
            if Path(str(command[0])).name.endswith('strip'):
                Path(command[2]).write_bytes(b'runtime')
            return ''

        from retrorecomp import core
        for patcher in (mock.patch.object(scummvm_build, 'ROOT', self.root), mock.patch.object(core, 'ROOT', self.root),
                        mock.patch.object(scummvm_build, '_require_portable_tools'),
                        mock.patch.object(scummvm_build, 'prepare_sources', side_effect=prepare),
                        mock.patch.object(scummvm_build, '_build_freetype', return_value=self.root),
                        mock.patch.object(scummvm_build, '_ensure_sdl'),
                        mock.patch.object(scummvm_build, '_host_tool', return_value=Path('create_project')),
                        mock.patch.object(scummvm_build, '_sdl_shim', return_value=self.root),
                        mock.patch.object(scummvm_build, 'collect_data', return_value=[]),
                        mock.patch.object(scummvm_build, '_run', side_effect=run),
                        mock.patch.object(core, 'toolchain', return_value=('cmake', 'Ninja'))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_the_first_runtime_is_not_stale_at_once_and_it_is_announced_once(self):
        started = []
        family = scummvm_build.DETECT_FAMILY
        out = scummvm_build.build_runtime(family, lambda text: None, started=lambda: started.append(1))
        self.assertEqual(started, [1])
        self.assertTrue(out.is_file())
        self.steps.clear()
        self.assertEqual(scummvm_build.build_runtime(family, lambda text: None, started=lambda: started.append(1)), out)
        self.assertEqual((self.steps, started), ([], [1]), 'a second build, or a sentence with nothing being built')

    def test_nothing_is_announced_without_the_tools(self):
        from unittest import mock
        started = []
        with mock.patch.object(scummvm_build, '_require_portable_tools', side_effect=scummvm_build.ScummvmToolsMissing('no')):
            with self.assertRaises(scummvm_build.ScummvmToolsMissing):
                scummvm_build.build_runtime(scummvm_build.DETECT_FAMILY, lambda text: None, started=lambda: started.append(1))
        self.assertEqual(started, [])


class InterruptedClone(unittest.TestCase):
    def test_a_window_closed_during_the_download_leaves_no_checkout(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            place = Path(tmp).resolve() / 'scummvm'
            log = Path(tmp).resolve() / 'log'
            attempts = []

            def run(command, cwd, log, timeout=3600):
                if 'clone' not in command:
                    return 'wanted\n'
                target = Path(command[-1])
                self.assertFalse(target.exists(), 'the earlier partial clone was not removed')
                (target / '.git').mkdir(parents=True)
                pack = target / '.git' / 'pack'
                pack.write_bytes(b'')
                pack.chmod(0o444)       # git leaves its pack files read-only
                attempts.append(target)
                if len(attempts) == 1:
                    raise KeyboardInterrupt('the process stops here')
                return ''

            with mock.patch.object(scummvm_build, '_run', side_effect=run):
                with self.assertRaises(KeyboardInterrupt):
                    scummvm_build._checkout(place, 'url', 'tag', 'wanted', log, lambda text: None)
                self.assertFalse(place.exists())      # the next start does not mistake it for a checkout
                scummvm_build._checkout(place, 'url', 'tag', 'wanted', log, lambda text: None)
            self.assertTrue((place / '.git').is_dir())
            self.assertEqual(attempts[0], attempts[1])
            self.assertFalse(attempts[0].exists())
            (place / '.git' / 'pack').chmod(0o666)    # the temporary folder can be removed


class ReconfiguredFolder(unittest.TestCase):
    """A build folder made with the compiler at another place: CMake deletes its cache, loses the -D values of the command line and
    stops on find_package(SDL2) (what Sam & Max met in the packaged exe, once the runtime of its family was stale)."""

    def setUp(self):
        from unittest import mock
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.build, self.log = base / 'scumm' / 'build', base / 'scumm.log'
        self.compiler = 'A/clang'
        self.fail = False

        def run(command, cwd, log, timeout=3600):
            self.build.mkdir(parents=True, exist_ok=True)
            (self.build / 'CMakeCache.txt').write_text('cache', encoding='utf-8')
            if self.fail:
                raise scummvm_build.ScummvmBuildError('configure failed')
            return ''

        for patcher in (mock.patch.object(scummvm_build, '_run', side_effect=run),
                        mock.patch.object(scummvm_build.shutil, 'which', side_effect=lambda name, path=None: self.compiler)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def configure(self, flag='-DSDL2_DIR=x'):
        scummvm_build._configure('cmake', Path('cfg'), self.build, 'Ninja', [flag], Path('.'), self.log)

    def objects(self):
        place = self.build / 'CMakeFiles' / 'game.obj'
        place.parent.mkdir(parents=True, exist_ok=True)
        place.touch()
        return place

    def test_the_same_command_and_compiler_keep_the_objects(self):
        self.configure()
        objects = self.objects()
        self.configure()
        self.assertTrue(objects.exists())

    def test_a_compiler_elsewhere_starts_from_a_new_folder(self):
        self.configure()
        objects = self.objects()
        self.compiler = 'B/clang'
        self.configure()
        self.assertFalse(objects.exists())
        self.assertTrue((self.build / 'CMakeCache.txt').exists())

    def test_another_command_starts_from_a_new_folder(self):
        self.configure()
        objects = self.objects()
        self.configure('-DSDL2_DIR=moved')
        self.assertFalse(objects.exists())

    def test_a_folder_from_an_earlier_version_starts_again(self):
        objects = self.objects()
        self.configure()
        self.assertFalse(objects.exists())

    def test_nothing_goes_on_from_a_configure_that_failed(self):
        self.configure()
        self.fail = True
        with self.assertRaises(scummvm_build.ScummvmBuildError):
            self.configure()
        self.fail = False
        objects = self.objects()
        self.configure()
        self.assertFalse(objects.exists())


class WhatThePlayerReads(unittest.TestCase):
    """What is missing and what to do, never a tool's own failure; the raw output stays in the log."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = Path(self.temp.name).resolve() / 'family.log'

    def test_a_tool_that_fails_is_a_sentence_and_its_output_is_in_the_log(self):
        import sys
        with self.assertRaises(scummvm_build.ScummvmBuildError) as caught:
            scummvm_build._run([sys.executable, '-c', 'print("raw output"); raise SystemExit(3)'], self.log.parent, self.log)
        self.assertEqual(str(caught.exception), scummvm_build.BUILD_FAILED.format(log=self.log))
        self.assertIn('raw output', self.log.read_text(encoding='utf-8'))

    def test_a_missing_program_is_a_missing_tool_not_a_crash(self):
        with self.assertRaises(scummvm_build.ScummvmToolsMissing) as caught:
            scummvm_build._run(['no-such-program-of-retro-recomp'], self.log.parent, self.log)
        self.assertIn('no-such-program-of-retro-recomp is missing', str(caught.exception))

    def test_a_clone_that_fails_says_to_check_the_connection(self):
        from unittest import mock
        place = self.log.parent / 'scummvm'
        with mock.patch.object(scummvm_build, '_run', side_effect=scummvm_build.ScummvmBuildError('git')):
            with self.assertRaises(scummvm_build.ScummvmDownloadFailed) as caught:
                scummvm_build._checkout(place, 'url', 'tag', 'wanted', self.log, lambda text: None)
        self.assertEqual(str(caught.exception), scummvm_build.DOWNLOAD_FAILED.format(log=self.log))
        self.assertEqual(caught.exception.key, 'scummvm_detect_offline')
        self.assertFalse(place.exists())

    def sdl(self, follow=None, build=None):
        from unittest import mock
        from retrorecomp import core
        with mock.patch.object(core, 'toolchain', return_value=('cmake', 'Ninja')), \
                mock.patch.object(core, 'follow_pin', side_effect=follow), mock.patch.object(core, 'ensure_sdl', side_effect=build), \
                mock.patch('retrorecomp.platforms.sdl_install', return_value=self.log.parent):
            scummvm_build._ensure_sdl(self.log, lambda text: None)

    def test_the_sdl_of_a_first_use_says_the_same(self):
        from retrorecomp.core import ConversionError, StopRequested
        for text in ('Commande interrompue (128).\nfatal: unable to access', 'Impossible de récupérer la version épinglée de SDL'):
            with self.assertRaises(scummvm_build.ScummvmDownloadFailed):
                self.sdl(follow=ConversionError(text))
        with self.assertRaises(scummvm_build.ScummvmBuildError) as caught:
            self.sdl(build=ConversionError('Commande interrompue (1).\nCMake Error'))
        self.assertEqual(str(caught.exception), scummvm_build.BUILD_FAILED.format(log=self.log))
        with self.assertRaises(StopRequested):       # Stop stays Stop
            self.sdl(build=StopRequested('stop'))

    def test_a_folder_it_refuses_to_touch_keeps_its_own_sentence(self):
        from retrorecomp.core import ConversionError
        text = 'Le dossier SDL contient des modifications locales : il n’est ni utilisé ni remplacé.'
        with self.assertRaises(scummvm_build.ScummvmBuildError) as caught:
            self.sdl(follow=ConversionError(text))
        self.assertEqual(str(caught.exception), text)
        self.assertNotIsInstance(caught.exception, scummvm_build.ScummvmDownloadFailed)

    def test_the_window_shows_them_in_each_language_after_the_title(self):
        from retrorecomp.i18n import LANGUAGES, STRINGS, log_text, tr
        self.assertEqual(scummvm_build.DOWNLOAD_FAILED, STRINGS['scummvm_download_failed'][0])
        self.assertEqual(scummvm_build.BUILD_FAILED, STRINGS['scummvm_build_failed'][0])
        for sentence, key in ((scummvm_build.DOWNLOAD_FAILED, 'scummvm_download_failed'),
                              (scummvm_build.BUILD_FAILED, 'scummvm_build_failed')):
            for code in LANGUAGES:
                self.assertEqual(log_text('Sam : ' + sentence.format(log=r'C:\d\f.log'), code),
                                 'Sam : ' + tr(key, code, log=r'C:\d\f.log'), code)

    def test_a_scan_stopped_by_the_network_says_so(self):
        from unittest import mock
        from retrorecomp.i18n import LANGUAGES, catalog, tr
        from retrorecomp.systems.scummvm import SCUMMVM
        from retrorecomp.systems.registry import FolderDiscoveryUnavailable
        for code in LANGUAGES[:2]:
            self.assertNotEqual(tr('scummvm_detect_offline', code), 'scummvm_detect_offline')
        self.assertTrue(all(catalog(code)['ui'].get('scummvm_detect_offline') for code in LANGUAGES[2:]))
        with mock.patch.object(sx, 'find_game_folders', side_effect=scummvm_build.ScummvmDownloadFailed('no network')):
            with self.assertRaises(FolderDiscoveryUnavailable) as caught:
                SCUMMVM.find_folders(self.log.parent)
        self.assertEqual(caught.exception.key, 'scummvm_detect_offline')

    def test_a_conversion_that_builds_the_detection_says_so_in_its_log(self):
        from unittest import mock
        sx._DETECTED.clear()
        self.addCleanup(sx._DETECTED.clear)
        said = []

        def build(family, emit, started=None):
            emit('Compilation de ScummVM (detect)…')
            return Path('fake-runtime')

        with mock.patch.object(scummvm_build, 'build_runtime', side_effect=build), mock.patch.object(sx, 'detect', return_value=[]):
            sx.candidates_of(self.log.parent, emit=said.append)
        self.assertEqual(said, ['Compilation de ScummVM (detect)…'])

    @unittest.skipUnless(os.name == 'nt', 'the portable tools are the Windows route')
    def test_without_git_nothing_starts(self):
        from unittest import mock
        from retrorecomp import toolchain
        with mock.patch.object(toolchain, 'select', return_value=mock.Mock(kind=toolchain.LLVM)), \
                mock.patch.object(toolchain, 'portable_installed', return_value=True), \
                mock.patch.object(scummvm_build.shutil, 'which', return_value=None):
            with self.assertRaises(scummvm_build.ScummvmToolsMissing):
                scummvm_build._require_portable_tools()


class Pack(unittest.TestCase):
    def test_a_pack_already_there_builds_nothing(self):
        from unittest import mock
        with mock.patch.object(scummvm_build, 'runtime_current', return_value=True), \
                mock.patch.object(scummvm_build, 'build_runtime') as build:
            self.assertFalse(scummvm_build.prepare_pack(lambda text: None))
        build.assert_not_called()

    def test_a_pack_absent_is_the_detection_runtime_built(self):
        from unittest import mock
        emit = lambda text: None
        with mock.patch.object(scummvm_build, 'runtime_current', return_value=False), \
                mock.patch.object(scummvm_build, 'build_runtime') as build:
            self.assertTrue(scummvm_build.prepare_pack(emit))
        build.assert_called_once_with(scummvm_build.DETECT_FAMILY, emit)

    def test_its_steps_and_results_are_interface_strings(self):
        from unittest import mock
        from retrorecomp.i18n import STRINGS
        from retrorecomp.systems.scummvm import SCUMMVM
        steps = []

        def prepare(emit):
            for text in ('Téléchargement de scummvm v2026.4.0…', 'Téléchargement de SDL…', 'Application du correctif Retro-Recomp à ScummVM…',
                         'Compilation de FreeType…', 'Mise à jour de SDL vers la version épinglée…',
                         'Compilation de SDL2 statique (première utilisation)…', 'Préparation de ScummVM (detect)…'):
                emit(text)
            return True

        with mock.patch.object(scummvm_build, 'prepare_pack', side_effect=prepare):
            result = SCUMMVM.run_option_action('scummvm_pack', lambda key, **values: steps.append((key, values)))
        self.assertEqual(result, 'scummvm_pack_done')
        self.assertEqual(steps, [('tools_step_download', {'name': 'scummvm'}), ('tools_step_download', {'name': 'SDL'}),
                                 ('scummvm_pack_compile', {}), ('scummvm_pack_compile', {}), ('deps_step_sdl_update', {}),
                                 ('deps_step_sdl', {}), ('scummvm_pack_compile', {})])
        for key, _values in steps:
            self.assertIn(key, STRINGS)
        with mock.patch.object(scummvm_build, 'prepare_pack', return_value=False):
            self.assertEqual(SCUMMVM.run_option_action('scummvm_pack', lambda key, **values: None), 'scummvm_pack_ready')

    def test_the_shared_pieces_with_no_network_are_a_sentence(self):
        from retrorecomp.gui_updates import shared_pieces_unreachable
        from retrorecomp.i18n import LANGUAGES, catalog
        self.assertTrue(shared_pieces_unreachable("Commande interrompue (128).\nfatal: unable to access 'https://...'"))
        self.assertTrue(shared_pieces_unreachable('Impossible de récupérer la version épinglée de SDL'))
        self.assertFalse(shared_pieces_unreachable('Commande interrompue (1).\nCMake Error'))
        self.assertFalse(shared_pieces_unreachable('Git: download failed (timed out).'))
        self.assertTrue(all(catalog(code)['ui'].get('deps_download_failed') for code in LANGUAGES[2:]))

    def test_the_strings_of_the_button_exist_in_every_language(self):
        from retrorecomp.i18n import LANGUAGES, catalog
        names = ('scummvm_pack', 'scummvm_pack_note', 'scummvm_pack_button', 'scummvm_pack_working', 'scummvm_pack_compile',
                 'scummvm_pack_done', 'scummvm_pack_ready', 'tip_scummvm_pack', 'scummvm_download_failed', 'scummvm_build_failed')
        for code in LANGUAGES[2:]:
            for name in names:
                self.assertTrue(catalog(code)['ui'].get(name), (code, name))


@unittest.skipUnless(os.name == 'nt', 'a real window, as in test_dropfiles')
class PackButton(unittest.TestCase):
    """The button in a real window: Options, Consoles, Adventure (ScummVM). Nothing runs but its worker."""

    def setUp(self):
        import tkinter as tk
        from unittest import mock
        from retrorecomp.gui import Application
        from tools.gui_patching import patch_gui
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name).resolve()
        self.root = tk.Tk()
        self.root.withdraw()
        with patch_gui('load_preferences', return_value={}), patch_gui('preferred_games_root', return_value=(folder / 'exports', False)):
            self.app = Application(self.root)
        self.addCleanup(self.close_window)
        self.app.save_preferences = mock.Mock()
        self.app.ensure_build_tools = mock.Mock(return_value=True)
        self.app.show_options()
        ids = [system for system, _, _ in self.app.options_console_pages]
        self.app.show_console_page(ids.index('scummvm'))
        self.root.update()
        self.button, self.bar, self.status = self.app.option_action_rows['scummvm_pack']

    def close_window(self):
        def widgets(parent):
            yield parent
            for child in parent.winfo_children():
                yield from widgets(child)
        owners = {name: widget for widget in widgets(self.root) for name in (widget._tclCommands or [])}
        for job in self.root.tk.call('after', 'info'):
            owners.get(self.root.tk.call('after', 'info', job)[0], self.root).after_cancel(job)
        self.root.destroy()

    def pump(self, until, seconds=20):
        import time
        deadline = time.monotonic() + seconds
        while not until() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        self.assertTrue(until(), self.status.get())

    def phase(self):
        return self.app.option_actions.get('scummvm_pack', {}).get('phase')

    def log(self):
        self.app.drain()
        return self.app.log.get('1.0', 'end')

    def test_the_page_offers_the_button_and_says_nothing_before_it_is_used(self):
        self.assertEqual(self.button.cget('text'), self.app.tr('scummvm_pack_button'))
        self.assertEqual(self.status.get(), '')
        self.assertFalse(self.bar.winfo_ismapped())

    def test_it_runs_off_the_window_and_shows_each_step_then_the_result(self):
        import threading
        from unittest import mock
        release = threading.Event()
        self.addCleanup(release.set)

        def prepare(emit):
            emit('Téléchargement de scummvm v2026.4.0…')
            release.wait(20)
            return True

        with mock.patch.object(scummvm_build, 'prepare_pack', side_effect=prepare):
            self.button.invoke()
            downloading = self.app.tr('tools_step_download', name='scummvm')
            self.pump(lambda: self.status.get() == downloading)     # the window is being pumped while the worker waits
            self.assertEqual(str(self.button.cget('state')), 'disabled')
            self.assertEqual(self.phase(), 'working')
            self.button.invoke()                                    # a second click starts nothing
            self.app.set_controls(True)                             # nor does the end of something else enable the button
            self.assertEqual(str(self.button.cget('state')), 'disabled')
            self.assertIn(downloading, self.log())
            release.set()
            self.pump(lambda: self.phase() == 'done')
            self.pump(lambda: self.status.get() == self.app.tr('scummvm_pack_done'))
        self.assertEqual(str(self.button.cget('state')), 'normal')
        self.assertFalse(self.bar.winfo_ismapped())
        self.assertIn(self.app.tr('scummvm_pack_done'), self.log())

    def test_it_says_when_the_pack_is_already_there(self):
        from unittest import mock
        with mock.patch.object(scummvm_build, 'prepare_pack', return_value=False):
            self.button.invoke()
            self.pump(lambda: self.status.get() == self.app.tr('scummvm_pack_ready'))
        self.assertEqual(str(self.button.cget('state')), 'normal')

    def test_with_no_network_it_says_what_to_do_and_can_be_used_again(self):
        from unittest import mock
        failure = scummvm_build.ScummvmDownloadFailed(scummvm_build.DOWNLOAD_FAILED.format(log='family.log'))
        with mock.patch.object(scummvm_build, 'prepare_pack', side_effect=failure):
            self.button.invoke()
            self.pump(lambda: self.status.get() == self.app.tr('scummvm_download_failed', log='family.log'))
        self.assertEqual(str(self.button.cget('state')), 'normal')
        self.assertIn(self.app.tr('scummvm_download_failed', log='family.log'), self.log())
        with mock.patch.object(scummvm_build, 'prepare_pack', return_value=False):
            self.button.invoke()
            self.pump(lambda: self.status.get() == self.app.tr('scummvm_pack_ready'))

    def test_the_build_tools_come_first(self):
        from unittest import mock
        self.app.ensure_build_tools.return_value = False
        with mock.patch.object(scummvm_build, 'prepare_pack', return_value=False) as prepare:
            self.button.invoke()
            self.root.update()
            prepare.assert_not_called()
            self.assertIsNone(self.phase())
            retry = self.app.ensure_build_tools.call_args.args[0]    # the tools are installed: the window calls it again
            self.app.ensure_build_tools.return_value = True
            retry()
            self.pump(lambda: self.phase() == 'done')
        prepare.assert_called_once()

    def test_it_follows_the_language_and_a_reopened_page(self):
        from unittest import mock
        with mock.patch.object(scummvm_build, 'prepare_pack', return_value=False):
            self.button.invoke()
            self.pump(lambda: self.phase() == 'done')
        self.app.language = 'fr'
        self.app.render_option_actions()
        self.assertEqual(self.status.get(), self.app.tr('scummvm_pack_ready'))
        self.app.close_options()
        self.app.show_options()
        self.root.update()
        status = self.app.option_action_rows['scummvm_pack'][2]
        self.assertEqual(status.get(), self.app.tr('scummvm_pack_ready'))


class Theme(unittest.TestCase):
    """Patch 0003: every ScummVM menu in Retro-Recomp's colours, from the zip of the default theme made again at build time."""

    def setUp(self):
        self.patch = (scummvm_build.PATCH_DIRECTORY / '0003-retrorecomp-theme-colours.patch').read_text(encoding='utf-8')

    def test_only_colours_change_and_no_file_is_added(self):
        files = [line.split(' b/')[-1] for line in self.patch.splitlines() if line.startswith('diff --git')]
        self.assertEqual(files, [f'gui/themes/scummremastered/{name}' for name in
                                 ('checkbox.svg', 'checkbox_empty.svg', 'radiobutton.svg', 'radiobutton_empty.svg', 'remastered_gfx.stx')])
        self.assertNotIn('new file', self.patch)
        self.assertNotIn('.ttf', self.patch)
        for line in self.patch.splitlines():
            if line.startswith('+') and not line.startswith('+++') and not line.lstrip('+').startswith('<svg'):
                self.assertRegex(line, r"(rgb|color|fg_color|bg_color|gradient_start|gradient_end) = '")

    def test_the_colours_are_those_of_the_interface(self):
        from retrorecomp.branding import COLORS
        for name in ('background', 'header', 'button', 'gold', 'text'):
            value = COLORS[name].lstrip('#')
            rgb = ', '.join(str(int(value[at:at + 2], 16)) for at in (0, 2, 4))
            self.assertIn(rgb, self.patch, name)

    def test_the_zip_is_made_from_the_folder_and_those_it_names(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp).resolve()
            themes = tree / 'gui' / 'themes'
            folder, common = themes / scummvm_build.THEME, themes / 'common'
            folder.mkdir(parents=True)
            common.mkdir()
            (folder / 'THEMERC').write_text('[SCUMMVM_STX0.9.24:Name:Author]\n%using ../common\n', encoding='utf-8')
            (folder / 'colours.stx').write_text('recoloured', encoding='utf-8')
            (folder / '.hidden.stx').write_text('x', encoding='utf-8')
            (folder / 'notes.txt').write_text('x', encoding='utf-8')
            (common / 'layout.stx').write_text('layout', encoding='utf-8')
            (common / 'colours.stx').write_text('the theme\'s own wins', encoding='utf-8')
            scummvm_build._pack_theme(tree)
            first = folder.with_suffix('.zip').read_bytes()
            with zipfile.ZipFile(folder.with_suffix('.zip')) as package:
                self.assertEqual(package.namelist(), ['THEMERC', 'colours.stx', 'layout.stx'])
                self.assertEqual(package.read('colours.stx'), b'recoloured')
            scummvm_build._pack_theme(tree)
            self.assertEqual(folder.with_suffix('.zip').read_bytes(), first)


class OptionsPage(unittest.TestCase):
    """Patch 0002: the Retro-Recomp page of the in-game options and the settings shared through datas/Retro-Recomp.ini
    (checked headless with the real runtime: .build/scummvm-step2/ui_cases.py; here, the text of the patch)."""

    def setUp(self):
        self.patch = (scummvm_build.PATCH_DIRECTORY / '0002-retrorecomp-options-page.patch').read_text(encoding='utf-8')

    def test_the_series_has_both_patches_in_order(self):
        names = sorted(path.name for path in scummvm_build.PATCH_DIRECTORY.glob('*.patch'))
        self.assertEqual(names, ['0001-retrorecomp-pack-launch-nodialog.patch', '0002-retrorecomp-options-page.patch',
                                 '0003-retrorecomp-theme-colours.patch'])

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
        # shown for three seconds, once, from the first poll of the engine (an OSD message lasts about two seconds)
        self.assertIn('g_hintBurst = 3;', self.patch)
        self.assertNotIn('g_hintMouse', self.patch)

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
                         [('normal', 'Sharp pixels'), ('hq', 'HQ2x'), ('advmame', 'Scale2x'), ('normal', 'Scanlines')])
        self.assertNotIn('xBR"', self.patch)      # no mention of xBR in what the player sees
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
