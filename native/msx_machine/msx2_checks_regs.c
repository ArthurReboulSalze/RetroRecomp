/* MSX2 hardware fixtures, V9938 registers, ports, palette, VRAM pointer, status registers and line timing.
 * MIT, Retro-Recomp. A development check, never built into a game. Each fixture programs a fresh machine through its
 * I/O ports (no CPU, no BIOS code), advances machine time with msx_advance (228 cycles a line, 262 lines NTSC), and
 * compares with values worked out by hand from the V9938 Technical Data Book, the MSX2 Technical Handbook and the
 * stage 6 design note (the expected number and its reason are written next to each check). Time zero is the boundary
 * of line 0 (the start of the left border); the draw point of line L, where its line interrupt flag rises, is
 * 228 * L + 180; the frame flag rises at the boundary of the first line after the picture (192 or 212).
 * Prints one line per check and exits 1 if any fails. */
#include "msx_machine.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { LINE = MSX_CYCLES_PER_LINE, DRAW = MSX2_DRAW_AT };

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

static void point(uint16_t address, int write)
{
    msx_out(&m, 0x99, (uint8_t)(address & 0xFF));
    msx_out(&m, 0x99, (uint8_t)((write ? 0x40 : 0x00) | (address >> 8)));
}

/* A status register, through R#15 and port 99h. */
static uint8_t status(int n) { reg(15, (uint8_t)n); return msx_in(&m, 0x99); }

/* Run to an absolute machine cycle of this machine's time. */
static void to(uint64_t cycle) { if (cycle > m.cycles) msx_advance(&m, cycle - m.cycles); }

/* Run whole lines until `frames` frames have wrapped: the machine then sits exactly at the boundary of line 0. */
static void to_frame(uint64_t frames) { for (int guard = 0; m.frames < frames && guard < 2000; ++guard) msx_advance(&m, LINE); }

static uint64_t line_start(void) { return m.next_line - LINE; }

static int fh_flag(void) { return vdp.status1 & 1; }
static int f_flag(void) { return (vdp.status0 & 0x80) != 0; }

static void register_checks(void)
{
    /* reg-masks: Data Book register list, a bit that does not exist reads back 0. R#0 7E (bits 7 and 0 unused), R#1 7F,
     * R#2 7F, R#3 FF, R#4 3F, R#5 FF, R#6 3F, R#7 FF, R#8 FB, R#9 BF, R#10 07, R#11 03, R#12 FF, R#13 FF, R#14 07,
     * R#15 0F, R#16 0F, R#17 BF, R#18 FF, R#19 FF, R#20 3F, R#21 3F, R#22 3F, R#23 FF. */
    static const uint8_t masks[24] = { 0x7E, 0x7F, 0x7F, 0xFF, 0x3F, 0xFF, 0x3F, 0xFF, 0xFB, 0xBF, 0x07, 0x03,
                                       0xFF, 0xFF, 0x07, 0x0F, 0x0F, 0xBF, 0xFF, 0xFF, 0x3F, 0x3F, 0x3F, 0xFF };
    fresh();
    for (int r = 0; r < 24; ++r) reg(r, 0xFF);
    int wrong = 0;
    for (int r = 0; r < 24; ++r) wrong += vdp.reg[r] != masks[r];
    check("reg-masks (registers that differ from the mask row)", wrong, 0);
    reg(24, 0xFF);
    reg(31, 0xFF);
    reg(47, 0xFF);
    reg(63, 0xFF);
    int stray = 0;
    for (int r = 24; r < 32; ++r) stray += vdp.reg[r] != 0;
    check("reg-masks R#24-R#31 do not exist", stray, 0);

    /* ctrl-latch: 12h is a first byte; the status read abandons it; 34h is then the first byte of a new pair, so
     * 34h, 87h writes R#7 = 34h (Data Book: reading the status register resets the two-byte sequence). */
    fresh();
    msx_out(&m, 0x99, 0x12);
    (void)msx_in(&m, 0x99);
    msx_out(&m, 0x99, 0x34);
    msx_out(&m, 0x99, 0x87);
    check_hex("ctrl-latch R#7", vdp.reg[7], 0x34);

    /* indirect: R#17 = 02h (auto-increment, start at R#2); 9Bh 1Fh then 00h: R#2 = 1Fh, R#3 = 00h, R#17 -> 04h. */
    fresh();
    reg(3, 0x55);
    reg(17, 0x02);
    msx_out(&m, 0x9B, 0x1F);
    msx_out(&m, 0x9B, 0x00);
    check_hex("indirect R#2", vdp.reg[2], 0x1F);
    check_hex("indirect R#3", vdp.reg[3], 0x00);
    check_hex("indirect R#17", vdp.reg[17], 0x04);

    /* indirect-hold: R#17 = 82h (bit 7 = no auto-increment): both bytes go to R#2, the last wins, R#17 stays 82h. */
    fresh();
    reg(17, 0x82);
    msx_out(&m, 0x9B, 0x11);
    msx_out(&m, 0x9B, 0x22);
    check_hex("indirect-hold R#2", vdp.reg[2], 0x22);
    check_hex("indirect-hold R#17", vdp.reg[17], 0x82);

    /* palette: R#16 = 4; first byte 0RRR0BBB = 73h (R 7, B 3), second 0GGG = 05h (G 5): entry 573h, R#16 -> 5
     * (Data Book palette registers: red-blue byte first, then green). */
    fresh();
    reg(16, 4);
    msx_out(&m, 0x9A, 0x73);
    msx_out(&m, 0x9A, 0x05);
    check_hex("palette[4]", vdp.palette[4], 0x573);
    check("palette R#16 steps", vdp.reg[16], 5);
    /* The pointer wraps from 15 to 0 and unused bits are dropped (0RRR0BBB, 0GGG). */
    reg(16, 15);
    msx_out(&m, 0x9A, 0xFF);
    msx_out(&m, 0x9A, 0xFF);
    check_hex("palette[15] masked", vdp.palette[15], 0x777);
    check("palette R#16 wraps 15 -> 0", vdp.reg[16], 0);

    /* palette-reset: Data Book appendix, entry 8 = 171h (G 1, R 7, B 1: RGB 255, 36, 36). */
    fresh();
    check_hex("palette-reset entry 8", vdp.palette[8], 0x171);
    check_hex("palette-reset entry 15", vdp.palette[15], 0x777);

    /* palette-abort: a first byte written, then R#16 written: the entry starts over (DESIGN 1.3). R#16 = 1, 9Ah 11h,
     * R#16 = 2, 9Ah 22h, 03h -> entry 2 = 322h, entry 1 untouched (reset value 000h), R#16 -> 3. */
    fresh();
    reg(16, 1);
    msx_out(&m, 0x9A, 0x11);
    reg(16, 2);
    msx_out(&m, 0x9A, 0x22);
    msx_out(&m, 0x9A, 0x03);
    check_hex("palette-abort entry 2", vdp.palette[2], 0x322);
    check_hex("palette-abort entry 1", vdp.palette[1], 0x000);
    check("palette-abort R#16", vdp.reg[16], 3);
}

static void pointer_checks(void)
{
    /* pointer-carry: Graphic 4 (R#0 = 06h, a V9938 mode), R#14 = 1, pointer 3FFFh: A at 7FFFh, then the 14-bit pointer
     * wraps and carries into R#14 (now 2): B at 8000h. */
    fresh();
    reg(0, 0x06);
    reg(14, 1);
    point(0x3FFF, 1);
    msx_out(&m, 0x98, 0xAA);
    msx_out(&m, 0x98, 0xBB);
    check_hex("pointer-carry vram[7FFF]", vdp.vram[0x7FFF], 0xAA);
    check_hex("pointer-carry vram[8000]", vdp.vram[0x8000], 0xBB);
    check("pointer-carry R#14", vdp.reg[14], 2);

    /* pointer-nocarry: Graphic 2 (a TMS9918A-compatible mode): the pointer wraps inside the 16 KB bank, R#14 stays 1:
     * A at 7FFFh, B at 4000h. */
    fresh();
    reg(0, 0x02);
    reg(14, 1);
    point(0x3FFF, 1);
    msx_out(&m, 0x98, 0xAA);
    msx_out(&m, 0x98, 0xBB);
    check_hex("pointer-nocarry vram[7FFF]", vdp.vram[0x7FFF], 0xAA);
    check_hex("pointer-nocarry vram[4000]", vdp.vram[0x4000], 0xBB);
    check("pointer-nocarry R#14", vdp.reg[14], 1);

    /* The top bank wraps too: R#14 = 7 in Graphic 4 carries 7 -> 0 (three bits). */
    fresh();
    reg(0, 0x06);
    reg(14, 7);
    point(0x3FFF, 1);
    msx_out(&m, 0x98, 0x66);
    msx_out(&m, 0x98, 0x67);
    check("pointer-carry R#14 7 -> 0", vdp.reg[14], 0);
    check_hex("pointer-carry wrote 0000h", vdp.vram[0x0000], 0x67);

    /* read setup: the bytes written at 0100h come back through a read pointer (bit 6 clear in the second byte), one per
     * read of 98h, the pointer stepping each time. */
    fresh();
    point(0x0100, 1);
    msx_out(&m, 0x98, 0x11);
    msx_out(&m, 0x98, 0x22);
    msx_out(&m, 0x98, 0x33);
    point(0x0100, 0);
    int a = msx_in(&m, 0x98), b = msx_in(&m, 0x98), c = msx_in(&m, 0x98);
    check_hex("read-setup first", a, 0x11);
    check_hex("read-setup second", b, 0x22);
    check_hex("read-setup third", c, 0x33);
}

static void status_checks(void)
{
    /* status-2, idle: in the displayed part of an active line, with no command running: 0Ch only (bits 3-2 read 1);
     * TR, BD, CE, HR, VR all 0, EO 0 in the first frame. Line 100, cycle 100. */
    fresh();
    to(100 * LINE + 100);
    check_hex("status-2 idle", status(2), 0x0C);

    /* HR (S#2 bit 5): the horizontal blank, 1 outside the displayed part [cycle 9, cycle 180) of a line (DESIGN 1.4,
     * from the Data Book's display period); line 10 so VR is 0 too. */
    fresh();
    to(10 * LINE + 8);
    check_hex("status-2 HR at cycle 8", status(2), 0x2C);
    to(10 * LINE + 9);
    check_hex("status-2 HR at cycle 9", status(2), 0x0C);
    to(10 * LINE + 179);
    check_hex("status-2 HR at cycle 179", status(2), 0x0C);
    to(10 * LINE + 180);
    check_hex("status-2 HR at cycle 180", status(2), 0x2C);

    /* VR (S#2 bit 6): the vertical blank, from the boundary of the first line after the picture (192) to the boundary of
     * the last line of the frame (261) (DESIGN 1.4). Read at cycle 100 of a line so HR is 0. */
    to(191 * LINE + 100);
    check_hex("status-2 VR line 191", status(2), 0x0C);
    to(192 * LINE + 100);
    check_hex("status-2 VR line 192", status(2), 0x4C);
    to(260 * LINE + 100);
    check_hex("status-2 VR line 260", status(2), 0x4C);
    to(261 * LINE + 100);
    check_hex("status-2 VR line 261", status(2), 0x0C);

    /* EO (S#2 bit 1) toggles at every frame start, reading 0 in the first frame (S#2 = 0Ch after reset): 0Ch, 0Eh,
     * 0Ch, 0Eh at line 100 cycle 100 of four frames. */
    fresh();
    int eo[4];
    for (int f = 0; f < 4; ++f) {
        to_frame((uint64_t)f);
        to(line_start() + 100 * LINE + 100);
        eo[f] = status(2);
    }
    check_hex("EO frame 0", eo[0], 0x0C);
    check_hex("EO frame 1", eo[1], 0x0E);
    check_hex("EO frame 2", eo[2], 0x0C);
    check_hex("EO frame 3", eo[3], 0x0E);

    /* S#0: F rises at the boundary of line 192 (cycle 43776) and a read clears it, with the interrupt it raised. R#1
     * IE0 (bit 5) set while F is already 1 raises /INT at once (Data Book: the interrupt is F and IE0). */
    fresh();
    to(192 * (uint64_t)LINE - 1);
    check("F before line 192", f_flag(), 0);
    to(192 * (uint64_t)LINE);
    check("F at line 192 (f-192)", f_flag(), 1);
    check("irq low while IE0 is off", msx_irq(&m), 0);
    reg(1, 0x20);
    check("irq rises when IE0 is set with F on", msx_irq(&m), 1);
    check_hex("S#0 read gives F", status(0), 0x80);
    check("S#0 read drops irq", msx_irq(&m), 0);
    check_hex("S#0 second read", status(0), 0x00);
    to(262 * (uint64_t)LINE + 192 * LINE);
    check("irq again on the next frame", msx_irq(&m), 1);
    reg(1, 0x00);
    check("irq drops when IE0 is cleared", msx_irq(&m), 0);

    /* S#3-S#6: collision coordinates, 9 bits x and 10 bits y, upper bits of the high register read 1 (S#4 FEh | x8, S#6
     * FCh | y9-y8); a read of S#5 clears both coordinates, S#3 then reads 0 and S#4/S#6 their idle FEh/FCh. */
    fresh();
    vdp.collision_x = 0x123;
    vdp.collision_y = 0x105;
    check_hex("S#3", status(3), 0x23);
    check_hex("S#4", status(4), 0xFF);
    check_hex("S#6", status(6), 0xFD);
    check_hex("S#5", status(5), 0x05);
    check_hex("S#3 after S#5", status(3), 0x00);
    check_hex("S#4 after S#5", status(4), 0xFE);
    check_hex("S#5 after S#5", status(5), 0x00);
    check_hex("S#6 after S#5", status(6), 0xFC);
}

static void line_irq_checks(void)
{
    /* line-irq: R#19 = 100, R#23 = 0, IE1 (R#0 bit 4): FH and /INT at the draw point of line 100, 228 * 100 + 180 =
     * 22980 cycles after the boundary of line 0. */
    fresh();
    reg(23, 0);
    reg(19, 100);
    reg(0, 0x10);
    to(22979);
    check("line-irq FH before", fh_flag(), 0);
    check("line-irq /INT before", msx_irq(&m), 0);
    to(22980);
    check("line-irq FH at 22980", fh_flag(), 1);
    check("line-irq /INT at 22980", msx_irq(&m), 1);
    check_hex("line-irq S#1 read", status(1), 0x01);
    check("line-irq S#1 read clears FH", fh_flag(), 0);
    check("line-irq S#1 read drops /INT", msx_irq(&m), 0);
    to(23 * (uint64_t)LINE * 10);
    check("line-irq does not repeat on line 101", fh_flag(), 0);

    /* IE1 falling clears a pending FH (Data Book: FH is tied to the enable). */
    fresh();
    reg(19, 30);
    reg(0, 0x10);
    to(30 * LINE + 180);
    check("line-irq pending", fh_flag(), 1);
    reg(0, 0x00);
    check("line-irq IE1 off clears FH", fh_flag(), 0);

    /* line-irq-scroll: R#23 = 40 shifts the compare: the line counted is (R#19 - R#23) = 60, so 228 * 60 + 180 = 13860. */
    fresh();
    reg(23, 40);
    reg(19, 100);
    reg(0, 0x10);
    to(13859);
    check("line-irq-scroll before", fh_flag(), 0);
    to(13860);
    check("line-irq-scroll at 13860", fh_flag(), 1);

    /* line-irq-never, 192 lines NTSC: the counter runs 262 - 17 - 10 = 235 lines before it resets, so R#19 = 235 never
     * matches and 234 does (Data Book: a line past the last counted line gives no interrupt). */
    fresh();
    reg(19, 235);
    reg(0, 0x10);
    int seen = 0;
    for (int i = 0; i < 262 * 2; ++i) { msx_advance(&m, LINE); seen |= fh_flag(); }
    check("line-irq-never 192 lines R#19 = 235", seen, 0);
    fresh();
    reg(19, 234);
    reg(0, 0x10);
    to(234 * (uint64_t)LINE + 180);
    check("line-irq 192 lines R#19 = 234 fires", fh_flag(), 1);

    /* line-irq-never, 212 lines NTSC (LN set, taken at the next frame start): 262 - 17 = 245 lines, so 250 never
     * matches, 244 does at its draw point. Time is taken from the boundary of line 0 of frame 1. */
    fresh();
    reg(9, 0x80);
    reg(19, 250);
    reg(0, 0x10);
    to_frame(1);
    seen = 0;
    for (int i = 0; i < 262; ++i) { msx_advance(&m, LINE); seen |= fh_flag(); }
    check("line-irq-never 212 lines R#19 = 250", seen, 0);
    fresh();
    reg(9, 0x80);
    reg(19, 244);
    reg(0, 0x10);
    to_frame(1);
    uint64_t t0 = line_start();
    to(t0 + 244 * (uint64_t)LINE + 179);
    check("line-irq 212 lines R#19 = 244 before", fh_flag(), 0);
    to(t0 + 244 * (uint64_t)LINE + 180);
    check("line-irq 212 lines R#19 = 244 fires", fh_flag(), 1);

    /* fh-polled: IE1 clear, R#19 = 50: S#1 bit 0 reads 1 only from cycle 180 of line 50 to the end of that line. */
    fresh();
    reg(19, 50);
    reg(15, 1);
    to(50 * LINE - 1);
    check("fh-polled line 49 end", msx_in(&m, 0x99) & 1, 0);
    to(50 * LINE + 179);
    check("fh-polled line 50 cycle 179", msx_in(&m, 0x99) & 1, 0);
    to(50 * LINE + 180);
    check("fh-polled line 50 cycle 180", msx_in(&m, 0x99) & 1, 1);
    to(50 * LINE + 227);
    check("fh-polled line 50 cycle 227", msx_in(&m, 0x99) & 1, 1);
    check("fh-polled read keeps no latch", fh_flag(), 0);
    to(51 * LINE);
    check("fh-polled line 51", msx_in(&m, 0x99) & 1, 0);
}

static void frame_checks(void)
{
    /* f-192: LN clear, F at the boundary of line 192 (cycle 43776), checked in the status checks above. f-212: LN set
     * (R#9 bit 7) in the middle of frame 0: the frame flag at the boundary of line 212 (cycle 48336) as R#9 is then
     * (Data Book: the number of lines is the one in R#9 at the end of the picture). Not before. */
    fresh();
    reg(9, 0x80);
    to(212 * (uint64_t)LINE - 1);
    check("f-212 F not before line 212 (frame 0)", f_flag(), 0);
    to(212 * (uint64_t)LINE);
    check("f-212 F at line 212 (frame 0)", f_flag(), 1);

    /* The same one frame later, after the frame start has seen LN: F at line 212 of frame 1, not at 192. */
    fresh();
    reg(9, 0x80);
    to_frame(1);
    (void)status(0);
    uint64_t t0 = line_start();
    to(t0 + 211 * (uint64_t)LINE + 227);
    check("f-212 F absent at the end of line 211 (frame 1)", f_flag(), 0);
    to(t0 + 212 * (uint64_t)LINE);
    check("f-212 F at line 212 (frame 1)", f_flag(), 1);

    /* pal-switch: R#9 bit 1 set during frame 0 (262 lines): frame 1 has 313 lines, the next frame start after that. */
    fresh();
    reg(9, 0x02);
    to_frame(1);
    check("pal-switch lines per frame", m.lines_per_frame, 313);
    int lines = 0;
    while (m.frames < 2 && lines < 1000) { msx_advance(&m, LINE); ++lines; }
    check("pal-switch frame 1 length in lines", lines, 313);

    /* line-irq in 50 Hz, 192 lines: 313 - 44 - 10 = 259 lines counted, and R#19 holds at most 255, so every value
     * fires: R#19 = 255 at 228 * 255 + 180 after the boundary of line 0 of a PAL frame (the line is reachable only
     * because the PAL frame is longer than the NTSC one, where 255 >= 235 never matches). */
    fresh();
    reg(9, 0x02);
    reg(19, 255);
    reg(0, 0x10);
    to_frame(1);
    uint64_t t1 = line_start();
    to(t1 + 255 * (uint64_t)LINE + 179);
    check("line-irq PAL R#19 = 255 before", fh_flag(), 0);
    to(t1 + 255 * (uint64_t)LINE + 180);
    check("line-irq PAL R#19 = 255 fires", fh_flag(), 1);
}

/* R#13: the high nibble is the ON time and the low one the OFF time, in units of 10 frames; the state flips after that
 * many frame starts. The ON state starts at the write. */
static void blink_checks(void)
{
    char got[40], want[40];

    /* R#13 = 11h: ON 10 frames, OFF 10: after 1..9 frames on, 10..19 off, 20 on again. */
    fresh();
    reg(13, 0x11);
    int n = 0;
    for (int f = 1; f <= 20; ++f) { msx_advance(&m, (uint64_t)LINE * MSX_LINES_NTSC); got[n++] = vdp.blink_on ? '1' : '0'; }
    got[n] = 0;
    strcpy(want, "111111111" "0000000000" "1");
    check("blink R#13 = 11h", strcmp(got, want) == 0, 1);
    if (strcmp(got, want)) printf("     got %s want %s\n", got, want);

    /* R#13 = 21h: ON 20 frames, OFF 10: on through frame 19, off 20..29, on at 30. */
    fresh();
    reg(13, 0x21);
    n = 0;
    for (int f = 1; f <= 30; ++f) { msx_advance(&m, (uint64_t)LINE * MSX_LINES_NTSC); got[n++] = vdp.blink_on ? '1' : '0'; }
    got[n] = 0;
    strcpy(want, "1111111111111111111" "0000000000" "1");
    check("blink R#13 = 21h", strcmp(got, want) == 0, 1);
    if (strcmp(got, want)) printf("     got %s want %s\n", got, want);

    /* R#13 = 00h: no blinking, always the OFF state. */
    fresh();
    reg(13, 0x00);
    for (int f = 0; f < 15; ++f) msx_advance(&m, (uint64_t)LINE * MSX_LINES_NTSC);
    check("blink R#13 = 00h stays off", vdp.blink_on, 0);
}

int main(void)
{
    register_checks();
    pointer_checks();
    status_checks();
    line_irq_checks();
    frame_checks();
    blink_checks();
    printf("%s\n", failures ? "FAILED" : "all MSX2 register checks passed");
    return failures ? 1 : 0;
}
