/* State comparison shared by the Game Boy runtime checks (gb_tick_checks.c, gb_halt_checks.c): two contexts that must be in the same state.
 * compare_cheap looks at the fields a tick moves; compare_full at the whole context, the memory blocks, the whole PPU and the audio output. */
#ifndef RR_GB_STATE_COMPARE_H
#define RR_GB_STATE_COMPARE_H
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbrt.h"
#include "ppu.h"
#include "audio.h"

static unsigned checks;
static uint64_t audio_hash[2];
static uint64_t audio_samples[2];
static GBContext* audio_owner[2];

static void on_audio(GBContext* ctx, int16_t left, int16_t right) {
    const unsigned side = ctx == audio_owner[1] ? 1u : 0u;
    audio_hash[side] = (audio_hash[side] ^ (uint16_t)left) * 1099511628211ull;
    audio_hash[side] = (audio_hash[side] ^ (uint16_t)right) * 1099511628211ull;
    ++audio_samples[side];
}

static uint32_t seed = 0x1badf00du;
static uint32_t rnd(void) {
    seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5;
    return seed;
}

static void compare_cheap(const GBContext* a, const GBContext* b, unsigned scenario, unsigned op) {
    if (a->cycles != b->cycles || a->total_cycles != b->total_cycles || a->frame_cycles != b->frame_cycles ||
        a->div_counter != b->div_counter || a->stopped != b->stopped || a->frame_done != b->frame_done ||
        a->io[0x04] != b->io[0x04] || a->io[0x05] != b->io[0x05] || a->io[0x0F] != b->io[0x0F] ||
        a->last_sync_cycles != b->last_sync_cycles || a->ime != b->ime || a->ime_pending != b->ime_pending ||
        a->audio_pending_cpu_cycles != b->audio_pending_cpu_cycles ||
        a->audio_cycles_until_event != b->audio_cycles_until_event ||
        a->tima_reload_pending != b->tima_reload_pending) {
        fprintf(stderr, "scenario %u op %u: cycles %u/%u div %04X/%04X stopped %u/%u frame %u/%u IF %02X/%02X "
                "sync %u/%u audio %u/%u\n", scenario, op, a->cycles, b->cycles, a->div_counter, b->div_counter,
                a->stopped, b->stopped, a->frame_done, b->frame_done, a->io[0x0F], b->io[0x0F],
                a->last_sync_cycles, b->last_sync_cycles, a->audio_pending_cpu_cycles, b->audio_pending_cpu_cycles);
        assert(0);
    }
    ++checks;
}

static void compare_full(GBContext* a, GBContext* b, unsigned scenario, unsigned op) {
    compare_cheap(a, b, scenario, op);
    GBContext* ca = (GBContext*)malloc(sizeof(GBContext));
    GBContext* cb = (GBContext*)malloc(sizeof(GBContext));
    assert(ca && cb);
    memcpy(ca, a, sizeof(GBContext)); memcpy(cb, b, sizeof(GBContext));
    /* Pointers that differ by allocation, not by state; their contents are compared below. */
    ca->ppu = cb->ppu = NULL; ca->apu = cb->apu = NULL;
    ca->wram = cb->wram = NULL; ca->vram = cb->vram = NULL; ca->oam = cb->oam = NULL;
    ca->hram = cb->hram = NULL; ca->io = cb->io = NULL;
    if (memcmp(ca, cb, sizeof(GBContext)) != 0) {
        const unsigned char* pa = (const unsigned char*)ca;
        const unsigned char* pb = (const unsigned char*)cb;
        size_t first = 0;
        while (pa[first] == pb[first]) ++first;
        fprintf(stderr, "scenario %u op %u: context differs at byte %zu of %zu\n", scenario, op, first,
                sizeof(GBContext));
        assert(0);
    }
    free(ca); free(cb);
    /* The memory blocks are allocated apart from the context (sizes as in gb_context_create). */
    assert(memcmp(a->wram, b->wram, 0x1000u * 8u) == 0);
    assert(memcmp(a->vram, b->vram, 0x2000u * 2u) == 0);
    assert(memcmp(a->oam, b->oam, 0xA0u) == 0);
    assert(memcmp(a->hram, b->hram, 0x7Fu) == 0);
    assert(memcmp(a->io, b->io, 0x80u + 1u) == 0);
    assert(a->ppu && b->ppu);
    if (memcmp(a->ppu, b->ppu, sizeof(GBPPU)) != 0) {
        fprintf(stderr, "scenario %u op %u: PPU state differs\n", scenario, op);
        assert(0);
    }
    assert(audio_hash[0] == audio_hash[1] && audio_samples[0] == audio_samples[1]);
    assert(gb_audio_cycles_until_sample(a->apu) == gb_audio_cycles_until_sample(b->apu));
    for (uint16_t reg = 0xFF10; reg <= 0xFF3F; ++reg) assert(gb_read8(a, reg) == gb_read8(b, reg));
    for (uint16_t reg = 0xFF40; reg <= 0xFF4B; ++reg) assert(gb_read8(a, reg) == gb_read8(b, reg));
    ++checks;
}

#endif
