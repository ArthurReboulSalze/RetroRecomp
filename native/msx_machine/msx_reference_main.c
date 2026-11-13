/* Headless MSX reference run: the corrected reference Z80 interpreter (runtime_reference.c, prepared from the pinned
 * SuperZazu copy by retrorecomp.cpu.prepare_reference, never edited by hand) on the MSX machine of msx_machine.c.
 * MIT, Retro-Recomp. A development check only (tools/msx_reference.py): never built into a game.
 *
 * The MSX inserts one wait state in every M1 (opcode fetch) cycle. The interpreter counts the standard Z80 T-states;
 * tools/msx_reference.py adds a counter to the interpreter's R-register increment of its generated copy (one per M1
 * cycle, prefixes included), so the wait states of an instruction are its M1 fetches. An interrupt acknowledge keeps
 * its 13 cycles on the MSX (IM 1), so its fetch is not counted. The native bodies will carry the same cost as a
 * per-machine table of the shared emitter; this count is the cross-check.
 *
 * The /INT line is a level the Z80 samples at the end of each instruction: the step runs with nothing pending, the
 * machine advances by its cycles, then the level is read and an interrupt accepted (msx_reference_accept, the
 * interpreter's own acceptance, exported by the same generated copy). An instruction that reads the VDP status
 * therefore drops the line before it can be accepted, as on the machine.
 *
 * Usage: msx_reference --main main.rom [--logo logo.rom] [--cart cart.rom [--mapper plain|konami|konami-scc|ascii8|ascii16]
 *                      [--cart-base 4000] [--mirrored]] [--layout basic|expanded]
 *                      [--frames N] [--pal] [--until-halt] [--watch ADDR]... [--vram FILE] [--trace N]
 *                      [--frame FILE] [--audio FILE] [--event FRAME:key:ROW:BIT:DOWN | FRAME:joy:PORT:HEX]...
 * --frame writes the last picture (192 lines x 256 colour indices, then the 192 border colours), --audio the sound as
 * raw 16-bit mono samples at 44,100 Hz; an event applies at the start of its frame (keys of the matrix, a joystick
 * port's active-low bits).
 * With --until-halt the run stops after the first instruction that halts the CPU (authored timing checks). */
#include "msx_machine.h"
#include "runtime_reference.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

extern unsigned long z80_m1_fetches;          /* counted by the reference CPU (cpu.prepare_reference, m1_counter) */
void msx_reference_accept(z80 *const z);      /* the interpreter's interrupt acceptance */

static MsxMachine machine;
static uint8_t ram[65536];
static uint8_t slot0[0x10000];             /* the BIOS source: main, logo page; on the MSX2 the sub-ROM at C000h */
static MsxV9938 v9938;
static uint8_t mapper_ram[4u << 20];

/* --count-cart-writes: the cartridge writes per 2 KB window, for the conversion's mapper probe (msx_build.probe_mapper). */
static uint64_t cart_writes[32];
static void count_cart_write(void *user, uint16_t address, uint8_t value)
{
    (void)user; (void)value;
    ++cart_writes[address >> 11];
}

static void trace_cart_write(void *user, uint16_t address, uint8_t value)
{
    const MsxMachine *mm = (const MsxMachine *)user;
    if (address < 0x9800 || address >= 0xA000)          /* bank registers, not SCC sound registers */
        fprintf(stderr, "frame %llu line %u: cartridge write %04X <- %02X\n", (unsigned long long)mm->frames, mm->line,
                address, value);
}

static uint8_t bus_read(void *user, uint16_t address) { return msx_read((MsxMachine *)user, address); }
static void bus_write(void *user, uint16_t address, uint8_t value) { msx_write((MsxMachine *)user, address, value); }
static uint8_t bus_in(z80 *z, uint8_t port) { return msx_in((MsxMachine *)z->userdata, port); }
static void bus_out(z80 *z, uint8_t port, uint8_t value) { msx_out((MsxMachine *)z->userdata, port, value); }

/* "-" reads standard input: a player's ROM taken from its archive in memory reaches the runner with no file copy. */
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

static uint32_t fnv_add(uint32_t h, const uint8_t *data, size_t size)
{
    for (size_t i = 0; i < size; ++i) h = (h ^ data[i]) * 16777619u;
    return h;
}

static uint32_t fnv(const uint8_t *data, size_t size) { return fnv_add(2166136261u, data, size); }

#include "msx_route.inc"

/* The registers in the rows' order (msx_route_cpu_hash), as the native check gives them. */
static uint32_t reference_cpu_hash(const z80 *z)
{
    uint8_t f = (uint8_t)(z->sf << 7 | z->zf << 6 | z->yf << 5 | z->hf << 4 | z->xf << 3 | z->pf << 2 | z->nf << 1 | z->cf);
    const uint16_t regs[16] = {
        (uint16_t)(z->a << 8 | f), (uint16_t)(z->b << 8 | z->c), (uint16_t)(z->d << 8 | z->e), (uint16_t)(z->h << 8 | z->l),
        z->ix, z->iy, z->sp, z->pc,
        (uint16_t)(z->a_ << 8 | z->f_), (uint16_t)(z->b_ << 8 | z->c_), (uint16_t)(z->d_ << 8 | z->e_),
        (uint16_t)(z->h_ << 8 | z->l_), (uint16_t)(z->i << 8 | z->r),
        (uint16_t)(z->interrupt_mode | (z->iff1 ? 4 : 0) | (z->iff2 ? 8 : 0) | (z->halted ? 16 : 0)), z->mem_ptr, 0 };
    return msx_route_cpu_hash(regs);
}

int main(int argc, char **argv)
{
    const char *main_rom = NULL, *logo_rom = NULL, *cart_rom = NULL, *vram_out = NULL, *frame_out = NULL;
    const char *page3_out = NULL;
    unsigned long long trace_from = 0, trace_to = 0;   /* tools: the instructions that start in a window of machine cycles */                /* tools: the 16 KB the CPU sees at C000h-FFFFh, for oracle comparisons */
    int route_result;
    const char *layout = "basic", *sub_rom = NULL;
    unsigned long frames = 120, cart_base = 0x4000, trace = 0, mapper_kib = 256, sram_bit = 0;
    unsigned watch[32];
    int msx2plus = 0, watches = 0, pal = 0, until_halt = 0, mirrored = 0, trace_mapper = 0, count_writes = 0;
    MsxMapper mapper = MSX_MAPPER_PLAIN;
    static const char *const mapper_names[MSX_MAPPER_COUNT] = { "plain", "konami", "konami-scc", "ascii8", "ascii16" };
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i];
        const char *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!strcmp(a, "--pal")) { pal = 1; continue; }
        if (!strcmp(a, "--until-halt")) { until_halt = 1; continue; }
        if (!strcmp(a, "--mirrored")) { mirrored = 1; continue; }
        if (!strcmp(a, "--msx2plus")) { msx2plus = 1; continue; }
        if (!strcmp(a, "--trace-mapper")) { trace_mapper = 1; continue; }
        if (!strcmp(a, "--count-cart-writes")) { count_writes = 1; continue; }
        if (!v) { fprintf(stderr, "missing value for %s\n", a); return 2; }
        ++i;
        if (!strcmp(a, "--main")) main_rom = v;
        else if (!strcmp(a, "--logo")) logo_rom = v;
        else if (!strcmp(a, "--sub")) sub_rom = v;
        else if (!strcmp(a, "--mapper-kib")) mapper_kib = strtoul(v, NULL, 10);
        else if (!strcmp(a, "--cart")) cart_rom = v;
        else if (!strcmp(a, "--cart-base")) cart_base = strtoul(v, NULL, 16);
        else if (!strcmp(a, "--sram-bit")) sram_bit = strtoul(v, NULL, 10) < 8 ? 1ul << strtoul(v, NULL, 10) : 0;
        else if (!strcmp(a, "--layout")) layout = v;
        else if (!strcmp(a, "--mapper")) {
            int found = -1;
            for (int k = 0; k < MSX_MAPPER_COUNT; ++k) if (!strcmp(v, mapper_names[k])) found = k;
            if (found < 0) { fprintf(stderr, "unknown mapper %s\n", v); return 2; }
            mapper = (MsxMapper)found;
        }
        else if (!strcmp(a, "--frames")) frames = strtoul(v, NULL, 10);
        else if (!strcmp(a, "--vram")) vram_out = v;
        else if (!strcmp(a, "--page3")) page3_out = v;
        else if (!strcmp(a, "--trace")) trace = strtoul(v, NULL, 10);
        else if (!strcmp(a, "--trace-cycles")) sscanf(v, "%llu:%llu", &trace_from, &trace_to);
        else if (!strcmp(a, "--frame")) frame_out = v;
        else if ((route_result = msx_route_option(a, v)) != 0) {
            if (route_result < 0) { fprintf(stderr, "bad value for %s\n", a); return 2; }
        }
        else if (!strcmp(a, "--watch") && watches < 32) watch[watches++] = (unsigned)strtoul(v, NULL, 16) & 0xFFFF;
        else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!main_rom) { fprintf(stderr, "--main is required\n"); return 2; }

    msx_init(&machine, pal ? MSX_LINES_PAL : MSX_LINES_NTSC);
    machine.trace_frames = 1;                    /* comparisons: the per-frame running hash */
    if (trace_mapper) { machine.cart_write_hook = trace_cart_write; machine.hook_user = &machine; }
    else if (count_writes) { machine.cart_write_hook = count_cart_write; machine.hook_user = &machine; }
    memset(slot0, 0xFF, sizeof slot0);
    load(main_rom, slot0, 0x8000);
    if (logo_rom) load(logo_rom, slot0 + 0x8000, 0x4000);
    /* RAM content at power-on is not defined; a fixed pattern keeps runs reproducible. */
    memset(ram, 0, sizeof ram);
    if (sub_rom) {                                /* MSX2: the sub-ROM ends the BIOS source; the board of msx_setup_msx2 */
        uint32_t segments = (uint32_t)(mapper_kib / 16);
        if (segments < 4 || segments > 256 || (segments & (segments - 1))) { fprintf(stderr, "bad --mapper-kib\n"); return 2; }
        load(sub_rom, slot0 + 0xC000, 0x4000);
        (msx2plus ? msx_setup_msx2plus : msx_setup_msx2)(&machine, slot0, mapper_ram, segments, &v9938);
    } else {
    msx_set_device(&machine, 0, 0, (MsxDevice){ MSX_DEV_ROM, slot0, logo_rom ? 0xC000u : 0x8000u, 0, NULL });
    if (!strcmp(layout, "expanded")) {            /* slot 3 expanded, RAM in 3-2 (the C-BIOS MSX2 layout) */
        msx_set_expanded(&machine, 3, 1);
        msx_set_device(&machine, 3, 2, (MsxDevice){ MSX_DEV_RAM, NULL, 0, 0, ram });
    } else if (!strcmp(layout, "basic")) {        /* RAM in slot 3 (the C-BIOS MSX1 layout) */
        msx_set_device(&machine, 3, 0, (MsxDevice){ MSX_DEV_RAM, NULL, 0, 0, ram });
    } else { fprintf(stderr, "unknown layout %s\n", layout); return 2; }
    }
    static uint8_t cart[0x200000];
    if (cart_rom) {
        memset(cart, 0xFF, sizeof cart);              /* the padding up to a whole bank reads as an empty socket */
        long n = load(cart_rom, cart, (long)sizeof cart);
        MsxDevice device = { MSX_DEV_ROM, cart, (uint32_t)n, (uint16_t)cart_base, NULL };
        device.mapper = mapper;
        device.mirrored = (uint8_t)mirrored;
        if (sram_bit && (mapper == MSX_MAPPER_ASCII8 || mapper == MSX_MAPPER_ASCII16)) {
            static uint8_t sram[MSX_SRAM_ASCII8];     /* blank, as a fresh battery: the game's own file is not read here */
            device.sram = sram;
            device.sram_size = mapper == MSX_MAPPER_ASCII8 ? MSX_SRAM_ASCII8 : MSX_SRAM_ASCII16;
            device.sram_bit = (uint8_t)sram_bit;
        }
        msx_set_device(&machine, 1, 0, device);
    }

    z80 z;
    z80_init(&z);
    z.read_byte = bus_read;
    z.write_byte = bus_write;
    z.port_in = bus_in;
    z.port_out = bus_out;
    z.userdata = &machine;

    uint64_t waits = 0, steps = 0, accepted = 0;
    machine.line_hook = msx_route_line;
    while (machine.frames < frames) {
        if (trace_to && machine.cycles >= trace_from && machine.cycles < trace_to)   /* --trace-cycles: one line per instruction */
            fprintf(stderr, "T %llu %04X %02X%02X%02X%02X %02X%02X\n", (unsigned long long)machine.cycles, z.pc,
                    msx_peek(&machine, z.pc), msx_peek(&machine, (uint16_t)(z.pc + 1)), msx_peek(&machine, (uint16_t)(z.pc + 2)),
                    msx_peek(&machine, (uint16_t)(z.pc + 3)), machine.primary, machine.secondary[3]);
        if (trace && steps < trace)
            fprintf(stderr, "%06llu pc=%04X slot=%02X a=%02X sp=%04X\n", (unsigned long long)steps, z.pc,
                    msx_slot_of(&machine, z.pc), z.a, z.sp);
        int was_halted = z.halted;
        z.int_pending = 0;                    /* the step accepts nothing: the level is read after it */
        unsigned long c0 = z.cyc, f0 = z80_m1_fetches;
        z80_step(&z);
        unsigned long m1 = z80_m1_fetches - f0;
        waits += m1;
        ++steps;
        msx_advance(&machine, (uint64_t)(z.cyc - c0) + m1);
        if (until_halt && z.halted && !was_halted)
            break;
        if (msx_irq(&machine)) {
            z.int_pending = 1;
            z.int_data = 0xFF;
            unsigned long c1 = z.cyc;
            msx_reference_accept(&z);         /* nothing happens while IFF1 is clear or right after EI */
            if (!z.int_pending) {
                ++accepted;
                msx_advance(&machine, (uint64_t)(z.cyc - c1));
            }
            z.int_pending = 0;
        }
        if (route_frame_due)                     /* the service point: the instruction and its interrupt are complete */
            msx_route_row(reference_cpu_hash(&z), z.pc);
    }

    msx_route_finish();
    uint32_t frame_hash = msx_frame_hash(&machine);
    if (frame_out) {
        FILE *f = fopen(frame_out, "wb");
        if (!f || !msx_dump_frame(&machine, f)) return 3;
        fclose(f);
    }
    if (page3_out) {
        FILE *f = fopen(page3_out, "wb");
        if (!f) return 3;
        for (unsigned a = 0xC000; a <= 0xFFFF; ++a) fputc(msx_peek(&machine, (uint16_t)a), f);
        fclose(f);
    }
    if (vram_out) {
        FILE *f = fopen(vram_out, "wb");
        if (!f || !msx_dump_vram(&machine, f)) return 3;
        fclose(f);
    }
    unsigned nonzero = 0;
    const uint8_t *vram_bytes = machine.video == MSX_VIDEO_V9938 ? v9938.vram : machine.vdp.vram;
    size_t vram_size = machine.video == MSX_VIDEO_V9938 ? sizeof v9938.vram : sizeof machine.vdp.vram;
    for (size_t i = 0; i < vram_size; ++i) nonzero += vram_bytes[i] != 0;
    printf("{\"frames\": %llu, \"cycles\": %llu, \"z80_cycles\": %lu, \"m1_waits\": %llu, \"steps\": %llu, "
           "\"interrupts\": %llu, \"pc\": %u, \"pc_slot\": %u, \"sp\": %u, \"iff1\": %d, \"halted\": %d, "
           "\"primary\": %u, \"secondary\": [%u, %u, %u, %u], \"unmapped_reads\": %llu, \"dropped_writes\": %llu, "
           "\"vdp_regs\": [%u, %u, %u, %u, %u, %u, %u, %u], \"vdp_status\": %u, \"vram_fnv\": %u, \"vram_nonzero\": %u, "
           "\"frame_fnv\": %u, \"audio_samples\": %llu, \"audio_fnv\": %u, \"audio_dropped\": %llu, "
           "\"af\": %u, \"bc\": %u, \"de\": %u, \"hl\": %u, \"ix\": %u, \"iy\": %u, \"ram_fnv\": %u, ",
           (unsigned long long)machine.frames, (unsigned long long)machine.cycles, z.cyc, (unsigned long long)waits,
           (unsigned long long)steps, (unsigned long long)accepted, z.pc, msx_slot_of(&machine, z.pc), z.sp, z.iff1,
           z.halted, machine.primary, machine.secondary[0], machine.secondary[1], machine.secondary[2],
           machine.secondary[3], (unsigned long long)machine.unmapped_reads, (unsigned long long)machine.dropped_writes,
           machine.vdp.reg[0], machine.vdp.reg[1], machine.vdp.reg[2], machine.vdp.reg[3], machine.vdp.reg[4],
           machine.vdp.reg[5], machine.vdp.reg[6], machine.vdp.reg[7], machine.vdp.status,
           msx_vram_hash(&machine), nonzero, frame_hash, (unsigned long long)route_samples, route_audio_hash,
           (unsigned long long)machine.synth.dropped,
           (unsigned)(z.a << 8 | (z.sf << 7 | z.zf << 6 | z.yf << 5 | z.hf << 4 | z.xf << 3 | z.pf << 2 | z.nf << 1 | z.cf)),
           (unsigned)(z.b << 8 | z.c), (unsigned)(z.d << 8 | z.e), (unsigned)(z.h << 8 | z.l), z.ix, z.iy,
           msx_ram_hash(&machine, ram));
    printf("\"af2\": %u, \"bc2\": %u, \"de2\": %u, \"hl2\": %u, \"i\": %u, \"r\": %u, \"im\": %u, \"iff2\": %d, \"wz\": %u, ",
           (unsigned)(z.a_ << 8 | z.f_), (unsigned)(z.b_ << 8 | z.c_), (unsigned)(z.d_ << 8 | z.e_),
           (unsigned)(z.h_ << 8 | z.l_), z.i, z.r, z.interrupt_mode, z.iff2, z.mem_ptr);
    printf("\"cart_writes\": [");
    for (int i = 0; i < 32; ++i) printf("%s%llu", i ? ", " : "", (unsigned long long)cart_writes[i]);
    printf("], ");
    msx_print_state(&machine, stdout);
    printf("\"watch\": {");
    for (int i = 0; i < watches; ++i)
        printf("%s\"%04X\": %u", i ? ", " : "", watch[i], msx_peek(&machine, (uint16_t)watch[i]));
    printf("}}\n");
    return 0;
}
