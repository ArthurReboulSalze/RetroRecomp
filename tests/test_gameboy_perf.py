"""Game Boy frame cost (1.9.0): the line-with-sprites runs of the PPU (native/gb_ppu_object_span.h, retrorecomp/gameboy_hardware.adapt_ppu_object_spans)
and the sound ring of the adapter. No ROM, no compiler. What the text promises; the output is proved by the A/B conversion (per-frame picture, sound, RAM and
program counter identical to the unpatched runtime on a panel of games) and by tools/gameboy_machine_selftest.py."""
import unittest

from retrorecomp import gameboy_hardware as hardware
from retrorecomp.paths import ASSETS

SPAN = (ASSETS / 'native/gb_ppu_object_span.h').read_text(encoding='utf-8')
ADAPTER = (ASSETS / 'native/hostkit/adapters/rrhk_gb.inc').read_text(encoding='utf-8')

PPU = '''static uint32_t ppu_draw_stable_span(GBPPU* ppu,
                                     GBContext* ctx,
                                     uint32_t available_dots) {
    if (available_dots < 2u ||
        ppu->draw_startup != 0u ||
        ppu->draw_stall != 0u ||
        ppu->visible_mode != PPU_MODE_DRAW ||
        ppu->visible_sprite_count != 0u ||
        ctx->ppu_trace_file != NULL ||
        ppu->draw_x + 1u >= GB_SCREEN_WIDTH) {
        return 0;
    }
    if (span > until_tile_boundary) {
        span = until_tile_boundary;
    }
    if (span < 2u) {
        return 0;
    }

    ppu_render_background_span(ppu, ctx, span);
    ppu->draw_x = (uint16_t)(ppu->draw_x + span);
}
'''


class PpuPatchTests(unittest.TestCase):
    def test_a_line_with_sprites_runs_on_the_dmg_hardware_only(self):
        out = hardware.adapt_ppu_object_spans(PPU)
        self.assertIn('(ppu->visible_sprite_count != 0u && ctx->config.model == GB_MODEL_CGB) ||', out)
        self.assertNotIn('        ppu->visible_sprite_count != 0u ||\n', out)
        self.assertIn('#include "gb_ppu_object_span.h"\n\nstatic uint32_t ppu_draw_stable_span(', out)

    def test_a_run_stops_before_the_dot_where_a_sprite_fetch_starts(self):
        out = hardware.adapt_ppu_object_spans(PPU)
        loop = out[out.index('for (uint8_t slot = 0;'):out.index('if (span < 2u)')]
        self.assertIn('fetched_sprite_mask', loop)                       # a sprite already fetched starts nothing
        self.assertIn('trigger_x == (int)ppu->draw_x) return 0;', loop)   # the dot of the fetch stays with the dot path
        self.assertIn('span = (uint32_t)(trigger_x - (int)ppu->draw_x)', loop)
        self.assertLess(out.index('for (uint8_t slot = 0;'), out.index('ppu_render_object_span(ppu, ctx, span)'))

    def test_a_line_without_sprites_keeps_the_background_run(self):
        out = hardware.adapt_ppu_object_spans(PPU)
        self.assertIn('} else {\n        ppu_render_background_span(ppu, ctx, span);\n    }', out)

    def test_a_changed_upstream_is_refused(self):
        with self.assertRaises(Exception):
            hardware.adapt_ppu_object_spans('int x;\n')
        with self.assertRaises(Exception):
            hardware.adapt_ppu_object_spans(hardware.adapt_ppu_object_spans(PPU))


class ObjectSpanTextTests(unittest.TestCase):
    def test_the_pixels_follow_the_dot_path_rules(self):
        self.assertIn('LCDC_OBJ_ENABLE', SPAN)                                      # no sprite with the objects off
        self.assertIn('sprite->screen_x < chosen_x', SPAN)                          # DMG priority: further left, then lower OAM index
        self.assertIn('sprite->oam_index < chosen_index', SPAN)
        self.assertIn('bg_raw != 0 && (obj_flags & OAM_PRIORITY)', SPAN)            # a sprite behind a non-zero background pixel
        self.assertIn('resolve_obj_color(', SPAN)                                   # the palettes through the same functions
        self.assertIn('resolve_bg_color(', SPAN)
        self.assertNotIn('cgb_mode', SPAN.replace('DMG hardware only', ''))         # no colour hardware in the run


class SoundRingTextTests(unittest.TestCase):
    def test_the_sound_is_a_preallocated_ring(self):
        self.assertIn('static int16_t g_rr_pcm_ring[RR_GB_PCM_CAPACITY];', ADAPTER)
        self.assertNotIn('std::vector<int16_t> g_rr_pcm', ADAPTER)
        self.assertNotIn('g_rr_pcm.', ADAPTER)                                     # no push_back, erase or clear on a vector any more
        self.assertIn('g_rr_pcm_count + 2 > RR_GB_PCM_CAPACITY', ADAPTER)           # the same limit as before: 16,384 frames


if __name__ == '__main__':
    unittest.main()
