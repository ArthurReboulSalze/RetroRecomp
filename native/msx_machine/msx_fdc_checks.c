/* Checks of the MSX2+ disk controller (native/msx_machine/msx_fdc.c) driven through its four registers as a disk ROM does:
 * commands and data at 7FFBh, the terminal count at 7FF9h, the status at 7FFAh. Above all, a write changes exactly the
 * sectors it was given: one sector asked and terminal count sent, one sector written and every other byte of the image
 * kept. Built by tools/msx_fdc_selftest.py; no ROM, no machine. MIT, Retro-Recomp. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "msx_fdc.h"

enum { DOR = 0, CR1 = 1, MSR = 2, DATA = 3, IMAGE = 2 * MSX_FDC_TRACKS * MSX_FDC_SPT * MSX_FDC_SECTOR };

static MsxFdc fdc;
static uint8_t image[IMAGE], before[IMAGE];
static unsigned passed, failed;

static void expect(const char *what, int ok)
{
    if (ok) ++passed; else { ++failed; fprintf(stderr, "FAIL: %s\n", what); }
}

static long offset(unsigned c, unsigned h, unsigned r) { return ((long)(c * 2 + h) * MSX_FDC_SPT + (r - 1)) * MSX_FDC_SECTOR; }

static void command(const uint8_t *bytes, unsigned count)
{
    for (unsigned n = 0; n < count; ++n) msx_fdc_write(&fdc, DATA, bytes[n]);
}

static void result(uint8_t *out, unsigned count)
{
    for (unsigned n = 0; n < count; ++n) out[n] = msx_fdc_read(&fdc, DATA);
}

static void seek(unsigned track)
{
    uint8_t c[3] = { 0x0F, 0x00, (uint8_t)track }, s = 0x08, r[2];
    command(c, 3);
    command(&s, 1);
    result(r, 2);
}

/* Bytes of the image that differ from `before`, outside [from, to). */
static long changed_outside(long from, long to)
{
    long count = 0;
    for (long n = 0; n < IMAGE; ++n)
        if ((n < from || n >= to) && image[n] != before[n]) ++count;
    return count;
}

static void fresh(int write_protected)
{
    for (long n = 0; n < IMAGE; ++n) image[n] = (uint8_t)(n * 31 + (n >> 9));
    memcpy(before, image, IMAGE);
    memset(&fdc, 0, sizeof fdc);
    msx_fdc_reset(&fdc);
    msx_fdc_insert(&fdc, 0, image, IMAGE, write_protected);
    msx_fdc_write(&fdc, DOR, 0x00);                                /* reset, then out of reset with the motor on */
    msx_fdc_write(&fdc, DOR, 0x14);
    for (int d = 0; d < 4; ++d) { uint8_t s = 0x08, r[2]; command(&s, 1); result(r, 2); }
}

static void write_command(unsigned c, unsigned h, unsigned r, unsigned eot)
{
    uint8_t w[9] = { 0x45, (uint8_t)(h << 2), (uint8_t)c, (uint8_t)h, (uint8_t)r, 0x02, (uint8_t)eot, 0x50, 0xFF };
    command(w, 9);
}

static void feed(unsigned count, uint8_t seed)
{
    for (unsigned n = 0; n < count; ++n) msx_fdc_write(&fdc, DATA, (uint8_t)(seed + n * 7));
}

int main(void)
{
    uint8_t st[7];

    /* One sector asked (R3 of track 1, side 0: sector 20), 512 bytes, terminal count: one sector written. */
    fresh(0);
    seek(1);
    write_command(1, 0, 3, 9);
    expect("a write enters its execution phase (MSR B0h)", msx_fdc_read(&fdc, MSR) == 0xB0);
    feed(512, 0x5A);
    msx_fdc_write(&fdc, CR1, 0x03);
    expect("terminal count ends the write in the result phase", msx_fdc_read(&fdc, MSR) == 0xD0);
    msx_fdc_write(&fdc, DATA, 0xEE);                               /* a stray byte in the result phase is not data */
    result(st, 7);
    expect("one sector: ST0 normal end, ST1 and ST2 clear", st[0] == 0x00 && st[1] == 0x00 && st[2] == 0x00);
    expect("one sector: the next ID is C1 H0 R4 N2", st[3] == 1 && st[4] == 0 && st[5] == 4 && st[6] == 2);
    long at = offset(1, 0, 3);
    int same = 1;
    for (unsigned n = 0; n < 512; ++n) same &= image[at + n] == (uint8_t)(0x5A + n * 7);
    expect("one sector: sector 20 holds the 512 bytes", same && at == 20L * 512);
    expect("one sector: every other byte of the image is unchanged", changed_outside(at, at + 512) == 0);
    expect("one sector: the disk is marked written", fdc.disk[0].written == 1);
    expect("one sector: back to the command phase", msx_fdc_read(&fdc, MSR) == 0x80);

    /* Data after the command is over is a new command, never more data. */
    memcpy(before, image, IMAGE);
    uint8_t sense = 0x08, r2[2];
    command(&sense, 1);
    result(r2, 1);
    expect("after the write, the data register takes commands: nothing written", changed_outside(0, 0) == 0);

    /* Two sectors up to EOT (R8, R9), terminal count after EOT: two sectors, next ID C2 R1. */
    fresh(0);
    seek(1);
    write_command(1, 0, 8, 9);
    feed(1024, 0x11);
    msx_fdc_write(&fdc, CR1, 0x03);
    result(st, 7);
    expect("two sectors to EOT: normal end, next ID C2 R1", st[0] == 0x00 && st[1] == 0x00 && st[3] == 2 && st[5] == 1);
    expect("two sectors to EOT: only R8 and R9 change", changed_outside(offset(1, 0, 8), offset(1, 0, 9) + 512) == 0);

    /* No terminal count: a byte after EOT ends the write "abnormal, end of cylinder" and is not written. */
    fresh(0);
    seek(1);
    write_command(1, 0, 9, 9);
    feed(512 + 1, 0x22);
    result(st, 7);
    expect("past EOT without terminal count: abnormal end, end of cylinder", st[0] == 0x40 && st[1] == 0x80);
    expect("past EOT without terminal count: only R9 changes", changed_outside(offset(1, 0, 9), offset(1, 0, 9) + 512) == 0);

    /* A write-protected disk: refused, nothing changes. */
    fresh(1);
    seek(1);
    write_command(1, 0, 3, 9);
    result(st, 7);
    expect("write protected: abnormal end, not writable", st[0] == 0x40 && st[1] == 0x02);
    expect("write protected: nothing changes", changed_outside(0, 0) == 0 && fdc.disk[0].written == 0);

    /* A sector that is not on the track under the head: no data, nothing changes. */
    fresh(0);
    seek(1);
    write_command(2, 0, 3, 9);
    result(st, 7);
    expect("the head on another track: abnormal end, no data", st[0] == 0x40 && st[1] == 0x04);
    expect("the head on another track: nothing changes", changed_outside(0, 0) == 0);

    /* A read with terminal count: the sector's bytes, the image unchanged. */
    fresh(0);
    seek(1);
    uint8_t rd[9] = { 0x46, 0x00, 1, 0, 3, 0x02, 9, 0x50, 0xFF };
    command(rd, 9);
    expect("a read enters its execution phase (MSR F0h)", msx_fdc_read(&fdc, MSR) == 0xF0);
    same = 1;
    for (unsigned n = 0; n < 512; ++n) same &= msx_fdc_read(&fdc, DATA) == before[at + n];
    msx_fdc_write(&fdc, CR1, 0x03);
    result(st, 7);
    expect("a read gives the sector's bytes", same);
    expect("a read ends normally with the next ID R4", st[0] == 0x00 && st[5] == 4);
    expect("a read changes nothing", changed_outside(0, 0) == 0 && fdc.disk[0].written == 0);

    printf("{\"passed\": %u, \"failed\": %u}\n", passed, failed);
    return failed ? 1 : 0;
}
