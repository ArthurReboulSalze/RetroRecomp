/* Inline "idle" path of gb_tick for the generated Game Boy code.
 *
 * The generated bodies call gb_tick(ctx, n) after nearly every instruction. gb_tick is defined in gbrt.c, so each call
 * crosses a translation unit and runs the full general sequence (double speed, RTC, OAM DMA, serial, timer, PPU,
 * interrupts, audio). This header does exactly what gb_tick does for the ordinary case, in the caller, and hands every
 * other case to the real gb_tick before touching anything. It is a speed change only: the same state, the same order of
 * effects, the same cycles. tools/gameboy_tick_selftest.py checks it against the real gb_tick on random operation
 * streams, field by field.
 *
 * The ordinary case (DMG, which is the only model these exports run):
 *   - not CGB double speed, no instruction limit, no trace, none of the test switches that change how the runtime ticks
 *     (benchmark fast tick, forced scalar timer, eager audio);
 *   - no real-time clock running, no OAM DMA pending or active, no serial transfer in progress;
 *   - no TIMA reload in progress and, when the timer runs, no edge of its input inside these cycles (an edge is the
 *     one place where the arithmetic differs from a plain addition to DIV);
 *   - the audio pending state is consistent with single speed.
 * PPU synchronisation, the interrupt test, the audio scheduling and the delayed EI are the same code as gb_tick's, in the
 * same order. Anything else calls the real gb_tick.
 *
 * Not used when the runtime is built with its performance counters (they sit inside gb_tick).
 */
#ifndef RR_GB_TICK_FAST_H
#define RR_GB_TICK_FAST_H

#include "gbrt.h"
#include "ppu.h"
#include "audio.h"

#ifndef GBRT_ENABLE_PERFORMANCE_COUNTERS

#if defined(__GNUC__) || defined(__clang__)
#define RR_GB_TICK_UNLIKELY(x) __builtin_expect(!!(x), 0)
#else
#define RR_GB_TICK_UNLIKELY(x) (x)
#endif

static inline uint32_t rr_gb_tick_timer_period(uint8_t tac) {
    /* gb_timer_mask(tac) << 1: the DIV bit that clocks TIMA is 9, 3, 5 or 7. */
    static const uint32_t period[4] = {1u << 10, 1u << 4, 1u << 6, 1u << 8};
    return period[tac & 3u];
}

static inline void rr_gb_tick(GBContext* ctx, uint32_t cycles) {
    const uint8_t tac = ctx->io[0x07];
    if (RR_GB_TICK_UNLIKELY(
            cycles == 0u || ctx->cgb_double_speed ||
            gbrt_benchmark_fast_tick_enabled || gbrt_instruction_limit > 0 || gbrt_trace_enabled ||
            gbrt_force_scalar_timer || gbrt_force_eager_audio ||
            ctx->rtc.active || ctx->dma.pending || ctx->dma.active || ctx->serial_transfer.active ||
            ctx->tima_reload_pending ||
            ((tac & 0x04u) && cycles >= rr_gb_tick_timer_period(tac) -
                                           ((uint32_t)ctx->div_counter & (rr_gb_tick_timer_period(tac) - 1u))))) {
        gb_tick(ctx, cycles);
        return;
    }

    /* gb_tick: double speed bookkeeping (single speed: the remainder is read, then cleared). */
    const uint8_t previous_system_cycle_remainder = ctx->cgb_system_cycle_remainder & 1u;
    ctx->cgb_system_cycle_remainder = 0;

    /* gb_add_cycles */
    ctx->cycles += cycles;
    ctx->total_cycles += cycles;
    ctx->frame_cycles += cycles;
    if (ctx->run_cycle_budget > 0 &&
        (ctx->cycles - ctx->run_cycle_budget_start) >= ctx->run_cycle_budget) {
        ctx->stopped = 1;
    }
    if (ctx->lcd_off_active) {
        ctx->frame_lcd_off_cycles += cycles;
        ctx->total_lcd_off_cycles += cycles;
    }

    /* Timer: no reload in progress and no input edge inside these cycles, so DIV advances by the cycle count. */
    const uint16_t old_div = ctx->div_counter;
    ctx->div_counter = (uint16_t)(ctx->div_counter + cycles);
    ctx->io[0x04] = (uint8_t)(ctx->div_counter >> 8);

    /* gb_sync */
    for (;;) {
        const uint32_t current = ctx->cycles;
        const uint32_t delta = current - ctx->last_sync_cycles;
        if (delta > 0) {
            ctx->last_sync_cycles = current;
            if (ctx->ppu) ppu_tick((GBPPU*)ctx->ppu, ctx, delta);
        }
        if (ctx->hdma.cpu_stall_cycles > 0 && !ctx->hdma.processing_stall) {
            const uint16_t stall = ctx->hdma.cpu_stall_cycles;
            ctx->hdma.cpu_stall_cycles = 0;
            ctx->hdma.processing_stall = 1;
            gb_tick(ctx, stall);
            ctx->hdma.processing_stall = 0;
            continue;
        }
        break;
    }

    /* Interrupt acceptance and frame end stop the compiled code at the instruction boundary. */
    if (ctx->frame_done || (ctx->ime && (ctx->io[0x0F] & ctx->io[0x80] & 0x1F))) {
        ctx->stopped = 1;
    }

    /* gbrt_audio_schedule (single speed, lazy mode). */
    if (ctx->apu) {
        if (ctx->audio_pending_cpu_cycles != 0u && ctx->audio_pending_double_speed != 0u) {
            gbrt_audio_sync(ctx);
        }
        bool pending = true;
        if (ctx->audio_pending_cpu_cycles == 0u) {
            const uint32_t deadline = gb_audio_cycles_until_sample(ctx->apu);
            if (deadline == UINT32_MAX) {
                pending = false;
            } else {
                ctx->audio_pending_old_div = old_div;
                ctx->audio_pending_system_cycle_remainder = previous_system_cycle_remainder & 1u;
                ctx->audio_pending_double_speed = 0u;
                ctx->audio_cycles_until_event = deadline;
            }
        }
        if (pending) {
            ctx->audio_pending_cpu_cycles += cycles;
            if (cycles >= ctx->audio_cycles_until_event) {
                gbrt_audio_sync(ctx);
            } else {
                ctx->audio_cycles_until_event -= cycles;
            }
        }
    }

    if (ctx->ime_pending) { ctx->ime = 1; ctx->ime_pending = 0; }
}

/* Every call of the generated code goes through the inline path. The inline function above calls the real gb_tick
 * before this line, so the macro does not apply to it. */
#define gb_tick(ctx, cycles) rr_gb_tick((ctx), (cycles))

#endif /* GBRT_ENABLE_PERFORMANCE_COUNTERS */
#endif
