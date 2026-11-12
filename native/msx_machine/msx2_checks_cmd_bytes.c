/* MSX2 hardware fixtures, V9938 command engine: the byte commands (HMMV, HMMM, YMMM, HMMC), their clipping, STOP,
 * restart, live registers, the screen-mode latch, expansion RAM bits, Graphic 6 and 7 geometry, and the timing rows.
 * MIT, Retro-Recomp. A development check, never built into a game. Each fixture programs a fresh machine through its
 * I/O ports (no CPU, no BIOS code), advances machine time with msx_advance (228 cycles a line) and compares with values
 * worked out by hand from the V9938 Technical Data Book and the stage 7 design note (the expected number and its
 * reason are written next to each check). Graphic 4 byte address: (y << 7) | (x >> 1); Graphic 6: (y << 8) | (x >> 1);
 * Graphic 7: (y << 8) | x. The engine's cost table (ticks, 6 to a machine cycle): HMMV starts 112 ticks after the R#46
 * write, then 49 a byte with the display off (62 with the picture and sprites off, 65 with sprites on), 58 more at a line
 * end; HMMM 124 / 91; YMMM 124 / 65.
 * Prints one line per check and exits 1 if any fails. */
#include "msx_machine.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { LINE = MSX_CYCLES_PER_LINE };

static MsxMachine m;
static MsxV9938 vdp;
/* VRAM at a logical address of the current screen mode: Graphic 6 and 7 reach it through the chip's interleave
 * (msx_v9938_physical); every other mode in order. */
#define VR(logical) (vdp.vram[msx_v9938_physical((uint32_t)(logical), msx_v9938_interleaved(vdp.reg))])
static int failures;
static uint64_t t0;                            /* machine cycle of the last R#46 write */

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

static void reg(int r, uint8_t v) { msx_out(&m, 0x99, v); msx_out(&m, 0x99, (uint8_t)(0x80 | r)); }
static uint8_t status(int n) { reg(15, (uint8_t)n); return msx_in(&m, 0x99); }
static void to(uint64_t cycle) { if (cycle > m.cycles) msx_advance(&m, cycle - m.cycles); }

/* A fresh machine in a bitmap mode (R#0, R#1 given), one and a half lines on so the engine has latched the mode. */
static void setup(uint8_t r0, uint8_t r1)
{
    msx_init(&m, MSX_LINES_NTSC);
    msx_set_v9938(&m, &vdp);
    memset(vdp.vram, 0, sizeof vdp.vram);
    reg(0, r0);
    reg(1, r1);
    to(2 * LINE);
}

/* R#32-R#45 in one go through port 9Bh (R#17 = 32, auto-increment). */
static void block(unsigned sx, unsigned sy, unsigned dx, unsigned dy, unsigned nx, unsigned ny, uint8_t col, uint8_t arg)
{
    const unsigned w[6] = { sx, sy, dx, dy, nx, ny };
    reg(17, 32);
    for (int i = 0; i < 6; ++i) {
        msx_out(&m, 0x9B, (uint8_t)(w[i] & 0xFF));
        msx_out(&m, 0x9B, (uint8_t)(w[i] >> 8));
    }
    msx_out(&m, 0x9B, col);
    msx_out(&m, 0x9B, arg);
}

static void go(uint8_t cmd) { reg(46, cmd); t0 = m.cycles; }

/* Run to `cycles` after the last R#46 write and read S#2 (which syncs the engine); returns S#2. */
static uint8_t run(uint64_t cycles) { to(t0 + cycles); return status(2); }

static int ce(uint8_t s2) { return s2 & 1; }
static int tr(uint8_t s2) { return (s2 >> 7) & 1; }
static long rw(int i) { return vdp.reg[i] | (vdp.reg[i + 1] << 8); }

static long vram_sum(void)
{
    long sum = 0;
    for (long i = 0; i < MSX2_VRAM; ++i) sum += VR(i);
    return sum;
}

static void byte_checks(void)
{
    uint8_t s;

    /* hmmv: DX 4 NX 8 -> 4 bytes from byte 2; DY 2, NY 2 -> lines 2 and 3 (0100h, 0180h). 0102h-0105h and 0182h-0185h
     * = ABh, nothing else (sum 8 x ABh = 1368). Done 513 ticks after the write; DY 4, NY 0, R#46 reads 0. */
    setup(0x06, 0x00);
    block(0, 0, 4, 2, 8, 2, 0xAB, 0);
    go(0xC0);
    check("hmmv CE at once", ce(status(2)), 1);
    s = run(100);
    check_hex("hmmv 0102", VR(0x102), 0xAB);
    check_hex("hmmv 0105", VR(0x105), 0xAB);
    check_hex("hmmv 0182", VR(0x182), 0xAB);
    check_hex("hmmv 0185", VR(0x185), 0xAB);
    check("hmmv sum (nothing else changed)", vram_sum(), 8 * 0xAB);
    check("hmmv DY", rw(38), 4);
    check("hmmv NY", rw(42), 0);
    check("hmmv DX NX unchanged", rw(36) * 1000 + rw(40), 4008);
    check("hmmv R#46", vdp.reg[46], 0);
    check("hmmv CE/TR done", ce(s) + 2 * tr(s), 0);

    /* hmmv-nx1: in G4 NX 1 is 1 >> 1 = 0 bytes, which means a whole line; DX 252 is byte 126, so the line has
     * 128 - 126 = 2 bytes: 007Eh and 007Fh, nothing else. */
    setup(0x06, 0x00);
    block(0, 0, 252, 0, 1, 1, 0x5A, 0);
    go(0xC0);
    (void)run(100);
    check_hex("hmmv-nx1 007E", VR(0x7E), 0x5A);
    check_hex("hmmv-nx1 007F", VR(0x7F), 0x5A);
    check("hmmv-nx1 sum", vram_sum(), 2 * 0x5A);

    /* hmmv-dix: DX 4 is byte 2, going left a line has min(16 >> 1 = 8, 2 + 1) = 3 bytes: 0002h, 0001h, 0000h. */
    setup(0x06, 0x00);
    block(0, 0, 4, 0, 16, 1, 0x77, 0x04);
    go(0xC0);
    (void)run(100);
    check_hex("hmmv-dix 0000", VR(0), 0x77);
    check_hex("hmmv-dix 0002", VR(2), 0x77);
    check("hmmv-dix sum", vram_sum(), 3 * 0x77);

    /* hmmv-diy: DY 1, NY 5 going up: lines 1 and 0 only (min(5, 1 + 1) = 2). NY reads 5 - 2 = 3; DY went 1, 0, then
     * past the top: 1023 (FFh, 03h; ours is masked to 10 bits). One byte a line (NX 2), at byte 0: 0080h and 0000h. */
    setup(0x06, 0x00);
    block(0, 0, 0, 1, 2, 5, 0x33, 0x08);
    go(0xC0);
    s = run(100);
    check_hex("hmmv-diy 0000", VR(0x00), 0x33);
    check_hex("hmmv-diy 0080", VR(0x80), 0x33);
    check("hmmv-diy sum", vram_sum(), 2 * 0x33);
    check("hmmv-diy NY", rw(42), 3);
    check_hex("hmmv-diy R#38", vdp.reg[38], 0xFF);
    check_hex("hmmv-diy R#39", vdp.reg[39], 0x03);
    check("hmmv-diy CE", ce(s), 0);

    /* hmmv-x300: DX 300 is off the 256-dot line: one byte a line at x & 255 = 44, byte 22 = 0016h; line 1: 0096h. */
    setup(0x06, 0x00);
    block(0, 0, 300, 0, 8, 2, 0xC9, 0);
    go(0xC0);
    (void)run(100);
    check_hex("hmmv-x300 0016", VR(0x16), 0xC9);
    check_hex("hmmv-x300 0096", VR(0x96), 0xC9);
    check("hmmv-x300 sum", vram_sum(), 2 * 0xC9);

    /* hmmv-ny0: NY 0 means 1024 lines; one byte (NX 2) at byte 0 of every line, 1024 of them (the address wraps at
     * 1024 lines in G4: 128 KiB). After the first line (114 ticks: the first byte is due at 112) NY passes 1023. Ends
     * at 112 + 1023 x (49 + 58) + 49 = 109,602 ticks (18,267 cycles): NY 0, DY back to 0. */
    setup(0x06, 0x00);
    block(0, 0, 0, 0, 2, 0, 0x21, 0);
    go(0xC0);
    (void)run(19);
    check("hmmv-ny0 NY after one line", rw(42), 1023);
    check("hmmv-ny0 DY after one line", rw(38), 1);
    s = run(20000);
    int rows = 0;
    for (int y = 0; y < 1024; ++y) rows += VR(y << 7) == 0x21;
    check("hmmv-ny0 rows written", rows, 1024);
    check("hmmv-ny0 sum", vram_sum(), 1024 * 0x21);
    check("hmmv-ny0 NY end", rw(42), 0);
    check("hmmv-ny0 CE", ce(s), 0);

    /* hmmm: source bytes 12h 34h at 0000h; destination DX 16 = byte 8, DY 8 = 0400h: 0408h = 12h, 0409h = 34h.
     * SY 1, DY 9, NY 0; SX, DX unchanged. */
    setup(0x06, 0x00);
    VR(0) = 0x12;
    VR(1) = 0x34;
    block(0, 0, 16, 8, 4, 1, 0, 0);
    go(0xD0);
    s = run(100);
    check_hex("hmmm 0408", VR(0x408), 0x12);
    check_hex("hmmm 0409", VR(0x409), 0x34);
    check("hmmm sum (source kept, nothing else)", vram_sum(), 2 * (0x12 + 0x34));
    check("hmmm SY DY NY", rw(34) * 10000 + rw(38) * 100 + rw(42), 10900);
    check("hmmm CE", ce(s), 0);

    /* hmmm-overlap: source byte 0, destination byte 1 (DX 2), 4 bytes going right, row 11 22 33 44: each byte is read
     * after the previous one was written, so 11h smears: bytes 0-4 = 11h. */
    setup(0x06, 0x00);
    VR(0) = 0x11; VR(1) = 0x22; VR(2) = 0x33; VR(3) = 0x44;
    block(0, 0, 2, 0, 8, 1, 0, 0);
    go(0xD0);
    (void)run(200);
    check_hex("hmmm-overlap byte 1", VR(1), 0x11);
    check_hex("hmmm-overlap byte 3", VR(3), 0x11);
    check_hex("hmmm-overlap byte 4", VR(4), 0x11);
    check("hmmm-overlap sum", vram_sum(), 5 * 0x11);

    /* ymmm: row 3 holds each byte's index (0-127); DX 128 = byte 64, SY 3, DY 5, NY 1: bytes 64-127 of row 5 (0280h
     * + 40h...) get row 3's, bytes 0-63 stay 0. Sum: row 3 = 8128, row 5 = 64..127 = 6112. SY 4, DY 6, NY 0. */
    setup(0x06, 0x00);
    for (int i = 0; i < 128; ++i) VR(3 * 128 + i) = (uint8_t)i;
    block(0, 3, 128, 5, 0, 1, 0, 0);
    go(0xE0);
    s = run(1000);
    check_hex("ymmm row 5 byte 63 untouched", VR(5 * 128 + 63), 0x00);
    check_hex("ymmm row 5 byte 64", VR(5 * 128 + 64), 64);
    check_hex("ymmm row 5 byte 127", VR(5 * 128 + 127), 127);
    check("ymmm sum", vram_sum(), 8128 + 6112);
    check("ymmm SY DY NY", rw(34) * 10000 + rw(38) * 100 + rw(42), 40600);
    check("ymmm CE", ce(s), 0);
}

static void handshake_checks(void)
{
    uint8_t s;
    long sum;

    /* hmmc: NX 4 NY 2 -> 2 bytes a line. The R#44 written with the block (11h) is the first byte and is stored at the
     * R#46 write; 22h, 33h, 44h follow with each R#44 write: 0000h, 0001h, 0080h, 0081h. TR stays 1 throughout; CE 1
     * after three bytes, 0 after four. */
    setup(0x06, 0x00);
    block(0, 0, 0, 0, 4, 2, 0x11, 0);
    go(0xF0);
    s = status(2);
    check_hex("hmmc 0000 at the start", VR(0), 0x11);
    check("hmmc start TR CE", tr(s) * 10 + ce(s), 11);
    reg(44, 0x22);
    reg(44, 0x33);
    s = status(2);
    check_hex("hmmc 0001", VR(1), 0x22);
    check_hex("hmmc 0080", VR(0x80), 0x33);
    check("hmmc after three: TR CE", tr(s) * 10 + ce(s), 11);
    check_hex("hmmc 0081 not yet", VR(0x81), 0x00);
    reg(44, 0x44);
    s = status(2);
    check_hex("hmmc 0081", VR(0x81), 0x44);
    check("hmmc after four: TR CE", tr(s) * 10 + ce(s), 10);
    check("hmmc DY NY", rw(38) * 100 + rw(42), 200);
    check("hmmc R#46", vdp.reg[46], 0);
    sum = vram_sum();
    check("hmmc sum", sum, 0x11 + 0x22 + 0x33 + 0x44);

    /* hmmc-tr-clear: one more R#44 write with no command running clears TR (tested before anything else), writes
     * nothing. */
    reg(44, 0x55);
    s = status(2);
    check("hmmc-tr-clear TR CE", tr(s) * 10 + ce(s), 0);
    check("hmmc-tr-clear sum", vram_sum(), sum);

    /* hmmc-stale: a one-byte HMMC ends inside its own R#46 write (TR stays 1). A second start with new coordinates
     * (DX 10 = byte 5, DY 20 -> 0A05h) and no R#44 write waits: CE 1, nothing written; the first R#44 write (99h)
     * stores the byte and ends it. */
    setup(0x06, 0x00);
    block(0, 0, 0, 0, 2, 1, 0x11, 0);
    go(0xF0);
    s = status(2);
    check("hmmc-stale first: TR CE", tr(s) * 10 + ce(s), 10);
    reg(36, 10);
    reg(38, 20);
    reg(42, 1);
    go(0xF0);
    s = status(2);
    check_hex("hmmc-stale 0A05 before", VR(0xA05), 0x00);
    check("hmmc-stale waiting: TR CE", tr(s) * 10 + ce(s), 11);
    reg(44, 0x99);
    s = status(2);
    check_hex("hmmc-stale 0A05 after", VR(0xA05), 0x99);
    check("hmmc-stale done: TR CE", tr(s) * 10 + ce(s), 10);
    check("hmmc-stale sum", vram_sum(), 0x11 + 0x99);

    /* stop: HMMV of 8 bytes (NX 16, NY 1); units are due at 112, 161, 210 ticks, the fourth at 259. R#46 = 00h at
     * cycle 38 (228 ticks): 3 bytes written, CE 0 at once, R#46 0, DY 0 and NY 1 as they were (the line never ended);
     * nothing more appears later. Both R#46 writes are counted. */
    setup(0x06, 0x00);
    block(0, 0, 0, 0, 16, 1, 0x66, 0);
    go(0xC0);
    to(t0 + 38);
    reg(46, 0x00);
    s = status(2);
    check("stop sum", vram_sum(), 3 * 0x66);
    check("stop CE", ce(s), 0);
    check("stop R#46", vdp.reg[46], 0);
    check("stop DY NY", rw(38) * 100 + rw(42), 1);
    to(m.cycles + 400);
    (void)status(2);
    check("stop stays stopped", vram_sum(), 3 * 0x66);
    check("stop writes counted", (long)vdp.cmd.writes, 2);

    /* restart: after 3 bytes at cycle 38, DX 40 (byte 20), DY 4 and colour 22h are written and R#46 = C0h again: the
     * new block of 8 bytes takes the live registers: 0214h-021Bh = 22h (4 x 128 + 20 = 0214h), while the old block's
     * 3 bytes (11h) stay. DY 5, NY 0 at the end; two commands started. */
    setup(0x06, 0x00);
    block(0, 0, 0, 0, 16, 1, 0x11, 0);
    go(0xC0);
    to(t0 + 38);
    reg(36, 40);
    reg(38, 4);
    reg(44, 0x22);
    go(0xC0);
    s = run(200);
    check_hex("restart old 0002", VR(2), 0x11);
    check_hex("restart old 0003 not written", VR(3), 0x00);
    check_hex("restart new 0214", VR(0x214), 0x22);
    check_hex("restart new 021B", VR(0x21B), 0x22);
    check("restart sum", vram_sum(), 3 * 0x11 + 8 * 0x22);
    check("restart DY NY", rw(38) * 100 + rw(42), 500);
    check("restart started[12]", (long)vdp.cmd.started[12], 2);
    check("restart CE", ce(s), 0);

    /* live-reg: R#44 written after 3 bytes of an HMMV changes the colour of the rest: bytes 0-2 = 11h, 3-7 = 22h. */
    setup(0x06, 0x00);
    block(0, 0, 0, 0, 16, 1, 0x11, 0);
    go(0xC0);
    to(t0 + 38);
    reg(44, 0x22);
    (void)run(200);
    check_hex("live-reg byte 2", VR(2), 0x11);
    check_hex("live-reg byte 3", VR(3), 0x22);
    check_hex("live-reg byte 7", VR(7), 0x22);
    check("live-reg sum", vram_sum(), 3 * 0x11 + 5 * 0x22);
}

static void mode_checks(void)
{
    uint8_t s;

    /* no-mode: Graphic 2 (R#0 = 02h) has no commands: the R#46 write is counted, nothing runs: no VRAM change, CE 0,
     * TR and BD untouched, started[12] 0, R#46 reads 0. */
    setup(0x02, 0x00);
    block(0, 0, 0, 0, 8, 1, 0xAA, 0);
    go(0xC0);
    s = run(100);
    check("no-mode sum", vram_sum(), 0);
    check("no-mode CE TR", ce(s) + tr(s), 0);
    check("no-mode writes", (long)vdp.cmd.writes, 1);
    check("no-mode started[12]", (long)vdp.cmd.started[12], 0);
    check("no-mode R#46", vdp.reg[46], 0);

    /* mode-latch: the engine takes the screen mode at a line boundary. R#0/R#1 -> G4 at cycle 100 and R#46 in the same
     * line: dropped (writes 1, started 0, nothing drawn). After the boundary at 228 the same R#46 runs: bytes 0-3 =
     * 44h (NX 8 = 4 bytes). */
    msx_init(&m, MSX_LINES_NTSC);
    msx_set_v9938(&m, &vdp);
    memset(vdp.vram, 0, sizeof vdp.vram);
    to(100);
    reg(0, 0x06);
    reg(1, 0x00);
    block(0, 0, 0, 0, 8, 1, 0x44, 0);
    go(0xC0);
    s = run(60);
    check("mode-latch dropped: sum", vram_sum(), 0);
    check("mode-latch dropped: CE", ce(s), 0);
    check("mode-latch dropped: started[12]", (long)vdp.cmd.started[12], 0);
    to(LINE + 10);
    go(0xC0);
    s = run(100);
    check("mode-latch after the boundary: sum", vram_sum(), 4 * 0x44);
    check("mode-latch after the boundary: started[12]", (long)vdp.cmd.started[12], 1);
    check("mode-latch writes", (long)vdp.cmd.writes, 2);

    /* mxd: R#45 bit 5 sends the destination to expansion RAM, which is absent: nothing is written, but the time
     * passes as usual (CE 1 at 85 cycles = 510 ticks, 0 at 86). */
    setup(0x06, 0x00);
    block(4, 0, 4, 2, 8, 2, 0xAB, 0x20);
    go(0xC0);
    s = run(85);
    check("mxd CE at 85", ce(s), 1);
    s = run(86);
    check("mxd CE at 86", ce(s), 0);
    check("mxd sum", vram_sum(), 0);
    check("mxd DY NY", rw(38) * 100 + rw(42), 400);

    /* g6-byte: Graphic 6 (R#0 = 0Ah), 2 dots a byte, 512 dots, 256 bytes a line. DX 2 = byte 1, NX 4 = 2 bytes,
     * DY 1: (1 << 8) | 1 = 0101h and 0102h. */
    setup(0x0A, 0x00);
    block(0, 0, 2, 1, 4, 1, 0xE5, 0);
    go(0xC0);
    (void)run(100);
    check_hex("g6-byte 0101", VR(0x101), 0xE5);
    check_hex("g6-byte 0102", VR(0x102), 0xE5);
    check("g6-byte sum", vram_sum(), 2 * 0xE5);

    /* g7-byte: Graphic 7 (R#0 = 0Eh), one byte a dot, 256 a line. DX 3, NX 2 = 2 bytes, DY 1: 0103h and 0104h. */
    setup(0x0E, 0x00);
    block(0, 0, 3, 1, 2, 1, 0xB7, 0);
    go(0xC0);
    (void)run(100);
    check_hex("g7-byte 0103", VR(0x103), 0xB7);
    check_hex("g7-byte 0104", VR(0x104), 0xB7);
    check("g7-byte sum", vram_sum(), 2 * 0xB7);

    /* g7-ny600: Graphic 7 has 512 lines; going down is not clipped, so NY 600 writes lines 0-511 and then 0-87 again
     * (the address wraps). NX 1 = one byte a line. Every one of the 512 rows has its byte; DY ends at 600 (R#38 58h,
     * R#39 02h), NY 0. About 600 x 107 ticks: done long before 12,000 cycles. */
    setup(0x0E, 0x00);
    block(0, 0, 0, 0, 1, 600, 0x88, 0);
    go(0xC0);
    s = run(12000);
    int rows = 0;
    for (int y = 0; y < 512; ++y) rows += VR(y << 8) == 0x88;
    check("g7-ny600 rows written", rows, 512);
    check("g7-ny600 sum (nothing past line 511)", vram_sum(), 512 * 0x88);
    check("g7-ny600 DY", rw(38), 600);
    check("g7-ny600 NY", rw(42), 0);
    check("g7-ny600 CE", ce(s), 0);
}

/* The timing rows: an HMMV of 8 bytes (DX 4, NX 8, NY 2 in G4: 4 bytes a line), the last byte due at
 * 112 + 7 x cost + 58 ticks, read through S#2 one cycle (6 ticks) before and after that moment. */
static void timing_checks(void)
{
    uint8_t s;

    /* time-hmmv: display off (class 0, 49 ticks a byte): the last byte is due at 112 + 7 x 49 + 58 = 513 ticks.
     * 85 cycles = 510 ticks: CE 1; 86 cycles = 516 ticks: CE 0. */
    setup(0x06, 0x00);
    block(0, 0, 4, 2, 8, 2, 0xAB, 0);
    go(0xC0);
    s = run(85);
    check("time-hmmv CE at 85 cycles", ce(s), 1);
    s = run(86);
    check("time-hmmv CE at 86 cycles", ce(s), 0);

    /* time-vblank: display on but the command runs on a line below the picture (line 200 >= 192): class 0 again,
     * 85 / 86. */
    msx_init(&m, MSX_LINES_NTSC);
    msx_set_v9938(&m, &vdp);
    memset(vdp.vram, 0, sizeof vdp.vram);
    reg(0, 0x06);
    reg(1, 0x40);
    to(200 * LINE);
    block(0, 0, 4, 2, 8, 2, 0xAB, 0);
    go(0xC0);
    s = run(85);
    check("time-vblank CE at 85 cycles", ce(s), 1);
    s = run(86);
    check("time-vblank CE at 86 cycles", ce(s), 0);

    /* time-class 1: picture on, sprites off (R#8 bit 1): 62 a byte, due at 112 + 7 x 62 + 58 = 604 ticks: 100 cycles
     * = 600 ticks CE 1; 101 cycles = 606 ticks CE 0. */
    setup(0x06, 0x40);
    reg(8, 0x02);
    block(0, 0, 4, 2, 8, 2, 0xAB, 0);
    go(0xC0);
    s = run(100);
    check("time-class1 CE at 100 cycles", ce(s), 1);
    s = run(101);
    check("time-class1 CE at 101 cycles", ce(s), 0);

    /* time-class 2: picture on, sprites on: 65 a byte, due at 112 + 7 x 65 + 58 = 625 ticks: 104 cycles = 624 ticks
     * CE 1; 105 cycles = 630 ticks CE 0. */
    setup(0x06, 0x40);
    block(0, 0, 4, 2, 8, 2, 0xAB, 0);
    go(0xC0);
    s = run(104);
    check("time-class2 CE at 104 cycles", ce(s), 1);
    s = run(105);
    check("time-class2 CE at 105 cycles", ce(s), 0);
    check("time-class2 sum", vram_sum(), 8 * 0xAB);
}

int main(void)
{
    byte_checks();
    handshake_checks();
    mode_checks();
    timing_checks();
    printf("%s: %d failure(s)\n", failures ? "FAIL" : "all checks passed", failures);
    return failures ? 1 : 0;
}
