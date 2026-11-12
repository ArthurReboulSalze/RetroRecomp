/* MSX2 board fixtures: the slot layout of msx_setup_msx2, the secondary-slot register, the memory mapper (ports FCh-FFh)
 * and the RP5C01 clock (ports B4h/B5h). MIT, Retro-Recomp. A development check, never built into a game.
 * Each fixture programs the chips through their I/O ports on a fresh machine (no CPU runs), advances time with
 * msx_advance in machine cycles, and compares with values worked out by hand from the MSX2 Technical Handbook, the
 * RP5C01 data sheet and the rules of stage 6's design note (the reasoning is next to each check). Prints one line per
 * check and exits 1 if any fails. */
#include "msx_machine.h"

#include <stdio.h>
#include <string.h>

enum { SEGMENTS = 16, SEG = 0x4000 };

static MsxMachine m;
static MsxV9938 vdp;
static uint8_t ram[SEGMENTS * SEG];
static uint8_t bios[0x10000];
static int failures;

static void check(const char *name, long got, long want)
{
    printf("%s %s: %ld (expected %ld)\n", got == want ? "ok  " : "FAIL", name, got, want);
    failures += got != want;
}

static void check_read(const char *name, uint16_t address, uint8_t want) { check(name, msx_read(&m, address), want); }

/* A BIOS image of FFh with a marker at the start and the end of each part: main ROM 0000h-7FFFh, the logo page
 * 8000h-BFFFh, the sub-ROM C000h-FFFFh (its own addresses 0000h-3FFFh). 0x13 sits in the main ROM at 4000h. */
static void setup(uint32_t segments)
{
    memset(bios, 0xFF, sizeof bios);
    bios[0x0000] = 0x11; bios[0x4000] = 0x13; bios[0x7FFF] = 0x12;
    bios[0x8000] = 0x21; bios[0xBFFF] = 0x22;
    bios[0xC000] = 0x31; bios[0xFFFF] = 0x32;
    memset(ram, 0, sizeof ram);
    msx_init(&m, MSX_LINES_NTSC);
    msx_setup_msx2(&m, bios, ram, segments, &vdp);
}

/* ---- the RP5C01 helpers: register number to B4h, nibble through B5h ---- */
static void rtc_w(int reg, int value) { msx_out(&m, 0xB4, (uint8_t)reg); msx_out(&m, 0xB5, (uint8_t)value); }
static int rtc_raw(int reg) { msx_out(&m, 0xB4, (uint8_t)reg); return msx_in(&m, 0xB5); }
static int nib(int reg) { return rtc_raw(reg) & 0x0F; }
/* Block 0 registers: 0/1 seconds, 2/3 minutes, 4/5 hours, 6 weekday, 7/8 day, 9/10 month, 11/12 year. */
static long clock_hms(void) { return (nib(5) * 10 + nib(4)) * 10000L + (nib(3) * 10 + nib(2)) * 100L + nib(1) * 10 + nib(0); }
static long clock_md(void) { return (nib(10) * 10 + nib(9)) * 100L + nib(8) * 10 + nib(7); }
static long clock_year(void) { return nib(12) * 10 + nib(11); }
static long leap_counter(void) { rtc_w(13, 9); long v = nib(11); rtc_w(13, 8); return v; }   /* block 1, timer on */

/* Stop the timer, write the leap counter (block 1) and the time (block 0), start the timer again at this instant. */
static void set_clock(int h, int mi, int s, int weekday, int month, int day, int year, int leap)
{
    rtc_w(13, 1); rtc_w(11, leap);
    rtc_w(13, 0);
    rtc_w(0, s % 10); rtc_w(1, s / 10); rtc_w(2, mi % 10); rtc_w(3, mi / 10); rtc_w(4, h % 10); rtc_w(5, h / 10);
    rtc_w(6, weekday); rtc_w(7, day % 10); rtc_w(8, day / 10); rtc_w(9, month % 10); rtc_w(10, month / 10);
    rtc_w(11, year % 10); rtc_w(12, year / 10);
    rtc_w(13, 8);
}

static void seconds(uint64_t s) { msx_advance(&m, s * MSX_CPU_CLOCK); }

/* ---- slot layout ---- */
static void layout_checks(void)
{
    setup(SEGMENTS);
    /* Page-0 to page-3 primary slot 0 after reset: the main ROM in 0000h-7FFFh, the logo page in 8000h-BFFFh (design 3.1);
     * slot 0 holds nothing in C000h-FFFFh, so those reads give FFh. */
    check_read("slot 0 main first byte 0000h", 0x0000, 0x11);
    check_read("slot 0 main 4000h", 0x4000, 0x13);
    check_read("slot 0 main last byte 7FFFh", 0x7FFF, 0x12);
    check_read("slot 0 logo page 8000h", 0x8000, 0x21);
    check_read("slot 0 logo page BFFFh", 0xBFFF, 0x22);
    check_read("slot 0 empty at C000h", 0xC000, 0xFF);
    check("slot of 8000h is 0", msx_slot_of(&m, 0x8000), 0x00);

    /* Select slot 3 in pages 0 and 3 (A8h = 11 00 00 11): slot 3 is expanded, so the slot reads as bit 7 | 3 = 83h, the
     * secondary register is still 0 (3-0), and the sub-ROM image (16 KiB at its own 0000h) shows at 0000h-3FFFh only. */
    msx_out(&m, 0xA8, 0xC3);
    check("A8h read-back", msx_in(&m, 0xA8), 0xC3);
    check_read("3-0 sub-ROM first byte 0000h", 0x0000, 0x31);
    check_read("3-0 sub-ROM last byte 3FFFh", 0x3FFF, 0x32);
    check_read("page 1 still slot 0 (main ROM)", 0x4000, 0x13);
    check_read("3-0 does not repeat at C000h", 0xC000, 0xFF);
    check("slot of 0000h is 3-0", msx_slot_of(&m, 0x0000), 0x83);

    /* FFFFh: the secondary register of the slot in page 3, read back inverted (MSX2 Technical Handbook, slot select).
     * A reset value of 0 reads FFh; 24h (pages 0..3 = 3-0, 3-1, 3-2, 3-0) reads DBh. */
    check_read("FFFFh at reset reads inverted 00h", 0xFFFF, 0xFF);
    msx_write(&m, 0xFFFF, 0x24);
    check_read("FFFFh reads inverted 24h", 0xFFFF, 0xDB);
    msx_out(&m, 0xA8, 0xFF);
    check("slot of 0000h with FFFFh=24h: 3-0", msx_slot_of(&m, 0x0000), 0x83);
    check("slot of 4000h: 3-1", msx_slot_of(&m, 0x4000), 0x87);
    check("slot of 8000h: 3-2 (mapper RAM)", msx_slot_of(&m, 0x8000), 0x8B);
    check("slot of C000h: 3-0", msx_slot_of(&m, 0xC000), 0x83);
    check_read("3-0 sub-ROM in page 0 after FFFFh", 0x0000, 0x31);
    check_read("3-1 is empty", 0x4000, 0xFF);

    /* The write to FFFFh goes to the register, not to the RAM behind it: with page 3 on 3-2 the RAM stays untouched. */
    msx_write(&m, 0xFFFF, 0xAA);
    check("FFFFh write does not reach RAM", ram[0x3FFF], 0);
    check_read("FFFFh reads inverted AAh", 0xFFFF, 0x55);

    /* With page 3 on a slot that is not expanded, FFFFh is ordinary memory and the register stays as it was. */
    setup(SEGMENTS);
    msx_out(&m, 0xA8, 0x00);
    msx_write(&m, 0xFFFF, 0x55);
    msx_out(&m, 0xA8, 0xC0);
    check_read("FFFFh write with page 3 not expanded: register unchanged", 0xFFFF, 0xFF);
}

/* ---- memory mapper ---- */
static void mapper_checks(void)
{
    setup(SEGMENTS);
    /* Reset: all four registers 0; with 16 segments the four high bits read 1: F0h (design 3.2). */
    check("mapper reset FCh", msx_in(&m, 0xFC), 0xF0);
    check("mapper reset FDh", msx_in(&m, 0xFD), 0xF0);
    check("mapper reset FEh", msx_in(&m, 0xFE), 0xF0);
    check("mapper reset FFh", msx_in(&m, 0xFF), 0xF0);

    msx_out(&m, 0xA8, 0xFF);
    msx_write(&m, 0xFFFF, 0xAA);                  /* every page on 3-2, the mapper RAM */
    /* FEh = 05h reads F5h; 13h is masked to 4 bits (16 segments): reads F3h. */
    msx_out(&m, 0xFE, 0x05);
    check("mapper FEh=05h reads", msx_in(&m, 0xFE), 0xF5);
    msx_write(&m, 0x8000, 0xA5); msx_write(&m, 0xBFFF, 0x5B); msx_write(&m, 0xA000, 0x6C);
    check("page 2 start is segment 5", ram[5 * SEG], 0xA5);
    check("page 2 end is segment 5 last byte", ram[5 * SEG + 0x3FFF], 0x5B);
    check("page 2 A000h is segment 5 + 2000h", ram[5 * SEG + 0x2000], 0x6C);
    msx_out(&m, 0xFE, 0x13);
    check("mapper FEh=13h reads (masked)", msx_in(&m, 0xFE), 0xF3);
    check_read("page 2 shows segment 3 (empty)", 0x8000, 0x00);
    msx_write(&m, 0x8000, 0x3A);
    check("write lands in segment 3", ram[3 * SEG], 0x3A);
    check_read("page 2 reads segment 3", 0x8000, 0x3A);
    msx_out(&m, 0xFE, 0x05);
    check_read("page 2 back to segment 5", 0x8000, 0xA5);

    /* One register per page: FCh page 0, FDh page 1, FEh page 2, FFh page 3. */
    msx_out(&m, 0xFC, 9); msx_out(&m, 0xFD, 10); msx_out(&m, 0xFE, 11); msx_out(&m, 0xFF, 12);
    msx_write(&m, 0x0000, 0x91); msx_write(&m, 0x4000, 0xA1); msx_write(&m, 0x8000, 0xB1); msx_write(&m, 0xC000, 0xC1);
    check("page 0 through FCh = segment 9", ram[9 * SEG], 0x91);
    check("page 1 through FDh = segment 10", ram[10 * SEG], 0xA1);
    check("page 2 through FEh = segment 11", ram[11 * SEG], 0xB1);
    check("page 3 through FFh = segment 12", ram[12 * SEG], 0xC1);
    check("mapper read-back of the four pages",
          (long)msx_in(&m, 0xFC) << 24 | msx_in(&m, 0xFD) << 16 | msx_in(&m, 0xFE) << 8 | msx_in(&m, 0xFF), 0xF9FAFBFCL);

    /* Reset puts all four registers back to 0 (and the slots to power-on). */
    msx_reset(&m);
    check("mapper-reset FCh", msx_in(&m, 0xFC), 0xF0);
    check("mapper-reset FDh", msx_in(&m, 0xFD), 0xF0);
    check("mapper-reset FEh", msx_in(&m, 0xFE), 0xF0);
    check("mapper-reset FFh", msx_in(&m, 0xFF), 0xF0);

    /* Four segments (64 KiB): two address bits, so the six high bits read 1: 06h keeps 2 and reads FEh. */
    setup(4);
    msx_out(&m, 0xFC, 0x06);
    check("4 segments: FCh=06h reads", msx_in(&m, 0xFC), 0xFE);
    msx_out(&m, 0xFD, 0xFF);
    check("4 segments: FDh=FFh reads", msx_in(&m, 0xFD), 0xFF);
}

/* ---- the MSX1 has no mapper and no clock ---- */
static void msx1_checks(void)
{
    msx_init(&m, MSX_LINES_NTSC);
    msx_out(&m, 0xFE, 0x05);
    msx_out(&m, 0xB4, 0x0D);
    msx_out(&m, 0xB5, 0x00);
    check("MSX1 FCh reads FFh", msx_in(&m, 0xFC), 0xFF);
    check("MSX1 FDh reads FFh", msx_in(&m, 0xFD), 0xFF);
    check("MSX1 FEh reads FFh after a write", msx_in(&m, 0xFE), 0xFF);
    check("MSX1 FFh reads FFh", msx_in(&m, 0xFF), 0xFF);
    check("MSX1 B4h reads FFh", msx_in(&m, 0xB4), 0xFF);
    check("MSX1 B5h reads FFh", msx_in(&m, 0xB5), 0xFF);
}

/* ---- RP5C01: reset values ---- */
static void rtc_reset_checks(void)
{
    setup(SEGMENTS);
    /* Design 3.3: Saturday 1 January 2000, 12:00:00, 24-hour mode; the chip's year counts from 1980, so 20; mode
     * register 13 = 8 (timer enabled, block 0) and reads high nibble F; B4h reads FFh. */
    check("rtc reset time", clock_hms(), 120000);
    check("rtc reset weekday (Saturday = 6)", nib(6), 6);
    check("rtc reset date", clock_md(), 101);
    check("rtc reset year", clock_year(), 20);
    check("rtc mode register reads F8h", rtc_raw(13), 0xF8);
    check("rtc B5h high nibble is F", rtc_raw(4) & 0xF0, 0xF0);
    check("rtc B4h reads FFh", msx_in(&m, 0xB4), 0xFF);
    check("rtc test register (14) reads 0Fh | F0h", rtc_raw(14), 0xFF);
    check("rtc reset register (15) reads 0Fh | F0h", rtc_raw(15), 0xFF);

    /* Block 1 (mode 9: timer on, block 1): register 10 is the 12/24-hour flag, 1 = 24 hours; register 11 the leap
     * counter, 0 = a leap year (2000 is one). The alarm registers 0 and 1 have no bits. */
    rtc_w(13, 9);
    check("rtc block 1: 24-hour flag", rtc_raw(10), 0xF1);
    check("rtc block 1: leap counter", rtc_raw(11), 0xF0);
    check("rtc block 1: alarm minutes digit has no bits", rtc_raw(0), 0xF0);

    /* The nibbles keep the bits of their digit (RP5C01 data sheet): tens of seconds 3 bits, tens of months 1 bit. */
    rtc_w(13, 8);
    rtc_w(1, 0xF);
    check("rtc seconds tens keep 3 bits", rtc_raw(1), 0xF7);
    rtc_w(10, 0xF);
    check("rtc month tens keep 1 bit", rtc_raw(10), 0xF1);

    /* Blocks 2 and 3 are battery RAM: all four bits kept, independent of each other. */
    rtc_w(13, 10);
    rtc_w(12, 0xB);
    check("rtc block 2 RAM keeps all bits", rtc_raw(12), 0xFB);
    rtc_w(13, 11);
    check("rtc block 3 is separate", rtc_raw(12), 0xF0);
}

/* ---- RP5C01 running on machine time ---- */
static void rtc_run_checks(void)
{
    /* 61 s of machine time from 12:00:00: 12:01:01 (design 6.1 rtc-run). */
    setup(SEGMENTS);
    seconds(61);
    check("rtc after 61 s", clock_hms(), 120101);
    check("rtc date after 61 s", clock_md(), 101);

    /* One second is exactly 3,579,545 cycles: one cycle short, no tick; the cycle itself ticks. */
    setup(SEGMENTS);
    msx_advance(&m, MSX_CPU_CLOCK - 1);
    check("rtc one cycle short of a second", clock_hms(), 120000);
    msx_advance(&m, 1);
    check("rtc a whole second", clock_hms(), 120001);

    /* Hour carry: 12:59:59 + 1 s = 13:00:00. */
    setup(SEGMENTS);
    set_clock(12, 59, 59, 6, 1, 1, 20, 0);
    seconds(1);
    check("rtc hour carry", clock_hms(), 130000);

    /* Day rollover, month end: 31 Jan 23:59:59 on weekday 6 + 1 s = 1 Feb 00:00:00, weekday wraps 6 to 0. */
    setup(SEGMENTS);
    set_clock(23, 59, 59, 6, 1, 31, 20, 0);
    seconds(1);
    check("rtc day rollover time", clock_hms(), 0);
    check("rtc month rollover date", clock_md(), 201);
    check("rtc weekday wraps 6 to 0", nib(6), 0);

    /* A 30-day month: 30 April + 1 day = 1 May. */
    setup(SEGMENTS);
    set_clock(23, 59, 59, 2, 4, 30, 20, 0);
    seconds(1);
    check("rtc 30 April rolls to 1 May", clock_md(), 501);
    check("rtc weekday 2 becomes 3", nib(6), 3);

    /* Leap counter 0 (a leap year): 28 February is followed by 29 February; counter 1: by 1 March. */
    setup(SEGMENTS);
    set_clock(23, 59, 59, 1, 2, 28, 20, 0);
    seconds(1);
    check("rtc leap year: 28 Feb to 29 Feb", clock_md(), 229);
    setup(SEGMENTS);
    set_clock(23, 59, 59, 1, 2, 28, 21, 1);
    seconds(1);
    check("rtc leap counter 1: 28 Feb to 1 Mar", clock_md(), 301);

    /* Year end: 31 December of year 20 (leap counter 0) to 1 January of year 21, leap counter 1. */
    setup(SEGMENTS);
    set_clock(23, 59, 59, 3, 12, 31, 20, 0);
    seconds(1);
    check("rtc year end date", clock_md(), 101);
    check("rtc year end year", clock_year(), 21);
    check("rtc leap counter steps to 1", leap_counter(), 1);
    setup(SEGMENTS);
    set_clock(23, 59, 59, 3, 12, 31, 99, 3);
    seconds(1);
    check("rtc year 99 wraps to 00", clock_year(), 0);
    check("rtc leap counter 3 wraps to 0", leap_counter(), 0);

    /* Timer disabled (mode register bit 3 clear): ten seconds pass and nothing counts; when it is enabled again it
     * starts from that instant, so one more second gives 12:00:01 and not 12:00:11. */
    setup(SEGMENTS);
    rtc_w(13, 0);
    seconds(10);
    check("rtc stopped: ten seconds not counted", clock_hms(), 120000);
    rtc_w(13, 8);
    seconds(1);
    check("rtc restarted: one second", clock_hms(), 120001);

    /* Reset register bit 1 clears the divider (the fraction of a second): 2.5 s is two ticks; after the reset 0.6 s
     * gives no tick (it would give a third without the reset), and 0.4 s more completes the second. [RP5C01 data sheet,
     * reset register: timer reset; from memory, not re-read against the sheet.] */
    setup(SEGMENTS);
    msx_advance(&m, 8948862);
    check("rtc 2.5 s: two ticks", clock_hms(), 120002);
    rtc_w(15, 2);
    msx_advance(&m, 2147727);
    check("rtc 0.6 s after the divider reset: no tick", clock_hms(), 120002);
    msx_advance(&m, 1431818);
    check("rtc 0.4 s more: one tick", clock_hms(), 120003);
}

int main(void)
{
    layout_checks();
    mapper_checks();
    msx1_checks();
    rtc_reset_checks();
    rtc_run_checks();
    printf("%d failure(s)\n", failures);
    return failures ? 1 : 0;
}
