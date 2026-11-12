/* TMS9918A picture, one line at a time (MSX1). MIT, Retro-Recomp.
 *
 * Written from the TMS9918A data manual (Texas Instruments) and Sean Young's notes on its undocumented behaviour;
 * openMSX was read to settle the sprite rules (SpriteChecker.cc), nothing was copied from it. The line functions are
 * shared with the V9938 (msx_tiles.inc); this file gives them the TMS9918A's table addresses.
 *
 * Modes: Graphic 1, Graphic 2 with the table masks of R#3 and R#4 (on the TMS99xx R#3's low five bits also mask the
 * pattern address bits 6-10), Text 1 (40 x 6-pixel columns from x = 6 on the MSX1 VDP), Multicolor. The undocumented mode-bit mixes are drawn as the first documented mode their bits select (not
 * modelled). Sprites: 32 attribute entries, Y = 208 ends the list, displayed from line Y + 1 (wrapping, so Y = 255 is
 * line 0), 8 x 8 or 16 x 16, magnified x 2, early clock (x - 32), at most four per line (lower numbers in front), the
 * fifth-sprite flag with the number of the first fifth sprite (set only while the frame flag and the fifth-sprite flag
 * are clear; otherwise the low bits hold the last sprite number processed), and the collision flag for two sprite
 * pixels that meet inside the 256 visible columns (colour 0 sprites collide too). No sprites in text mode or with the
 * display off. A line is drawn with the registers and VRAM as they are when the line ends (line granularity). */
#include "msx_machine.h"

#include <string.h>

#include "msx_tiles.inc"

/* The TMS9918A's table addresses as the shared line functions take them. */
static void tms_params(const MsxVdp *v, MsxTileParams *t)
{
    memset(t, 0, sizeof *t);
    t->vram = v->vram;
    t->mask = 0x3FFF;
    t->names = (uint32_t)(v->reg[2] & 0x0F) << 10;
    t->patterns = (uint32_t)(v->reg[4] & 7) << 11;
    t->colours = (uint32_t)v->reg[3] << 6;
    /* Graphic 2: R#3's low five bits also mask the pattern address bits 6-10 on the TMS99xx. */
    t->pattern_or = (v->reg[4] & 4u) << 11;
    t->pattern_and = ((v->reg[4] & 3u) << 11) | ((v->reg[3] & 0x1Fu) << 6) | 0x3Fu;
    t->colour_or = (v->reg[3] & 0x80u) << 6;
    t->colour_and = ((v->reg[3] & 0x7Fu) << 6) | 0x3Fu;
    t->text_left = 6;
    t->sprite_attributes = (uint32_t)(v->reg[5] & 0x7F) << 7;
    t->sprite_patterns = (uint32_t)(v->reg[6] & 7) << 11;
    t->sprite_size = v->reg[1] & 3;
    t->colour0_collides = 1;                 /* colour-0 sprites never show but collide */
}

static int tms_mode(const MsxVdp *v)
{
    if (v->reg[1] & 0x10) return MSX_TILE_T1;
    if (v->reg[1] & 0x08) return MSX_TILE_MC;
    return (v->reg[0] & 0x02) ? MSX_TILE_G2 : MSX_TILE_G1;
}

void msx_vdp_draw_line(MsxMachine *m, int line)
{
    MsxVdp *v = &m->vdp;
    uint8_t *pixels = v->frame[line];
    uint8_t backdrop = v->reg[7] & 15;
    v->border[line] = backdrop;
    if (!(v->reg[1] & 0x40)) {               /* display off: the line is the border colour */
        memset(pixels, backdrop, MSX_WIDTH);
        return;
    }
    MsxTileParams t;
    tms_params(v, &t);
    int mode = tms_mode(v);
    msx_tiles_line(&t, mode, line, v->reg[7] >> 4, backdrop, pixels);
    if (mode != MSX_TILE_T1)                 /* no sprites in text mode */
        msx_sprites1_line(&t, line, &v->status, pixels);
    for (int x = 0; x < MSX_WIDTH; ++x)      /* colour 0 shows the backdrop */
        if (!pixels[x])
            pixels[x] = backdrop;
}

void msx_vdp_check_line(MsxMachine *m, int line)
{
    MsxVdp *v = &m->vdp;
    if ((v->reg[1] & 0x40) && !(v->reg[1] & 0x10)) {
        MsxTileParams t;
        tms_params(v, &t);
        msx_sprites1_line(&t, line, &v->status, NULL);
    }
}
