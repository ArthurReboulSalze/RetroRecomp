/* Adapted from the pinned NESRecomp PPU; its PolyForm Noncommercial terms
 * remain applicable. See THIRD_PARTY_NOTICES.md and licenses/nesrecomp.md.
 * Included after the original PPU helpers. Every dot, half dot, mapper event
 * and output pixel still runs; only settled-latch checks are cached.
 * Register accesses invalidate dot_kind before they can change these inputs. */
static bool rr_ppu_steady;
static bool rr_ppu_can_steady(void) {
    return sm_rest && rendering() && ppu.render_count >= 5 &&
        ppu.eval_bg == ppu.show_bg && ppu.eval_spr == ppu.show_spr &&
        !(ppu.w2005_delay | ppu.w2006_delay | ppu.w2001_delay |
          ppu.w2001_oam_delay | ppu.w2001_emph_delay);
}
static void rr_ppu_steady_dot(void) {
    if (render_line()) {
        if (ppu.dot == 256) increment_y();
        else if (ppu.dot == 257) ppu.v = (uint16_t)((ppu.v & 0x7BE0) | (ppu.t & 0x041F));
        if (ppu.dot >= 280 && ppu.dot <= 304 && ppu.scanline == RR_PRERENDER)
            ppu.v = (uint16_t)((ppu.v & 0x041F) | (ppu.t & 0x7BE0));
    }
    advance_dot();
    int sl = ppu.scanline;
    if (!RR_NES_PAL && ppu.odd_frame && sl == 0) {
        if (ppu.dot == 0) { ppu.dot = 1; ppu.skipped_dot = 1; }
        else if (ppu.dot == 2) ppu.skipped_dot = 0;
    }
    int dot = ppu.dot;
    bool blank = sl >= 240 && sl < RR_PRERENDER;
    bool h0 = ((dot - 1) & 1) != 0;
    ppu.blnk_latch = blank;
    ppu.pal_enable = (ppu.vbus & 0x3F00) == 0x3F00 && blank;
    ppu.rd = !blank && h0;
    hw_cart_ppu_rd(ppu.rd != 0);
    ppu.ale = !blank && !h0;
    ppu.oam_latch = ppu.oam_buffer;
    ppu.copy_v = 0;
    if (ppu.oam2_reset > 0) ppu.oam2_reset--;
    if (render_line()) {
        sprite_evaluation();
        if (dot == 63 || dot == 255 || dot == 339) ppu.oam2_reset = 3;
    }
    ppu.color[3] = ppu.color[2];
    ppu.color[2] = ppu.color[1];
    ppu.color[1] = ppu.color[0];
    if (render_line() || (sl == 240 && dot == 0)) {
        if ((dot >= 1 && dot <= 256) || (dot >= 321 && dot <= 336)) bg_fetch();
        else if (dot >= 337 || dot == 0) bg_fetch_tail();
        if (dot >= 1 && dot <= 256) {
            if (sl < 240) compute_pixel();
            shift_sprites();
        }
        if (sl < 240) output_pixel();
    }
    io_bus_decay();
}
static void rr_ppu_steady_half(void) {
    if (render_line() && ((ppu.dot >= 1 && ppu.dot <= 257) || (ppu.dot >= 321 && ppu.dot <= 336))) {
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
