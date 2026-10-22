/* Host-only extra sprite units (F5, off by default): objects 9-64 in range of
 * a scanline are shown where none of the eight original units is opaque.
 * Display only: secondary OAM, overflow, sprite-0 hit, OAM, the PPU bus and
 * mapper counters/latches are unchanged; patterns are read through the mapped
 * CHR window without a bus fetch. Prepared at dot 320 for the next scanline,
 * after the original units were loaded. MMC5 keeps the original limit. */
static struct {
    uint8_t enabled, count;
    uint8_t lo[56], hi[56], attr[56], x[56];
} rr_xs;

void rr_nes_extra_sprites(bool enabled)
{
    rr_xs.enabled = enabled;
    rr_xs.count = 0;
}

static uint8_t rr_xs_chr(uint16_t a)
{
    unsigned page = (a >> 10) & 7;
    if (hw_cart.chr_ciram & (1u << page)) return ppu.ciram[(hw_cart.chr_off[page] | (a & 0x3FF)) & 0x7FF];
    if (!hw_cart.chr || !hw_cart.chr_len) return 0;
    uint32_t index = hw_cart_chr_index(a);
    return index < hw_cart.chr_len ? hw_cart.chr[index] : 0;
}

static void rr_xs_prepare(void)
{
    rr_xs.count = 0;
    if (!rr_xs.enabled || !eval_rendering() || ppu.scanline >= 239 || hw_cart.mapper == 5) return;
    unsigned height = ppu.sprite16 ? 16 : 8, seen = 0;
    for (unsigned n = 0; n < 64 && rr_xs.count < 56; n++) {
        const uint8_t *o = &ppu.oam[n * 4];
        unsigned row = (uint8_t)((ppu.scanline & 0xFF) - o[0]);
        if (row >= height || ++seen <= 8) continue;
        unsigned r = (o[2] & 0x80) ? height - 1 - row : row;
        uint16_t a = ppu.sprite16
            ? (uint16_t)(((o[1] & 1) ? 0x1000 : 0) | (((o[1] & 0xFE) + (r >> 3)) << 4) | (r & 7))
            : (uint16_t)((ppu.sprite_table ? 0x1000 : 0) | (o[1] << 4) | r);
        uint8_t lo = rr_xs_chr(a), hi = rr_xs_chr((uint16_t)(a | 8));
        if (!(lo | hi)) continue;
        if (o[2] & 0x40) { lo = flip_bits(lo); hi = flip_bits(hi); }
        unsigned k = rr_xs.count++;
        rr_xs.lo[k] = lo; rr_xs.hi[k] = hi; rr_xs.attr[k] = o[2]; rr_xs.x[k] = o[3];
    }
}

/* Only reached when no original unit is opaque on this dot. The first opaque
 * extra object decides, like the original priority between units. */
static void rr_xs_pixel(uint8_t *color, uint8_t *pal)
{
    if (!ppu.show_spr || (ppu.dot <= 8 && !ppu.show_spr8)) return;
    unsigned x = ppu.dot - 1u;
    for (unsigned k = 0; k < rr_xs.count; k++) {
        unsigned o = x - rr_xs.x[k];
        if (o >= 8) continue;
        uint8_t sc = (uint8_t)(((rr_xs.lo[k] >> (7 - o)) & 1) | (((rr_xs.hi[k] >> (7 - o)) & 1) << 1));
        if (!sc) continue;
        if (*color == 0 || !(rr_xs.attr[k] & 0x20)) { *color = sc; *pal = (uint8_t)((rr_xs.attr[k] & 3) | 4); }
        return;
    }
}
