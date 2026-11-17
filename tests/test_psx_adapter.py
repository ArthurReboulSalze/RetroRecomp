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
        # only a pad in analog mode reads its sticks: a DualShock in digital mode (0) and a standard pad (-1) take them as directions
        self.assertIn('if (rr_psx_pad_analog_mode(rr_psx_host_session(), player) == 1) return pad;', ADAPTER)
        self.assertIn('failures += mode == 1;', ADAPTER)

    def test_a_raised_resolution_the_pc_cannot_draw_is_said(self):
        # Tobal No. 1 at 4x runs 18 % too slow in combat on the CPU renderer and its sound breaks up: a notice says so.
        self.assertIn('"1x (native)", "2x", "4x", "8x (graphics card)"};', ADAPTER)
        # 8x only on the graphics card (the owner, 15 November 2026: « le 8x, c'est injouable » on the CPU): asked for with the
        # CPU drawing, it draws 4x and says so
        self.assertIn('if (resolution == 3 && !card) {', ADAPTER)
        self.assertIn('"8x needs the graphics card: 4x on the CPU"', ADAPTER)
        self.assertIn('watch_load();', ADAPTER)
        self.assertIn('if (scale == 1 || warned_scale == scale || interrupted)', ADAPTER)

    def test_graphics_defaults_are_the_cores(self):
        # The default of each option is the setting every gate uses: Beetle's own.
        defaults = {'resolution_values': '1x(native)', 'dithering_values': '1x(native)',
                    'aspect_values': 'corrected', 'crop_values': 'smart'}
        for table, value in defaults.items():
            first = re.search(rf'{table}\[\] = \{{"([^"]+)"', ADAPTER).group(1)
            self.assertEqual(first, value, table)
        self.assertRegex(ADAPTER, r'\{"Internal resolution", L"resolution", resolutions, 4, 0\}')
        # No deinterlacing row (the owner's « ok » of 15 November 2026): always progressive, the session's core setting.
        self.assertNotIn('Deinterlacing', ADAPTER)
        self.assertIn('{"beetle_psx_deinterlacer", "off"},', (ROOT / 'native/psx_machine/psx_session.c').read_text(encoding='utf-8'))


    def test_the_renderer_row_starts_on_the_graphics_card_and_checks_stay_on_the_cpu(self):
        # 1.7.7 (the owner, 15 November 2026: « je veux que par défaut, on ait une accélération graphique Vulkan »): the first
        # row, the card by default; a headless run (a check) never applies it, so it draws with the CPU unless asked
        self.assertIn('{"Renderer", L"renderer", renderers, 2, 0},', ADAPTER)
        self.assertIn('static const char *const renderers[] = {"Graphics card (Vulkan)", "CPU"};', ADAPTER)
        self.assertIn('for (int i = 0; i < GFX_COUNT; ++i) if (i != GFX_RENDERER) gfx_apply(i, check_default(i)); }', ADAPTER)
        main = (ROOT / 'native/psx_machine/psx_main.c').read_text(encoding='utf-8')
        self.assertIn('want_vulkan = !headless && !input_check;', main)
        # a card that cannot be used is never an error: the session opens on the CPU and says why; the player is told
        session = (ROOT / 'native/psx_machine/psx_session.c').read_text(encoding='utf-8')
        self.assertIn('set_option(s, "beetle_psx_renderer", "software");', session)
        self.assertIn('set_option(s, "beetle_psx_renderer_software_fb", "enabled");', session)
        self.assertIn('"No usable graphics card: the CPU draws the picture"', ADAPTER)
        # the session opened again (renderer switch, Restart) gets every row's value again
        self.assertIn('for (int i = 0; i < GFX_COUNT; ++i) if (i != GFX_RENDERER) core_option(i, chosen[i]);', ADAPTER)

    def test_the_screen_format_row_is_offered(self):
        # D27 (1.7.6): a game with its own anamorphic 16:9 option can be shown 16 wide for 9 high, kept per game.
        self.assertIn('.widescreen = true,', ADAPTER)


    def test_a_stick_at_its_edge_is_not_read_as_the_other_edge(self):
        # Beetle's DualShock turns -32768 into the byte of the other edge (32768 + right - left * 32768 / 32767 = -1, then
        # 0xFF): a stick pushed straight left went right (Ape Escape, 15 November 2026). The session holds the edge at -32767.
        session = (ROOT / 'native/psx_machine/psx_session.c').read_text(encoding='utf-8')
        self.assertIn('s->sticks[player][i] = v < -32767 ? -32767 : v;', session)
        # the core's arithmetic, as frontio.c computes the byte the game reads
        def byte(x):
            right, left = max(x, 0), max(-x, 0)
            return ((32768 + right - left * 32768 // 32767) >> 8) & 0xFF
        self.assertEqual(byte(-32768), 0xFF)            # unclamped: the right edge
        self.assertEqual(byte(max(-32768, -32767)), 0)  # clamped: the left edge
        self.assertEqual((byte(32767), byte(0)), (0xFF, 0x80))


    def test_the_window_always_gets_a_picture(self):
        # A session that has drawn nothing yet (a Restart, a renderer switch while F3 holds the machine) gives black, never NULL:
        # the xBR and Scale2x filters read the pixels (the owner's report of 15 November 2026: the game closed on a switch)
        session = (ROOT / 'native/psx_machine/psx_session.c').read_text(encoding='utf-8')
        self.assertIn('return s->picture ? s->picture : black_picture;', session)
        main = (ROOT / 'native/psx_machine/psx_main.c').read_text(encoding='utf-8')
        self.assertIn('if (opened && last) rr_psx_keep_picture(session, last, w, h, w);', main)
        self.assertIn('!strcmp(argv[i], "--gfx-at")', main)


    def test_pgxp_is_offered_off_and_only_in_memory_mode(self):
        # 1.7.7 (study section 7): two rows, both Off by default; "On" is Beetle's "memory only"; the checks run with it off
        # On for the player since the owner's decision (15 November 2026); the checks (headless) keep both off
        self.assertIn('{"Geometry precision (PGXP)", L"pgxp", pgxp_modes, 2, 1},', ADAPTER)
        self.assertIn('{"Perspective-correct textures", L"pgxp_texture", pgxp_textures, 2, 1},', ADAPTER)
        self.assertIn('return option == GFX_PGXP || option == GFX_PGXP_TEXTURE ? 0 : gfx_options[option].def;', ADAPTER)
        self.assertIn('gfx_apply(i, check_default(i));', ADAPTER)
        self.assertIn("if (option == GFX_PGXP_TEXTURE && !row_value(GFX_PGXP)) value = 0;", ADAPTER)
        self.assertIn('static const char *const pgxp_mode_values[] = {"disabled", "memory only"};', ADAPTER)
        self.assertNotIn('memory + CPU', ADAPTER.split('pgxp_mode_values[]')[1].split(';')[0])
        self.assertNotIn('pgxp_nclip', ADAPTER)
        self.assertNotIn('pgxp_vertex', ADAPTER)


    def test_antialiasing_and_texture_filtering_are_card_rows_off_by_default(self):
        # 1.7.7 (the owner's questions of 15 November 2026): one anti-aliasing row (MSAA or Supersampling, never both), one texture
        # filtering row (nearest, bilinear, 3-point), Off by default; no texture upscaler, no mipmapping
        self.assertIn('{"Anti-aliasing (GPU)", L"antialiasing", antialiasing, 5, 0},', ADAPTER)
        self.assertIn('{"Texture filtering (GPU)", L"texture_filter", texture_filters, 3, 0},', ADAPTER)
        self.assertIn('static const char *const msaa_values[] = {"1x", "2x", "4x", "8x", "1x"};', ADAPTER)
        self.assertIn('static const char *const texture_filter_values[] = {"nearest", "bilinear", "3-point"};', ADAPTER)
        # Supersampling as on the N64: drawn at twice the resolution, the frames reduced by two; never Beetle's (down to 1x)
        self.assertIn('rr_psx_option(s, "internal_resolution", resolution_values[resolution + supersampled]);', ADAPTER)
        self.assertIn('rr_psx_option(s, "super_sampling", "disabled");', ADAPTER)
        self.assertIn('rr_psx_set_halve(s, supersampled);', ADAPTER)
        session = (ROOT / 'native/psx_machine/psx_session.c').read_text(encoding='utf-8')
        self.assertIn('const unsigned red = (p[r] + p[4 + r] + q[r] + q[4 + r] + 2) >> 2;', session)
        for upscaler in ('"xBR"', '"SABR"', '"JINC2"', 'adaptive_smoothing', 'mdec_yuv', 'replace_textures'):
            self.assertNotIn(upscaler, ADAPTER)


    def test_multisampling_changed_in_play_reopens_the_session_with_its_options(self):
        # Beetle's in-place rebuild kept the old sample count's programs: half the picture broke (the owner's report, 15 Nov 2026)
        self.assertIn('if (!rr_psx_host_reopen()) return;', ADAPTER)
        main = (ROOT / 'native/psx_machine/psx_main.c').read_text(encoding='utf-8')
        self.assertIn('int rr_psx_host_reopen(void) { return session ? reopen_session() : 0; }', main)
        self.assertIn('(const char (*)[2][64])carried, carried_count};', main)
        session = (ROOT / 'native/psx_machine/psx_session.c').read_text(encoding='utf-8')
        self.assertIn('for (int i = 0; game->options && i < game->option_count; ++i)', session)

    def test_multiplayer_delay_tier(self):
        # 17 Nov 2026: a digest without VRAM, a blank card; what changes the run is the host's (the owner: « il faut que ça soit
        # l'hôte qui les synchronise »): PGXP, its textures and the CPU's resolution; never forced off.
        self.assertIn('.digest = digest, .side_effects = side_effects, .session_begin = session_begin, .session_option = session_option,',
                      ADAPTER)
        self.assertNotIn('.snap_save', ADAPTER)   # the delay tier: no in-process snapshot
        self.assertIn('.session_options = rr_psx_session_values,', ADAPTER)   # session ABI 6: the host's values in HELLO
        for key in ('"pgxp"', '"pgxp_texture"', '"cpu_resolution"', '"renderer"'):
            self.assertIn(f'!strcmp(key, {key})', ADAPTER)
        self.assertIn('if (in_match && run_row(option)) return host_value[option] >= 0 ? host_value[option] : gfx_options[option].def;',
                      ADAPTER)
        self.assertIn('if (in_match && !card) resolution = host_cpu_resolution;', ADAPTER)
        self.assertIn('rrhk_notice(rr_tr("Set by the host in multiplayer"), 4000);', ADAPTER)
        self.assertNotIn('PGXP off in multiplayer', ADAPTER)
        self.assertNotIn('axes[p][i] = 0', ADAPTER)   # the session carries the sticks (rrhk_pad_axes answers them)
        self.assertIn('if (players && in_match) { rrhk_notice(rr_tr("Not during a multiplayer game"), 4000); return false; }', ADAPTER)
        session = (ROOT / 'native/psx_machine/psx_session.c').read_text(encoding='utf-8')
        body = session[session.index('uint64_t rr_psx_digest(const RrPsxSession *s) {'):]
        body = body[:body.index('\n}\n')]
        order = [body.index(part) for part in ('rr_psx_cpu_registers(cpu);', 'RETRO_MEMORY_SYSTEM_RAM', 'ScratchRAM->data8',
                                               'rr_psx_spu_ram()', 'RETRO_MEMORY_SAVE_RAM')]
        self.assertEqual(order, sorted(order))
        self.assertNotIn('vram', body.lower().replace('no vram', ''))
        main = (ROOT / 'native/psx_machine/psx_main.c').read_text(encoding='utf-8')
        match = main[main.index('void rr_psx_host_match(void) {'):]
        self.assertIn('card_path[0] = 0;', match[:match.index('\n}\n')])   # the player's card is never read again nor written
        self.assertIn('if (!rr_feedback_enabled() || !effects_allowed) return;', main)
        beetle = (ROOT / 'retrorecomp/psx_beetle.py').read_text(encoding='utf-8')
        self.assertIn("'const uint16_t *rr_psx_spu_ram(void) { return SPURAM; }\\n'", beetle)


if __name__ == '__main__':
    unittest.main()
