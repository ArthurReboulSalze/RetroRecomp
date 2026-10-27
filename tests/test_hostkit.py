"""The host kit of the 16-bit exports: what is staged, what it may contain, and how it is built."""
from pathlib import Path
import re
import tempfile
import unittest

from retrorecomp import compilation_inputs as inputs
from retrorecomp import hostkit

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'native/hostkit'
FAMILIES = ('md', 'snes', 'ng', 'cps1')


class StagingTests(unittest.TestCase):
    def test_a_family_gets_the_shell_and_its_own_adapter(self):
        for family in FAMILIES:
            with self.subTest(family=family), tempfile.TemporaryDirectory() as folder:
                project = Path(folder)
                listed = hostkit.stage(project, family)
                self.assertEqual(listed, hostkit.sources(family))
                self.assertEqual(len(listed), len(hostkit.SHELL) + 1)
                adapters = [name for name in listed if '/adapters/' in name]
                self.assertEqual(adapters, [f'hostkit/adapters/rrhk_{family}.c'])
                for name in (*listed, 'hostkit/hostkit.h', 'hostkit/hostkit_internal.h'):
                    self.assertEqual((project / name).read_bytes(), (KIT / name.split('/', 1)[1]).read_bytes())
                self.assertEqual(sorted(path.relative_to(project).as_posix() for path in (project / 'hostkit').rglob('*')
                                        if path.is_file()), sorted([*listed, 'hostkit/hostkit.h', 'hostkit/hostkit_internal.h']))

    def test_an_unchanged_file_keeps_its_timestamp(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            hostkit.stage(project, 'md')
            target = project / 'hostkit/shell/rrhk_main.c'
            before = target.stat().st_mtime_ns
            hostkit.stage(project, 'md')
            self.assertEqual(target.stat().st_mtime_ns, before)

    def test_every_kit_file_is_a_listed_host_input_and_every_name_is_unique(self):
        files = sorted(path.relative_to(ROOT).as_posix() for path in KIT.rglob('*') if path.is_file())
        listed = set(inputs.manifest_names())
        for name in files:
            self.assertIn(name, listed)
            self.assertEqual(inputs.role(name), 'host', name)
        names = [Path(name).name for name in files]
        self.assertEqual(len(names), len(set(names)))
        # A project builds one object per file name, whatever the folder: the engines own audio.c, menu.c, ...
        for name in names:
            if name.endswith('.c'):
                self.assertTrue(name.startswith('rrhk_'), name)
        self.assertEqual(inputs.role('retrorecomp.hostkit'), 'host')


class ContentTests(unittest.TestCase):
    def test_only_the_options_file_includes_the_options_header(self):
        """game_options.h keeps its settings in file-level statics: a second includer gets a second copy."""
        for path in KIT.rglob('*.c'):
            includes = 'game_options.h' in path.read_text(encoding='utf-8')
            self.assertEqual(includes, path.name == 'rrhk_options.c', path.name)

    def test_the_shell_knows_no_machine(self):
        for path in (KIT / 'shell').glob('*.c'):
            # console16_video.h is the geometry helper (rr16_video_rect) the headless runs share; no machine in it.
            text = path.read_text(encoding='utf-8').replace('rr16_video_rect', '')
            self.assertIsNone(re.search(r'RR16_(NG|CPS1|MD|SNES|GUN)|rr_(ng|cps1|md)_|rr16_', text), path.name)
            self.assertNotIn('retro_console16.h', text, path.name)

    def test_every_adapter_defines_the_entry_the_game_calls(self):
        for family in FAMILIES:
            text = (KIT / f'adapters/rrhk_{family}.c').read_text(encoding='utf-8')
            self.assertIn('int rr16_sdl_main(const char *title, int scale)', text)
            self.assertIn('const RrhkMachine *rrhk_adapter(void)', text)

    def test_the_builds_list_the_kit_and_not_the_old_shell(self):
        for module in ('console16', 'cps1_build', 'neogeo_build'):
            text = (ROOT / f'retrorecomp/{module}.py').read_text(encoding='utf-8')
            self.assertNotIn('console16_host_ui', text, module)
            self.assertIn('hostkit.stage(', text, module)
            self.assertIn('hostkit.sources(', text, module)
        self.assertFalse((ROOT / 'native/console16_host_ui.c').exists())


if __name__ == '__main__':
    unittest.main()
