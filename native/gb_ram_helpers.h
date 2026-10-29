/* Ahead-of-time bodies for small writable-memory helpers.
 * The live instruction signature is checked before EACH added instruction;
 * a DMA source operand stays live. The multi-instruction helpers use no
 * opcode decoder, cached RAM assumption, loop batching or interpreter call.
 * A changed helper, HALT bug or WRAM bus owned by DMA takes the usual fallback.
 * rr_gb_try_ram_instruction (below) is the one decoder here: a single
 * instruction read live from WRAM/HRAM, executed with the interpreter's own
 * helpers and timing, never batched; it only receives what the helpers and the
 * upstream RAM stub declined. It is NOT native code and NOT ahead-of-time
 * translation: it is a one-instruction-at-a-time executor of writable code,
 * cheaper than an interpreter session and returning to native ROM code at
 * once, and it is counted (rr_gb_try_ram_dispatch) and reported as such, like
 * the upstream stub. It is checked opcode by opcode against the interpreter
 * (native/gb_ram_checks.c).
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

/* One writable-memory instruction, executed on its own from its live bytes (counted, see
 * rr_gb_try_ram_dispatch).
 *
 * The upstream RAM stub covers a subset of the SM83 opcodes; any other opcode
 * located in WRAM or HRAM (a routine copied from the cartridge and patched, a
 * trampoline) used to start an interpreter session that then kept interpreting
 * the ROM code it jumped to. These are the remaining non-prefixed, non-branch
 * opcodes, written after the pinned interpreter case by case: same helpers,
 * same operand reads, same cycle split. The opcode and its operands are read
 * live at every execution (self-modifying operands are normal), so nothing is
 * cached; the instruction must lie wholly inside WRAM or HRAM, and the HALT
 * bug and WRAM during OAM DMA decline exactly like the upstream stub. HALT,
 * STOP, the CB prefix, RST and the illegal opcodes stay with the reference. */
static inline uint8_t rr_gb_ram_get8(GBContext* ctx, unsigned index) {
    switch (index) {
        case 0: return ctx->b;  case 1: return ctx->c;
        case 2: return ctx->d;  case 3: return ctx->e;
        case 4: return ctx->h;  case 5: return ctx->l;
        default: return ctx->a;
    }
}

static inline void rr_gb_ram_set8(GBContext* ctx, unsigned index, uint8_t value) {
    switch (index) {
        case 0: ctx->b = value; break;  case 1: ctx->c = value; break;
        case 2: ctx->d = value; break;  case 3: ctx->e = value; break;
        case 4: ctx->h = value; break;  case 5: ctx->l = value; break;
        default: ctx->a = value; break;
    }
}

static inline uint8_t rr_gb_ram_final_read8(GBContext* ctx, uint16_t address, uint8_t* cycles) {
    const uint8_t value = gbrt_timed_bus_read8(ctx, address, (uint8_t)(*cycles - 1u));
    *cycles = 0;
    return value;
}

static inline void rr_gb_ram_final_write8(GBContext* ctx, uint16_t address, uint8_t value,
                                          uint8_t* cycles) {
    gbrt_timed_bus_write8(ctx, address, value, (uint8_t)(*cycles - 1u));
    *cycles = 0;
}

static inline void rr_gb_ram_alu8(GBContext* ctx, unsigned operation, uint8_t value) {
    switch (operation) {
        case 0: gb_add8(ctx, value); break;  case 1: gb_adc8(ctx, value); break;
        case 2: gb_sub8(ctx, value); break;  case 3: gb_sbc8(ctx, value); break;
        case 4: gb_and8(ctx, value); break;  case 5: gb_xor8(ctx, value); break;
        case 6: gb_or8(ctx, value); break;   default: gb_cp8(ctx, value); break;
    }
}

/* Length in bytes of an opcode handled here, 0 for the others. */
static inline unsigned rr_gb_ram_length(uint8_t op) {
    if (op == 0x08 || op == 0x01 || op == 0x11 || op == 0x21 || op == 0x31) return 3;
    if (op == 0x36 || op == 0xC6 || op == 0xCE || op == 0xD6 || op == 0xDE ||
        op == 0xE6 || op == 0xEE || op == 0xF6 || op == 0xFE) return 2;
    if (op >= 0x41 && op <= 0xBF && op != 0x76) return 1;
    switch (op) {
        case 0x02: case 0x0A: case 0x12: case 0x1A:
        case 0x03: case 0x13: case 0x23: case 0x33: case 0x0B: case 0x1B: case 0x2B: case 0x3B:
        case 0x09: case 0x19: case 0x29: case 0x39: case 0x34: case 0x35:
        case 0x07: case 0x0F: case 0x17: case 0x1F: case 0x27: case 0x2F: case 0x37: case 0x3F:
        case 0xC1: case 0xD1: case 0xE1: case 0xF1: case 0xC5: case 0xD5: case 0xE5: case 0xF5:
        case 0xF9: case 0xF3: case 0xFB:
            return 1;
        default:
            return 0;
    }
}

static inline uint8_t rr_gb_try_ram_instruction(GBContext* ctx, uint16_t addr) {
    if (!ctx || ctx->halt_bug) return 0;
    const bool wram = addr >= 0xC000 && addr < 0xFE00;
    const bool hram = addr >= 0xFF80 && addr <= 0xFFFE;
    if ((!wram && !hram) || (wram && ctx->dma.active)) return 0;
    const uint8_t op = gb_read8(ctx, addr);
    const unsigned length = rr_gb_ram_length(op);
    if (!length || (wram ? addr + length > 0xFE00u : addr + length > 0xFFFFu)) return 0;
    uint8_t cycles = 4;
    ctx->pc = (uint16_t)(addr + length);
    if (op >= 0x41 && op <= 0x7F) {                 /* LD r,r' / LD r,(HL) / LD (HL),r */
        const unsigned dst = (op >> 3) & 7u, src = op & 7u;
        if (dst == 6) { cycles = 8; rr_gb_ram_final_write8(ctx, ctx->hl, rr_gb_ram_get8(ctx, src), &cycles); }
        else if (src == 6) { cycles = 8; rr_gb_ram_set8(ctx, dst, rr_gb_ram_final_read8(ctx, ctx->hl, &cycles)); }
        else rr_gb_ram_set8(ctx, dst, rr_gb_ram_get8(ctx, src));
    } else if (op >= 0x80 && op <= 0xBF) {          /* ALU A,r / ALU A,(HL) */
        uint8_t value;
        if ((op & 7u) == 6) { cycles = 8; value = rr_gb_ram_final_read8(ctx, ctx->hl, &cycles); }
        else value = rr_gb_ram_get8(ctx, op & 7u);
        rr_gb_ram_alu8(ctx, (op >> 3) & 7u, value);
    } else {
        switch (op) {
        case 0x01: ctx->bc = gb_read16(ctx, (uint16_t)(addr + 1)); cycles = 12; break;
        case 0x11: ctx->de = gb_read16(ctx, (uint16_t)(addr + 1)); cycles = 12; break;
        case 0x21: ctx->hl = gb_read16(ctx, (uint16_t)(addr + 1)); cycles = 12; break;
        case 0x31: ctx->sp = gb_read16(ctx, (uint16_t)(addr + 1)); cycles = 12; break;
        case 0x08: gb_write16(ctx, gb_read16(ctx, (uint16_t)(addr + 1)), ctx->sp); cycles = 20; break;
        case 0xF9: ctx->sp = ctx->hl; cycles = 8; break;
        case 0x02: cycles = 8; rr_gb_ram_final_write8(ctx, ctx->bc, ctx->a, &cycles); break;
        case 0x12: cycles = 8; rr_gb_ram_final_write8(ctx, ctx->de, ctx->a, &cycles); break;
        case 0x0A: cycles = 8; ctx->a = rr_gb_ram_final_read8(ctx, ctx->bc, &cycles); break;
        case 0x1A: cycles = 8; ctx->a = rr_gb_ram_final_read8(ctx, ctx->de, &cycles); break;
        case 0x36: {
            const uint8_t value = gb_read8(ctx, (uint16_t)(addr + 1));
            cycles = 12; rr_gb_ram_final_write8(ctx, ctx->hl, value, &cycles); break;
        }
        case 0x34: case 0x35: {                     /* INC (HL) / DEC (HL) */
            const uint16_t target = ctx->hl;
            uint8_t value = gbrt_timed_bus_read8(ctx, target, 7);
            value = op == 0x34 ? gb_inc8(ctx, value) : gb_dec8(ctx, value);
            gbrt_timed_bus_rmw_write8(ctx, target, value);
            cycles = 0; break;
        }
        case 0x03: gbrt_timed_inc16(ctx, &ctx->bc); cycles = 0; break;
        case 0x13: gbrt_timed_inc16(ctx, &ctx->de); cycles = 0; break;
        case 0x23: gbrt_timed_inc16(ctx, &ctx->hl); cycles = 0; break;
        case 0x33: gbrt_timed_inc16(ctx, &ctx->sp); cycles = 0; break;
        case 0x0B: gbrt_timed_dec16(ctx, &ctx->bc); cycles = 0; break;
        case 0x1B: gbrt_timed_dec16(ctx, &ctx->de); cycles = 0; break;
        case 0x2B: gbrt_timed_dec16(ctx, &ctx->hl); cycles = 0; break;
        case 0x3B: gbrt_timed_dec16(ctx, &ctx->sp); cycles = 0; break;
        case 0x09: gb_add16(ctx, ctx->bc); cycles = 8; break;
        case 0x19: gb_add16(ctx, ctx->de); cycles = 8; break;
        case 0x29: gb_add16(ctx, ctx->hl); cycles = 8; break;
        case 0x39: gb_add16(ctx, ctx->sp); cycles = 8; break;
        case 0x07: gb_rlca(ctx); break;
        case 0x0F: gb_rrca(ctx); break;
        case 0x17: gb_rla(ctx); break;
        case 0x1F: gb_rra(ctx); break;
        case 0x27: gb_daa(ctx); break;
        case 0x2F: ctx->a = (uint8_t)~ctx->a; ctx->f_n = 1; ctx->f_h = 1; break;
        case 0x37: ctx->f_n = 0; ctx->f_h = 0; ctx->f_c = 1; break;
        case 0x3F: ctx->f_n = 0; ctx->f_h = 0; ctx->f_c = !ctx->f_c; break;
        case 0xC6: case 0xCE: case 0xD6: case 0xDE: case 0xE6: case 0xEE: case 0xF6: case 0xFE:
            cycles = 8;
            rr_gb_ram_alu8(ctx, (op >> 3) & 7u, gb_read8(ctx, (uint16_t)(addr + 1)));
            break;
        case 0xC1: ctx->bc = gbrt_timed_pop16(ctx); cycles = 0; break;
        case 0xD1: ctx->de = gbrt_timed_pop16(ctx); cycles = 0; break;
        case 0xE1: ctx->hl = gbrt_timed_pop16(ctx); cycles = 0; break;
        case 0xF1: {
            const uint16_t af = gbrt_timed_pop16(ctx);
            ctx->af = af & 0xFFF0; gb_unpack_flags(ctx); cycles = 0; break;
        }
        case 0xC5: gbrt_timed_push16(ctx, ctx->bc); cycles = 0; break;
        case 0xD5: gbrt_timed_push16(ctx, ctx->de); cycles = 0; break;
        case 0xE5: gbrt_timed_push16(ctx, ctx->hl); cycles = 0; break;
        case 0xF5: gb_pack_flags(ctx); gbrt_timed_push16(ctx, ctx->af & 0xFFF0); cycles = 0; break;
        case 0xF3: ctx->ime = 0; ctx->ime_pending = 0; break;
        case 0xFB: ctx->ime_pending = 1; break;
        default: return 0;
        }
    }
    if (cycles) gb_tick(ctx, cycles);
    return 1;
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

/* The dispatch entry used by the generated game (and by the checks): the guarded multi-instruction
 * helpers, then the upstream RAM stub, then rr_gb_try_ram_instruction. The last two execute one
 * instruction of writable code per call from a per-opcode switch: that is not native code, so every
 * instruction they run is counted, each in its own pair of counters (instructions and guest cycles), and the
 * conversion report shows them beside the interpreter figures (never added to them, never hidden). The counters
 * are host-only fields of the context, outside every saved state. */
static inline uint8_t rr_gb_try_ram_dispatch(GBContext* ctx, uint16_t addr) {
    if (rr_gb_try_store_helper(ctx, addr)) return 1;
    const uint64_t before = ctx ? ctx->total_cycles : 0;
    if (gbrt_try_execute_ram_stub(ctx, addr)) {
        ctx->rr_ram_stub_instructions++;
        ctx->rr_ram_stub_cycles += ctx->total_cycles - before;
        return 1;
    }
    if (rr_gb_try_ram_instruction(ctx, addr)) {
        ctx->rr_ram_single_step_instructions++;
        ctx->rr_ram_single_step_cycles += ctx->total_cycles - before;
        return 1;
    }
    return 0;
}
#endif
