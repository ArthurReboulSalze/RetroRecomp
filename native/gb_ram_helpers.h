/* Ahead-of-time bodies for small writable-memory helpers.
 * The live instruction signature is checked before EACH added instruction;
 * a DMA source operand stays live. No
 * opcode decoder, cached RAM assumption, loop batching or interpreter call.
 * A changed helper, HALT bug or WRAM bus owned by DMA takes the usual fallback.
 */
#ifndef RETRO_GB_RAM_HELPERS_H
#define RETRO_GB_RAM_HELPERS_H
#include "gbrt.h"

static inline bool rr_gb_interrupt_dma_matches(GBContext* ctx, uint16_t start) {
    /* DI; LD A,page; LDH (DMA),A; LD A,40; DEC A; JR NZ,-3; EI; RET.
     * The DMA source page is live data, not an assumed constant. Every code
     * byte is checked before each added native DI/EI instruction. */
    static const uint8_t code[] =
        {0xF3, 0x3E, 0x00, 0xE0, 0x46, 0x3E, 0x28, 0x3D, 0x20, 0xFD, 0xFB, 0xC9};
    if (!ctx || ctx->halt_bug || start < 0xFF80 ||
        (uint32_t)start + sizeof(code) - 1u > 0xFFFE) return false;
    for (unsigned i = 0; i < sizeof(code); ++i)
        if (i != 2 && gb_read8(ctx, (uint16_t)(start + i)) != code[i]) return false;
    return true;
}

static inline uint8_t rr_gb_try_interrupt_dma_helper(GBContext* ctx, uint16_t addr) {
    if (rr_gb_interrupt_dma_matches(ctx, addr)) {
        ctx->ime = 0; ctx->ime_pending = 0;
        ctx->pc = (uint16_t)(addr + 1);
        gb_tick(ctx, 4);
        return 1;
    }
    if (addr >= 10 && rr_gb_interrupt_dma_matches(ctx, (uint16_t)(addr - 10))) {
        ctx->ime_pending = 1;
        ctx->pc = (uint16_t)(addr + 1);
        gb_tick(ctx, 4);
        return 1;
    }
    return 0;
}

static inline bool rr_gb_store_helper_matches(GBContext* ctx, uint16_t start) {
    static const uint8_t bytes[] = {0x12, 0x00, 0x00, 0x13, 0xC9};
    const uint32_t end = (uint32_t)start + sizeof(bytes) - 1u;
    const bool wram = start >= 0xC000 && end < 0xE000;
    const bool hram = start >= 0xFF80 && end <= 0xFFFE;
    if (!ctx || ctx->halt_bug || (!wram && !hram) || (wram && ctx->dma.active))
        return false;
    for (unsigned i = 0; i < sizeof(bytes); ++i)
        if (gb_read8(ctx, (uint16_t)(start + i)) != bytes[i]) return false;
    return true;
}

static inline uint8_t rr_gb_try_store_helper(GBContext* ctx, uint16_t addr) {
    if (addr < 0xC000) return 0;
    if (rr_gb_store_helper_matches(ctx, addr)) {
        /* LD (DE),A. The two following NOPs stay separate CPU instructions. */
        ctx->pc = (uint16_t)(addr + 1);
        gbrt_timed_bus_write8(ctx, ctx->de, ctx->a, 7);
        return 1;
    }
    if (addr >= 3 && rr_gb_store_helper_matches(ctx, (uint16_t)(addr - 3))) {
        /* INC DE, including the existing timed OAM/bus behavior. */
        ctx->pc = (uint16_t)(addr + 1);
        gbrt_timed_inc16(ctx, &ctx->de);
        return 1;
    }
    /* Keep the dispatch entry point compatible with already generated code. */
    return rr_gb_try_interrupt_dma_helper(ctx, addr);
}
#endif
