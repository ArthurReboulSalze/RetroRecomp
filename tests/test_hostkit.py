"""The host kit of the 16-bit and NES exports: what is staged, what it may contain, and how it is built."""
from pathlib import Path
import re
import tempfile
import unittest

from retrorecomp import compilation_inputs as inputs
from retrorecomp import hostkit

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'native/hostkit'
FAMILIES = ('md', 'snes', 'ng', 'cps1', 'nes', 'sms', 'gb')
# An adapter the platform file of its runtime includes (one translation unit) is staged, not compiled by itself.
INCLUDED = {'gb': 'hostkit/adapters/rrhk_gb.inc'}


class StagingTests(unittest.TestCase):
    def test_a_family_gets_the_shell_and_its_own_adapter(self):
        for family in FAMILIES:
            with self.subTest(family=family), tempfile.TemporaryDirectory() as folder:
                project = Path(folder)
                listed = hostkit.stage(project, family)
                self.assertEqual(listed, hostkit.sources(family))
                included = INCLUDED.get(family)
                self.assertEqual(len(listed), len(hostkit.SHELL) + (0 if included else 1))
                adapters = [name for name in listed if '/adapters/' in name]
                self.assertEqual(adapters, [] if included else [f'hostkit/adapters/rrhk_{family}.c'])
                staged = [*listed, *([included] if included else [])]
                for name in (*staged, 'hostkit/hostkit.h', 'hostkit/hostkit_internal.h'):
                    self.assertEqual((project / name).read_bytes(), (KIT / name.split('/', 1)[1]).read_bytes())
                self.assertEqual(sorted(path.relative_to(project).as_posix() for path in (project / 'hostkit').rglob('*')
                                        if path.is_file()), sorted([*staged, 'hostkit/hostkit.h', 'hostkit/hostkit_internal.h']))

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
            text = (KIT / f'adapters/rrhk_{family}.{"inc" if family in INCLUDED else "c"}').read_text(encoding='utf-8')
            entry = {'nes': 'int cyc_sdl_main(const char *title, int scale)',
                     'gb': 'bool gb_platform_init(int scale)',
                     'sms': 'bool host_init(int width, int height, int x, int y, int crop_w, int crop_h, int scale'}.get(
                family, 'int rr16_sdl_main(const char *title, int scale)')
            self.assertIn(entry, text)
            self.assertIn('const RrhkMachine *rrhk_adapter(void)', text)

    def test_the_builds_list_the_kit_and_not_the_old_shell(self):
        for module in ('console16', 'cps1_build', 'neogeo_build'):
            text = (ROOT / f'retrorecomp/{module}.py').read_text(encoding='utf-8')
            self.assertNotIn('console16_host_ui', text, module)
            self.assertIn('hostkit.stage(', text, module)
            self.assertIn('hostkit.sources(', text, module)
        self.assertFalse((ROOT / 'native/console16_host_ui.c').exists())

    def test_the_master_system_and_game_gear_share_one_adapter_staged_beside_the_common_runtime(self):
        self.assertEqual(hostkit.sources('sms'), hostkit.sources('gg'))
        core = (ROOT / 'retrorecomp/core.py').read_text(encoding='utf-8')
        self.assertIn('hostkit.stage(native_source, "sms")', core)
        cmake = (ROOT / 'native/CMakeLists.txt').read_text(encoding='utf-8')
        for name in hostkit.sources('sms'):
            self.assertIn(name, cmake, name)
        for name in ('host.c', 'controls.c', 'ui.c', 'ui.h', 'controls.h'):
            self.assertFalse((ROOT / 'native' / name).exists(), name)
            self.assertNotIn(f' {name} ', cmake, name)

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


class GameBoyTests(unittest.TestCase):
    """The Game Boy (phase 5): the runtime's platform file keeps the loop and calls the kit; its adapter is included by it."""

    def test_the_platform_file_includes_the_adapter_and_the_build_compiles_the_shell(self):
        from retrorecomp import gameboy_host
        self.assertEqual(gameboy_host.ADAPTER, 'hostkit/adapters/rrhk_gb.inc')
        self.assertEqual(inputs.role('native/hostkit/adapters/rrhk_gb.inc'), 'host')
        cmake = gameboy_host.kit_cmake('')
        for name in hostkit.sources('gb'):
            self.assertIn(name, cmake, name)
        self.assertNotIn('rrhk_gb', cmake)

    def test_the_former_shell_is_gone(self):
        for name in ('gb_menu.inc', 'gb_audio_output.inc', 'gb_input_refresh.inc'):
            self.assertFalse((ROOT / 'native' / name).exists(), name)
        self.assertFalse((ROOT / 'retrorecomp/gameboy_timing.py').exists())

    def test_the_adapter_plays_through_the_stereo_ring_and_is_driven(self):
        text = (KIT / 'adapters/rrhk_gb.inc').read_text(encoding='utf-8')
        for setting in ('audio_model = RRHK_AUDIO_RING', 'audio_channels = 2', 'audio_rate = 44100u', 'driven = true', 'host_pause = '):
            self.assertIn(setting, text)


class SoundAndSpeedTests(unittest.TestCase):
    """Decision D12 (1.6.3): the Game Boy's former Tab, backquote and M keys, the volume and the output device, on every console."""

    def test_every_console_goes_through_the_one_sound_stage(self):
        options = (ROOT / 'native/game_options.h').read_text(encoding='utf-8')
        for name in ('volume', 'muted', 'speed_held'):
            self.assertIn(name, options)
        # the ring and the queue of the kit, the Master System / Game Gear output and the Mega Drive engine all call it
        self.assertIn('rrhk_options_audio(', (KIT / 'shell/rrhk_ring.c').read_text(encoding='utf-8'))
        self.assertIn('rrhk_options_audio(', (KIT / 'shell/rrhk_audio.c').read_text(encoding='utf-8'))
        self.assertIn('RR_HOST_AUDIO_FILTER', (ROOT / 'native/audio_output.inc').read_text(encoding='utf-8'))
        self.assertIn('rr_md_audio_stage(', (ROOT / 'retrorecomp/megadrive_audio.py').read_text(encoding='utf-8'))
        self.assertIn('rr_md_audio_stage = rrhk_options_audio', (KIT / 'adapters/rrhk_md.c').read_text(encoding='utf-8'))

    def test_the_keys_are_the_game_boys_former_ones(self):
        events = (KIT / 'shell/rrhk_events.c').read_text(encoding='utf-8')
        for key in ('SDL_SCANCODE_TAB', 'SDL_SCANCODE_GRAVE', 'SDL_SCANCODE_M', 'SDL_CONTROLLER_AXIS_TRIGGERRIGHT',
                    'SDL_CONTROLLER_AXIS_TRIGGERLEFT'):
            self.assertIn(key, events)
        main = (KIT / 'shell/rrhk_main.c').read_text(encoding='utf-8')
        self.assertIn('rrhk.max_speed ? 500 : rrhk.fast_hold ? 250 : 100', main)
        # the pacing of a normal speed is the expression it always was
        self.assertIn('if (r->speed != 100) period = period * 100 / (Uint64)r->speed;', main)
        self.assertIn('Tab  Fast-forward', (KIT / 'shell/rrhk_menu.c').read_text(encoding='utf-8'))

    def test_the_game_boy_preferences_of_1_6_2_are_read(self):
        adapter = (KIT / 'adapters/rrhk_gb.inc').read_text(encoding='utf-8')
        for key in ('audio.muted', 'audio.volume_percent', 'audio.device_name'):
            self.assertIn(key, adapter)

    def test_a_menu_stops_a_guest_that_owns_the_loop_even_with_a_state_pending(self):
        main = (KIT / 'shell/rrhk_main.c').read_text(encoding='utf-8')
        self.assertIn('(!r->pending_state || r->driven)', main)

    def test_the_game_boy_reset_forgets_the_held_buttons_like_a_state_load(self):
        adapter = (KIT / 'adapters/rrhk_gb.inc').read_text(encoding='utf-8')
        body = adapter.split('static void rr_gb_reset(void) {', 1)[1].split('}', 1)[0]
        self.assertIn('rrhk_autofire_reset();', body)

    def test_a_removed_output_device_is_replaced_on_every_console(self):
        audio = (KIT / 'shell/rrhk_audio.c').read_text(encoding='utf-8')
        # the machines that own their device say which one it is
        self.assertIn('m->audio_device_id()', audio)
        self.assertIn('.audio_device_id = host_audio_device_id', (KIT / 'adapters/rrhk_sms.c').read_text(encoding='utf-8'))
        self.assertIn('.audio_device_id = audio_device_id', (KIT / 'adapters/rrhk_md.c').read_text(encoding='utf-8'))
        self.assertIn('rr_md_audio_device_id', (ROOT / 'retrorecomp/megadrive_audio.py').read_text(encoding='utf-8'))
        # a device that is gone is opened again through the opening path, not only replaced while it is open
        body = audio.split('bool rrhk_audio_reopen(RrhkRun *run) {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('rrhk_audio_open(run)', body)
        self.assertNotIn('if (!run->audio) return false;', body)

    def test_a_pad_plugged_or_unplugged_never_leaves_the_fast_forward_held(self):
        events = (KIT / 'shell/rrhk_events.c').read_text(encoding='utf-8')
        speed = events.split('static void speed_event(', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('SDL_CONTROLLERDEVICEREMOVED', speed)
        self.assertIn('rrhk.fast_hold &= ~HOLD_TRIGGER', speed)

    def test_a_chord_of_the_quit_or_restart_combination_is_not_a_sound_key(self):
        events = (KIT / 'shell/rrhk_events.c').read_text(encoding='utf-8')
        self.assertEqual(events.count('rrhk_options_component('), 4)     # Pause (two), the Tab hold, and M / backquote

    def test_the_new_strings_are_in_every_locale(self):
        import json
        for code in ('fr', 'it', 'es', 'de', 'ja', 'ru', 'zh'):
            runtime = json.loads((ROOT / f'assets/locales/{code}.json').read_text(encoding='utf-8'))['runtime']
            for key in ('Maximum speed ON', 'Maximum speed OFF', 'Sound muted', 'Sound on', 'Volume: %s', 'M Sound: %s',
                        'Output device: %s', 'System default', '` Max speed: %s', 'Tab  Fast-forward | `  Max speed | M  Mute'):
                self.assertIn(key, runtime, code)


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
