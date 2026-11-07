"""The PlayStation adapter's controls (native/hostkit/adapters/rrhk_psx.c), read from its source: no ROM, no build.

The game's own input check (psx_main.c --input-check, run by every conversion) proves each control reaches its button of the
console through the core; this test keeps the table that check compares with complete and coherent."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = (ROOT / 'native/hostkit/adapters/rrhk_psx.c').read_text(encoding='utf-8')
SESSION = (ROOT / 'native/psx_machine/psx_session.c').read_text(encoding='utf-8')
# Sony's bit of each button in the pad's answer (Select 0 ... Square 15), the Analog button after them.
CONSOLE = {'Select': 0, 'L3': 1, 'R3': 2, 'Start': 3, 'Up': 4, 'Right': 5, 'Down': 6, 'Left': 7, 'L2': 8, 'R2': 9,
           'L1': 10, 'R1': 11, 'Triangle': 12, 'Circle': 13, 'Cross': 14, 'Square': 15, 'Analog': 16}


class PsxAdapterTest(unittest.TestCase):
    def setUp(self):
        self.order = re.search(r'enum \{ (CROSS[^}]*), ACTIONS \};', ADAPTER).group(1).replace(' ', '').split(',')
        table = ADAPTER[ADAPTER.index('static const RrhkAction actions[ACTIONS] = {'):]
        table = table[:table.index('};')]
        self.names = re.findall(r'^\s*\{"([^"]+)", L"', table, flags=re.M)
        bits = re.search(r'static const int ps_bits\[ACTIONS\] = \{([^}]*)\};', ADAPTER).group(1)
        self.bits = [int(b) for b in bits.replace(' ', '').split(',')]

    def test_every_control_has_its_console_button(self):
        self.assertEqual(len(self.names), len(self.order))
        self.assertEqual(len(self.bits), len(self.order))
        for name, bit in zip(self.names, self.bits):
            self.assertEqual(bit, CONSOLE.get(name, -1), name)
        # seventeen controls of the pad, each its own button, and Change disc
        self.assertEqual(sorted(b for b in self.bits if b >= 0), list(range(17)))
        self.assertEqual(self.names[-1], 'Change disc')

    def test_host_side_actions(self):
        self.assertIn('{"Analog", L"Analog", 0, RRHK_SYSTEM', ADAPTER)
        self.assertIn('{"Change disc", L"ChangeDisc", 0, RRHK_SYSTEM', ADAPTER)
        self.assertIn('.host_media = 1 + DISC', ADAPTER)
        self.assertNotIn('SDL_CONTROLLER_BUTTON_GUIDE', ADAPTER)    # the Guide button opens F2
        self.assertLessEqual(len(self.order), 20)                   # RRHK_MAX_ACTIONS

    def test_capabilities_declared(self):
        for field in ('.analog_sticks = 2', '.trigger_buttons = true', '.rumble = true', '.gfx_apply = gfx_apply',
                      '.pixel_pitch = pixel_pitch', '.event = event'):
            self.assertIn(field, ADAPTER)
        self.assertIn('PADS(RRHK_PAD_LEFT_TRIGGER)', ADAPTER)
        self.assertIn('PADS(RRHK_PAD_RIGHT_TRIGGER)', ADAPTER)

    def test_the_pad_powers_on_digital(self):
        # Beetle's default keeps the DualShock in analog mode, where Tomba! read no direction (6 November 2026).
        self.assertIn('{"beetle_psx_analog_toggle", "enabled"}', SESSION)

    def test_the_core_gets_its_own_option_defaults(self):
        # An option the session does not set is answered with the core's declared default, as a frontend does: left
        # unanswered, the DualShock's mode combination was "no button" and each release switched the mode (6 November 2026).
        self.assertIn('case RETRO_ENVIRONMENT_SET_VARIABLES:', SESSION)
        self.assertIn('keep_core_defaults((const struct retro_variable *)data);', SESSION)
        self.assertRegex(SESSION, r'for \(int i = 0; i < core_default_count; \+\+i\)\s+if \(strcmp\(core_defaults\[i\]\.key')
        self.assertIn('mode after presses', ADAPTER)

    def test_the_stick_drives_the_dpad_of_a_digital_pad(self):
        self.assertIn('pads[p] = stick_directions(p, pads[p], axes[p]);', ADAPTER)
        self.assertIn('if (rr_psx_pad_analog_mode(rr_psx_host_session(), player) != 0) return pad;', ADAPTER)

    def test_graphics_defaults_are_the_cores(self):
        # The default of each option is the setting every gate uses: Beetle's own, except deinterlacing (progressive).
        defaults = {'resolution_values': '1x(native)', 'dithering_values': '1x(native)', 'deinterlacing_values': 'off',
                    'aspect_values': 'corrected', 'crop_values': 'smart'}
        for table, value in defaults.items():
            first = re.search(rf'{table}\[\] = \{{"([^"]+)"', ADAPTER).group(1)
            self.assertEqual(first, value, table)
        self.assertRegex(ADAPTER, r'\{"Internal resolution", L"resolution", resolutions, 4, 0\}')
        # The first build's key held an index into another list (Weave first): a new key, so every player starts progressive.
        self.assertIn('{"Deinterlacing", L"deinterlace", deinterlacing, 4, 0}', ADAPTER)


if __name__ == '__main__':
    unittest.main()
