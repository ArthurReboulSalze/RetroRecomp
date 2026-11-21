/* Headless Amstrad CPC reference run: the corrected reference Z80 interpreter (runtime_reference.c, prepared from the pinned
 * SuperZazu copy by retrorecomp.cpu.prepare_reference with the CPC's costs and 16-bit ports, never edited by hand) on the board of
 * cpc_machine.c. MIT, Retro-Recomp. The conversion's reference and a development check (tools/cpc_reference.py): never built into
 * a game.
 *
 * Timing, the same contract as the chain's step loop (native/z80_chain_glue.inc): the interpreter counts the CPC's whole
 * microseconds itself (its copy carries the CPC's cost table); an instruction's I/O happens at its start (the board is caught up
 * to the step's start before the step, so the I/O of the step sees the machine at that time); the board then advances by the
 * step's cycles; /INT is read once the board has caught up and accepted with the interpreter's own acceptance
 * (cpc_reference_accept), whose cycles the board then runs; an acceptance acknowledges the Gate Array. The service point (the
 * headless run's: the frame's sound, row and boot keys, the stop) comes after that, as the chain's comes after an instruction and
 * the interrupt it may accept.
 *
 * Usage: cpc_reference --system FILE (32 KiB: OS then BASIC) [--amsdos FILE] [--disk FILE] [--crtc 0|1|2] and the options of
 * cpc_headless.inc (--frames, --until-halt, --picture, --audio, --watch, --report, --rows). Its report adds the steps run and the
 * interrupts accepted. */
#include "cpc_machine.h"
#include "runtime_reference.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void cpc_reference_accept(z80 *const z);     /* the interpreter's interrupt acceptance (z80_chain_build.instrument_reference) */

static CpcMachine machine;
static z80 z;
static unsigned long long steps, accepted;

#define CPC_HEADLESS_REFERENCE 1                     /* the CPU view and the counts are this program's (below) */
#include "boot_keys.h"
#include "cpc_headless.inc"

static uint8_t system_rom[0x8000], amsdos_rom[0x4000];
static uint8_t disk_bytes[2u << 20];

static uint8_t bus_read(void *user, uint16_t address) { (void)user; return cpc_read(&machine, address); }
static void bus_write(void *user, uint16_t address, uint8_t value) { (void)user; cpc_write(&machine, address, value); }
static uint8_t bus_in(z80 *cpu, uint16_t port) { (void)cpu; return cpc_in(&machine, port); }
static void bus_out(z80 *cpu, uint16_t port, uint8_t value) { (void)cpu; cpc_out(&machine, port, value); }

static void headless_cpu(CpcCpuView *v)
{
    const uint8_t f = (uint8_t)(z.sf << 7 | z.zf << 6 | z.yf << 5 | z.hf << 4 | z.xf << 3 | z.pf << 2 | z.nf << 1 | z.cf);
    v->af = (uint16_t)(z.a << 8 | f); v->bc = (uint16_t)(z.b << 8 | z.c); v->de = (uint16_t)(z.d << 8 | z.e);
    v->hl = (uint16_t)(z.h << 8 | z.l); v->ix = z.ix; v->iy = z.iy; v->sp = z.sp; v->pc = z.pc;
    v->af2 = (uint16_t)(z.a_ << 8 | z.f_); v->bc2 = (uint16_t)(z.b_ << 8 | z.c_); v->de2 = (uint16_t)(z.d_ << 8 | z.e_);
    v->hl2 = (uint16_t)(z.h_ << 8 | z.l_); v->ir = (uint16_t)(z.i << 8 | z.r); v->wz = z.mem_ptr;
    v->iff1 = z.iff1; v->iff2 = z.iff2; v->im = z.interrupt_mode; v->halted = z.halted;
}

static void headless_counts(FILE *out)
{
    fprintf(out, "\"steps\": %llu, \"interrupts\": %llu, ", steps, accepted);
}

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

    z80_init(&z);
    z.read_byte = bus_read;
    z.write_byte = bus_write;
    z.port_in = bus_in;
    z.port_out = bus_out;
    z.userdata = &machine;
    for (;;) {                                               /* ends through headless_finish() */
        z.int_pending = 0;                                   /* the step accepts nothing: the level is read after it */
        unsigned long c0 = z.cyc;
        z80_step(&z);
        ++steps;
        cpc_advance(&machine, (uint64_t)(z.cyc - c0));
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
        headless_service();
    }
}
