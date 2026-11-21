/* Checks of the copies of written disks (native/disk_copies.inc), on disks made here: MIT, Retro-Recomp. Built by
 * tools/disk_copies_selftest.py, never into a game. No ROM, no disk image of any game.
 *
 *   disk_copies_checks FOLDER     (an ASCII folder that exists; the checks write their files there)
 *
 * Prints one line per check and a last JSON line {"passed": N, "failed": M}. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <direct.h>
#define make_folder(path) _mkdir(path)
#define remove_folder(path) _rmdir(path)
#else
#include <sys/stat.h>
#include <unistd.h>
#define make_folder(path) mkdir(path, 0700)
#define remove_folder(path) rmdir(path)
#endif
#include "disk_copies.inc"

static int passed, failed;
static void expect(const char *name, int condition)
{
    printf("%s %s\n", condition ? "ok  " : "FAIL", name);
    if (condition) ++passed; else ++failed;
}

static char root[900];
static uint8_t disk_a[2048], disk_b[4096], embedded_a[2048], embedded_b[4096];

static void file_path(char *out, size_t size, const char *folder, const char *name) { snprintf(out, size, "%s/%s/%s", root, folder, name); }

static long read_file(const char *folder, const char *name, uint8_t *into, size_t room)
{
    char path[1100];
    file_path(path, sizeof path, folder, name);
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    long n = (long)fread(into, 1, room, f);
    fclose(f);
    return n;
}

static void write_file(const char *folder, const char *name, const uint8_t *data, size_t size)
{
    char path[1100];
    file_path(path, sizeof path, folder, name);
    FILE *f = fopen(path, "wb");
    if (f) { fwrite(data, 1, size, f); fclose(f); }
}

static int exists(const char *folder, const char *name)
{
    char path[1100];
    file_path(path, sizeof path, folder, name);
    FILE *f = fopen(path, "rb");
    if (f) fclose(f);
    return f != NULL;
}

static void fresh(RrDiskCopies *c, const char *folder)
{
    char path[1100];
    snprintf(path, sizeof path, "%s/%s", root, folder);
    make_folder(path);
    for (size_t i = 0; i < sizeof embedded_a; ++i) embedded_a[i] = (uint8_t)(i * 7);
    for (size_t i = 0; i < sizeof embedded_b; ++i) embedded_b[i] = (uint8_t)(i * 13 + 1);
    memcpy(disk_a, embedded_a, sizeof disk_a);
    memcpy(disk_b, embedded_b, sizeof disk_b);
    memset(c, 0, sizeof *c);
    rr_disk_copies_init(c, path);
    c->disk[0] = (RrDiskImage){ disk_a, sizeof disk_a, 0 };
    c->disk[1] = (RrDiskImage){ disk_b, sizeof disk_b, 0 };
    c->count = 2;
}

int main(int argc, char **argv)
{
    if (argc < 2 || strlen(argv[1]) >= sizeof root) { fprintf(stderr, "usage: disk_copies_checks FOLDER\n"); return 2; }
    strcpy(root, argv[1]);
    static uint8_t read_back[8192];
    RrDiskCopies c;

    /* The start: no copy, a copy of the right size, a copy of another size. */
    fresh(&c, "start");
    expect("no copy: the embedded disks stay", rr_disk_copies_load(&c) == 0 && !memcmp(disk_a, embedded_a, sizeof disk_a));
    uint8_t other[2048];
    memset(other, 0x3C, sizeof other);
    write_file("start", "disk-1.dsk", other, sizeof other);
    write_file("start", "disk-2.dsk", other, sizeof other);                   /* disk 2 is 4096 bytes: not its copy */
    expect("a copy of the disk's size replaces it in memory, one of another size does not",
           rr_disk_copies_load(&c) == 1 && !memcmp(disk_a, other, sizeof disk_a) && !memcmp(disk_b, embedded_b, sizeof disk_b));
    write_file("start", "disk-1.dsk", other, sizeof other - 1);
    memcpy(disk_a, embedded_a, sizeof disk_a);
    expect("a copy one byte short is not the disk's", rr_disk_copies_load(&c) == 0 && !memcmp(disk_a, embedded_a, sizeof disk_a));

    /* The timed write: nothing before the disks have been quiet long enough, then the marked disk only. */
    fresh(&c, "timed");
    disk_b[100] = 0xEE;
    rr_disk_copies_written(&c, 1);
    rr_disk_copies_frame(&c, 1, 1);
    for (int f = 1; f < RR_DISK_COPY_QUIET; ++f) rr_disk_copies_frame(&c, 0, 1);
    expect("not written before the disks are quiet", !exists("timed", "disk-2.dsk") && c.disk[1].dirty);
    rr_disk_copies_frame(&c, 0, 1);
    expect("written once they are quiet, the marked disk only",
           read_file("timed", "disk-2.dsk", read_back, sizeof read_back) == (long)sizeof disk_b
           && !memcmp(read_back, disk_b, sizeof disk_b) && !exists("timed", "disk-1.dsk") && !c.disk[1].dirty
           && !exists("timed", "disk-2.dsk.tmp"));
    disk_b[101] = 0xDD;
    rr_disk_copies_written(&c, 1);
    for (int f = 0; f < RR_DISK_COPY_QUIET + 5; ++f) rr_disk_copies_frame(&c, 0, 0);
    expect("a frame that may not write keeps the disk due", c.disk[1].dirty && read_file("timed", "disk-2.dsk", read_back,
           sizeof read_back) == (long)sizeof disk_b && read_back[101] != 0xDD);
    rr_disk_copies_frame(&c, 0, 1);
    expect("and the next frame that may writes it", !c.disk[1].dirty && read_file("timed", "disk-2.dsk", read_back,
           sizeof read_back) == (long)sizeof disk_b && read_back[101] == 0xDD);

    /* A write that fails leaves the old copy whole and the disk marked. */
    char blocked[1100];
    snprintf(blocked, sizeof blocked, "%s/timed/disk-2.dsk.tmp", root);
    make_folder(blocked);                                                     /* the staged file cannot be opened */
    disk_b[102] = 0xCC;
    rr_disk_copies_written(&c, 1);
    expect("a failed write leaves the disk marked", !rr_disk_copies_save(&c) && c.disk[1].dirty);
    expect("and the old copy whole", read_file("timed", "disk-2.dsk", read_back, sizeof read_back) == (long)sizeof disk_b
           && read_back[101] == 0xDD && read_back[102] != 0xCC);
    remove_folder(blocked);
    expect("tried again, it is written", rr_disk_copies_save(&c) && !c.disk[1].dirty
           && read_file("timed", "disk-2.dsk", read_back, sizeof read_back) == (long)sizeof disk_b && read_back[102] == 0xCC);

    /* The clean end of a match: the previous copy kept as .bak, then the match's disk. */
    fresh(&c, "commit");
    write_file("commit", "disk-1.dsk", other, sizeof other);
    disk_a[5] = 0x99;
    rr_disk_copies_written(&c, 0);
    disk_b[6] = 0x88;
    rr_disk_copies_written(&c, 1);                                            /* disk 2 has no copy yet: no .bak to keep */
    expect("the commit writes every marked disk", rr_disk_copies_commit(&c) && !rr_disk_copies_dirty_any(&c));
    expect("the previous copy kept as .bak", read_file("commit", "disk-1.dsk.bak", read_back, sizeof read_back) == (long)sizeof other
           && !memcmp(read_back, other, sizeof other));
    expect("the match's disks written", read_file("commit", "disk-1.dsk", read_back, sizeof read_back) == (long)sizeof disk_a
           && read_back[5] == 0x99 && read_file("commit", "disk-2.dsk", read_back, sizeof read_back) == (long)sizeof disk_b
           && read_back[6] == 0x88 && !exists("commit", "disk-2.dsk.bak") && !exists("commit", "disk-1.dsk.bak.tmp"));
    snprintf(blocked, sizeof blocked, "%s/commit/disk-1.dsk.bak.tmp", root);
    make_folder(blocked);                                                     /* the .bak cannot be staged */
    disk_a[7] = 0x77;
    rr_disk_copies_written(&c, 0);
    expect("no .bak: the copy is not rewritten and the commit says so", !rr_disk_copies_commit(&c) && !c.disk[0].dirty
           && read_file("commit", "disk-1.dsk", read_back, sizeof read_back) == (long)sizeof disk_a && read_back[7] != 0x77);
    remove_folder(blocked);

    /* A run without copies (headless) reads and writes nothing. */
    RrDiskCopies none;
    memset(&none, 0, sizeof none);
    rr_disk_copies_init(&none, NULL);
    none.disk[0] = (RrDiskImage){ disk_a, sizeof disk_a, 0 };
    none.count = 1;
    rr_disk_copies_written(&none, 0);
    expect("no copies folder: nothing read, nothing written", rr_disk_copies_load(&none) == 0 && rr_disk_copies_save(&none)
           && rr_disk_copies_commit(&none) && !none.disk[0].dirty);
    char long_name[1200];
    memset(long_name, 'x', sizeof long_name - 1);
    long_name[sizeof long_name - 1] = 0;
    expect("a folder name too long is refused", !rr_disk_copies_init(&none, long_name) && !rr_disk_copies_enabled(&none));

    printf("{\"passed\": %d, \"failed\": %d}\n", passed, failed);
    return 0;                                    /* the JSON line carries the verdict */
}
