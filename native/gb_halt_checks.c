/* Authored scenarios: the halted fast-forward of the pinned runtime, with or without the mode 3 bound of 1.6.7
 * (gameboy_runtime.adapt_halt_mode3). No original cartridge bytes or assets.
 *
 * A program that waits in HALT (`EI` or `DI`, then `HALT ; NOP ; clear IF ; JR` back to the HALT) runs in short slices of random length
 * (gb_run_cycles with a budget) on random video memory, sprites, scroll, window and palettes, with an interrupt source that wakes the CPU
 * on a different PPU event in each variant: vertical blank, the HBlank source (the end of mode 3, the event the bound must not skip), the
 * OAM source, and LYC. After every slice a digest of the whole state is written to the trace file given as the argument: the context, the
 * memory blocks, the whole PPU and the sound unit's registers (not the lazy bookkeeping of its scheduling), and, in two further columns, the
 * count and the hash of the samples handed out so far.
 *
 * tools/gameboy_halt_selftest.py builds the runtime twice, with the bound and without, runs this on both and compares the traces line by
 * line: the state must be the same after every slice. ppu_tick is wrapped (the link option --wrap=ppu_tick) to count the long steps taken
 * inside mode 3, which the build without the bound never takes. */
#include "gb_state_compare.h"

static uint8_t rom_image[0x8000];

/* The interpreter runs the one instruction of the program, as the debug step of the runtime does. */
void gb_dispatch(GBContext* ctx, uint16_t addr) {
    const uint8_t saved = ctx->single_step_mode;
    ctx->single_step_mode = 1;
    gb_interpret(ctx, addr);
    ctx->single_step_mode = saved;
}

static GBContext* counted;
static unsigned long long mode3_long_steps, mode3_dots_in_long_steps, other_long_steps;
void __real_ppu_tick(GBPPU* ppu, GBContext* ctx, uint32_t cycles);
void __wrap_ppu_tick(GBPPU* ppu, GBContext* ctx, uint32_t cycles) {
    if (ctx == counted && cycles > 24u) {            /* longer than any instruction or interrupt dispatch: a halted step */
        if (ppu->mode == PPU_MODE_DRAW) { ++mode3_long_steps; mode3_dots_in_long_steps += cycles; }
        else ++other_long_steps;
    }
    __real_ppu_tick(ppu, ctx, cycles);
}

static void build_rom(unsigned ime) {
    memset(rom_image, 0, sizeof rom_image);
    rom_image[0x40] = 0xD9; rom_image[0x48] = 0xD9;                       /* RETI at the vertical blank and STAT vectors */
    const uint8_t program[] = {ime ? 0xFB : 0xF3, 0x76, 0x00, 0xAF, 0xE0, 0x0F, 0x18, 0xF9};   /* EI/DI ; HALT ; NOP ; XOR A ; LDH (IF),A ; JR HALT */
    memcpy(rom_image + 0x150, program, sizeof program);
}

/* The video setup of a variant: it only depends on the variant number. */
static GBContext* make(unsigned variant) {
    seed = 0x2468ace1u + variant * 7919u;
    const unsigned ime = (variant >> 3) & 1u;
    build_rom(ime);
    GBContext* ctx = gb_context_create(NULL);
    assert(ctx && gb_context_load_rom(ctx, rom_image, sizeof rom_image));
    ctx->callbacks.on_audio_sample = on_audio;
    audio_owner[0] = ctx;
    static const struct { uint16_t reg; uint8_t value; } sound[] = {{0xFF26, 0x80}, {0xFF24, 0x77}, {0xFF25, 0xFF}, {0xFF12, 0xF3}, {0xFF17, 0xB3}};
    for (unsigned i = 0; i < sizeof sound / sizeof *sound; ++i) gb_write8(ctx, sound[i].reg, sound[i].value);
    gb_write8(ctx, 0xFF13, (uint8_t)rnd()); gb_write8(ctx, 0xFF14, 0x80 | (rnd() & 7u));   /* a square channel playing */
    gb_write8(ctx, 0xFF40, 0x00);                                          /* screen off while video memory is filled */
    for (unsigned i = 0; i < 0x2000; ++i) ctx->vram[i] = (uint8_t)rnd();
    for (unsigned i = 0; i < 40; ++i) {
        ctx->oam[i * 4 + 0] = (uint8_t)(16 + rnd() % 150);                 /* Y: mostly visible lines */
        ctx->oam[i * 4 + 1] = (uint8_t)(rnd() % 168);                      /* X */
        ctx->oam[i * 4 + 2] = (uint8_t)rnd();
        ctx->oam[i * 4 + 3] = (uint8_t)(rnd() & 0xF0u);
    }
    gb_write8(ctx, 0xFF42, (uint8_t)rnd()); gb_write8(ctx, 0xFF43, (uint8_t)rnd());
    gb_write8(ctx, 0xFF4A, (uint8_t)(rnd() % 144)); gb_write8(ctx, 0xFF4B, (uint8_t)(rnd() % 167));
    gb_write8(ctx, 0xFF47, (uint8_t)rnd()); gb_write8(ctx, 0xFF48, (uint8_t)rnd()); gb_write8(ctx, 0xFF49, (uint8_t)rnd());
    gb_write8(ctx, 0xFF45, (uint8_t)(rnd() % 154));                        /* LYC */
    static const uint8_t stat_sources[] = {0x00, 0x08, 0x20, 0x40, 0x48, 0x60};
    gb_write8(ctx, 0xFF41, stat_sources[variant % 6u]);
    gb_write8(ctx, 0xFFFF, (variant % 6u) ? 0x03 : 0x01);                  /* vertical blank, and STAT for the sources */
    gb_write8(ctx, 0xFF40, (uint8_t)(0x80u | (rnd() & 0x7Fu)));            /* screen on, random layers, sizes and maps */
    gb_write8(ctx, 0xFF0F, 0x00);
    gb_tick(ctx, 4u * (rnd() % 114u));                                     /* a random place on the line, on a machine-cycle boundary */
    ctx->pc = 0x150;
    ctx->halted = 0; ctx->ime = 0; ctx->ime_pending = 0;
    return ctx;
}

static uint64_t fnv(uint64_t hash, const void* data, size_t size) {
    const unsigned char* bytes = (const unsigned char*)data;
    for (size_t i = 0; i < size; ++i) hash = (hash ^ bytes[i]) * 1099511628211ull;
    return hash;
}

/* A digest of everything that is the state of the console: the context without its allocation addresses and the lazy audio bookkeeping,
 * the memory blocks, the PPU, and the registers of the sound unit. */
static uint64_t digest(GBContext* ctx) {
    GBContext copy;
    memcpy(&copy, ctx, sizeof copy);
    copy.ppu = NULL; copy.apu = NULL; copy.wram = NULL; copy.vram = NULL; copy.oam = NULL; copy.hram = NULL; copy.io = NULL;
    copy.rom = NULL; copy.eram = NULL; copy.data_mod_state = NULL;
    /* Addresses of this process, not state (the two builds are two programs). */
    memset(&copy.callbacks, 0, sizeof copy.callbacks);
    copy.port_state = NULL; copy.host_configuration_path = NULL;
    memset(&copy.host_configuration_contract, 0, sizeof copy.host_configuration_contract);
    copy.audio_pending_cpu_cycles = 0; copy.audio_cycles_until_event = 0; copy.audio_pending_old_div = 0;
    copy.audio_pending_system_cycle_remainder = 0; copy.audio_pending_double_speed = 0;
    uint64_t hash = 1469598103934665603ull;
    hash = fnv(hash, &copy, sizeof copy);
    hash = fnv(hash, ctx->wram, 0x1000u * 8u);
    hash = fnv(hash, ctx->vram, 0x2000u * 2u);
    hash = fnv(hash, ctx->oam, 0xA0u);
    hash = fnv(hash, ctx->hram, 0x7Fu);
    hash = fnv(hash, ctx->io, 0x80u + 1u);
    hash = fnv(hash, ctx->ppu, sizeof(GBPPU));
    for (uint16_t reg = 0xFF10; reg <= 0xFF3F; ++reg) { const uint8_t value = gb_read8(ctx, reg); hash = fnv(hash, &value, 1); }
    return hash;
}

int main(int argc, char** argv) {
    FILE* trace = argc > 1 ? fopen(argv[1], "w") : NULL;
    assert(trace);
    const unsigned variants = 48, frames = 6;
    unsigned long long slices = 0, halted_slices = 0;
    for (unsigned variant = 0; variant < variants; ++variant) {
        audio_hash[0] = 1469598103934665603ull;
        audio_samples[0] = 0;
        GBContext* ctx = make(variant);
        counted = ctx;
        /* Slices of random length, a multiple of four cycles: a wake-up that comes a few cycles late shows at the next slice. */
        for (unsigned long long run = 0; run < (unsigned long long)frames * 70224ull;) {
            const uint32_t slice = 4u * (1u + rnd() % 150u);
            const uint32_t before = ctx->cycles;
            gb_run_cycles(ctx, slice);
            run += ctx->cycles - before;
            const int frame_end = ctx->frame_done != 0;
            gbrt_audio_sync(ctx);
            fprintf(trace, "%u %llu %u %d %016llx %llu %016llx\n", variant, slices, ctx->cycles, frame_end,
                    (unsigned long long)digest(ctx), (unsigned long long)audio_samples[0], (unsigned long long)audio_hash[0]);
            ++slices;
            halted_slices += ctx->halted != 0;
            if (frame_end) gb_reset_frame(ctx);
        }
        gb_context_destroy(ctx);
    }
    fclose(trace);
    printf("{\"variants\":%u,\"frames_each\":%u,\"slices\":%llu,\"slices_that_ended_halted\":%llu,"
           "\"long_steps_inside_mode3\":%llu,\"dots_in_those_steps\":%llu,\"long_steps_elsewhere\":%llu}\n",
           variants, frames, slices, halted_slices, mode3_long_steps, mode3_dots_in_long_steps, other_long_steps);
    return 0;
}
