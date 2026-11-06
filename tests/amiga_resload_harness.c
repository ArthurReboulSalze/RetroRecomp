/* ROM-free checks of native/amiga_whdload/rr_resload.c on a flat 16 MiB guest memory with authored files.
   Prints one line per failed check and exits with the number of failures (0: all passed). */
#include "rr_resload.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned char mem[1 << 24];
static int failures, flushes;
static char saved_name[64];
static uint32_t saved_offset, saved_size;
static unsigned char saved_bytes[64];
static int saved_whole;

#define CHECK(cond) do { if (!(cond)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); failures++; } } while (0)

static uint8_t rd(void *u, uint32_t a) { (void)u; return mem[a & 0xFFFFFF]; }
static void wr(void *u, uint32_t a, uint8_t v) { (void)u; mem[a & 0xFFFFFF] = v; }
static void put16(uint32_t a, uint16_t v) { mem[a] = (uint8_t)(v >> 8); mem[a + 1] = (uint8_t)v; }
static void put32(uint32_t a, uint32_t v) { put16(a, (uint16_t)(v >> 16)); put16(a + 2, (uint16_t)v); }
static uint16_t get16(uint32_t a) { return (uint16_t)(mem[a] << 8 | mem[a + 1]); }
static uint32_t get32(uint32_t a) { return (uint32_t)get16(a) << 16 | get16(a + 2); }
static void puts_at(uint32_t a, const char *s) { memcpy(mem + a, s, strlen(s) + 1); }

static const unsigned char file_main[] = "main program bytes";
static unsigned char disk1[4096];

/* An RNC1 file and its unpacked bytes, written by tests/test_amiga_resload.py with its own encoder. */
static unsigned char *packed_file, *expected_file;
static uint32_t packed_size, expected_size;

static int lookup(void *u, const char *name, const uint8_t **data, uint32_t *size) {
    (void)u;
    if (!strcmp(name, "main")) { *data = file_main; *size = sizeof file_main - 1; return 1; }
    if (!strcmp(name, "packed") && packed_file) { *data = packed_file; *size = packed_size; return 1; }
    if (!strcmp(name, "Disk.1")) { *data = disk1; *size = sizeof disk1; return 1; }
    return 0;
}

static int save(void *u, const char *name, uint32_t offset, const uint8_t *data, uint32_t size, int whole) {
    (void)u;
    snprintf(saved_name, sizeof saved_name, "%s", name);
    saved_offset = offset; saved_size = size; saved_whole = whole;
    memcpy(saved_bytes, data, size < sizeof saved_bytes ? size : sizeof saved_bytes);
    return 0;
}

static void on_flush(void *u) { (void)u; flushes++; }

static RrResload make(uint16_t version, uint16_t flags) {
    RrResloadHost host = {NULL, rd, wr, lookup, save, NULL, on_flush};
    RrResload r;
    rr_resload_init(&r, &host, 0x100000, version, flags);
    return r;
}

static void files_and_disks(void) {
    RrResload r = make(17, 0);
    uint32_t regs[16] = {0};
    puts_at(0x2000, "main");
    regs[8] = 0x2000; regs[9] = 0x3000;
    CHECK(rr_resload_call(&r, 0x08, regs) == RR_RESLOAD_RETURN);
    CHECK(regs[0] == sizeof file_main - 1 && regs[1] == 0 && !memcmp(mem + 0x3000, file_main, regs[0]));
    CHECK(flushes == 1);
    regs[8] = 0x2000;
    CHECK(rr_resload_call(&r, 0x24, regs) == RR_RESLOAD_RETURN && regs[0] == sizeof file_main - 1);
    regs[0] = 4; regs[1] = 5; regs[8] = 0x2000; regs[9] = 0x3100;          /* LoadFileOffset: 4 bytes from 5 */
    CHECK(rr_resload_call(&r, 0x4C, regs) == RR_RESLOAD_RETURN && !memcmp(mem + 0x3100, "prog", 4));
    puts_at(0x2100, "absent");
    regs[8] = 0x2100;
    CHECK(rr_resload_call(&r, 0x08, regs) == RR_RESLOAD_RETURN && regs[0] == 0 && regs[1] == RR_DOS_OBJECT_NOT_FOUND);
    for (unsigned k = 0; k < sizeof disk1; k++) disk1[k] = (unsigned char)(k * 7);
    regs[0] = 512; regs[1] = 16; regs[2] = 1; regs[8] = 0x4000;             /* DiskLoad */
    CHECK(rr_resload_call(&r, 0x28, regs) == RR_RESLOAD_RETURN && regs[0] == 0xFFFFFFFFu && mem[0x4000] == ((512 * 7) & 0xFF));
    regs[0] = 4090; regs[1] = 16; regs[2] = 1; regs[8] = 0x4000;
    CHECK(rr_resload_call(&r, 0x28, regs) == RR_RESLOAD_RETURN && regs[1] == RR_DOS_SEEK_ERROR);
    regs[0] = 0; regs[1] = 16; regs[2] = 2;
    CHECK(rr_resload_call(&r, 0x28, regs) == RR_RESLOAD_RETURN && regs[1] == RR_DOS_OBJECT_NOT_FOUND);
    RrResload strict = make(17, 0x2);                                         /* WHDLF_NoError: failures abort */
    regs[8] = 0x2100;
    CHECK(rr_resload_call(&strict, 0x08, regs) == RR_RESLOAD_ABORT && strstr(strict.message, "absent"));
    puts_at(0x2200, "highs");
    memcpy(mem + 0x5000, "SCORES", 6);
    regs[0] = 6; regs[1] = 10; regs[8] = 0x2200; regs[9] = 0x5000;          /* SaveFileOffset */
    CHECK(rr_resload_call(&r, 0x38, regs) == RR_RESLOAD_RETURN && regs[0] == 0xFFFFFFFFu);
    CHECK(!strcmp(saved_name, "highs") && saved_offset == 10 && saved_size == 6 && !saved_whole && !memcmp(saved_bytes, "SCORES", 6));
}

static void crc_and_control(void) {
    RrResload r = make(17, 0);
    uint32_t regs[16] = {0};
    memcpy(mem + 0x6000, "123456789", 9);
    regs[0] = 9; regs[8] = 0x6000;
    CHECK(rr_resload_call(&r, 0x30, regs) == RR_RESLOAD_RETURN && regs[0] == 0xBB3D);
    r.custom[0] = 3;
    put32(0x6100, 0x88000011u); put32(0x6104, 0);          /* VERSION_GET */
    put32(0x6108, 0x88000007u); put32(0x610C, 0);          /* CUSTOM1_GET */
    put32(0x6110, 1); put32(0x6114, 0);                    /* TAG_IGNORE */
    put32(0x6118, 0x88000001u); put32(0x611C, 0);          /* ECLOCKFREQ_GET */
    put32(0x6120, 0);
    regs[8] = 0x6100;
    CHECK(rr_resload_call(&r, 0x34, regs) == RR_RESLOAD_RETURN && regs[0] == 0xFFFFFFFFu);
    CHECK(get32(0x6104) == RR_RESLOAD_WHDLOAD_VERSION && get32(0x610C) == 3 && get32(0x611C) == 709379u);
    r.scratch = 0x6800; r.time_days = 8035; r.time_mins = 13 * 60 + 7; r.time_ticks = 50 * 9;   /* 2000-01-01 13:07:09 */
    put32(0x6300, 0x88000014u); put32(0x6304, 0); put32(0x6308, 0);     /* TIME_GET */
    regs[8] = 0x6300;
    CHECK(rr_resload_call(&r, 0x34, regs) == RR_RESLOAD_RETURN && get32(0x6304) == 0x6800);
    CHECK(get32(0x6800) == 8035 && mem[0x680C] == 0 && mem[0x680D] == 1 && mem[0x680E] == 1);
    CHECK(mem[0x680F] == 13 && mem[0x6810] == 7 && mem[0x6811] == 9);
    r.time_days = 365 + 31 + 28;                            /* 1979-03-01 */
    CHECK(rr_resload_call(&r, 0x34, regs) == RR_RESLOAD_RETURN && mem[0x680C] == 79 && mem[0x680D] == 3 && mem[0x680E] == 1);
    put32(0x6200, 0x88000003u); put32(0x6208, 0);         /* a private tag: FALSE and noted, as WHDLoad */
    regs[8] = 0x6200;
    CHECK(rr_resload_call(&r, 0x34, regs) == RR_RESLOAD_RETURN && regs[0] == 0 && r.unknown_tags == 1 && strstr(r.message, "0x88000003"));
}

static void refusals(void) {
    RrResload r = make(17, 0);
    uint32_t regs[16] = {0};
    memcpy(mem + 0x8000, "IMP!", 4);                        /* a format recognised but not unpacked yet */
    regs[8] = 0x8000; regs[9] = 0x9000;
    CHECK(rr_resload_call(&r, 0x18, regs) == RR_RESLOAD_REFUSED && strstr(r.message, "Imploder"));
    memcpy(mem + 0x8000, "DATA", 4);                        /* unpacked data: size 0, as WHDLoad */
    CHECK(rr_resload_call(&r, 0x18, regs) == RR_RESLOAD_RETURN && regs[0] == 0);
    CHECK(rr_resload_call(&r, 0x5C, regs) == RR_RESLOAD_REFUSED && strstr(r.message, "ProtectSMC"));
    CHECK(rr_resload_call(&r, 0x90, regs) == RR_RESLOAD_REFUSED);
    RrResload old = make(4, 0);                             /* Control needs ws_Version 5 */
    CHECK(rr_resload_call(&old, 0x34, regs) == RR_RESLOAD_REFUSED && strstr(old.message, "newer slave"));
    CHECK(r.calls[0x18 / 4] == 2 && r.calls[0x5C / 4] == 1);
    put32(0x7000 + 4, 0); put32(0x7000 + 8, 3); put32(0x7000 + 12, 4);   /* Abort(0, 3, 4) on the stack */
    regs[15] = 0x7000;
    CHECK(rr_resload_call(&r, 0x04, regs) == RR_RESLOAD_ABORT && r.abort_reason[1] == 3 && r.abort_reason[2] == 4);
}

/* A patch list at 0x10000 (labels are offsets from its start), applied to 0x20000. */
static void patches(void) {
    RrResload r = make(17, 0);
    uint32_t L = 0x10000, D = 0x20000, p = L;
    memset(mem + D, 0xAA, 0x200);
    put32(D + 0x60, 0x00000010);
    put32(D + 0x70, 0x0000FFFF);
#define W(v) (put16(p, (uint16_t)(v)), p += 2)
#define LONG(v) (put32(p, (uint32_t)(v)), p += 4)
#define CMD(c, off) (W(0x8000 | (c)), W(off))
    CMD(1, 0x00);                         /* PL_R */
    CMD(2, 0x02); W(0x100);               /* PL_P  -> L+0x100 */
    CMD(3, 0x08); W(0x104);               /* PL_PS -> L+0x104 */
    CMD(4, 0x0E); W(0x0006);              /* PL_S  bra +8 */
    CMD(5, 0x12);                         /* PL_I */
    CMD(6, 0x14); W(0x0055);              /* PL_B */
    CMD(7, 0x16); W(0x1234);              /* PL_W */
    W(8); LONG(0x18); LONG(0xCAFEBABE);    /* PL_L with a 32-bit address */
    CMD(9, 0x1C); LONG(0x40);             /* PL_A: write D+0x40 */
    CMD(10, 0x20); W(0x108);              /* PL_PA: write L+0x108 */
    CMD(11, 0x24); W(6);                  /* PL_NOP 6 bytes */
    CMD(12, 0x2A); W(3);                  /* PL_C 3 bytes */
    CMD(13, 0x2D);                        /* PL_CB */
    CMD(14, 0x2E);                        /* PL_CW */
    CMD(15, 0x30);                        /* PL_CL */
    CMD(16, 0x34); W(0x10C); W(4);        /* PL_PSS: jsr + 4 bytes of NOP */
    CMD(18, 0x60); W(0x05);               /* PL_AB */
    CMD(19, 0x62); W(0x0001);             /* PL_AW */
    CMD(20, 0x70); LONG(0x00000001);      /* PL_AL */
    CMD(22, 0x74); W(0x0F);               /* PL_ORB */
    CMD(45, 0x76); W(0x00F0);             /* PL_ANDW */
    CMD(21, 0x80); W(3); W(0x4142); W(0x4300);   /* PL_DATA "ABC" (padded) */
    CMD(25, 0x90); W(0x110);              /* PL_GA: store D+0x90 at L+0x110 */
    W(0x4000 | 29);                       /* PL_IFC1 (Custom1 is 0: false) */
    CMD(7, 0xA0); W(0x1111);
    W(0x4000 | 39);                       /* PL_ELSE */
    CMD(7, 0xA0); W(0x2222);
    W(0x4000 | 28);                       /* nested PL_IFBW (false) */
    CMD(7, 0xA2); W(0x3333);
    W(0x4000 | 40);                       /* PL_ENDIF */
    W(0x4000 | 40);                       /* PL_ENDIF */
    W(0x4000 | 47); W(0);                 /* PL_IFC1EQ 0 (true) */
    CMD(7, 0xA4); W(0x4444);
    W(0x4000 | 40);
    CMD(41, 0xA6); W(0x114);              /* PL_VB from L+0x114 */
    CMD(17, 0); W(0x180);                 /* PL_NEXT -> list at L+0x180 */
    put16(L + 0x114, 0x7700);
    p = L + 0x180;
    CMD(7, 0xA8); W(0x5555);              /* the next list: its labels count from L+0x180 */
    CMD(10, 0xAC); W(0x10);               /* PL_PA -> L+0x190 */
    W(0);                                 /* PL_END */
    CHECK(rr_resload_patch(&r, L, D) == RR_RESLOAD_RETURN);
    CHECK(get16(D) == 0x4E75);
    CHECK(get16(D + 2) == 0x4EF9 && get32(D + 4) == L + 0x100);
    CHECK(get16(D + 8) == 0x4EB9 && get32(D + 10) == L + 0x104);
    CHECK(get16(D + 0x0E) == 0x6000 && get16(D + 0x10) == 6);
    CHECK(get16(D + 0x12) == 0x4AFC && mem[D + 0x14] == 0x55 && get16(D + 0x16) == 0x1234 && get32(D + 0x18) == 0xCAFEBABE);
    CHECK(get32(D + 0x1C) == D + 0x40 && get32(D + 0x20) == L + 0x108);
    CHECK(get16(D + 0x24) == 0x4E71 && get16(D + 0x26) == 0x4E71 && get16(D + 0x28) == 0x4E71);
    CHECK(mem[D + 0x2A] == 0 && mem[D + 0x2C] == 0 && mem[D + 0x2D] == 0 && get16(D + 0x2E) == 0 && get32(D + 0x30) == 0);
    CHECK(get16(D + 0x34) == 0x4EB9 && get32(D + 0x36) == L + 0x10C && get16(D + 0x3A) == 0x4E71 && get16(D + 0x3C) == 0x4E71);
    CHECK(get16(D + 0x3E) == 0xAAAA);
    CHECK(mem[D + 0x60] == 0x05 && get16(D + 0x62) == 0x0011 && get32(D + 0x70) == 0x00010000);
    CHECK(mem[D + 0x74] == 0xAF && get16(D + 0x76) == 0x00A0);
    CHECK(!memcmp(mem + D + 0x80, "ABC", 3) && mem[D + 0x83] == 0xAA);
    CHECK(get32(L + 0x110) == D + 0x90);
    CHECK(get16(D + 0xA0) == 0x2222 && get16(D + 0xA2) == 0xAAAA && get16(D + 0xA4) == 0x4444);
    CHECK(mem[D + 0xA6] == 0x77);
    CHECK(get16(D + 0xA8) == 0x5555 && get32(D + 0xAC) == L + 0x190);
    /* an unbalanced list and a debugging command are refused */
    p = 0x11000; W(0x4000 | 28); W(0);
    CHECK(rr_resload_patch(&r, 0x11000, D) == RR_RESLOAD_REFUSED);
    p = 0x11100; CMD(26, 0); W(0);
    CHECK(rr_resload_patch(&r, 0x11100, D) == RR_RESLOAD_REFUSED && strstr(r.message, "PL_BKPT"));
}

/* Two segments as LoadSeg leaves them: [size][next BPTR][data]; offsets run across both. */
static void patch_segments(void) {
    RrResload r = make(17, 0);
    uint32_t s1 = 0x30000, s2 = 0x31000;
    put32(s1, 8 + 0x20); put32(s1 + 4, (s2 + 4) >> 2);
    put32(s2, 8 + 0x40); put32(s2 + 4, 0);
    uint32_t p = 0x12000;
    CMD(7, 0x04); W(0xBEEF);      /* in the first segment */
    CMD(7, 0x24); W(0xF00D);      /* 0x24 - 0x20 = 4 into the second */
    W(0);
    uint32_t regs[16] = {0};
    regs[8] = 0x12000; regs[9] = (s1 + 4) >> 2;
    CHECK(rr_resload_call(&r, 0x74, regs) == RR_RESLOAD_RETURN);
    CHECK(get16(s1 + 8 + 4) == 0xBEEF && get16(s2 + 8 + 4) == 0xF00D);
    p = 0x12100; CMD(7, 0x100); W(1); W(0);
    regs[8] = 0x12100;
    CHECK(rr_resload_call(&r, 0x74, regs) == RR_RESLOAD_REFUSED);
}

/* An executable in memory: a code hunk with a pointer to the data hunk, a data hunk pointing back, a BSS hunk. */
static uint32_t write_executable(uint32_t a) {
    uint32_t p = a;
    LONG(0x3F3); LONG(0); LONG(3); LONG(0); LONG(2);
    LONG(2); LONG(1 | 0x40000000u); LONG(2);           /* code 2 longs, data 1 long (chip), BSS 2 longs */
    LONG(0x3E9); LONG(2); LONG(0x4E714E71); LONG(0x00000000);
    LONG(0x3EC); LONG(1); LONG(1); LONG(4); LONG(0);    /* code+4 -> data hunk */
    LONG(0x3F2);
    LONG(0x3EA); LONG(1); LONG(0x00000004);
    LONG(0x3FC); W(1); W(0); W(0); W(0);                /* short relocation: data+0 -> code hunk (+4) */
    LONG(0x3F2);
    LONG(0x3EB); LONG(2); LONG(0x3F2);
    return p - a;
}

static void relocate(void) {
    RrResload r = make(17, 0);
    uint32_t a = 0x40000, regs[16] = {0};
    memset(mem + a, 0xEE, 0x400);
    write_executable(a);
    regs[8] = a; regs[9] = 0;
    CHECK(rr_resload_call(&r, 0x50, regs) == RR_RESLOAD_RETURN);
    /* code at a (8 bytes), data at a+8 (4), BSS at a+12 (8) */
    CHECK(regs[0] == 20);
    CHECK(get32(a) == 0x4E714E71 && get32(a + 4) == a + 8);
    CHECK(get32(a + 8) == a + 4);
    CHECK(get32(a + 12) == 0 && get32(a + 16) == 0);
    /* the data hunk is CHIP: with WHDLTAG_CHIPPTR it goes there, and the tag returns the length used */
    memset(mem + a, 0xEE, 0x400);
    write_executable(a);
    put32(0x50000, 0x88100000u); put32(0x50004, 0x60000); put32(0x50008, 0);
    regs[8] = a; regs[9] = 0x50000;
    CHECK(rr_resload_call(&r, 0x50, regs) == RR_RESLOAD_RETURN);
    CHECK(get32(a + 4) == 0x60000 && get32(0x60000) == a + 4 && get32(0x50004) == 4 && regs[0] == 16);
    /* LoadSeg layout, 8-byte alignment */
    memset(mem + a, 0xEE, 0x400);
    write_executable(a);
    put32(0x50100, 0x88100003u); put32(0x50104, 0xFFFFFFFFu);
    put32(0x50108, 0x88100002u); put32(0x5010C, 8); put32(0x50110, 0);
    regs[8] = a; regs[9] = 0x50100;
    CHECK(rr_resload_call(&r, 0x50, regs) == RR_RESLOAD_RETURN);
    /* segments: code [a: 16 bytes + 8 = 16], data [a+16: 4+8 -> 16], BSS [a+32: 8+8 = 16] */
    CHECK(get32(a) == 16 && get32(a + 4) == (a + 16 + 4) >> 2 && get32(a + 8) == 0x4E714E71 && get32(a + 12) == a + 24);
    CHECK(get32(a + 16) == 16 && get32(a + 20) == (a + 32 + 4) >> 2 && get32(a + 24) == a + 12);
    CHECK(get32(a + 36) == 0 && regs[0] == 48);
}

static unsigned char *read_all(const char *path, uint32_t *size) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    unsigned char *d = (unsigned char *)malloc((size_t)n + 1);
    *size = (uint32_t)fread(d, 1, (size_t)n, f);
    fclose(f);
    return d;
}

/* RNC1: LoadFileDecrunch from a file, Decrunch in memory, GetFileSizeDec, and a damaged copy refused. */
static void rnc1(void) {
    RrResload r = make(17, 0);
    uint32_t regs[16] = {0};
    puts_at(0x2300, "packed");
    regs[8] = 0x2300; regs[9] = 0x100000;
    CHECK(rr_resload_call(&r, 0x70, regs) == RR_RESLOAD_RETURN && regs[0] == expected_size);
    regs[8] = 0x2300; regs[9] = 0x100000;
    CHECK(rr_resload_call(&r, 0x1C, regs) == RR_RESLOAD_RETURN && regs[0] == expected_size);
    CHECK(!memcmp(mem + 0x100000, expected_file, expected_size));
    memcpy(mem + 0x200000, packed_file, packed_size);
    regs[8] = 0x200000; regs[9] = 0x300000;
    CHECK(rr_resload_call(&r, 0x18, regs) == RR_RESLOAD_RETURN && regs[0] == expected_size);
    CHECK(!memcmp(mem + 0x300000, expected_file, expected_size));
    mem[0x200000 + packed_size - 1] ^= 0x40;                  /* a damaged packed byte: its CRC no longer matches */
    CHECK(rr_resload_call(&r, 0x18, regs) == RR_RESLOAD_REFUSED && strstr(r.message, "CRC"));
}

int main(int argc, char **argv) {
    files_and_disks();
    crc_and_control();
    refusals();
    patches();
    patch_segments();
    relocate();
    if (argc > 2) {
        packed_file = read_all(argv[1], &packed_size);
        expected_file = read_all(argv[2], &expected_size);
        CHECK(packed_file && expected_file);
        if (packed_file && expected_file) rnc1();
    }
    printf("%s (%d failures)\n", failures ? "FAILED" : "OK", failures);
    return failures;
}
