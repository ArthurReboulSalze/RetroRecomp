"""The host kit of the 16-bit and NES exports: what is staged, what it may contain, and how it is built."""
from pathlib import Path
import re
import tempfile
import unittest

from retrorecomp import compilation_inputs as inputs
from retrorecomp import hostkit

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'native/hostkit'
FAMILIES = ('md', 'snes', 'ng', 'cps1', 'nes')


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
            self.assertIsNone(re.search(r'RR16_(NG|CPS1|MD|SNES|GUN)|rr_(ng|cps1|md|nes)_|rr16_|cyc_|RR_NES', text), path.name)
            self.assertNotIn('retro_console16.h', text, path.name)

    def test_every_adapter_defines_the_entry_the_game_calls(self):
        for family in FAMILIES:
            text = (KIT / f'adapters/rrhk_{family}.c').read_text(encoding='utf-8')
            entry = 'int cyc_sdl_main(const char *title, int scale)' if family == 'nes' else 'int rr16_sdl_main(const char *title, int scale)'
            self.assertIn(entry, text)
            self.assertIn('const RrhkMachine *rrhk_adapter(void)', text)

    def test_the_builds_list_the_kit_and_not_the_old_shell(self):
        for module in ('console16', 'cps1_build', 'neogeo_build'):
            text = (ROOT / f'retrorecomp/{module}.py').read_text(encoding='utf-8')
            self.assertNotIn('console16_host_ui', text, module)
            self.assertIn('hostkit.stage(', text, module)
            self.assertIn('hostkit.sources(', text, module)
        self.assertFalse((ROOT / 'native/console16_host_ui.c').exists())

    def test_the_nes_build_stages_the_kit_and_not_its_old_host(self):
        text = (ROOT / 'retrorecomp/nes_runtime.py').read_text(encoding='utf-8')
        self.assertIn("hostkit.stage(project, 'nes')", text)
        self.assertIn('cyc_host.c {kit}', text)
        self.assertNotIn('nes_host_ui', text)
        self.assertFalse((ROOT / 'native/nes_host_ui.c').exists())
        self.assertFalse((ROOT / 'native/nes_audio_output.inc').exists())

    def test_a_machine_picks_its_audio_model_in_the_adapter(self):
        """The queue model is the default; the NES keeps the callback ring it always had (decision D5)."""
        text = (KIT / 'adapters/rrhk_nes.c').read_text(encoding='utf-8')
        self.assertIn('.audio_model = RRHK_AUDIO_RING', text)
        for family in ('md', 'snes', 'ng', 'cps1'):
            self.assertNotIn('RRHK_AUDIO_RING', (KIT / f'adapters/rrhk_{family}.c').read_text(encoding='utf-8'))

    def test_the_pad_slot_policy_strings_are_in_the_catalogue_in_every_language(self):
        """Decision D11: the Gamepad row and the capture notice speak every interface language."""
        import json
        keys = ('Gamepad', 'Automatic', 'None', '%s (disconnected)', 'No gamepad for player %d',
                'Enter: change gamepad | Delete: Automatic')
        for code in ('fr', 'it', 'es', 'de', 'ja', 'ru', 'zh'):
            runtime = json.loads((ROOT / f'assets/locales/{code}.json').read_text(encoding='utf-8'))['runtime']
            for key in keys:
                self.assertIn(key, runtime, (code, key))
        catalogue = (ROOT / 'native/runtime_catalog.inc').read_text(encoding='ascii')
        for key in keys:
            self.assertIn('{"' + key + '",', catalogue)
        shell = (KIT / 'shell/rrhk_input.c').read_text(encoding='utf-8')
        for name in ('"auto"', '"none"', 'L"device"', 'L"name"'):
            self.assertIn(name, shell)


if __name__ == '__main__':
    unittest.main()


class X68000Tests(unittest.TestCase):
    """The X68000 (phase 3) compiles the kit from the tree: its adapter is included by the one translation unit that owns the core."""

    def test_the_adapter_is_included_by_the_frontend_and_the_build_lists_the_shell(self):
        host = (ROOT / 'native/x68000_reference/reference_host.c').read_text(encoding='utf-8')
        self.assertIn('#include "hostkit/adapters/rrhk_x68k.inc"', host)
        adapter = (KIT / 'adapters/rrhk_x68k.inc').read_text(encoding='utf-8')
        self.assertIn('const RrhkMachine *rrhk_adapter(void)', adapter)
        self.assertIn('rrhk_main(', adapter)
        cmake = (ROOT / 'native/x68000_reference/CMakeLists.txt').read_text(encoding='utf-8')
        for name in hostkit.SHELL:
            self.assertIn(Path(name).stem.removeprefix('rrhk_'), cmake.split('foreach(RR_KIT_FILE', 1)[1].split(')', 1)[0], name)
        self.assertEqual(inputs.role('native/hostkit/adapters/rrhk_x68k.inc'), 'host')
        self.assertEqual(inputs.role('native/x68000_reference/reference_host.c'), 'game')

    def test_the_old_player_ui_is_gone(self):
        self.assertFalse((ROOT / 'native/x68000_reference/player_ui.inc').exists())
