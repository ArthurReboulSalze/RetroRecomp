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

extern unsigned long msx_m1_fetches;          /* counted by the generated interpreter copy */
void msx_reference_accept(z80 *const z);      /* the interpreter's interrupt acceptance */

static MsxMachine machine;
static uint8_t ram[65536];
static uint8_t slot0[0xC000];

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

typedef struct { unsigned long frame; int joy, a, b, c; } Event;

int main(int argc, char **argv)
{
    const char *main_rom = NULL, *logo_rom = NULL, *cart_rom = NULL, *vram_out = NULL, *frame_out = NULL, *audio_out = NULL;
    static Event events[64];
    int event_count = 0;
    const char *layout = "basic";
    unsigned long frames = 120, cart_base = 0x4000, trace = 0;
    unsigned watch[32];
    int watches = 0, pal = 0, until_halt = 0, mirrored = 0, trace_mapper = 0;
    MsxMapper mapper = MSX_MAPPER_PLAIN;
    static const char *const mapper_names[MSX_MAPPER_COUNT] = { "plain", "konami", "konami-scc", "ascii8", "ascii16" };
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i];
        const char *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!strcmp(a, "--pal")) { pal = 1; continue; }
        if (!strcmp(a, "--until-halt")) { until_halt = 1; continue; }
        if (!strcmp(a, "--mirrored")) { mirrored = 1; continue; }
        if (!strcmp(a, "--trace-mapper")) { trace_mapper = 1; continue; }
        if (!v) { fprintf(stderr, "missing value for %s\n", a); return 2; }
        ++i;
        if (!strcmp(a, "--main")) main_rom = v;
        else if (!strcmp(a, "--logo")) logo_rom = v;
        else if (!strcmp(a, "--cart")) cart_rom = v;
        else if (!strcmp(a, "--cart-base")) cart_base = strtoul(v, NULL, 16);
        else if (!strcmp(a, "--layout")) layout = v;
        else if (!strcmp(a, "--mapper")) {
            int found = -1;
            for (int k = 0; k < MSX_MAPPER_COUNT; ++k) if (!strcmp(v, mapper_names[k])) found = k;
            if (found < 0) { fprintf(stderr, "unknown mapper %s\n", v); return 2; }
            mapper = (MsxMapper)found;
        }
        else if (!strcmp(a, "--frames")) frames = strtoul(v, NULL, 10);
        else if (!strcmp(a, "--vram")) vram_out = v;
        else if (!strcmp(a, "--trace")) trace = strtoul(v, NULL, 10);
        else if (!strcmp(a, "--frame")) frame_out = v;
        else if (!strcmp(a, "--audio")) audio_out = v;
        else if (!strcmp(a, "--event") && event_count < 64) {
            Event *e = &events[event_count];
            unsigned long f; int r, b, d; unsigned port, bits;
            if (sscanf(v, "%lu:key:%d:%d:%d", &f, &r, &b, &d) == 4) *e = (Event){ f, 0, r, b, d };
            else if (sscanf(v, "%lu:joy:%u:%x", &f, &port, &bits) == 3) *e = (Event){ f, 1, (int)port, (int)bits, 0 };
            else { fprintf(stderr, "bad event %s\n", v); return 2; }
            ++event_count;
        }
        else if (!strcmp(a, "--watch") && watches < 32) watch[watches++] = (unsigned)strtoul(v, NULL, 16) & 0xFFFF;
        else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!main_rom) { fprintf(stderr, "--main is required\n"); return 2; }

    msx_init(&machine, pal ? MSX_LINES_PAL : MSX_LINES_NTSC);
    if (trace_mapper) { machine.cart_write_hook = trace_cart_write; machine.hook_user = &machine; }
    memset(slot0, 0xFF, sizeof slot0);
    load(main_rom, slot0, 0x8000);
    if (logo_rom) load(logo_rom, slot0 + 0x8000, 0x4000);
    msx_set_device(&machine, 0, 0, (MsxDevice){ MSX_DEV_ROM, slot0, logo_rom ? 0xC000u : 0x8000u, 0, NULL });
    /* RAM content at power-on is not defined; a fixed pattern keeps runs reproducible. */
    memset(ram, 0, sizeof ram);
    if (!strcmp(layout, "expanded")) {            /* slot 3 expanded, RAM in 3-2 (the C-BIOS MSX2 layout) */
        msx_set_expanded(&machine, 3, 1);
        msx_set_device(&machine, 3, 2, (MsxDevice){ MSX_DEV_RAM, NULL, 0, 0, ram });
    } else if (!strcmp(layout, "basic")) {        /* RAM in slot 3 (the C-BIOS MSX1 layout) */
        msx_set_device(&machine, 3, 0, (MsxDevice){ MSX_DEV_RAM, NULL, 0, 0, ram });
    } else { fprintf(stderr, "unknown layout %s\n", layout); return 2; }
    static uint8_t cart[0x200000];
    if (cart_rom) {
        memset(cart, 0xFF, sizeof cart);              /* the padding up to a whole bank reads as an empty socket */
        long n = load(cart_rom, cart, (long)sizeof cart - 0x4000);
        MsxDevice device = { MSX_DEV_ROM, cart, (uint32_t)n, (uint16_t)cart_base, NULL };
        device.mapper = mapper;
        device.mirrored = (uint8_t)mirrored;
        msx_set_device(&machine, 1, 0, device);
    }

    z80 z;
    z80_init(&z);
    z.read_byte = bus_read;
    z.write_byte = bus_write;
    z.port_in = bus_in;
    z.port_out = bus_out;
    z.userdata = &machine;

    uint64_t waits = 0, steps = 0, accepted = 0, samples = 0;
    uint32_t audio_hash = 2166136261u;
    FILE *audio = audio_out ? fopen(audio_out, "wb") : NULL;
    if (audio_out && !audio) { fprintf(stderr, "cannot write %s\n", audio_out); return 3; }
    static int16_t chunk[MSX_AUDIO_BUFFER];
    int next_event = 0;
    while (machine.frames < frames) {
        for (; next_event < event_count && events[next_event].frame <= machine.frames; ++next_event) {
            const Event *e = &events[next_event];
            if (e->joy) msx_joystick(&machine, e->a, (uint8_t)e->b);
            else msx_key(&machine, e->a, e->b, e->c);
        }
        if (machine.synth.out_count >= MSX_AUDIO_BUFFER / 2) {
            unsigned n = msx_audio_take(&machine, chunk, MSX_AUDIO_BUFFER);
            audio_hash = fnv_add(audio_hash, (const uint8_t *)chunk, n * sizeof *chunk);
            samples += n;
            if (audio) fwrite(chunk, sizeof *chunk, n, audio);
        }
        if (trace && steps < trace)
            fprintf(stderr, "%06llu pc=%04X slot=%02X a=%02X sp=%04X\n", (unsigned long long)steps, z.pc,
                    msx_slot_of(&machine, z.pc), z.a, z.sp);
        int was_halted = z.halted;
        z.int_pending = 0;                    /* the step accepts nothing: the level is read after it */
        unsigned long c0 = z.cyc, f0 = msx_m1_fetches;
        z80_step(&z);
        unsigned long m1 = msx_m1_fetches - f0;
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
    }

    {
        unsigned n = msx_audio_take(&machine, chunk, MSX_AUDIO_BUFFER);
        audio_hash = fnv_add(audio_hash, (const uint8_t *)chunk, n * sizeof *chunk);
        samples += n;
        if (audio) { fwrite(chunk, sizeof *chunk, n, audio); fclose(audio); }
    }
    uint32_t frame_hash = fnv_add(fnv(&machine.vdp.frame[0][0], sizeof machine.vdp.frame), machine.vdp.border,
                                  sizeof machine.vdp.border);
    if (frame_out) {
        FILE *f = fopen(frame_out, "wb");
        if (!f || fwrite(machine.vdp.frame, 1, sizeof machine.vdp.frame, f) != sizeof machine.vdp.frame
            || fwrite(machine.vdp.border, 1, sizeof machine.vdp.border, f) != sizeof machine.vdp.border) return 3;
        fclose(f);
    }
    if (vram_out) {
        FILE *f = fopen(vram_out, "wb");
        if (!f || fwrite(machine.vdp.vram, 1, sizeof machine.vdp.vram, f) != sizeof machine.vdp.vram) return 3;
        fclose(f);
    }
    unsigned nonzero = 0;
    for (size_t i = 0; i < sizeof machine.vdp.vram; ++i) nonzero += machine.vdp.vram[i] != 0;
    printf("{\"frames\": %llu, \"cycles\": %llu, \"z80_cycles\": %lu, \"m1_waits\": %llu, \"steps\": %llu, "
           "\"interrupts\": %llu, \"pc\": %u, \"pc_slot\": %u, \"sp\": %u, \"iff1\": %d, \"halted\": %d, "
           "\"primary\": %u, \"secondary\": [%u, %u, %u, %u], \"unmapped_reads\": %llu, \"dropped_writes\": %llu, "
           "\"vdp_regs\": [%u, %u, %u, %u, %u, %u, %u, %u], \"vdp_status\": %u, \"vram_fnv\": %u, \"vram_nonzero\": %u, "
           "\"frame_fnv\": %u, \"audio_samples\": %llu, \"audio_fnv\": %u, \"audio_dropped\": %llu, "
           "\"watch\": {",
           (unsigned long long)machine.frames, (unsigned long long)machine.cycles, z.cyc, (unsigned long long)waits,
           (unsigned long long)steps, (unsigned long long)accepted, z.pc, msx_slot_of(&machine, z.pc), z.sp, z.iff1,
           z.halted, machine.primary, machine.secondary[0], machine.secondary[1], machine.secondary[2],
           machine.secondary[3], (unsigned long long)machine.unmapped_reads, (unsigned long long)machine.dropped_writes,
           machine.vdp.reg[0], machine.vdp.reg[1], machine.vdp.reg[2], machine.vdp.reg[3], machine.vdp.reg[4],
           machine.vdp.reg[5], machine.vdp.reg[6], machine.vdp.reg[7], machine.vdp.status,
           fnv(machine.vdp.vram, sizeof machine.vdp.vram), nonzero, frame_hash, (unsigned long long)samples, audio_hash,
           (unsigned long long)machine.synth.dropped);
    for (int i = 0; i < watches; ++i)
        printf("%s\"%04X\": %u", i ? ", " : "", watch[i], msx_peek(&machine, (uint16_t)watch[i]));
    printf("}}\n");
    return 0;
}
