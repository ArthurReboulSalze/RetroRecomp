/* Checks of the cartridge save file of the Mega Drive (md_battery.c), the Super Nintendo (snes_battery.c) and the PC Engine
 * (pce_backup.c), on the machine's real entry points with a stand-in memory. One program per machine (-DCS_MD, -DCS_SNES or
 * -DCS_PCE), built by tools/cart_save_selftest.py; ROM-free. It checks the file against its own writer of the format and prints a
 * log of everything observable (results, notices, memory, every byte left on disk), so that two builds of the sources, before and
 * after a change, can be compared line by line. Windows hosts. Original RetroRecomp code: MIT. */
#define _CRT_SECURE_NO_WARNINGS
#include "platform_io.h"
#include <io.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "retro16_state_config.h"

#if defined(CS_MD)
#include "md_battery.h"
#define NAME "md"
enum { MEMBYTES = 8192, NWORDS = 3, HASHOFF = 32, SETS_ASIDE = 0, REPORTS_UNREADABLE = 0, MAXSIZE = 0x10000 };
static const uint8_t MAGIC[8] = {'R', 'R', 'M', 'D', 'R', 'A', '1', 0};
static const uint32_t WORDS[3] = {0x200000, 0x203fff, 2};
static GenesisBus bus;
static uint8_t *memory(void) { return bus.sram; }
static void machine_reset(void)
{
    memset(&bus, 0, sizeof bus);
    bus.sram_present = bus.sram_battery = 1;
    bus.sram_base = WORDS[0]; bus.sram_end = WORDS[1]; bus.sram_stride = (uint8_t)WORDS[2]; bus.sram_size = MEMBYTES;
}
static int m_open(const wchar_t *path) { return rr_md_battery_open(&bus, path); }
static int m_flush(uint64_t now, int force) { return rr_md_battery_flush(&bus, now, force != 0); }
static unsigned m_notice(void) { return 0; }
static int m_path(wchar_t *path, size_t n) { return rr_md_battery_path(path, n); }
#elif defined(CS_SNES)
#include "snes_battery.h"
#define NAME "snes"
enum { MEMBYTES = 8192, NWORDS = 3, HASHOFF = 32, SETS_ASIDE = 1, REPORTS_UNREADABLE = 0, MAXSIZE = 0x20000 };
static const uint8_t MAGIC[8] = {'R', 'R', 'S', 'N', 'R', 'A', '1', 0};
static const uint32_t WORDS[3] = {2, 0, 0};
static Cart cart;
static uint8_t ram[MEMBYTES];
static uint8_t *memory(void) { return ram; }
static void machine_reset(void)
{
    memset(&cart, 0, sizeof cart);
    cart.type = 2; cart.ram = ram; cart.ramSize = MEMBYTES;
}
static int m_open(const wchar_t *path) { return rr_snes_battery_open(&cart, true, path); }
static int m_flush(uint64_t now, int force) { return rr_snes_battery_flush(&cart, now, force != 0); }
static unsigned m_notice(void) { return rr_snes_battery_notice(); }
static int m_path(wchar_t *path, size_t n) { return rr_snes_battery_path(path, n); }
#elif defined(CS_PCE)
#include "pce_backup.h"
#include "pce_machine.h"
#define NAME "pce"
enum { MEMBYTES = PCE_BACKUP_BYTES, NWORDS = 0, HASHOFF = 16, SETS_ASIDE = 1, REPORTS_UNREADABLE = 1, MAXSIZE = PCE_BACKUP_BYTES };
static const uint8_t MAGIC[8] = {'R', 'R', 'P', 'C', 'E', 'B', 'R', '1'};
static const uint32_t WORDS[3] = {0, 0, 0};
static uint8_t pce_ram[PCE_BACKUP_BYTES];
static int pce_present;
const uint8_t *pce_machine_backup(void) { return pce_present ? pce_ram : NULL; }
void pce_machine_set_backup(const uint8_t data[PCE_BACKUP_BYTES]) { memcpy(pce_ram, data, PCE_BACKUP_BYTES); }
static uint8_t *memory(void) { return pce_ram; }
static void machine_reset(void) { pce_present = 1; memset(pce_ram, 0, sizeof pce_ram); }
static int m_open(const wchar_t *path) { rr_pce_backup_open(path); return -1; }   /* the PC Engine's open says nothing */
static int m_flush(uint64_t now, int force) { return rr_pce_backup_flush(now, force != 0); }
static unsigned m_notice(void) { return rr_pce_backup_notice(); }
static int m_path(wchar_t *path, size_t n) { return rr_pce_backup_path(path, n); }
#else
#error "define CS_MD, CS_SNES or CS_PCE"
#endif

static int failures;
#define CHECK(x) do { if (!(x)) { failures++; printf("CHECK FAILED line %d: %s\n", __LINE__, #x); } } while (0)

static void L(const char *format, ...)
{
    va_list args;
    va_start(args, format);
    vprintf(format, args);
    va_end(args);
    putchar('\n');
}

static uint64_t fnv(const uint8_t *p, size_t n)
{
    uint64_t h = 14695981039346656037ull;
    for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ull; }
    return h;
}
static void put32(uint8_t *p, uint32_t n) { for (unsigned i = 0; i < 4; i++) p[i] = (uint8_t)(n >> (i * 8)); }

static wchar_t root[1024];
static void join(wchar_t *out, const wchar_t *base, const char *tail)
{
    size_t n = wcslen(base);
    memcpy(out, base, n * sizeof *out);
    out[n++] = L'\\';
    while (*tail) out[n++] = (wchar_t)(unsigned char)*tail++;
    out[n] = 0;
}
static void make_dirs(const wchar_t *path)
{
    wchar_t parent[1024];
    wcscpy(parent, path);
    for (wchar_t *p = parent + 3; *p; p++)
        if (*p == L'\\') { *p = 0; CreateDirectoryW(parent, NULL); *p = L'\\'; }
}
static void write_file(const wchar_t *path, const uint8_t *data, size_t n)
{
    make_dirs(path);
    FILE *file = _wfopen(path, L"wb");
    CHECK(file != NULL);
    if (file) { CHECK(fwrite(data, 1, n, file) == n); fclose(file); }
}
static size_t read_file(const wchar_t *path, uint8_t *data, size_t capacity)
{
    FILE *file = _wfopen(path, L"rb");
    if (!file) return (size_t)-1;
    size_t n = fread(data, 1, capacity, file);
    fclose(file);
    return n;
}

/* A file the way the format says it is written (magic, version, size, identity words, hash, ROM, memory). */
static size_t make_file(uint8_t *out, const uint8_t *payload, uint32_t version, const uint32_t *words, const char *sha, int bad_hash)
{
    memset(out, 0, 112);
    memcpy(out, MAGIC, 8);
    put32(out + 8, version);
    put32(out + 12, MEMBYTES);
    for (unsigned i = 0; i < NWORDS; i++) put32(out + 16 + 4 * i, words[i]);
    uint64_t h = fnv(payload, MEMBYTES);
    if (bad_hash) h ^= 1;
    put32(out + HASHOFF, (uint32_t)h);
    put32(out + HASHOFF + 4, (uint32_t)(h >> 32));
    memcpy(out + 40, sha, 64);
    memcpy(out + 112, payload, MEMBYTES);
    return 112 + MEMBYTES;
}

static void fill(uint8_t *p, unsigned seed) { for (unsigned i = 0; i < MEMBYTES; i++) p[i] = (uint8_t)(i * 7 + seed); }

/* Every file below `dir`: relative name, size, hash of the bytes, read-only attribute; the header of what is small enough. */
static int compare_names(const void *a, const void *b) { return wcscmp(*(wchar_t *const *)a, *(wchar_t *const *)b); }
static void dump(const wchar_t *dir, const wchar_t *relative, const char *tag)
{
    wchar_t pattern[1024], *names[512];
    size_t count = 0;
    swprintf(pattern, 1024, L"%ls\\*", dir);
    WIN32_FIND_DATAW found;
    HANDLE find = FindFirstFileW(pattern, &found);
    if (find != INVALID_HANDLE_VALUE) {
        do {
            if (!wcscmp(found.cFileName, L".") || !wcscmp(found.cFileName, L"..") || count == 512) continue;
            names[count++] = _wcsdup(found.cFileName);
        } while (FindNextFileW(find, &found));
        FindClose(find);
    }
    qsort(names, count, sizeof *names, compare_names);
    for (size_t i = 0; i < count; i++) {
        wchar_t full[1024], rel[1024];
        swprintf(full, 1024, L"%ls\\%ls", dir, names[i]);
        swprintf(rel, 1024, L"%ls%ls%ls", relative, relative[0] ? L"/" : L"", names[i]);
        DWORD attributes = GetFileAttributesW(full);
        char name[1024];
        rr_to_utf8(rel, name, sizeof name);
        if (attributes & FILE_ATTRIBUTE_DIRECTORY) {
            L("%s dir %s", tag, name);
            dump(full, rel, tag);
        } else {
            static uint8_t data[1 << 20];
            size_t n = read_file(full, data, sizeof data);
            L("%s file %s size=%zu fnv=%016llx%s", tag, name, n, (unsigned long long)fnv(data, n == (size_t)-1 ? 0 : n),
              (attributes & FILE_ATTRIBUTE_READONLY) ? " readonly" : "");
            if (n != (size_t)-1 && n >= 112 && n < 4096) {
                char hex[112 * 2 + 1];
                for (unsigned k = 0; k < 112; k++) sprintf(hex + k * 2, "%02x", data[k]);
                L("%s head %s %s", tag, name, hex);
            }
        }
        free(names[i]);
    }
}
static void unlock_all(const wchar_t *dir)
{
    wchar_t pattern[1024];
    swprintf(pattern, 1024, L"%ls\\*", dir);
    WIN32_FIND_DATAW found;
    HANDLE find = FindFirstFileW(pattern, &found);
    if (find == INVALID_HANDLE_VALUE) return;
    do {
        wchar_t full[1024];
        if (!wcscmp(found.cFileName, L".") || !wcscmp(found.cFileName, L"..")) continue;
        swprintf(full, 1024, L"%ls\\%ls", dir, found.cFileName);
        if (found.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) unlock_all(full);
        else SetFileAttributesW(full, FILE_ATTRIBUTE_NORMAL);
    } while (FindNextFileW(find, &found));
    FindClose(find);
}

static int equals(const uint8_t *a, const uint8_t *b, size_t n) { return !memcmp(a, b, n); }

/* The result and the notice are read in two steps: the order in which a call's arguments are evaluated is not defined. */
static int Open(const char *label, const wchar_t *path)
{
    int result = m_open(path);
    unsigned notice = m_notice();
    L("%s -> %d notice=%u", label, result, notice);
    return result;
}
static int Flush(const char *label, uint64_t now, int force)
{
    int result = m_flush(now, force);
    L("%s -> %d", label, result);
    return result;
}

static void state(const char *step, int result, const wchar_t *file)
{
    static uint8_t data[1 << 16];
    size_t n = read_file(file, data, sizeof data);
    if (n == (size_t)-1) L("  %s -> %d file=none notice=%u", step, result, m_notice());
    else L("  %s -> %d file=%zu:%016llx notice=%u", step, result, n, (unsigned long long)fnv(data, n), m_notice());
}

/* A fresh machine whose memory holds the pattern `seed`. */
static void fresh(unsigned seed) { machine_reset(); fill(memory(), seed); }

static void scenario_fresh_and_reload(void)
{
    L("== fresh save, then a reload");
    wchar_t dir[1024], file[1024], expected_path[1024];
    join(dir, root, "s1");
    swprintf(file, 1024, L"%ls\\a\\b\\save.rrsram", dir);
    fresh(1);
    uint8_t first[MEMBYTES], written[112 + MEMBYTES], oracle[112 + MEMBYTES];
    memcpy(first, memory(), MEMBYTES);
    Open("open", file);
    state("flush(0,force) unchanged", m_flush(0, 1), file);
    memory()[0] ^= 1; memory()[MEMBYTES - 1] = 0x7b;
    state("flush(500)", m_flush(500, 0), file);
    state("flush(1000)", m_flush(1000, 0), file);
    state("flush(2000)", m_flush(2000, 0), file);
    state("flush(2500) quiet for 2000", m_flush(2500, 0), file);
    CHECK(read_file(file, written, sizeof written) == 112 + MEMBYTES);
    make_file(oracle, memory(), 1, WORDS, RR16_STATE_ROM, 0);
    CHECK(equals(written, oracle, 112 + MEMBYTES));
    memory()[3] = 9;
    state("flush(2600) too soon", m_flush(2600, 0), file);
    state("flush(3100) sees the change", m_flush(3100, 0), file);
    state("flush(5099)", m_flush(5099, 0), file);
    state("flush(5600) quiet", m_flush(5600, 0), file);
    memory()[4] = 77;
    state("flush(5700,force)", m_flush(5700, 1), file);
    make_file(oracle, memory(), 1, WORDS, RR16_STATE_ROM, 0);
    CHECK(read_file(file, written, sizeof written) == 112 + MEMBYTES && equals(written, oracle, 112 + MEMBYTES));
    state("flush(5800,force) unchanged", m_flush(5800, 1), file);
    uint8_t saved[MEMBYTES];
    memcpy(saved, memory(), MEMBYTES);
    dump(dir, L"", "s1");
    /* a new run: a blank machine takes the file */
    fresh(9);
    Open("reopen", file);
    CHECK(equals(memory(), saved, MEMBYTES) && m_notice() == 0);
    L("  memory after reopen %016llx (saved %016llx, first %016llx)", (unsigned long long)fnv(memory(), MEMBYTES),
      (unsigned long long)fnv(saved, MEMBYTES), (unsigned long long)fnv(first, MEMBYTES));
    state("flush(0,force) after reopen", m_flush(0, 1), file);
    /* the same file under the path the game derives */
    wchar_t derived[2048];
    int derived_ok = m_path(derived, 2048);
    L("path %d ends with %ls", derived_ok, derived_ok ? wcsstr(derived, L"datas") : L"-");
    (void)expected_path;
}

/* One kind of file in the place of a good one. */
static void variant(const char *name, int kind)
{
    wchar_t dir[1024], file[1024], aside[1024];
    char folder[64];
    snprintf(folder, sizeof folder, "s3_%s", name);
    join(dir, root, folder);
    swprintf(file, 1024, L"%ls\\save.rrsram", dir);
    static uint8_t stored[MEMBYTES], image[112 + MEMBYTES + 8];
    fill(stored, 5);
    size_t n = make_file(image, stored, 1, WORDS, RR16_STATE_ROM, 0);
    uint32_t words[3] = {WORDS[0], WORDS[1], WORDS[2]};
    int valid = 0;
    switch (kind) {
    case 0: valid = 1; break;                                                                  /* a good file */
    case 1: n = 0; break;                                                                      /* empty */
    case 2: n = 50; break;                                                                     /* a short header */
    case 3: n = 112 + MEMBYTES / 2; break;                                                         /* a short payload */
    case 4: n = 112 + MEMBYTES - 1; break;                                                         /* one byte short */
    case 5: image[n++] = 0; break;                                                             /* one byte too long */
    case 6: image[0] ^= 0x20; break;                                                           /* another magic */
    case 7: put32(image + 8, 2); break;                                                        /* another version */
    case 8: put32(image + 12, MEMBYTES / 2); break;                                                /* another size */
    case 9: image[112 + 10] ^= 1; break;                                                       /* a changed byte, the hash as it was */
    case 10: image[40] ^= 1; break;                                                            /* another ROM */
    case 11: if (NWORDS) put32(image + 16, words[0] + 1); else valid = -1; break;              /* another first identity word */
    case 12: if (NWORDS) put32(image + 20, words[1] + 1); else valid = -1; break;              /* another second one */
    case 13: if (NWORDS) put32(image + 24, words[2] + 1); else valid = -1; break;              /* another third one */
    case 14: put32(image + HASHOFF + 4, 0); break;                                             /* the hash's high word wrong */
    case 15: n = make_file(image, stored, 1, WORDS, RR16_STATE_ROM, 1); break;                 /* a wrong hash */
    case 16: image[104] = 9; image[111] = 9; valid = 1; break;                                 /* bytes no field covers */
    case 17: memset(stored, 0, MEMBYTES); n = make_file(image, stored, 1, WORDS, RR16_STATE_ROM, 0); valid = 1; break;   /* all zero */
    case 18: image[8] = 0; break;                                                              /* version 0 */
    default: break;
    }
    if (kind == 16) { if (NWORDS) image[28] ^= 0x55; else { image[24] ^= 0x55; image[28] = 3; } }
    if (valid < 0) { L("== file %s: not applicable", name); return; }
    write_file(file, image, n);
    fresh(1);
    uint8_t blank[MEMBYTES];
    memcpy(blank, memory(), MEMBYTES);
    L("== file %s (%zu bytes)", name, n);
    int opened = m_open(file);
    L("open %d notice=%u memory=%s", opened, m_notice(), equals(memory(), blank, MEMBYTES) ? "blank" : equals(memory(), stored, MEMBYTES) ? "restored" : "other");
    if (valid) { CHECK(m_notice() == 0 && equals(memory(), stored, MEMBYTES)); CHECK(opened != 0); }
    else {
        CHECK(equals(memory(), blank, MEMBYTES));
        CHECK(m_notice() == (SETS_ASIDE ? 1 : 0));
    }
    dump(dir, L"", name);
    memory()[2] ^= 0xff;
    Flush("flush(10000,force)", 10000, 1);
    dump(dir, L"", name);
    swprintf(aside, 1024, L"%ls.unusable-1", file);
    CHECK((!valid && SETS_ASIDE) == (GetFileAttributesW(aside) != INVALID_FILE_ATTRIBUTES));
}

static void scenario_variants(void)
{
    static const char *names[] = {"ok", "empty", "short_header", "short_payload", "one_byte_short", "one_byte_long", "magic", "version",
                                  "size", "payload_changed", "rom", "word0", "word1", "word2", "hash_high", "hash_wrong",
                                  "uncovered_bytes", "all_zero", "version0"};
    for (int kind = 0; kind < (int)(sizeof names / sizeof *names); kind++) variant(names[kind], kind);
}

static void scenario_unreadable(void)
{
    L("== a folder where the file should be");
    wchar_t dir[1024], file[1024];
    join(dir, root, "s4");
    swprintf(file, 1024, L"%ls\\save.rrsram", dir);
    make_dirs(file);
    CreateDirectoryW(file, NULL);
    fresh(1);
    Open("open", file);
    CHECK(m_notice() == (REPORTS_UNREADABLE ? 2 : 0));
    memory()[0] ^= 1;
    Flush("flush(9000,force)", 9000, 1);
    dump(dir, L"", "s4");
}

static void scenario_blocked_folder(void)
{
    L("== a file where the folder should be");
    wchar_t dir[1024], blocker[1024], file[1024];
    join(dir, root, "s5");
    swprintf(blocker, 1024, L"%ls\\blocker", dir);
    swprintf(file, 1024, L"%ls\\blocker\\save.rrsram", dir);
    write_file(blocker, (const uint8_t *)"x", 1);
    fresh(1);
    Open("open", file);
    memory()[0] ^= 1;
    Flush("flush(100,force)", 100, 1);
    Flush("flush(5000) within the ten seconds", 5000, 0);
    Flush("flush(10099)", 10099, 0);
    Flush("flush(10100)", 10100, 0);
    Flush("flush(12700,force)", 12700, 1);
    dump(dir, L"", "s5");
    /* the folder is made when it can be */
    wchar_t other[1024];
    swprintf(other, 1024, L"%ls\\later\\x\\save.rrsram", dir);
    fresh(1);
    L("open %d", m_open(other));
    memory()[1] ^= 1;
    Flush("flush(100,force)", 100, 1);
    dump(dir, L"", "s5b");
}

static void scenario_read_only(void)
{
    L("== read-only files");
    static uint8_t stored[MEMBYTES], image[112 + MEMBYTES];
    wchar_t dir[1024], file[1024], damaged[1024];
    join(dir, root, "s6");
    swprintf(file, 1024, L"%ls\\good\\save.rrsram", dir);
    fill(stored, 5);
    size_t n = make_file(image, stored, 1, WORDS, RR16_STATE_ROM, 0);
    write_file(file, image, n);
    _wchmod(file, _S_IREAD);
    fresh(1);
    Open("open", file);
    L("restored=%d", equals(memory(), stored, MEMBYTES));
    memory()[5] ^= 1;
    Flush("flush(100,force)", 100, 1);
    Flush("flush(200,force)", 200, 1);
    dump(dir, L"", "s6");
    swprintf(damaged, 1024, L"%ls\\bad\\save.rrsram", dir);
    image[10] ^= 1;
    write_file(damaged, image, n);
    _wchmod(damaged, _S_IREAD);
    fresh(1);
    Open("open damaged", damaged);
    memory()[5] ^= 1;
    Flush("flush(100,force)", 100, 1);
    dump(dir, L"", "s6b");
    unlock_all(dir);
}

static void scenario_asides(void)
{
    L("== names set aside");
    static uint8_t stored[MEMBYTES], image[112 + MEMBYTES];
    wchar_t dir[1024], file[1024], one[1024];
    join(dir, root, "s7");
    swprintf(file, 1024, L"%ls\\two\\save.rrsram", dir);
    fill(stored, 5);
    size_t n = make_file(image, stored, 1, WORDS, RR16_STATE_ROM, 0);
    image[10] ^= 1;
    write_file(file, image, n);
    for (unsigned k = 1; k <= 2; k++) { swprintf(one, 1024, L"%ls.unusable-%u", file, k); write_file(one, (const uint8_t *)"old", 3); }
    fresh(1);
    Open("open", file);
    dump(dir, L"", "s7");
    /* all ninety-nine taken */
    swprintf(file, 1024, L"%ls\\full\\save.rrsram", dir);
    write_file(file, image, n);
    for (unsigned k = 1; k <= 99; k++) { swprintf(one, 1024, L"%ls.unusable-%u", file, k); write_file(one, (const uint8_t *)"old", 3); }
    fresh(1);
    Open("open", file);
    CHECK(m_notice() == (SETS_ASIDE ? 2 : 0));
    memory()[0] ^= 1;
    Flush("flush(100,force)", 100, 1);
    Flush("flush(20000,force)", 20000, 1);
    dump(dir, L"", "s7b");
    /* the hundredth is never made */
    swprintf(one, 1024, L"%ls.unusable-100", file);
    CHECK(GetFileAttributesW(one) == INVALID_FILE_ATTRIBUTES);
}

static void scenario_off_and_guards(void)
{
    L("== off by design, refused, and guards");
    wchar_t dir[1024], file[1024];
    join(dir, root, "s8");
    swprintf(file, 1024, L"%ls\\x\\save.rrsram", dir);
    fresh(1);
    Open("open NULL", NULL);
    memory()[0] ^= 1;
    Flush("flush(9000,force)", 9000, 1);
    Open("open empty path", L"");
    Flush("flush(9100,force)", 9100, 1);
    static wchar_t long_path[40000];
    wcscpy(long_path, file);
    wcsncat(long_path, L"\\", 1);
    for (size_t i = wcslen(long_path); i < 32100; i++) long_path[i] = L'a';
    long_path[32100] = 0;
    Open("open path of 32100 characters", long_path);
    Flush("flush(9200,force)", 9200, 1);
#if defined(CS_MD)
    L("open without sram"); bus.sram_present = 0; Open(" ", file);
    fresh(1); bus.sram_battery = 0; Open("open without battery", file);
    fresh(1); bus.sram_size = 0; Open("open of size 0", file);
    fresh(1); bus.sram_size = MAXSIZE + 1; Open("open past the capacity", file);
    Flush("flush", 9300, 1);
    fresh(1); Open("open", file);
    bus.sram_present = 0; Flush("flush without sram", 9400, 1);
    bus.sram_present = 1; bus.sram_battery = 0; Flush("flush without battery", 9400, 1);
    bus.sram_battery = 1; bus.sram_size = 0; Flush("flush of size 0", 9400, 1);
    bus.sram_size = MAXSIZE + 1; Flush("flush past the capacity", 9400, 1);
    bus.sram_size = MEMBYTES; Flush("flush back", 9500, 1);
    /* a size the file does not have */
    fresh(1); bus.sram_size = 4096; Open("open at 4096", file);
    bus.sram_size = 0x4000; Flush("flush(10000) at 0x4000", 10000, 1);
    /* the full capacity */
    fresh(1); bus.sram_size = MAXSIZE; Open("open at the capacity", file);
    bus.sram[MAXSIZE - 1] = 3; Flush("flush", 20000, 1);
#elif defined(CS_SNES)
    L("open without bus %d", rr_snes_battery_open(NULL, true, file));
    L("flush no bus guard skipped");
    fresh(1); L("open battery off -> %d", rr_snes_battery_open(&cart, false, file));
    Flush("flush", 9300, 1);
    fresh(1); cart.ram = NULL; Open("open without ram", file);
    fresh(1); cart.ramSize = 0; Open("open of size 0", file);
    fresh(1); cart.ramSize = MAXSIZE + 1; Open("open past the capacity", file);
    Flush("flush", 9400, 1);
    fresh(1); Open("open", file);
    cart.type = 3; Flush("flush with another mapping", 9500, 1);
    cart.type = 2; cart.ram = NULL; Flush("flush without ram", 9500, 1);
    cart.ram = ram; cart.ramSize = 0; Flush("flush of size 0", 9500, 1);
    cart.ramSize = MAXSIZE + 1; Flush("flush past the capacity", 9500, 1);
    cart.ramSize = MEMBYTES; Flush("flush back", 9600, 1);
    static uint8_t big[MAXSIZE];
    fresh(1); cart.ram = big; cart.ramSize = MAXSIZE; Open("open at the capacity", file);
    big[MAXSIZE - 1] = 3; Flush("flush", 20000, 1);
#else
    fresh(1); Open("open", file);
    pce_present = 0; Flush("flush while the machine is not there", 9400, 1);
    pce_present = 1; Flush("flush back", 9500, 1);
#endif
    /* open again over an open save: the first is forgotten */
    fresh(1);
    m_open(file);
    L("reopen NULL %d", m_open(NULL));
    memory()[0] ^= 1;
    Flush("flush(30000,force) after close", 30000, 1);
    dump(dir, L"", "s8");
}

int main(int argc, char **argv)
{
    if (argc != 2 || !rr_from_utf8(argv[1], root, 1024)) { fprintf(stderr, "usage: cart_save_checks <empty folder>\n"); return 2; }
    L("machine %s", NAME);
    scenario_fresh_and_reload();
    scenario_variants();
    scenario_unreadable();
    scenario_blocked_folder();
    scenario_read_only();
    scenario_asides();
    scenario_off_and_guards();
    L("failures=%d", failures);
    return failures ? 1 : 0;
}
