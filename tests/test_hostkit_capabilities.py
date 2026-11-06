"""The host kit's 1.7.0 capabilities through its loop (tools/hostkit_capabilities_selftest.py): analog sticks, the D14
graphics page, a picture that grows, rumble and discs on a fake machine, and the same machine with all of them left out.
Runs when a C compiler and the pinned SDL2 build are available, and skips cleanly otherwise. No ROM, no visible window, no
sound device."""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'native/hostkit'
spec = importlib.util.spec_from_file_location('hostkit_capabilities_selftest', ROOT / 'tools' / 'hostkit_capabilities_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class CapabilityTests(unittest.TestCase):
    def test_sticks_graphics_page_picture_rumble_and_discs_through_the_loop(self):
        reason = selftest.ready()
        if reason:
            self.skipTest(reason)
        # A folder of the build tree (not a temporary one), so that a second run only relinks what changed.
        code, output, seconds = selftest.run_checks(ROOT / '.build/hostkit-capabilities-selftest')
        self.assertEqual(code, 0, output)
        self.assertIn('PASS', output)
        self.assertGreaterEqual(int(re.search(r'(\d+) checks', output).group(1)), 100, output)
        self.assertLess(seconds, 30, output)


class DefaultsOffTests(unittest.TestCase):
    """Every new field is off when an adapter leaves it out: none of today's adapters declares one."""

    def test_no_adapter_of_today_declares_the_new_fields(self):
        fields = ('.analog_sticks', '.script_axes', '.trigger_buttons', '.gfx_options', '.gfx_option_count', '.gfx_apply', '.pixel_pitch',
                  '.rumble', '.host_media', '.media_count', '.media_current', '.media_select')
        for path in (KIT / 'adapters').iterdir():
            text = path.read_text(encoding='utf-8')
            for field in fields:
                self.assertNotIn(field + ' =', text, (path.name, field))

    def test_the_kit_reaches_the_new_paths_only_through_the_new_fields(self):
        input_c = (KIT / 'shell/rrhk_input.c').read_text(encoding='utf-8')
        self.assertIn('if (rrhk.pads[p] && !m->analog_sticks) {', input_c)     # the left stick is the d-pad unless sticks are read
        self.assertIn('if (m->rumble) rrhk.rumble = ', input_c)
        events = (KIT / 'shell/rrhk_events.c').read_text(encoding='utf-8')
        self.assertIn('else if (key == SDL_SCANCODE_F3 && m->gfx_option_count > 0) toggle_graphics();', events)
        video = (KIT / 'shell/rrhk_video.c').read_text(encoding='utf-8')
        self.assertIn('if (m->pixel_pitch) {', video)
        main = (KIT / 'shell/rrhk_main.c').read_text(encoding='utf-8')
        self.assertIn('if (m->gfx_option_count > 0) rrhk_gfx_start(', main)
        options = (KIT / 'shell/rrhk_options.c').read_text(encoding='utf-8')
        self.assertIn('if (m->rumble) rrhk_option_row(', options)
        # Twenty actions; a page of up to fifteen rows (every machine of 1.6.9) never scrolls; a trigger binding needs the flag.
        self.assertIn('#define RRHK_MAX_ACTIONS 20', (KIT / 'hostkit.h').read_text(encoding='utf-8'))
        menu = (KIT / 'shell/rrhk_menu.c').read_text(encoding='utf-8')
        self.assertIn('enum { PAGE_ROWS = 15 };', menu)
        self.assertIn('if (rows <= PAGE_ROWS) return page_first = 0;', menu)
        self.assertIn('if (!rrhk.machine->trigger_buttons || (button != RRHK_PAD_LEFT_TRIGGER && button != RRHK_PAD_RIGHT_TRIGGER)) return false;', input_c)
        self.assertIn('if (!m || !m->trigger_buttons) return false;', input_c)
        self.assertIn('(m->trigger_buttons && (value == RRHK_PAD_LEFT_TRIGGER || value == RRHK_PAD_RIGHT_TRIGGER))', input_c)
        # The trigger values are fixed, outside SDL's buttons; an options page of fourteen rows or fewer is handed over whole.
        header = (KIT / 'hostkit.h').read_text(encoding='utf-8')
        self.assertIn('#define RRHK_PAD_LEFT_TRIGGER ((SDL_GameControllerButton)64)', header)
        self.assertIn('#define RRHK_PAD_RIGHT_TRIGGER ((SDL_GameControllerButton)65)', header)
        self.assertIn('if (all.count <= RRHK_OPTION_WINDOW) {', options)
    def test_the_new_strings_are_in_every_locale_and_the_game_catalogue(self):
        import json
        keys = ('Stick dead zone: %s', 'Vibration: %s', 'Retro-Recomp - Graphics', 'Filter: %s', 'Restore defaults',
                'Disc %d/%d', 'Change disc', 'F3  Graphics options', '%s (not at this size)')
        for code in ('fr', 'it', 'es', 'de', 'ja', 'ru', 'zh'):
            runtime = json.loads((ROOT / f'assets/locales/{code}.json').read_text(encoding='utf-8'))['runtime']
            for key in keys:
                self.assertIn(key, runtime, (code, key))
        catalogue = (ROOT / 'native/runtime_catalog.inc').read_text(encoding='ascii')
        for key in keys:
            self.assertIn('{"' + key + '",', catalogue)


if __name__ == '__main__':
    unittest.main()
