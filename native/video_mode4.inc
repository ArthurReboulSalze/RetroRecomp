/* Original mode-4 raster renderer. 192-line display on NTSC/PAL; scanline precision.
 * Pixel-clock CRAM dots and VRAM-fetch contention are outside this model.
 * Register/port/timing core remains in the pinned upstream local adaptation.
 */
static uint32_t raster_buffers[2][SMS_SCREEN_W * SMS_SCREEN_H];
static int raster_work, raster_complete, raster_hscroll, raster_vscroll;
static int raster_all_masked, raster_complete_masked, frame_left_border;
int g_vdp_force_display;

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

static void mode4_line(uint32_t *pixels, int y, int hs, int vs, bool status) {
    uint8_t r0 = g_vdp.reg[0], r1 = g_vdp.reg[1];
    uint32_t palette[32];
    for (int i = 0; i < 32; ++i) palette[i] = mode4_color(i);
    uint32_t backdrop = palette[16 + (g_vdp.reg[7] & 15)];
    if (!(r1 & 0x40) && !g_vdp_force_display) {
        for (int x = 0; x < SMS_SCREEN_W; ++x) pixels[x] = backdrop;
        return;
    }
    uint8_t priority[SMS_SCREEN_W], sprite_seen[SMS_SCREEN_W] = {0};
    int table = (g_vdp.reg[2] & 14) << 10;
    if ((r0 & 0x40) && y < 16) hs = 0;
    for (int x = 0; x < SMS_SCREEN_W; ++x) {
        int bx = (x - hs) & 255;
        int by = (y + ((r0 & 0x80) && x >= 192 ? 0 : vs)) % 224;
        int address = (table + ((by >> 3) * 32 + (bx >> 3)) * 2) & 0x3FFF;
        int entry = g_vdp.vram[address] | (g_vdp.vram[address + 1] << 8);
        int px = bx & 7, py = by & 7;
        if (entry & 0x200) px = 7 - px;
        if (entry & 0x400) py = 7 - py;
        int color = mode4_pattern(entry & 511, px, py);
        pixels[x] = palette[((entry & 0x800) ? 16 : 0) + color];
        priority[x] = (entry & 0x1000) && color != 0;
    }
    int sat = (g_vdp.reg[5] & 0x7E) << 7;
    int zoom = (r1 & 1) ? 2 : 1;
    int height = ((r1 & 2) ? 16 : 8) * zoom;
    int count = 0;
    for (int i = 0; i < 64; ++i) {
        int raw_y = g_vdp.vram[(sat + i) & 0x3FFF];
        if (raw_y == 0xD0) break;
        int row = (y - ((raw_y + 1) & 255)) & 255;
        if (row >= height) continue;
        if (++count > 8) {
            if (status) g_vdp.status |= 0x40;
            break;
        }
        int sx = g_vdp.vram[(sat + 128 + i * 2) & 0x3FFF] - ((r0 & 8) ? 8 : 0);
        int tile = g_vdp.vram[(sat + 129 + i * 2) & 0x3FFF];
        if (r1 & 2) tile &= 254;
        if (g_vdp.reg[6] & 4) tile |= 256;
        row /= zoom;
        tile += row >> 3;
        for (int rx = 0; rx < 8 * zoom; ++rx) {
            int x = sx + rx;
            if (x < 0 || x >= SMS_SCREEN_W) continue;
            int color = mode4_pattern(tile, rx / zoom, row & 7);
            if (!color) continue;
            if (sprite_seen[x]) {
                if (status) g_vdp.status |= 0x20;
                continue; /* The first nontransparent sprite wins. */
            }
            sprite_seen[x] = 1;
            if (!priority[x]) pixels[x] = palette[16 + color];
        }
    }
    /* Blanking is the final pixel mux, after both background and sprites. */
    if ((r0 & 0x24) == 0x24)
        for (int x = 0; x < 8; ++x) pixels[x] = backdrop;
}

void smsrecomp_video_reset(void) {
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
        raster_work = work; raster_complete = complete; raster_hscroll = hs; raster_vscroll = vs;
        raster_all_masked = masked; raster_complete_masked = complete_masked; frame_left_border = border;
    }
}
