/* The TMS9918A: ports and picture, one line at a time (tms9918.h). MIT, Retro-Recomp.
 *
 * Written from the TMS9918A data manual (Texas Instruments) and Sean Young's notes on its undocumented behaviour;
 * the sprite rules they leave open were checked against openMSX 22.0 run as a separate program (private comparisons; none of its code or tables is here). The line functions are
 * shared with the V9938 (tms_tiles.inc); this file gives them the TMS9918A's table addresses.
 *
 * Modes: Graphic 1, Graphic 2 with the table masks of R#3 and R#4 (on the TMS99xx R#3's low five bits also mask the
 * pattern address bits 6-10), Text 1 (40 x 6-pixel columns from x = 6 on the MSX1 VDP), Multicolor. The undocumented mode-bit mixes are drawn as the first documented mode their bits select (not
 * modelled). Sprites: 32 attribute entries, Y = 208 ends the list, displayed from line Y + 1 (wrapping, so Y = 255 is
 * line 0), 8 x 8 or 16 x 16, magnified x 2, early clock (x - 32), at most four per line (lower numbers in front), the
 * fifth-sprite flag with the number of the first fifth sprite (set only while the frame flag and the fifth-sprite flag
 * are clear; otherwise the low bits hold the last sprite number processed), and the collision flag for two sprite
 * pixels that meet inside the 256 visible columns (colour 0 sprites collide too). No sprites in text mode or with the
 * display off. A line is drawn with the registers and VRAM as they are when the line ends (line granularity). */
#include "tms9918.h"

#include <string.h>

#include "tms_tiles.inc"

/* The player's choice (F5, off unless asked): the picture also shows the sprites past the fourth of a line. A switch of the host, not
 * part of the chip's state: nothing the program reads, no quick state and no digest changes with it. */
static int tms_all_sprites;
void tms9918_set_all_sprites(int on) { tms_all_sprites = on != 0; }

/* The TMS9918A's table addresses as the shared line functions take them. */
static void tms_params(const Tms9918 *v, TmsTileParams *t)
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
    t->show_all = (uint8_t)tms_all_sprites;
}

static int tms_mode(const Tms9918 *v)
{
    if (v->reg[1] & 0x10) return TMS_TILE_T1;
    if (v->reg[1] & 0x08) return TMS_TILE_MC;
    return (v->reg[0] & 0x02) ? TMS_TILE_G2 : TMS_TILE_G1;
}

void tms9918_draw_line(Tms9918 *v, int line)
{
    uint8_t *pixels = v->frame[line];
    uint8_t backdrop = v->reg[7] & 15;
    v->border[line] = backdrop;
    if (!(v->reg[1] & 0x40)) {               /* display off: the line is the border colour */
        memset(pixels, backdrop, TMS_WIDTH);
        return;
    }
    TmsTileParams t;
    tms_params(v, &t);
    int mode = tms_mode(v);
    tms_tiles_line(&t, mode, line, v->reg[7] >> 4, backdrop, pixels);
    if (mode != TMS_TILE_T1)                 /* no sprites in text mode */
        tms_sprites1_line(&t, line, &v->status, pixels);
    for (int x = 0; x < TMS_WIDTH; ++x)      /* colour 0 shows the backdrop */
        if (!pixels[x])
            pixels[x] = backdrop;
}

void tms9918_check_line(Tms9918 *v, int line)
{
    if ((v->reg[1] & 0x40) && !(v->reg[1] & 0x10)) {
        TmsTileParams t;
        tms_params(v, &t);
        tms_sprites1_line(&t, line, &v->status, NULL);
    }
}

int tms9918_line_end(Tms9918 *v, unsigned *line, unsigned lines_per_frame)
{
    if (*line < TMS_HEIGHT)                  /* the line that just ended is drawn with the state it ended with */
        tms9918_draw_line(v, (int)*line);
    if (*line == TMS_HEIGHT - 1)             /* sprites of line 192: flags only, before the frame flag */
        tms9918_check_line(v, TMS_HEIGHT);
    if (++*line == TMS_VBLANK_LINE)
        v->status |= 0x80;
    if (*line == lines_per_frame) {
        *line = 0;
        return 1;
    }
    return 0;
}

/* The CPU's access. The first control byte sets the low address at once (Sean Young's notes on the TMS99x8), a register
 * write also loads the high address bits, a read setup prefetches a byte, and a status read clears the frame, fifth-sprite
 * and collision flags and the control latch. */
uint8_t tms9918_read_data(Tms9918 *v)
{
    uint8_t value = v->readahead;
    v->readahead = v->vram[v->address];
    v->address = (uint16_t)((v->address + 1) & 0x3FFF);
    v->latch = 0;
    return value;
}

void tms9918_write_data(Tms9918 *v, uint8_t value)
{
    v->vram[v->address] = value;
    v->readahead = value;
    v->address = (uint16_t)((v->address + 1) & 0x3FFF);
    v->latch = 0;
}

uint8_t tms9918_read_status(Tms9918 *v)
{
    uint8_t value = v->status;
    v->status &= 0x1F;        /* the frame flag, the fifth-sprite flag and the collision flag clear on a read */
    v->latch = 0;
    return value;
}

/* Bits the TMS9918A keeps in each register (the others read as zero in our model). */
static const uint8_t tms_masks[8] = { 0x03, 0xFB, 0x0F, 0xFF, 0x07, 0x7F, 0x07, 0xFF };

void tms9918_write_control(Tms9918 *v, uint8_t value)
{
    if (!v->latch) {
        /* The chip has no real latch for the address: the first byte is the low address byte at once. */
        v->address = (uint16_t)((v->address & 0x3F00) | value);
        v->first = value;
        v->latch = 1;
        return;
    }
    v->latch = 0;
    if (value & 0x80) {
        v->reg[value & 7] = (uint8_t)(v->first & tms_masks[value & 7]);
        /* A register write also loads the high address bits (TMS99x8 behaviour some programs rely on). */
        v->address = (uint16_t)(((value << 8) | (v->address & 0xFF)) & 0x3FFF);
    } else {
        v->address = (uint16_t)(v->first | ((value & 0x3F) << 8));
        if (!(value & 0x40)) {     /* read setup: the VDP prefetches the first byte */
            v->readahead = v->vram[v->address];
            v->address = (uint16_t)((v->address + 1) & 0x3FFF);
        }
    }
}
