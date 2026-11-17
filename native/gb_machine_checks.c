/* Authored checks of the Game Boy machine's snapshot and digest (native/gb_machine_state.h), the base of multiplayer rollback and of the
 * host's F8 / F9 for everyone. No original cartridge bytes or assets: three small programs written here (an MBC1 cartridge with RAM, an MBC3
 * with a clock, an MBC5 on the colour hardware) run in random slices of a few thousand cycles, between which the host writes random values
 * to the registers that matter (DMA, HDMA, sound, timer, serial, LCD, scroll, palettes, mapper, video and work memory, interrupt flags).
 * The sequence of slices and writes depends on the step number only.
 *
 *  1. Determinism: a run, then the same run with a snapshot at step K, loaded again after the end and replayed, gives the same digest and the same
 *     whole-state hash (an independent one, over the raw context, memory, video unit and sound registers) after every step; the same on a second
 *     context allocated apart; the snapshots taken again during the replay are equal byte for byte to those of the first run.
 *  2. Taking a snapshot every step (the rollback tier does) changes nothing of the run.
 *  3. A snapshot over a buffer of other bytes is the same bytes; a load of the wrong size, of a damaged header or of another game is refused and
 *     leaves the context as it was.
 *  4. The digest moves when any field of every group moves (CPU, mapper, clock, memory blocks, video unit, sound unit).
 *  5. The snapshots were taken while a DMA, an HDMA, a timer reload, a serial transfer, a halted CPU, a pending IME, a lit sound channel, a
 *     switched-off screen and a finished frame were in flight (counted in the summary, so that "equal" is not an empty result).
 * The summary is one JSON line; any failure stops the program. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbrt.h"
#include "ppu.h"
#include "audio.h"

enum { VARIANTS = 3, STEPS = 420, SAVE_AT = 137, SECOND_SAVE_AT = 301 };

static uint8_t rom_image[0x10000];
static const uint8_t* real_rom;      /* the player's own cartridge, given on the command line: a fourth variant (not in the repository) */
static size_t real_size;

/* The interpreter runs the one instruction at the address, as the debug step of the runtime does. */
void gb_dispatch(GBContext* ctx, uint16_t addr) {
    const uint8_t saved = ctx->single_step_mode;
    ctx->single_step_mode = 1;
    gb_interpret(ctx, addr);
    ctx->single_step_mode = saved;
}

static uint64_t samples_seen;
static void on_audio(GBContext* ctx, int16_t left, int16_t right) { (void)ctx; (void)left; (void)right; ++samples_seen; }

static uint64_t mix(uint64_t z) {
    z += 0x9e3779b97f4a7c15ull;
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ull;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebull;
    return z ^ (z >> 31);
}

static uint64_t fnv(uint64_t hash, const void* data, size_t size) {
    const unsigned char* bytes = (const unsigned char*)data;
    for (size_t i = 0; i < size; ++i) hash = (hash ^ bytes[i]) * 1099511628211ull;
    return hash;
}

/* ---- the authored cartridges ---- */
static size_t put(size_t at, const char* hex) {
    while (*hex) {
        if (*hex == ' ') { ++hex; continue; }
        unsigned value = 0;
        assert(sscanf(hex, "%2x", &value) == 1);
        rom_image[at++] = (uint8_t)value;
        hex += 2;
    }
    return at;
}

/* variant 0: MBC1 + RAM; 1: MBC3 + TIMER + RAM + BATTERY; 2: MBC5 + RAM, colour hardware. The program keeps a multiplicative generator in HRAM, writes
 * it to work RAM, cartridge RAM and the registers of the sound unit and the scroll, and waits in HALT for the vertical blank and the timer. */
static void build_rom(unsigned variant) {
    memset(rom_image, 0, sizeof rom_image);
    put(0x40, "C3 00 02");                                   /* vertical blank: JP 0200 */
    put(0x50, "C3 10 02");                                   /* timer: JP 0210 */
    put(0x58, "C3 20 02");                                   /* serial: JP 0220 */
    put(0x200, "F5 F0 82 3C E0 82 F1 D9");                   /* PUSH AF ; LDH A,(82) ; INC A ; LDH (82),A ; POP AF ; RETI */
    put(0x210, "F5 F0 83 3C E0 83 F1 D9");
    put(0x220, "F5 F0 84 3C E0 84 F1 D9");
    put(0x100, "00 C3 50 01");
    static const uint8_t types[VARIANTS] = {0x03, 0x10, 0x1A};
    rom_image[0x143] = variant == 2 ? 0x80 : 0x00;
    rom_image[0x147] = types[variant];
    rom_image[0x148] = 0x01;                                 /* 64 KiB: four banks */
    rom_image[0x149] = 0x02;                                 /* 8 KiB of cartridge RAM */
    size_t at = 0x150;
    at = put(at, "F3 31 FE FF");                             /* DI ; LD SP,FFFE */
    at = put(at, "3E 0A EA 00 00");                          /* the RAM (and the clock) of the cartridge on */
    at = put(at, "3E 80 E0 26 3E 77 E0 24 3E FF E0 25");     /* the sound unit on, full volume, every channel to both sides */
    at = put(at, "3E 05 E0 07 3E 07 E0 FF");                 /* timer on at 262 kHz ; vertical blank, timer and serial enabled */
    at = put(at, "3E 91 E0 40 AF E0 0F");                    /* screen and background on ; no flag pending */
    if (variant == 2) at = put(at, "3E 01 E0 4D 10 00");     /* arm the speed switch and STOP: double speed */
    at = put(at, "FB");                                      /* EI */
    const size_t loop = at;
    at = put(at, "F0 80 47 87 87 80 C6 11 E0 80 4F");        /* x = 5 x + 17 in HRAM (80) ; B = old, C = new */
    at = put(at, "26 C0 69 71 26 A0 69 71");                 /* work RAM and cartridge RAM at C0xx and A0xx, indexed by x */
    at = put(at, "79 E0 43 79 E0 13 F6 80 E0 14 79 E0 22");  /* scroll X ; a square channel retriggered ; the noise divisor */
    at = put(at, "F3 FB 76 00");                             /* DI ; EI ; HALT ; NOP: the interrupt flag of the EI is armed at each turn */
    const int jump = (int)loop - (int)(at + 2);
    rom_image[at++] = 0x18; rom_image[at++] = (uint8_t)(jump & 0xFF);
}

static GBContext* make(unsigned variant) {
    if (variant < VARIANTS) build_rom(variant);
    GBConfig config;
    memset(&config, 0, sizeof config);
    config.model = variant == 2 ? GB_MODEL_CGB : GB_MODEL_DMG;
    config.enable_audio = true; config.enable_serial = true; config.speed_percent = 100;
    config.rtc_unix_time_override_enabled = true; config.rtc_unix_time_override = 1700000000u;   /* the clock never reads the host's */
    config.ignore_rtc_persistence = true;
    GBContext* ctx = gb_context_create(&config);
    if (variant == VARIANTS) {
        assert(ctx && gb_context_load_rom(ctx, real_rom, real_size));
        ctx->callbacks.on_audio_sample = on_audio;
        gb_context_reset(ctx, true);                      /* the state the console leaves its boot ROM in, as the product starts it */
        return ctx;
    }
    assert(ctx && gb_context_load_rom(ctx, rom_image, sizeof rom_image));
    ctx->callbacks.on_audio_sample = on_audio;
    ctx->pc = 0x150; ctx->halted = 0; ctx->ime = 0; ctx->ime_pending = 0;
    return ctx;
}

/* ---- one step: the host's writes (a function of the step number), then a slice ---- */
static void step(GBContext* ctx, unsigned variant, unsigned i) {
    const uint64_t r = mix(0x6a09e667f3bcc908ull ^ ((uint64_t)variant << 40) ^ i);
    if (ctx->frame_done) gb_reset_frame(ctx);
    ctx->stopped = 0;
    if (variant == VARIANTS) {                            /* a real game: slices of a third of a frame to a frame and a half, no host writes */
        gb_run_cycles(ctx, 20000u + (uint32_t)((r >> 32) % 90000u));
        return;
    }
    const uint8_t v = (uint8_t)(r >> 24);
    uint32_t short_slice = 0;
    switch ((r >> 8) % 14u) {
    case 0: gb_write8(ctx, 0xFF46, (uint8_t)(0xC0 + ((r >> 16) % 0x1F))); short_slice = 8; break;                        /* OAM DMA */
    case 1: gb_write8(ctx, (uint16_t)(0xFF10 + ((r >> 16) % 0x30)), v); break;                           /* a sound register or the wave memory */
    case 2: gb_write8(ctx, (uint16_t)(0xFF05 + ((r >> 16) % 3)), v); break;                              /* TIMA, TMA, TAC */
    case 3: gb_write8(ctx, 0xFF40, ((r >> 16) % 7u) == 0 ? 0x00 : (uint8_t)(0x80 | (v & 0x7F))); break;   /* the screen off, now and then */
    case 4: gb_write8(ctx, 0xFF01, v); gb_write8(ctx, 0xFF02, 0x81); break;                              /* a serial transfer on the internal clock */
    case 5: gb_write8(ctx, (uint16_t)(0xFF42 + ((r >> 16) % 10)), v); break;                             /* scroll, LYC, DMA register, palettes, window */
    case 6: gb_write8(ctx, (uint16_t)(0x8000 + ((r >> 16) % 0x2000)), v); break;                         /* video memory */
    case 7: gb_write8(ctx, (uint16_t)(0xA000 + ((r >> 16) % 0x2000)), v); break;                         /* cartridge RAM */
    case 8: gb_write8(ctx, (uint16_t)((r >> 16) % 0x8000), v); break;                                    /* the mapper registers, and the clock latch */
    case 9: gb_write8(ctx, 0xFF0F, (uint8_t)(v & 0x1F)); break;                                          /* a pending interrupt, or none */
    case 10: gb_write8(ctx, 0xFF04, v); break;                                                           /* DIV */
    case 11: gb_write8(ctx, 0xFF00, (uint8_t)(v & 0x30)); break;                                         /* the pad lines */
    case 12:                                                                                             /* HDMA (colour) or a stack write */
        if (variant == 2) {
            gb_write8(ctx, 0xFF51, (uint8_t)(0xC0 + (v & 0x1F))); gb_write8(ctx, 0xFF52, (uint8_t)(r >> 32) & 0xF0);
            gb_write8(ctx, 0xFF53, (uint8_t)(0x80 + ((r >> 40) & 0x1F))); gb_write8(ctx, 0xFF54, (uint8_t)(r >> 48) & 0xF0);
            gb_write8(ctx, 0xFF55, (uint8_t)(((r >> 56) & 1u ? 0x80 : 0x00) | ((r >> 20) & 0x07))); short_slice = 600;
        } else gb_write8(ctx, 0xFFFF, (uint8_t)(0x05 | (v & 0x1A)));
        break;
    default: gb_write8(ctx, (uint16_t)(0xFF80 + ((r >> 16) % 0x7F)), v); break;                         /* high RAM */
    }
    if (variant == 2 && ((r >> 12) & 7u) == 0) { gb_write8(ctx, 0xFF4F, (uint8_t)(v & 1)); gb_write8(ctx, 0xFF70, (uint8_t)(v & 7)); }
    /* A slice of a few thousand cycles, or, one step in four, of a few cycles: the snapshot then lands inside an instruction's neighbourhood,
     * after an EI, in the start-up of a DMA. */
    uint32_t cycles = 1u + (uint32_t)((r >> 32) % 3000u);
    if (((r >> 44) & 3u) == 0) cycles = 1u + (uint32_t)((r >> 46) % 12u);
    gb_run_cycles(ctx, short_slice ? 1u + (uint32_t)((r >> 46) % short_slice) : cycles);
}

/* ---- an independent hash of the whole state: the raw context without what a snapshot leaves out on purpose, the memory, the video unit and
 * the registers of the sound unit. It does not know the snapshot's layout. ---- */
static uint64_t full_hash(GBContext* ctx) {
    GBContext* copy = (GBContext*)malloc(sizeof(GBContext));
    assert(copy);
    memcpy(copy, ctx, sizeof *copy);
    copy->ppu = NULL; copy->apu = NULL; copy->wram = NULL; copy->vram = NULL; copy->oam = NULL; copy->hram = NULL; copy->io = NULL;
    copy->rom = NULL; copy->eram = NULL; copy->data_mod_state = NULL; copy->timer = NULL; copy->serial = NULL; copy->joypad = NULL;
    copy->platform = NULL; copy->trace_file = NULL; copy->ppu_trace_file = NULL; copy->port_state = NULL; copy->host_configuration_path = NULL;
    memset(&copy->callbacks, 0, sizeof copy->callbacks);
    memset(&copy->host_configuration_contract, 0, sizeof copy->host_configuration_contract);
    /* Host-side bookkeeping outside the state: diagnostics and counters of the shell, the dirty flags of the persistence. */
    memset(&copy->performance_counters, 0, sizeof copy->performance_counters);
    memset(copy->dispatch_fallback_sites, 0, sizeof copy->dispatch_fallback_sites);
    copy->dispatch_fallback_site_count = 0; copy->dispatch_fallback_sites_dropped = 0;
    copy->semantic_transaction_sequence = 0; copy->semantic_transaction_outcome = GB_SEMANTIC_TRANSACTION_NONE;
    copy->semantic_transaction_dirty_count = 0;
    memset(copy->semantic_transaction_dirty, 0, sizeof copy->semantic_transaction_dirty);
    copy->persistence_load_failed = false; copy->eram_dirty = false; copy->rtc_dirty = false;
    copy->rr_ram_stub_instructions = copy->rr_ram_stub_cycles = copy->rr_ram_single_step_instructions = copy->rr_ram_single_step_cycles = 0;
    copy->rr_highmem_stub_instructions = copy->rr_highmem_stub_cycles = 0;
    memset(copy->rr_helper_entries, 0, sizeof copy->rr_helper_entries); memset(copy->rr_helper_cycles, 0, sizeof copy->rr_helper_cycles);
    uint64_t hash = 1469598103934665603ull;
    hash = fnv(hash, copy, sizeof *copy);
    free(copy);
    hash = fnv(hash, ctx->wram, 0x1000u * 8u);
    hash = fnv(hash, ctx->vram, 0x2000u * 2u);
    hash = fnv(hash, ctx->oam, 0xA0u);
    hash = fnv(hash, ctx->hram, 0x7Fu);
    hash = fnv(hash, ctx->io, 0x80u + 1u);
    if (ctx->eram_size) hash = fnv(hash, ctx->eram, ctx->eram_size);
    hash = fnv(hash, ctx->ppu, sizeof(GBPPU));
    for (uint16_t reg = 0xFF10; reg <= 0xFF3F; ++reg) { const uint8_t value = gb_read8(ctx, reg); hash = fnv(hash, &value, 1); }
    return hash;
}

typedef struct Trace { uint64_t digest[STEPS + 1], full[STEPS + 1], snapshot[STEPS + 1]; } Trace;

static struct {
    unsigned snapshots, dma_active, dma_pending, tima_reload, serial_active, halted, ime_pending, ime_on, sound_on, lcd_off, frame_done, hdma_active,
             double_speed, mbc_ram_on, rtc_variant;
} coverage;

static void note(const GBContext* ctx, unsigned variant) {
    ++coverage.snapshots;
    coverage.dma_active += ctx->dma.active != 0; coverage.dma_pending += ctx->dma.pending != 0;
    coverage.tima_reload += ctx->tima_reload_pending != 0; coverage.serial_active += ctx->serial_transfer.active != 0;
    coverage.halted += ctx->halted != 0; coverage.ime_pending += ctx->ime_pending != 0; coverage.ime_on += ctx->ime != 0;
    coverage.sound_on += (ctx->io[0x26] & 0x0F) != 0 || ctx->io[0x26] == 0x80; coverage.lcd_off += ctx->lcd_off_active != 0;
    coverage.frame_done += ctx->frame_done != 0; coverage.hdma_active += ctx->hdma.hblank_mode != 0 || ctx->hdma.blocks_remaining != 0;
    coverage.double_speed += ctx->cgb_double_speed != 0; coverage.mbc_ram_on += ctx->ram_enabled != 0; coverage.rtc_variant += variant == 1;
}

static void record(GBContext* ctx, Trace* trace, unsigned index) {
    trace->digest[index] = rr_gb_digest(ctx);
    trace->full[index] = full_hash(ctx);
}

static unsigned long long snapshots_compared, steps_replayed, sensitivity_checks, refusals;
static size_t bounds[VARIANTS + 1];
static uint8_t* foreign;          /* a snapshot of the first variant: another game's, for the others */
static size_t foreign_size;

static void expect_equal(const Trace* a, const Trace* b, unsigned from, unsigned to, const char* what, unsigned variant) {
    for (unsigned i = from; i <= to; ++i) {
        if (a->digest[i] != b->digest[i] || a->full[i] != b->full[i]) {
            fprintf(stderr, "variant %u: %s differs at step %u (digest %016llx/%016llx, whole state %016llx/%016llx)\n", variant, what, i,
                    (unsigned long long)a->digest[i], (unsigned long long)b->digest[i], (unsigned long long)a->full[i], (unsigned long long)b->full[i]);
            assert(0);
        }
    }
}

/* A snapshot that is not the one of the first run: run the first run again up to that step and say where the bytes first differ. */
static void diagnose(unsigned variant, unsigned after, const uint8_t* got, size_t bound) {
    GBContext* fresh = make(variant);
    uint8_t* want = (uint8_t*)malloc(bound);
    assert(want);
    for (unsigned i = 0; i < after; ++i) step(fresh, variant, i);
    assert(rr_gb_snap_save(fresh, want, bound) == bound);
    size_t first = 0, count = 0;
    while (first < bound && got[first] == want[first]) ++first;
    for (size_t i = 0; i < bound; ++i) count += got[i] != want[i];
    uint32_t core_size = 0, ppu_size = 0, apu_size = 0;
    memcpy(&core_size, want + 24, 4); memcpy(&ppu_size, want + 28, 4); memcpy(&apu_size, want + 32, 4);
    const size_t core_end = 64u + core_size, memory_end = bound - ppu_size - apu_size;
    fprintf(stderr, "variant %u: the snapshot after step %u differs from the first run's: %zu bytes, the first at %zu (header 0-64, core state 64-%zu, "
            "memory and cartridge RAM to %zu, video unit %u bytes, sound unit %u bytes)\n", variant, after, count, first, core_end, memory_end,
            ppu_size, apu_size);
    free(want); gb_context_destroy(fresh);
}

/* The state after the step `from`: loaded from a snapshot, it must give the digests and snapshots of the first run, step after step. */
static void replay(GBContext* ctx, unsigned variant, unsigned from, const Trace* ref, const Trace* roll, uint8_t* scratch, size_t bound) {
    assert(rr_gb_digest(ctx) == ref->digest[from] && full_hash(ctx) == ref->full[from]);
    for (unsigned i = from; i < STEPS; ++i) {
        step(ctx, variant, i);
        /* The snapshot first, as in the run it is compared with: the whole-state hash reads the sound registers through the bus, which
         * synchronises the sound unit, and a snapshot taken after that is not the one taken before. */
        assert(rr_gb_snap_save(ctx, scratch, bound) == bound);
        if (fnv(1469598103934665603ull, scratch, bound) != roll->snapshot[i + 1]) { diagnose(variant, i + 1, scratch, bound); assert(0); }
        assert(rr_gb_digest(ctx) == ref->digest[i + 1]);
        assert(full_hash(ctx) == ref->full[i + 1]);
        ++steps_replayed; ++snapshots_compared;
    }
}

#define MOVES(field, delta) do { __typeof__(field) saved_ = (field); (field) = (__typeof__(field))((field) + (delta)); \
        if (rr_gb_digest(ctx) == base) { fprintf(stderr, "the digest does not move with %s\n", #field); assert(0); } (field) = saved_; assert(rr_gb_digest(ctx) == base); ++sensitivity_checks; } while (0)

static void sensitivity(GBContext* ctx) {
    GBPPU* ppu = (GBPPU*)ctx->ppu;
    const uint64_t base = rr_gb_digest(ctx);
    MOVES(ctx->pc, 1); MOVES(ctx->sp, 0x100); MOVES(ctx->af, 0x10); MOVES(ctx->hl, 1); MOVES(ctx->ime, 1); MOVES(ctx->halted, 1);
    MOVES(ctx->rom_bank, 1); MOVES(ctx->ram_bank, 1); MOVES(ctx->ram_enabled, 1); MOVES(ctx->rtc.s, 1); MOVES(ctx->rtc.last_time, 1);
    MOVES(ctx->cycles, 1); MOVES(ctx->total_cycles, 1); MOVES(ctx->frame_cycles, 1); MOVES(ctx->div_counter, 1); MOVES(ctx->tima_reload_pending, 1);
    MOVES(ctx->dma.progress, 1); MOVES(ctx->dma.cycles_remaining, 1); MOVES(ctx->hdma.blocks_remaining, 1); MOVES(ctx->serial_transfer.cycles_remaining, 1);
    MOVES(ctx->audio_pending_cpu_cycles, 1); MOVES(ctx->audio_cycles_until_event, 1); MOVES(ctx->lcd_off_active, 1);
    MOVES(ctx->wram[0x1234], 1); MOVES(ctx->wram[0x7FFF], 1); MOVES(ctx->vram[0x1FFF], 1); MOVES(ctx->vram[0x3FFF], 1); MOVES(ctx->oam[5], 1);
    MOVES(ctx->hram[3], 1); MOVES(ctx->io[0x40], 1); MOVES(ctx->io[0x80], 1);
    if (ctx->eram_size) MOVES(ctx->eram[7], 1);
    MOVES(ppu->window_line, 1); MOVES(ppu->mode_cycles, 1); MOVES(ppu->draw_x, 1); MOVES(ppu->ly, 1); MOVES(ppu->bg_palette_ram[3], 1);
    MOVES(ppu->visible_sprite_x[9], 1); MOVES(ppu->considered_bg_tiles, 1);
    /* The sound unit's private fields are reached through its registers: a write that changes a channel (or switches the unit) moves the digest,
     * and the snapshot taken before gives the state back exactly. */
    {
        const size_t bound = rr_gb_snap_bound(ctx);
        uint8_t* keep = (uint8_t*)malloc(bound);
        assert(keep && rr_gb_snap_save(ctx, keep, bound) == bound);
        const uint64_t before = rr_gb_digest(ctx);
        static const uint16_t registers[] = {0xFF26, 0xFF24, 0xFF25, 0xFF12, 0xFF17, 0xFF1C, 0xFF22};
        static const uint8_t values[] = {0x5A, 0xA5, 0x80, 0x00};
        unsigned moved = 0;
        for (unsigned r = 0; r < sizeof registers / sizeof *registers; ++r)
            for (unsigned v = 0; v < sizeof values; ++v) {
                gb_write8(ctx, registers[r], values[v]);
                if (rr_gb_digest(ctx) != before) ++moved;
                assert(rr_gb_snap_load(ctx, keep, bound));
                assert(rr_gb_digest(ctx) == before);
            }
        assert(moved > 0);
        sensitivity_checks += moved;
        free(keep);
    }
    /* The pictures and the host's bookkeeping are not in the digest. */
    ppu->framebuffer[100] ^= 1; ppu->rgb_framebuffer[100] ^= 1; ctx->performance_counters.tick_cycles += 5; ctx->total_interpreter_cycles += 3;
    assert(rr_gb_digest(ctx) == base);
    ppu->framebuffer[100] ^= 1; ppu->rgb_framebuffer[100] ^= 1; ctx->performance_counters.tick_cycles -= 5; ctx->total_interpreter_cycles -= 3;
}
#undef MOVES

static void refusals_of(GBContext* ctx, const uint8_t* good, size_t bound, unsigned variant) {
    uint8_t* bad = (uint8_t*)malloc(bound + 16u);
    assert(bad);
    const uint64_t digest = rr_gb_digest(ctx), full = full_hash(ctx);
    memcpy(bad, good, bound);
    assert(!rr_gb_snap_load(ctx, good, bound - 1u)); assert(!rr_gb_snap_load(ctx, bad, bound + 16u));
    assert(!rr_gb_snap_load(ctx, good, 0)); assert(!rr_gb_snap_load(ctx, NULL, bound));
    for (unsigned field = 0; field < 5; ++field) {         /* the magic, the version, the ROM hash, the ROM size and the total of the header */
        static const unsigned offsets[5] = {0, 4, 8, 16, 36};
        memcpy(bad, good, bound);
        bad[offsets[field]] ^= 0x5A;
        assert(!rr_gb_snap_load(ctx, bad, bound));
    }
    if (foreign && foreign_size == bound && variant) assert(!rr_gb_snap_load(ctx, foreign, foreign_size));   /* another game's snapshot */
    refusals += 9u;
    assert(rr_gb_digest(ctx) == digest && full_hash(ctx) == full);                                       /* the context is as it was */
    free(bad);
}

/* EI just executed, the interrupt master enable not yet on: the snapshot taken there, loaded into a context allocated apart, gives the same next
 * instructions (IME comes on after the instruction that follows the EI, and a pending interrupt is then taken). */
static unsigned ime_pending_cases;
static void ime_pending_case(void) {
    GBContext* a = make(0);
    GBContext* b = make(0);
    const size_t bound = rr_gb_snap_bound(a);
    uint8_t* snapshot = (uint8_t*)malloc(bound);
    assert(snapshot);
    put(0x300, "F3 FB 3C 3C 3C 18 FB");                      /* DI ; EI ; INC A ; INC A ; INC A ; JR (the loop) */
    memcpy(a->rom + 0x300, rom_image + 0x300, 7); memcpy(b->rom + 0x300, rom_image + 0x300, 7);
    for (unsigned k = 0; k < 2; ++k) {
        GBContext* ctx = k ? b : a;
        ctx->pc = 0x300; ctx->ime = 0; ctx->ime_pending = 0; ctx->halted = 0;
        gb_write8(ctx, 0xFFFF, 0x01); gb_write8(ctx, 0xFF0F, 0x01);                         /* a vertical blank is pending */
    }
    gb_run_cycles(a, 8);                                                                     /* DI ; EI: the next instruction has not run */
    assert(a->ime_pending != 0 && a->ime == 0);
    assert(rr_gb_snap_save(a, snapshot, bound) == bound);
    assert(rr_gb_snap_load(b, snapshot, bound));
    assert(rr_gb_digest(a) == rr_gb_digest(b) && full_hash(a) == full_hash(b));
    for (unsigned i = 0; i < 6; ++i) {
        gb_run_cycles(a, 4); gb_run_cycles(b, 4);
        assert(rr_gb_digest(a) == rr_gb_digest(b) && full_hash(a) == full_hash(b));
    }
    assert(a->pc != 0x300 && a->pc == b->pc);
    ++ime_pending_cases;
    free(snapshot); gb_context_destroy(a); gb_context_destroy(b);
}

static void run_variant(unsigned variant) {
    Trace* ref = (Trace*)calloc(1, sizeof(Trace));
    Trace* roll = (Trace*)calloc(1, sizeof(Trace));
    assert(ref && roll);
    GBContext* a = make(variant);
    const size_t bound = rr_gb_snap_bound(a);
    assert(bound && bound % 16u == 0);
    bounds[variant] = bound;
    uint8_t* scratch = (uint8_t*)malloc(bound);
    uint8_t* other = (uint8_t*)malloc(bound);
    uint8_t* at_k = (uint8_t*)malloc(bound);
    uint8_t* at_k2 = (uint8_t*)malloc(bound);
    assert(scratch && other && at_k && at_k2);
    assert(rr_gb_snap_save(a, scratch, bound - 16u) == 0);       /* a buffer that is too small: nothing written, no success */

    /* A: the plain run. */
    record(a, ref, 0);
    for (unsigned i = 0; i < STEPS; ++i) { step(a, variant, i); record(a, ref, i + 1); }

    /* B: the same run with a snapshot after every step, as the rollback tier takes them: nothing changes. */
    GBContext* b = make(variant);
    record(b, roll, 0);
    for (unsigned i = 0; i < STEPS; ++i) {
        step(b, variant, i);
        assert(rr_gb_snap_save(b, scratch, bound) == bound);
        roll->snapshot[i + 1] = fnv(1469598103934665603ull, scratch, bound);
        note(b, variant);
        if (i + 1 == SAVE_AT) memcpy(at_k, scratch, bound);
        if (i + 1 == SECOND_SAVE_AT) memcpy(at_k2, scratch, bound);
        record(b, roll, i + 1);
        ++snapshots_compared;
    }
    expect_equal(ref, roll, 0, STEPS, "a run with a snapshot every step", variant);
    if (variant == 0) { foreign = (uint8_t*)malloc(bound); assert(foreign); memcpy(foreign, at_k, bound); foreign_size = bound; }

    /* A snapshot of the same state is the same bytes whatever the buffer held before. */
    memset(scratch, 0x00, bound); memset(other, 0xA5, bound);
    assert(rr_gb_snap_save(b, scratch, bound) == bound && rr_gb_snap_save(b, other, bound) == bound);
    assert(memcmp(scratch, other, bound) == 0);

    /* C: the first run is loaded back to the step SAVE_AT and replayed to the end: every digest, whole-state hash and snapshot comes again. */
    assert(rr_gb_snap_load(a, at_k, bound));
    replay(a, variant, SAVE_AT, ref, roll, scratch, bound);
    /* The same load over a context that is at the end, then a second load point, and again the end. */
    assert(rr_gb_snap_load(a, at_k2, bound));
    replay(a, variant, SECOND_SAVE_AT, ref, roll, scratch, bound);

    /* D: a context allocated apart, at its first step, loads the snapshot and replays: the state is the state, not the allocation. */
    GBContext* c = make(variant);
    assert(rr_gb_snap_load(c, at_k, bound));
    replay(c, variant, SAVE_AT, ref, roll, scratch, bound);
    refusals_of(c, at_k, bound, variant);
    sensitivity(c);

    gb_context_destroy(a); gb_context_destroy(b); gb_context_destroy(c);
    free(ref); free(roll); free(scratch); free(other); free(at_k); free(at_k2);
}

int main(int argc, char** argv) {
    for (unsigned variant = 0; variant < VARIANTS; ++variant) run_variant(variant);
    unsigned missing = 0;
    ime_pending_case();
#define NEEDS(name) do { if (!coverage.name) { fprintf(stderr, "no snapshot was taken with %s\n", #name); ++missing; } } while (0)
    NEEDS(dma_active); NEEDS(dma_pending); NEEDS(tima_reload); NEEDS(serial_active); NEEDS(halted); NEEDS(ime_on); NEEDS(sound_on);
    NEEDS(lcd_off); NEEDS(frame_done); NEEDS(hdma_active); NEEDS(double_speed); NEEDS(mbc_ram_on);
#undef NEEDS
    unsigned real_games = 0;
    if (argc > 1) {                                       /* the same checks on the player's own cartridge: its mapper, its code, its sound */
        FILE* file = fopen(argv[1], "rb");
        assert(file);
        fseek(file, 0, SEEK_END);
        const long length = ftell(file);
        fseek(file, 0, SEEK_SET);
        assert(length > 0x150 && length <= 8 * 1024 * 1024);
        uint8_t* data = (uint8_t*)malloc((size_t)length);
        assert(data && fread(data, 1, (size_t)length, file) == (size_t)length);
        fclose(file);
        real_rom = data; real_size = (size_t)length;
        run_variant(VARIANTS);
        real_games = 1;
        free(data);
    }
    printf("{\"variants\": %u, \"steps\": %u, \"bounds\": [%zu, %zu, %zu], \"snapshots_taken\": %u, \"snapshots_compared\": %llu, "
           "\"steps_replayed\": %llu, \"sensitivity_checks\": %llu, \"refusals\": %llu, \"in_flight\": {\"dma_active\": %u, \"dma_pending\": %u, "
           "\"tima_reload\": %u, \"serial\": %u, \"halted\": %u, \"ime_pending\": %u, \"ime\": %u, \"sound_on\": %u, \"lcd_off\": %u, "
           "\"frame_done\": %u, \"hdma\": %u, \"double_speed\": %u, \"mbc_ram\": %u}, \"audio_samples\": %llu, \"ime_pending_cases\": %u, \"real_game\": %u, \"real_bound\": %zu}\n",
           VARIANTS, STEPS, bounds[0], bounds[1], bounds[2], coverage.snapshots, snapshots_compared, steps_replayed, sensitivity_checks, refusals,
           coverage.dma_active, coverage.dma_pending, coverage.tima_reload, coverage.serial_active, coverage.halted, coverage.ime_pending, coverage.ime_on,
           coverage.sound_on, coverage.lcd_off, coverage.frame_done, coverage.hdma_active, coverage.double_speed, coverage.mbc_ram_on,
           (unsigned long long)samples_seen, ime_pending_cases, real_games, bounds[VARIANTS]);
    return missing ? 1 : 0;
}
