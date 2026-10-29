/* Previous scalar presentation renderer retained as a differential oracle. */
static void mode4_line_reference(uint32_t *pixels, int y, int hs, int vs, bool status) {
    uint8_t r0 = g_vdp.reg[0], r1 = g_vdp.reg[1];
    uint32_t palette[32];
    for (int i = 0; i < 32; ++i) palette[i] = mode4_color(i);
    uint32_t backdrop = palette[16 + (g_vdp.reg[7] & 15)];
    if (!(r1 & 0x40) && !g_vdp_force_display) {
        for (int x = 0; x < SMS_SCREEN_W; ++x) pixels[x] = backdrop;
        return;
    }
    uint8_t priority[SMS_SCREEN_W], sprite_seen[SMS_SCREEN_W] = {0};
    uint8_t hardware_seen[SMS_SCREEN_W] = {0};
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
    int reverse_priority = sprite_tracking_reverse_valid(sat);
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
            if (!reduce_sprite_flicker) break;
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
