/* Headless MSX native run: the translated Z80 bodies of the cartridge and of the BIOS, the shared banked step loop
 * (native/banked_runtime.inc rendered for the MSX by retrorecomp.z80_chain: a region map, one wait state per M1 cycle,
 * /INT read at the end of each instruction), the counted fallback on the corrected reference interpreter, and the MSX
 * machine of msx_machine.c. MIT, Retro-Recomp. A development check (tools/msx_native.py): not yet a game.
 *
 * Timing contract, the same as msx_reference_main.c so the two runs can be compared state for state: an instruction's
 * I/O and its writes to a cartridge device happen at the instruction's start time; the machine's lines are run at
 * instruction boundaries; /INT is read once the machine has caught up with the instruction.
 *
 * Same options as msx_reference: --main --logo --cart [--mapper --cart-base --mirrored] --layout --frames --pal
 * --watch --event --frame --audio --vram. It prints the same JSON, plus the native and fallback step counts. */
#define SMSRECOMP_BANKED_AOT 1
#include "msx_machine.h"
#include "game_banked.h"
#include "runtime_reference.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

static MsxMachine machine;
static uint8_t ram[65536];
static uint8_t slot0[0xC000];
static uint8_t cart[0x200000];

/* ---- the names the shared step loop and the generated bodies use ---- */
Z80State g_z80;
uint64_t g_sync_deadline, g_frame_ic;
int g_diff_freeze; uint64_t g_diff_icount;
void sms_diff_abort(void) {}
void sms_sync(void) {}
void sms_halt(void) {}
int sms_slot_bank(uint16_t addr) { (void)addr; return -1; }
static z80 g_hz;
static bool g_hz_init;
static uint64_t g_hybrid_calls, g_hybrid_cyc, g_irq_taken, g_next_line_cyc;
static uint64_t smsrecomp_total_cycles, smsrecomp_measured_guest_cycles;
static int banked_last_interpreted, smsrecomp_interp_depth, smsrecomp_stop_pending;
static uint64_t step_start;                 /* g_z80.cyc when the current instruction began */
uint16_t g_dbg_pc, g_enter_ring[SMS_ENTER_RING_SIZE];
uint32_t g_enter_pos;
int g_diff_active;
void sms_diff_enter(uint16_t addr) { (void)addr; }
/* The step loop marks each step's start with SMS_PC. An instruction's I/O happens at its start; a chain of redundant
 * DD/FD prefixes is one instruction for the reference (it discards them inside one step), so inside a chain the start
 * stays the chain's (prefix_pending is the step loop's own flag, in scope where SMS_PC expands). */
static uint64_t fragments_at_step;          /* banked_prefix_fragments when the current step began */
#undef SMS_PC
#define SMS_PC(pc) (g_dbg_pc = (uint16_t)(pc), prefix_pending ? (void)0 : (void)(step_start = g_z80.cyc), \
                    fragments_at_step = banked_prefix_fragments)

extern unsigned long z80_m1_fetches;        /* the reference CPU's M1 count (cpu.prepare_reference, m1_counter) */

static unsigned long frames_wanted = 120;
static void finish(void);

/* Bring the machine to `cycle`: its lines, frame flag and sound up to then. */
static void machine_to(uint64_t cycle)
{
    if (cycle > machine.cycles)
        msx_advance(&machine, cycle - machine.cycles);
    g_next_line_cyc = machine.next_line;
}

static void advance_vdp(uint64_t cycle);    /* after the step loop: it reads the loop's prefix counter */

static int vdp_irq_asserted(void) { return msx_irq(&machine); }

uint8_t sms_read8(uint16_t address) { return msx_read(&machine, address); }

void sms_write8(uint16_t address, uint8_t value)
{
    if (!machine.region[address >> 13].write)
        machine_to(step_start);             /* a device (mapper, SCC) sees the write at the instruction's start */
    msx_write(&machine, address, value);
}

uint8_t sms_io_in(uint8_t port) { machine_to(step_start); return msx_in(&machine, port); }
void sms_io_out(uint8_t port, uint8_t value) { machine_to(step_start); msx_out(&machine, port, value); }

/* The reference CPU of the fallback, on the same bus. */
static uint8_t hyb_read(void *user, uint16_t address) { (void)user; return sms_read8(address); }
static void hyb_write(void *user, uint16_t address, uint8_t value) { (void)user; sms_write8(address, value); }
static uint8_t hyb_in(z80 *z, uint8_t port) { (void)z; return sms_io_in(port); }
static void hyb_out(z80 *z, uint8_t port, uint8_t value) { (void)z; sms_io_out(port, value); }

static void state_to_hz(void)
{
    g_hz.a = g_z80.a; g_hz.b = g_z80.b; g_hz.c = g_z80.c; g_hz.d = g_z80.d; g_hz.e = g_z80.e; g_hz.h = g_z80.h;
    g_hz.l = g_z80.l;
    uint8_t f = g_z80.f;
    g_hz.sf = f >> 7 & 1; g_hz.zf = f >> 6 & 1; g_hz.yf = f >> 5 & 1; g_hz.hf = f >> 4 & 1;
    g_hz.xf = f >> 3 & 1; g_hz.pf = f >> 2 & 1; g_hz.nf = f >> 1 & 1; g_hz.cf = f & 1;
    g_hz.a_ = g_z80.a_; g_hz.b_ = g_z80.b_; g_hz.c_ = g_z80.c_; g_hz.d_ = g_z80.d_; g_hz.e_ = g_z80.e_;
    g_hz.h_ = g_z80.h_; g_hz.l_ = g_z80.l_; g_hz.f_ = g_z80.f_;
    g_hz.ix = g_z80.ix; g_hz.iy = g_z80.iy; g_hz.sp = g_z80.sp; g_hz.mem_ptr = g_z80.wz;
    g_hz.i = g_z80.i; g_hz.r = g_z80.r; g_hz.iff1 = g_z80.iff1; g_hz.iff2 = g_z80.iff2;
    g_hz.interrupt_mode = g_z80.im; g_hz.halted = g_z80.halted;
    g_hz.int_pending = 0; g_hz.nmi_pending = 0; g_hz.iff_delay = g_z80.ei_block;
    g_hz.q = g_z80.q; g_hz.p = g_z80.p;
}

static void state_from_hz(void)
{
    g_z80.a = g_hz.a; g_z80.b = g_hz.b; g_z80.c = g_hz.c; g_z80.d = g_hz.d; g_z80.e = g_hz.e; g_z80.h = g_hz.h;
    g_z80.l = g_hz.l;
    g_z80.f = (uint8_t)(g_hz.sf << 7 | g_hz.zf << 6 | g_hz.yf << 5 | g_hz.hf << 4 | g_hz.xf << 3 | g_hz.pf << 2
                        | g_hz.nf << 1 | g_hz.cf);
    g_z80.a_ = g_hz.a_; g_z80.b_ = g_hz.b_; g_z80.c_ = g_hz.c_; g_z80.d_ = g_hz.d_; g_z80.e_ = g_hz.e_;
    g_z80.h_ = g_hz.h_; g_z80.l_ = g_hz.l_; g_z80.f_ = g_hz.f_;
    g_z80.ix = g_hz.ix; g_z80.iy = g_hz.iy; g_z80.sp = g_hz.sp; g_z80.wz = g_hz.mem_ptr;
    g_z80.i = g_hz.i; g_z80.r = g_hz.r; g_z80.iff1 = g_hz.iff1; g_z80.iff2 = g_hz.iff2;
    g_z80.im = g_hz.interrupt_mode; g_z80.halted = g_hz.halted; g_z80.ei_block = g_hz.iff_delay ? 1 : 0;
    g_z80.q = g_hz.q; g_z80.p = g_hz.p;
}

/* Fallback accounting: where the interpreter ran (first addresses, for the report). */
static uint16_t fallback_at[16];
static uint64_t fallback_count[16];
static void smsrecomp_feedback_at(uint16_t address)
{
    for (int i = 0; i < 16; ++i) {
        if (fallback_count[i] && fallback_at[i] == address) { ++fallback_count[i]; return; }
        if (!fallback_count[i]) { fallback_at[i] = address; fallback_count[i] = 1; return; }
    }
}
/* Learning (--learn FILE): the four bytes at each address the interpreter ran, written out at the end; the next
 * generation translates them as byte-guarded native bodies (native.patterns beside game.toml, read by the emitter). */
static const char *learn_out;
static uint32_t learned[4096];
static int learned_count;
static int smsrecomp_learning_enabled(void) { return learn_out != NULL; }
static void smsrecomp_observe_code(const uint8_t *bytes)
{
    uint32_t word = (uint32_t)bytes[0] << 24 | (uint32_t)bytes[1] << 16 | (uint32_t)bytes[2] << 8 | bytes[3];
    for (int i = 0; i < learned_count; ++i)
        if (learned[i] == word) return;
    if (learned_count < 4096) learned[learned_count++] = word;
}
static void smsrecomp_state_service(void);
static void smsrecomp_banked_fallback(uint16_t addr);
void sms_dispatch_miss(uint16_t addr) { smsrecomp_banked_fallback(addr); }
void call_by_address(uint16_t addr) { smsrecomp_banked_fallback(addr); }

/* The region map the step loop reads: which source and bank (8 KB units) each region shows, or RAM (anything the
 * translated sources do not hold: RAM, an empty socket, the SCC window). */
static BankedRegion region_map[8];
static uint32_t smsrecomp_region_generation, map_built = UINT32_MAX;
static const BankedRegion *smsrecomp_region_map(void)
{
    if (map_built != machine.generation) {
        for (int i = 0; i < 8; ++i) {
            const MsxRegion *r = &machine.region[i];
            const MsxDevice *d = &machine.slot[r->primary][r->secondary];
            int rom = d->kind == MSX_DEV_ROM && r->read && d->block[i] >= 0 && d->source != MSX_SOURCE_NONE;
            region_map[i].source = rom ? d->source : 0;
            region_map[i].bank = rom ? (uint8_t)d->block[i] : 0;
            region_map[i].ram = (uint8_t)!rom;
        }
        map_built = machine.generation;
        smsrecomp_region_generation = machine.generation;
    }
    return region_map;
}

#include "msx_banked_loop.inc"

/* The machine catches up at the end of an instruction, never in the middle of a prefix chain (the reference runs the
 * whole chain as one step). */
static void advance_vdp(uint64_t cycle)
{
    if (banked_prefix_fragments != fragments_at_step)
        return;                              /* this step was a redundant prefix: the chain goes on */
    smsrecomp_total_cycles += cycle > smsrecomp_measured_guest_cycles ? cycle - smsrecomp_measured_guest_cycles : 0;
    smsrecomp_measured_guest_cycles = cycle;
    machine_to(cycle);
}

/* Called by the loop once an instruction and the interrupt it may accept are complete: the run stops there at the
 * frame limit, as the reference does. */
static void smsrecomp_state_service(void)
{
    if (machine.frames >= frames_wanted)
        finish();
}

/* ---- options, report ---- */
static const char *frame_out, *audio_out, *vram_out;
static unsigned watch[32];
static int watches;
typedef struct { unsigned long frame; int joy, a, b, c; } Event;
static Event events[64];
static int event_count, next_event;
static FILE *audio;
static uint32_t audio_hash = 2166136261u;
static uint64_t samples;
static int16_t chunk[MSX_AUDIO_BUFFER];

static uint32_t fnv_add(uint32_t h, const uint8_t *data, size_t size)
{
    for (size_t i = 0; i < size; ++i) h = (h ^ data[i]) * 16777619u;
    return h;
}

static void drain_audio(void)
{
    unsigned n = msx_audio_take(&machine, chunk, MSX_AUDIO_BUFFER);
    audio_hash = fnv_add(audio_hash, (const uint8_t *)chunk, n * sizeof *chunk);
    samples += n;
    if (audio) fwrite(chunk, sizeof *chunk, n, audio);
}

/* Called from the step loop's time path: apply input events, collect sound. */
static void frame_service(void)
{
    for (; next_event < event_count && events[next_event].frame <= machine.frames; ++next_event) {
        const Event *e = &events[next_event];
        if (e->joy) msx_joystick(&machine, e->a, (uint8_t)e->b);
        else msx_key(&machine, e->a, e->b, e->c);
    }
    if (machine.synth.out_count >= MSX_AUDIO_BUFFER / 2)
        drain_audio();
}

static void finish(void)
{
    drain_audio();
    if (audio) fclose(audio);
    if (learn_out) {
        FILE *f = fopen(learn_out, "w");
        for (int i = 0; f && i < learned_count; ++i) fprintf(f, "%08X\n", (unsigned)learned[i]);
        if (f) fclose(f);
    }
    uint32_t frame_hash = fnv_add(fnv_add(2166136261u, &machine.vdp.frame[0][0], sizeof machine.vdp.frame),
                                  machine.vdp.border, sizeof machine.vdp.border);
    if (frame_out) {
        FILE *f = fopen(frame_out, "wb");
        if (f) { fwrite(machine.vdp.frame, 1, sizeof machine.vdp.frame, f); fwrite(machine.vdp.border, 1, sizeof machine.vdp.border, f); fclose(f); }
    }
    if (vram_out) {
        FILE *f = fopen(vram_out, "wb");
        if (f) { fwrite(machine.vdp.vram, 1, sizeof machine.vdp.vram, f); fclose(f); }
    }
    printf("{\"engine\": \"native\", \"frames\": %llu, \"cycles\": %llu, \"interrupts\": %llu, "
           "\"pc\": %u, \"pc_slot\": %u, \"sp\": %u, \"af\": %u, \"bc\": %u, \"de\": %u, \"hl\": %u, \"ix\": %u, \"iy\": %u, "
           "\"iff1\": %d, \"halted\": %d, \"primary\": %u, \"secondary\": [%u, %u, %u, %u], "
           "\"vdp_regs\": [%u, %u, %u, %u, %u, %u, %u, %u], \"vdp_status\": %u, \"vram_fnv\": %u, \"ram_fnv\": %u, "
           "\"frame_fnv\": %u, \"audio_samples\": %llu, \"audio_fnv\": %u, "
           "\"native_steps\": %llu, \"halt_steps\": %llu, \"fallback_steps\": %llu, \"guarded_steps\": %llu, "
           "\"fallback_cycles\": %llu, \"fallback_at\": {",
           (unsigned long long)machine.frames, (unsigned long long)machine.cycles, (unsigned long long)g_irq_taken,
           g_z80.pc, msx_slot_of(&machine, g_z80.pc), g_z80.sp, z80_af(&g_z80), z80_bc(&g_z80), z80_de(&g_z80),
           z80_hl(&g_z80), g_z80.ix, g_z80.iy, g_z80.iff1, g_z80.halted, machine.primary, machine.secondary[0],
           machine.secondary[1], machine.secondary[2], machine.secondary[3], machine.vdp.reg[0], machine.vdp.reg[1],
           machine.vdp.reg[2], machine.vdp.reg[3], machine.vdp.reg[4], machine.vdp.reg[5], machine.vdp.reg[6],
           machine.vdp.reg[7], machine.vdp.status, fnv_add(2166136261u, machine.vdp.vram, sizeof machine.vdp.vram),
           fnv_add(2166136261u, ram, sizeof ram), frame_hash, (unsigned long long)samples, audio_hash,
           (unsigned long long)banked_native_steps, (unsigned long long)banked_halt_steps,
           (unsigned long long)banked_fallback_steps, (unsigned long long)banked_guarded_steps,
           (unsigned long long)g_hybrid_cyc);
    for (int i = 0; i < 16 && fallback_count[i]; ++i)
        printf("%s\"%04X\": %llu", i ? ", " : "", fallback_at[i], (unsigned long long)fallback_count[i]);
    printf("}, \"af2\": %u, \"bc2\": %u, \"de2\": %u, \"hl2\": %u, \"i\": %u, \"r\": %u, \"im\": %u, \"iff2\": %d, \"wz\": %u, ",
           (unsigned)(g_z80.a_ << 8 | g_z80.f_), (unsigned)(g_z80.b_ << 8 | g_z80.c_), (unsigned)(g_z80.d_ << 8 | g_z80.e_),
           (unsigned)(g_z80.h_ << 8 | g_z80.l_), g_z80.i, g_z80.r, g_z80.im, g_z80.iff2, g_z80.wz);
    msx_print_state(&machine, stdout);
    printf("\"watch\": {");
    for (int i = 0; i < watches; ++i)
        printf("%s\"%04X\": %u", i ? ", " : "", watch[i], msx_peek(&machine, (uint16_t)watch[i]));
    printf("}}\n");
    fflush(stdout);
    exit(0);
}

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
    const char *main_rom = NULL, *logo_rom = NULL, *cart_rom = NULL, *layout = "basic";
    unsigned long cart_base = 0x4000;
    int pal = 0, mirrored = 0;
    MsxMapper mapper = MSX_MAPPER_PLAIN;
    static const char *const mapper_names[MSX_MAPPER_COUNT] = { "plain", "konami", "konami-scc", "ascii8", "ascii16" };
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!strcmp(a, "--pal")) { pal = 1; continue; }
        if (!strcmp(a, "--mirrored")) { mirrored = 1; continue; }
        if (!v) { fprintf(stderr, "missing value for %s\n", a); return 2; }
        ++i;
        if (!strcmp(a, "--main")) main_rom = v;
        else if (!strcmp(a, "--logo")) logo_rom = v;
        else if (!strcmp(a, "--cart")) cart_rom = v;
        else if (!strcmp(a, "--cart-base")) cart_base = strtoul(v, NULL, 16);
        else if (!strcmp(a, "--layout")) layout = v;
        else if (!strcmp(a, "--frames")) frames_wanted = strtoul(v, NULL, 10);
        else if (!strcmp(a, "--frame")) frame_out = v;
        else if (!strcmp(a, "--audio")) audio_out = v;
        else if (!strcmp(a, "--vram")) vram_out = v;
        else if (!strcmp(a, "--learn")) learn_out = v;
        else if (!strcmp(a, "--watch") && watches < 32) watch[watches++] = (unsigned)strtoul(v, NULL, 16) & 0xFFFF;
        else if (!strcmp(a, "--mapper")) {
            int found = -1;
            for (int k = 0; k < MSX_MAPPER_COUNT; ++k) if (!strcmp(v, mapper_names[k])) found = k;
            if (found < 0) { fprintf(stderr, "unknown mapper %s\n", v); return 2; }
            mapper = (MsxMapper)found;
        } else if (!strcmp(a, "--event") && event_count < 64) {
            Event *e = &events[event_count];
            unsigned long f; int r, b, d; unsigned port, bits;
            if (sscanf(v, "%lu:key:%d:%d:%d", &f, &r, &b, &d) == 4) *e = (Event){ f, 0, r, b, d };
            else if (sscanf(v, "%lu:joy:%u:%x", &f, &port, &bits) == 3) *e = (Event){ f, 1, (int)port, (int)bits, 0 };
            else { fprintf(stderr, "bad event %s\n", v); return 2; }
            ++event_count;
        } else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!main_rom) { fprintf(stderr, "--main is required\n"); return 2; }
    msx_init(&machine, pal ? MSX_LINES_PAL : MSX_LINES_NTSC);
    machine.trace_frames = 1;                    /* comparisons: the per-frame running hash */
    memset(slot0, 0xFF, sizeof slot0);
    load(main_rom, slot0, 0x8000);
    if (logo_rom) load(logo_rom, slot0 + 0x8000, 0x4000);
    MsxDevice bios = { MSX_DEV_ROM, slot0, logo_rom ? 0xC000u : 0x8000u, 0, NULL };
    bios.source = 1;                             /* the BIOS is the second translated source (banked.sources) */
    msx_set_device(&machine, 0, 0, bios);
    memset(ram, 0, sizeof ram);
    if (!strcmp(layout, "expanded")) {
        msx_set_expanded(&machine, 3, 1);
        msx_set_device(&machine, 3, 2, (MsxDevice){ MSX_DEV_RAM, NULL, 0, 0, ram });
    } else if (!strcmp(layout, "basic")) {
        msx_set_device(&machine, 3, 0, (MsxDevice){ MSX_DEV_RAM, NULL, 0, 0, ram });
    } else { fprintf(stderr, "unknown layout %s\n", layout); return 2; }
    if (cart_rom) {
        memset(cart, 0xFF, sizeof cart);
        long n = load(cart_rom, cart, (long)sizeof cart - 0x4000);
        MsxDevice device = { MSX_DEV_ROM, cart, (uint32_t)n, (uint16_t)cart_base, NULL };
        device.mapper = mapper;
        device.mirrored = (uint8_t)mirrored;
        device.source = 0;                       /* the cartridge is the first translated source (game.toml) */
        msx_set_device(&machine, 1, 0, device);
    }
    if (audio_out && !(audio = fopen(audio_out, "wb"))) { fprintf(stderr, "cannot write %s\n", audio_out); return 3; }
    machine.line_hook = frame_service;
    memset(&g_z80, 0, sizeof g_z80);
    g_next_line_cyc = machine.next_line;
    smsrecomp_banked_run();                      /* returns through finish() at the frame limit */
    return 0;
}
