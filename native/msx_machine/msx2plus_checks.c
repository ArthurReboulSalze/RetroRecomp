/* MSX2+ hardware fixtures: the V9958's registers, ID, horizontal scroll, mask, two-page scroll and YJK / YAE colours.
 * MIT, Retro-Recomp. A development check, never built into a game. Each fixture programs a fresh V9958 (or a V9938, to show
 * that it does not see the new registers) through port 99h, writes VRAM cells directly, draws line 0 with
 * msx_v9938_draw_line and compares the points of the line with values worked out by hand from the V9958 formulas
 * (docs/MSX.md section 9): R = Y + J, G = Y + K, B = (5Y - 2J - K) / 4 rounded down, each clipped to 0-31, a point
 * MSX_COLOUR15 | G << 10 | R << 5 | B; Graphic 7's ordinary colour GGGRRRBB -> 0GGG0RRR0BBB with blue 0, 2, 4, 7.
 * Prints one line per check and exits 1 if any fails. */
#include "msx_machine.h"

#include <stdio.h>
#include <string.h>

static MsxMachine m;
static MsxV9938 vdp;
static int failures;

static void check_hex(const char *name, long got, long want)
{
    printf("%s %s: %04lX (expected %04lX)\n", got == want ? "ok  " : "FAIL", name, got, want);
    failures += got != want;
}

static void reg(int r, uint8_t v) { msx_out(&m, 0x99, v); msx_out(&m, 0x99, (uint8_t)(0x80 | r)); }
static uint8_t status(int n) { reg(15, (uint8_t)n); return msx_in(&m, 0x99); }

/* A fresh machine in Graphic 7 (R#0 0Eh, R#1 40h: display on), sprites off (R#8 02h), page 0 (R#2 1Fh), VRAM cleared. */
static void fresh(int v9958)
{
    msx_init(&m, MSX_LINES_NTSC);
    memset(&vdp, 0, sizeof vdp);
    msx_set_v9938(&m, &vdp);
    vdp.v9958 = (uint8_t)v9958;
    reg(0, 0x0E);
    reg(1, 0x40);
    reg(2, 0x1F);
    reg(8, 0x02);
}

/* The byte at x of line 0 of a Graphic 7 page (interleaved, as the chip holds it). */
static void poke(int page, int x, uint8_t value) { vdp.vram[msx_v9938_physical(((uint32_t)page << 16) | (uint32_t)x, 1)] = value; }

static uint16_t at(int x) { msx_v9938_draw_line(&m, 0); return vdp.frame[0][2 * x]; }

int main(void)
{
    /* The ID in S#1 bits 1-5: 2 on the V9958, 0 on the V9938. */
    fresh(1);
    check_hex("V9958 S#1 ID bits", status(1) & 0x3E, 0x04);
    fresh(0);
    check_hex("V9938 S#1 ID bits", status(1) & 0x3E, 0x00);
    /* R#25-R#27 exist on the V9958 only, masked to 7, 6 and 3 bits. */
    reg(25, 0xFF);
    check_hex("V9938 ignores R#25", vdp.reg[25], 0x00);
    fresh(1);
    reg(25, 0xFF); reg(26, 0xFF); reg(27, 0xFF);
    check_hex("V9958 R#25 masked", vdp.reg[25], 0x7F);
    check_hex("V9958 R#26 masked", vdp.reg[26], 0x3F);
    check_hex("V9958 R#27 masked", vdp.reg[27], 0x07);

    /* YJK: a group of Y = 16 everywhere, K = +3 (bytes 0 and 1: low bits 3 and 0), J = -2 (6-bit 3Eh: bytes 2 and 3: 6 and 7):
     * 83h 80h 86h 87h. R = 16 - 2 = 14, G = 16 + 3 = 19, B = (80 + 4 - 3) / 4 = 20 -> 8000h | 19 << 10 | 14 << 5 | 20 = CDD4h. */
    fresh(1);
    reg(25, 0x08);
    poke(0, 0, 0x83); poke(0, 1, 0x80); poke(0, 2, 0x86); poke(0, 3, 0x87);
    check_hex("YJK point 0", at(0), 0xCDD4);
    check_hex("YJK point 3 (same J and K)", at(3), 0xCDD4);
    /* Clipping: Y = 31, J = +31 (low bits 7 then 3), K = -32 (20h: low bits 0 then 4): F8h FCh FFh FBh. R = 62 -> 31,
     * G = -1 -> 0, B = (155 - 62 + 32) / 4 = 31 -> 8000h | 0 | 31 << 5 | 31 = 83FFh. */
    poke(0, 4, 0xF8); poke(0, 5, 0xFC); poke(0, 6, 0xFF); poke(0, 7, 0xFB);
    check_hex("YJK clipped point", at(4), 0x83FF);
    /* YAE: a byte with bit 3 set is the palette colour of its bits 7-4: 5Ch -> colour 5, 327h after a reset. The group's
     * other bytes stay YJK, and 5Ch's low bits still count: 80h 80h 80h 5Ch gives K = 0 and J = 4 << 3 = 20h = -32, so
     * point 0 (Y = 16) is R = -16 -> 0, G = 16, B = (80 + 64) / 4 = 36 -> 31: 8000h | 16 << 10 | 31 = C01Fh. */
    fresh(1);
    reg(25, 0x18);
    poke(0, 0, 0x80); poke(0, 1, 0x80); poke(0, 2, 0x80); poke(0, 3, 0x5C);
    check_hex("YAE palette point", at(3), 0x327);
    check_hex("YAE group's YJK point", at(0), 0xC01F);

    /* Horizontal scroll, Graphic 7 without YJK: E0h (G 7, R 0, B 0 -> 700h) at x = 8; R#26 = 1 moves the picture 8 dots left. */
    fresh(1);
    poke(0, 8, 0xE0);
    reg(26, 1);
    check_hex("R#26 = 1: x 0 shows dot 8", at(0), 0x700);
    check_hex("R#26 = 1: x 8 shows dot 16", at(8), 0x000);
    /* R#27 = 3 moves it back 3 dots right: 8 - 3 = 5. */
    reg(27, 3);
    check_hex("R#26 = 1, R#27 = 3: x 3 shows dot 8", at(3), 0x700);
    /* The V9938 does not scroll. */
    fresh(0);
    poke(0, 8, 0xE0);
    reg(26, 1);
    check_hex("V9938: x 8 stays dot 8", at(8), 0x700);
    /* MSK: the left 8 dots show the border, R#7 = 1Ch (R 7 -> 070h); dot 8 is drawn. */
    fresh(1);
    poke(0, 8, 0xE0);
    reg(7, 0x1C);
    reg(25, 0x02);
    check_hex("MSK: x 0 is the border", at(0), 0x070);
    check_hex("MSK: x 7 is the border", at(7), 0x070);
    check_hex("MSK: x 8 is drawn", at(8), 0x700);
    /* SP2: two pages side by side; R#26 = 32 (256 dots) shows page 1 from x = 0. E0h at page 1 x = 0, page 0 x = 0 empty. */
    fresh(1);
    poke(1, 0, 0xE0);
    reg(25, 0x01);
    reg(26, 32);
    check_hex("SP2, R#26 = 32: x 0 shows page 1 dot 0", at(0), 0x700);
    reg(25, 0x00);
    check_hex("no SP2, R#26 = 32: x 0 shows page 0 dot 0", at(0), 0x000);

    printf("%s\n", failures ? "MSX2+ checks: FAIL" : "MSX2+ checks: PASS");
    return failures ? 1 : 0;
}
