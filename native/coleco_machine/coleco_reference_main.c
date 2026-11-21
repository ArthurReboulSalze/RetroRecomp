/* Headless ColecoVision reference run: the corrected reference Z80 interpreter (runtime_reference.c, prepared from the pinned SuperZazu
 * copy by retrorecomp.cpu.prepare_reference with the NMI corrections, never edited by hand) on the ColecoVision machine of
 * coleco_machine.c. MIT, Retro-Recomp. A development check and the conversion's oracle: never built into a game.
 *
 * The ColecoVision inserts no wait state. The VDP's interrupt is /NMI, an edge the Z80 takes at the end of an instruction: the step runs with
 * nothing pending, the machine advances by its cycles, then the edge is read and the NMI accepted (coleco_reference_accept, the
 * interpreter's own acceptance, exported by the same generated copy; the corrected interpreter accepts it even right after EI). /INT is not wired.
 *
* Usage: coleco_reference --bios FILE --cart FILE|- [--pal] [--frames N] [--watch ADDR]... [--vram FILE] [--ram FILE] [--frame FILE] [--rows FILE] [--audio FILE]
 *                         [--script FILE | --event FRAME:pad:PORT:HEX]... [--report FILE] */
#include "coleco_machine.h"
#include "runtime_reference.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

void coleco_reference_accept(z80 *const z);      /* the interpreter's interrupt acceptance (both /INT and /NMI) */

static CvMachine machine;
static uint8_t bios[CV_BIOS_SIZE];
static uint8_t cart[0x8000];

static uint8_t bus_read(void *user, uint16_t address) { return cv_read((CvMachine *)user, address); }
static void bus_write(void *user, uint16_t address, uint8_t value) { cv_write((CvMachine *)user, address, value); }
static uint8_t bus_in(z80 *z, uint8_t port) { return cv_in((CvMachine *)z->userdata, port); }
static void bus_out(z80 *z, uint8_t port, uint8_t value) { cv_out((CvMachine *)z->userdata, port, value); }

/* "-" reads standard input: a player's ROM taken from its archive in memory reaches the program with no file copy. */
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

#include "coleco_headless.inc"

static CvCpuView reference_cpu(const z80 *z)
{
    uint8_t f = (uint8_t)(z->sf << 7 | z->zf << 6 | z->yf << 5 | z->hf << 4 | z->xf << 3 | z->pf << 2 | z->nf << 1 | z->cf);
    CvCpuView c;
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
    const char *cart_rom = NULL, *bios_rom = NULL;
    int pal = 0, route_result;
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!strcmp(a, "--pal")) { pal = 1; continue; }
        if (!v) { fprintf(stderr, "missing value for %s\n", a); return 2; }
        ++i;
        if (!strcmp(a, "--cart")) cart_rom = v;
        else if (!strcmp(a, "--bios")) bios_rom = v;
        else if ((route_result = headless_option(a, v)) != 0) {
            if (route_result < 0) { fprintf(stderr, "bad value for %s\n", a); return 2; }
        } else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!cart_rom || !bios_rom) { fprintf(stderr, "--bios and --cart are required\n"); return 2; }
    if (load(bios_rom, bios, CV_BIOS_SIZE) != CV_BIOS_SIZE) { fprintf(stderr, "%s is not an 8 KiB BIOS\n", bios_rom); return 2; }
    memset(cart, 0xFF, sizeof cart);
    long n = load(cart_rom, cart, (long)sizeof cart);
    uint32_t size = (uint32_t)((n + 0x1FFF) & ~0x1FFFL);
    if (!size) size = 0x2000;
    cv_init(&machine, bios, cart, size, pal ? CV_LINES_PAL : CV_LINES_NTSC);
    machine.trace_frames = 1;

    z80 z;
    z80_init(&z);
    z.read_byte = bus_read;
    z.write_byte = bus_write;
    z.port_in = bus_in;
    z.port_out = bus_out;
    z.userdata = &machine;

    uint64_t accepted = 0;
    machine.line_hook = cv_route_line;
    while (machine.frames < frames_wanted) {
        z.int_pending = 0;                    /* the step accepts nothing: the levels are read after it */
        unsigned long c0 = z.cyc;
        z80_step(&z);
        cv_advance(&machine, (uint64_t)(z.cyc - c0));
        if (cv_nmi_edge(&machine)) {
            unsigned long c1 = z.cyc;
            z.nmi_pending = 1;
            coleco_reference_accept(&z);      /* the NMI: never masked, ahead of /INT, even right after EI (not counted with /INT) */
            cv_advance(&machine, (uint64_t)(z.cyc - c1));
        } else if (cv_irq(&machine)) {
            z.int_pending = 1;
            z.int_data = 0xFF;
            unsigned long c1 = z.cyc;
            coleco_reference_accept(&z);      /* nothing happens while IFF1 is clear or right after EI */
            if (!z.int_pending) {
                ++accepted;
                cv_advance(&machine, (uint64_t)(z.cyc - c1));
            }
            z.int_pending = 0;
        }
        if (route_frame_due) {                /* the service point: the instruction and its interrupt are complete */
            CvCpuView c = reference_cpu(&z);
            cv_route_row(&c);
        }
    }
    CvCpuView c = reference_cpu(&z);
    headless_report("reference", &c, accepted, NULL);
    return 0;
}
