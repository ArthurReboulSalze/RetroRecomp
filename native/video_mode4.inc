/* Original mode-4 raster renderer. 192-line display on NTSC/PAL; scanline precision.
 * Pixel-clock CRAM dots and VRAM-fetch contention are outside this model.
 * Register/port/timing core remains in the pinned upstream local adaptation.
 */
#include <stdlib.h>
#include "planar_rows.h"
static uint32_t raster_buffers[2][SMS_SCREEN_W * SMS_SCREEN_H];
static int raster_work, raster_complete, raster_hscroll, raster_vscroll;
static int raster_all_masked, raster_complete_masked, frame_left_border;
int g_vdp_force_display;
static int reduce_sprite_flicker;

/* Host-only tracking of rapidly reversing SAT lists. Some games reverse the
 * entire list to distribute hardware sprite dropouts. Removing the eight-sprite
 * limit alone still alternates which character is in front. Recognize an
 * unambiguous identities in at least 75% of both lists, with 95% of their pair
 * priorities reversed, twice before stabilizing it. Animation may add/remove
 * or rearrange a few pieces; never reuse old pixels. */
typedef struct { int x, y, tile; } Mode4SpriteIdentity;
static Mode4SpriteIdentity sprite_previous[64];
static int sprite_previous_count, sprite_orientation, sprite_reverse_streak;
static int sprite_reverse_age, sprite_stable_reverse, sprite_tracking_mode;
static int sprite_tracking_sat;
static uint8_t sprite_tracking_attributes[192];

static void sprite_tracking_reset(void) {
    sprite_previous_count = sprite_orientation = sprite_reverse_streak = 0;
    sprite_reverse_age = sprite_stable_reverse = 0;
    sprite_tracking_mode = -1;
}

void smsrecomp_video_set_sprite_flicker_reduction(int enabled) {
    if (reduce_sprite_flicker != (enabled != 0)) sprite_tracking_reset();
    reduce_sprite_flicker = enabled != 0;
}

static void sprite_tracking_begin_frame(void) {
    if (!reduce_sprite_flicker || g_vdp.is_gg || !(g_vdp.reg[1] & 0x40)) {
        sprite_tracking_reset();
        return;
    }
    int sat = (g_vdp.reg[5] & 0x7E) << 7;
    int mode = (g_vdp.reg[0] & 8) | (g_vdp.reg[1] & 3) | ((g_vdp.reg[6] & 4) << 4);
    int zoom = (g_vdp.reg[1] & 1) ? 2 : 1;
    int height = ((g_vdp.reg[1] & 2) ? 16 : 8) * zoom;
    Mode4SpriteIdentity current[64];
    int count = 0;
    for (int i = 0; i < 64; ++i) {
        int raw_y = g_vdp.vram[sat + i];
        if (raw_y == 0xD0) break;
        int sy = raw_y + 1 - (raw_y >= 240 ? 256 : 0);
        if (sy >= SMS_SCREEN_H || sy + height <= 0) continue;
        int tile = g_vdp.vram[sat + 129 + i * 2];
        if (g_vdp.reg[1] & 2) tile &= 254;
        if (g_vdp.reg[6] & 4) tile |= 256;
        current[count++] = (Mode4SpriteIdentity){
            g_vdp.vram[sat + 128 + i * 2] - ((g_vdp.reg[0] & 8) ? 8 : 0), sy, tile};
    }
    int ascending_pairs = 0, descending_pairs = 0;
    int used[64] = {0}, order[64], matches = 0;
    int matched = count >= 8 && sprite_previous_count >= 8 && mode == sprite_tracking_mode
        && sat == sprite_tracking_sat;
    for (int i = 0; matched && i < count; ++i) {
        int best = -1, distance = 65, ambiguous = 0;
        for (int j = 0; j < sprite_previous_count; ++j) {
            if (current[i].tile != sprite_previous[j].tile) continue;
            int dx = abs(current[i].x - sprite_previous[j].x);
            int dy = abs(current[i].y - sprite_previous[j].y);
            if (dx > 32 || dy > 32) continue;
            int d = dx + dy;
            if (d < distance) { best = j; distance = d; ambiguous = 0; }
            else if (d == distance) ambiguous = 1;
        }
        if (best < 0) continue;
        if (ambiguous || used[best]) { matched = 0; break; }
        used[best] = 1;
        for (int j = 0; j < matches; ++j) {
            ascending_pairs += best > order[j];
            descending_pairs += best < order[j];
        }
        order[matches++] = best;
    }
    matched &= matches >= 8 && matches * 4 >= count * 3 && matches * 4 >= sprite_previous_count * 3;
    int pairs = ascending_pairs + descending_pairs;
    int ascending = pairs && ascending_pairs * 100 >= pairs * 95;
    int descending = pairs && descending_pairs * 100 >= pairs * 95;
    if (!matched || (!ascending && !descending)) {
        sprite_orientation = sprite_reverse_streak = sprite_reverse_age = 0;
    } else {
        ++sprite_reverse_age;
        if (descending) {
            sprite_orientation ^= 1;
            if (sprite_reverse_age > 4) sprite_reverse_streak = 0;
            if (sprite_reverse_streak < 2) ++sprite_reverse_streak;
            sprite_reverse_age = 0;
        } else if (sprite_reverse_age > 8) {
            /* A lasting priority change is no longer a flickering cycle. */
            sprite_orientation = sprite_reverse_streak = 0;
        }
    }
    sprite_stable_reverse = sprite_reverse_streak >= 2 && sprite_orientation;
    memcpy(sprite_previous, current, count * sizeof current[0]);
    sprite_previous_count = count; sprite_tracking_mode = mode; sprite_tracking_sat = sat;
    memcpy(sprite_tracking_attributes, g_vdp.vram + sat, 64);
    memcpy(sprite_tracking_attributes + 64, g_vdp.vram + sat + 128, 128);
}

static int sprite_tracking_reverse_valid(int sat) {
    /* A raster SAT rewrite must immediately use the current cartridge order. */
    int mode = (g_vdp.reg[0] & 8) | (g_vdp.reg[1] & 3) | ((g_vdp.reg[6] & 4) << 4);
    return sprite_stable_reverse && reduce_sprite_flicker && !g_vdp.is_gg
        && sat == sprite_tracking_sat && mode == sprite_tracking_mode
        && !memcmp(sprite_tracking_attributes, g_vdp.vram + sat, 64)
        && !memcmp(sprite_tracking_attributes + 64, g_vdp.vram + sat + 128, 128);
}

int smsrecomp_frame_left_border(void) { return frame_left_border; }

static uint32_t mode4_color(int index) {
    if (g_vdp.is_gg) {
        uint8_t lo = g_vdp.cram[(index * 2) & 63];
        uint8_t hi = g_vdp.cram[(index * 2 + 1) & 63];
        return 0xFF000000u | ((lo & 15) * 17u << 16)
             | ((lo >> 4) * 17u << 8) | ((hi & 15) * 17u);
    }
    uint8_t color = g_vdp.cram[index & 31];
    return 0xFF000000u | ((color & 3) * 85u << 16)
         | (((color >> 2) & 3) * 85u << 8) | (((color >> 4) & 3) * 85u);
}

static int mode4_pattern(int tile, int x, int y) {
    int address = (tile * 32 + y * 4) & 0x3FFF;
    int bit = 7 - x;
    return ((g_vdp.vram[address] >> bit) & 1)
         | (((g_vdp.vram[address + 1] >> bit) & 1) << 1)
         | (((g_vdp.vram[address + 2] >> bit) & 1) << 2)
         | (((g_vdp.vram[address + 3] >> bit) & 1) << 3);
}

/* The 32 host colors, rebuilt only when CRAM or the palette format changed:
 * every line still reads the current CRAM bytes. */
static uint32_t mode4_palette[32];
static uint8_t mode4_palette_cram[64];
static int mode4_palette_gg = -1;

static const uint32_t *mode4_current_palette(void) {
    size_t size = g_vdp.is_gg ? 64 : 32;
    if (mode4_palette_gg != (int)g_vdp.is_gg || memcmp(mode4_palette_cram, g_vdp.cram, size)) {
        for (int i = 0; i < 32; ++i) mode4_palette[i] = mode4_color(i);
        memcpy(mode4_palette_cram, g_vdp.cram, size);
        mode4_palette_gg = g_vdp.is_gg;
    }
    return mode4_palette;
}

/* One bitplane byte spread to eight byte lanes: in [1], lane n holds the bit
 * of tile column n (bit 7 - n); in [0], horizontally flipped, bit n. */
static uint64_t mode4_lanes[2][256];

static void mode4_init_lanes(void) {
    if (mode4_lanes[1][0x80]) return;
    for (unsigned b = 0; b < 256; ++b) {
        unsigned r = 0;
        for (unsigned bit = 0; bit < 8; ++bit) r |= ((b >> bit) & 1u) << (7 - bit);
        mode4_lanes[0][b] = rr_plane_lanes((uint8_t)b);
        mode4_lanes[1][b] = rr_plane_lanes((uint8_t)r);
    }
}

static void mode4_line(uint32_t *pixels, int y, int hs, int vs, bool status) {
    uint8_t r0 = g_vdp.reg[0], r1 = g_vdp.reg[1];
    mode4_init_lanes();
    const uint32_t *palette = mode4_current_palette();
    uint32_t backdrop = palette[16 + (g_vdp.reg[7] & 15)];
    if (!(r1 & 0x40) && !g_vdp_force_display) {
        for (int x = 0; x < SMS_SCREEN_W; ++x) pixels[x] = backdrop;
        return;
    }
    uint8_t priority[SMS_SCREEN_W], sprite_seen[SMS_SCREEN_W];
    uint8_t hardware_seen[SMS_SCREEN_W];
    int table = (g_vdp.reg[2] & 14) << 10;
    if ((r0 & 0x40) && y < 16) hs = 0;
    /* Columns 24-31 ignore the vertical scroll when it is locked. */
    int by_scrolled = (y + vs) % 224, by_locked = y % 224;
    for (int x = 0; x < SMS_SCREEN_W;) {
        int bx = (x - hs) & 255;
        int by = (r0 & 0x80) && x >= 192 ? by_locked : by_scrolled;
        int address = (table + ((by >> 3) * 32 + (bx >> 3)) * 2) & 0x3FFF;
        int entry = g_vdp.vram[address] | (g_vdp.vram[address + 1] << 8);
        int py = by & 7;
        if (entry & 0x400) py = 7 - py;
        int base = ((entry & 511) * 32 + py * 4) & 0x3fff;
        int count = 8 - (bx & 7);
        if (count > SMS_SCREEN_W - x) count = SMS_SCREEN_W - x;
        /* Column-scroll lock can split a partially scrolled tile. */
        if ((r0 & 0x80) && x < 192 && x + count > 192) count = 192 - x;
        const uint32_t *tile_palette = palette + ((entry & 0x800) ? 16 : 0);
        if (count == 8) {
            /* A whole tile: byte n is the color of pixel x + n. */
            const uint64_t *lanes = mode4_lanes[(entry & 0x200) ? 0 : 1];
            uint64_t ordered = lanes[g_vdp.vram[base]] | (lanes[g_vdp.vram[base + 1]] << 1) |
                               (lanes[g_vdp.vram[base + 2]] << 2) | (lanes[g_vdp.vram[base + 3]] << 3);
            for (int n = 0; n < 8; ++n) pixels[x + n] = tile_palette[(ordered >> (n * 8)) & 15];
            uint64_t opaque = (ordered | (ordered >> 1) | (ordered >> 2) | (ordered >> 3)) &
                              UINT64_C(0x0101010101010101);
            if (!(entry & 0x1000)) opaque = 0;
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
            for (int n = 0; n < 8; ++n) priority[x + n] = (uint8_t)((opaque >> (n * 8)) & 1);
#else
            memcpy(priority + x, &opaque, 8);
#endif
            x += 8;
            continue;
        }
        uint64_t colors=rr_planar_pair((uint16_t)(g_vdp.vram[base]|g_vdp.vram[base+1]<<8)) |
            (rr_planar_pair((uint16_t)(g_vdp.vram[base+2]|g_vdp.vram[base+3]<<8))<<2);
        for(int n=0;n<count;++n) {
            unsigned col=(unsigned)((bx+n)&7);
            int color=(int)rr_planar_pixel(colors,(entry&0x200)?col:7-col);
            pixels[x+n]=tile_palette[color];
            priority[x+n]=(entry&0x1000) && color!=0;
        }
        x+=count;
    }
    bool seen_cleared = false;
    int sat = (g_vdp.reg[5] & 0x7E) << 7;
    int reverse_priority = sprite_tracking_reverse_valid(sat);
    int zoom = (r1 & 1) ? 2 : 1;
    int height = ((r1 & 2) ? 16 : 8) * zoom;
    int count = 0;
    for (int i = 0; i < 64; ++i) {
        int raw_y = g_vdp.vram[(sat + i) & 0x3FFF];
        if (raw_y == 0xD0) break;
        int row = (y - ((raw_y + 1) & 255)) & 255;
        if (row >= height) continue;
        if (!seen_cleared) {
            memset(sprite_seen, 0, sizeof sprite_seen);
            memset(hardware_seen, 0, sizeof hardware_seen);
            seen_cleared = true;
        }
        if (++count > 8) {
            if (status) g_vdp.status |= 0x40;
            if (!reduce_sprite_flicker || g_vdp.is_gg) break;
        }
        int sx = g_vdp.vram[(sat + 128 + i * 2) & 0x3FFF] - ((r0 & 8) ? 8 : 0);
        int tile = g_vdp.vram[(sat + 129 + i * 2) & 0x3FFF];
        if (r1 & 2) tile &= 254;
        if (g_vdp.reg[6] & 4) tile |= 256;
        row /= zoom;
        tile += row >> 3;
        int base=(tile*32+(row&7)*4)&0x3fff;
        uint64_t colors=rr_planar_pair((uint16_t)(g_vdp.vram[base]|g_vdp.vram[base+1]<<8)) |
            (rr_planar_pair((uint16_t)(g_vdp.vram[base+2]|g_vdp.vram[base+3]<<8))<<2);
        for (int rx = 0; rx < 8 * zoom; ++rx) {
            int x = sx + rx;
            if (x < 0 || x >= SMS_SCREEN_W) continue;
            int color = (int)rr_planar_pixel(colors,7u-(unsigned)(rx >> (zoom==2)));
            if (!color) continue;
            /* Guest collisions use the original first eight SAT entries,
             * independently of the host's unlimited/stabilized presentation. */
            if (status && count <= 8) {
                if (hardware_seen[x] && !((r0 & 0x20) && x < 8))
                    g_vdp.status |= 0x20;
                hardware_seen[x] = 1;
            }
            if (sprite_seen[x] && !reverse_priority) continue;
            sprite_seen[x] = 1;
            if (!priority[x]) pixels[x] = palette[16 + color];
        }
    }
    /* Blanking is the final pixel mux, after both background and sprites. */
    if ((r0 & 0x24) == 0x24)
        for (int x = 0; x < 8; ++x) pixels[x] = backdrop;
}

void smsrecomp_video_reset(void) {
    sprite_tracking_reset();
    raster_work = 0; raster_complete = 1;
    raster_hscroll = raster_vscroll = 0;
    raster_all_masked = 1; raster_complete_masked = frame_left_border = 0;
    for (int b = 0; b < 2; ++b)
        for (int i = 0; i < SMS_SCREEN_W * SMS_SCREEN_H; ++i)
            raster_buffers[b][i] = 0xFF000000u;
}

void smsrecomp_video_begin_line(int line) {
    raster_hscroll = g_vdp.reg[8];
    if (line == 0) {
        raster_vscroll = g_vdp.reg[9];
        raster_all_masked = 1;
    }
}

void smsrecomp_video_end_line(int line) {
    if (line < 0 || line >= SMS_SCREEN_H) return;
    if (line == 0) sprite_tracking_begin_frame();
    mode4_line(raster_buffers[raster_work] + line * SMS_SCREEN_W,
               line, raster_hscroll, raster_vscroll, true);
    raster_all_masked &= !g_vdp.is_gg && (g_vdp.reg[0] & 0x24) == 0x24;
    if (line == SMS_SCREEN_H - 1) {
        raster_complete = raster_work;
        raster_work ^= 1;
        raster_complete_masked = raster_all_masked;
    }
}

void smsrecomp_video_present(uint32_t *fb) {
    memcpy(fb, raster_buffers[raster_complete], sizeof raster_buffers[0]);
    frame_left_border = raster_complete_masked ? 8 : 0;
}

uint64_t smsrecomp_video_hash(void) {
    const unsigned char *bytes = (const unsigned char *)raster_buffers[raster_complete];
    uint64_t hash = 1469598103934665603ULL;
    for (unsigned i = 0; i < sizeof raster_buffers[0]; ++i)
        hash = (hash ^ bytes[i]) * 1099511628211ULL;
    return hash;
}

/* Snapshot helper for authored chip fixtures, never used for live frames.
 * It does not mutate status, raster buffers, or the next frame's latches. */
void vdp_render_frame(uint32_t *fb) {
    for (int y = 0; y < SMS_SCREEN_H; ++y)
        mode4_line(fb + y * SMS_SCREEN_W, y, g_vdp.reg[8], g_vdp.reg[9], false);
    frame_left_border = !g_vdp.is_gg && (g_vdp.reg[0] & 0x24) == 0x24 ? 8 : 0;
}

#include "state_io.h"
void smsrecomp_video_state(RetroStateIO *io) {
    int work = (int)rr_state_word(io, raster_work, 1, 1);
    int complete = (int)rr_state_word(io, raster_complete, 1, 1);
    int hs = (int)rr_state_word(io, raster_hscroll, 1, 255);
    int vs = (int)rr_state_word(io, raster_vscroll, 1, 255);
    int masked = (int)rr_state_word(io, raster_all_masked, 1, 1);
    int complete_masked = (int)rr_state_word(io, raster_complete_masked, 1, 1);
    int border = (int)rr_state_word(io, frame_left_border, 1, 8);
    if (work == complete || (border != 0 && border != 8)) io->ok = false;
    for (int b = 0; b < 2; ++b) for (int i = 0; i < SMS_SCREEN_W * SMS_SCREEN_H; ++i) {
        uint32_t pixel = (uint32_t)rr_state_word(io, raster_buffers[b][i], 4, UINT32_MAX);
        if (io->mode == RR_STATE_APPLY && io->ok) raster_buffers[b][i] = pixel;
    }
    if (io->mode == RR_STATE_APPLY && io->ok) {
        /* Presentation history is intentionally not cartridge state. Relearn
         * on current frames after load, without changing the save format. */
        sprite_tracking_reset();
        raster_work = work; raster_complete = complete; raster_hscroll = hs; raster_vscroll = vs;
        raster_all_masked = masked; raster_complete_masked = complete_masked; frame_left_border = border;
    }
}
