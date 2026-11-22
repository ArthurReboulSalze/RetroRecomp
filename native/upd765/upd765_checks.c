/* Checks of the DSK / EXTENDED DSK reader (dsk_image.c) and the uPD765 (upd765.c), on images this file builds: a standard
 * 40-track AMSDOS data disk, and an extended one with an unformatted track, a weak sector in three copies, an 8 KiB sector
 * stored as 6 KiB, a deleted sector, a sector with a CRC error, an ID with no data field and odd IDs. The controller is
 * driven through its two registers as AMSDOS drives the CPC's (no terminal count), and once with the line wired. Built by
 * tools/upd765_selftest.py; no ROM, no disk image of a game. MIT, Retro-Recomp. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "dsk_image.h"
#include "upd765.h"

static unsigned passed, failed;

static void expect(const char *what, int ok)
{
    if (ok) ++passed; else { ++failed; fprintf(stderr, "FAIL: %s\n", what); }
}

/* ---- image builders ---- */

static uint8_t standard[256 + 40 * (256 + 9 * 512)];

static uint8_t pattern(unsigned track, unsigned sector, unsigned byte) { return (uint8_t)(track * 31 + sector * 7 + byte * 3 + 1); }

static void build_standard(void)
{
    memset(standard, 0, sizeof standard);
    memcpy(standard, "MV - CPCEMU Disk-File\r\nDisk-Info\r\n", 34);
    standard[0x30] = 40;
    standard[0x31] = 1;
    standard[0x32] = 0x00;
    standard[0x33] = 0x13;                                           /* 256 + 9 * 512 */
    for (unsigned t = 0; t < 40; ++t) {
        uint8_t *block = standard + 256 + t * 0x1300;
        memcpy(block, "Track-Info\r\n", 12);
        block[0x10] = (uint8_t)t;
        block[0x14] = 2;
        block[0x15] = 9;
        block[0x16] = 0x4E;
        block[0x17] = 0xE5;
        static const uint8_t order[9] = { 0xC1, 0xC6, 0xC2, 0xC7, 0xC3, 0xC8, 0xC4, 0xC9, 0xC5 };   /* AMSDOS interleave */
        for (unsigned s = 0; s < 9; ++s) {
            uint8_t *info = block + 0x18 + 8 * s;
            info[0] = (uint8_t)t; info[1] = 0; info[2] = order[s]; info[3] = 2;
            for (unsigned b = 0; b < 512; ++b)
                block[256 + s * 512 + b] = pattern(t, order[s], b);
        }
    }
}

/* Extended: 3 cylinders, 1 side. Track 0: sectors 1..4 of 512 bytes, sector 2 deleted, sector 3 a CRC error in its data,
 * sector 4 an ID with no data field. Track 1: not formatted. Track 2: a weak sector 0x41 (three copies of 512 bytes), an 8 KiB
 * sector 0x42 (N 6) stored as 6 KiB, and an ID with cylinder FFh. */
static uint8_t extended[256 + (256 + 4 * 512) + (256 + 3 * 512 + 0x1800 + 512)];
static uint32_t track2_at;

static void sector_info(uint8_t *info, uint8_t c, uint8_t h, uint8_t r, uint8_t n, uint8_t st1, uint8_t st2, uint16_t stored)
{
    info[0] = c; info[1] = h; info[2] = r; info[3] = n; info[4] = st1; info[5] = st2;
    info[6] = (uint8_t)stored; info[7] = (uint8_t)(stored >> 8);
}

static void build_extended(void)
{
    memset(extended, 0, sizeof extended);
    memcpy(extended, "EXTENDED CPC DSK File\r\nDisk-Info\r\n", 34);
    extended[0x30] = 3;
    extended[0x31] = 1;
    uint32_t t0 = 256 + 4 * 512, t2 = 256 + 3 * 512 + 0x1800 + 512;
    extended[0x34] = (uint8_t)(t0 >> 8);
    extended[0x35] = 0;
    extended[0x36] = (uint8_t)(t2 >> 8);
    uint8_t *block = extended + 256;
    memcpy(block, "Track-Info\r\n", 12);
    block[0x14] = 2; block[0x15] = 4;
    sector_info(block + 0x18, 0, 0, 1, 2, 0x00, 0x00, 512);
    sector_info(block + 0x20, 0, 0, 2, 2, 0x00, 0x40, 512);          /* deleted */
    sector_info(block + 0x28, 0, 0, 3, 2, 0x20, 0x20, 512);          /* CRC error in the data field */
    sector_info(block + 0x30, 0, 0, 4, 2, 0x01, 0x01, 512);          /* no data address mark */
    for (unsigned s = 0; s < 4; ++s)
        for (unsigned b = 0; b < 512; ++b)
            block[256 + s * 512 + b] = pattern(0, s + 1, b);
    track2_at = 256 + t0;
    block = extended + track2_at;
    memcpy(block, "Track-Info\r\n", 12);
    block[0x10] = 2; block[0x14] = 2; block[0x15] = 3;
    sector_info(block + 0x18, 2, 0, 0x41, 2, 0x20, 0x20, 3 * 512);    /* weak: three copies */
    sector_info(block + 0x20, 2, 0, 0x42, 6, 0x20, 0x20, 0x1800);    /* 8 KiB asked, 6 KiB stored */
    sector_info(block + 0x28, 0xFF, 0, 0x43, 2, 0x00, 0x00, 0);      /* stored length left out: 512 */
    for (unsigned k = 0; k < 3; ++k)
        for (unsigned b = 0; b < 512; ++b)
            block[256 + k * 512 + b] = (uint8_t)(b < 256 ? 0x55 : 0x10 * k);   /* the second half differs per copy */
    for (unsigned b = 0; b < 0x1800; ++b)
        block[256 + 3 * 512 + b] = (uint8_t)(b >> 4);
}

/* ---- driving the controller ---- */

static Upd765 fdc;
static DskImage disk_a, disk_b;

static void command(const uint8_t *bytes, unsigned count)
{
    for (unsigned n = 0; n < count; ++n) upd765_write_data(&fdc, bytes[n]);
}

static void result(uint8_t *out, unsigned count)
{
    for (unsigned n = 0; n < count; ++n) out[n] = upd765_read_data(&fdc);
}

/* AMSDOS's read loop: bytes while the execution bit is set and the direction is to the CPU, then the result. */
static unsigned read_loop(uint8_t *out, unsigned room)
{
    unsigned count = 0;
    while ((upd765_status(&fdc) & 0xE0) == 0xE0 && count < room + 64) {
        uint8_t v = upd765_read_data(&fdc);
        if (count < room) out[count] = v;
        ++count;
    }
    return count;
}

static void seek(uint8_t unit, uint8_t cylinder, uint8_t *st0, uint8_t *pcn)
{
    uint8_t c[3] = { 0x0F, unit, cylinder }, s = 0x08, r[2];
    command(c, 3);
    command(&s, 1);
    result(r, 2);
    if (st0) *st0 = r[0];
    if (pcn) *pcn = r[1];
}

static void read_command(uint8_t code, uint8_t unit, uint8_t c, uint8_t h, uint8_t r, uint8_t n, uint8_t eot)
{
    uint8_t rd[9] = { code, unit, c, h, r, n, eot, 0x2A, 0xFF };
    command(rd, 9);
}

static void reset_cpc(void)
{
    memset(&fdc, 0, sizeof fdc);
    fdc.unit_mask = 1;                                               /* the CPC decodes US0 only */
    upd765_reset(&fdc);
}

static void check_reader(void)
{
    build_standard();
    build_extended();
    expect("a standard image is read", dsk_parse(&disk_a, standard, sizeof standard) == DSK_OK);
    expect("its geometry: 40 cylinders, one side, 9 sectors a track", disk_a.cylinders == 40 && disk_a.sides == 1
        && dsk_track(&disk_a, 39, 0)->count == 9 && disk_a.sector_count == 360 && !disk_a.extended);
    const DskSector *s = &disk_a.sector[dsk_track(&disk_a, 5, 0)->first + 1];
    expect("a sector's ID and data offset", s->c == 5 && s->r == 0xC6 && s->n == 2 && s->stored == 512 && s->copies == 1
        && s->data == 256 + 5 * 0x1300 + 256 + 512);
    expect("no side 1 on a one-sided image", dsk_track(&disk_a, 0, 1) == NULL && dsk_track(&disk_a, 40, 0) == NULL);

    expect("an extended image is read", dsk_parse(&disk_b, extended, sizeof extended) == DSK_OK && disk_b.extended);
    expect("its unformatted track has no sector", dsk_track(&disk_b, 1, 0)->count == 0);
    const DskTrack *t2 = dsk_track(&disk_b, 2, 0);
    const DskSector *weak = &disk_b.sector[t2->first], *big = weak + 1, *nolen = weak + 2;
    expect("a weak sector in three copies of 512", weak->copies == 3 && weak->stored == 512);
    expect("an 8 KiB sector stored as 6 KiB, one copy", big->n == 6 && big->copies == 1 && big->stored == 0x1800);
    expect("a length of 0 on a track that gives lengths: no data", nolen->stored == 0 && nolen->c == 0xFF);
    static uint8_t old[sizeof extended];
    memcpy(old, extended, sizeof old);
    for (unsigned s = 0; s < 4; ++s) old[256 + 0x18 + 8 * s + 6] = old[256 + 0x18 + 8 * s + 7] = 0;
    DskImage early;
    expect("a track with every length left out (an early extended image): 128 << N each",
        dsk_parse(&early, old, sizeof old) == DSK_OK && early.sector[0].stored == 512 && early.sector[3].stored == 512
        && early.sector[3].data == 256 + 256 + 3 * 512);
    expect("the recorded status is kept", disk_b.sector[1].st2 == 0x40 && disk_b.sector[2].st1 == 0x20);

    static uint8_t bad[sizeof standard];
    memcpy(bad, standard, sizeof bad);
    memcpy(bad, "MV - XYZ", 8);
    DskImage refused;
    expect("a wrong signature is refused", dsk_parse(&refused, bad, sizeof bad) == DSK_ERR_SIGNATURE && !refused.bytes);
    expect("a short image is refused (track past the end)", dsk_parse(&refused, standard, sizeof standard - 1)
        == DSK_ERR_TRACK_BLOCK && refused.sector_count == 0);
    memcpy(bad, standard, sizeof bad);
    bad[256 + 0x15] = 30;
    expect("more sectors than a track block lists is refused", dsk_parse(&refused, bad, sizeof bad) == DSK_ERR_SECTOR_COUNT);
    memcpy(bad, standard, sizeof bad);
    bad[0x30] = 0;
    expect("no track is refused", dsk_parse(&refused, bad, sizeof bad) == DSK_ERR_GEOMETRY);
}

static void check_cpc_reads(void)
{
    static uint8_t buffer[0x3000];
    uint8_t st[7], st0, pcn;
    reset_cpc();
    dsk_parse(&disk_a, standard, sizeof standard);
    upd765_insert(&fdc, 0, &disk_a, 0);
    expect("idle: ready for a command (80h)", upd765_status(&fdc) == 0x80);

    seek(0, 3, &st0, &pcn);
    expect("SEEK then SENSE INTERRUPT: seek end on unit 0, cylinder 3", st0 == 0x20 && pcn == 3);
    uint8_t s = 0x08, invalid;
    command(&s, 1);
    result(&invalid, 1);
    expect("SENSE INTERRUPT with nothing pending answers invalid (80h)", invalid == 0x80 && upd765_status(&fdc) == 0x80);

    read_command(0x46, 0, 3, 0, 0xC4, 2, 0xC4);
    expect("a read enters its execution phase (F0h)", upd765_status(&fdc) == 0xF0);
    unsigned got = read_loop(buffer, sizeof buffer);
    int same = 1;
    for (unsigned b = 0; b < 512; ++b) same &= buffer[b] == pattern(3, 0xC4, b);
    expect("one sector read: exactly 512 bytes, then the result phase (D0h)", got == 512 && upd765_status(&fdc) == 0xD0);
    expect("the sector's bytes", same);
    result(st, 7);
    expect("no terminal count: abnormal, end of cylinder (40h 80h), next ID C+1 R1",
        st[0] == 0x40 && st[1] == 0x80 && st[2] == 0x00 && st[3] == 4 && st[5] == 1 && st[6] == 2);
    expect("then idle", upd765_status(&fdc) == 0x80);

    read_command(0x46, 0, 3, 0, 0xC1, 2, 0xC3);
    got = read_loop(buffer, sizeof buffer);
    same = 1;
    for (unsigned k = 0; k < 3; ++k)
        for (unsigned b = 0; b < 512; ++b) same &= buffer[k * 512 + b] == pattern(3, 0xC1 + k, b);
    result(st, 7);
    expect("C1 to C3 across the interleave: 1536 bytes in ID order", got == 1536 && same && st[1] == 0x80);

    read_command(0x46, 0, 3, 0, 0xCA, 2, 0xCA);
    result(st, 7);
    expect("a sector not on the track: no data (40h 04h), no execution phase", st[0] == 0x40 && st[1] == 0x04
        && upd765_status(&fdc) == 0x80);
    read_command(0x46, 0, 2, 0, 0xC1, 2, 0xC1);
    result(st, 7);
    expect("a cylinder the head is not on: no data and wrong cylinder", st[1] == 0x04 && (st[2] & 0x10));

    uint8_t id[2] = { 0x4A, 0x00 }, ids[9];
    for (unsigned k = 0; k < 9; ++k) {
        command(id, 2);
        result(st, 7);
        ids[k] = st[5];
    }
    int order = 1;
    for (unsigned k = 0; k < 9; ++k) {
        static const uint8_t expected[9] = { 0xC1, 0xC6, 0xC2, 0xC7, 0xC3, 0xC8, 0xC4, 0xC9, 0xC5 };
        /* the head stands after C3 (the last sector read) */
        order &= ids[k] == expected[(k + 5) % 9];
    }
    expect("READ ID gives the IDs as they pass under the head", order);

    seek(1, 0, &st0, NULL);
    expect("unit 1 seeks its own drive; with no disk, seek end and not ready", st0 == 0x69 && fdc.drive[0].pcn == 3
        && fdc.drive[1].pcn == 0);
    read_command(0x46, 1, 0, 0, 0xC1, 2, 0xC1);
    result(st, 7);
    expect("no disk in drive B: not ready (48h + unit)", st[0] == 0x49);
    seek(2, 0, &st0, NULL);
    expect("unit 2 is drive A on the CPC (US1 not decoded)", fdc.drive[0].pcn == 0 && (st0 & 3) == 2);

    uint8_t sense[2] = { 0x04, 0x00 }, st3;
    command(sense, 2);
    result(&st3, 1);
    expect("SENSE DRIVE STATUS: ready, track 0, one side, writable", st3 == 0x30);

    uint8_t scan[9] = { 0x11, 0, 0, 0, 0xC1, 2, 0xC1, 0x2A, 0xFF }, inv;
    unsigned before = fdc.unmodelled;
    command(scan, 9);
    result(&inv, 1);
    expect("SCAN EQUAL is not modelled: invalid, counted", inv == 0x80 && fdc.unmodelled == before + 1);
}

static void check_extended_reads(void)
{
    static uint8_t buffer[0x3000];
    uint8_t st[7];
    reset_cpc();
    build_extended();
    dsk_parse(&disk_b, extended, sizeof extended);
    upd765_insert(&fdc, 0, &disk_b, 0);
    seek(0, 0, NULL, NULL);

    read_command(0x46, 0, 0, 0, 1, 2, 2);
    unsigned got = read_loop(buffer, sizeof buffer);
    result(st, 7);
    expect("READ DATA meeting a deleted sector: reads it, control mark, ends there (00h, ST2 40h, the ID after EOT)",
        got == 1024 && st[0] == 0x00 && (st[2] & 0x40) && st[3] == 1 && st[5] == 1);
    read_command(0x66, 0, 0, 0, 1, 2, 2);
    got = read_loop(buffer, sizeof buffer);
    result(st, 7);
    expect("with SK the deleted sector is skipped", got == 512 && st[0] == 0x40 && st[1] == 0x80);
    read_command(0x4C, 0, 0, 0, 2, 2, 2);
    got = read_loop(buffer, sizeof buffer);
    result(st, 7);
    expect("READ DELETED DATA reads the deleted sector", got == 512 && buffer[0] == pattern(0, 2, 0) && (st[2] & 0x40) == 0);

    read_command(0x46, 0, 0, 0, 3, 2, 3);
    got = read_loop(buffer, sizeof buffer);
    result(st, 7);
    expect("a CRC error: the bytes, then abnormal with DE and DD", got == 512 && st[0] == 0x40 && st[1] == 0x20
        && st[2] == 0x20 && buffer[7] == pattern(0, 3, 7));
    read_command(0x46, 0, 0, 0, 4, 2, 4);
    got = read_loop(buffer, sizeof buffer);
    result(st, 7);
    expect("an ID with no data field: missing address mark, no byte", got == 0 && st[1] == 0x01 && st[2] == 0x01);

    seek(0, 1, NULL, NULL);
    read_command(0x46, 0, 1, 0, 1, 2, 1);
    result(st, 7);
    expect("an unformatted track: missing address mark", st[0] == 0x40 && st[1] == 0x01);
    uint8_t id[2] = { 0x4A, 0x00 };
    command(id, 2);
    result(st, 7);
    expect("READ ID on it: missing address mark", st[0] == 0x40 && st[1] == 0x01);

    seek(0, 2, NULL, NULL);
    uint8_t second[3];
    for (unsigned k = 0; k < 3; ++k) {
        read_command(0x46, 0, 2, 0, 0x41, 2, 0x41);
        got = read_loop(buffer, sizeof buffer);
        result(st, 7);
        second[k] = buffer[300];
        expect("a weak sector: 512 bytes, its stable half the same", got == 512 && buffer[0] == 0x55 && buffer[255] == 0x55);
    }
    expect("its weak half changes from read to read, copy after copy", second[0] == 0x00 && second[1] == 0x10
        && second[2] == 0x20);

    read_command(0x46, 0, 2, 0, 0x42, 6, 0x42);
    got = read_loop(buffer, sizeof buffer);
    result(st, 7);
    expect("an 8 KiB sector: 8192 bytes, the stored 6 KiB then again from its start", got == 8192
        && buffer[0x17FF] == 0x7F && buffer[0x1800] == 0x00 && buffer[0x1810] == 0x01 && st[1] == 0x20);

    read_command(0x46, 0, 2, 0, 0x43, 2, 0x43);
    result(st, 7);
    expect("an ID with cylinder FFh asked as cylinder 2: no data, wrong and bad cylinder", st[1] == 0x04
        && (st[2] & 0x12) == 0x12);

    seek(0, 0, NULL, NULL);
    uint8_t track[9] = { 0x42, 0x00, 0, 0, 1, 2, 3, 0x2A, 0xFF };
    command(track, 9);
    got = read_loop(buffer, sizeof buffer);
    result(st, 7);
    expect("READ TRACK: three sectors from the index, deleted or not, IDs compared", got == 1536
        && buffer[512] == pattern(0, 2, 0) && buffer[1024] == pattern(0, 3, 0) && st[1] == 0x80);
}

static void check_writes(void)
{
    static uint8_t copy[sizeof standard], buffer[0x1000];
    uint8_t st[7];
    build_standard();
    memcpy(copy, standard, sizeof copy);
    reset_cpc();
    dsk_parse(&disk_a, standard, sizeof standard);
    upd765_insert(&fdc, 0, &disk_a, 1);
    seek(0, 10, NULL, NULL);
    uint8_t wr[9] = { 0x45, 0x00, 10, 0, 0xC5, 2, 0xC5, 0x2A, 0xFF };
    command(wr, 9);
    result(st, 7);
    expect("a write-protected disk: not writable, nothing written", st[0] == 0x40 && st[1] == 0x02
        && !memcmp(copy, standard, sizeof copy) && !fdc.drive[0].written);

    upd765_insert(&fdc, 0, &disk_a, 0);
    command(wr, 9);
    expect("a write enters its execution phase (B0h)", upd765_status(&fdc) == 0xB0);
    for (unsigned b = 0; b < 512; ++b) upd765_write_data(&fdc, (uint8_t)(b ^ 0x5A));
    result(st, 7);
    uint32_t at = disk_a.sector[dsk_track(&disk_a, 10, 0)->first + 8].data;   /* C5 is the ninth in the interleave */
    int changed_elsewhere = 0, wrote = 1;
    for (uint32_t i = 0; i < sizeof copy; ++i) {
        if (i >= at && i < at + 512) wrote &= standard[i] == (uint8_t)((i - at) ^ 0x5A);
        else changed_elsewhere |= standard[i] != copy[i];
    }
    expect("a write ends at EOT like a read (40h 80h)", st[0] == 0x40 && st[1] == 0x80);
    expect("a write changes exactly its sector", wrote && !changed_elsewhere && fdc.drive[0].written);
    read_command(0x46, 0, 10, 0, 0xC5, 2, 0xC5);
    unsigned got = read_loop(buffer, sizeof buffer);
    result(st, 7);
    expect("and reads back", got == 512 && buffer[3] == (3 ^ 0x5A));

    build_extended();
    dsk_parse(&disk_b, extended, sizeof extended);
    upd765_insert(&fdc, 0, &disk_b, 0);
    seek(0, 0, NULL, NULL);
    uint8_t wd[9] = { 0x49, 0x00, 0, 0, 1, 2, 1, 0x2A, 0xFF };
    command(wd, 9);
    for (unsigned b = 0; b < 512; ++b) upd765_write_data(&fdc, 0);
    result(st, 7);
    expect("WRITE DELETED DATA records the mark in the image", (extended[256 + 0x18 + 5] & 0x40) && (disk_b.sector[0].st2 & 0x40));
    uint8_t wn[9] = { 0x45, 0x00, 0, 0, 3, 2, 3, 0x2A, 0xFF };
    command(wn, 9);
    for (unsigned b = 0; b < 512; ++b) upd765_write_data(&fdc, 1);
    result(st, 7);
    expect("writing a sector clears its recorded CRC error", extended[256 + 0x28 + 4] == 0 && extended[256 + 0x28 + 5] == 0);

    seek(0, 2, NULL, NULL);
    uint8_t wweak[9] = { 0x45, 0x00, 2, 0, 0x41, 2, 0x41, 0x2A, 0xFF };
    command(wweak, 9);
    for (unsigned b = 0; b < 512; ++b) upd765_write_data(&fdc, 0x77);
    result(st, 7);
    expect("a weak sector written: every copy holds the bytes", extended[track2_at + 256 + 300] == 0x77
        && extended[track2_at + 256 + 512 + 300] == 0x77 && extended[track2_at + 256 + 1024 + 300] == 0x77);

    /* FORMAT in place: the standard disk's cylinder 10, nine IDs of a data format again, filled with E5h. */
    build_standard();
    dsk_parse(&disk_a, standard, sizeof standard);
    upd765_insert(&fdc, 0, &disk_a, 0);
    seek(0, 10, NULL, NULL);
    uint8_t fmt[6] = { 0x4D, 0x00, 2, 9, 0x52, 0xE5 };
    command(fmt, 6);
    expect("FORMAT enters its execution phase", upd765_status(&fdc) == 0xB0);
    for (unsigned k = 0; k < 9; ++k) {
        upd765_write_data(&fdc, 10); upd765_write_data(&fdc, 0);
        upd765_write_data(&fdc, (uint8_t)(0x41 + k)); upd765_write_data(&fdc, 2);
    }
    result(st, 7);
    const DskSector *first = &disk_a.sector[dsk_track(&disk_a, 10, 0)->first];
    expect("FORMAT writes the new IDs and the filler", st[0] == 0x00 && first->r == 0x41 && first[8].r == 0x49
        && standard[first->data] == 0xE5 && standard[first->info + 2] == 0x41);
    uint8_t fmt8[6] = { 0x4D, 0x00, 2, 10, 0x52, 0xE5 };
    unsigned before = fdc.unmodelled;
    command(fmt8, 6);
    result(st, 7);
    expect("a format the image cannot hold in place: refused not writable, counted", st[1] == 0x02
        && fdc.unmodelled == before + 1);
}

static void check_wired_tc(void)
{
    static uint8_t buffer[0x1000];
    uint8_t st[7];
    build_standard();
    memset(&fdc, 0, sizeof fdc);
    fdc.unit_mask = 3;
    fdc.tc_wired = 1;
    dsk_parse(&disk_a, standard, sizeof standard);
    upd765_insert(&fdc, 0, &disk_a, 0);
    read_command(0x46, 0, 0, 0, 0xC1, 2, 0xC1);
    for (unsigned b = 0; b < 512; ++b) buffer[b] = upd765_read_data(&fdc);
    expect("wired: after the sector EOT the transfer waits", upd765_status(&fdc) == 0xF0);
    upd765_terminal_count(&fdc);
    result(st, 7);
    expect("wired: terminal count ends it normally with C+1 R1", st[0] == 0x00 && st[1] == 0x00 && st[3] == 1 && st[5] == 1);
    expect("the boot sector read is counted (lowest R of cylinder 0)", fdc.boot_reads == 1 && fdc.commands == 1);
    read_command(0x46, 0, 0, 0, 0xC1, 2, 0xC1);
    for (unsigned b = 0; b < 512; ++b) upd765_read_data(&fdc);
    upd765_read_data(&fdc);
    result(st, 7);
    expect("wired: a byte asked past EOT ends it end of cylinder", st[0] == 0x40 && st[1] == 0x80);
}

int main(void)
{
    check_reader();
    check_cpc_reads();
    check_extended_reads();
    check_writes();
    check_wired_tc();
    printf("{\"passed\": %u, \"failed\": %u}\n", passed, failed);
    return failed ? 1 : 0;
}
