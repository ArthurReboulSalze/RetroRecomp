/* Headless ZX Spectrum reference run: the corrected reference Z80 interpreter (runtime_reference.c, prepared from the pinned copy
 * by retrorecomp.cpu.prepare_reference with 16-bit ports, never edited by hand) on the machine of zxs_machine.c. MIT, Retro-Recomp.
 * The conversion compares every native run with it; never built into a game.
 *
 * The /INT line is a level the Z80 samples at the end of each instruction: the step runs with nothing pending, the machine advances
 * by its cycles, then the level is read and an interrupt accepted (zxs_reference_accept, the interpreter's own acceptance exported
 * by the generated copy), as the native loop does. An instruction's I/O happens during its step, before the machine advances: at
 * its start time, as in the native glue.
 *
 * Usage: zxs_reference --rom FILE --image FILE and the route's options (zxs_headless.inc); "-" for --image reads the standard
 * input. It prints the report JSON. */
#include "zxs_machine.h"
#include "sms_runtime.h"
#include "runtime_reference.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

void zxs_reference_accept(z80 *const z);      /* the interpreter's interrupt acceptance */

static ZxsMachine machine;
static uint8_t rom[0x8000];
Z80State g_z80;                                 /* the image's registers, copied to the interpreter (banked_reference_state.inc) */
static z80 g_hz;
static uint64_t accepted;

static uint8_t bus_read(void *user, uint16_t address) { (void)user; return zxs_read(&machine, address); }
static void bus_write(void *user, uint16_t address, uint8_t value) { (void)user; zxs_write(&machine, address, value); }
static uint8_t bus_in(z80 *z, uint16_t port) { (void)z; return zxs_in(&machine, port); }
static void bus_out(z80 *z, uint16_t port, uint8_t value) { (void)z; zxs_out(&machine, port, value); }

#include "banked_reference_state.inc"
#include "zxs_cpu_start.inc"

static void headless_registers(uint16_t r[16])
{
    const z80 *z = &g_hz;
    const uint16_t regs[16] = {
        (uint16_t)(z->a << 8 | banked_pack_f(z)), (uint16_t)(z->b << 8 | z->c), (uint16_t)(z->d << 8 | z->e),
        (uint16_t)(z->h << 8 | z->l), z->ix, z->iy, z->sp, z->pc,
        (uint16_t)(z->a_ << 8 | z->f_), (uint16_t)(z->b_ << 8 | z->c_), (uint16_t)(z->d_ << 8 | z->e_),
        (uint16_t)(z->h_ << 8 | z->l_), (uint16_t)(z->i << 8 | z->r),
        (uint16_t)(z->interrupt_mode | (z->iff1 ? 4 : 0) | (z->iff2 ? 8 : 0) | (z->halted ? 16 : 0)), z->mem_ptr, 0 };
    memcpy(r, regs, sizeof regs);
}
static uint64_t headless_interrupts(void) { return accepted; }
#define HEADLESS_ENGINE "reference"
#include "zxs_headless.inc"

static long load(const char *path, uint8_t *into, long limit)
{
    int piped = !strcmp(path, "-");
#ifdef _WIN32
    if (piped) _setmode(_fileno(stdin), _O_BINARY);
#endif
    FILE *f = piped ? stdin : fopen(path, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", path); exit(2); }
    long n = (long)fread(into, 1, (size_t)limit, f);
    int more = fgetc(f) != EOF;
    if (!piped) fclose(f);
    if (more) { fprintf(stderr, "%s is larger than %ld bytes\n", path, limit); exit(2); }
    return n;
}

int main(int argc, char **argv)
{
    const char *rom_file = NULL, *image_file = NULL;
    static uint8_t image[ZXS_IMAGE_BYTES];
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!v) { fprintf(stderr, "missing value for %s\n", a); return 2; }
        ++i;
        int result;
        if (!strcmp(a, "--rom")) rom_file = v;
        else if (!strcmp(a, "--image")) image_file = v;
        else if ((result = headless_option(a, v)) != 0) { if (result < 0) { fprintf(stderr, "bad value for %s\n", a); return 2; } }
        else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!rom_file || !image_file) { fprintf(stderr, "--rom and --image are required\n"); return 2; }
    memset(rom, 0xFF, sizeof rom);
    long rom_size = load(rom_file, rom, (long)sizeof rom);
    long size = load(image_file, image, (long)sizeof image);
    ZxsCpuStart cpu;
    if (zxs_load_image(&machine, image, (size_t)size, rom, &cpu)) { fprintf(stderr, "not a machine image\n"); return 2; }
    if (rom_size != (machine.model == ZXS_128K ? 0x8000 : 0x4000)) { fprintf(stderr, "the ROM is not the model's\n"); return 2; }
    headless_start();
    zxs_cpu_from_image(&cpu);
    z80_init(&g_hz);
    g_hz.read_byte = bus_read; g_hz.write_byte = bus_write; g_hz.port_in = bus_in; g_hz.port_out = bus_out;
    state_to_hz();
    g_hz.pc = g_z80.pc;
    for (;;) {
        g_hz.int_pending = 0;                    /* the step accepts nothing: the level is read after it */
        unsigned long c0 = g_hz.cyc;
        z80_step(&g_hz);
        zxs_advance(&machine, (uint64_t)(g_hz.cyc - c0));
        if (zxs_irq(&machine)) {
            g_hz.int_pending = 1;
            g_hz.int_data = 0xFF;
            unsigned long c1 = g_hz.cyc;
            zxs_reference_accept(&g_hz);         /* nothing happens while IFF1 is clear or right after EI */
            if (!g_hz.int_pending) {
                ++accepted;
                zxs_advance(&machine, (uint64_t)(g_hz.cyc - c1));
            }
            g_hz.int_pending = 0;
        }
        if (headless_service())                  /* the service point: the instruction and its interrupt are complete */
            break;
    }
    headless_report();
    return 0;
}
