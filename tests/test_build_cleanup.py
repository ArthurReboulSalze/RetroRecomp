"""Per-game build projects are removed after publication, and only those."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retrorecomp import __version__
from retrorecomp import build_cleanup
from retrorecomp.build_cleanup import (RECENT_SECONDS, REMOVING, classify, game_projects, leftover_projects,
                                       release_build, remove_projects, report_project)
from retrorecomp.batch import identify, convert_batch
from retrorecomp.core import ConversionError, slug
from retrorecomp.library import entry_lock

SHA = hashlib.sha256(b'this cartridge').hexdigest()
OTHER = hashlib.sha256(b'another cartridge').hexdigest()
EXE = ('build/Release/game.exe', 'build/game.exe')     # Visual Studio, Ninja/Linux


def files(path: Path, *names, size=1000):
    for name in names or ('generated/game.c', 'build/Release/game.exe'):
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_bytes(b'x' * size)
    return path


def age(path: Path, seconds=2 * RECENT_SECONDS):
    moment = time.time() - seconds
    for directory, folders, names in os.walk(path):
        for name in folders + names:
            os.utime(os.path.join(directory, name), (moment, moment))
    os.utime(path, (moment, moment))
    return path


def link(source: Path, target: Path):
    """Make ``source`` a directory link to ``target``: a symbolic link, else a
    Windows junction (no privilege needed)."""
    try:
        os.symlink(target, source, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    if os.name == 'nt':
        import _winapi
        _winapi.CreateJunction(str(target), str(source))
        return
    raise unittest.SkipTest('No directory links on this system.')


def catalogue(module):
    return next((sha, profile['id']) for sha, profile in module.PROFILES.items())


class IdentificationTests(unittest.TestCase):
    def test_each_console_project_shape_is_recognized(self):
        from retrorecomp import megadrive, supernintendo
        md_sha, md_id = catalogue(megadrive)
        snes_sha, snes_id = catalogue(supernintendo)
        shapes = {
            ('sms_Ace_of_Aces_887D9F6B_c66ac645f7d1_banked',): ('sms', 'c66ac645f7d1'),
            ('sms_CPU_Test_00000001_c66ac645f7d1',): ('sms', 'c66ac645f7d1'),
            ('gg_Sonic_Chaos_12AB34CD_0123456789ab_banked',): ('gg', '0123456789ab'),
            ('gb_Kirby_s_Dream_Land_0f6dba94fae2_9150f87d',): ('gb', '0f6dba94fae2'),
            ('nes_Mega_Man_2_49136b412ff6_1b0c621a_ntsc',): ('nes', '49136b412ff6'),
            ('nes_Mega_Man_58fb9ef0c14c_1b0c621a',): ('nes', '58fb9ef0c14c'),     # before video standards
            ('md-rom-' + SHA,): ('md', SHA),
            ('md-' + md_id,): ('md', md_sha),
            ('snes-rom-' + SHA[:16],): ('snes', SHA[:16]),
            ('snes-rom-' + SHA,): ('snes', SHA),
            ('snes-' + snes_id,): ('snes', snes_sha),
            ('ng-289e4a4de23c0ff534ea-native',): ('ng', '289e4a4de23c0ff534ea'),
            ('ng-289e4a4de23c0ff534ea',): ('ng', '289e4a4de23c0ff534ea'),
            ('ng-4354046cd98c5c7985e2-fe62d3e8',): ('ng', '4354046cd98c5c7985e2'),
            ('cps1', 'ffight-22897b4338a7'): ('cps1', '22897b4338a7'),
            ('x68', 'win', '013098655eb5', '609d891fcc979af8'): ('x68', '609d891fcc979af8'),
            ('x68', 'win-llvm', '013098655eb5', '609d891fcc979af8'): ('x68', '609d891fcc979af8'),
            ('x68', 'linux', '013098655eb5', '609d891fcc979af8'): ('x68', '609d891fcc979af8'),
            (REMOVING + '0123456789abcdef',): ('removing', ''),
        }
        for parts, expected in shapes.items():
            self.assertEqual(classify(parts), expected, parts)

    def test_shared_caches_research_and_test_folders_are_never_projects(self):
        for parts in [('native-source',), ('nes-compiler',), ('nes-compiler', '1b0c621a-0123456789ab'),
                      ('megadrive-compiler',), ('megadrive-step-decoder',), ('neogeo-step-decoder',),
                      ('neogeo-preparation',), ('cps1-reference',), ('cps1-native', 'ffight'),
                      ('cps1-native',), ('cps1',), ('cps1-batch',), ('x68',), ('x68', 'win'),
                      ('x68', 'win', '013098655eb5'), ('x68', 'win', '013098655eb5', 'discovery'),
                      ('x68', 'win', '013098655eb5', 'machine-74ddbb3'), ('x68', 'win', '013098655eb5', 'discovery-lock'),
                      ('x68', 'mac', '013098655eb5', '609d891fcc979af8'), ('release-1.5.1',),
                      ('md-perf',), ('md-campaign-20261024',), ('snes-pal',), ('snes-native-selftest',),
                      ('sms-sprite-selftest',), ('video-selftest',), ('neogeo-thirty-20261020',),
                      ('ng-host-pages',), ('gb_Tetris',), ('sms_Game_887D9F6B_C66AC645F7D1',),
                      ('nes_Game_58fb9ef0c14c_1b0c621a_dendy',), ('cleanup-check',), ('.deps',),
                      ('sms_Ace_887D9F6B_c66ac645f7d1_banked', 'build-native')]:
            self.assertIsNone(classify(parts), parts)

    def test_removing_build_folders_never_changes_a_game_stamp(self):
        # Like the interface, the cleanup is not a compiler input: changing it
        # must not make every export look stale.
        from retrorecomp.compilation_inputs import INTERFACE_MODULES
        self.assertIn('build_cleanup', INTERFACE_MODULES)

    def test_report_paths_map_to_the_project_at_every_build_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            build = root / '.build'
            cases = [('sms', 'sms_Ace_of_Aces_887D9F6B_' + SHA[:12] + '_banked', 'build-native/Release/Ace_of_Aces.exe'),
                     ('gg', 'gg_Sonic_12AB34CD_' + SHA[:12], 'build-native/Sonic.exe'),
                     ('gb', 'gb_Tetris_' + SHA[:12] + '_9150f87d', EXE[0]),
                     ('gb', 'gb_Tetris_' + SHA[:12] + '_9150f87d', EXE[1]),
                     ('nes', 'nes_Mega_Man_' + SHA[:12] + '_1b0c621a_pal', EXE[1]),
                     ('md', 'md-rom-' + SHA, EXE[0]), ('snes', 'snes-rom-' + SHA[:16], 'build/game'),
                     ('ng', 'ng-289e4a4de23c0ff534ea-native', EXE[0]),
                     ('cps1', 'cps1/ffight-' + SHA[:12], 'native/build/Release/game.exe'),
                     ('x68', 'x68/win/013098655eb5/' + SHA[:16], 'native/build/reference/Release/RetroRecomp-X68000-Native.exe'),
                     ('x68', 'x68/linux/013098655eb5/' + SHA[:16], 'native/build/reference/RetroRecomp-X68000-Native')]
            for system, name, executable in cases:
                project = build / name
                for report in ({'build_executable': str(project / executable)},
                               {'build_executable': (project / executable).as_posix(),
                                'build_directory': str(project / ('native' if system == 'cps1' else ''))}):
                    self.assertEqual(report_project(system, report, root), project, (system, report))
                # Another console's report never names this folder.
                self.assertIsNone(report_project('gb' if system != 'gb' else 'nes',
                                                 {'build_executable': str(project / executable)}, root))
            self.assertIsNone(report_project('sms', {'build_executable': str(build / 'native-source/x.exe')}, root))
            self.assertIsNone(report_project('sms', {}, root))


class RemovalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.build = self.root / '.build'
        self.build.mkdir()
        self.log = []
        # Shared caches and research folders that nothing here may touch.
        self.shared = [files(self.root / '.deps/SDL'), files(self.build / 'native-source'),
                       files(self.build / 'nes-compiler/1b0c621a-0123456789ab'),
                       files(self.build / 'megadrive-compiler'), files(self.build / 'cps1-reference'),
                       files(self.build / 'cps1-native/ffight'), files(self.build / 'x68/win/013098655eb5/discovery'),
                       files(self.build / 'x68/win/013098655eb5/machine-74ddbb3'), files(self.build / 'md-perf'),
                       files(self.build / 'release-1.5.1')]
        for path in self.shared:
            age(path)

    def item(self, system='gb', sha=SHA, title='Tetris'):
        return SimpleNamespace(system=system, sha256=sha, title=title)

    def assertShared(self):
        for path in self.shared:
            self.assertTrue((path / 'generated/game.c').is_file(), path)

    def test_publication_removes_the_project_and_older_ones_of_the_same_cartridge_only(self):
        current = files(self.build / f'gb_Tetris_{SHA[:12]}_9150f87d')        # just used: still removed
        older = age(files(self.build / f'gb_Tetris_{SHA[:12]}_00c0ffee'))      # older engine revision
        renamed = files(self.build / f'gb_Tetris_DX_{SHA[:12]}_9150f87d')      # touched within the hour
        other = age(files(self.build / f'gb_Tetris_{OTHER[:12]}_9150f87d'))
        sega = age(files(self.build / f'sms_Tetris_887D9F6B_{SHA[:12]}_banked'))  # another console
        report = {'build_executable': str(current / EXE[0]), 'build_directory': str(current)}
        found = game_projects('gb', SHA, report, self.root)
        self.assertEqual((found[0], set(found)), (current, {current, older, renamed}))
        freed = release_build(self.item(), report, self.log.append, root=self.root)
        self.assertEqual(freed, 4000)
        self.assertFalse(current.exists() or older.exists())
        self.assertTrue(renamed.exists() and other.exists() and sega.exists())
        self.assertIn('in use', self.log[-1])
        self.assertEqual([p.name for p in self.build.iterdir() if p.name.startswith(REMOVING)], [])
        self.assertShared()

    def test_each_console_matches_its_own_cartridge_identity(self):
        from retrorecomp import megadrive
        md_sha, md_id = catalogue(megadrive)
        neo = files(self.build / 'ng-289e4a4de23c0ff534ea-native')
        (neo / 'input.json').write_text(json.dumps({'source': {'sha256': SHA}}))
        older_neo = age(files(self.build / 'ng-0000000000c0ffee0000'))
        (older_neo / 'input.json').write_text(json.dumps({'source': {'sha256': SHA}}))
        other_neo = age(files(self.build / 'ng-1111111111c0ffee1111-native'))
        (other_neo / 'input.json').write_text(json.dumps({'source': {'sha256': OTHER}}))
        self.assertEqual(game_projects('ng', SHA, {'build_directory': str(neo)}, self.root), [neo, older_neo])
        # The report names its project even before the project records its source.
        (neo / 'input.json').unlink()
        self.assertEqual(game_projects('ng', SHA, {'build_directory': str(neo)}, self.root), [neo, older_neo])
        catalogue_folder = files(self.build / ('md-' + md_id))
        generic = age(files(self.build / ('md-rom-' + md_sha)))
        self.assertEqual(game_projects('md', md_sha, {'build_executable': str(catalogue_folder / EXE[0])}, self.root),
                         [catalogue_folder, generic])
        snes = files(self.build / ('snes-rom-' + SHA[:16]))
        (snes / 'generation-identity.json').write_text(json.dumps({'rom': SHA}))
        clash = age(files(self.build / ('snes-rom-' + SHA[:32])))
        (clash / 'generation-identity.json').write_text(json.dumps({'rom': SHA[:32] + OTHER[32:]}))
        self.assertEqual(game_projects('snes', SHA, {'build_directory': str(snes)}, self.root), [snes])
        # X68000 folders carry the machine identity (disks + firmware) of the report.
        machine = OTHER
        x68 = files(self.build / 'x68/win/013098655eb5' / machine[:16])
        old_sdk = age(files(self.build / 'x68/win/0123456789ab' / machine[:16]))
        game = files(self.build / 'x68/win/013098655eb5' / SHA[:16])
        report = {'build_executable': str(x68 / 'native/build/reference/Release/RetroRecomp-X68000-Native.exe'),
                  'source_identity': machine}
        self.assertEqual(game_projects('x68', SHA, report, self.root), [x68, old_sdk])
        self.assertEqual(game_projects('x68', SHA, {**report, 'source_identity': None}, self.root), [])
        self.assertTrue(game.exists())
        cps1 = files(self.build / 'cps1' / ('ffight-' + SHA[:12]))
        self.assertEqual(game_projects('cps1', SHA, {'build_directory': str(cps1 / 'native')}, self.root), [cps1])
        # A report whose project carries another cartridge's identity removes nothing.
        stray = files(self.build / f'gb_Tetris_{OTHER[:12]}_9150f87d')
        self.assertEqual(game_projects('gb', SHA, {'build_directory': str(stray)}, self.root), [])

    def test_paths_outside_the_build_folder_and_shared_caches_are_refused(self):
        outside = files(self.root / 'elsewhere' / f'gb_Tetris_{SHA[:12]}_9150f87d')
        for report in ({'build_directory': str(outside)},
                       {'build_directory': str(self.build / '..' / 'elsewhere' / outside.name)},
                       {'build_executable': str(self.build / 'native-source/game.exe')},
                       {'build_directory': str(self.build / 'nes-compiler')}):
            self.assertEqual(release_build(self.item(), report, self.log.append, root=self.root), 0)
        self.assertTrue((outside / 'generated/game.c').is_file())
        for path in (outside, self.build / 'native-source', self.build / 'x68/win/013098655eb5',
                     self.build, self.root):
            with self.assertRaises(ValueError):
                build_cleanup._remove(path, self.build, keep_recent=False)
        self.assertShared()

    def test_links_and_junctions_are_never_followed(self):
        outside = files(self.root / 'precious')
        project = files(self.build / f'gb_Tetris_{SHA[:12]}_9150f87d')
        link(project / 'engine', outside)
        release_build(self.item(), {'build_directory': str(project)}, self.log.append, root=self.root)
        self.assertFalse(project.exists())
        self.assertTrue((outside / 'generated/game.c').is_file())
        # A project that is itself a link, or reached through one, is refused.
        target = files(self.root / 'linked-project')
        linked = self.build / f'gb_Tetris_{OTHER[:12]}_9150f87d'
        link(linked, target)
        cps1_target = files(self.root / 'cps1-elsewhere' / ('ffight-' + SHA[:12]))
        link(self.build / 'cps1', cps1_target.parent)
        release_build(self.item(sha=OTHER), {'build_directory': str(linked)}, self.log.append, root=self.root)
        release_build(self.item('cps1'), {'build_directory': str(self.build / 'cps1' / cps1_target.name)},
                      self.log.append, root=self.root)
        self.assertTrue((target / 'generated/game.c').is_file() and (cps1_target / 'generated/game.c').is_file())
        listed = {project.path for project in leftover_projects(self.root)}
        self.assertNotIn(linked, listed)
        self.assertNotIn(self.build / 'cps1' / cps1_target.name, listed)
        remove_projects([build_cleanup.Project(linked, 'gb', 0)], self.root)
        self.assertTrue((target / 'generated/game.c').is_file())

    def test_keep_variable_keeps_the_project(self):
        project = files(self.build / f'gb_Tetris_{SHA[:12]}_9150f87d')
        with patch.dict(os.environ, {build_cleanup.KEEP_VARIABLE: '1'}):
            self.assertEqual(release_build(self.item(), {'build_directory': str(project)}, self.log.append,
                                           root=self.root), 0)
        self.assertTrue(project.exists())
        self.assertIn(build_cleanup.KEEP_VARIABLE, self.log[-1])

    def test_free_space_lists_and_removes_leftovers_but_keeps_recent_and_locked_ones(self):
        old = age(files(self.build / f'sms_Alex_Kidd_887D9F6B_{SHA[:12]}_banked'))
        fresh = files(self.build / f'nes_Zelda_{OTHER[:12]}_1b0c621a_ntsc')
        locked = age(files(self.build / 'cps1' / ('ffight-' + SHA[:12])))
        x68 = age(files(self.build / 'x68/win/013098655eb5' / SHA[:16]))
        interrupted = age(files(self.build / (REMOVING + '0123456789abcdef')))
        with entry_lock(locked, timeout=1):
            age(locked)     # held, not recent: the lock alone keeps it
            found = {project.path: project for project in leftover_projects(self.root)}
            self.assertEqual(set(found), {old, fresh, locked, x68, interrupted})
            self.assertEqual({path for path, project in found.items() if project.in_use}, {fresh, locked})
            self.assertEqual(found[old].size, 2000)
            self.assertEqual(found[x68].system, 'x68')
            outcome = remove_projects(found.values(), self.root, emit=self.log.append)
        self.assertEqual((outcome['removed'], outcome['freed'], outcome['kept'], outcome['errors']),
                         (3, 6000, 2, []))
        self.assertTrue(fresh.exists() and locked.exists())
        self.assertFalse(old.exists() or x68.exists() or interrupted.exists())
        self.assertTrue((self.build / 'x68/win/013098655eb5/discovery').is_dir())
        self.assertShared()
        # An interrupted removal is finished by the next one.
        age(fresh)
        with patch('retrorecomp.build_cleanup._delete_tree', side_effect=OSError('locked file')):
            outcome = remove_projects([build_cleanup.Project(fresh, 'nes', 0)], self.root)
        self.assertEqual(outcome['removed'], 0)
        self.assertEqual(len(outcome['errors']), 1)
        self.assertFalse(fresh.exists())
        trash = [p for p in leftover_projects(self.root) if p.system == 'removing']
        self.assertEqual(len(trash), 1)
        self.assertTrue(trash[0].path.name.startswith(REMOVING))
        age(trash[0].path)
        self.assertEqual(remove_projects(trash, self.root)['removed'], 1)
        self.assertEqual([p for p in self.build.iterdir() if p.name.startswith(REMOVING)], [])

    def test_nothing_to_list_without_a_build_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(leftover_projects(Path(folder)), [])


class BatchCleanupTests(unittest.TestCase):
    """The batch removes a project only after its game is published."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root / 'Games'
        for name, value in [('retrorecomp.publishing.compact_executable', None),
                            ('retrorecomp.paths.load_preferences', {}),
                            ('retrorecomp.cover_settings.load_settings', {}),
                            ('retrorecomp.library.library_root', self.root / 'bank')]:
            mocked = patch(name, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)
        mocked = patch('retrorecomp.build_cleanup.ROOT', self.root)
        mocked.start()
        self.addCleanup(mocked.stop)
        mocked = patch('retrorecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.compiler)
        self.compiler_mock = mocked.start()
        self.addCleanup(mocked.stop)
        self.projects = {}
        self.failures = set()
        self.hold = {}

    def rom(self, name, value):
        path = self.root / name
        path.write_bytes(bytes([value]) * 8192)
        return identify(path)

    def project(self, item):
        from retrorecomp.systems import get_profile
        rom = get_profile('sms').read_rom(item.path)
        return self.root / '.build' / f'sms_{slug(item.title)}_{rom.crc32:08X}_{rom.sha256[:12]}_banked'

    def compiler(self, path, *, output, title, **options):
        item = identify(path)
        item.title = title
        project = self.project(item)
        executable = files(project, 'generated/game_banked_index.c', 'build-native/Release/game.exe') / \
            'build-native/Release/game.exe'
        executable.write_bytes(b'MZ authored game')
        self.projects[title] = project
        if title in self.hold:
            self.hold[title]()
        if title in self.failures:
            self.failures.discard(title)
            raise ConversionError('validation diverged')
        output.mkdir(parents=True, exist_ok=True)
        report = {'version': __version__, 'rom': {'name': path.name}, 'executable': executable.name,
                  'build_executable': str(executable), 'build_directory': str(project),
                  'final_checks': [{'interpreter_percent': 0}]}
        (output / 'conversion-report.json').write_text(json.dumps(report))
        return executable

    def run_batch(self, items, **options):
        options.setdefault('emit', lambda _: None)
        return convert_batch(items, self.output, **options)['games']

    def test_published_game_leaves_no_build_project(self):
        item = self.rom('Authored.sms', 1)
        log, seen = [], []
        with patch('retrorecomp.linux_desktop.publish_launcher',
                   side_effect=lambda *_: seen.append(self.projects['Authored'].is_dir())):
            result, = self.run_batch([item], emit=log.append)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(Path(result['executable']).read_bytes(), b'MZ authored game')
        # The Linux launcher still found the project's icon before removal.
        self.assertEqual(seen, [True])
        self.assertFalse(self.projects['Authored'].exists())
        self.assertTrue(any('build files removed after publication' in line for line in log), log)
        report = json.loads(Path(result['report']).read_text())
        self.assertEqual(report['build_directory'], str(self.projects['Authored']))   # text only

    def test_failed_conversion_or_publication_keeps_the_project(self):
        item = self.rom('Authored.sms', 1)
        self.failures.add('Authored')
        result, = self.run_batch([item])
        self.assertEqual(result['status'], 'error')
        self.assertTrue(self.projects['Authored'].is_dir())
        with patch('retrorecomp.batch.publish_executable', side_effect=OSError('disk full')):
            result, = self.run_batch([item], force=True)
        self.assertEqual(result['status'], 'error')
        self.assertTrue((self.projects['Authored'] / 'build-native/Release/game.exe').is_file())
        result, = self.run_batch([item], force=True)
        self.assertEqual(result['status'], 'success')
        self.assertFalse(self.projects['Authored'].exists())

    def test_parallel_jobs_never_remove_a_running_conversion_project(self):
        first, copy, second = self.rom('First.sms', 1), self.rom('First copy.sms', 1), self.rom('Second.sms', 2)
        first_published = threading.Event()
        alive = []

        def wait_for_first():
            self.assertTrue(first_published.wait(20))
            alive.append(self.projects['Second'].is_dir())

        self.hold['Second'] = wait_for_first

        def on_event(kind, index, value):
            if kind == 'result' and index == 0:
                first_published.set()

        results = self.run_batch([first, copy, second], jobs=2, on_event=on_event)
        self.assertEqual([r['status'] for r in results], ['success', 'duplicate', 'success'])
        self.assertEqual(alive, [True])
        self.assertFalse(self.projects['First'].exists() or self.projects['Second'].exists())

    def test_a_second_copy_of_the_same_rom_retries_in_the_kept_project(self):
        first, copy = self.rom('Same.sms', 3), self.rom('Same (copy).sms', 3)
        copy.title = first.title
        self.failures.add('Same')
        results = self.run_batch([first, copy], jobs=2)
        self.assertEqual([r['status'] for r in results], ['error', 'success'])
        self.assertEqual(self.compiler_mock.call_count, 2)
        self.assertFalse(self.projects['Same'].exists())


if __name__ == '__main__':
    unittest.main()
