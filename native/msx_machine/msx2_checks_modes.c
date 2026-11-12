/* MSX2 hardware fixtures, part "modes": the V9938 picture (9-bit colours, 512 half-pixels a line, 256-pixel modes
 * doubled, border colours per line). MIT, Retro-Recomp.
 * A development check, never built into a game. Each fixture programs a fresh V9938 through its I/O ports (no CPU),
 * runs whole frames with msx_advance, and compares the picture with values worked out by hand from the V9938 Technical
 * Data Book, the MSX2 Technical Handbook and the rules of the stage 6 design (section 1.5): the reasoning is in the
 * comment next to each check. Prints one line per check and exits 1 if any fails.
 * Frame k of a fixture starts at cycle k * 262 * 228; line L is drawn 180 cycles into its line. A palette word is
 * 0GGG0RRR0BBB; the picture stores the words after the palette. */
#include "msx_machine.h"

#include <stdio.h>
#include <string.h>

static MsxMachine m;
static MsxV9938 vdp;
static int failures;

static void check(const char *name, long got, long want)
{
    printf("%s %s: %03lX (expected %03lX)\n", got == want ? "ok  " : "FAIL", name, got, want);
    failures += got != want;
}

static void reg(int r, uint8_t v) { msx_out(&m, 0x99, v); msx_out(&m, 0x99, (uint8_t)(0x80 | r)); }

static void vpoke(uint32_t address, uint8_t value)
{
    reg(14, (uint8_t)(address >> 14));
    msx_out(&m, 0x99, (uint8_t)(address & 0xFF));
    msx_out(&m, 0x99, (uint8_t)(0x40 | ((address >> 8) & 0x3F)));
    msx_out(&m, 0x98, value);
}

/* The test palette: 16 distinct words, entry i = G (2, or 5 from entry 8) R = i & 7, B = (3i + 1) & 7. */
static long pw(int i) { return (long)(((i >> 3) ? 5 : 2) << 8 | (i & 7) << 4 | ((i * 3 + 1) & 7)); }

static void load_palette(void)
{
    reg(16, 0);
    for (int i = 0; i < 16; ++i) {
        long w = pw(i);
        msx_out(&m, 0x9A, (uint8_t)(w & 0xFF));
        msx_out(&m, 0x9A, (uint8_t)(w >> 8));
    }
}

/* A fresh V9938, display on with R#1 = r1, sprites off (R#8 bit 1), the test palette, backdrop R#7. */
static void fresh(uint8_t r0, uint8_t r1, uint8_t r2, uint8_t r7)
{
    msx_init(&m, MSX_LINES_NTSC);
    msx_set_v9938(&m, &vdp);
    load_palette();
    reg(0, r0); reg(1, r1); reg(2, r2); reg(7, r7); reg(8, 0x02);
}

static void frame(void) { msx_advance(&m, (uint64_t)MSX_CYCLES_PER_LINE * MSX_LINES_NTSC); }
static void settle(void) { frame(); frame(); }       /* the second frame has the registers from its line 0 */
static long px(int half, int line) { return vdp.frame[line][half]; }

/* S#2 bit 1 (EO) now. */
static int eo_now(void)
{
    reg(15, 2);
    return (msx_in(&m, 0x99) >> 1) & 1;
}

/* One frame, with S#2 read in the middle of it: the EO flag the frame's picture was drawn with. */
static int frame_eo(void)
{
    msx_advance(&m, (uint64_t)MSX_CYCLES_PER_LINE * 100);
    int eo = eo_now();
    msx_advance(&m, (uint64_t)MSX_CYCLES_PER_LINE * (MSX_LINES_NTSC - 100));
    return eo;
}

static void legacy_checks(void)
{
    /* Graphic 1 on the V9938 table addresses: names (R#2 & 7Fh) << 10 = 3000h; patterns (R#4 & 3Fh) << 11 = 2800h;
     * colours R#10 bits 0-2 = A16-A14 and R#3 = A13-A6: (1 << 14) | (80h << 6) = 6000h. Name 9 at row 1, column 1
     * (3000h + 33), its pattern row 0 at 2800h + 72 = 2848h = 80h, colour byte (name >> 3) = 1 at 6001h = 34h:
     * pixel (8,8) foreground 3, pixel (9,8) background 4; each pixel is two half-pixels. */
    fresh(0x00, 0x40, 0x0C, 0x00);
    reg(3, 0x80); reg(4, 0x05); reg(10, 0x01);
    vpoke(0x3000 + 33, 9); vpoke(0x2848, 0x80); vpoke(0x6001, 0x34);
    settle();
    check("g1 tables: pixel (8,8) foreground, half-pixel 16", px(16, 8), pw(3));
    check("g1 tables: pixel (8,8) doubled, half-pixel 17", px(17, 8), pw(3));
    check("g1 tables: pixel (9,8) background, half-pixel 18", px(18, 8), pw(4));

    /* Graphic 2 with the V9938's masks. R#4 = 07h: pattern base A13 = 1 (2000h), both mask bits set so the three
     * thirds keep their own patterns; R#3 = 1Fh: colour base A13 = 0, mask bits 0-4 set only (low 11 bits of the index:
     * the thirds share one colour table); R#10 = 1: colours at 4000h. Name 7 at row 9, column 3 (third 1, line 74):
     * pattern index (1 << 11) | (7 << 3) | 2 = 83Ah, pattern at 2000h + 83Ah = 283Ah (80h); colour index and 7FFh = 3Ah,
     * colour 403Ah = 5Ah. A decoy colour at 483Ah (3Ch) is not used; third 0's pattern (203Ah) stays 00h. The data
     * book gives the pattern mask to R#4 alone: if R#3 leaked into the pattern address, the pattern would be 203Ah (00h)
     * and pixel 24 would show the background. */
    fresh(0x02, 0x40, 0x06, 0x00);
    reg(3, 0x1F); reg(4, 0x07); reg(10, 0x01);
    vpoke(0x1800 + 9 * 32 + 3, 7); vpoke(0x283A, 0x80); vpoke(0x403A, 0x5A); vpoke(0x483A, 0x3C);
    settle();
    check("g2 masks: third 1 pattern, own colour mask (24,74), half-pixel 48", px(48, 74), pw(5));
    check("g2 masks: background of the aliased colour byte (25,74), half-pixel 50", px(50, 74), pw(10));

    /* Text 1: 40 columns of 6 pixels, the left edge at pixel 9 on the V9938 (the TMS9918A: 6). Names at (R#2 & 7Fh) <<
     * 10 = 400h, patterns R#4 = 1 -> 800h; name 1 = pattern FCh (six pixels) in columns 0 and 39. R#7 = 56h: text
     * foreground 5, background and backdrop 6.
     * Pixels 9-14 are the first column, 8 and 15 are not text (8 is the left border, the backdrop 6); column 39 spans
     * 9 + 234 = 243 to 248; pixel 249 is border. */
    fresh(0x00, 0x50, 0x01, 0x56);
    reg(4, 0x01);
    vpoke(0x400, 1); vpoke(0x400 + 39, 1); vpoke(0x808, 0xFC);
    settle();
    check("t1 left offset: pixel 8 is border, half-pixel 16", px(16, 0), pw(6));
    check("t1 left offset: pixel 9 is the first text pixel, half-pixel 18", px(18, 0), pw(5));
    check("t1 left offset: pixel 14 is the last of column 0, half-pixel 28", px(28, 0), pw(5));
    check("t1 left offset: pixel 15 is background, half-pixel 30", px(30, 0), pw(6));
    check("t1 last column: pixel 248, half-pixel 496", px(496, 0), pw(5));
    check("t1 right edge: pixel 249 is border (not foreground), half-pixel 498", px(498, 0), pw(6));
}

static void bitmap_checks(void)
{
    /* Graphic 4 (256 x 4 bits): R#0 = 06h, R#1 = 40h, mode 0Ch. Page = R#2 bits 6-5: R#2 = 3Fh is page 1, 8000h.
     * Line 3, byte 7: address 8000h + 3 * 128 + 7 = 8187h = 5Ah: pixel 14 colour 5, pixel 15 colour Ah (high nibble
     * first); doubled, half-pixels 28, 29 = 5 and 30, 31 = A. A decoy 12h at page 0 (0187h) must not show. */
    fresh(0x06, 0x40, 0x3F, 0x00);
    vpoke(0x8187, 0x5A); vpoke(0x0187, 0x12);
    settle();
    check("g4 pixel: half-pixel 28", px(28, 3), pw(5));
    check("g4 pixel: half-pixel 29", px(29, 3), pw(5));
    check("g4 pixel: half-pixel 30", px(30, 3), pw(10));
    check("g4 pixel: half-pixel 31", px(31, 3), pw(10));
    check("g4 pixel: line 4 is not line 3 (colour 0 = backdrop 0)", px(28, 4), pw(0));

    /* Graphic 5 (512 x 2 bits): R#0 = 08h, mode 10h; page 1 at 8000h. Line 3, byte 5 = 1Bh = 00 01 10 11: half-pixels
     * 20-23 are colours 0, 1, 2, 3. R#7 = 0Dh: the border and colour-0 pair is bits 3-2 = 3 for even half-pixels and
     * bits 1-0 = 1 for odd ones. Colour 0 on half-pixel 20 (even) is that pair's even colour (palette 3), not
     * palette 0 (TP clear); colours 1-3 use their own palette entries. */
    fresh(0x08, 0x40, 0x3F, 0x0D);
    vpoke(0x8000 + 3 * 128 + 5, 0x1B);
    settle();
    check("g5 pixel: half-pixel 20 colour 0 shows the even backdrop, palette 3", px(20, 3), pw(3));
    check("g5 pixel: half-pixel 21 colour 1", px(21, 3), pw(1));
    check("g5 pixel: half-pixel 22 colour 2", px(22, 3), pw(2));
    check("g5 pixel: half-pixel 23 colour 3", px(23, 3), pw(3));
    check("g5 backdrop pair: even border colour of line 3 is palette 3", vdp.border[3][0], pw(3));
    check("g5 backdrop pair: odd border colour of line 3 is palette 1", vdp.border[3][1], pw(1));
    check("g5 colour 0 odd half-pixel 1 of line 5 shows palette 1", px(1, 5), pw(1));
    reg(8, 0x22);                                  /* TP set: colour 0 is palette 0 */
    settle();
    check("g5 tp: half-pixel 20 colour 0 is palette 0", px(20, 3), pw(0));
    reg(1, 0x00);                                  /* display off: the whole line is border pairs */
    settle();
    check("g5 display off: even half-pixel is the even border colour", px(0, 3), pw(3));
    check("g5 display off: odd half-pixel is the odd border colour", px(1, 3), pw(1));

    /* Graphic 6 (512 x 4 bits): R#0 = 0Ah, mode 14h; two half-pixels a byte; the page is R#2 bit 5 only: R#2 = 3Fh is
     * page 1 at 10000h. Line 2, byte 9: address 10000h + 2 * 256 + 9 = 10209h = 37h: half-pixels 18, 19 = colours
     * 3, 7. A decoy at page 0 (0209h) must not show. */
    fresh(0x0A, 0x40, 0x3F, 0x00);
    vpoke(0x10209, 0x37); vpoke(0x0209, 0x12);
    settle();
    check("g6 pixel: half-pixel 18 high nibble", px(18, 2), pw(3));
    check("g6 pixel: half-pixel 19 low nibble", px(19, 2), pw(7));

    /* Graphic 7 (256 x 8 bits, GGGRRRBB, blue 2 bits widened to 0, 2, 4, 7): R#0 = 0Eh, mode 1Ch, page 0. Line 1,
     * x = 20..25, address 0100h + x. E3h = G 7, R 0, B 3 -> 7, 0, 7 = 707h. 55h = G 2, R 5, B 1 -> 2 = 252h.
     * 00h is black (000h): Graphic 7 has no transparency, so the backdrop (R#7 = E3h) does not replace it. 02h =
     * blue 4 = 004h. 01h = blue 2 = 002h. 4Dh = G 2, R 3, B 1 -> 2 = 232h. Each byte is two half-pixels. */
    fresh(0x0E, 0x40, 0x1F, 0xE3);
    vpoke(0x100 + 20, 0xE3); vpoke(0x100 + 21, 0x55); vpoke(0x100 + 22, 0x00);
    vpoke(0x100 + 23, 0x02); vpoke(0x100 + 24, 0x01); vpoke(0x100 + 25, 0x4D);
    settle();
    check("g7 pixel E3h, half-pixel 40", px(40, 1), 0x707);
    check("g7 pixel E3h doubled, half-pixel 41", px(41, 1), 0x707);
    check("g7 pixel 55h, half-pixel 42", px(42, 1), 0x252);
    check("g7 pixel 00h is black, not the backdrop, half-pixel 44", px(44, 1), 0x000);
    check("g7 blue 2 (02h) = 4, half-pixel 46", px(46, 1), 0x004);
    check("g7 blue 1 (01h) = 2, half-pixel 48", px(48, 1), 0x002);
    check("g7 pixel 4Dh, half-pixel 50", px(50, 1), 0x232);
    /* Graphic 7 backdrop from all of R#7 (GGGRRRBB): E3h = 707h on both halves of the border. */
    check("g7 backdrop E3h: even border", vdp.border[1][0], 0x707);
    check("g7 backdrop E3h: odd border", vdp.border[1][1], 0x707);
    reg(7, 0x4D);
    settle();
    check("g7 backdrop 4Dh: border", vdp.border[1][0], 0x232);
    reg(1, 0x00);                                  /* display off: the line is the border */
    settle();
    check("g7 display off: half-pixel 40 is the backdrop", px(40, 1), 0x232);
}

static void tp_display_checks(void)
{
    /* Transparency: a colour-0 pixel shows the backdrop palette[R#7 & Fh] with TP (R#8 bit 5) clear and palette 0 with
     * TP set. In Graphic 4 only R#7 bits 3-0 count (R#7 = 54h: backdrop 4); the border is the backdrop either way. */
    fresh(0x06, 0x40, 0x1F, 0x54);
    settle();
    check("tp clear: colour 0 shows palette 4", px(10, 5), pw(4));
    reg(8, 0x22);
    settle();
    check("tp set: colour 0 shows palette 0", px(10, 5), pw(0));
    check("tp set: the border stays palette 4", vdp.border[5][0], pw(4));

    /* Display off (R#1 bit 6 clear): the line is the border, whatever the VRAM holds. Graphic 4 with a pixel of colour
     * 7 at line 5; backdrop palette 4. */
    fresh(0x06, 0x40, 0x1F, 0x04);
    vpoke(5 * 128, 0x70);
    settle();
    check("display on: pixel colour 7", px(0, 5), pw(7));
    reg(1, 0x00);
    settle();
    check("display off: the line is the border, half-pixel 0", px(0, 5), pw(4));
    check("display off: the border colour", vdp.border[5][0], pw(4));
}

static void scroll_checks(void)
{
    /* Vertical scroll R#23 in Graphic 4: line L shows picture row (L + R#23) & FFh. R#23 = 16: line 0 shows row 16
     * (7), not row 0 (3). R#23 = 250: line 10 shows row 260 & FFh = 4 (colour 9). */
    fresh(0x06, 0x40, 0x1F, 0x00);
    vpoke(0 * 128, 0x30); vpoke(16 * 128, 0x70); vpoke(4 * 128, 0x90);
    reg(23, 16);
    settle();
    check("scroll g4 R#23 = 16: line 0 shows row 16", px(0, 0), pw(7));
    reg(23, 250);
    settle();
    check("scroll g4 R#23 = 250: line 10 shows row 4 (wrap)", px(0, 10), pw(9));

    /* Graphic 2 with R#23 = 16: line 191 shows row 207 = name row 25, fine row 7, past the 24 rows of the unscrolled
     * picture. Third 3 of the pattern index: R#4 = 07h (patterns 2000h, no alias), R#3 = FFh (colours A13 = 1, all
     * mask bits), R#10 = 1: colours 6000h; names at 1800h. Name 3 at row 25, column 4: 1800h + 800 + 4 = 1B24h. Pattern
     * index (3 << 11) | (3 << 3) | 7 = 181Fh: pattern 2000h | 181Fh = 381Fh = 80h, colour 6000h | 181Fh = 781Fh = 9Ch.
     * Pixel 32 = foreground 9, pixel 33 = background Ch (12). */
    fresh(0x02, 0x40, 0x06, 0x00);
    reg(3, 0xFF); reg(4, 0x07); reg(10, 0x01); reg(23, 16);
    vpoke(0x1800 + 25 * 32 + 4, 3); vpoke(0x381F, 0x80); vpoke(0x781F, 0x9C);
    settle();
    check("scroll g2 R#23 = 16: line 191 reads name row 25, half-pixel 64", px(64, 191), pw(9));
    check("scroll g2 R#23 = 16: line 191 background, half-pixel 66", px(66, 191), pw(12));
}

static void page_checks(void)
{
    /* Even/odd page interchange: R#9 bit 2 (EO) with R#2 designating page 1 (3Fh): the field with S#2 bit 1 clear shows
     * page 0, the field with it set shows page 1 (design 1.5: the low page bit is cleared on even fields). Graphic 4,
     * line 3 byte 0: page 0 (0180h) = 10h (colour 1), page 1 (8180h) = 20h (colour 2). The EO flag flips every frame. */
    fresh(0x06, 0x40, 0x3F, 0x00);
    vpoke(3 * 128, 0x10); vpoke(0x8000 + 3 * 128, 0x20);
    reg(9, 0x04);
    int flips = 0, wrong = 0, last = -1;
    long shown[6];
    for (int k = 0; k < 6; ++k) {
        int eo = frame_eo();
        shown[k] = px(0, 3);
        wrong += shown[k] != pw(eo ? 2 : 1);
        flips += last >= 0 && eo != last;
        last = eo;
    }
    check("page flip EO: S#2 bit 1 changes on each of 5 frame starts", flips, 5);
    check("page flip EO: frames showing the page their EO asks (0 wrong of 6)", wrong, 0);
    reg(9, 0x00);
    settle();
    check("page flip off: R#2 page 1 alone", px(0, 3), pw(2));

    /* R#13 blink in a bitmap mode: ON time 1 (10 frames), OFF time 1 (10 frames). Writing R#13 starts in the ON state:
     * the low page bit is cleared (page 0, colour 1) for frames 0-9, then page 1 (colour 2) for 10-19, then ON again. */
    fresh(0x06, 0x40, 0x3F, 0x00);
    vpoke(3 * 128, 0x10); vpoke(0x8000 + 3 * 128, 0x20);
    reg(13, 0x11);
    long seen[21];
    for (int k = 0; k < 21; ++k) {
        frame();
        seen[k] = px(0, 3);
    }
    check("blink page: frame 0 (ON) shows page 0", seen[0], pw(1));
    check("blink page: frame 9 (last ON) shows page 0", seen[9], pw(1));
    check("blink page: frame 10 (OFF) shows page 1", seen[10], pw(2));
    check("blink page: frame 19 (last OFF) shows page 1", seen[19], pw(2));
    check("blink page: frame 20 (ON again) shows page 0", seen[20], pw(1));
}

static void text2_checks(void)
{
    /* Text 2 (80 columns of 6 half-pixels from half-pixel 18): R#0 = 04h, R#1 = 50h, mode 09h. Names (R#2 & 7Ch) << 10 =
     * 3000h (R#2 = 0Fh); patterns R#4 = 04h -> 2000h; blink table ((R#10 << 14) | (R#3 << 6)) & ~1FFh = 1E00h (R#3 =
     * 7Fh), one bit per character, bit 7 of the first byte for character 0. Name 1 in columns 0, 1 and 79, pattern
     * row 0 = F8h (five pixels). R#7 = 5Ah: foreground 5, background A; R#12 = 4Fh: blink foreground 4, background F.
     * R#13 = 11h: ON 10 frames then OFF 10 frames. Character 0 blinks; character 1 does not. In the ON state character
     * 0 takes R#12's colours, in the OFF state R#7's. */
    fresh(0x04, 0x50, 0x0F, 0x5A);
    reg(3, 0x7F); reg(4, 0x04); reg(12, 0x4F);
    vpoke(0x3000, 1); vpoke(0x3001, 1); vpoke(0x3000 + 79, 1); vpoke(0x2008, 0xF8); vpoke(0x1E00, 0x80);
    reg(13, 0x11);
    long fg[21], bg[21], other[21];
    for (int k = 0; k < 21; ++k) {
        frame();
        fg[k] = px(18, 0);                         /* character 0, first pixel */
        bg[k] = px(23, 0);                         /* character 0, sixth pixel (clear in F8h) */
        other[k] = px(24, 0);                      /* character 1, first pixel: never blinks */
    }
    check("t2 blink: frame 0 foreground is R#12 high nibble", fg[0], pw(4));
    check("t2 blink: frame 0 background is R#12 low nibble", bg[0], pw(15));
    check("t2 blink: frame 9 (last ON) foreground", fg[9], pw(4));
    check("t2 blink: frame 10 (OFF) foreground is R#7 high nibble", fg[10], pw(5));
    check("t2 blink: frame 10 (OFF) background is R#7 low nibble", bg[10], pw(10));
    check("t2 blink: frame 19 (last OFF) foreground", fg[19], pw(5));
    check("t2 blink: frame 20 (ON again) foreground", fg[20], pw(4));
    check("t2 blink: a character without its blink bit never blinks (ON frame)", other[0], pw(5));
    check("t2 blink: a character without its blink bit never blinks (OFF frame)", other[12], pw(5));
    check("t2 columns: character 79, pixel 4 at half-pixel 496", px(18 + 79 * 6 + 4, 0), pw(5));
    check("t2 columns: half-pixel 17 is backdrop", px(17, 0), pw(10));
}

int main(void)
{
    legacy_checks();
    bitmap_checks();
    tp_display_checks();
    scroll_checks();
    page_checks();
    text2_checks();
    printf("%s: %d failure(s)\n", failures ? "FAILED" : "PASSED", failures);
    return failures ? 1 : 0;
}
