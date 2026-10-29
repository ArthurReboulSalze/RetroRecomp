/* ROM-free checks of the Neo Geo fix-layer edge-mask detector and its latch (neogeo_fixmask.h) on synthetic fix tiles,
 * palettes and pictures: a coloured mask is painted black after 30 matching frames, a black mask, a picture, a flash and
 * a partly filled column are never touched, a latched band is released after 120 frames that do not match, and the
 * picture the validation hashes read is never written. Original RetroRecomp code: MIT. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "neogeo_fixmask.h"

RrNgFixMask rr_ng_fix_mask;
#define W RR_NG_FIXMASK_WIDTH
#define H RR_NG_FIXMASK_HEIGHT
enum { LEFT = 0, RIGHT = 1 };
static const uint32_t GREY = 0xffd9d9d9u, ORANGE = 0xffe08020u, DARK_BLUE = 0xff202060u, NEAR_BLACK = 0xff101010u;
static uint32_t picture[W * H], copy[W * H], view[W * H];

static void fill(uint32_t colour) { for (unsigned n = 0; n < W * H; ++n) picture[n] = colour; }

/* The engine's note for one tile row: tile bytes, fix-map entry and a palette whose entry 3 is `colour`. */
static void note(RrNgFixMask *m, unsigned side, unsigned row, unsigned palette_number, unsigned solid_index, uint32_t colour) {
    uint8_t tile[32];
    uint32_t colours[16];
    for (unsigned n = 0; n < 16; ++n) colours[n] = 0xff000000u | n * 0x111111u;
    colours[solid_index & 15u] = colour;
    memset(tile, (int)((solid_index & 15u) * 17u), sizeof tile);
    rr_ng_fixmask_note(m, side, row, palette_number << 12 | 0x20u, tile, colours);
}
/* A tile that is not solid: two palette indices. */
static void note_picture(RrNgFixMask *m, unsigned side, unsigned row) {
    uint8_t tile[32];
    uint32_t colours[16];
    for (unsigned n = 0; n < 16; ++n) { colours[n] = 0xff000000u | n * 0x111111u; }
    for (unsigned n = 0; n < 32; ++n) tile[n] = (uint8_t)(n & 1u ? 0x33u : 0x44u);
    rr_ng_fixmask_note(m, side, row, 0x1234u, tile, colours);
}
/* Rows 2..29 of one side hold the solid tile, except the last `missing` rows, which hold a picture tile. */
static void frame_mask(RrNgFixMask *m, unsigned side, uint32_t colour, unsigned missing) {
    for (unsigned row = 2; row < 30; ++row) {
        if (row >= 30 - missing) note_picture(m, side, row);
        else note(m, side, row, 1, 3, colour);
    }
}
static void run(RrNgFixMask *m, unsigned frames, unsigned left_missing, unsigned right_missing,
                uint32_t left, uint32_t right) {
    for (unsigned n = 0; n < frames; ++n) {
        frame_mask(m, LEFT, left, left_missing);
        frame_mask(m, RIGHT, right, right_missing);
        rr_ng_fixmask_frame(m, picture);
    }
}
static void run_empty(RrNgFixMask *m, unsigned frames) { for (unsigned n = 0; n < frames; ++n) rr_ng_fixmask_frame(m, picture); }

static bool band_black(const uint32_t *shown, unsigned first) {
    for (unsigned y = 0; y < H; ++y) for (unsigned x = 0; x < 8; ++x) if (shown[y * W + first + x] != 0xff000000u) return false;
    return true;
}
static bool band_untouched(const uint32_t *shown, unsigned first) {
    for (unsigned y = 0; y < H; ++y) for (unsigned x = 0; x < 8; ++x) if (shown[y * W + first + x] != picture[y * W + first + x]) return false;
    return true;
}
/* Whatever the view shows, the frame the hashes read is the same bytes as before and outside the bands the same pixels. */
static void check_source_untouched(const RrNgFixMask *m) {
    memcpy(copy, picture, sizeof picture);
    const uint32_t *shown = rr_ng_fixmask_view(m, picture, view);
    assert(!memcmp(copy, picture, sizeof picture));
    for (unsigned y = 0; y < H; ++y) for (unsigned x = 8; x < W - 8; ++x) assert(shown[y * W + x] == picture[y * W + x]);
}

int main(void) {
    RrNgFixMask m;
    /* A grey right mask next to a dark picture: shown untouched for 29 frames, painted black from the 30th. */
    fill(DARK_BLUE);
    rr_ng_fixmask_reset(&m);
    run(&m, 29, 0, 0, NEAR_BLACK, GREY);
    assert(!m.latched[LEFT] && !m.latched[RIGHT]);
    assert(rr_ng_fixmask_view(&m, picture, view) == picture);          /* no copy while nothing is latched */
    run(&m, 1, 0, 0, NEAR_BLACK, GREY);
    assert(m.latched[RIGHT] && !m.latched[LEFT]);
    const uint32_t *shown = rr_ng_fixmask_view(&m, picture, view);
    assert(shown == view && band_black(shown, W - 8) && band_untouched(shown, 0));
    check_source_untouched(&m);
    assert(picture[W - 8] == DARK_BLUE);                                 /* the frame itself still holds its pixels */
    /* Both sides, one orange and one grey. */
    rr_ng_fixmask_reset(&m);
    run(&m, 30, 0, 0, GREY, ORANGE);
    shown = rr_ng_fixmask_view(&m, picture, view);
    assert(m.latched[LEFT] && m.latched[RIGHT] && band_black(shown, 0) && band_black(shown, W - 8));
    check_source_untouched(&m);
    /* A black or near-black mask is the legitimate overscan: never touched, however long it lasts. */
    rr_ng_fixmask_reset(&m);
    run(&m, 500, 0, 0, NEAR_BLACK, 0xff000000u);
    assert(!m.latched[LEFT] && !m.latched[RIGHT] && rr_ng_fixmask_view(&m, picture, view) == picture);
    /* Picture tiles in the edge columns (not solid): never. A tile with index 0 (transparent) too. */
    rr_ng_fixmask_reset(&m);
    for (unsigned n = 0; n < 200; ++n) {
        for (unsigned row = 2; row < 30; ++row) { note_picture(&m, LEFT, row); note(&m, RIGHT, row, 1, 0, GREY); }
        rr_ng_fixmask_frame(&m, picture);
    }
    assert(!m.latched[LEFT] && !m.latched[RIGHT]);
    /* 26 of 28 rows are enough, 25 are not. */
    rr_ng_fixmask_reset(&m);
    run(&m, 30, 2, 3, GREY, GREY);
    assert(m.latched[LEFT] && !m.latched[RIGHT]);
    /* Two palettes in the column: no tile holds 26 rows. */
    rr_ng_fixmask_reset(&m);
    for (unsigned n = 0; n < 60; ++n) {
        for (unsigned row = 2; row < 30; ++row) note(&m, RIGHT, row, row < 16 ? 1 : 2, 3, GREY);
        rr_ng_fixmask_frame(&m, picture);
    }
    assert(!m.latched[RIGHT]);
    /* A full-screen flash (the picture beside the band is as bright as the band): never. */
    fill(GREY);
    rr_ng_fixmask_reset(&m);
    run(&m, 300, 0, 0, GREY, GREY);
    assert(!m.latched[LEFT] && !m.latched[RIGHT]);
    fill(0xffd0d0d0u);
    run(&m, 300, 0, 0, GREY, GREY);
    assert(!m.latched[LEFT] && !m.latched[RIGHT]);
    /* Matching frames must be consecutive: 29 + a gap + 29 never latches. */
    fill(DARK_BLUE);
    rr_ng_fixmask_reset(&m);
    run(&m, 29, 0, 0, GREY, GREY);
    run_empty(&m, 1);
    run(&m, 29, 0, 0, GREY, GREY);
    assert(!m.latched[LEFT] && !m.latched[RIGHT]);
    run(&m, 1, 0, 0, GREY, GREY);
    assert(m.latched[LEFT] && m.latched[RIGHT]);
    /* Release: 119 frames that do not match keep the band black (no flicker mid-scene), the 120th gives the picture back,
     * and a matching frame in between restarts the count. */
    rr_ng_fixmask_reset(&m);
    run(&m, 30, 0, 0, GREY, GREY);
    run_empty(&m, 119);
    assert(m.latched[LEFT] && m.latched[RIGHT]);
    run(&m, 1, 0, 0, GREY, GREY);
    run_empty(&m, 119);
    assert(m.latched[LEFT] && m.latched[RIGHT]);
    run_empty(&m, 1);
    assert(!m.latched[LEFT] && !m.latched[RIGHT] && rr_ng_fixmask_view(&m, picture, view) == picture);
    /* A flash while latched (the band no longer differs from its neighbour) is a non-matching stretch shorter than 120. */
    run(&m, 30, 0, 0, GREY, GREY);
    assert(m.latched[LEFT] && m.latched[RIGHT]);
    fill(GREY);
    run(&m, 40, 0, 0, GREY, GREY);
    assert(m.latched[LEFT] && m.latched[RIGHT]);
    fill(DARK_BLUE);
    /* A reset (a state loaded, a restart) forgets the latch and what was noted. */
    rr_ng_fixmask_reset(&m);
    assert(!m.latched[LEFT] && !m.latched[RIGHT] && rr_ng_fixmask_view(&m, picture, view) == picture);
    /* Notes outside the visible rows or sides are ignored. */
    rr_ng_fixmask_reset(&m);
    for (unsigned n = 0; n < 60; ++n) {
        for (unsigned row = 0; row < 32; ++row) {
            if (row >= 2 && row < 30) note(&m, 2, row, 1, 3, GREY);          /* no such side */
            else note(&m, RIGHT, row, 1, 3, GREY);                          /* the rows above and below the picture */
        }
        rr_ng_fixmask_frame(&m, picture);
    }
    assert(!m.latched[LEFT] && !m.latched[RIGHT]);
    puts("{\"neogeo_fixmask\":\"ok\"}");
    return 0;
}
