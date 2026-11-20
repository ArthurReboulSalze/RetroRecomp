/* The dot-accurate pixel transfer of the pinned PPU (runtime/src/ppu.c), batched for a line that has sprites. Included by ppu.c, right before
 * ppu_draw_stable_span (retrorecomp/gameboy_hardware.py: adapt_ppu_object_spans). Original RetroRecomp code: MIT.
 *
 * The pinned runtime already draws a sprite-free run of dots in one go (ppu_draw_stable_span: up to the next tile boundary, the window or the end of
 * the line) and falls back to one dot at a time on every line that has a sprite: ppu_draw_one_dot, with the background fetched again for each pixel
 * and the sprites of the line scanned again for each pixel. This does the same work for a run of dots on a line with sprites, DMG hardware only
 * (the colour hardware keeps the dot path): the caller proves that no sprite fetch starts inside the run (so no stall, no change of the mask of
 * fetched sprites), no window starts, no mode or tile boundary falls inside it; a tick of the CPU does not change the registers or the memory
 * the pixels read, so they are the same for every dot of the run, as in ppu_draw_stable_span. Each pixel is the one ppu_render_dot would have
 * given: the background pixel of the tile row (0 with the background off), the sprite chosen by ppu_fetch_object_dot (the first slot with a
 * non-zero pixel wins unless a later one is further left, or at the same x with a lower OAM index), the sprite behind the background kept
 * behind a non-zero background pixel, the palettes resolved by the same functions. */
#ifndef RR_GB_PPU_OBJECT_SPAN_H
#define RR_GB_PPU_OBJECT_SPAN_H

typedef struct {
    int screen_x;
    int oam_index;
    uint8_t lo, hi, flags;
} RrGbSpanSprite;

static void ppu_render_object_span(GBPPU* ppu, GBContext* ctx, uint32_t span) {
    uint8_t bg_lo = 0, bg_hi = 0;
    const bool bg_enabled = (ppu->lcdc & LCDC_BG_ENABLE) != 0;          /* DMG: the background may be off */
    const bool in_window = ppu->window_active_line;
    int source_x;
    int source_y;
    uint16_t tilemap_addr;
    if (in_window) {
        source_x = ppu->window_pixel_x;
        source_y = ppu->window_line;
        tilemap_addr = get_window_tilemap_addr(ppu->lcdc);
    } else {
        source_x = (ppu->draw_x + ppu->scx) & 0xFF;
        source_y = (ppu->ly + ppu->scy) & 0xFF;
        tilemap_addr = get_bg_tilemap_addr(ppu->lcdc);
    }
    if (bg_enabled) {
        const uint8_t tile_x = (uint8_t)((source_x >> 3) & 31);
        const uint8_t tile_y = (uint8_t)((source_y >> 3) & 31);
        const uint16_t map_entry = (uint16_t)(tilemap_addr + tile_y * 32u + tile_x);
        const uint8_t tile_idx = vram_read_bank(ctx, 0, map_entry);
        const uint8_t pixel_y = (uint8_t)(source_y & 7);
        const uint16_t tile_addr = get_tile_data_addr(ppu->lcdc, tile_idx, false);
        bg_lo = vram_read_bank(ctx, 0, (uint16_t)(tile_addr + pixel_y * 2u));
        bg_hi = vram_read_bank(ctx, 0, (uint16_t)(tile_addr + pixel_y * 2u + 1u));
    }

    /* The sprites of the line that can colour a pixel of the run, in slot order, with their tile row fetched once. */
    RrGbSpanSprite sprites[10];
    unsigned sprite_count = 0;
    if (ppu->lcdc & LCDC_OBJ_ENABLE) {
        for (uint8_t slot = 0; slot < ppu->visible_sprite_count; ++slot) {
            const int screen_x = (int)ppu->visible_sprite_x[slot] - 8;
            if (screen_x + 8 <= (int)ppu->draw_x || screen_x >= (int)(ppu->draw_x + span)) continue;     /* covers no pixel of the run */
            const int oam_index = ppu->visible_sprite_indices[slot];
            const size_t oam_offset = (size_t)oam_index * 4u;
            const uint8_t flags = ctx->oam[oam_offset + 3u];
            uint8_t tile = ctx->oam[oam_offset + 2u];
            int line = (int)ppu->ly - ((int)ppu->visible_sprite_y[slot] - 16);
            if (ppu->line_sprite_height == 16) tile &= 0xFE;
            if (flags & OAM_FLIP_Y) line = ppu->line_sprite_height - 1 - line;
            if (line < 0 || line >= ppu->line_sprite_height) continue;
            const uint16_t tile_addr = (uint16_t)(0x8000u + tile * 16u + line * 2u);
            sprites[sprite_count].screen_x = screen_x;
            sprites[sprite_count].oam_index = oam_index;
            sprites[sprite_count].lo = vram_read_bank(ctx, 0, tile_addr);
            sprites[sprite_count].hi = vram_read_bank(ctx, 0, (uint16_t)(tile_addr + 1u));
            sprites[sprite_count].flags = flags;
            ++sprite_count;
        }
    }

    for (uint32_t offset = 0; offset < span; ++offset) {
        const int x = (int)ppu->draw_x + (int)offset;
        const uint8_t bit = (uint8_t)(7u - (uint8_t)((source_x + (int)offset) & 7));
        const uint8_t bg_raw = bg_enabled ? (uint8_t)(((bg_lo >> bit) & 1u) | (((bg_hi >> bit) & 1u) << 1u)) : 0;

        bool present = false;
        uint8_t obj_raw = 0, obj_flags = 0;
        int chosen_x = 256, chosen_index = 256;
        for (unsigned s = 0; s < sprite_count; ++s) {
            const RrGbSpanSprite* sprite = &sprites[s];
            const int sprite_pixel = x - sprite->screen_x;
            if (sprite_pixel < 0 || sprite_pixel >= 8) continue;
            const int sbit = (sprite->flags & OAM_FLIP_X) ? sprite_pixel : (7 - sprite_pixel);
            const uint8_t raw = (uint8_t)(((sprite->lo >> sbit) & 1u) | (((sprite->hi >> sbit) & 1u) << 1u));
            if (raw == 0) continue;
            const bool wins = !present || sprite->screen_x < chosen_x ||
                              (sprite->screen_x == chosen_x && sprite->oam_index < chosen_index);   /* DMG priority */
            if (!wins) continue;
            present = true;
            obj_raw = raw;
            obj_flags = sprite->flags;
            chosen_x = sprite->screen_x;
            chosen_index = sprite->oam_index;
        }
        if (present && bg_raw != 0 && (obj_flags & OAM_PRIORITY)) present = false;      /* behind a non-zero background pixel */

        const size_t framebuffer_index = (size_t)ppu->ly * GB_SCREEN_WIDTH + (size_t)x;
        if (present) {
            const uint8_t palette = (obj_flags & OAM_PALETTE) ? 1 : 0;
            const uint8_t palette_reg = palette ? ppu->obp1 : ppu->obp0;
            ppu->framebuffer[framebuffer_index] = apply_palette(obj_raw, palette_reg);
            ppu->color_framebuffer[framebuffer_index] = resolve_obj_color(ppu, ctx, palette, obj_raw, palette_reg);
        } else {
            ppu->framebuffer[framebuffer_index] = apply_palette(bg_raw, ppu->bgp);
            ppu->color_framebuffer[framebuffer_index] = resolve_bg_color(ppu, ctx, 0, bg_raw, ppu->bgp);
        }
    }
}

#endif
