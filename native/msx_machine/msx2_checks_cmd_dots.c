/* MSX2 hardware fixtures, V9938 command engine, the dot commands and the logical operations: LMMV, LMMM, LMMC, LMCM,
 * PSET, POINT, and the same LMMV/LMMM in Graphic 5, 6 and 7. MIT, Retro-Recomp. A development check, never built into a
 * game. Each fixture programs a fresh machine through its I/O ports (no CPU, no BIOS code), advances machine time with
 * msx_advance (228 cycles a line), and compares with values worked out by hand from the V9938 Technical Data Book (the
 * commands chapter) and from the stage 7 design note, sections 1.2 to 1.5 (geometry, clipping, the logical operations,
 * the CPU handshake) and 2.2 (the cost table). The expected number and its reason are written next to each check. The
 * VRAM is read through MsxV9938.vram and the control registers through MsxV9938.reg[32..46] (a check may; a CPU cannot).
 * All timed checks run with the display off (cost class 0). Prints one line per check and exits 1 if any fails. */
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

static void reg(int r, unsigned v) { msx_out(&m, 0x99, (uint8_t)v); msx_out(&m, 0x99, (uint8_t)(0x80 | r)); }
static uint8_t status(int n) { reg(15, (unsigned)n); return msx_in(&m, 0x99); }

/* A fresh machine in the bitmap mode whose R#0 is given (G4 06h, G5 08h, G6 0Ah, G7 0Eh), display off. The engine latches
 * its screen at a line boundary, so one line passes before any command is written. */
static void setmode(unsigned r0)
{
    msx_init(&m, MSX_LINES_NTSC);
    msx_set_v9938(&m, &vdp);
    memset(vdp.vram, 0, sizeof vdp.vram);
    reg(0, r0);
    reg(1, 0x00);
    msx_advance(&m, LINE);
}

static void block(unsigned sx, unsigned sy, unsigned dx, unsigned dy, unsigned nx, unsigned ny, unsigned col, unsigned arg)
{
    reg(32, sx & 255); reg(33, sx >> 8);
    reg(34, sy & 255); reg(35, sy >> 8);
    reg(36, dx & 255); reg(37, dx >> 8);
    reg(38, dy & 255); reg(39, dy >> 8);
    reg(40, nx & 255); reg(41, nx >> 8);
    reg(42, ny & 255); reg(43, ny >> 8);
    reg(44, col);
    reg(45, arg);
}

static void go(unsigned cmd) { reg(46, cmd); }
static void idle(void) { msx_advance(&m, 4 * LINE); }   /* far longer than any block here */

/* Machine cycles from now (just after the R#46 write) to the first read of S#2 with CE clear. */
static int ce_after(void)
{
    for (int k = 0; k < 4000; ++k) {
        if (!(status(2) & 1))
            return k;
        msx_advance(&m, 1);
    }
    return -1;
}

static long vram_sum(void)
{
    long s = 0;
    for (size_t i = 0; i < sizeof vdp.vram; ++i) s += VR(i);
    return s;
}

/* Run codes first..first+count-1 on one dot, D = Ch (high nibble of 0Ch/05h at VRAM 0000h, x = 0), source colour col.
 * The low nibble (x = 1, value 5) must stay. want[i] is the new high nibble. */
static void ops_run(const char *tag, unsigned first, unsigned col, const uint8_t *want, int count)
{
    char name[64];
    setmode(0x06);
    for (int i = 0; i < count; ++i) {
        VR(0) = 0xC5;
        block(0, 0, 0, 0, 1, 1, col, 0);
        go(0x80 | (first + (unsigned)i));
        idle();
        snprintf(name, sizeof name, "%s code %X", tag, first + (unsigned)i);
        check_hex(name, VR(0), (want[i] << 4) | 5);
    }
}

static void lmmv_checks(void)
{
    /* lmmv-ops: D = Ch, S = Ah, one dot. IMP: A; AND: A and C = 8; OR: A or C = E; XOR: A xor C = 6; NOT: not A in the dot
     * = 5 (DESIGN 1.4 table). The neighbouring dot (x = 1, nibble 5) is never touched. */
    static const uint8_t ops[5] = { 0xA, 0x8, 0xE, 0x6, 0x5 };
    ops_run("lmmv-ops", 0, 0xA, ops, 5);

    /* lmmv-t: codes 8-Ch are the same five with the T rule: S = Ah is not zero, so the same results. */
    ops_run("lmmv-t S=A", 8, 0xA, ops, 5);

    /* lmmv-t, S = 0: the T operations keep D = Ch every time (a transparent source dot). */
    static const uint8_t keep[5] = { 0xC, 0xC, 0xC, 0xC, 0xC };
    ops_run("lmmv-t S=0", 8, 0x0, keep, 5);

    /* lmmv-s0: S = 0, codes 0-4: IMP 0; AND 0 and C = 0; OR 0 or C = C; XOR 0 xor C = C; NOT not 0 = F. */
    static const uint8_t s0[5] = { 0x0, 0x0, 0xC, 0xC, 0xF };
    ops_run("lmmv-s0", 0, 0x0, s0, 5);

    /* lmmv-undef: codes 5, 6, 7, Dh, Eh, Fh write nothing (D stays Ch) and last as long as code 0: one dot, start 117
     * ticks, the unit is due when 6 * cycle >= 6 * start + 117, 20 cycles later (117 / 6 = 19.5). */
    static const unsigned undef[6] = { 5, 6, 7, 0xD, 0xE, 0xF };
    char name[64];
    setmode(0x06);
    VR(0) = 0xC5;
    block(0, 0, 0, 0, 1, 1, 0xA, 0);
    go(0x80);
    check("lmmv-undef code 0 CE lasts (cycles)", ce_after(), 20);
    for (int i = 0; i < 6; ++i) {
        VR(0) = 0xC5;
        block(0, 0, 0, 0, 1, 1, 0xA, 0);
        go(0x80 | undef[i]);
        snprintf(name, sizeof name, "lmmv-undef code %X CE lasts (cycles)", undef[i]);
        check(name, ce_after(), 20);
        snprintf(name, sizeof name, "lmmv-undef code %X leaves the dot", undef[i]);
        check_hex(name, VR(0), 0xC5);
    }

    /* lmmv-odd: DX 1, NX 3, NY 1, COL 5, G4: dots x = 1 (low nibble of byte 0), x = 2 and 3 (both nibbles of byte 1). The
     * registers read back: DX, NX, COL unchanged, DY 1, NY 0, R#46 0, CE 0. Nothing else in the 128 KiB changes (sum). */
    setmode(0x06);
    block(0, 0, 1, 0, 3, 1, 5, 0);
    go(0x80);
    idle();
    check_hex("lmmv-odd 0000h", VR(0), 0x05);
    check_hex("lmmv-odd 0001h", VR(1), 0x55);
    check("lmmv-odd VRAM sum", vram_sum(), 0x05 + 0x55);
    check("lmmv-odd DY", vdp.reg[38], 1);
    check("lmmv-odd NY", vdp.reg[42], 0);
    check("lmmv-odd DX", vdp.reg[36], 1);
    check("lmmv-odd NX", vdp.reg[40], 3);
    check_hex("lmmv-odd COL", vdp.reg[44], 5);
    check_hex("lmmv-odd R#46 back to 0", vdp.reg[46], 0);
    check("lmmv-odd CE", status(2) & 1, 0);

    /* lmmv-block: DX 3, DY 1, NX 3, NY 2, COL 6: x = 3, 4, 5 on lines 1 and 2: byte 0081h = 06h (x = 3 low nibble), 0082h =
     * 66h; the same on line 2 at 0101h and 0102h. DY 3, NY 0. Sum 2 * (06h + 66h) = D8h. */
    setmode(0x06);
    block(0, 0, 3, 1, 3, 2, 6, 0);
    go(0x80);
    idle();
    check_hex("lmmv-block 0081h", VR(0x81), 0x06);
    check_hex("lmmv-block 0082h", VR(0x82), 0x66);
    check_hex("lmmv-block 0101h", VR(0x101), 0x06);
    check_hex("lmmv-block 0102h", VR(0x102), 0x66);
    check("lmmv-block VRAM sum", vram_sum(), 0xD8);
    check("lmmv-block DY", vdp.reg[38], 3);
    check("lmmv-block NY", vdp.reg[42], 0);

    /* lmmv-dix: DX 3, NX 8, NY 1, DIX (R#45 bit 2): going left min(8, 3 + 1) = 4 dots, x = 3, 2, 1, 0: bytes 0 and 1 = 66h,
     * byte 2 untouched. */
    setmode(0x06);
    block(0, 0, 3, 0, 8, 1, 6, 4);
    go(0x80);
    idle();
    check_hex("lmmv-dix 0000h", VR(0), 0x66);
    check_hex("lmmv-dix 0001h", VR(1), 0x66);
    check_hex("lmmv-dix 0002h", VR(2), 0x00);

    /* lmmv-time: three dots on one line, class 0: units due at 117, 117 + 98, 117 + 196 = 313 ticks; 313 / 6 = 52.17, so
     * CE is still set 51 cycles after the write (306 ticks) and clear at 52. */
    setmode(0x06);
    block(0, 0, 0, 0, 3, 1, 6, 0);
    go(0x80);
    check("lmmv-time CE lasts (cycles)", ce_after(), 53);
}

static void lmmm_checks(void)
{
    /* lmmm: dots 1, 2, 3 at x = 0-2 (0000h = 12h, 0001h = 30h), SX 0, SY 0, DX 5, DY 0, NX 3, NY 1, IMP: x = 5 is the low
     * nibble of byte 2 (01h), x = 6 and 7 are byte 3 (23h). SY 1, DY 1, NY 0 read back, SX, DX, NX unchanged. */
    setmode(0x06);
    VR(0) = 0x12;
    VR(1) = 0x30;
    block(0, 0, 5, 0, 3, 1, 0, 0);
    go(0x90);
    idle();
    check_hex("lmmm 0002h", VR(2), 0x01);
    check_hex("lmmm 0003h", VR(3), 0x23);
    check_hex("lmmm source 0000h kept", VR(0), 0x12);
    check("lmmm VRAM sum", vram_sum(), 0x12 + 0x30 + 0x01 + 0x23);
    check("lmmm SY", vdp.reg[34], 1);
    check("lmmm DY", vdp.reg[38], 1);
    check("lmmm NY", vdp.reg[42], 0);
    check("lmmm SX", vdp.reg[32], 0);
    check("lmmm DX", vdp.reg[36], 5);

    /* lmmm-dix: the same copy going left (DIX): SX 2, DX 7 take x = 2, 1, 0 to x = 7, 6, 5: the same bytes as above. */
    setmode(0x06);
    VR(0) = 0x12;
    VR(1) = 0x30;
    block(2, 0, 7, 0, 3, 1, 0, 4);
    go(0x90);
    idle();
    check_hex("lmmm-dix 0002h", VR(2), 0x01);
    check_hex("lmmm-dix 0003h", VR(3), 0x23);

    /* lmmm-overlap: SX 0, DX 1, NX 3 going right over the same row: the units run in order, each reading what the one
     * before wrote: x1 <- x0 (1), x2 <- x1 (now 1), x3 <- x2 (now 1). Byte 0 = 11h, byte 1 = 11h (x2 was 3, x3 was 0). */
    setmode(0x06);
    VR(0) = 0x12;
    VR(1) = 0x30;
    block(0, 0, 1, 0, 3, 1, 0, 0);
    go(0x90);
    idle();
    check_hex("lmmm-overlap 0000h", VR(0), 0x11);
    check_hex("lmmm-overlap 0001h", VR(1), 0x11);

    /* lmmm-ops: source dot 6, destination dot 3 (one dot, x = 0 and x = 8: bytes 0000h = 60h, 0004h = 30h), XOR (code 93h):
     * 6 xor 3 = 5. T-IMP (98h) with source 0 keeps the destination, with source 6 writes 6. */
    setmode(0x06);
    VR(0) = 0x60;
    VR(4) = 0x30;
    block(0, 0, 8, 0, 1, 1, 0, 0);
    go(0x93);
    idle();
    check_hex("lmmm-ops XOR", VR(4), 0x50);
    VR(4) = 0x30;
    VR(0) = 0x00;
    block(0, 0, 8, 0, 1, 1, 0, 0);
    go(0x98);
    idle();
    check_hex("lmmm-ops TIMP with source 0", VR(4), 0x30);
    VR(0) = 0x60;
    block(0, 0, 8, 0, 1, 1, 0, 0);
    go(0x98);
    idle();
    check_hex("lmmm-ops TIMP with source 6", VR(4), 0x60);

    /* lmmm-time: three dots on one line, class 0: due at 123, 123 + 130, 123 + 260 = 383 ticks; 383 / 6 = 63.83: CE set
     * 63 cycles after the write (378 ticks), clear at 64. */
    setmode(0x06);
    block(0, 0, 5, 0, 3, 1, 0, 0);
    go(0x90);
    check("lmmm-time CE lasts (cycles)", ce_after(), 64);
}

static void cpu_paced_checks(void)
{
    /* lmmc: DX 1, DY 0, NX 3, NY 1; the R#44 written with the registers is dot 1 (DESIGN 1.5: runs inside the R#46 write);
     * then 2 and 3 by R#44 writes. x = 1 is the low nibble of byte 0 (01h), x = 2 and 3 byte 1 (23h). TR is set from the
     * start, CE is set until the third dot. */
    setmode(0x06);
    block(0, 0, 1, 0, 3, 1, 1, 0);
    go(0xB0);
    check_hex("lmmc first dot in the R#46 write: 0000h", VR(0), 0x01);
    check_hex("lmmc S#2 TR and CE after the first dot", status(2) & 0x81, 0x81);

    /* lmmc-pace: the engine never moves by itself: 50 lines later, still the first dot only. */
    msx_advance(&m, 50 * LINE);
    check_hex("lmmc-pace 0001h after 50 lines", VR(1), 0x00);
    check_hex("lmmc-pace S#2 TR and CE", status(2) & 0x81, 0x81);
    reg(44, 2);
    check_hex("lmmc second dot: 0001h", VR(1), 0x20);
    check_hex("lmmc S#2 after the second dot", status(2) & 0x81, 0x81);
    reg(44, 3);
    check_hex("lmmc third dot: 0001h", VR(1), 0x23);
    /* TR is tested before the unit runs (DESIGN 1.5), so the last dot leaves TR set; the command is over: CE 0. */
    check_hex("lmmc S#2 after the last dot (TR stays, CE 0)", status(2) & 0x81, 0x80);
    check("lmmc DY", vdp.reg[38], 1);
    check("lmmc NY", vdp.reg[42], 0);
    check_hex("lmmc R#46 back to 0", vdp.reg[46], 0);
    /* One more R#44 write with no command running clears TR and draws nothing. */
    reg(44, 9);
    check_hex("lmmc extra R#44 write clears TR", status(2) & 0x81, 0x00);
    check("lmmc extra write VRAM sum", vram_sum(), 0x01 + 0x23);

    /* lmcm: 0000h = 12h, 0001h = 34h; SX 0, SY 0, NX 3, NY 1, old R#44 = 77h. Dots 1, 2, 3 (x = 2 is the high nibble of byte
     * 1 = 3). Start delay 66 ticks, 66 / 6 = 11: nothing is fetched 10 cycles after the write, the first dot at 11. */
    setmode(0x06);
    VR(0) = 0x12;
    VR(1) = 0x34;
    block(0, 0, 0, 0, 3, 1, 0x77, 0);
    go(0xA0);
    check_hex("lmcm S#7 at start = old R#44", status(7), 0x77);
    check_hex("lmcm S#2 TR and CE after the start", status(2) & 0x81, 0x81);
    msx_advance(&m, 10);
    check_hex("lmcm S#7 before 66 ticks = old R#44", status(7), 0x77);
    msx_advance(&m, 1);
    check_hex("lmcm S#7 first read = dot 1", status(7), 0x01);
    check_hex("lmcm S#2 after the first read", status(2) & 0x81, 0x81);
    /* The first read already fetched dot 2 and the second fetches dot 3, the last: CE drops then, before the CPU has read
     * it, and TR stays until that last read (DESIGN 1.5). */
    check_hex("lmcm S#7 second read = dot 2", status(7), 0x02);
    check_hex("lmcm S#2 CE 0 once the last dot is fetched, TR 1", status(2) & 0x81, 0x80);
    check_hex("lmcm S#7 third read = dot 3", status(7), 0x03);
    check_hex("lmcm S#2 TR 0 after the last read", status(2) & 0x81, 0x00);
    check("lmcm SY", vdp.reg[34], 1);
    check("lmcm NY", vdp.reg[42], 0);
    check("lmcm DY untouched", vdp.reg[38], 0);
    check_hex("lmcm R#44 = last dot", vdp.reg[44], 0x03);
    check_hex("lmcm R#46 back to 0", vdp.reg[46], 0);
    check("lmcm VRAM unchanged", vram_sum(), 0x12 + 0x34);
}

static void point_pset_checks(void)
{
    /* pset: PSET at (3, 1), COL 7, IMP: the address is (1 << 7) | (3 >> 1) = 0081h, x odd = low nibble: 07h. DY and the
     * other registers do not change; CE lasts the start delay, 117 ticks = 20 cycles; sum shows nothing else moved. */
    setmode(0x06);
    block(0, 0, 3, 1, 0, 0, 7, 0);
    go(0x50);
    check("pset CE lasts (cycles)", ce_after(), 20);
    check_hex("pset 0081h", VR(0x81), 0x07);
    check("pset VRAM sum", vram_sum(), 7);
    check("pset DY unchanged", vdp.reg[38], 1);
    check_hex("pset R#46 back to 0", vdp.reg[46], 0);

    /* pset-ops: with 0081h = A5h, XOR of 7 on the low nibble: 5 xor 7 = 2 -> A2h; T-IMP with colour 0 keeps A5h. */
    VR(0x81) = 0xA5;
    block(0, 0, 3, 1, 0, 0, 7, 0);
    go(0x53);
    idle();
    check_hex("pset-ops XOR", VR(0x81), 0xA2);
    VR(0x81) = 0xA5;
    block(0, 0, 3, 1, 0, 0, 0, 0);
    go(0x58);
    idle();
    check_hex("pset-ops TIMP with colour 0", VR(0x81), 0xA5);

    /* point: 0081h = 37h; POINT (3, 1) = 7 (low nibble), POINT (2, 1) = 3 (high nibble). R#44 and S#7 return the dot.
     * Start 66 ticks = 11, due at 11 cycles. */
    setmode(0x06);
    VR(0x81) = 0x37;
    block(3, 1, 0, 0, 0, 0, 0, 0);
    go(0x40);
    check("point CE lasts (cycles)", ce_after(), 11);
    check_hex("point R#44", vdp.reg[44], 0x07);
    check_hex("point S#7", status(7), 0x07);
    block(2, 1, 0, 0, 0, 0, 0, 0);
    go(0x40);
    idle();
    check_hex("point (2, 1) high nibble", status(7), 0x03);
    check("point VRAM sum", vram_sum(), 0x37);
}

static void mode_checks(void)
{
    /* g5-dot: Graphic 5, 2 bits a dot, 4 dots a byte, x = 0 in the top bits: LMMV at (5, 0), colour 2: byte 5 >> 2 = 1,
     * shift (~5 and 3) * 2 = 4: 0001h = 20h. */
    setmode(0x08);
    block(0, 0, 5, 0, 1, 1, 2, 0);
    go(0x80);
    idle();
    check_hex("g5-dot 0001h", VR(1), 0x20);
    check("g5-dot VRAM sum", vram_sum(), 0x20);

    /* g5 colour mask: COL FEh is masked to 2 bits = 2 (not 3 or FEh): the same byte. */
    setmode(0x08);
    block(0, 0, 5, 0, 1, 1, 0xFE, 0);
    go(0x80);
    idle();
    check_hex("g5 colour masked to 2 bits", VR(1), 0x20);

    /* g5-lmmm: byte 0000h = 1Bh = dots 0, 1, 2, 3 (top bits first); copied to x = 4-7 of line 1 (byte 128 + 1 = 0081h):
     * the same 1Bh. */
    setmode(0x08);
    VR(0) = 0x1B;
    block(0, 0, 4, 1, 4, 1, 0, 0);
    go(0x90);
    idle();
    check_hex("g5-lmmm 0081h", VR(0x81), 0x1B);
    check("g5-lmmm VRAM sum", vram_sum(), 0x1B + 0x1B);

    /* g5-nibble: dot 2 of 0000h (bits 3-2 = 2) copied to x = 7 (bits 1-0 of byte 1): 01h with its dot 0 .. 2 set to 2. */
    setmode(0x08);
    VR(0) = 0x1B;
    block(2, 0, 7, 0, 1, 1, 0, 0);
    go(0x90);
    idle();
    check_hex("g5-nibble 0001h", VR(1), 0x02);

    /* g5-edge: 512 dots a line: LMMV at x = 511 (R#37 = 1) with NX 4 draws min(4, 512 - 511) = 1 dot: byte 127 = 01h and
     * the next line's first byte (0080h) stays 0. */
    setmode(0x08);
    block(0, 0, 511, 0, 4, 1, 1, 0);
    go(0x80);
    idle();
    check_hex("g5-edge 007Fh", VR(0x7F), 0x01);
    check_hex("g5-edge 0080h", VR(0x80), 0x00);

    /* g6-dot: Graphic 6, 512 dots, 4 bits, 256 bytes a line: LMMV at (3, 1), colour 9: (1 << 8) | 1 = 0101h, x odd = low
     * nibble: 09h. */
    setmode(0x0A);
    block(0, 0, 3, 1, 1, 1, 9, 0);
    go(0x80);
    idle();
    check_hex("g6-dot 0101h", VR(0x101), 0x09);
    check("g6-dot VRAM sum", vram_sum(), 9);

    /* g6-lmmm: dots 1, 2, 3 (0000h = 12h, 0001h = 30h) to x = 300, y = 1: the address is 0100h + 150 = 0196h; x = 300 is
     * even, so dots 1 and 2 are byte 0196h = 12h and dot 3 is the high nibble of 0197h = 30h. */
    setmode(0x0A);
    VR(0) = 0x12;
    VR(1) = 0x30;
    block(0, 0, 300, 1, 3, 1, 0, 0);
    go(0x90);
    idle();
    check_hex("g6-lmmm 0196h", VR(0x196), 0x12);
    check_hex("g6-lmmm 0197h", VR(0x197), 0x30);

    /* g6-edge: LMMV at x = 510, NX 4, colour Fh on line 0: min(4, 512 - 510) = 2 dots, byte 255 = FFh; 0100h stays 0. */
    setmode(0x0A);
    block(0, 0, 510, 0, 4, 1, 0xF, 0);
    go(0x80);
    idle();
    check_hex("g6-edge 00FFh", VR(0xFF), 0xFF);
    check_hex("g6-edge 0100h", VR(0x100), 0x00);

    /* g7-dot: Graphic 7, 256 dots of a byte: LMMV at (3, 1), colour A5h (the whole byte is the colour): (1 << 8) | 3 =
     * 0103h = A5h. */
    setmode(0x0E);
    block(0, 0, 3, 1, 1, 1, 0xA5, 0);
    go(0x80);
    idle();
    check_hex("g7-dot 0103h", VR(0x103), 0xA5);
    check("g7-dot VRAM sum", vram_sum(), 0xA5);

    /* g7-not: NOT (code 84h) of 5Ah in an 8-bit dot is A5h. */
    setmode(0x0E);
    block(0, 0, 3, 1, 1, 1, 0x5A, 0);
    go(0x84);
    idle();
    check_hex("g7-not 0103h", VR(0x103), 0xA5);

    /* g7-lmmm-t: source bytes 11h, 00h, 33h at x = 0-2 of line 0, destination (10, 2) holding AAh, BBh, CCh, TIMP (code 98h):
     * the zero source dot keeps BBh: 11h, BBh, 33h at 0200h + 10 = 020Ah. */
    setmode(0x0E);
    VR(0) = 0x11;
    VR(1) = 0x00;
    VR(2) = 0x33;
    VR(0x20A) = 0xAA;
    VR(0x20B) = 0xBB;
    VR(0x20C) = 0xCC;
    block(0, 0, 10, 2, 3, 1, 0, 0);
    go(0x98);
    idle();
    check_hex("g7-lmmm-t 020Ah", VR(0x20A), 0x11);
    check_hex("g7-lmmm-t 020Bh", VR(0x20B), 0xBB);
    check_hex("g7-lmmm-t 020Ch", VR(0x20C), 0x33);

    /* g7-edge: 256 dots a line: LMMV at x = 254, NX 5: min(5, 256 - 254) = 2 dots: 00FEh and 00FFh = 77h, 0100h stays 0. */
    setmode(0x0E);
    block(0, 0, 254, 0, 5, 1, 0x77, 0);
    go(0x80);
    idle();
    check_hex("g7-edge 00FEh", VR(0xFE), 0x77);
    check_hex("g7-edge 00FFh", VR(0xFF), 0x77);
    check_hex("g7-edge 0100h", VR(0x100), 0x00);
}

int main(void)
{
    lmmv_checks();
    lmmm_checks();
    cpu_paced_checks();
    point_pset_checks();
    mode_checks();
    printf("%s\n", failures ? "FAILED" : "all MSX2 dot command checks passed");
    return failures ? 1 : 0;
}
