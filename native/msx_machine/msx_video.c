/* TMS9918A picture, one line at a time (MSX1). MIT, Retro-Recomp.
 *
 * Written from the TMS9918A data manual (Texas Instruments) and Sean Young's notes on its undocumented behaviour;
 * openMSX was read to settle the sprite rules (SpriteChecker.cc), nothing was copied from it.
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

typedef struct {
    int x;
    uint16_t bits;      /* pattern row, 16 bits, left pixel in bit 15, before magnification */
    uint8_t colour;
} LineSprite;

static int sprite_row_bits(const MsxVdp *v, uint8_t pattern, int row, int big, uint16_t *bits)
{
    uint16_t base = (uint16_t)((v->reg[6] & 7) << 11);
    if (big) {
        pattern &= 0xFC;
        uint8_t left = v->vram[(base + pattern * 8 + row) & 0x3FFF];
        uint8_t right = v->vram[(base + pattern * 8 + 16 + row) & 0x3FFF];
        *bits = (uint16_t)(left << 8 | right);
    } else {
        *bits = (uint16_t)(v->vram[(base + pattern * 8 + row) & 0x3FFF] << 8);
    }
    return 0;
}

/* Evaluate the sprites of one line: the status flags always, the pixels when `pixels` is given (line 192 is
 * evaluated for the flags only, before the frame flag rises, as the VDP checks a line one line ahead). */
static void draw_sprites(MsxVdp *v, int line, uint8_t *pixels)
{
    int big = (v->reg[1] >> 1) & 1, mag = v->reg[1] & 1;
    int size = big ? 16 : 8, shown = size << mag;
    uint16_t table = (uint16_t)((v->reg[5] & 0x7F) << 7);
    LineSprite visible[4];
    int count = 0, fifth = -1, sprite = 0;
    for (; sprite < 32; ++sprite) {
        const uint8_t *a = &v->vram[(table + sprite * 4) & 0x3FFF];
        if (a[0] == 208)
            break;
        int row = (line - 1 - a[0]) & 0xFF;
        if (row >= shown)
            continue;
        if (count == 4) {                    /* a fifth sprite on this line: not drawn; the scan goes on to Y = 208 */
            if (fifth < 0)
                fifth = sprite;
            continue;
        }
        LineSprite *s = &visible[count++];
        sprite_row_bits(v, a[2], row >> mag, big, &s->bits);
        s->x = a[1] - ((a[3] & 0x80) ? 32 : 0);
        s->colour = a[3] & 15;
    }
    if (fifth >= 0 && !(v->status & 0xC0))
        v->status = (uint8_t)(0x40 | (v->status & 0x20) | fifth);
    if (!(v->status & 0x40))
        v->status = (uint8_t)((v->status & 0xE0) | (sprite < 31 ? sprite : 31));
    if (count == 0)
        return;
    uint8_t hit[MSX_WIDTH], painted[MSX_WIDTH];
    memset(hit, 0, sizeof hit);
    memset(painted, 0, sizeof painted);
    for (int i = 0; i < count; ++i) {
        const LineSprite *s = &visible[i];
        for (int p = 0; p < shown; ++p) {
            int x = s->x + p;
            if (x < 0 || x >= MSX_WIDTH || !(s->bits & (0x8000u >> (p >> mag))))
                continue;
            if (hit[x])
                v->status |= 0x20;           /* two sprite pixels meet: collision, whatever their colours */
            hit[x] = 1;
            if (pixels && s->colour && !painted[x]) {  /* the lower-numbered visible pixel stays in front; colour 0 is clear */
                pixels[x] = s->colour;
                painted[x] = 1;
            }
        }
    }
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
    int text = (v->reg[1] >> 4) & 1, multicolour = (v->reg[1] >> 3) & 1, graphic2 = (v->reg[0] >> 1) & 1;
    uint16_t names = (uint16_t)((v->reg[2] & 0x0F) << 10);
    int y = line, cell = y >> 3, fine = y & 7;
    if (text) {
        uint16_t patterns = (uint16_t)((v->reg[4] & 7) << 11);
        uint8_t fg = v->reg[7] >> 4, bg = backdrop;
        memset(pixels, backdrop, MSX_WIDTH);
        for (int column = 0; column < 40; ++column) {
            uint8_t name = v->vram[(names + cell * 40 + column) & 0x3FFF];
            uint8_t bits = v->vram[(patterns + name * 8 + fine) & 0x3FFF];
            for (int p = 0; p < 6; ++p) {
                uint8_t c = (bits & (0x80 >> p)) ? fg : bg;
                pixels[6 + column * 6 + p] = c ? c : backdrop;
            }
        }
        return;                              /* no sprites in text mode */
    }
    for (int column = 0; column < 32; ++column) {
        uint8_t name = v->vram[(names + cell * 32 + column) & 0x3FFF];
        uint8_t bits, colours;
        if (multicolour) {
            uint16_t patterns = (uint16_t)((v->reg[4] & 7) << 11);
            uint8_t block = v->vram[(patterns + name * 8 + (cell & 3) * 2 + (fine >> 2)) & 0x3FFF];
            bits = 0xF0;
            colours = block;
        } else if (graphic2) {
            unsigned index = (unsigned)((cell >> 3) << 8 | name);
            unsigned pattern = ((v->reg[4] & 4u) << 11)
                             | ((index << 3) & (((v->reg[4] & 3u) << 11) | ((v->reg[3] & 0x1Fu) << 6) | 0x3Fu)) | (unsigned)fine;
            unsigned colour = ((v->reg[3] & 0x80u) << 6) | ((index << 3) & (((v->reg[3] & 0x7Fu) << 6) | 0x3Fu)) | (unsigned)fine;
            bits = v->vram[pattern & 0x3FFF];
            colours = v->vram[colour & 0x3FFF];
        } else {
            uint16_t patterns = (uint16_t)((v->reg[4] & 7) << 11);
            bits = v->vram[(patterns + name * 8 + fine) & 0x3FFF];
            colours = v->vram[((v->reg[3] << 6) + (name >> 3)) & 0x3FFF];
        }
        for (int p = 0; p < 8; ++p) {
            uint8_t c = (bits & (0x80 >> p)) ? colours >> 4 : colours & 15;
            pixels[column * 8 + p] = c ? c : backdrop;
        }
    }
    draw_sprites(v, line, pixels);
}

void msx_vdp_check_line(MsxMachine *m, int line)
{
    MsxVdp *v = &m->vdp;
    if ((v->reg[1] & 0x40) && !(v->reg[1] & 0x10))
        draw_sprites(v, line, NULL);
}
