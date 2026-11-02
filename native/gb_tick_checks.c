/* Authored operation streams: the inline gb_tick path (gb_tick_fast.h) against the real gb_tick of the pinned runtime.
 * No original cartridge bytes or assets. Two contexts start identical and receive the same stream of ticks, register
 * writes and reads, interrupt-flag changes and host-style flag clears; one ticks through rr_gb_tick, the other through
 * the real gb_tick. After every operation the cheap fields are compared, and every 32 operations (and at the end) the
 * whole context, the whole PPU and the audio output are compared byte for byte. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbrt.h"
static unsigned long rr_gb_tick_fast_calls, rr_gb_tick_slow_calls, rr_gb_tick_why[9];   /* counted by the header, test builds only */
#define RR_GB_TICK_STATS 1
#include "gb_tick_fast.h"

#include "gb_state_compare.h"

/* Registers a game writes while it runs: timer, LCD, interrupt flags, OAM DMA, serial and the sound unit. */
static const uint16_t writable[] = {
    0xFF04, 0xFF05, 0xFF06, 0xFF07, 0xFF0F, 0xFFFF, 0xFF40, 0xFF41, 0xFF42, 0xFF43, 0xFF45, 0xFF47, 0xFF48,
    0xFF49, 0xFF4A, 0xFF4B, 0xFF46, 0xFF01, 0xFF02, 0xFF10, 0xFF11, 0xFF12, 0xFF13, 0xFF14, 0xFF16, 0xFF17,
    0xFF19, 0xFF1A, 0xFF1C, 0xFF1D, 0xFF1E, 0xFF21, 0xFF22, 0xFF23, 0xFF24, 0xFF25, 0xFF26, 0xFF30, 0xFF3F,
    0xC000, 0xFE00, 0xFF80};
static const uint32_t lengths[] = {4, 4, 4, 4, 8, 8, 12, 16, 20, 24, 1, 2, 3, 5, 7, 36, 64, 456, 4, 4, 8};

static void run_scenario(unsigned scenario, unsigned operations) {
    GBContext* a = gb_context_create(NULL);
    GBContext* b = gb_context_create(NULL);
    assert(a && b);
    audio_owner[0] = a; audio_owner[1] = b;
    audio_hash[0] = audio_hash[1] = 1469598103934665603ull;
    audio_samples[0] = audio_samples[1] = 0;
    a->callbacks.on_audio_sample = on_audio; b->callbacks.on_audio_sample = on_audio;
    /* Bring up the sound unit and the LCD the way a game does, then let the stream do the rest. */
    static const struct { uint16_t reg; uint8_t value; } boot[] = {
        {0xFF26, 0x80}, {0xFF24, 0x77}, {0xFF25, 0xFF}, {0xFF12, 0xF3}, {0xFF14, 0x87}, {0xFF40, 0x91},
        {0xFFFF, 0x1F}};
    for (unsigned i = 0; i < sizeof(boot) / sizeof(*boot); ++i) {
        gb_write8(a, boot[i].reg, boot[i].value); gb_write8(b, boot[i].reg, boot[i].value);
    }
    /* Scenario flavours: the timer off, on at each of its four rates; DMG interrupts enabled or masked. */
    const uint8_t tac = (uint8_t)(scenario % 5u == 0 ? 0u : (4u | (scenario % 4u)));
    gb_write8(a, 0xFF07, tac); gb_write8(b, 0xFF07, tac);
    a->ime = b->ime = (scenario & 1u) ? 1 : 0;
    for (unsigned op = 0; op < operations; ++op) {
        const unsigned kind = rnd() % 100u;
        if (kind < 70u) {
            const uint32_t n = lengths[rnd() % (sizeof(lengths) / sizeof(*lengths))];
            (gb_tick)(a, n);
            rr_gb_tick(b, n);
        } else if (kind < 88u) {
            const uint16_t reg = writable[rnd() % (sizeof(writable) / sizeof(*writable))];
            const uint8_t value = (uint8_t)rnd();
            gb_write8(a, reg, value); gb_write8(b, reg, value);
        } else if (kind < 94u) {
            const uint16_t reg = (uint16_t)(0xFF00u + rnd() % 0x80u);
            assert(gb_read8(a, reg) == gb_read8(b, reg));
        } else if (kind < 97u) {
            /* The host loop after a frame or an interrupt stop. */
            a->stopped = b->stopped = 0;
            if (rnd() & 1u) { gb_reset_frame(a); gb_reset_frame(b); }   /* the frame loop of the host */
            else { a->frame_done = b->frame_done = 0; }
        } else {
            const uint8_t ime = (uint8_t)(rnd() & 1u), pending = (uint8_t)(rnd() % 3u);
            a->ime = b->ime = ime; a->ime_pending = b->ime_pending = pending;
        }
        compare_cheap(a, b, scenario, op);
        if ((op & 31u) == 31u) compare_full(a, b, scenario, op);
    }
    compare_full(a, b, scenario, operations);
    gb_context_destroy(a); gb_context_destroy(b);
}

/* The slow-path conditions hand the call to the real gb_tick untouched: each of these must give the same state. */
static uint8_t rtc_rom[0x200] = {[0x147] = 0x10};   /* MBC3+TIMER+RAM+BATTERY header byte only */

static void slow_condition_checks(void) {
    for (unsigned flavour = 0; flavour < 6; ++flavour) {
        GBContext* a = gb_context_create(NULL);
        GBContext* b = gb_context_create(NULL);
        assert(a && b);
        audio_owner[0] = a; audio_owner[1] = b;
        audio_hash[0] = audio_hash[1] = 1469598103934665603ull; audio_samples[0] = audio_samples[1] = 0;
        a->callbacks.on_audio_sample = on_audio; b->callbacks.on_audio_sample = on_audio;
        gb_write8(a, 0xFF26, 0x80); gb_write8(b, 0xFF26, 0x80);
        gb_write8(a, 0xFF40, 0x91); gb_write8(b, 0xFF40, 0x91);
        gb_write8(a, 0xFF07, 5); gb_write8(b, 0xFF07, 5);
        switch (flavour) {
        case 0: a->tima_reload_pending = b->tima_reload_pending = 3; break;
        case 1: a->dma.active = b->dma.active = 1; a->dma.cycles_remaining = b->dma.cycles_remaining = 640; break;
        case 2: a->dma.pending = b->dma.pending = 1; a->dma.startup_delay = b->dma.startup_delay = 8; break;
        case 3: a->serial_transfer.active = b->serial_transfer.active = 1; break;
        case 4: a->rtc.active = b->rtc.active = 1; a->rom = b->rom = rtc_rom; a->rom_size = b->rom_size = sizeof(rtc_rom); break;
        default: a->div_counter = b->div_counter = 0x000C; break;   /* an input edge of the 16-cycle timer inside the tick */
        }
        for (unsigned op = 0; op < 600; ++op) {
            const uint32_t n = lengths[rnd() % (sizeof(lengths) / sizeof(*lengths))];
            (gb_tick)(a, n);
            rr_gb_tick(b, n);
            compare_cheap(a, b, 1000 + flavour, op);
        }
        compare_full(a, b, 1000 + flavour, 600);
        a->rom = b->rom = NULL; a->rom_size = b->rom_size = 0;   /* the array is not heap memory */
        gb_context_destroy(a); gb_context_destroy(b);
    }
}

/* With the LCD off there is no vblank: a frame is 70,224 cycles. Both ticks must end the frame at the same cycle, and a
 * frame that has not reached 70,224 cycles must not end. */
static void lcd_off_frame_checks(void) {
    for (unsigned flavour = 0; flavour < 4; ++flavour) {
        GBContext* a = gb_context_create(NULL);
        GBContext* b = gb_context_create(NULL);
        assert(a && b);
        audio_owner[0] = a; audio_owner[1] = b;
        audio_hash[0] = audio_hash[1] = 1469598103934665603ull; audio_samples[0] = audio_samples[1] = 0;
        a->callbacks.on_audio_sample = on_audio; b->callbacks.on_audio_sample = on_audio;
        gb_write8(a, 0xFF40, 0x91); gb_write8(b, 0xFF40, 0x91);
        (gb_tick)(a, 40); rr_gb_tick(b, 40);
        gb_write8(a, 0xFF40, 0x11); gb_write8(b, 0xFF40, 0x11);   /* LCD off */
        assert(a->lcd_off_active && b->lcd_off_active);
        gb_reset_frame(a); gb_reset_frame(b);
        const uint32_t step = flavour == 0 ? 4 : (flavour == 1 ? 12 : (flavour == 2 ? 7 : 456));
        uint32_t cycles_done = 0;
        while (!a->frame_done) {
            (gb_tick)(a, step); rr_gb_tick(b, step);
            cycles_done += step;
            assert(a->frame_done == b->frame_done && a->frame_cycles == b->frame_cycles);
            assert(a->frame_done == (a->frame_cycles >= 70224u));
            assert(cycles_done < 200000u);
        }
        assert(b->frame_done && b->stopped && a->stopped);
        compare_full(a, b, 2000 + flavour, cycles_done);
        /* The next frame starts clean and ends 70,224 cycles later. */
        gb_reset_frame(a); gb_reset_frame(b);
        assert(!a->frame_done && !b->frame_done && a->frame_cycles == 0);
        for (cycles_done = 0; !a->frame_done; cycles_done += step) {
            a->stopped = b->stopped = 0;
            (gb_tick)(a, step); rr_gb_tick(b, step);
            assert(cycles_done < 200000u);
        }
        assert(a->frame_cycles >= 70224u && a->frame_cycles - step < 70224u);
        compare_full(a, b, 2100 + flavour, cycles_done);
        gb_context_destroy(a); gb_context_destroy(b);
    }
}

int main(void) {
    for (unsigned scenario = 0; scenario < 48; ++scenario) run_scenario(scenario, 6000);
    slow_condition_checks();
    lcd_off_frame_checks();
    fprintf(stderr, "inline path %lu calls, handed to gb_tick %lu\n", rr_gb_tick_fast_calls, rr_gb_tick_slow_calls);
    fprintf(stderr, "why slow: zero %lu dbl %lu dbg %lu force %lu rtc %lu dma %lu serial %lu reload %lu timer-on %lu\n",
            rr_gb_tick_why[0], rr_gb_tick_why[1], rr_gb_tick_why[2], rr_gb_tick_why[3], rr_gb_tick_why[4],
            rr_gb_tick_why[5], rr_gb_tick_why[6], rr_gb_tick_why[7], rr_gb_tick_why[8]);
    assert(rr_gb_tick_fast_calls > rr_gb_tick_slow_calls);   /* the streams force DMA, serial and timer edges often; the inline path must still be the majority */
    printf("{\"checks\":%u,\"inline_tick_matches_gb_tick\":true,\"scenarios\":48}\n", checks);
    return 0;
}
