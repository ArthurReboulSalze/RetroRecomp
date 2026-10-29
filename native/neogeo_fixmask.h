/* Neo Geo fix-layer edge masks: display only. Original RetroRecomp code: MIT.
 *
 * The BIOS draws a solid fix tile (0x0020) in fix columns 0 and 39 as an overscan mask. Most games keep it black; a few
 * leave it coloured (grey, orange) and the 320-column picture then shows a bright band at one or both edges. The
 * maintainer's decision (29 October 2026): keep all 320 columns, never crop, and paint a detected coloured mask band black
 * at display time only.
 *
 * The engine's fix-layer routine notes the two edge tiles of every visible tile row as it draws them (it sees the exact
 * tile after bank switching and the exact palette). At the end of each guest frame the detector asks, per side:
 *   - at least RR_NG_FIXMASK_NEED of the 28 visible tile rows hold one and the same opaque solid tile (one non-zero
 *     palette index over the whole 8 x 8 tile, one palette);
 *   - the band colour is not near black (largest channel above 24);
 *   - the band differs visibly from the picture next to it (mean absolute RGB difference above 60 against column 8 or
 *     311), so a full-screen flash never matches.
 * A per-side latch turns on after RR_NG_FIXMASK_ON consecutive matching frames and off after RR_NG_FIXMASK_OFF
 * consecutive frames that do not match, so the picture never flickers inside a scene. The view paints the 8-pixel band of a
 * latched side black in a copy; the pixels the validation hashes, the reference runs and the checks read are never touched.
 * Nothing here enters a saved state. No per-game list: the rule reads the hardware's own fix map, tile and palette. */
#ifndef RR_NEOGEO_FIXMASK_H
#define RR_NEOGEO_FIXMASK_H
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

enum {
    RR_NG_FIXMASK_WIDTH = 320, RR_NG_FIXMASK_HEIGHT = 224, RR_NG_FIXMASK_BAND = 8,
    RR_NG_FIXMASK_FIRST_ROW = 2, RR_NG_FIXMASK_ROWS = 28, RR_NG_FIXMASK_NEED = 26,
    RR_NG_FIXMASK_ON = 30, RR_NG_FIXMASK_OFF = 120,
    RR_NG_FIXMASK_MIN_CHANNEL = 24, RR_NG_FIXMASK_MIN_STEP = 60
};

typedef struct {
    uint8_t seen[2][RR_NG_FIXMASK_ROWS];       /* a tile of this side and row was drawn since the last frame check */
    uint8_t key[2][RR_NG_FIXMASK_ROWS];        /* palette number << 4 | palette index of its solid tile */
    uint32_t colour[2][RR_NG_FIXMASK_ROWS];    /* the colour that tile paints */
    unsigned matching[2], missing[2];          /* consecutive frames that match / do not match */
    bool latched[2];
} RrNgFixMask;

static inline void rr_ng_fixmask_reset(RrNgFixMask *mask) { memset(mask, 0, sizeof *mask); }

/* Called by the fix-layer routine for the first line of a tile row. entry is the fix-map word, tile the 32 bytes of the
 * tile (four bytes per row, two pixels per byte), palette the 16 colours of its palette. Reads 32 bytes. */
static inline void rr_ng_fixmask_note(RrNgFixMask *mask, unsigned side, unsigned row, unsigned entry,
                                      const uint8_t *tile, const uint32_t *palette) {
    if (side > 1 || row < RR_NG_FIXMASK_FIRST_ROW || row >= RR_NG_FIXMASK_FIRST_ROW + RR_NG_FIXMASK_ROWS) return;
    unsigned slot = row - RR_NG_FIXMASK_FIRST_ROW, index = tile[0] & 15u;
    mask->seen[side][slot] = 1;
    mask->key[side][slot] = 0;
    if (!index) return;
    for (unsigned n = 0; n < 32; ++n)
        if (tile[n] != index * 17u) return;
    mask->key[side][slot] = (uint8_t)(((entry >> 12) & 15u) << 4 | index);
    mask->colour[side][slot] = palette[index];
}

static inline unsigned rr_ng_fixmask_channel_max(uint32_t colour) {
    unsigned r = (colour >> 16) & 255u, g = (colour >> 8) & 255u, b = colour & 255u;
    return r > g ? (r > b ? r : b) : (g > b ? g : b);
}

/* Does the side hold a coloured mask band right now? picture is the 320 x 224 frame the engine drew. */
static inline bool rr_ng_fixmask_candidate(const RrNgFixMask *mask, unsigned side, const uint32_t *picture) {
    uint8_t votes[256];
    memset(votes, 0, sizeof votes);
    unsigned best = 0, best_slot = 0;
    for (unsigned slot = 0; slot < RR_NG_FIXMASK_ROWS; ++slot) {
        unsigned key = mask->key[side][slot];
        if (!mask->seen[side][slot] || !key) continue;
        if (++votes[key] > best) { best = votes[key]; best_slot = slot; }
    }
    if (best < RR_NG_FIXMASK_NEED) return false;
    uint32_t band = mask->colour[side][best_slot];
    if (rr_ng_fixmask_channel_max(band) <= RR_NG_FIXMASK_MIN_CHANNEL) return false;
    unsigned column = side ? RR_NG_FIXMASK_WIDTH - RR_NG_FIXMASK_BAND - 1 : RR_NG_FIXMASK_BAND;
    unsigned long total = 0;
    int br = (int)((band >> 16) & 255u), bg = (int)((band >> 8) & 255u), bb = (int)(band & 255u);
    for (unsigned y = 0; y < RR_NG_FIXMASK_HEIGHT; ++y) {
        uint32_t next = picture[y * RR_NG_FIXMASK_WIDTH + column];
        int dr = br - (int)((next >> 16) & 255u), dg = bg - (int)((next >> 8) & 255u), db = bb - (int)(next & 255u);
        total += (unsigned long)((dr < 0 ? -dr : dr) + (dg < 0 ? -dg : dg) + (db < 0 ? -db : db));
    }
    return total > (unsigned long)RR_NG_FIXMASK_MIN_STEP * RR_NG_FIXMASK_HEIGHT;
}

/* End of a guest frame: update the latches and forget what the fix routine noted. */
static inline void rr_ng_fixmask_frame(RrNgFixMask *mask, const uint32_t *picture) {
    for (unsigned side = 0; side < 2; ++side) {
        if (rr_ng_fixmask_candidate(mask, side, picture)) {
            if (mask->matching[side] < 1000000u) ++mask->matching[side];
            mask->missing[side] = 0;
            if (mask->matching[side] >= RR_NG_FIXMASK_ON) mask->latched[side] = true;
        } else {
            mask->matching[side] = 0;
            if (mask->missing[side] < 1000000u) ++mask->missing[side];
            if (mask->missing[side] >= RR_NG_FIXMASK_OFF) mask->latched[side] = false;
        }
    }
    memset(mask->seen, 0, sizeof mask->seen);
}

/* The picture to show: the frame itself while no band is latched (no copy), else a copy in view with the bands black. */
static inline const uint32_t *rr_ng_fixmask_view(const RrNgFixMask *mask, const uint32_t *picture, uint32_t *view) {
    if (!mask->latched[0] && !mask->latched[1]) return picture;
    memcpy(view, picture, sizeof(uint32_t) * RR_NG_FIXMASK_WIDTH * RR_NG_FIXMASK_HEIGHT);
    for (unsigned side = 0; side < 2; ++side) {
        if (!mask->latched[side]) continue;
        unsigned first = side ? RR_NG_FIXMASK_WIDTH - RR_NG_FIXMASK_BAND : 0;
        for (unsigned y = 0; y < RR_NG_FIXMASK_HEIGHT; ++y)
            for (unsigned x = 0; x < RR_NG_FIXMASK_BAND; ++x) view[y * RR_NG_FIXMASK_WIDTH + first + x] = 0xff000000u;
    }
    return view;
}

/* The one detector of the running game, defined next to the fix-layer routine in the engine's geo_lspc.c. */
extern RrNgFixMask rr_ng_fix_mask;
#endif
