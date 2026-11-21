/* Headless SG-1000 reference run: the corrected reference Z80 interpreter (runtime_reference.c, prepared from the pinned SuperZazu
 * copy by retrorecomp.cpu.prepare_reference with the NMI corrections, never edited by hand) on the SG-1000 machine of
 * sg1000_machine.c. MIT, Retro-Recomp. A development check and the conversion's oracle: never built into a game.
 *
 * The SG-1000 inserts no wait state. /INT is a level the Z80 samples at the end of each instruction: the step runs with nothing
 * pending, the machine advances by its cycles, then the level is read and an interrupt accepted (sg1000_reference_accept, the
 * interpreter's own acceptance, exported by the same generated copy). The Pause button is /NMI, an edge: taken first, at the same
 * boundary (the corrected interpreter accepts it even right after EI).
 *
 * Usage: sg1000_reference --cart FILE [--pal] [--frames N] [--watch ADDR]... [--vram FILE] [--frame FILE] [--rows FILE] [--audio FILE]
 *                         [--script FILE | --event FRAME:pad:PORT:HEX | --event FRAME:pause]... [--report FILE] */
#include "sg1000_machine.h"
#include "runtime_reference.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void sg1000_reference_accept(z80 *const z);      /* the interpreter's interrupt acceptance (both /INT and /NMI) */

static SgMachine machine;
static uint8_t cart[0xC000];

static uint8_t bus_read(void *user, uint16_t address) { return sg_read((SgMachine *)user, address); }
static void bus_write(void *user, uint16_t address, uint8_t value) { sg_write((SgMachine *)user, address, value); }
static uint8_t bus_in(z80 *z, uint8_t port) { return sg_in((SgMachine *)z->userdata, port); }
static void bus_out(z80 *z, uint8_t port, uint8_t value) { sg_out((SgMachine *)z->userdata, port, value); }

static long load(const char *path, uint8_t *into, long limit)
{
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", path); exit(2); }
    long n = (long)fread(into, 1, (size_t)limit, f);
    int more = fgetc(f) != EOF;
    fclose(f);
    if (more) { fprintf(stderr, "%s is larger than %ld bytes\n", path, limit); exit(2); }
    return n;
}

#include "sg1000_headless.inc"

static SgCpuView reference_cpu(const z80 *z)
{
    uint8_t f = (uint8_t)(z->sf << 7 | z->zf << 6 | z->yf << 5 | z->hf << 4 | z->xf << 3 | z->pf << 2 | z->nf << 1 | z->cf);
    SgCpuView c;
    c.af = (uint16_t)(z->a << 8 | f); c.bc = (uint16_t)(z->b << 8 | z->c); c.de = (uint16_t)(z->d << 8 | z->e);
    c.hl = (uint16_t)(z->h << 8 | z->l); c.ix = z->ix; c.iy = z->iy; c.sp = z->sp; c.pc = z->pc;
    c.af2 = (uint16_t)(z->a_ << 8 | z->f_); c.bc2 = (uint16_t)(z->b_ << 8 | z->c_); c.de2 = (uint16_t)(z->d_ << 8 | z->e_);
    c.hl2 = (uint16_t)(z->h_ << 8 | z->l_); c.ir = (uint16_t)(z->i << 8 | z->r);
    c.flags = (uint16_t)(z->interrupt_mode | (z->iff1 ? 4 : 0) | (z->iff2 ? 8 : 0) | (z->halted ? 16 : 0));
    c.wz = z->mem_ptr; c.iff1 = z->iff1; c.iff2 = z->iff2; c.halted = z->halted; c.im = z->interrupt_mode;
    c.i = z->i; c.r = z->r;
    return c;
}

int main(int argc, char **argv)
{
    const char *cart_rom = NULL;
    int pal = 0, route_result;
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!strcmp(a, "--pal")) { pal = 1; continue; }
        if (!v) { fprintf(stderr, "missing value for %s\n", a); return 2; }
        ++i;
        if (!strcmp(a, "--cart")) cart_rom = v;
        else if ((route_result = headless_option(a, v)) != 0) {
            if (route_result < 0) { fprintf(stderr, "bad value for %s\n", a); return 2; }
        } else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!cart_rom) { fprintf(stderr, "--cart is required\n"); return 2; }
    memset(cart, 0xFF, sizeof cart);
    long n = load(cart_rom, cart, (long)sizeof cart);
    uint32_t size = (uint32_t)((n + 0x1FFF) & ~0x1FFFL);
    if (!size) size = 0x2000;
    sg_init(&machine, cart, size, pal ? SG_LINES_PAL : SG_LINES_NTSC);
    machine.trace_frames = 1;

    z80 z;
    z80_init(&z);
    z.read_byte = bus_read;
    z.write_byte = bus_write;
    z.port_in = bus_in;
    z.port_out = bus_out;
    z.userdata = &machine;

    uint64_t accepted = 0;
    machine.line_hook = sg_route_line;
    while (machine.frames < frames_wanted) {
        z.int_pending = 0;                    /* the step accepts nothing: the levels are read after it */
        unsigned long c0 = z.cyc;
        z80_step(&z);
        sg_advance(&machine, (uint64_t)(z.cyc - c0));
        if (sg_nmi_edge(&machine)) {
            unsigned long c1 = z.cyc;
            z.nmi_pending = 1;
            sg1000_reference_accept(&z);      /* the NMI: never masked, ahead of /INT, even right after EI (not counted with /INT) */
            sg_advance(&machine, (uint64_t)(z.cyc - c1));
        } else if (sg_irq(&machine)) {
            z.int_pending = 1;
            z.int_data = 0xFF;
            unsigned long c1 = z.cyc;
            sg1000_reference_accept(&z);      /* nothing happens while IFF1 is clear or right after EI */
            if (!z.int_pending) {
                ++accepted;
                sg_advance(&machine, (uint64_t)(z.cyc - c1));
            }
            z.int_pending = 0;
        }
        if (route_frame_due) {                /* the service point: the instruction and its interrupt are complete */
            SgCpuView c = reference_cpu(&z);
            sg_route_row(&c);
        }
    }
    SgCpuView c = reference_cpu(&z);
    headless_report("reference", &c, accepted, NULL);
    return 0;
}
