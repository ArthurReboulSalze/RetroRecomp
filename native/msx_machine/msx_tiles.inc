/* The legacy screen modes and mode-1 sprites, one line at a time, shared by the TMS9918A (msx_video.c) and the V9938
 * (msx_v9938_draw.c). MIT, Retro-Recomp. Included, not compiled alone.
 *
 * Written from the TMS9918A data manual (Texas Instruments), the V9938 Technical Data Book and Sean Young's notes on
 * the undocumented behaviour; the sprite rules they leave open were checked against openMSX 22.0
 * run as a separate program (private comparisons; none of its code or tables is here).
 *
 * Each chip computes its table addresses (MsxTileParams); the line functions only read VRAM through them. A line is
 * written as raw colour indices: colour 0 stays 0 and the caller resolves it (the TMS9918A shows the backdrop; the
 * V9938 shows the backdrop or palette 0 with TP). Sprites write their colour over the line; a sprite of colour 0 is
 * written only when `sprite_colour0` is set (the V9938 with TP), and then also collides (on the TMS9918A colour-0
 * sprites never show but always collide: `colour0_collides`). */

enum { MSX_TILE_G1 = 0, MSX_TILE_G2, MSX_TILE_MC, MSX_TILE_T1 };

typedef struct {
    const uint8_t *vram;
    uint32_t mask;                 /* 3FFFh (TMS9918A) or 1FFFFh (V9938) */
    uint32_t names;                /* name table base */
    uint32_t patterns;             /* pattern generator base (G1, MC, T1) */
    uint32_t colours;              /* colour table base (G1) */
    /* Graphic 2 / 3: address = (or | ((index << 3 | row) & and)), index = third << 8 | name. */
    uint32_t pattern_or, pattern_and, colour_or, colour_and;
    int text_left;                 /* first pixel of text mode's 40 columns */
    /* Mode-1 sprites. */
    uint32_t sprite_attributes, sprite_patterns;
    uint8_t sprite_size;           /* R#1: bit 1 16 x 16, bit 0 magnified */
    uint8_t sprite_colour0;        /* colour-0 sprite pixels are drawn and collide (V9938, TP set) */
    uint8_t colour0_collides;      /* colour-0 sprite pixels collide though never drawn (TMS9918A) */
} MsxTileParams;

/* One line of a tile mode: `y` is the picture row (0-255, after any vertical scroll), `fg`/`bg` the text colours. */
static void msx_tiles_line(const MsxTileParams *t, int mode, int y, uint8_t fg, uint8_t bg, uint8_t *pixels)
{
    const uint8_t *vram = t->vram;
    uint32_t mask = t->mask;
    int cell = (y >> 3) & 31, fine = y & 7;
    if (mode == MSX_TILE_T1) {
        memset(pixels, 0, MSX_WIDTH);
        for (int column = 0; column < 40; ++column) {
            uint8_t name = vram[(t->names + (uint32_t)(cell * 40 + column)) & mask];
            uint8_t bits = vram[(t->patterns + name * 8u + (uint32_t)fine) & mask];
            for (int p = 0; p < 6; ++p)
                pixels[t->text_left + column * 6 + p] = (bits & (0x80 >> p)) ? fg : bg;
        }
        return;
    }
    for (int column = 0; column < 32; ++column) {
        uint8_t name = vram[(t->names + (uint32_t)(cell * 32 + column)) & mask];
        uint8_t bits, colours;
        if (mode == MSX_TILE_MC) {
            uint8_t block = vram[(t->patterns + name * 8u + (uint32_t)((cell & 3) * 2 + (fine >> 2))) & mask];
            bits = 0xF0;
            colours = block;
        } else if (mode == MSX_TILE_G2) {
            uint32_t index = (uint32_t)((cell >> 3) << 8 | name) << 3 | (uint32_t)fine;
            bits = vram[(t->pattern_or | (index & t->pattern_and)) & mask];
            colours = vram[(t->colour_or | (index & t->colour_and)) & mask];
        } else {
            bits = vram[(t->patterns + name * 8u + (uint32_t)fine) & mask];
            colours = vram[(t->colours + (uint32_t)(name >> 3)) & mask];
        }
        for (int p = 0; p < 8; ++p)
            pixels[column * 8 + p] = (bits & (0x80 >> p)) ? colours >> 4 : colours & 15;
    }
}

typedef struct {
    int x;
    uint16_t bits;      /* pattern row, 16 bits, left pixel in bit 15, before magnification */
    uint8_t colour;
} MsxLineSprite;

static uint16_t msx_sprite1_bits(const MsxTileParams *t, uint8_t pattern, int row, int big)
{
    if (big) {
        pattern &= 0xFC;
        uint8_t left = t->vram[(t->sprite_patterns + pattern * 8u + (uint32_t)row) & t->mask];
        uint8_t right = t->vram[(t->sprite_patterns + pattern * 8u + 16u + (uint32_t)row) & t->mask];
        return (uint16_t)(left << 8 | right);
    }
    return (uint16_t)(t->vram[(t->sprite_patterns + pattern * 8u + (uint32_t)row) & t->mask] << 8);
}

/* Mode-1 sprites of one line: 32 attribute entries, Y = 208 ends the list, displayed from line Y + 1 (wrapping, so Y =
 * 255 is line 0), 8 x 8 or 16 x 16, magnified x 2, early clock (x - 32), at most four per line (lower numbers in front),
 * the fifth-sprite flag with the number of the first fifth sprite (set only while the frame flag and the fifth-sprite
 * flag are clear; otherwise the low bits hold the last sprite number processed), and the collision flag for two sprite
 * pixels that meet inside the 256 visible columns. `line` is the sprite line (after any vertical scroll); `pixels` NULL
 * evaluates the flags only. */
static void msx_sprites1_line(const MsxTileParams *t, int line, uint8_t *status, uint8_t *pixels)
{
    int big = (t->sprite_size >> 1) & 1, mag = t->sprite_size & 1;
    int size = big ? 16 : 8, shown = size << mag;
    MsxLineSprite visible[4];
    int count = 0, fifth = -1, sprite = 0;
    for (; sprite < 32; ++sprite) {
        uint32_t a = t->sprite_attributes + (uint32_t)sprite * 4;
        uint8_t y = t->vram[a & t->mask];
        if (y == 208)
            break;
        int row = (line - 1 - y) & 0xFF;
        if (row >= shown)
            continue;
        if (count == 4) {                    /* a fifth sprite on this line: not drawn; the scan goes on to Y = 208 */
            if (fifth < 0)
                fifth = sprite;
            continue;
        }
        MsxLineSprite *s = &visible[count++];
        s->bits = msx_sprite1_bits(t, t->vram[(a + 2) & t->mask], row >> mag, big);
        uint8_t attr = t->vram[(a + 3) & t->mask];
        s->x = t->vram[(a + 1) & t->mask] - ((attr & 0x80) ? 32 : 0);
        s->colour = attr & 15;
    }
    if (fifth >= 0 && !(*status & 0xC0))
        *status = (uint8_t)(0x40 | (*status & 0x20) | fifth);
    if (!(*status & 0x40))
        *status = (uint8_t)((*status & 0xE0) | (sprite < 31 ? sprite : 31));
    if (count == 0)
        return;
    uint8_t hit[MSX_WIDTH], painted[MSX_WIDTH];
    memset(hit, 0, sizeof hit);
    memset(painted, 0, sizeof painted);
    for (int i = 0; i < count; ++i) {
        const MsxLineSprite *s = &visible[i];
        int drawn = s->colour || t->sprite_colour0;
        if (!drawn && !t->colour0_collides)
            continue;                        /* an invisible sprite that does not collide either */
        for (int p = 0; p < shown; ++p) {
            int x = s->x + p;
            if (x < 0 || x >= MSX_WIDTH || !(s->bits & (0x8000u >> (p >> mag))))
                continue;
            if (hit[x])
                *status |= 0x20;             /* two sprite pixels meet: collision */
            hit[x] = 1;
            if (pixels && drawn && !painted[x]) {   /* the lower-numbered visible pixel stays in front */
                pixels[x] = s->colour;
                painted[x] = 1;
            }
        }
    }
}
