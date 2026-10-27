"""Stamps hash explicit lists and normalised text, never what happens to be on disk (docs/STANDARDS.md rule 5)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from retrorecomp import compilation_inputs as inputs
from retrorecomp import stamp_inputs
from retrorecomp.paths import ASSETS

ROOT = Path(__file__).resolve().parents[1]
CONSOLES = ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'x68', 'cps1')
# Output of the algorithm on the synthetic input of AlgorithmTests. If it changes, the stamps of every
# game change: bump compilation_inputs.STAMP_LABEL on purpose, then update these values.
PINNED_SYNTHETIC = {
    'game': '6e9a637ab9893f98c164950e4d26f8aa73366a3fffd3fd311836f3a5bd8a3998',
    'host': '22b9a0cd6a175586c6728612f54328cc8a2767f4167b9c6fb2165fd2aac37d00',
    'build': '63faac6a87479301cabff7accb4124c14cf9a9116cf1eaada3b58286c8b431e0',
}


def tracked_files():
    try:
        done = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return [name for name in done.stdout.decode('utf-8').split('\0') if name]


def module_name(path):
    name = path[:-3].replace('/', '.')
    return name[:-len('.__init__')] if name.endswith('.__init__') else name


class WorkTree:
    """A temporary copy of every listed file, standing in for the bundle root."""

    def setUpTree(self, crlf=False):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for name in inputs.manifest_names():
            if name.startswith('retrorecomp.'):
                continue
            data = (ASSETS / name).read_bytes()
            if crlf and inputs._file_kind(name) == 'text':
                data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        patched = patch('retrorecomp.paths.ASSETS', self.root); patched.start(); self.addCleanup(patched.stop)

    def stamps(self):
        return {system: (inputs.engine_stamp(system), inputs.role_stamps(system)) for system in CONSOLES}


class ManifestTests(unittest.TestCase):
    def test_every_tracked_input_is_listed_or_declared_out(self):
        tracked = tracked_files()
        if tracked is None:
            self.skipTest('not a git checkout')
        listed = set(inputs.manifest_names())
        stray = [name for name in tracked
                 if name.startswith(('native/', 'assets/', 'profiles/', 'licenses/'))
                 and name not in listed and not name.startswith(stamp_inputs.NOT_INPUTS)]
        self.assertEqual(stray, [], 'add each file to INPUTS (with its owners) or to NOT_INPUTS in retrorecomp/stamp_inputs.py')
        modules = [module_name(name) for name in tracked if name.startswith('retrorecomp/') and name.endswith('.py')
                   and name != 'retrorecomp/__init__.py']
        unlisted = [name for name in modules
                    if name not in listed and name.rsplit('.', 1)[-1] not in stamp_inputs.INTERFACE_MODULES]
        self.assertEqual(unlisted, [], 'add each module to INPUTS or to INTERFACE_MODULES in retrorecomp/stamp_inputs.py')
        self.assertIn('THIRD_PARTY_NOTICES.md', listed)
        for name in listed:
            if not name.startswith('retrorecomp.'):
                self.assertIn(name, tracked, name + ' is listed but not tracked')
            else:
                self.assertIn(name, modules, name + ' is listed but is no tracked module')

    def test_the_lists_are_consistent(self):
        names = [name for listed in stamp_inputs.INPUTS.values() for name in listed]
        self.assertEqual(len(names), len(set(names)), 'a name is listed twice')
        listed = set(names)
        self.assertFalse(listed & set(stamp_inputs.NOT_INPUTS))
        interface = {name for name in listed if name.rsplit('.', 1)[-1] in stamp_inputs.INTERFACE_MODULES
                     and name.startswith('retrorecomp')}
        self.assertEqual(interface, set(), 'a module cannot be both listed and an interface module')
        for module in stamp_inputs.HOST_MODULES | stamp_inputs.BUILD_MODULES:
            self.assertTrue(any(name.endswith('.' + module) for name in listed), module)
        for name in stamp_inputs.HOST_NATIVE:
            self.assertIn('native/' + name, listed)
        for key in stamp_inputs.INPUTS:
            self.assertTrue(key == stamp_inputs.ALL or set(key) <= set(CONSOLES), key)
        for name in listed:
            if not name.startswith('retrorecomp'):
                inputs._file_kind(name)  # every listed type is classified as text or binary

    def test_the_rules_never_own_a_file_the_manifest_leaves_to_others(self):
        # owners() is the default scope of a new file; the manifest may add consoles (the X68000 uses
        # code generators and 68000 sources of other consoles) but must not drop the rule's consoles.
        for name in inputs.manifest_names():
            if name.startswith('retrorecomp.'):
                leaf = name.rsplit('.', 1)[-1]
            elif name.startswith('native/') and name.count('/') == 1:
                leaf = Path(name).name
            else:
                continue
            for system in inputs.owners(leaf):
                self.assertIn(name, inputs.manifest_names(system), f'{name} is owned by {system} by rule')

    def test_everything_listed_is_bundled_in_the_executable(self):
        from tools.prepare_publication import BUNDLED_FILES, PUBLIC_MODULES
        for name in inputs.manifest_names():
            if name.startswith('retrorecomp'):
                self.assertIn(name, PUBLIC_MODULES)
            else:
                self.assertIn(name, BUNDLED_FILES, name + ' is a stamp input missing from the executable')

    def test_the_definition_of_the_stamps_is_not_an_input(self):
        for system in CONSOLES:
            names = {name for name, _ in inputs.input_fingerprints(system)}
            self.assertFalse({'retrorecomp.compilation_inputs', 'retrorecomp.stamp_inputs'} & names, system)
        self.assertLessEqual({'compilation_inputs', 'stamp_inputs'}, stamp_inputs.INTERFACE_MODULES)

    def test_the_x68000_sdk_tools_are_listed(self):
        from retrorecomp.x68000_conversion import SDK_TOOLS
        self.assertEqual({name for name in inputs.manifest_names('x68') if name.startswith('tools/')},
                         {'tools/' + name for name in SDK_TOOLS})
        for name in ('retrorecomp.neogeo_codegen', 'retrorecomp.megadrive_codegen', 'native/neogeo_native.h',
                     'native/neogeo_native.c', 'native/md_prefetch.inc'):
            self.assertIn(name, inputs.manifest_names('x68'))

    def test_the_package_qualification_hook_covers_the_nine_consoles(self):
        with tempfile.TemporaryDirectory() as folder:
            for command, expected in (('_compilation-stamps', inputs.engine_stamp),
                                      ('_compilation-inputs', lambda system: [list(pair) for pair in inputs.input_fingerprints(system)])):
                out = Path(folder) / (command + '.json')
                subprocess.run([sys.executable, '-B', str(ROOT / 'RetroRecomp.py'), command, str(out)], cwd=ROOT, check=True)
                written = json.loads(out.read_text(encoding='utf-8'))
                self.assertEqual(sorted(written), sorted(CONSOLES))
                self.assertEqual(written, {system: expected(system) for system in CONSOLES})

    def test_stamps_do_not_enumerate_the_disk(self):
        with patch('pkgutil.iter_modules', side_effect=AssertionError('modules are listed, not discovered')):
            self.assertEqual(len(inputs.engine_stamp('sms')), 64)

    def test_text_line_ends_are_pinned_by_gitattributes(self):
        attributes = (ROOT / '.gitattributes').read_text(encoding='utf-8')
        for pattern in ('CMakeLists.txt', '*.cmake', '*.json', '*.txt', '*.c', '*.h', '*.inc', '*.md', '*.py', '*.toml'):
            self.assertRegex(attributes, r'(?m)^' + pattern.replace('.', r'\.').replace('*', r'\*') + r' text eol=lf\s*$')
        for name in stamp_inputs.RAW_FILES:
            self.assertRegex(attributes, r'(?m)^' + name.replace('.', r'\.') + r' -text\b')
        tracked = tracked_files()
        if tracked is None:
            self.skipTest('not a git checkout')
        listing = subprocess.run(['git', 'ls-files', '--eol', '-z', *[n for n in tracked if n in set(inputs.manifest_names())]],
                                 cwd=ROOT, capture_output=True, check=True).stdout.decode('utf-8')
        for entry in filter(None, listing.split('\0')):
            info, name = entry.split('\t', 1)
            if inputs._file_kind(name) == 'text' and name not in stamp_inputs.RAW_FILES:
                self.assertTrue(info.startswith('i/lf') or info.startswith('i/none'), entry)


class ReproducibleTests(WorkTree, unittest.TestCase):
    """What lies beside the listed files, and the line ends they carry, change no stamp."""

    def test_a_crlf_copy_gives_the_stamps_of_the_original(self):
        reference = {system: (inputs.engine_stamp(system), inputs.role_stamps(system)) for system in CONSOLES}
        self.setUpTree(crlf=True)
        self.assertEqual(self.stamps(), reference)

    def test_files_that_are_not_listed_change_no_stamp(self):
        self.setUpTree()
        before = self.stamps()
        for stray in ('native/dummy_untracked.c', 'native/x68000_reference/dummy_untracked.c',
                      'native/x68000_native/dummy_untracked.inc', 'native/x68000_machine/dummy_untracked.h',
                      'native/x68000_reference/adapt_upstream.cmake', 'assets/dummy.png', 'licenses/dummy.md',
                      'profiles/dummy.toml', 'tools/x68000_dummy.py'):
            path = self.root / stray
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('stray file ' + stray, encoding='utf-8')
        self.assertEqual(self.stamps(), before)

    def test_the_x68000_sdk_stamp_ignores_stray_files_and_line_ends(self):
        from retrorecomp.x68000_conversion import sdk_stamp
        self.setUpTree()
        before = (sdk_stamp(), sdk_stamp('game'))
        for stray in ('native/x68000_reference/dummy.c', 'native/x68000_native/dummy.c', 'native/x68000_machine/dummy.c'):
            (self.root / stray).write_text('stray', encoding='utf-8')
        self.assertEqual((sdk_stamp(), sdk_stamp('game')), before)
        # A listed file moves it; the player shell moves the full stamp only.
        (self.root / 'native/x68000_reference/player_ui.inc').write_text('new menu', encoding='utf-8')
        self.assertEqual(sdk_stamp('game'), before[1])
        self.assertNotEqual(sdk_stamp(), before[0])
        (self.root / 'native/x68000_reference/probe.c').write_text('new probe', encoding='utf-8')
        self.assertNotEqual(sdk_stamp('game'), before[1])

    def test_a_listed_file_that_is_missing_is_an_error_not_a_skip(self):
        self.setUpTree()
        (self.root / 'native/x68000_reference/probe.c').unlink()
        with self.assertRaises(ValueError):
            inputs.engine_stamp('x68')
        self.assertEqual(len(inputs.engine_stamp('sms')), 64)  # other consoles do not own it
        with patch.object(inputs, 'INPUTS', {**inputs.INPUTS, ('sms',): ('native/unknown_type.xyz',)}):
            (self.root / 'native/unknown_type.xyz').write_text('x', encoding='utf-8')
            with self.assertRaises(ValueError):
                inputs.engine_stamp('sms')

    def test_adding_a_console_file_list_entry_moves_only_that_console(self):
        self.setUpTree()
        before = self.stamps()
        (self.root / 'native/gb_new_file.c').write_text('new Game Boy file', encoding='utf-8')
        self.assertEqual(self.stamps(), before)  # on disk only: ignored
        listed = {**stamp_inputs.INPUTS, ('gb',): (*stamp_inputs.INPUTS[('gb',)], 'native/gb_new_file.c')}
        with patch.object(inputs, 'INPUTS', listed):
            after = self.stamps()
        self.assertNotEqual(before['gb'], after['gb'])
        for system in CONSOLES:
            if system != 'gb':
                self.assertEqual(before[system], after[system], system)

    def test_a_listed_file_that_changes_moves_only_its_owners(self):
        self.setUpTree()
        before = self.stamps()
        (self.root / 'native/gb_menu.inc').write_text('new Game Boy menu', encoding='utf-8')
        after = self.stamps()
        self.assertNotEqual(before['gb'][0], after['gb'][0])
        self.assertNotEqual(before['gb'][1]['host'], after['gb'][1]['host'])
        self.assertEqual(before['gb'][1]['game'], after['gb'][1]['game'])
        for system in CONSOLES:
            if system != 'gb':
                self.assertEqual(before[system], after[system], system)

    def test_save_state_and_compiler_signatures_follow_the_listed_files_only(self):
        from retrorecomp import console16_state, core
        self.setUpTree()
        game = self.root / 'game'
        game.mkdir()
        project = self.root / 'project'
        project.mkdir()
        (project / 'retro_md_game.h').write_text('#define X 1\n')
        rom = SimpleNamespace(sha256='d' * 64)

        def abi():
            console16_state.write_config(project, rom, 'md', 'Test', {})
            return (project / 'retro16_state_config.h').read_text(encoding='ascii')

        before = (abi(), core.compiler_signature(game))
        for stray in ('native/dummy_untracked.c', 'native/dummy_untracked.h'):
            (self.root / stray).write_text('stray', encoding='utf-8')
        self.assertEqual((abi(), core.compiler_signature(game)), before)
        # Another console's file moves neither; a shared or own file moves them.
        (self.root / 'native/gb_menu.inc').write_text('new Game Boy menu', encoding='utf-8')
        self.assertEqual((abi(), core.compiler_signature(game)), before)
        (self.root / 'native/md_prefetch.inc').write_text('new pipeline', encoding='utf-8')
        self.assertNotEqual(abi(), before[0])
        self.assertEqual(core.compiler_signature(game), before[1])
        (self.root / 'native/CMakeLists.txt').write_text('new shared build file', encoding='utf-8')
        self.assertNotEqual(core.compiler_signature(game), before[1])
        # The same text with CRLF line ends is the same input.
        text = (self.root / 'native/CMakeLists.txt').read_bytes()
        signature, state = core.compiler_signature(game), abi()
        (self.root / 'native/CMakeLists.txt').write_bytes(text.replace(b'\n', b'\r\n'))
        self.assertEqual((abi(), core.compiler_signature(game)), (state, signature))


class InterfaceListTests(unittest.TestCase):
    def test_registering_an_interface_module_changes_no_stamp(self):
        before = {system: (inputs.engine_stamp(system), inputs.role_stamps(system)) for system in CONSOLES}
        registered = inputs.INTERFACE_MODULES | {'a_new_interface_module', 'another_one'}
        with patch.object(inputs, 'INTERFACE_MODULES', registered), \
                patch.object(stamp_inputs, 'INTERFACE_MODULES', registered):
            after = {system: (inputs.engine_stamp(system), inputs.role_stamps(system)) for system in CONSOLES}
        self.assertEqual(before, after)

    def test_legacy_stamps_and_the_role_tables_are_not_inputs(self):
        before = {system: inputs.role_stamps(system) for system in CONSOLES}
        with patch.dict(inputs.LEGACY_GAME_STAMPS, {'sms': ('f' * 64,), 'x68': ('e' * 64,)}):
            self.assertEqual(before, {system: inputs.role_stamps(system) for system in CONSOLES})


class AlgorithmTests(unittest.TestCase):
    """The algorithm is not hashed (it is an interface module); this pins its output instead."""

    def test_the_stamp_of_a_synthetic_input_is_pinned(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        files = {'native/retro_menu.c': b'menu\r\nsecond line\r\n', 'native/launcher.c': b'launcher\n',
                 'assets/Retro-Recomp.ico': b'\x00\x01\r\n\x02', 'assets/neogeo-catalogue.json': b'{"a":1}\r\n'}
        for name, data in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_bytes(data)
        manifest = {inputs.ALL: ('retrorecomp.core', 'retrorecomp.toolchain', *files)}
        with patch('retrorecomp.paths.ASSETS', root), patch.object(inputs, 'INPUTS', manifest), \
                patch.object(inputs, '_code_digest', side_effect=lambda name, *rest: 'code:' + name):
            stamps = inputs.role_stamps('sms')
            # Line ends of text are not part of the stamp; the pinned catalogue and the icon stay exact.
            (root / 'native/retro_menu.c').write_bytes(b'menu\nsecond line\n')
            self.assertEqual(inputs.role_stamps('sms'), stamps)
            (root / 'assets/neogeo-catalogue.json').write_bytes(b'{"a":1}\n')
            self.assertNotEqual(inputs.role_stamps('sms')['game'], stamps['game'])
            (root / 'assets/neogeo-catalogue.json').write_bytes(b'{"a":1}\r\n')
        self.assertEqual(inputs.STAMP_LABEL, 'v2')
        self.assertEqual(stamps, PINNED_SYNTHETIC, 'the algorithm changed: bump STAMP_LABEL and update the pinned values')


if __name__ == '__main__':
    unittest.main()
