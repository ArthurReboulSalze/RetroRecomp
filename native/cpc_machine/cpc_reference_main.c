/* Headless Amstrad CPC reference run: the corrected reference Z80 interpreter (runtime_reference.c, prepared from the pinned
 * SuperZazu copy by retrorecomp.cpu.prepare_reference with the CPC's costs and 16-bit ports, never edited by hand) on the board of
 * cpc_machine.c. MIT, Retro-Recomp. A development check (tools/cpc_reference.py): never built into a game.
 *
 * Timing, the same contract as the chain's step loop (native/z80_chain_glue.inc): the interpreter counts the CPC's whole
 * microseconds itself (its copy carries the CPC's cost table); an instruction's I/O happens at its start (the board is caught up
 * to the step's start before the step, so the I/O of the step sees the machine at that time); the board then advances by the
 * step's cycles; /INT is read once the board has caught up and accepted with the interpreter's own acceptance
 * (cpc_reference_accept), whose cycles the board then runs; an acceptance acknowledges the Gate Array.
 *
 * Usage: cpc_reference --system FILE (32 KiB: OS then BASIC) [--amsdos FILE] [--disk FILE] [--frames N] [--until-halt]
 *                      [--picture FILE] [--audio FILE] [--watch ADDR]... [--crtc 0|1|2]
 * The state is printed as one JSON line; --picture writes the last frame (768 x 272 x 0x00RRGGBB, little endian), --audio the
 * sound (44,100 Hz, 16-bit stereo). With --until-halt the run stops after the first instruction that halts the CPU. */
#include "cpc_machine.h"
#include "runtime_reference.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void cpc_reference_accept(z80 *const z);     /* the interpreter's interrupt acceptance (z80_chain_build.instrument_reference) */

static CpcMachine machine;
static uint8_t system_rom[0x8000], amsdos_rom[0x4000];
static uint8_t disk_bytes[2u << 20];
static uint32_t picture[CPC_SCREEN_WIDTH * CPC_SCREEN_HEIGHT];

static uint8_t bus_read(void *user, uint16_t address) { (void)user; return cpc_read(&machine, address); }
static void bus_write(void *user, uint16_t address, uint8_t value) { (void)user; cpc_write(&machine, address, value); }
static uint8_t bus_in(z80 *z, uint16_t port) { (void)z; return cpc_in(&machine, port); }
static void bus_out(z80 *z, uint16_t port, uint8_t value) { (void)z; cpc_out(&machine, port, value); }

static uint32_t fnv_add(uint32_t h, const uint8_t *data, size_t size)
{
    for (size_t i = 0; i < size; ++i) { h ^= data[i]; h *= 16777619u; }
    return h;
}
static uint32_t fnv(const uint8_t *data, size_t size) { return fnv_add(2166136261u, data, size); }

static size_t load(const char *path, uint8_t *into, size_t room)
{
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "cannot read %s\n", path); exit(2); }
    size_t n = fread(into, 1, room, f);
    fclose(f);
    return n;
}

int main(int argc, char **argv)
{
    const char *system_file = NULL, *amsdos_file = NULL, *disk_file = NULL, *picture_file = NULL, *audio_file = NULL;
    unsigned long long frames = 50;
    int until_halt = 0, crtc = CPC_CRTC_TYPE1;
    unsigned watch[16], watches = 0;
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : "";
        if (!strcmp(a, "--system")) { system_file = v; ++i; }
        else if (!strcmp(a, "--amsdos")) { amsdos_file = v; ++i; }
        else if (!strcmp(a, "--disk")) { disk_file = v; ++i; }
        else if (!strcmp(a, "--frames")) { frames = strtoull(v, NULL, 10); ++i; }
        else if (!strcmp(a, "--until-halt")) until_halt = 1;
        else if (!strcmp(a, "--picture")) { picture_file = v; ++i; }
        else if (!strcmp(a, "--audio")) { audio_file = v; ++i; }
        else if (!strcmp(a, "--crtc")) { crtc = atoi(v); ++i; }
        else if (!strcmp(a, "--watch") && watches < 16) { watch[watches++] = (unsigned)strtoul(v, NULL, 16); ++i; }
        else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!system_file || load(system_file, system_rom, sizeof system_rom) != sizeof system_rom) {
        fprintf(stderr, "--system: a 32 KiB system ROM (OS then BASIC)\n");
        return 2;
    }
    machine.os = system_rom;
    machine.basic = system_rom + 0x4000;
    machine.amsdos = amsdos_file && load(amsdos_file, amsdos_rom, sizeof amsdos_rom) == sizeof amsdos_rom ? amsdos_rom : NULL;
    machine.picture = picture;
    cpc_reset(&machine, (uint8_t)crtc);
    if (disk_file) {
        size_t n = load(disk_file, disk_bytes, sizeof disk_bytes);
        if (cpc_insert_disk(&machine, 0, disk_bytes, (uint32_t)n, 0) != DSK_OK) { fprintf(stderr, "--disk: not a DSK image\n"); return 2; }
    }
    FILE *audio = audio_file ? fopen(audio_file, "wb") : NULL;

    z80 z;
    z80_init(&z);
    z.read_byte = bus_read;
    z.write_byte = bus_write;
    z.port_in = bus_in;
    z.port_out = bus_out;
    z.userdata = &machine;

    unsigned long long steps = 0, accepted = 0;
    static int16_t samples[CPC_AUDIO_BUFFER * 2];
    while (machine.frames < frames) {
        int was_halted = z.halted;
        z.int_pending = 0;                                   /* the step accepts nothing: the level is read after it */
        unsigned long c0 = z.cyc;
        z80_step(&z);
        ++steps;
        cpc_advance(&machine, (uint64_t)(z.cyc - c0));
        if (until_halt && z.halted && !was_halted)
            break;
        if (cpc_irq(&machine)) {
            z.int_pending = 1;
            z.int_data = 0xFF;
            unsigned long c1 = z.cyc;
            cpc_reference_accept(&z);                         /* nothing happens while IFF1 is clear or right after EI */
            if (!z.int_pending) {
                ++accepted;
                cpc_acknowledge(&machine);
                cpc_advance(&machine, (uint64_t)(z.cyc - c1));
            }
            z.int_pending = 0;
        }
        if (machine.frame_ready) {
            machine.frame_ready = 0;
            uint32_t n = cpc_audio_take(&machine, samples, CPC_AUDIO_BUFFER);
            if (audio) fwrite(samples, sizeof *samples * 2, n, audio);
        }
    }
    if (audio) fclose(audio);
    if (picture_file) {
        FILE *f = fopen(picture_file, "wb");
        if (f) { fwrite(picture, sizeof picture, 1, f); fclose(f); }
    }
    uint8_t f = (uint8_t)(z.sf << 7 | z.zf << 6 | z.yf << 5 | z.hf << 4 | z.xf << 3 | z.pf << 2 | z.nf << 1 | z.cf);
    printf("{\"frames\": %llu, \"cycles\": %llu, \"steps\": %llu, \"interrupts\": %llu, \"pc\": %u, \"sp\": %u, "
           "\"af\": %u, \"bc\": %u, \"de\": %u, \"hl\": %u, \"ix\": %u, \"iy\": %u, \"iff1\": %d, \"im\": %d, \"halted\": %d, "
           "\"ram_fnv\": %u, \"picture_fnv\": %u, \"mode\": %u, \"rom_config\": %u, \"ram_config\": %u, \"upper_rom\": %u, "
           "\"ay\": [", (unsigned long long)machine.frames, (unsigned long long)machine.cycles, steps, accepted, z.pc, z.sp,
           (unsigned)(z.a << 8 | f), (unsigned)(z.b << 8 | z.c), (unsigned)(z.d << 8 | z.e), (unsigned)(z.h << 8 | z.l), z.ix,
           z.iy, z.iff1, z.interrupt_mode, z.halted, fnv(machine.ram, sizeof machine.ram),
           fnv((const uint8_t *)picture, sizeof picture), machine.ga.mode, machine.ga.rom_config, machine.ga.ram_config,
           machine.upper_rom);
    for (int r = 0; r < 16; ++r) printf("%s%u", r ? ", " : "", machine.ay_reg[r]);
    printf("], \"fdc_commands\": %u, \"disk_written\": %d, \"watch\": {", machine.fdc.commands, machine.fdc.drive[0].written);
    for (unsigned w = 0; w < watches; ++w)
        printf("%s\"%04X\": %u", w ? ", " : "", watch[w], cpc_read(&machine, (uint16_t)watch[w]));
    printf("}}\n");
    return 0;
}
