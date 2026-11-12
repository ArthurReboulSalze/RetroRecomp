/* MSX2 hardware fixtures, V9938 commands LINE and SRCH, and the partition proof. MIT, Retro-Recomp. A development check,
 * never built into a game. Each fixture programs a fresh machine through its I/O ports (no CPU, no BIOS code), in Graphic 4
 * with the display off (cost class 0), and compares with values worked out by hand from the stage 7 design note (the
 * LINE and SRCH rules of its section 1.4, the cost table of its section 2.2) and the V9938 Technical Data Book. The
 * expected number and its reason are written next to each check. Graphic 4 addresses a dot (x, y) at byte y * 128 + x / 2,
 * the even x in the high nibble. Time moves only through msx_advance (228 cycles a line). The engine latches the screen
 * mode at a line boundary, so each fixture advances one line after setting the mode and before writing R#46.
 * Prints one line per check and exits 1 if any fails. */
#include "msx_machine.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { LINE = MSX_CYCLES_PER_LINE, TR = 0x80, BD = 0x10, CE = 0x01, MAJ = 1, EQ = 2, DIX = 4, DIY = 8 };

static MsxMachine m;
static MsxV9938 vdp;
static int failures;

static void check(const char *name, long got, long want)
{
    printf("%s %s: %ld (expected %ld)\n", got == want ? "ok  " : "FAIL", name, got, want);
    failures += got != want;
}

static void check_hex(const char *name, long got, long want)
{
    printf("%s %s: %02lX (expected %02lX)\n", got == want ? "ok  " : "FAIL", name, got, want);
    failures += got != want;
}

static void fresh(void)
{
    msx_init(&m, MSX_LINES_NTSC);
    msx_set_v9938(&m, &vdp);
}

static void reg(int r, uint8_t v) { msx_out(&m, 0x99, v); msx_out(&m, 0x99, (uint8_t)(0x80 | r)); }

/* A status register, through R#15 and port 99h. */
static uint8_t status(int n) { reg(15, (uint8_t)n); return msx_in(&m, 0x99); }

/* S#2 reduced to the command bits TR, BD and CE (HR and VR depend on where in the frame the read falls). */
static int s2(void) { return status(2) & (TR | BD | CE); }

/* A fresh machine in Graphic 4, display off, with the engine's mode latched (one line boundary has passed). */
static void setup_g4(void)
{
    fresh();
    reg(0, 0x06);
    reg(1, 0x00);
    msx_advance(&m, LINE);
}

/* R#32-R#46 in one burst through port 9Bh with R#17 = 32 (auto-increment); the write of R#46 starts the command. */
static void launch(unsigned sx, unsigned sy, unsigned dx, unsigned dy, unsigned nx, unsigned ny, unsigned col, unsigned arg,
                   unsigned cmd)
{
    const unsigned w[6] = { sx, sy, dx, dy, nx, ny };
    reg(17, 32);
    for (int i = 0; i < 6; ++i) {
        msx_out(&m, 0x9B, (uint8_t)(w[i] & 0xFF));
        msx_out(&m, 0x9B, (uint8_t)(w[i] >> 8));
    }
    msx_out(&m, 0x9B, (uint8_t)col);
    msx_out(&m, 0x9B, (uint8_t)arg);
    msx_out(&m, 0x9B, (uint8_t)cmd);
}

/* Far more machine time than any fixture's command needs (class 0: a LINE dot costs 19 cycles, a SRCH dot 15.2). */
static void run(void) { msx_advance(&m, 8 * LINE * 5); }

static int dot4(int x, int y) { return (vdp.vram[(y << 7) | (x >> 1)] >> ((~x & 1) * 4)) & 15; }

static long nonzero_dots(void)
{
    long n = 0;
    for (int i = 0; i < MSX2_VRAM; ++i) n += ((vdp.vram[i] & 15) != 0) + ((vdp.vram[i] >> 4) != 0);
    return n;
}

/* The listed dots all hold `col` and nothing else of the 128 KiB is non-zero. */
static void expect_dots(const char *name, const int (*d)[2], int n, int col)
{
    char label[96];
    int matched = 0;
    for (int i = 0; i < n; ++i) matched += dot4(d[i][0], d[i][1]) == col;
    snprintf(label, sizeof label, "%s listed dots drawn", name);
    check(label, matched, n);
    snprintf(label, sizeof label, "%s other non-zero dots", name);
    check(label, nonzero_dots() - matched, 0);
}

static int idle(const char *name)
{
    char label[96];
    snprintf(label, sizeof label, "%s ended (CE 0, R#46 0)", name);
    int ended = (s2() & CE) == 0 && vdp.reg[46] == 0;
    check(label, ended, 1);
    return ended;
}

static void line_checks(void)
{
    /* line-x: DX 10, DY 20, NX 4 (long side), NY 2 (short side), MAJ 0, COL 5, IMP (R#46 = 70h). asx starts at (4 - 1) >> 1 =
     * 1, anx 0. Dot 1 (10,20); asx 1 < 2: asx 5, DY 21, asx 3. Dot 2 (11,21); 3 < 2 no, asx 1. Dot 3 (12,21); 1 < 2: DY 22,
     * asx 3. Dot 4 (13,22); asx 1. Dot 5 (14,22); anx 4 = nx: done before asx changes, so asx stays 1. NX + 1 = 5 dots. Bytes:
     * (10,20) 0A05h high = 50h, (11,21) 0A85h low = 05h, (12,21) 0A86h high = 50h, (13,22) 0B06h low = 05h, (14,22) 0B07h
     * high = 50h. DY reads 22; S#8 = asx & FFh = 01h, S#9 = FEh | asx bit 8 = FEh. */
    setup_g4();
    launch(0, 0, 10, 20, 4, 2, 5, 0, 0x70);
    check("line-x CE while running (before the 136-tick start)", s2() & CE, CE);
    run();
    idle("line-x");
    check_hex("line-x 0A05h", vdp.vram[0x0A05], 0x50);
    check_hex("line-x 0A85h", vdp.vram[0x0A85], 0x05);
    check_hex("line-x 0A86h", vdp.vram[0x0A86], 0x50);
    check_hex("line-x 0B06h", vdp.vram[0x0B06], 0x05);
    check_hex("line-x 0B07h", vdp.vram[0x0B07], 0x50);
    check("line-x no other dot", nonzero_dots(), 5);
    check("line-x DY (R#38)", vdp.reg[38] | (vdp.reg[39] << 8), 22);
    check("line-x DX, NX unchanged", vdp.reg[36] | (vdp.reg[40] << 8), 10 | (4 << 8));
    check_hex("line-x S#8", status(8), 0x01);
    check_hex("line-x S#9", status(9), 0xFE);

    /* line-y: the same with MAJ (Y is the long side): dot 1 (10,20); DY 21; asx 1 < 2: asx 5, DX 11, asx 3. Dot 2 (11,21); DY
     * 22; 3 < 2 no, asx 1. Dot 3 (11,22); DY 23; 1 < 2: DX 12, asx 3. Dot 4 (12,23); DY 24; asx 1. Dot 5 (12,24); DY 25;
     * 1 < 2: DX 13, asx 3; anx 4 = nx: done. DY reads 25; asx = 3 (S#8 03h). Bytes: 0A05h 50h, 0A85h 05h, 0B05h 05h, 0B86h 50h,
     * 0C06h 50h. */
    setup_g4();
    launch(0, 0, 10, 20, 4, 2, 5, MAJ, 0x70);
    run();
    idle("line-y");
    static const int yd[5][2] = { { 10, 20 }, { 11, 21 }, { 11, 22 }, { 12, 23 }, { 12, 24 } };
    expect_dots("line-y", yd, 5, 5);
    check("line-y DY (R#38)", vdp.reg[38] | (vdp.reg[39] << 8), 25);
    check_hex("line-y S#8", status(8), 0x03);

    /* line-nx0: NX 0: the first dot is plotted, then anx 0 = nx 0: done. One dot, at (10,20) = 0A05h high nibble. */
    setup_g4();
    launch(0, 0, 10, 20, 0, 2, 5, 0, 0x70);
    run();
    idle("line-nx0");
    static const int n0[1][2] = { { 10, 20 } };
    expect_dots("line-nx0", n0, 1, 5);

    /* line-edge: DX 254, NX 10, NY 0: dot (254,20), adx 255, dot (255,20), adx 256: bit 8 set in a 256-dot screen: done. Two
     * dots, the pair of nibbles of byte 20 * 128 + 127 = 0A7Fh = 55h. */
    setup_g4();
    launch(0, 0, 254, 20, 10, 0, 5, 0, 0x70);
    run();
    idle("line-edge");
    check_hex("line-edge 0A7Fh", vdp.vram[0x0A7F], 0x55);
    check("line-edge no other dot", nonzero_dots(), 2);

    /* line-xor: line-x with XOR (R#46 = 73h) over a prepared screen. COL 5. (10,20) holds 3: 3 xor 5 = 6, its neighbour (11,20)
     * holds Ah and is not touched: 0A05h = 6Ah. (11,21) holds 5: 5 xor 5 = 0, its neighbour (10,21) holds 9: 0A85h = 90h.
     * The other three dots hold 0 and take 5: 0A86h = 50h, 0B06h = 05h, 0B07h = 50h. */
    setup_g4();
    vdp.vram[0x0A05] = 0x3A;
    vdp.vram[0x0A85] = 0x95;
    launch(0, 0, 10, 20, 4, 2, 5, 0, 0x73);
    run();
    idle("line-xor");
    check_hex("line-xor 0A05h", vdp.vram[0x0A05], 0x6A);
    check_hex("line-xor 0A85h", vdp.vram[0x0A85], 0x90);
    check_hex("line-xor 0A86h", vdp.vram[0x0A86], 0x50);
    check_hex("line-xor 0B06h", vdp.vram[0x0B06], 0x05);
    check_hex("line-xor 0B07h", vdp.vram[0x0B07], 0x50);
}

static void direction_checks(void)
{
    /* All eight directions from (20,20) with NX 4, NY 2: the walk is the one of line-x (MAJ 0: offsets (0,0) (1,1) (2,1) (3,2)
     * (4,2) in (long, short) steps) or line-y (MAJ 1: (0,0) (1,1) (1,2) (2,3) (2,4)), with the X offsets negated by DIX and
     * the Y offsets negated by DIY: the pattern of steps does not depend on the direction (asx is the same), only the sign
     * of each step. The last DY is 20 +- 2 (MAJ 0) or 20 +- 5 (MAJ 1), and S#8 is 01h (MAJ 0) or 03h (MAJ 1). */
    static const int base[2][5][2] = { { { 0, 0 }, { 1, 1 }, { 2, 1 }, { 3, 2 }, { 4, 2 } },
                                       { { 0, 0 }, { 1, 1 }, { 1, 2 }, { 2, 3 }, { 2, 4 } } };
    static const int endy[2] = { 2, 5 };
    for (int maj = 0; maj < 2; ++maj)
        for (int diy = 0; diy < 2; ++diy)
            for (int dix = 0; dix < 2; ++dix) {
                char name[48];
                int d[5][2];
                snprintf(name, sizeof name, "dir MAJ %d DIX %d DIY %d", maj, dix, diy);
                setup_g4();
                launch(0, 0, 20, 20, 4, 2, 5, (unsigned)(maj | (dix ? DIX : 0) | (diy ? DIY : 0)), 0x70);
                run();
                for (int i = 0; i < 5; ++i) {
                    d[i][0] = 20 + (dix ? -base[maj][i][0] : base[maj][i][0]);
                    d[i][1] = 20 + (diy ? -base[maj][i][1] : base[maj][i][1]);
                }
                expect_dots(name, d, 5, 5);
                char label[64];
                snprintf(label, sizeof label, "%s DY and S#8", name);
                int dy = vdp.reg[38] | (vdp.reg[39] << 8);
                check(label, dy * 256 + status(8), (20 + (diy ? -endy[maj] : endy[maj])) * 256 + (maj ? 3 : 1));
            }

    /* line-top: Y long, going up, DY 2, NX 10, NY 0, DX 30: dots (30,2), (30,1), (30,0); after the dot at y 0 the step up leaves
     * the screen: done, DY wraps to 1023 (kept masked to 10 bits, DESIGN 1.4). Row 1023 is not drawn. The dots are 010Fh (y 2), 008Fh (y 1), 000Fh (y 0), each with the high nibble 5. */
    setup_g4();
    launch(0, 0, 30, 2, 10, 0, 5, MAJ | DIY, 0x70);
    run();
    idle("line-top");
    check_hex("line-top y 2", vdp.vram[(2 << 7) | 15], 0x50);
    check_hex("line-top y 1", vdp.vram[(1 << 7) | 15], 0x50);
    check_hex("line-top y 0", vdp.vram[15], 0x50);
    check("line-top no other dot (nothing wrapped to row 1023)", nonzero_dots(), 3);
    check("line-top DY wrapped (R#38/R#39)", vdp.reg[38] | (vdp.reg[39] << 8), 1023);

    /* line-up-x: X long, going up, DX 10, DY 1, NX 8, NY 1: asx 3. Dots 1-3 at y 1 (asx 3 -> 2 -> 1 -> 0, each step less than
     * 1 is false), dot 4 (13,1) then asx 0 < 1: asx 8, DY 0, asx 7; dots 5-9 at y 0 (x 14-18; the 9th has anx 8 = nx: done).
     * Nine dots (nx + 1), and DY 0: the top was reached but not crossed. */
    setup_g4();
    launch(0, 0, 10, 1, 8, 1, 5, DIY, 0x70);
    run();
    idle("line-up-x");
    static const int ux[9][2] = { { 10, 1 }, { 11, 1 }, { 12, 1 }, { 13, 1 }, { 14, 0 }, { 15, 0 }, { 16, 0 }, { 17, 0 }, { 18, 0 } };
    expect_dots("line-up-x", ux, 9, 5);
    check("line-up-x DY", vdp.reg[38] | (vdp.reg[39] << 8), 0);
}

static void srch_row_fill(int y, int from_byte, int to_byte, uint8_t value)
{
    for (int b = from_byte; b < to_byte; ++b) vdp.vram[(y << 7) | b] = value;
}

static void srch_checks(void)
{
    /* srch: row 0 is zero except colour 3 at x 9 (byte 4, odd x: low nibble = 03h). SX 2, SY 0, COL 3, EQ clear: the search
     * stops on the first dot equal to the colour. asx 2, 3, ... 9: stop. BD set, CE clear (S#2 TR/BD/CE = 10h). S#8 = 09h,
     * S#9 = FEh. A read of S#9 clears BD (and only that). */
    setup_g4();
    vdp.vram[4] = 0x03;
    launch(2, 0, 0, 0, 0, 0, 3, 0, 0x60);
    check("srch CE while running", s2() & CE, CE);
    run();
    check_hex("srch S#2 (BD set, CE clear)", s2(), BD);
    check_hex("srch S#8", status(8), 0x09);
    check_hex("srch S#8 again (not a clearing read)", status(8), 0x09);
    check_hex("srch S#9", status(9), 0xFE);
    check_hex("srch S#2 after S#9 (BD cleared)", s2(), 0x00);
    check_hex("srch S#8 after S#9", status(8), 0x09);
    check("srch writes no VRAM", nonzero_dots(), 1);

    /* srch-miss: row 1 holds no colour 3: asx runs 0 ... 255, then 256 has bit 8 set (a 256-dot screen): done with BD
     * untouched (0), asx = 256: S#8 = 00h, S#9 = FEh | 1 = FFh. */
    setup_g4();
    launch(0, 1, 0, 0, 0, 0, 3, 0, 0x60);
    run();
    check_hex("srch-miss S#2 (BD untouched, CE clear)", s2(), 0x00);
    check_hex("srch-miss S#8", status(8), 0x00);
    check_hex("srch-miss S#9", status(9), 0xFF);

    /* srch-bd-kept: a hit sets BD; starting another SRCH that misses (a row without colour 3) does not clear it; only the S#9
     * read does. A third SRCH that hits after that sets it again. */
    setup_g4();
    vdp.vram[4] = 0x03;
    launch(2, 0, 0, 0, 0, 0, 3, 0, 0x60);
    run();
    check_hex("srch-bd-kept first hit", s2(), BD);
    launch(0, 1, 0, 0, 0, 0, 3, 0, 0x60);
    run();
    check_hex("srch-bd-kept BD survives a miss", s2(), BD);
    check_hex("srch-bd-kept S#9 of the miss", status(9), 0xFF);
    check_hex("srch-bd-kept BD cleared by S#9", s2(), 0x00);

    /* srch-neq: EQ set: stop on the first dot different from the colour. Row 0: every dot 3 except x 6 (byte 3 = 03h: x 6 =
     * 0, x 7 = 3). asx 0 ... 5 are 3, asx 6 differs: BD set, S#8 = 06h, S#9 = FEh. */
    setup_g4();
    srch_row_fill(0, 0, 128, 0x33);
    vdp.vram[3] = 0x03;
    launch(0, 0, 0, 0, 0, 0, 3, EQ, 0x60);
    run();
    check_hex("srch-neq S#2", s2(), BD);
    check_hex("srch-neq S#8", status(8), 0x06);
    check_hex("srch-neq S#9", status(9), 0xFE);

    /* srch-left: DIX: the search walks left. Row 0 holds colour 3 at x 12 (right of the start, never seen), x 4 (byte 2 high
     * nibble) and x 2 (byte 1 high nibble, never reached): SX 10, asx 10, 9, ... 4: stop. S#8 = 04h. */
    setup_g4();
    vdp.vram[6] = 0x30;
    vdp.vram[2] = 0x30;
    vdp.vram[1] = 0x30;
    launch(10, 0, 0, 0, 0, 0, 3, DIX, 0x60);
    run();
    check_hex("srch-left S#2", s2(), BD);
    check_hex("srch-left S#8", status(8), 0x04);
    check_hex("srch-left S#9", status(9), 0xFE);

    /* srch-left-miss: DIX, colour 7 absent, SX 5: asx 5, 4, ... 0, then 0 - 1 = 1023 (10 bits), which has bit 8 set: done, BD
     * untouched, S#8 = FFh, S#9 = FFh. */
    setup_g4();
    launch(5, 0, 0, 0, 0, 0, 7, DIX, 0x60);
    run();
    check_hex("srch-left-miss S#2", s2(), 0x00);
    check_hex("srch-left-miss S#8", status(8), 0xFF);
    check_hex("srch-left-miss S#9", status(9), 0xFF);
}

/* ---- the partition fixture ---- */

typedef struct {
    uint64_t hash, next, cycles;
    uint8_t regs[15], s2, status, transfer;
    uint16_t asx, adx, anx;
} Snap;

static uint64_t fnv(const uint8_t *p, size_t n)
{
    uint64_t h = 1469598103934665603ull;
    for (size_t i = 0; i < n; ++i) h = (h ^ p[i]) * 1099511628211ull;
    return h;
}

/* One LMMM of 64 x 16 dots (SX 0, SY 0, DX 100, DY 40, IMP) over a pseudo-random source, run for `span` cycles from the start
 * of the command: step 0 = one msx_advance for the whole span; step N = N cycles at a time, a status read (which syncs the
 * engine) after each. Then the final S#2 read syncs both runs to the same cycle before the state is taken. */
static void run_lmmm(Snap *s, uint64_t span, unsigned step)
{
    setup_g4();
    uint32_t seed = 12345;
    for (int i = 0; i < 16 * 128; ++i) { seed = seed * 1103515245u + 12345u; vdp.vram[i] = (uint8_t)(seed >> 16); }
    launch(0, 0, 100, 40, 64, 16, 0, 0, 0x90);
    uint64_t target = m.cycles + span;
    if (!step) {
        msx_advance(&m, span);
    } else {
        reg(15, 2);
        while (m.cycles < target) {
            uint64_t d = target - m.cycles;
            msx_advance(&m, d > step ? step : d);
            (void)msx_in(&m, 0x99);
        }
    }
    s->s2 = (uint8_t)s2();
    s->hash = fnv(vdp.vram, sizeof vdp.vram);
    memcpy(s->regs, vdp.reg + 32, 15);
    s->next = vdp.cmd.next;
    s->cycles = m.cycles;
    s->asx = vdp.cmd.asx;
    s->adx = vdp.cmd.adx;
    s->anx = vdp.cmd.anx;
    s->status = vdp.cmd.status;
    s->transfer = vdp.cmd.transfer;
}

static void compare_snaps(const char *name, const Snap *a, const Snap *b)
{
    char label[96];
    snprintf(label, sizeof label, "%s same machine cycle", name);
    check(label, a->cycles == b->cycles, 1);
    snprintf(label, sizeof label, "%s same VRAM hash", name);
    check(label, a->hash == b->hash, 1);
    snprintf(label, sizeof label, "%s same R#32-R#46", name);
    check(label, memcmp(a->regs, b->regs, 15) == 0, 1);
    snprintf(label, sizeof label, "%s same S#2 and status", name);
    check(label, a->s2 == b->s2 && a->status == b->status && a->transfer == b->transfer, 1);
    snprintf(label, sizeof label, "%s same working counters", name);
    check(label, a->asx == b->asx && a->adx == b->adx && a->anx == b->anx, 1);
    snprintf(label, sizeof label, "%s same next tick", name);
    check(label, a->next == b->next, 1);
}

static void partition_checks(void)
{
    static Snap one, seven;

    /* partition, mid-run: 9001 cycles after the start (the start is at cycle 228 after the one-line wait; the first unit is due
     * 123 ticks after it, tick 6 * 228 + 123 = 1491). Class 0: a unit costs 130 ticks, the last unit of a 64-dot line 130 + 59 =
     * 189, so a line costs 63 * 130 + 189 = 8379 ticks. The span ends at tick 6 * 9229 = 55374: 53883 ticks after the first
     * unit; six whole lines take 50274, the next line starts at tick 1491 + 50274 = 51765, and its units are due at 51765 +
     * 130 j <= 55374, j = 0 ... 27: 28 units. So SY 6, DY 46, NY 10 (16 - 6), anx 64 - 28 = 36, asx 28, adx 128 and the next
     * unit due at 51765 + 28 * 130 = 55405. The command still runs (CE). */
    run_lmmm(&one, 9001, 0);
    run_lmmm(&seven, 9001, 7);
    compare_snaps("partition mid-run", &one, &seven);
    check("partition mid-run SY (R#34)", one.regs[2], 6);
    check("partition mid-run DY (R#38)", one.regs[6], 46);
    check("partition mid-run NY (R#42)", one.regs[10], 10);
    check("partition mid-run units left in the line", one.anx, 36);
    check("partition mid-run working source X", one.asx, 28);
    check("partition mid-run working destination X", one.adx, 128);
    check("partition mid-run next tick", (long)one.next, 55405);
    check("partition mid-run CE", one.s2 & CE, CE);

    /* partition, finished: both runs 30000 cycles after the start (the command needs 123 + 16 * 8379 = 134187 ticks = 22365
     * cycles). CE clear, SY 16, DY 56, NY 0, R#46 0, and the destination block (byte 50 + i of rows 40-55) equals the source
     * (byte i of rows 0-15 for i < 32): the dots are even-aligned so whole bytes copy. */
    run_lmmm(&one, 30000, 0);
    run_lmmm(&seven, 30000, 7);
    compare_snaps("partition finished", &one, &seven);
    check("partition finished CE", one.s2 & CE, 0);
    check("partition finished SY, DY, NY", one.regs[2] | (one.regs[6] << 8) | (one.regs[10] << 16), 16 | (56 << 8));
    check("partition finished R#46", one.regs[14], 0);
    int wrong = 0;
    uint32_t seed = 12345;
    for (int r = 0; r < 16; ++r)
        for (int i = 0; i < 128; ++i) {
            seed = seed * 1103515245u + 12345u;
            if (i < 32) wrong += vdp.vram[((40 + r) << 7) | (50 + i)] != (uint8_t)(seed >> 16);
        }
    check("partition finished destination equals the source", wrong, 0);
}

int main(void)
{
    line_checks();
    direction_checks();
    srch_checks();
    partition_checks();
    printf("%s\n", failures ? "FAILED" : "all MSX2 LINE, SRCH and partition checks passed");
    return failures ? 1 : 0;
}
