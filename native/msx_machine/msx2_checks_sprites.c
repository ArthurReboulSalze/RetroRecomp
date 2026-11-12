/* MSX2 sprite fixtures: the V9938's sprite mode 2 (G4-G7) and sprite mode 1 (G2) as the V9938 draws them. MIT,
 * Retro-Recomp. A development check, never built into a game. Each fixture programs the V9938 through its I/O ports on
 * a fresh machine (no CPU), runs whole lines with msx_advance, and compares with values worked out by hand from the
 * V9938 Technical Data Book (sprite chapter, status registers S#0, S#3-S#6) and the MSX2 Technical Handbook, and from
 * the rules of stage 6's DESIGN.md (section 1.5). The reasoning is written next to each check. openMSX was read to
 * understand behaviour, nothing was copied from it. Prints one line per check and exits 1 if any fails.
 *
 * Layout used everywhere: sprite colour table at 7400h, attribute table at 7600h (R#5 = EFh, R#11 = 0: base =
 * (R#5 << 7) & ~3FFh = 7400h, colours at the base, Y/X/pattern at base + 200h), sprite patterns at 7800h (R#6 = 0Fh).
 * A sprite with Y shows from line Y + 1 (so Y = 49 starts at line 50). The 16 palette entries are all different. */
#include "msx_machine.h"

#include <stdio.h>
#include <string.h>

static MsxMachine m;
static MsxV9938 vdp;
static int failures;
static uint32_t tbl;

static void check(const char *name, long got, long want)
{
    printf("%s %s: %ld (expected %ld)\n", got == want ? "ok  " : "FAIL", name, got, want);
    failures += got != want;
}

static void reg(int r, uint8_t v) { msx_out(&m, 0x99, v); msx_out(&m, 0x99, (uint8_t)(0x80 | r)); }

/* Point the write pointer at a 17-bit VRAM address (R#14 holds bits 16-14). */
static void vaddr(uint32_t a)
{
    reg(14, (uint8_t)(a >> 14));
    msx_out(&m, 0x99, (uint8_t)(a & 0xFF));
    msx_out(&m, 0x99, (uint8_t)(0x40 | ((a >> 8) & 0x3F)));
}

/* A mode written through R#0/R#1 reaches the VRAM port's layout (the G6/G7 interleave) at the next line boundary, as the
 * engine's screen does (openMSX: the display mode changes at the next line): the helpers below let that line pass first. */
static void mode_settled(void)
{
    int live = msx_v9938_interleaved(vdp.reg), latched = vdp.cmd.mode == 2 || vdp.cmd.mode == 3;
    if (live != latched)
        msx_advance(&m, m.next_line - m.cycles);
}

static void fill(uint32_t a, uint8_t value, int n)
{
    mode_settled();
    vaddr(a);
    for (int i = 0; i < n; ++i) msx_out(&m, 0x98, value);
}

static void poke(uint32_t a, const uint8_t *bytes, int n)
{
    mode_settled();
    vaddr(a);
    for (int i = 0; i < n; ++i) msx_out(&m, 0x98, bytes[i]);
}

/* The 9-bit colour (0GGG0RRR0BBB) of palette entry i in these fixtures: red i & 7, blue (i >> 3) + 1, green (i >> 1) & 7.
 * Red and blue together are unique among the 16 entries. */
static uint16_t palv(int i) { return (uint16_t)((((i >> 1) & 7) << 8) | ((i & 7) << 4) | ((i >> 3) + 1)); }

/* One sprite of the current table: Y, X, pattern, and `colour` (a whole attribute byte, EC/CC/IC/colour) on all 16 rows. */
static void spr(int n, uint8_t y, uint8_t x, uint8_t pat, uint8_t colour)
{
    uint8_t a[3] = { y, x, pat };
    poke(tbl + 0x200 + (uint32_t)n * 4, a, 3);
    fill(tbl + (uint32_t)n * 16, colour, 16);
}

static void end_list(int n) { fill(tbl + 0x200 + (uint32_t)n * 4, 216, 1); }

/* A fresh machine in the mode R#0 = r0 (G4 06h, G5 08h, G7 0Eh), display on, 8x8 sprites with pattern 0 all ones,
 * backdrop colour 0, TP off, no scroll. `r1` adds bits to R#1 (40h display on). */
static void setup(uint8_t r0, uint8_t r1)
{
    msx_init(&m, MSX_LINES_NTSC);
    msx_set_v9938(&m, &vdp);
    reg(0, r0); reg(1, (uint8_t)(0x40 | r1)); reg(2, 0x1F); reg(5, 0xEF); reg(11, 0); reg(6, 0x0F);
    reg(7, 0); reg(8, 0); reg(9, 0); reg(23, 0);
    reg(16, 0);
    for (int i = 0; i < 16; ++i) {
        msx_out(&m, 0x9A, (uint8_t)(((i & 7) << 4) | ((i >> 3) + 1)));
        msx_out(&m, 0x9A, (uint8_t)((i >> 1) & 7));
    }
    tbl = 0x7400;
    fill(0x7800, 0xFF, 8);
}

static void lines(unsigned n) { msx_advance(&m, (uint64_t)MSX_CYCLES_PER_LINE * n); }

/* The lines 0-99 have been drawn (F, at line 192, is still clear): every fixture reads its picture on line 50 and after. */
static void run(void) { lines(100); }

static long px(int line, int x) { return vdp.frame[line][2 * x]; }

static long status(int index)
{
    reg(15, (uint8_t)index);
    return msx_in(&m, 0x99);
}

static void nine(void)
{
    /* Nine sprites with Y = 49: on line 50 the ninth (entry 8) does not fit (8 per line). S#0: bit 6 (ninth) + its
     * number 8 = 48h (data book, S#0: "9th sprite flag" and "9th sprite number"). The eighth shows, the ninth does not. */
    setup(0x06, 0);
    for (int i = 0; i < 9; ++i) spr(i, 49, (uint8_t)(16 * i), 0, (uint8_t)(i + 1));
    end_list(9);
    run();
    check("spr2-nine S#0", status(0), 0x48);
    check("spr2-nine eighth sprite drawn", px(50, 16 * 7 + 3), palv(8));
    check("spr2-nine ninth sprite not drawn", px(50, 16 * 8 + 3), palv(0));
}

static void list_end(void)
{
    /* Y = 216 in entry 3 ends the list (data book: sprite mode 2 stops at Y = D8h): entries 0-2 show, entry 4 (a sprite
     * that would show on line 50) does not. S#0 has no flag and the number of the entry that ended the scan, 3. */
    setup(0x06, 0);
    for (int i = 0; i < 3; ++i) spr(i, 49, (uint8_t)(16 * i), 0, (uint8_t)(i + 1));
    end_list(3);
    spr(4, 49, 200, 0, 9);
    run();
    check("spr2-end S#0", status(0), 3);
    check("spr2-end third sprite drawn", px(50, 35), palv(3));
    check("spr2-end entry after the end not drawn", px(50, 203), palv(0));
}

static void colour_rows(void)
{
    /* Mode 2 has one colour byte per sprite row: row r (r = 0-7) of an 8x8 sprite shows colour r + 1 on line 50 + r. */
    setup(0x06, 0);
    spr(0, 49, 100, 0, 0);
    uint8_t rows[16];
    for (int r = 0; r < 16; ++r) rows[r] = (uint8_t)((r + 1) & 15);
    poke(tbl, rows, 16);
    end_list(1);
    run();
    long good = 0;
    for (int r = 0; r < 8; ++r) good += px(50 + r, 102) == palv(r + 1);
    check("spr2-colour rows 1-8 on lines 50-57", good, 8);
    check("spr2-colour below the sprite", px(58, 102), palv(0));
    /* Magnified (R#1 bit 0): each pattern row and each colour row covers two lines, each pixel two columns: 16x16. */
    setup(0x06, 1);
    spr(0, 49, 100, 0, 0);
    poke(tbl, rows, 16);
    end_list(1);
    run();
    good = 0;
    for (int l = 0; l < 16; ++l) good += px(50 + l, 100) == palv((l >> 1) + 1);
    check("spr2-mag colour row per two lines", good, 16);
    check("spr2-mag last column", px(50, 115), palv(1));
    check("spr2-mag past the last column", px(50, 116), palv(0));
    check("spr2-mag past the last line", px(66, 100), palv(0));
}

static void cc_or(void)
{
    /* CC (bit 6) ORs the sprite's colour into the sprite before it: sprite 0 colour 4 at x 100, sprite 1 colour 2 + CC
     * at x 104. Pixels 104-107 hold both: 4 | 2 = 6; sprite 0 alone (100): 4; sprite 1 alone (108): its own colour 2
     * (DESIGN.md: a CC sprite shows alone where no sprite covers it). CC sprites do not count for collisions: S#0 is
     * just the entry that ended the scan, 2. */
    setup(0x06, 0);
    spr(0, 49, 100, 0, 4);
    spr(1, 49, 104, 0, 0x42);
    end_list(2);
    run();
    check("spr2-cc base alone", px(50, 100), palv(4));
    check("spr2-cc overlap is the OR", px(50, 104), palv(6));
    check("spr2-cc CC sprite alone", px(50, 108), palv(2));
    check("spr2-cc no collision", status(0), 2);
    /* A CC sprite before every CC = 0 sprite of the line has nothing to OR into and is not shown. */
    setup(0x06, 0);
    spr(0, 49, 100, 0, 0x42);
    spr(1, 49, 104, 0, 5);
    end_list(2);
    run();
    check("spr2-cc first CC sprite hidden", px(50, 100), palv(0));
    check("spr2-cc base after it unaffected", px(50, 104), palv(5));
}

static void collide(void)
{
    /* Two sprites at x 100, Y 49, colour 1, CC and IC clear: they meet on line 50, column 100. S#0 bit 5 (C); S#3-S#4 the
     * column + 12 = 112 (bit 8 in S#4 bit 0, S#4's other bits read 1: FEh), S#5-S#6 the line + 8 = 58 (S#6: FCh). A read of
     * S#0 clears the flag; a read of S#5 clears the coordinates. */
    setup(0x06, 0);
    spr(0, 49, 100, 0, 1);
    spr(1, 49, 100, 0, 1);
    end_list(2);
    run();
    check("spr2-collide S#0 bit 5", status(0) & 0x20, 0x20);
    check("spr2-collide S#0 cleared by the read", status(0) & 0x20, 0);
    check("spr2-collide S#3 (x + 12)", status(3), 112);
    check("spr2-collide S#4", status(4), 0xFE);
    check("spr2-collide S#5 (line + 8)", status(5), 58);
    check("spr2-collide S#6", status(6), 0xFC);
    check("spr2-collide S#3 after S#5 read", status(3), 0);
    check("spr2-collide S#5 after S#5 read", status(5), 0);
    /* IC (bit 5) on one of them: drawn, but no collision. */
    setup(0x06, 0);
    spr(0, 49, 100, 0, 1);
    spr(1, 49, 100, 0, 0x21);
    end_list(2);
    run();
    check("spr2-ic still drawn", px(50, 100), palv(1));
    check("spr2-ic no collision", status(0) & 0x20, 0);
}

static void zero_colour(int tp)
{
    /* Colour 0 sprites over a line of colour-3 pixels. TP clear: colour 0 is transparent, so the sprites are invisible and
     * do not collide (data book: collisions are of visible pixels). TP set: colour 0 is palette 0, drawn, and collides. */
    setup(0x06, 0);
    reg(8, (uint8_t)(tp ? 0x20 : 0));
    fill(50 * 128, 0x33, 128);
    spr(0, 49, 100, 0, 0);
    spr(1, 49, 100, 0, 0);
    end_list(2);
    run();
    char name[48];
    snprintf(name, sizeof name, "spr2-zero TP=%d pixel", tp);
    check(name, px(50, 100), tp ? palv(0) : palv(3));
    snprintf(name, sizeof name, "spr2-zero TP=%d collision", tp);
    check(name, status(0) & 0x20, tp ? 0x20 : 0);
}

static void mode1(void)
{
    /* Sprite mode 1 on the V9938 (Graphic 2): attributes at R#5 << 7 = 7780h, patterns at 7800h. Five sprites on line 50:
     * S#0 = fifth-sprite flag + number 4 = 44h; the fifth does not show. */
    msx_init(&m, MSX_LINES_NTSC);
    msx_set_v9938(&m, &vdp);
    reg(0, 0x02); reg(1, 0x40); reg(2, 0x06); reg(3, 0xFF); reg(4, 0x03); reg(5, 0xEF); reg(11, 0); reg(6, 0x0F);
    reg(7, 0); reg(8, 0); reg(9, 0); reg(23, 0);
    reg(16, 0);
    for (int i = 0; i < 16; ++i) {
        msx_out(&m, 0x9A, (uint8_t)(((i & 7) << 4) | ((i >> 3) + 1)));
        msx_out(&m, 0x9A, (uint8_t)((i >> 1) & 7));
    }
    fill(0x7800, 0xFF, 8);
    for (int i = 0; i < 5; ++i) {
        uint8_t a[4] = { 49, (uint8_t)(16 * i), 0, (uint8_t)(i + 1) };
        poke(0x7780 + 4u * i, a, 4);
    }
    fill(0x7780 + 20, 208, 1);
    run();
    check("spr1-v9938 S#0 fifth sprite", status(0), 0x44);
    check("spr1-v9938 fourth drawn", px(50, 51), palv(4));
    check("spr1-v9938 fifth not drawn", px(50, 67), palv(0));
    /* Two colour-0 sprites on the same pixels: they collide only with TP set. */
    for (int tp = 0; tp < 2; ++tp) {
        msx_init(&m, MSX_LINES_NTSC);
        msx_set_v9938(&m, &vdp);
        reg(0, 0x02); reg(1, 0x40); reg(2, 0x06); reg(3, 0xFF); reg(4, 0x03); reg(5, 0xEF); reg(6, 0x0F);
        reg(8, (uint8_t)(tp ? 0x20 : 0));
        fill(0x7800, 0xFF, 8);
        uint8_t a[9] = { 49, 100, 0, 0, 49, 100, 0, 0, 208 };
        poke(0x7780, a, 9);
        run();
        char name[48];
        snprintf(name, sizeof name, "spr1-v9938 colour 0 TP=%d collision", tp);
        check(name, status(0) & 0x20, tp ? 0x20 : 0);
    }
}

static void tables(void)
{
    /* R#5 bits 0-2 do not count: R#5 = EFh gives the table at 7400h (not at EFh << 7 = 7780h), whose colours are at the base
     * and attributes at base + 200h. A decoy sprite where an unmasked base would put it must not show. */
    setup(0x06, 0);
    spr(0, 49, 100, 0, 5);
    end_list(1);
    tbl = 0x7780;
    spr(0, 49, 150, 0, 9);
    tbl = 0x7400;
    run();
    check("spr2-table R#5 low bits ignored", px(50, 100), palv(5));
    check("spr2-table no sprite at the unmasked base", px(50, 150), palv(0));
    /* R#11 bits 1-0 are address bits 16-15: R#11 = 2 (bit 16) and R#5 = E8h put the table at 17400h; the table at 7400h is unused. */
    setup(0x06, 0);
    reg(11, 2); reg(5, 0xE8);
    tbl = 0x17400;
    spr(0, 49, 100, 0, 6);
    end_list(1);
    tbl = 0x7400;
    spr(0, 49, 150, 0, 9);
    tbl = 0x17400;
    run();
    check("spr2-table R#11 = 2 at 17400h", px(50, 100), palv(6));
    check("spr2-table 7400h unused when R#11 = 2", px(50, 150), palv(0));
}

static void early_clock(void)
{
    /* EC (bit 7 of the colour byte) moves the sprite 32 pixels left: X = 36 shows at columns 4-11. */
    setup(0x06, 0);
    spr(0, 49, 36, 0, 0x87);
    end_list(1);
    run();
    long first = -1, count = 0;
    for (int x = 0; x < 256; ++x)
        if (px(50, x) == palv(7)) { if (first < 0) first = x; ++count; }
    check("spr2-ec first column", first, 4);
    check("spr2-ec width", count, 8);
}

static void sixteen(void)
{
    /* 16x16 (R#1 bit 1): pattern number & FCh, four 8x8 quadrants in the order top-left, bottom-left, top-right,
     * bottom-right (bytes 0-7, 8-15, 16-23, 24-31). Here left half all ones, top-right empty, bottom-right all ones;
     * colour row r is (r mod 15) + 1. Pattern 3 is read as pattern 0. */
    uint8_t quad[32];
    memset(quad, 0xFF, sizeof quad);
    memset(quad + 16, 0x00, 8);
    uint8_t rows[16];
    for (int r = 0; r < 16; ++r) rows[r] = (uint8_t)((r % 15) + 1);
    setup(0x06, 2);
    poke(0x7800, quad, 32);
    spr(0, 49, 100, 3, 0);
    poke(tbl, rows, 16);
    end_list(1);
    run();
    check("spr2-16 top-left", px(50, 100), palv(1));
    check("spr2-16 top-right empty", px(50, 108), palv(0));
    check("spr2-16 bottom-right (row 8, colour 9)", px(58, 108), palv(9));
    check("spr2-16 row 14 colour", px(64, 100), palv(15));
    check("spr2-16 below the sprite", px(66, 100), palv(0));
    /* Magnified 16x16: 32x32; line 66 is row 16 = pattern row 8, colour row 8 (colour 9), column 116 = pixel 16 = bit 0
     * of the right byte. */
    setup(0x06, 3);
    poke(0x7800, quad, 32);
    spr(0, 49, 100, 3, 0);
    poke(tbl, rows, 16);
    end_list(1);
    run();
    check("spr2-16mag bottom-right starts at row 16", px(66, 116), palv(9));
    check("spr2-16mag row 15 right half empty", px(65, 116), palv(0));
    check("spr2-16mag last column", px(66, 131), palv(9));
    check("spr2-16mag past the last column", px(66, 132), palv(0));
}

static void disabled(void)
{
    /* R#8 bit 1 (SPD) switches the sprites off: nothing drawn, and no sprite is evaluated, so S#0 stays 0 even with two
     * sprites on the same pixels. */
    setup(0x06, 0);
    reg(8, 0x02);
    spr(0, 49, 100, 0, 1);
    spr(1, 49, 100, 0, 1);
    end_list(2);
    run();
    check("spr2-off pixel", px(50, 100), palv(0));
    check("spr2-off S#0", status(0), 0);
}

static void graphic5(void)
{
    /* Graphic 5: a sprite pixel is two half-pixels (512 wide), colour bits 3-2 on the even one, bits 1-0 on the odd one
     * (data book: in screen 6 the sprite colour is split in two palette entries). Colour 0Dh = 11 01b: entries 3 and 1. */
    setup(0x08, 0);
    spr(0, 49, 100, 0, 0x0D);
    end_list(1);
    run();
    check("spr2-g5 even half-pixel", vdp.frame[50][200], palv(3));
    check("spr2-g5 odd half-pixel", vdp.frame[50][201], palv(1));
    check("spr2-g5 last half-pixel pair", vdp.frame[50][215], palv(1));
    check("spr2-g5 past the sprite", vdp.frame[50][216], palv(0));
}

static void graphic7(void)
{
    /* Graphic 7 sprites use fixed colours, not the palette (data book, screen 8 sprite colours: code 8 = G4 R7 B2 = 472h,
     * 12 = G7 R0 B0 = 700h, 1 = B2 = 002h). */
    setup(0x0E, 0);
    spr(0, 49, 100, 0, 8);
    spr(1, 49, 116, 0, 12);
    spr(2, 49, 132, 0, 1);
    end_list(3);
    run();
    check("spr2-g7 colour 8", px(50, 100), 0x472);
    check("spr2-g7 colour 12", px(50, 116), 0x700);
    check("spr2-g7 colour 1", px(50, 132), 0x002);
}

static void scroll(void)
{
    /* R#23 = 16 moves the display, sprites included, 16 lines up: Y = 49 starts at line 50 - 16 = 34 and ends at line 41. */
    setup(0x06, 0);
    reg(23, 16);
    spr(0, 49, 100, 0, 5);
    end_list(1);
    run();
    check("spr2-scroll first line 34", px(34, 100), palv(5));
    check("spr2-scroll last line 41", px(41, 100), palv(5));
    check("spr2-scroll line 42 empty", px(42, 100), palv(0));
    check("spr2-scroll unscrolled line 50 empty", px(50, 100), palv(0));
}

int main(void)
{
    nine();
    list_end();
    colour_rows();
    cc_or();
    collide();
    zero_colour(0);
    zero_colour(1);
    mode1();
    tables();
    early_clock();
    sixteen();
    disabled();
    graphic5();
    graphic7();
    scroll();
    printf("%s\n", failures ? "FAILED" : "all sprite checks passed");
    return failures ? 1 : 0;
}
