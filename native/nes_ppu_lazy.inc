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

/* vram_fetch() with /RD low and no write, on a plain board. */
HW_ALWAYS_INLINE uint8_t rr_ppu_plain_fetch(void)
{
    uint8_t value;
    if (ppu.vbus & 0x2000) {
        unsigned a10;
        if (hw_cart.info.four_screen) a10 = ppu.vbus & 0xc00;
        else switch (hw_cart.mirroring) {
        case HW_MIRROR_HORIZONTAL: a10 = (ppu.vbus & 0x800) ? 0x400 : 0; break;
        case HW_MIRROR_VERTICAL:   a10 = (ppu.vbus & 0x400) ? 0x400 : 0; break;
        case HW_MIRROR_SCREEN_B:   a10 = 0x400; break;
        default:                   a10 = 0; break;
        }
        value = ppu.ciram[(ppu.vbus & 0x300) | ppu.octal_latch | a10];
    } else {
        unsigned addr = ((ppu.vbus & 0x3F00) | ppu.octal_latch) & 0x1FFF;
        uint32_t index = hw_cart.chr_off[addr >> 10] | (addr & 0x3FF);
        if (rr_ppu_chr_wrap)
            index = (rr_ppu_chr_wrap & (rr_ppu_chr_wrap - 1)) ? index % rr_ppu_chr_wrap : index & (rr_ppu_chr_wrap - 1);
        value = hw_cart.chr[index];
    }
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
    rr_ppu_tile_pair(0, false, false); rr_ppu_tile_pair(1, false, false); rr_ppu_tile_pair(2, false, false); rr_ppu_tile_pair(3, false, false);
    rr_ppu_tile_pair(4, false, false); rr_ppu_tile_pair(5, false, false); rr_ppu_tile_pair(6, false, false); rr_ppu_tile_pair(7, false, false);
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

#define RR_PPU_SLOT(slot) static void rr_ppu_sprite_slot_##slot(void) {     rr_ppu_slot_pair(0, slot); rr_ppu_slot_pair(1, slot); rr_ppu_slot_pair(2, slot); rr_ppu_slot_pair(3, slot);     rr_ppu_slot_pair(4, slot); rr_ppu_slot_pair(5, slot); rr_ppu_slot_pair(6, slot); rr_ppu_slot_pair(7, slot); }
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
