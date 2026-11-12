/* The V9938's picture, one line at a time (MSX2). MIT, Retro-Recomp.
 *
 * Written from the V9938 Technical Data Book; openMSX (SpriteChecker.cc, SpriteConverter.hh, VDP.hh) was read to settle
 * what the book leaves open, nothing was copied from it. A line is drawn at its draw point (msx_v9938.c) with the
 * registers, palette and VRAM of that instant, as 512 colours of 9 bits (0GGG0RRR0BBB, the palette applied: a split
 * that changes the palette between lines shows); a 256-pixel mode is doubled.
 *
 * Modes: Graphic 1, Graphic 2, Multicolor and Text 1 through msx_tiles.inc (shared with the TMS9918A) on the V9938's
 * table addresses; Graphic 3 (Graphic 2 with sprite mode 2); Text 2 (80 columns, blink attributes and R#12's colours);
 * Graphic 4 (256 x 4 bits), 5 (512 x 2 bits), 6 (512 x 4 bits), 7 (256 x 8 bits, colours GGGRRRBB). The vertical
 * scroll R#23 picks the picture row; R#2 the page of the bitmap modes, its low bit alternating with R#13 or on even
 * fields with R#9 EO. Colour 0 shows the backdrop, or palette 0 with TP (R#8 bit 5); Graphic 7 has no transparency.
 *
 * Sprite mode 1 in G1, G2 and MC (msx_tiles.inc; colour-0 sprites drawn and colliding only with TP); sprite mode 2 in
 * G3-G7: 8 per line, Y = 216 ends the list, a colour byte per row (EC, CC, IC, colour), sprites with CC set OR their
 * colour into the sprite before them and show only after a sprite with CC clear, collisions between sprites with CC
 * and IC clear (colour 0 only with TP) with the coordinates x + 12, y + 8 in S#3-S#6. Where hardware reports disagree,
 * the rules follow openMSX's reading ("follows openMSX" in docs/MSX.md). */
#include "msx_machine.h"

#include <string.h>

#include "msx_tiles.inc"

enum { MODE_G1 = 0x00, MODE_T1 = 0x01, MODE_MC = 0x02, MODE_G2 = 0x04, MODE_G3 = 0x08, MODE_T2 = 0x09,
       MODE_G4 = 0x0C, MODE_G5 = 0x10, MODE_G6 = 0x14, MODE_G7 = 0x1C };

static int mode_number(const MsxV9938 *v)
{
    return ((v->reg[0] & 0x0E) << 1) | ((v->reg[1] >> 2) & 2) | ((v->reg[1] >> 4) & 1);
}

/* A Graphic 7 byte GGGRRRBB as a 9-bit colour; blue's two bits widen to 0, 2, 4, 7. */
static uint16_t g7_colour(uint8_t byte)
{
    static const uint8_t blue[4] = { 0, 2, 4, 7 };
    return (uint16_t)(((byte >> 5) << 8) | (((byte >> 2) & 7) << 4) | blue[byte & 3]);
}

/* The fixed colours of the sprites in Graphic 7 (data book, sprite colours of screen 8). */
static const uint16_t g7_sprite_colours[16] = {
    0x000, 0x002, 0x030, 0x032, 0x300, 0x302, 0x330, 0x332,
    0x472, 0x007, 0x070, 0x077, 0x700, 0x707, 0x770, 0x777,
};

static void v9938_tile_params(const MsxV9938 *v, MsxTileParams *t, int tp)
{
    memset(t, 0, sizeof *t);
    t->vram = v->vram;
    t->mask = MSX2_VRAM - 1;
    t->names = (uint32_t)(v->reg[2] & 0x7F) << 10;
    t->patterns = (uint32_t)(v->reg[4] & 0x3F) << 11;
    t->colours = ((uint32_t)(v->reg[10] & 7) << 14) | ((uint32_t)v->reg[3] << 6);
    /* Graphic 2 / 3: the table registers act as masks on the 13-bit index; no R#3 leak into the patterns. */
    t->pattern_or = (uint32_t)(v->reg[4] & 0x3C) << 11;
    t->pattern_and = ((uint32_t)(v->reg[4] & 3) << 11) | 0x7FFu;
    t->colour_or = ((uint32_t)(v->reg[10] & 7) << 14) | ((uint32_t)(v->reg[3] & 0x80) << 6);
    t->colour_and = ((uint32_t)(v->reg[3] & 0x7F) << 6) | 0x3Fu;
    t->text_left = 9;
    t->sprite_attributes = ((uint32_t)(v->reg[11] & 3) << 15) | ((uint32_t)v->reg[5] << 7);
    t->sprite_patterns = (uint32_t)(v->reg[6] & 0x3F) << 11;
    t->sprite_size = v->reg[1] & 3;
    t->sprite_colour0 = (uint8_t)tp;
    t->colour0_collides = (uint8_t)tp;
}

/* ---- sprite mode 2 ---- */

typedef struct {
    int x;
    uint16_t bits;
    uint8_t attr;       /* EC 80h, CC 40h, IC 20h, colour 0Fh */
} Sprite2;

/* The sprites of one line (`sline` = the line after the vertical scroll), the status flags, and when `layer` is given
 * the colour of each of the 256 columns (bit 4 set where a sprite shows). */
static void sprites2(MsxMachine *m, int line, int sline, uint8_t *layer)
{
    MsxV9938 *v = m->v9938;
    int planar = msx_v9938_interleaved(v->reg);  /* in G6/G7 the sprite tables are read through the interleave too */
#define SPRITE_VRAM(a) (v->vram[msx_v9938_physical((a), planar)])
    int tp = (v->reg[8] & 0x20) != 0;
    int big = (v->reg[1] >> 1) & 1, mag = v->reg[1] & 1;
    int size = big ? 16 : 8, shown = size << mag;
    uint32_t base = (((uint32_t)(v->reg[11] & 3) << 15) | ((uint32_t)v->reg[5] << 7)) & ~0x3FFu;
    uint32_t patterns = (uint32_t)(v->reg[6] & 0x3F) << 11, mask = MSX2_VRAM - 1;
    Sprite2 visible[8];
    int count = 0, ninth = -1, sprite = 0;
    for (; sprite < 32; ++sprite) {
        uint32_t a = base + 0x200 + (uint32_t)sprite * 4;
        uint8_t y = SPRITE_VRAM(a & mask);
        if (y == 216)
            break;
        int row = (sline - 1 - y) & 0xFF;
        if (row >= shown)
            continue;
        if (count == 8) {
            if (ninth < 0)
                ninth = sprite;
            continue;
        }
        Sprite2 *s = &visible[count++];
        int r = row >> mag;
        uint8_t pattern = SPRITE_VRAM((a + 2) & mask);
        if (big) {
            pattern &= 0xFC;
            s->bits = (uint16_t)(SPRITE_VRAM((patterns + pattern * 8u + (uint32_t)r) & mask) << 8
                                 | SPRITE_VRAM((patterns + pattern * 8u + 16u + (uint32_t)r) & mask));
        } else {
            s->bits = (uint16_t)(SPRITE_VRAM((patterns + pattern * 8u + (uint32_t)r) & mask) << 8);
        }
        s->attr = SPRITE_VRAM((base + (uint32_t)sprite * 16 + (uint32_t)r) & mask);
        s->x = SPRITE_VRAM((a + 1) & mask) - ((s->attr & 0x80) ? 32 : 0);
    }
#undef SPRITE_VRAM
    if (ninth >= 0 && !(v->status0 & 0xC0))
        v->status0 = (uint8_t)(0x40 | (v->status0 & 0x20) | ninth);
    if (!(v->status0 & 0x40))
        v->status0 = (uint8_t)((v->status0 & 0xE0) | (sprite < 31 ? sprite : 31));
    if (!count)
        return;
    /* Collisions: the first pair of sprites with CC and IC clear (colour 0 only with TP) whose pixels meet inside the
     * 256 columns; the leftmost column of this line; nothing more while the flag is set. */
    if (!(v->status0 & 0x20)) {
        int first_x = 999;
        for (int i = 0; i < count; ++i) {
            if ((visible[i].attr & 0x60) || (!tp && !(visible[i].attr & 0x0F)))
                continue;
            for (int j = i + 1; j < count; ++j) {
                if ((visible[j].attr & 0x60) || (!tp && !(visible[j].attr & 0x0F)))
                    continue;
                for (int p = 0; p < shown; ++p) {
                    int x = visible[i].x + p;
                    if (x < 0 || x >= MSX_WIDTH || x >= first_x)
                        continue;
                    int q = x - visible[j].x;
                    if (q < 0 || q >= shown)
                        continue;
                    if ((visible[i].bits & (0x8000u >> (p >> mag))) && (visible[j].bits & (0x8000u >> (q >> mag))))
                        first_x = x;
                }
            }
        }
        if (first_x != 999) {
            v->status0 |= 0x20;
            v->collision_x = (uint16_t)(first_x + 12);
            v->collision_y = (uint16_t)(line + 8);
        }
    }
    if (!layer)
        return;
    /* Drawing: CC sprites before the first CC-clear sprite do not show; from the last sprite to that first one, each
     * pixel takes the sprite's colour OR-ed with the CC sprites that directly follow it and have a pixel there, so the
     * lower numbers end in front. A colour-0 sprite is skipped unless TP is set. */
    int first = 0;
    while (first < count && (visible[first].attr & 0x40))
        ++first;
    for (int i = count - 1; i >= first; --i) {
        const Sprite2 *s = &visible[i];
        uint8_t c = s->attr & 0x0F;
        if (!c && !tp)
            continue;
        for (int p = 0; p < shown; ++p) {
            int x = s->x + p;
            if (x < 0 || x >= MSX_WIDTH || !(s->bits & (0x8000u >> (p >> mag))))
                continue;
            uint8_t colour = c;
            for (int j = i + 1; j < count && (visible[j].attr & 0x40); ++j) {
                int q = x - visible[j].x;
                if (q >= 0 && q < shown && (visible[j].bits & (0x8000u >> (q >> mag))))
                    colour |= visible[j].attr & 0x0F;
            }
            layer[x] = (uint8_t)(0x10 | colour);
        }
    }
}

/* ---- the line ---- */

static void fill(uint16_t *out, uint16_t even, uint16_t odd)
{
    for (int x = 0; x < MSX2_WIDTH; x += 2) {
        out[x] = even;
        out[x + 1] = odd;
    }
}

void msx_v9938_draw_line(MsxMachine *m, int line)
{
    MsxV9938 *v = m->v9938;
    uint16_t *out = v->frame[line];
    int mode = mode_number(v);
    int tp = (v->reg[8] & 0x20) != 0;
    uint8_t backdrop = v->reg[7] & 0x0F;
    uint16_t border_even, border_odd;
    if (mode == MODE_G7) {
        border_even = border_odd = g7_colour(v->reg[7]);
    } else if (mode == MODE_G5) {
        border_even = v->palette[(v->reg[7] >> 2) & 3];
        border_odd = v->palette[v->reg[7] & 3];
    } else {
        border_even = border_odd = v->palette[backdrop];
    }
    v->border[line][0] = border_even;
    v->border[line][1] = border_odd;
    v->line_mode[line] = (uint8_t)mode;
    if (!(v->reg[1] & 0x40)) {                 /* display off: the line is the border */
        fill(out, border_even, border_odd);
        return;
    }
    int y = (line + v->reg[23]) & 0xFF;
    uint16_t zero = tp ? v->palette[0] : v->palette[backdrop];
    uint8_t idx[MSX_WIDTH];
    switch (mode) {
    case MODE_G1: case MODE_G2: case MODE_G3: case MODE_MC: case MODE_T1: {
        MsxTileParams t;
        v9938_tile_params(v, &t, tp);
        int tile = mode == MODE_T1 ? MSX_TILE_T1 : mode == MODE_MC ? MSX_TILE_MC : mode == MODE_G1 ? MSX_TILE_G1 : MSX_TILE_G2;
        msx_tiles_line(&t, tile, y, v->reg[7] >> 4, backdrop, idx);
        uint8_t layer[MSX_WIDTH];
        memset(layer, 0, sizeof layer);
        if (mode == MODE_G3) {
            if (!(v->reg[8] & 0x02))
                sprites2(m, line, y, layer);
        } else if (mode != MODE_T1 && !(v->reg[8] & 0x02)) {
            uint8_t plain[MSX_WIDTH];
            memset(plain, 0xFF, sizeof plain);       /* mode 1: 0FFh marks "no sprite" */
            msx_sprites1_line(&t, y, &v->status0, plain);
            for (int x = 0; x < MSX_WIDTH; ++x)
                if (plain[x] != 0xFF)
                    layer[x] = (uint8_t)(0x10 | plain[x]);
        }
        for (int x = 0; x < MSX_WIDTH; ++x) {
            uint8_t c = (layer[x] & 0x10) ? (layer[x] & 0x0F) : idx[x];
            uint16_t colour = c ? v->palette[c] : zero;
            if (mode == MODE_T1 && (x < t.text_left || x >= t.text_left + 240))
                colour = v->palette[backdrop];
            out[2 * x] = out[2 * x + 1] = colour;
        }
        return;
    }
    case MODE_T2: {
        uint32_t names = ((uint32_t)(v->reg[2] & 0x7C) << 10), mask = MSX2_VRAM - 1;
        uint32_t patterns = (uint32_t)(v->reg[4] & 0x3F) << 11;
        uint32_t blinks = (((uint32_t)(v->reg[10] & 7) << 14) | ((uint32_t)v->reg[3] << 6)) & ~0x1FFu;
        int row = y >> 3, fine = y & 7;
        fill(out, v->palette[backdrop], v->palette[backdrop]);
        for (int column = 0; column < 80; ++column) {
            uint32_t at = (uint32_t)(row * 80 + column);
            uint8_t name = v->vram[(names + at) & mask];
            uint8_t bits = v->vram[(patterns + name * 8u + (uint32_t)fine) & mask];
            uint8_t fg = v->reg[7] >> 4, bg = backdrop;
            if (v->blink_on && (v->vram[(blinks + at / 8) & mask] & (0x80 >> (at & 7)))) {
                fg = v->reg[12] >> 4;
                bg = v->reg[12] & 0x0F;
            }
            for (int p = 0; p < 6; ++p) {
                uint8_t c = (bits & (0x80 >> p)) ? fg : bg;
                out[18 + column * 6 + p] = c ? v->palette[c] : zero;
            }
        }
        return;                                    /* no sprites in text modes */
    }
    default:
        break;
    }
    /* Bitmap modes: the page (R#2), its low bit cleared while R#13 blinks or on even fields with R#9 EO. */
    int page = (v->reg[2] >> 5) & 3;
    if (v->blink_on || ((v->reg[9] & 0x04) && !(v->status2 & 0x02)))
        page &= ~1;
    uint8_t layer[MSX_WIDTH];
    memset(layer, 0, sizeof layer);
    if (mode == MODE_G4 || mode == MODE_G5 || mode == MODE_G6 || mode == MODE_G7) {
        if (!(v->reg[8] & 0x02))
            sprites2(m, line, y, layer);
    }
    switch (mode) {
    case MODE_G4: {                                /* 256 x 4 bits: two pixels a byte, high nibble first */
        const uint8_t *row = &v->vram[((uint32_t)page << 15) | ((uint32_t)y << 7)];
        for (int x = 0; x < MSX_WIDTH; ++x) {
            uint8_t c = (layer[x] & 0x10) ? (layer[x] & 0x0F) : ((x & 1) ? row[x >> 1] & 0x0F : row[x >> 1] >> 4);
            out[2 * x] = out[2 * x + 1] = c ? v->palette[c] : zero;
        }
        break;
    }
    case MODE_G5: {                                /* 512 x 2 bits: four half-pixels a byte, bits 7-6 first */
        const uint8_t *row = &v->vram[((uint32_t)page << 15) | ((uint32_t)y << 7)];
        uint16_t zero_even = tp ? v->palette[0] : v->palette[(v->reg[7] >> 2) & 3];
        uint16_t zero_odd = tp ? v->palette[0] : v->palette[v->reg[7] & 3];
        for (int h = 0; h < MSX2_WIDTH; ++h) {
            uint8_t c = (uint8_t)((row[h >> 2] >> (6 - 2 * (h & 3))) & 3);
            uint8_t s = layer[h >> 1];
            if (s & 0x10)                          /* a sprite pixel is two half-pixels: colour bits 3-2, then 1-0 */
                c = (h & 1) ? (s & 3) : ((s >> 2) & 3);
            out[h] = c || (s & 0x10) ? v->palette[c] : ((h & 1) ? zero_odd : zero_even);
        }
        break;
    }
    case MODE_G6: {                                /* 512 x 4 bits: two half-pixels a byte, through the interleave */
        uint32_t row = ((uint32_t)(page & 1) << 16) | ((uint32_t)y << 8);
        for (int h = 0; h < MSX2_WIDTH; ++h) {
            uint8_t s = layer[h >> 1], byte = v->vram[msx_v9938_physical(row + (uint32_t)(h >> 1), 1)];
            uint8_t c = (s & 0x10) ? (s & 0x0F) : ((h & 1) ? byte & 0x0F : byte >> 4);
            out[h] = c ? v->palette[c] : zero;
        }
        break;
    }
    case MODE_G7: {                                /* 256 x 8 bits, GGGRRRBB, through the interleave; no transparency */
        uint32_t row = ((uint32_t)(page & 1) << 16) | ((uint32_t)y << 8);
        for (int x = 0; x < MSX_WIDTH; ++x) {
            uint16_t colour = (layer[x] & 0x10) ? g7_sprite_colours[layer[x] & 0x0F]
                                                : g7_colour(v->vram[msx_v9938_physical(row + (uint32_t)x, 1)]);
            out[2 * x] = out[2 * x + 1] = colour;
        }
        break;
    }
    default:                                       /* an undocumented mode mix: the backdrop, no sprites */
        fill(out, v->palette[backdrop], v->palette[backdrop]);
        break;
    }
}
