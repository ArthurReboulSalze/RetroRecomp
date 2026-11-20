/* The sprite scan of the LSPC, resolved once per change of the sprite tables instead of 381 times per line. Original work: MIT.
 *
 * Geolith's `geo_lspc_sprcalc` walks the 381 sprites for every scanline: for each it reads SCB2, SCB3 and SCB4, follows the chain
 * bit and tests whether the line falls inside the sprite. Games rewrite those tables once a frame (in the blanking), so the 381
 * decoded entries and the list of sprites that touch each line are the same for the 240 lines that follow. This keeps them, keyed
 * by a byte comparison of the three tables (3 KiB) made at every line: a write by any path (the data port, a state load, a
 * rollback, a reset) shows there, nothing has to be hooked. The result of the scan is the same list of sprites in the same order
 * with the same values; the per-sprite work (tile map, palette, auto-animation, pixels, the sprite limit) stays in LSPC as it was.
 *
 * Where the tables change within a few lines of each other (a raster effect rewriting them), the original scan runs instead: the
 * list is built only after RR_NG_SCAN_CLEAN lines without a change, so a game that rewrites them every line never pays for it. */
#ifndef RR_NEOGEO_SPRITE_SCAN_H
#define RR_NEOGEO_SPRITE_SCAN_H
#include <stdint.h>
#include <string.h>

enum { RR_NG_SCAN_SPRITES = 381, RR_NG_SCAN_LINES = 242, RR_NG_SCAN_WORDS = 0x600, RR_NG_SCAN_CLEAN = 3 };

typedef struct {
    uint32_t xpos;          /* a chained position is not masked here, as in the scan: it is where it is used */
    uint16_t ypos, sprsize, vshrink, hshrink;
} RrNgScanSprite;

typedef struct {
    uint16_t shadow[RR_NG_SCAN_WORDS];                 /* SCB2, SCB3 and SCB4 as the list was built from them */
    RrNgScanSprite sprite[RR_NG_SCAN_SPRITES + 1];     /* index 1..381 as in the tables */
    uint32_t start[RR_NG_SCAN_LINES + 1];              /* the first entry of each line in `index` */
    uint16_t index[RR_NG_SCAN_SPRITES * RR_NG_SCAN_LINES];
    unsigned clean;                                    /* lines seen since the tables last changed */
    int built;
} RrNgSpriteScan;

static RrNgSpriteScan rr_ng_scan;

/* The three tables are the 0x600 words at 0x8000 of the video RAM: SCB2 (zoom), SCB3 (Y, size, chain), SCB4 (X). */
static void rr_ng_scan_build(const uint16_t *scb) {
    RrNgSpriteScan *s = &rr_ng_scan;
    unsigned xpos = 0, ypos = 0, sprsize = 0, hshrink = 0x0f, vshrink = 0xff;
    uint32_t count[RR_NG_SCAN_LINES];
    memset(count, 0, sizeof count);
    for (unsigned i = 1; i <= RR_NG_SCAN_SPRITES; ++i) {
        if (scb[0x200 + i] & 0x40) xpos += (hshrink + 1);                  /* chained: the edge of the previous one */
        else {
            xpos = (scb[0x400 + i] >> 7) & 0x1ff;
            ypos = (scb[0x200 + i] >> 7) & 0x1ff;
            sprsize = scb[0x200 + i] & 0x3f;
            vshrink = scb[i] & 0xff;
        }
        hshrink = (scb[i] >> 8) & 0x0f;
        RrNgScanSprite *e = &s->sprite[i];
        e->xpos = xpos; e->ypos = (uint16_t)ypos; e->sprsize = (uint16_t)sprsize; e->vshrink = (uint16_t)vshrink;
        e->hshrink = (uint16_t)hshrink;
        if (!sprsize) continue;
        /* The lines of the sprite are those where (line - (0x200 - ypos)) & 0x1ff is below sprsize * 16. */
        unsigned rows = sprsize << 4;
        if (rows > 0x200) rows = 0x200;
        unsigned line = (0x200 - ypos) & 0x1ff;
        for (unsigned r = 0; r < rows; ++r, line = (line + 1) & 0x1ff)
            if (line < RR_NG_SCAN_LINES) ++count[line];
    }
    uint32_t at[RR_NG_SCAN_LINES], total = 0;
    for (unsigned l = 0; l < RR_NG_SCAN_LINES; ++l) { s->start[l] = total; at[l] = total; total += count[l]; }
    s->start[RR_NG_SCAN_LINES] = total;
    for (unsigned i = 1; i <= RR_NG_SCAN_SPRITES; ++i) {
        const RrNgScanSprite *e = &s->sprite[i];
        if (!e->sprsize) continue;
        unsigned rows = (unsigned)e->sprsize << 4;
        if (rows > 0x200) rows = 0x200;
        unsigned line = (0x200 - e->ypos) & 0x1ff;
        for (unsigned r = 0; r < rows; ++r, line = (line + 1) & 0x1ff)
            if (line < RR_NG_SCAN_LINES) s->index[at[line]++] = (uint16_t)i;
    }
}

/* Nonzero when the list of `line` can be used (then rr_ng_scan_first / rr_ng_scan_end bound it). `scb` is &vram[0x8000]. */
static inline int rr_ng_scan_ready(const uint16_t *scb, unsigned line) {
    RrNgSpriteScan *s = &rr_ng_scan;
    if (memcmp(s->shadow, scb, sizeof s->shadow)) {
        memcpy(s->shadow, scb, sizeof s->shadow);
        s->clean = 0; s->built = 0;
        return 0;
    }
    if (line >= RR_NG_SCAN_LINES) return 0;
    if (!s->built) {
        if (++s->clean < RR_NG_SCAN_CLEAN) return 0;
        rr_ng_scan_build(s->shadow);
        s->built = 1;
    }
    return 1;
}
#endif
