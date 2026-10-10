/* Ahead-of-time bodies for small writable-memory helpers.
 * The live instruction signature is checked before EACH added instruction;
 * a DMA source operand stays live. No
 * opcode decoder, cached RAM assumption, loop batching or interpreter call.
 * A changed helper, HALT bug or WRAM bus owned by DMA takes the usual fallback.
 */
#ifndef RETRO_GB_RAM_HELPERS_H
#define RETRO_GB_RAM_HELPERS_H
#include "gbrt.h"

static inline bool rr_gb_ram_signature(GBContext* ctx, uint16_t start,
                                      const uint8_t* bytes, unsigned size) {
    const uint32_t end = (uint32_t)start + size - 1u;
    const bool wram = start >= 0xC000 && end < 0xE000;
    const bool hram = start >= 0xFF80 && end <= 0xFFFE;
    if (!ctx || ctx->halt_bug || (!wram && !hram) || (wram && ctx->dma.active)) return false;
    for (unsigned i = 0; i < size; ++i)
        if (gb_read8(ctx, (uint16_t)(start + i)) != bytes[i]) return false;
    return true;
}

static inline uint8_t rr_gb_try_copy_helper(GBContext* ctx, uint16_t addr) {
    /* Unrolled byte copy: LD (DE),A; INC E; LD A,(HL+).
       Only the missing store is added; no transfer is coalesced. */
    static const uint8_t unrolled[] = {0x12, 0x1C, 0x2A};
    /* LCD-safe copy/fill loops. Recognize the complete live routine before
       every added instruction, including its backward-branch displacement. */
    static const uint8_t copy[] = {0xF3,0xF0,0x41,0xCB,0x4F,0x20,0xFA,0x2A,
                                 0x12,0xFB,0x13,0x0B,0x79,0xB0,0x20,0xF0,0xC9};
    static const uint8_t fill[] = {0x57,0xF3,0xF0,0x41,0xCB,0x4F,0x20,0xFA,
                                 0x72,0xFB,0x23,0x0B,0x79,0xB0,0x20,0xF1,0xC9};
    static const unsigned copy_entries[] = {0,3,8,9,10,11,12,13};
    static const unsigned fill_entries[] = {0,1,4,8,9,10,11,12,13};
    if (!ctx || ctx->halt_bug || addr < 0xC000 || addr == 0xFFFF ||
        (addr < 0xFF80 && ctx->dma.active)) return 0;
    const uint8_t opcode = gb_read8(ctx, addr);
    if (opcode == 0x12 && rr_gb_ram_signature(ctx, addr, unrolled, sizeof(unrolled))) {
        ctx->pc = (uint16_t)(addr + 1);
        gbrt_timed_bus_write8(ctx, ctx->de, ctx->a, 7);
        return 1;
    }
    for (unsigned kind = 0; kind < 2; ++kind) {
        const uint8_t* code = kind ? fill : copy;
        const unsigned* entries = kind ? fill_entries : copy_entries;
        const unsigned count = kind ? 9 : 8;
        for (unsigned i = 0; i < count; ++i) {
            const unsigned entry = entries[i];
            if (addr < entry || opcode != code[entry] ||
                !rr_gb_ram_signature(ctx, (uint16_t)(addr-entry), code, 17)) continue;
            ctx->pc = (uint16_t)(addr + (opcode == 0xCB ? 2 : 1));
            if (kind && entry == 0) { ctx->d = ctx->a; gb_tick(ctx,4); }
            else if (entry == (kind ? 1u : 0u)) { ctx->ime=0; ctx->ime_pending=0; gb_tick(ctx,4); }
            else if (entry == (kind ? 4u : 3u)) { gb_bit(ctx,1,ctx->a); gb_tick(ctx,8); }
            else if (entry == 8) { gbrt_timed_bus_write8(ctx,kind ? ctx->hl : ctx->de,kind ? ctx->d : ctx->a,7); }
            else if (entry == 9) { ctx->ime_pending=1; gb_tick(ctx,4); }
            else if (entry == 10) { gbrt_timed_inc16(ctx,kind ? &ctx->hl : &ctx->de); }
            else if (entry == 11) { gbrt_timed_dec16(ctx,&ctx->bc); }
            else if (entry == 12) { ctx->a=ctx->c; gb_tick(ctx,4); }
            else if (entry == 13) { gb_or8(ctx,ctx->b); gb_tick(ctx,4); }
            return 1;
        }
    }
    return 0;
}

static inline bool rr_gb_dma_page_signature(GBContext* ctx, uint16_t start) {
    /* LDH A,(flag); RRA; RRA; select one of two live DMA source pages. */
    static const uint8_t code[] = {0xF0,0x80,0x1F,0x1F,0x3E,0,0x30,0x02,
                                  0x3E,0,0xE0,0x46,0x3E,0x28,0x3D,0x20,0xFD,0xC9};
    if (!ctx || ctx->halt_bug || start < 0xFF80 || (uint32_t)start+sizeof(code)>0xFFFFu) return false;
    for (unsigned i=0;i<sizeof(code);++i)
        if (i!=5 && i!=9 && gb_read8(ctx,(uint16_t)(start+i))!=code[i]) return false;
    return true;
}

static inline uint8_t rr_gb_try_dma_page_helper(GBContext* ctx, uint16_t addr) {
    if (addr < 0xFF82 || !ctx || ctx->halt_bug || gb_read8(ctx,addr)!=0x1F) return 0;
    if (!rr_gb_dma_page_signature(ctx,(uint16_t)(addr-2)) &&
        !rr_gb_dma_page_signature(ctx,(uint16_t)(addr-3))) return 0;
    ctx->a=gb_rr(ctx,ctx->a);ctx->f_z=0;
    ctx->pc=(uint16_t)(addr+1);gb_tick(ctx,4);
    return 1;
}

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
    return rr_gb_try_interrupt_dma_helper(ctx, addr) || rr_gb_try_dma_page_helper(ctx, addr) ||
           rr_gb_try_copy_helper(ctx, addr);
}
#endif
