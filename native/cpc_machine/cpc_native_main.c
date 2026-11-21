/* Headless Amstrad CPC native run: the translated Z80 bodies of the system ROM and AMSDOS, the shared banked step loop
 * (native/banked_runtime.inc rendered for the CPC by retrorecomp.z80_chain: a region map of four 16 KiB regions, the CPC's
 * costs in whole microseconds, the full 16-bit port, /INT read at the end of each instruction), the counted fallback on the
 * corrected reference interpreter, and the board of cpc_machine.c, through cpc_glue.inc. MIT, Retro-Recomp. A development
 * check (tools/cpc_native.py): it is compared field by field with cpc_reference_main.c, which takes the same options and
 * prints the same JSON; this one adds the native and fallback step counts (cpc_headless.inc, shared with the game's
 * --headless mode). Its machine comes from files: --system FILE (32 KiB: OS then BASIC) [--amsdos FILE] [--disk FILE]
 * [--crtc 0|1|2]. */
#define SMSRECOMP_BANKED_AOT 1
#include "cpc_glue.inc"
#include "cpc_headless.inc"

static uint8_t system_rom[0x8000], amsdos_rom[0x4000];
static uint8_t disk_bytes[2u << 20];

static size_t load(const char *path, uint8_t *into, size_t room)
{
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "cannot read %s\n", path); exit(2); }
    size_t n = fread(into, 1, room, f);
    fclose(f);
    return n;
}

static void cpc_main_service(void)
{
    headless_service();
}

int main(int argc, char **argv)
{
    const char *system_file = NULL, *amsdos_file = NULL, *disk_file = NULL;
    int crtc = CPC_CRTC_TYPE1;
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : "";
        if (headless_option(argc, argv, &i)) continue;
        if (!strcmp(a, "--system")) { system_file = v; ++i; }
        else if (!strcmp(a, "--amsdos")) { amsdos_file = v; ++i; }
        else if (!strcmp(a, "--disk")) { disk_file = v; ++i; }
        else if (!strcmp(a, "--crtc")) { crtc = atoi(v); ++i; }
        else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!system_file || load(system_file, system_rom, sizeof system_rom) != sizeof system_rom) {
        fprintf(stderr, "--system: a 32 KiB system ROM (OS then BASIC)\n");
        return 2;
    }
    machine.os = system_rom;
    machine.basic = system_rom + 0x4000;
    machine.amsdos = amsdos_file && load(amsdos_file, amsdos_rom, sizeof amsdos_rom) == sizeof amsdos_rom ? amsdos_rom : NULL;
    headless_start();
    cpc_reset(&machine, (uint8_t)crtc);
    if (disk_file) {
        size_t n = load(disk_file, disk_bytes, sizeof disk_bytes);
        if (cpc_insert_disk(&machine, 0, disk_bytes, (uint32_t)n, 0) != DSK_OK) { fprintf(stderr, "--disk: not a DSK image\n"); return 2; }
    }
    smsrecomp_banked_run();                      /* returns through headless_finish() */
    return 0;
}
