/* The MSX2's board: the memory mapper (ports FCh-FFh) and the RP5C01 clock (ports B4h/B5h). MIT, Retro-Recomp.
 *
 * Written from the MSX2 Technical Handbook and the RP5C01 data sheet; openMSX (MSXMemoryMapperBase.cc, RP5C01.cc) was
 * read to settle what they leave open, nothing was copied from it.
 *
 * Mapper: one register per 16 KB page; a write keeps the bits that address a segment, a read gives the register with
 * the unused high bits as 1. The machine places the selected segments (msx_machine.c, rebuild_regions).
 *
 * Clock: it never reads the host's clock. After a reset it holds Saturday 1 January 2000, 12:00:00, 24-hour mode, and
 * while the timer is enabled (mode register bit 3) it advances with machine time (3,579,545 cycles a second): the same
 * in every run and on both CPUs. Blocks 2 and 3 (the battery RAM) start at 0 and are not kept between sessions. */
#include "msx_machine.h"

#include <string.h>

uint8_t msx_mapper_in(const MsxMachine *m, uint8_t port)
{
    return (uint8_t)(m->mapper.reg[port & 3] | (uint8_t)~(m->mapper.segments - 1));
}

void msx_mapper_out(MsxMachine *m, uint8_t port, uint8_t value)
{
    m->mapper.reg[port & 3] = (uint8_t)(value & (m->mapper.segments - 1));
}

/* The bits each nibble keeps, per block (the data sheet's register map). */
static const uint8_t rtc_masks[4][13] = {
    { 0xF, 0x7, 0xF, 0x7, 0xF, 0x3, 0x7, 0xF, 0x3, 0xF, 0x1, 0xF, 0xF },   /* time */
    { 0x0, 0x0, 0xF, 0x7, 0xF, 0x3, 0x7, 0xF, 0x3, 0x0, 0x1, 0x3, 0x0 },   /* alarm, 12/24, leap counter */
    { 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF },
    { 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF },
};

enum { T_SEC1, T_SEC10, T_MIN1, T_MIN10, T_HOUR1, T_HOUR10, T_WEEKDAY, T_DAY1, T_DAY10, T_MONTH1, T_MONTH10, T_YEAR1,
       T_YEAR10 };

void msx_rtc_reset(MsxRtc *r)
{
    memset(r, 0, sizeof *r);
    r->mode = 0x08;                            /* timer enabled, block 0 */
    uint8_t *t = r->nibble[0];
    t[T_HOUR1] = 2; t[T_HOUR10] = 1;           /* 12:00:00 */
    t[T_WEEKDAY] = 6;                          /* Saturday */
    t[T_DAY1] = 1; t[T_MONTH1] = 1;            /* 1 January */
    t[T_YEAR1] = 0; t[T_YEAR10] = 2;           /* 1980 + 20 = 2000 */
    r->nibble[1][10] = 1;                      /* 24-hour mode */
    r->nibble[1][11] = 0;                      /* leap counter: 2000 is a leap year */
}

static int two(const uint8_t *t, int low) { return t[low] + 10 * t[low + 1]; }
static void set_two(uint8_t *t, int low, int value) { t[low] = (uint8_t)(value % 10); t[low + 1] = (uint8_t)(value / 10); }

static int month_days(int month, int leap_counter)
{
    static const uint8_t days[12] = { 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 };
    return month == 2 && leap_counter == 0 ? 29 : days[(month + 11) % 12];
}

static void tick_second(MsxRtc *r)
{
    uint8_t *t = r->nibble[0];
    int s = two(t, T_SEC1) + 1;
    if (s < 60) { set_two(t, T_SEC1, s); return; }
    set_two(t, T_SEC1, 0);
    int mi = two(t, T_MIN1) + 1;
    if (mi < 60) { set_two(t, T_MIN1, mi); return; }
    set_two(t, T_MIN1, 0);
    int h = two(t, T_HOUR1) + 1;                  /* 24-hour mode (the reset value; 12-hour mode is not counted) */
    if (h < 24) { set_two(t, T_HOUR1, h); return; }
    set_two(t, T_HOUR1, 0);
    t[T_WEEKDAY] = (uint8_t)((t[T_WEEKDAY] + 1) % 7);
    int d = two(t, T_DAY1) + 1, mo = two(t, T_MONTH1);
    if (d <= month_days(mo, r->nibble[1][11] & 3)) { set_two(t, T_DAY1, d); return; }
    set_two(t, T_DAY1, 1);
    if (++mo <= 12) { set_two(t, T_MONTH1, mo); return; }
    set_two(t, T_MONTH1, 1);
    set_two(t, T_YEAR1, (two(t, T_YEAR1) + 1) % 100);
    r->nibble[1][11] = (uint8_t)((r->nibble[1][11] + 1) & 3);
}

/* Bring the clock to the machine's time. */
static void rtc_catch_up(MsxMachine *m)
{
    MsxRtc *r = &m->rtc;
    if (!(r->mode & 0x08)) {
        r->counted = m->cycles;                /* stopped: the seconds that pass are not counted */
        return;
    }
    while (m->cycles - r->counted >= MSX_CPU_CLOCK) {
        r->counted += MSX_CPU_CLOCK;
        tick_second(r);
    }
}

uint8_t msx_rtc_in(MsxMachine *m, uint8_t port)
{
    if (port == 0xB4)
        return 0xFF;
    MsxRtc *r = &m->rtc;
    rtc_catch_up(m);
    unsigned reg = r->latch & 0x0F;
    if (reg == 13)
        return (uint8_t)(0xF0 | r->mode);
    if (reg > 13)
        return 0xFF;                           /* test and reset registers are write-only */
    unsigned block = r->mode & 3;
    return (uint8_t)(0xF0 | (r->nibble[block][reg] & rtc_masks[block][reg]));
}

void msx_rtc_out(MsxMachine *m, uint8_t port, uint8_t value)
{
    MsxRtc *r = &m->rtc;
    if (port == 0xB4) {
        r->latch = value & 0x0F;
        return;
    }
    rtc_catch_up(m);
    unsigned reg = r->latch & 0x0F;
    value &= 0x0F;
    if (reg == 13) {
        r->mode = value;
    } else if (reg == 14) {
        r->test = value;                       /* the test bits speed up counting: not modelled */
    } else if (reg == 15) {
        if (value & 0x02)
            r->counted = m->cycles;            /* reset the fraction of the current second */
    } else {
        unsigned block = r->mode & 3;
        r->nibble[block][reg] = (uint8_t)(value & rtc_masks[block][reg]);
    }
}
