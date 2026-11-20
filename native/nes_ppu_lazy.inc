/* Adapted from the pinned NESRecomp PPU; its PolyForm Noncommercial terms
 * remain applicable. See THIRD_PARTY_NOTICES.md and licenses/nesrecomp.md.
 * Included after the dot functions of the staged hw_ppu.c.
 *
 * Deferred PPU clocking. Between register accesses the CPU sees the PPU only
 * through /NMI (vblank) and the frame-complete flag, and on some boards
 * through the cartridge: an IRQ counter watching PPU addresses, a CPU-clocked
 * device, or MMC5. Those boards and the Zapper keep the eager clock; PAL
 * defers like NTSC, its edges following the rational 16:5 phase.
 * Elsewhere every edge still runs, in order and unchanged, but late: just
 * before a register or cartridge access, the dot that can change vblank, or
 * the end of the frame. */
unsigned rr_ppu_due, rr_ppu_room = 1;
bool rr_ppu_lazy;
static bool rr_ppu_next_dot, rr_ppu_hold;

/* Edges that may wait: up to and including the next dot entering (241, 1)
 * or (pre-render, 1), or the next dot after a $2002 read that clears vblank. */
static unsigned rr_ppu_compute_room(void)
{
    if (ppu.read2002 && ppu.vblank) return rr_ppu_next_dot ? 1u : 2u;
    const unsigned frame = (RR_PRERENDER + 1u) * 341u;
    unsigned pos = ppu.scanline * 341u + ppu.dot;
    unsigned set = (241u * 341u + 1u + frame - pos) % frame;
    unsigned clear = (RR_PRERENDER * 341u + 1u + frame - pos) % frame;
    if (!set) set = frame;
    if (!clear) clear = frame;
    unsigned dots = set < clear ? set : clear;
    unsigned edges = 2u * dots - (rr_ppu_next_dot ? 1u : 0u);
    /* The odd-frame skip can remove one dot on the way. */
    return edges > 2u ? edges - 2u : 1u;
}

/* rr_ppu_steady_dot() and rr_ppu_steady_half() on a visible scanline that
 * does not end on this dot (dot 0-339 before it): render_line() holds and
 * nothing is blanked. */
HW_ALWAYS_INLINE void rr_ppu_visible_pair(void)
{
    if (ppu.dot == 256) increment_y();
    else if (ppu.dot == 257) ppu.v = (uint16_t)((ppu.v & 0x7BE0) | (ppu.t & 0x041F));
    advance_dot();
    if (!RR_NES_PAL && ppu.odd_frame && ppu.scanline == 0 && ppu.dot == 2) ppu.skipped_dot = 0;
    unsigned dot = ppu.dot;
    bool h0 = !(dot & 1);
    ppu.blnk_latch = 0;
    ppu.pal_enable = 0;
    ppu.rd = h0;
    if (RR_NES_MAPPER == 5 || RR_NES_MAPPER == 9 || RR_NES_MAPPER == 10) hw_cart_ppu_rd(h0);
    ppu.ale = !h0;
    ppu.oam_latch = ppu.oam_buffer;
    ppu.copy_v = 0;
    if (ppu.oam2_reset > 0) ppu.oam2_reset--;
    sprite_evaluation();
    if (dot == 63 || dot == 255 || dot == 339) ppu.oam2_reset = 3;
    ppu.color[3] = ppu.color[2];
    ppu.color[2] = ppu.color[1];
    ppu.color[1] = ppu.color[0];
    if (dot <= 256) {
        bg_fetch();
        compute_pixel();
        shift_sprites();
    } else if (dot >= 321 && dot <= 336) {
        bg_fetch();
    } else if (dot >= 337) {
        bg_fetch_tail();
    }
    output_pixel();
    io_bus_decay();
    hw_cart_ppu_addr(ppu.vbus);

    if (dot <= 257 || (dot >= 321 && dot <= 336)) {
        ppu.bg_lo = (uint16_t)(ppu.bg_lo << 1);
        ppu.bg_hi = (uint16_t)(ppu.bg_hi << 1 | 1);
        ppu.attr_lo = (uint16_t)(ppu.attr_lo << 1 | (ppu.attr_latch & 1));
        ppu.attr_hi = (uint16_t)(ppu.attr_hi << 1 | ((ppu.attr_latch >> 1) & 1));
    }
    if (ppu.oam2_reset > 0 && --ppu.oam2_reset == 0) {
        ppu.oam2_addr = 0;
        ppu.oam2_full = 0;
    }
    if (ppu.commit) bg_commit();
    ppu.oam_buffer = ppu.oam_buffer_in;
    half_dot_status();
    ppu.ale = 0;
    ppu.wr = 0;
}

/* Boards whose VRAM bus is plain: CIRAM nametables by mirroring, CHR reads
 * without side effects. Set with rr_ppu_lazy. */
static bool rr_ppu_plain;
static uint32_t rr_ppu_chr_wrap;

/* What a read of the VRAM bus returns with /RD low and no write, on a plain board, for a latched address (the high byte on the
 * bus and the low byte in the octal latch). */
HW_ALWAYS_INLINE uint8_t rr_ppu_fetch_at(uint16_t vbus, uint8_t latch)
{
    uint8_t value;
    if (vbus & 0x2000) {
        unsigned a10;
        if (hw_cart.info.four_screen) a10 = vbus & 0xc00;
        else switch (hw_cart.mirroring) {
        case HW_MIRROR_HORIZONTAL: a10 = (vbus & 0x800) ? 0x400 : 0; break;
        case HW_MIRROR_VERTICAL:   a10 = (vbus & 0x400) ? 0x400 : 0; break;
        case HW_MIRROR_SCREEN_B:   a10 = 0x400; break;
        default:                   a10 = 0; break;
        }
        value = ppu.ciram[(vbus & 0x300) | latch | a10];
    } else {
        unsigned addr = ((vbus & 0x3F00) | latch) & 0x1FFF;
        uint32_t index = hw_cart.chr_off[addr >> 10] | (addr & 0x3FF);
        if (rr_ppu_chr_wrap)
            index = (rr_ppu_chr_wrap & (rr_ppu_chr_wrap - 1)) ? index % rr_ppu_chr_wrap : index & (rr_ppu_chr_wrap - 1);
        value = hw_cart.chr[index];
    }
    return value;
}

/* vram_fetch() with /RD low and no write, on a plain board. */
HW_ALWAYS_INLINE uint8_t rr_ppu_plain_fetch(void)
{
    uint8_t value = rr_ppu_fetch_at(ppu.vbus, ppu.octal_latch);
    ppu.vbus = (uint16_t)((ppu.vbus & 0xFF00) | value);
    return value;
}

/* compute_pixel() when no sprite unit can output on this dot and no palette
 * corruption is pending. */
HW_ALWAYS_INLINE void rr_ppu_bg_pixel(unsigned dot)
{
    uint8_t color = 0, pal = 0;
    if (ppu.show_bg && (dot > 8 || ppu.show_bg8)) {
        unsigned fx = ppu.fine_x;
        color = (uint8_t)(((ppu.bg_lo >> (15 - fx)) & 1) | (((ppu.bg_hi >> (15 - fx)) & 1) << 1));
        pal = (uint8_t)(((ppu.attr_lo >> (7 - fx)) & 1) | (((ppu.attr_hi >> (7 - fx)) & 1) << 1));
        if (color == 0) pal = 0;
    }
    ppu.color[0] = ppu.palette[(uint8_t)(pal << 2 | color)] & 0x3F;
}

/* One steady dot and half dot of an 8-dot background tile on a visible
 * scanline, dots 1-256: step is the fetch step, (dot + 7) & 7. The caller
 * checked that no corruption latch, commit or Namco CIRAM pattern is
 * pending and that the board is plain; the fetch commits are applied here.
 * Without sprites, no unit can be opaque during the tile: the caller
 * advances the sprite counters afterwards. */
HW_ALWAYS_INLINE void rr_ppu_tile_pair(unsigned step, bool sprites, bool prefetch)
{
    advance_dot();
    if (step == 1 && !RR_NES_PAL && ppu.odd_frame && ppu.scanline == 0 && ppu.dot == 2) ppu.skipped_dot = 0;
    unsigned dot = ppu.dot;
    bool h0 = (step & 1) != 0;
    ppu.blnk_latch = 0;
    ppu.pal_enable = 0;
    ppu.rd = h0;
    ppu.ale = !h0;
    ppu.oam_latch = ppu.oam_buffer;
    ppu.copy_v = 0;
    if (ppu.oam2_reset > 0) ppu.oam2_reset--;
    if (prefetch) {
        /* sprite_evaluation() on dots 321-340, rendering, no corruption latch */
        ppu.oam_buffer_in = ppu.oam2[ppu.oam2_addr];
    } else if (dot > 64) {
        if (h0) {
            eval_objects(false);
        } else {
            /* eval_objects() on an odd dot, no corruption latch set */
            if (step == 0 && dot == 65) {
                ppu.eval_nine = 0;
                ppu.eval_odd_corrupt = 0;
                ppu.eval_wrapped = 0;
            }
            if (ppu.instant_bg || ppu.instant_spr) ppu.oam_buffer_in = ppu.oam[ppu.oam_addr];
        }
    } else if (!h0) {
        ppu.oam_buffer_in = 0xFF;
        if (dot == 1) {
            ppu.oam2_addr = 0;
            ppu.eval_tick = 0;
            ppu.eval_wrapped = 0;
        }
    } else {
        ppu.oam2[ppu.oam2_addr] = ppu.oam_buffer;
        oam2_increment();
    }
    if (step == 6 && (dot == 63 || dot == 255)) ppu.oam2_reset = 3;
    ppu.color[3] = ppu.color[2];
    ppu.color[2] = ppu.color[1];
    ppu.color[1] = ppu.color[0];
    switch (step) {
    case 0:
        ppu.vbus = (uint16_t)(0x2000 | (ppu.v & 0x0FFF));
        break;
    case 1:
        ppu.vbus = (uint16_t)(0x2000 | (ppu.v & 0x0F00) | ppu.octal_latch);
        ppu.fetch_data = rr_ppu_plain_fetch();
        break;
    case 2:
        ppu.vbus = (uint16_t)(0x23C0 | (ppu.v & 0x0C00) | ((ppu.v >> 4) & 0x38) | ((ppu.v >> 2) & 0x07));
        break;
    case 3:
        ppu.vbus = (uint16_t)(0x2300 | (ppu.v & 0x0C00) | ppu.octal_latch);
        ppu.fetch_data = rr_ppu_plain_fetch();
        break;
    case 4:
        ppu.par_chr = (uint16_t)((ppu.par_chr & 0x0FF8) | (ppu.bg_table ? 0x1000 : 0) | ((ppu.v & 0x7000) >> 12));
        ppu.par_chr &= 0x1FF7;
        ppu.vbus = ppu.par_chr;
        break;
    case 5:
        ppu.vbus = (uint16_t)((ppu.par_chr & 0xFF00) | ppu.octal_latch);
        ppu.fetch_data = rr_ppu_plain_fetch();
        break;
    case 6:
        ppu.par_chr = (uint16_t)((ppu.par_chr & 0x0FF8) | (ppu.bg_table ? 0x1000 : 0) | ((ppu.v & 0x7000) >> 12));
        ppu.par_chr |= 8;
        ppu.vbus = ppu.par_chr;
        break;
    default:
        ppu.vbus = (uint16_t)((ppu.par_chr & 0xFF00) | ppu.octal_latch);
        ppu.fetch_data = rr_ppu_plain_fetch();
        break;
    }
    if (!h0) ppu.octal_latch = (uint8_t)ppu.vbus;
    if (prefetch) {
    } else if (sprites) {
        compute_pixel();
        shift_sprites();
    } else {
        rr_ppu_bg_pixel(dot);
    }
    if (!prefetch && dot > 3) {
        uint8_t c = ppu.color[3];
        if (ppu.greyscale) c &= 0x30;
        hw_frame_index[ppu.scanline * 256 + dot - 4] = (uint16_t)(c | ppu.emphasis << 6);
    }
    io_bus_decay();
    hw_cart_ppu_addr(ppu.vbus);

    ppu.bg_lo = (uint16_t)(ppu.bg_lo << 1);
    ppu.bg_hi = (uint16_t)(ppu.bg_hi << 1 | 1);
    ppu.attr_lo = (uint16_t)(ppu.attr_lo << 1 | (ppu.attr_latch & 1));
    ppu.attr_hi = (uint16_t)(ppu.attr_hi << 1 | ((ppu.attr_latch >> 1) & 1));
    if (ppu.oam2_reset > 0 && --ppu.oam2_reset == 0) {
        ppu.oam2_addr = 0;
        ppu.oam2_full = 0;
    }
    switch (step) {
    case 1:
        ppu.par_chr = (uint16_t)((ppu.par_chr & 0x100F) | ((uint8_t)ppu.vbus << 4));
        break;
    case 3: {
        uint8_t a = ppu.fetch_data;
        if ((ppu.v & 3) >= 2) a >>= 2;
        if (((ppu.v >> 5) & 3) >= 2) a >>= 4;
        ppu.attribute = a & 3;
        break;
    }
    case 5:
        ppu.lo_plane = ppu.fetch_data;
        break;
    case 7:
        ppu.hi_plane = ppu.fetch_data;
        ppu.bg_lo = (uint16_t)((ppu.bg_lo & 0xFF00) | ppu.lo_plane);
        ppu.bg_hi = (uint16_t)((ppu.bg_hi & 0xFF00) | ppu.hi_plane);
        ppu.attr_latch = ppu.attribute;
        increment_x();
        break;
    }
    ppu.oam_buffer = ppu.oam_buffer_in;
    half_dot_status();
    ppu.ale = 0;
    ppu.wr = 0;
}

/* The background of one tile in locals. rr_ppu_tile_pair() eight times with no sprite output (sprites false, prefetch false),
 * with the fetch pipeline, the shift registers and the colour pipeline kept in registers instead of the global PPU between the
 * calls that cannot alias them, and the values that every pair sets and the next one overwrites (the bus signals, the latches
 * that are cleared) written once. Everything a pair does, in the same order: the sprite-evaluation fields stay in the PPU
 * (eval_objects() reads and writes them), the A12 hook sees the address of every dot, and the frame index gets the same
 * pixels from the same colour pipeline. */
typedef struct {
    uint16_t v, vbus, par, bg_lo, bg_hi, attr_lo, attr_hi, sprite_row;
    uint8_t latch, fetch, attribute, lo_plane, hi_plane, attr_latch, color[4];
    /* The sprite evaluation of the tile's eight dots: its fields in locals (a block runs with rendering on and settled, no
     * pending $2001 or $2003-side latch, so nothing outside the tile can change them), written back after the eighth. */
    uint8_t oam_addr, oam2_addr, oam2_full, oam2_reset, eval_tick, eval_wrapped, eval_nine, eval_odd_corrupt;
    uint8_t oam_buffer, oam_buffer_in, oam_latch, scan8, height;
} RrTile;

HW_ALWAYS_INLINE void rr_eval_oam2_increment(RrTile *t)
{
    if (!t->oam2_full && ++t->oam2_addr == 0x20) {
        t->oam2_full = 1;
        t->oam2_addr = 0;
    }
}

/* eval_objects(false) on an even dot of a visible line with rendering on and no corruption latch (oamc_disabled_now clear):
 * the same statements on the locals. */
HW_ALWAYS_INLINE void rr_eval_even(RrTile *t, unsigned dot)
{
    const bool step = !t->eval_odd_corrupt;
    if (!t->eval_wrapped) {
        const uint8_t before = t->oam_addr;
        if (!t->oam2_full) ppu.oam2[t->oam2_addr] = t->oam_buffer;
        const uint8_t oam2_value = ppu.oam2[t->oam2_addr];
        if (t->eval_tick == 0) {
            t->sprite_row = (uint16_t)(t->scan8 - t->oam_buffer);
            if (!t->eval_nine && t->sprite_row < t->height) {
                if (!t->oam2_full) {
                    if (!t->eval_odd_corrupt) {
                        t->oam_addr++;
                        rr_eval_oam2_increment(t);
                    }
                    if (dot == 66) ppu.next_has_s0 = 1;
                } else {
                    t->eval_nine = 1;
                    t->oam_addr++;
                    ppu.overflow = 1;
                }
                t->eval_tick++;
            } else {
                if (dot == 66) ppu.next_has_s0 = 0;
                if (step) {
                    if (t->oam2_full && !t->eval_nine) {
                        t->oam_addr += (t->oam_addr & 3) == 3 ? 1 : 5;
                    } else {
                        t->oam_addr = (uint8_t)((t->oam_addr + 4) & 0xFC);
                    }
                }
            }
        } else {
            if (t->eval_tick == 3) {
                int row = (int)t->scan8 - t->oam_buffer;
                if (row >= 0 && row < (int)t->height) {
                    if (step) t->oam_addr += t->oam2_full ? 4 : 1;
                } else if (!t->oam2_full) {
                    if (step) t->oam_addr = (uint8_t)((t->oam_addr + 1) & 0xFC);
                } else {
                    t->oam_addr = (uint8_t)((t->oam_addr + 1) & 0xFC);
                }
            } else if (step) {
                t->oam_addr++;
            }
            t->eval_tick = (uint8_t)((t->eval_tick + 1) & 3);
            if (!t->oam2_full) rr_eval_oam2_increment(t);
        }
        t->eval_odd_corrupt = 0;
        if (t->oam_addr < before && t->oam_addr < 4) t->eval_wrapped = 1;
        t->oam_buffer_in = oam2_value;
    } else {
        if (step) t->oam_addr = (uint8_t)((t->oam_addr + 4) & 0xFC);
        t->oam_buffer_in = ppu.oam2[t->oam2_addr];
    }
}

HW_ALWAYS_INLINE uint16_t rr_tile_increment_x(uint16_t v)
{
    if ((v & 0x1F) == 31) v = (uint16_t)((v & 0xFFE0) ^ 0x0400);
    else v++;
    return (uint16_t)(v & 0x7FFF);
}

HW_ALWAYS_INLINE void rr_tile_step(RrTile *t, unsigned step, unsigned d0, bool bg_on, bool a12_only, bool watch)
{
    advance_dot();                  /* the position, and the status latches of the first half of the dot */
    const unsigned dot = d0 + step + 1;
    const bool h0 = (step & 1) != 0;
    t->oam_latch = t->oam_buffer;
    if (t->oam2_reset > 0) t->oam2_reset--;
    if (d0 >= 64) {                 /* dots 65-256: evaluation */
        if (h0) {
            rr_eval_even(t, dot);
        } else {
            if (step == 0 && d0 == 64) {
                t->eval_nine = 0;
                t->eval_odd_corrupt = 0;
                t->eval_wrapped = 0;
            }
            t->oam_buffer_in = ppu.oam[t->oam_addr];    /* rendering is on: instant_bg or instant_spr is set */
        }
    } else if (!h0) {               /* dots 1-64: secondary OAM clear */
        t->oam_buffer_in = 0xFF;
        if (step == 0 && d0 == 0) {
            t->oam2_addr = 0;
            t->eval_tick = 0;
            t->eval_wrapped = 0;
        }
    } else {
        ppu.oam2[t->oam2_addr] = t->oam_buffer;
        rr_eval_oam2_increment(t);
    }
    if (step == 6 && (d0 == 56 || d0 == 248)) t->oam2_reset = 3;
    t->color[3] = t->color[2];
    t->color[2] = t->color[1];
    t->color[1] = t->color[0];
    switch (step) {
    case 0:
        t->vbus = (uint16_t)(0x2000 | (t->v & 0x0FFF));
        break;
    case 1:
        t->vbus = (uint16_t)(0x2000 | (t->v & 0x0F00) | t->latch);
        t->fetch = rr_ppu_fetch_at(t->vbus, t->latch);
        t->vbus = (uint16_t)((t->vbus & 0xFF00) | t->fetch);
        break;
    case 2:
        t->vbus = (uint16_t)(0x23C0 | (t->v & 0x0C00) | ((t->v >> 4) & 0x38) | ((t->v >> 2) & 0x07));
        break;
    case 3:
        t->vbus = (uint16_t)(0x2300 | (t->v & 0x0C00) | t->latch);
        t->fetch = rr_ppu_fetch_at(t->vbus, t->latch);
        t->vbus = (uint16_t)((t->vbus & 0xFF00) | t->fetch);
        break;
    case 4:
        t->par = (uint16_t)((t->par & 0x0FF8) | (ppu.bg_table ? 0x1000 : 0) | ((t->v & 0x7000) >> 12));
        t->par &= 0x1FF7;
        t->vbus = t->par;
        break;
    case 5:
        t->vbus = (uint16_t)((t->par & 0xFF00) | t->latch);
        t->fetch = rr_ppu_fetch_at(t->vbus, t->latch);
        t->vbus = (uint16_t)((t->vbus & 0xFF00) | t->fetch);
        break;
    case 6:
        t->par = (uint16_t)((t->par & 0x0FF8) | (ppu.bg_table ? 0x1000 : 0) | ((t->v & 0x7000) >> 12));
        t->par |= 8;
        t->vbus = t->par;
        break;
    default:
        t->vbus = (uint16_t)((t->par & 0xFF00) | t->latch);
        t->fetch = rr_ppu_fetch_at(t->vbus, t->latch);
        t->vbus = (uint16_t)((t->vbus & 0xFF00) | t->fetch);
        break;
    }
    if (!h0) t->latch = (uint8_t)t->vbus;
    uint8_t color = 0, pal = 0;
    if (bg_on) {
        const unsigned fx = ppu.fine_x;
        color = (uint8_t)(((t->bg_lo >> (15 - fx)) & 1) | (((t->bg_hi >> (15 - fx)) & 1) << 1));
        pal = (uint8_t)(((t->attr_lo >> (7 - fx)) & 1) | (((t->attr_hi >> (7 - fx)) & 1) << 1));
        if (color == 0) pal = 0;
    }
    t->color[0] = ppu.palette[(uint8_t)(pal << 2 | color)] & 0x3F;
    if (dot > 3) {
        uint8_t c = t->color[3];
        if (ppu.greyscale) c &= 0x30;
        hw_frame_index[ppu.scanline * 256 + dot - 4] = (uint16_t)(c | ppu.emphasis << 6);
    }
    if (watch && (!a12_only || (unsigned)((t->vbus >> 12) & 1) != hw_cart.m.a12)) hw_cart_ppu_addr_watched(t->vbus);
    t->bg_lo = (uint16_t)(t->bg_lo << 1);
    t->bg_hi = (uint16_t)(t->bg_hi << 1 | 1);
    t->attr_lo = (uint16_t)(t->attr_lo << 1 | (t->attr_latch & 1));
    t->attr_hi = (uint16_t)(t->attr_hi << 1 | ((t->attr_latch >> 1) & 1));
    if (t->oam2_reset > 0 && --t->oam2_reset == 0) {
        t->oam2_addr = 0;
        t->oam2_full = 0;
    }
    switch (step) {
    case 1:
        t->par = (uint16_t)((t->par & 0x100F) | ((uint8_t)t->vbus << 4));
        break;
    case 3: {
        uint8_t a = t->fetch;
        if ((t->v & 3) >= 2) a >>= 2;
        if (((t->v >> 5) & 3) >= 2) a >>= 4;
        t->attribute = a & 3;
        break;
    }
    case 5:
        t->lo_plane = t->fetch;
        break;
    case 7:
        t->hi_plane = t->fetch;
        t->bg_lo = (uint16_t)((t->bg_lo & 0xFF00) | t->lo_plane);
        t->bg_hi = (uint16_t)((t->bg_hi & 0xFF00) | t->hi_plane);
        t->attr_latch = t->attribute;
        t->v = rr_tile_increment_x(t->v);
        break;
    }
    t->oam_buffer = t->oam_buffer_in;
    half_dot_status();
}

static void rr_ppu_tile_bg(void)
{
    const unsigned d0 = ppu.dot;
    /* The first tile of the odd frame's first line drops a dot, and a decaying open bus counts its dots against a deadline:
     * the pairs take those. */
    if ((!RR_NES_PAL && d0 == 0 && ppu.scanline == 0 && ppu.odd_frame) ||
        (ppu.io_bus && ppu.io_decay_clock + 8 >= ppu.io_decay_next) ||
        /* the evaluation of the tile runs on locals only with rendering on and no corruption latch (rr_ppu_block checks the latter) */
        !(ppu.instant_bg || ppu.instant_spr) || ppu.oamc_disabled_now) {
        rr_ppu_tile_pair(0, false, false); rr_ppu_tile_pair(1, false, false); rr_ppu_tile_pair(2, false, false); rr_ppu_tile_pair(3, false, false);
        rr_ppu_tile_pair(4, false, false); rr_ppu_tile_pair(5, false, false); rr_ppu_tile_pair(6, false, false); rr_ppu_tile_pair(7, false, false);
        return;
    }
    RrTile t;
    t.v = ppu.v; t.vbus = ppu.vbus; t.par = ppu.par_chr;
    t.bg_lo = ppu.bg_lo; t.bg_hi = ppu.bg_hi; t.attr_lo = ppu.attr_lo; t.attr_hi = ppu.attr_hi;
    t.latch = ppu.octal_latch; t.fetch = ppu.fetch_data; t.attribute = ppu.attribute;
    t.lo_plane = ppu.lo_plane; t.hi_plane = ppu.hi_plane; t.attr_latch = ppu.attr_latch;
    for (unsigned i = 0; i < 4; i++) t.color[i] = ppu.color[i];
    t.sprite_row = ppu.sprite_row;
    t.oam_addr = ppu.oam_addr; t.oam2_addr = ppu.oam2_addr; t.oam2_full = ppu.oam2_full; t.oam2_reset = ppu.oam2_reset;
    t.eval_tick = ppu.eval_tick; t.eval_wrapped = ppu.eval_wrapped; t.eval_nine = ppu.eval_nine;
    t.eval_odd_corrupt = ppu.eval_odd_corrupt;
    t.oam_buffer = ppu.oam_buffer; t.oam_buffer_in = ppu.oam_buffer_in; t.oam_latch = ppu.oam_latch;
    t.scan8 = (uint8_t)ppu.scanline; t.height = ppu.sprite16 ? 16 : 8;
    const bool bg_on = ppu.show_bg && (d0 >= 8 || ppu.show_bg8);
    /* A board that watches the bus here is an MMC1: its hook only reacts to a change of A12. */
    const bool watch = hw_cart.watch_ppu_addr != 0;
    const bool a12_only = RR_NES_MAPPER == 1 || RR_NES_MAPPER == 155;
    if (watch && !a12_only) {
        rr_ppu_tile_pair(0, false, false); rr_ppu_tile_pair(1, false, false); rr_ppu_tile_pair(2, false, false); rr_ppu_tile_pair(3, false, false);
        rr_ppu_tile_pair(4, false, false); rr_ppu_tile_pair(5, false, false); rr_ppu_tile_pair(6, false, false); rr_ppu_tile_pair(7, false, false);
        return;
    }
    rr_tile_step(&t, 0, d0, bg_on, a12_only, watch); rr_tile_step(&t, 1, d0, bg_on, a12_only, watch);
    rr_tile_step(&t, 2, d0, bg_on, a12_only, watch); rr_tile_step(&t, 3, d0, bg_on, a12_only, watch);
    rr_tile_step(&t, 4, d0, bg_on, a12_only, watch); rr_tile_step(&t, 5, d0, bg_on, a12_only, watch);
    rr_tile_step(&t, 6, d0, bg_on, a12_only, watch); rr_tile_step(&t, 7, d0, bg_on, a12_only, watch);
    ppu.v = t.v; ppu.vbus = t.vbus; ppu.par_chr = t.par;
    ppu.bg_lo = t.bg_lo; ppu.bg_hi = t.bg_hi; ppu.attr_lo = t.attr_lo; ppu.attr_hi = t.attr_hi;
    ppu.octal_latch = t.latch; ppu.fetch_data = t.fetch; ppu.attribute = t.attribute;
    ppu.lo_plane = t.lo_plane; ppu.hi_plane = t.hi_plane; ppu.attr_latch = t.attr_latch;
    for (unsigned i = 0; i < 4; i++) ppu.color[i] = t.color[i];
    ppu.sprite_row = t.sprite_row;
    ppu.oam_addr = t.oam_addr; ppu.oam2_addr = t.oam2_addr; ppu.oam2_full = t.oam2_full; ppu.oam2_reset = t.oam2_reset;
    ppu.eval_tick = t.eval_tick; ppu.eval_wrapped = t.eval_wrapped; ppu.eval_nine = t.eval_nine;
    ppu.eval_odd_corrupt = t.eval_odd_corrupt;
    ppu.oam_buffer = t.oam_buffer; ppu.oam_buffer_in = t.oam_buffer_in; ppu.oam_latch = t.oam_latch;
    if (ppu.io_bus) ppu.io_decay_clock += 8;
    /* Set by every pair, and the same at the end of each. */
    ppu.blnk_latch = 0;
    ppu.pal_enable = 0;
    ppu.rd = 1;
    ppu.ale = 0;
    ppu.wr = 0;
    ppu.copy_v = 0;
}

static void rr_ppu_visible_tile(void)
{
    /* A unit can be opaque only once its counter is 0; one with pattern
     * bits needs at least 8 more dots, one without never outputs. */
    bool sprites = ppu.skipped_dot || ppu.palc_disabled || ppu.palc_v_left || rr_xs.count;
    for (unsigned i = 0; i < 8; i++) sprites |= (ppu.spr_lo[i] | ppu.spr_hi[i]) && ppu.spr_x[i] < 8;
    if (sprites) {
        rr_ppu_tile_pair(0, true, false); rr_ppu_tile_pair(1, true, false); rr_ppu_tile_pair(2, true, false); rr_ppu_tile_pair(3, true, false);
        rr_ppu_tile_pair(4, true, false); rr_ppu_tile_pair(5, true, false); rr_ppu_tile_pair(6, true, false); rr_ppu_tile_pair(7, true, false);
        return;
    }
    rr_ppu_tile_bg();
    /* shift_sprites() eight times: counters step down to 0, and a unit
     * reaching 0 has no pattern bits to shift. */
    for (unsigned i = 0; i < 8; i++) ppu.spr_x[i] = ppu.spr_x[i] > 8 ? (uint8_t)(ppu.spr_x[i] - 8) : 0;
}

static void rr_ppu_prefetch_tile(void)
{
    rr_ppu_tile_pair(0, false, true); rr_ppu_tile_pair(1, false, true);
    rr_ppu_tile_pair(2, false, true); rr_ppu_tile_pair(3, false, true);
    rr_ppu_tile_pair(4, false, true); rr_ppu_tile_pair(5, false, true);
    rr_ppu_tile_pair(6, false, true); rr_ppu_tile_pair(7, false, true);
}

/* One steady dot and half dot of sprite slot `slot` on a visible scanline,
 * dots 257-320 (rr_ppu_steady_dot/half with eval_load() and its dummy
 * nametable fetches): the same preconditions as a tile. */
HW_ALWAYS_INLINE void rr_ppu_slot_pair(unsigned step, unsigned slot)
{
    if (slot == 0 && step == 0) increment_y();
    else if (slot == 0 && step == 1) ppu.v = (uint16_t)((ppu.v & 0x7BE0) | (ppu.t & 0x041F));
    advance_dot();
    unsigned dot = ppu.dot;
    bool h0 = (step & 1) != 0;
    ppu.blnk_latch = 0;
    ppu.pal_enable = 0;
    ppu.rd = h0;
    ppu.ale = !h0;
    ppu.oam_latch = ppu.oam_buffer;
    ppu.copy_v = 0;
    if (ppu.oam2_reset > 0) ppu.oam2_reset--;
    unsigned height = ppu.sprite16 ? 16 : 8;
    ppu.cur_has_s0 = ppu.next_has_s0;
    ppu.oam_addr = 0;
    if (h0) ppu.octal_latch = (uint8_t)ppu.vbus;
    ppu.oam_buffer_in = ppu.oam2[ppu.oam2_addr];
    switch (step) {
    case 0:
        ppu.vbus = (uint16_t)(0x2000 | (ppu.v & 0x0FFF));
        oam2_increment();
        break;
    case 1:
        ppu.sprite_row = (uint16_t)((ppu.scanline & 0xFF) - ppu.oam_buffer);
        ppu.vbus = (uint16_t)(0x2000 | (ppu.v & 0x0F00) | ppu.octal_latch);
        ppu.fetch_data = rr_ppu_plain_fetch();
        oam2_increment();
        break;
    case 2:
        ppu.load_tile = ppu.oam_buffer;
        ppu.vbus = (uint16_t)(0x2000 | (ppu.v & 0x0FFF));
        oam2_increment();
        break;
    case 3:
        ppu.spr_attr[slot] = ppu.oam_buffer;
        ppu.load_attr = ppu.oam_buffer;
        ppu.vbus = (uint16_t)(0x2000 | (ppu.v & 0x0F00) | ppu.octal_latch);
        ppu.fetch_data = rr_ppu_plain_fetch();
        break;
    case 4:
        ppu.spr_x[slot] = ppu.oam_buffer;
        par_context();
        ppu.par_chr &= 0x1FF7;
        ppu.vbus = ppu.par_chr;
        break;
    case 5: {
        par_context();
        ppu.par_chr &= 0x1FF7;
        ppu.vbus = (uint16_t)((ppu.par_chr & 0xFF00) | ppu.octal_latch);
        uint8_t bits = rr_ppu_plain_fetch();
        if (ppu.spr_attr[slot] & 0x40) bits = flip_bits(bits);
        ppu.spr_lo[slot] = ppu.sprite_row < height ? bits : 0;
        break;
    }
    case 6:
        par_context();
        ppu.par_chr |= 8;
        ppu.vbus = ppu.par_chr;
        break;
    default: {
        par_context();
        ppu.par_chr |= 8;
        ppu.vbus = (uint16_t)((ppu.par_chr & 0xFF00) | ppu.octal_latch);
        uint8_t bits = rr_ppu_plain_fetch();
        if (ppu.spr_attr[slot] & 0x40) bits = flip_bits(bits);
        ppu.spr_hi[slot] = ppu.sprite_row < height ? bits : 0;
        oam2_increment();
        break;
    }
    }
    if (!h0) ppu.octal_latch = (uint8_t)ppu.vbus;
    ppu.color[3] = ppu.color[2];
    ppu.color[2] = ppu.color[1];
    ppu.color[1] = ppu.color[0];
    if (slot == 0 && step < 3) {
        uint8_t c = ppu.color[3];
        if (ppu.greyscale) c &= 0x30;
        hw_frame_index[ppu.scanline * 256 + dot - 4] = (uint16_t)(c | ppu.emphasis << 6);
    }
    io_bus_decay();
    hw_cart_ppu_addr(ppu.vbus);

    if (slot == 0 && step == 0) {
        ppu.bg_lo = (uint16_t)(ppu.bg_lo << 1);
        ppu.bg_hi = (uint16_t)(ppu.bg_hi << 1 | 1);
        ppu.attr_lo = (uint16_t)(ppu.attr_lo << 1 | (ppu.attr_latch & 1));
        ppu.attr_hi = (uint16_t)(ppu.attr_hi << 1 | ((ppu.attr_latch >> 1) & 1));
    }
    if (ppu.oam2_reset > 0 && --ppu.oam2_reset == 0) {
        ppu.oam2_addr = 0;
        ppu.oam2_full = 0;
    }
    /* bg_commit() of the dummy nametable fetch */
    if (step == 1 || step == 3) ppu.par_chr = (uint16_t)((ppu.par_chr & 0x100F) | (ppu.load_tile << 4));
    ppu.oam_buffer = ppu.oam_buffer_in;
    half_dot_status();
    ppu.ale = 0;
    ppu.wr = 0;
}

/* The eight pairs of a sprite slot with the fetch pipeline and the colour pipeline in locals, as rr_ppu_tile_bg() does for a tile:
 * the same pairs in the same order (rr_ppu_slot_pair above is the reference), the fields of the sprite loading stay in the PPU, and
 * what every pair sets and the next overwrites is written once. */
typedef struct { uint16_t vbus, par; uint8_t latch, fetch, color[4]; } RrSlotRegs;

HW_ALWAYS_INLINE void rr_slot_step(RrSlotRegs *t, unsigned step, unsigned slot, unsigned d0, bool watch, bool a12_only)
{
    if (slot == 0 && step == 0) increment_y();
    else if (slot == 0 && step == 1) ppu.v = (uint16_t)((ppu.v & 0x7BE0) | (ppu.t & 0x041F));
    advance_dot();
    const unsigned dot = d0 + step + 1;
    const bool h0 = (step & 1) != 0;
    ppu.oam_latch = ppu.oam_buffer;
    ppu.copy_v = 0;
    if (ppu.oam2_reset > 0) ppu.oam2_reset--;
    const unsigned height = ppu.sprite16 ? 16 : 8;
    ppu.cur_has_s0 = ppu.next_has_s0;
    ppu.oam_addr = 0;
    if (h0) t->latch = (uint8_t)t->vbus;
    ppu.oam_buffer_in = ppu.oam2[ppu.oam2_addr];
    switch (step) {
    case 0:
        t->vbus = (uint16_t)(0x2000 | (ppu.v & 0x0FFF));
        oam2_increment();
        break;
    case 1:
        ppu.sprite_row = (uint16_t)((ppu.scanline & 0xFF) - ppu.oam_buffer);
        t->vbus = (uint16_t)(0x2000 | (ppu.v & 0x0F00) | t->latch);
        t->fetch = rr_ppu_fetch_at(t->vbus, t->latch);
        t->vbus = (uint16_t)((t->vbus & 0xFF00) | t->fetch);
        oam2_increment();
        break;
    case 2:
        ppu.load_tile = ppu.oam_buffer;
        t->vbus = (uint16_t)(0x2000 | (ppu.v & 0x0FFF));
        oam2_increment();
        break;
    case 3:
        ppu.spr_attr[slot] = ppu.oam_buffer;
        ppu.load_attr = ppu.oam_buffer;
        t->vbus = (uint16_t)(0x2000 | (ppu.v & 0x0F00) | t->latch);
        t->fetch = rr_ppu_fetch_at(t->vbus, t->latch);
        t->vbus = (uint16_t)((t->vbus & 0xFF00) | t->fetch);
        break;
    case 4:
        ppu.spr_x[slot] = ppu.oam_buffer;
        ppu.par_chr = t->par; par_context(); t->par = ppu.par_chr;
        t->par &= 0x1FF7;
        t->vbus = t->par;
        break;
    case 5: {
        ppu.par_chr = t->par; par_context(); t->par = ppu.par_chr;
        t->par &= 0x1FF7;
        t->vbus = (uint16_t)((t->par & 0xFF00) | t->latch);
        uint8_t bits = rr_ppu_fetch_at(t->vbus, t->latch);
        t->vbus = (uint16_t)((t->vbus & 0xFF00) | bits);
        if (ppu.spr_attr[slot] & 0x40) bits = flip_bits(bits);
        ppu.spr_lo[slot] = ppu.sprite_row < height ? bits : 0;
        break;
    }
    case 6:
        ppu.par_chr = t->par; par_context(); t->par = ppu.par_chr;
        t->par |= 8;
        t->vbus = t->par;
        break;
    default: {
        ppu.par_chr = t->par; par_context(); t->par = ppu.par_chr;
        t->par |= 8;
        t->vbus = (uint16_t)((t->par & 0xFF00) | t->latch);
        uint8_t bits = rr_ppu_fetch_at(t->vbus, t->latch);
        t->vbus = (uint16_t)((t->vbus & 0xFF00) | bits);
        if (ppu.spr_attr[slot] & 0x40) bits = flip_bits(bits);
        ppu.spr_hi[slot] = ppu.sprite_row < height ? bits : 0;
        oam2_increment();
        break;
    }
    }
    if (!h0) t->latch = (uint8_t)t->vbus;
    t->color[3] = t->color[2];
    t->color[2] = t->color[1];
    t->color[1] = t->color[0];
    if (slot == 0 && step < 3) {
        uint8_t c = t->color[3];
        if (ppu.greyscale) c &= 0x30;
        hw_frame_index[ppu.scanline * 256 + dot - 4] = (uint16_t)(c | ppu.emphasis << 6);
    }
    if (watch && (!a12_only || (unsigned)((t->vbus >> 12) & 1) != hw_cart.m.a12)) hw_cart_ppu_addr_watched(t->vbus);
    if (slot == 0 && step == 0) {
        ppu.bg_lo = (uint16_t)(ppu.bg_lo << 1);
        ppu.bg_hi = (uint16_t)(ppu.bg_hi << 1 | 1);
        ppu.attr_lo = (uint16_t)(ppu.attr_lo << 1 | (ppu.attr_latch & 1));
        ppu.attr_hi = (uint16_t)(ppu.attr_hi << 1 | ((ppu.attr_latch >> 1) & 1));
    }
    if (ppu.oam2_reset > 0 && --ppu.oam2_reset == 0) {
        ppu.oam2_addr = 0;
        ppu.oam2_full = 0;
    }
    if (step == 1 || step == 3) t->par = (uint16_t)((t->par & 0x100F) | (ppu.load_tile << 4));
    ppu.oam_buffer = ppu.oam_buffer_in;
    half_dot_status();
}

HW_ALWAYS_INLINE void rr_ppu_slot_run(unsigned slot)
{
    const unsigned d0 = ppu.dot;
    const bool watch = hw_cart.watch_ppu_addr != 0;
    const bool a12_only = RR_NES_MAPPER == 1 || RR_NES_MAPPER == 155;
    if ((ppu.io_bus && ppu.io_decay_clock + 8 >= ppu.io_decay_next) || (watch && !a12_only)) {
        rr_ppu_slot_pair(0, slot); rr_ppu_slot_pair(1, slot); rr_ppu_slot_pair(2, slot); rr_ppu_slot_pair(3, slot);
        rr_ppu_slot_pair(4, slot); rr_ppu_slot_pair(5, slot); rr_ppu_slot_pair(6, slot); rr_ppu_slot_pair(7, slot);
        return;
    }
    RrSlotRegs t;
    t.vbus = ppu.vbus; t.par = ppu.par_chr; t.latch = ppu.octal_latch; t.fetch = ppu.fetch_data;
    for (unsigned i = 0; i < 4; i++) t.color[i] = ppu.color[i];
    rr_slot_step(&t, 0, slot, d0, watch, a12_only); rr_slot_step(&t, 1, slot, d0, watch, a12_only);
    rr_slot_step(&t, 2, slot, d0, watch, a12_only); rr_slot_step(&t, 3, slot, d0, watch, a12_only);
    rr_slot_step(&t, 4, slot, d0, watch, a12_only); rr_slot_step(&t, 5, slot, d0, watch, a12_only);
    rr_slot_step(&t, 6, slot, d0, watch, a12_only); rr_slot_step(&t, 7, slot, d0, watch, a12_only);
    ppu.vbus = t.vbus; ppu.par_chr = t.par; ppu.octal_latch = t.latch; ppu.fetch_data = t.fetch;
    for (unsigned i = 0; i < 4; i++) ppu.color[i] = t.color[i];
    if (ppu.io_bus) ppu.io_decay_clock += 8;
    ppu.blnk_latch = 0;
    ppu.pal_enable = 0;
    ppu.rd = 1;
    ppu.ale = 0;
    ppu.wr = 0;
}

#define RR_PPU_SLOT(slot) static void rr_ppu_sprite_slot_##slot(void) { rr_ppu_slot_run(slot); }
RR_PPU_SLOT(0) RR_PPU_SLOT(1) RR_PPU_SLOT(2) RR_PPU_SLOT(3)
RR_PPU_SLOT(4) RR_PPU_SLOT(5) RR_PPU_SLOT(6) RR_PPU_SLOT(7)
#undef RR_PPU_SLOT

/* Eight steady pairs from a tile boundary of a visible scanline (dot 0-328
 * before them), when nothing pending needs the general paths. */
static bool rr_ppu_block(void)
{
    unsigned dot = ppu.dot;
    if (ppu.scanline >= 240 || (dot & 7) || dot > 328 || !rr_ppu_plain || ppu.commit ||
        (ppu.oamc_disabled | ppu.oamc_disabled_now | ppu.oamc_pending) || hw_cart.chr_ciram) return false;
    switch (dot >> 3) {
    case 32: rr_ppu_sprite_slot_0(); break;
    case 33: rr_ppu_sprite_slot_1(); break;
    case 34: rr_ppu_sprite_slot_2(); break;
    case 35: rr_ppu_sprite_slot_3(); break;
    case 36: rr_ppu_sprite_slot_4(); break;
    case 37: rr_ppu_sprite_slot_5(); break;
    case 38: rr_ppu_sprite_slot_6(); break;
    case 39: rr_ppu_sprite_slot_7(); rr_xs_prepare(); break;
    case 40: case 41: rr_ppu_prefetch_tile(); break;
    default: rr_ppu_visible_tile(); break;
    }
    return true;
}

void rr_ppu_flush(void)
{
    unsigned n = rr_ppu_due;
    rr_ppu_due = 0;
    if (n && !rr_ppu_next_dot) {
        rr_step_half();
        n--;
        rr_ppu_next_dot = true;
    }
    /* Without register accesses a steady or blank classification holds for
     * the whole run. */
    while (n >= 2) {
        if (dot_kind == DOT_UNKNOWN) {
            dot_kind = is_blank() ? DOT_BLANK : DOT_GENERAL;
            rr_ppu_steady = dot_kind == DOT_GENERAL && rr_ppu_can_steady();
        }
        if (dot_kind == DOT_BLANK) {
            for (; n >= 2; n -= 2) {
                blank_dot();
                hw_cart_ppu_addr(ppu.vbus);
                blank_half_dot();
            }
        } else if (rr_ppu_steady) {
            while (n >= 2) {
                if (n >= 16 && rr_ppu_block()) {
                    n -= 16;
                    continue;
                }
                if (ppu.scanline < 240 && ppu.dot != 340) {
                    rr_ppu_visible_pair();
                } else {
                    rr_ppu_steady_dot();
                    hw_cart_ppu_addr(ppu.vbus);
                    rr_ppu_steady_half();
                }
                n -= 2;
            }
        } else {
            rr_step_dot();
            rr_step_half();
            n -= 2;
        }
    }
    if (n) {
        rr_step_dot();
        rr_ppu_next_dot = false;
    }
    rr_ppu_room = rr_ppu_hold ? 1u : rr_ppu_compute_room();
}

/* After power-on or a restored state: nothing is pending, and the next
 * edge follows from the master clock position. */
void rr_ppu_lazy_reset(void)
{
    rr_ppu_due = 0;
    rr_ppu_hold = false;
    /* MMC1 watches A12 for its CHR-selected PRG A18 and RAM bank/enable.
     * Up to 256 KiB of PRG ROM, only RAM accesses can observe it, and those
     * synchronize; the A12 hook still runs on every deferred dot. */
    bool mmc1 = (RR_NES_MAPPER == 1 || RR_NES_MAPPER == 155) && hw_cart.prg_slots <= 64;
    rr_ppu_lazy = !RR_NES_ZAPPER && (!hw_cart.watch_ppu_addr || mmc1) && !hw_cart.watch_cpu &&
                  RR_NES_MAPPER != 5;
    /* CHR latches (MMC2/4), nametable ROM, CHR enables and cartridge
     * mirroring overrides keep the full VRAM path. */
    rr_ppu_plain = rr_ppu_lazy && RR_NES_MAPPER != 9 && RR_NES_MAPPER != 10 && RR_NES_MAPPER != 68 &&
                   RR_NES_MAPPER != 93 && RR_NES_MAPPER != 95 && RR_NES_MAPPER != 185 && RR_NES_MAPPER != 207;
    rr_ppu_chr_wrap = hw_cart.chr_ram && hw_cart.chr_len ? hw_cart.chr_len : 0;
    unsigned k = hw.tick;
    if (RR_NES_PAL) {
        /* run_tick: a dot at phase 0 and a half dot at phase 2 of the 5-tick PPU period,
         * counted from the cycle the next tick belongs to. */
        uint64_t phase = (hw.cycles + hw.pal_bus_pending) * 16u + hw.align + k;
        while (phase % 5u != 0 && phase % 5u != 2) phase++;
        rr_ppu_next_dot = phase % 5u == 0;
    } else {
        while ((hw.align + k) & 1u) k++;
        rr_ppu_next_dot = ((hw.align + k) & 3u) == 0;
    }
    rr_ppu_room = rr_ppu_lazy ? rr_ppu_compute_room() : 1u;
}

static void rr_ppu_lazy_stop(void)
{
    rr_ppu_lazy = false;
    rr_ppu_due = 0;
    rr_ppu_room = 1;
}

/* Register accesses run their own partial ticks with the clock eager. */
static void rr_ppu_access_begin(void)
{
    rr_ppu_hold = true;
    rr_ppu_sync();
    rr_ppu_room = 1;
}

static void rr_ppu_access_end(void)
{
    rr_ppu_hold = false;
    if (rr_ppu_lazy) rr_ppu_room = rr_ppu_compute_room();
}
