/* Runtime ABI for individually translated ROM instructions. */
#pragma once
#include "m68k_interp.h"
#include "m68k_decoder.h"
#include "md_prefetch.h"
extern uint32_t rr_md_cpu_stopped;
/* Instruction-local cost, consumed before entering the scheduler. It is not
 * guest state and never survives an instruction or an F8/F9 boundary. */
extern unsigned rr_md_exception_cycles;
extern unsigned rr_md_trace_suppressed;

/* Preserve the pinned CPU/snapshot layout: A7 is the active stack and USP
 * holds the inactive stack (USP in supervisor mode, SSP in user mode).
 * MOVE USP is privileged and therefore always sees the actual USP here. */
static inline uint32_t rr_md_user_sp(void) {
    return (g_cpu.SR & SR_S) ? g_cpu.USP : g_cpu.A[7];
}
static inline uint32_t rr_md_supervisor_sp(void) {
    return (g_cpu.SR & SR_S) ? g_cpu.A[7] : g_cpu.USP;
}
static inline void rr_md_set_sr(uint16_t value) {
    if ((g_cpu.SR ^ value) & SR_S) {
        uint32_t previous = g_cpu.A[7];
        g_cpu.A[7] = g_cpu.USP;
        g_cpu.USP = previous;
    }
    g_cpu.SR = value & 0xa71fu;
}
static inline void rr_md_exception_frame(uint16_t saved_sr, uint32_t pc,
                                         uint16_t handler_sr) {
    rr_md_cpu_stopped = 0; /* An accepted exception wakes STOP. */
    rr_md_set_sr(handler_sr); /* Select SSP before the first stack write. */
    /* MC68000 normal frame bus order: PC low, SR, PC high. */
    uint32_t sp=g_cpu.A[7];g_cpu.A[7]=sp-6;
    m68k_write16(sp-2,(uint16_t)pc);
    m68k_write16(sp-6,saved_sr);
    m68k_write16(sp-4,(uint16_t)(pc>>16));
}
static inline M68kiStatus rr_md_instruction_exception(uint32_t *next_pc,
        unsigned vector, uint32_t saved_pc, unsigned cycles) {
    uint16_t saved_sr = g_cpu.SR;
    rr_md_exception_cycles = cycles;
    rr_md_exception_bus_begin();
    rr_md_exception_frame(saved_sr, saved_pc,
                         (uint16_t)((saved_sr & ~0x8000u) | SR_S));
    *next_pc = m68k_read32(vector * 4u);
    /* These instructions did not execute; no post-instruction trace. */
    rr_md_trace_suppressed = vector == 4 || vector == 8 || vector == 10 || vector == 11;
    return M68KI_OK;
}
typedef struct {
    M68KInstr instruction;
    unsigned cycles;
    M68kiStatus (*execute)(uint32_t *next_pc);
} RrMdNativeStep;
const RrMdNativeStep *rr_md_native_lookup(uint32_t pc);
/* These keys address immutable physical ROM bytes, not the mapped guest PC. */
extern uint32_t rr_md_rom_fetch_offset;
uint32_t rr_md_cart_rom_offset(uint32_t pc);
uint32_t rr_md_cart_code_offset(uint32_t pc,const uint16_t *words,unsigned count);
/* Relocate a guarded RAM body without decoding its opcode or replacing the
 * architectural PC with a preferred alias. Absolute targets stay absolute. */
static inline void rr_md_relocate_instruction(M68KInstr *ins, uint32_t pc) {
    if (ins->mnemonic == MN_BRA || ins->mnemonic == MN_BSR ||
        ins->mnemonic == MN_Bcc || ins->mnemonic == MN_DBcc)
        ins->target_addr = (ins->target_addr + pc - ins->addr) & 0xffffffu;
    ins->addr = pc;
}
extern int rr_md_illegal_ea;
void rr16_note_rom_fallback(uint32_t pc);
void rr16_note_ram_instruction(const M68KInstr *instruction);

/* An instruction can start anywhere in work RAM, including the final word.
 * Guard its actual extent, not the maximum possible instruction size. Keep
 * cross-bus-boundary fetches on the reference path until supported explicitly. */
static inline int rr_md_ram_instruction_recordable(const M68KInstr *ins) {
    return ins->addr >= 0xe00000u && ins->addr <= 0xfffffeu && !(ins->addr & 1u)
        && ins->word_count >= 1 && ins->word_count <= 8
        && ins->byte_length == (unsigned)ins->word_count * 2u
        && ins->byte_length <= 0x1000000u - ins->addr;
}
