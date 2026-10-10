/* Runtime ABI for individually translated ROM instructions. */
#pragma once
#include "m68k_interp.h"
#include "m68k_decoder.h"
extern uint32_t rr_md_cpu_stopped;

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
    g_cpu.A[7] -= 4; m68k_write32(g_cpu.A[7], pc);
    g_cpu.A[7] -= 2; m68k_write16(g_cpu.A[7], saved_sr);
}
typedef struct {
    M68KInstr instruction;
    unsigned cycles;
    M68kiStatus (*execute)(uint32_t *next_pc);
} RrMdNativeStep;
const RrMdNativeStep *rr_md_native_lookup(uint32_t pc);
extern int rr_md_illegal_ea;
void rr16_note_rom_fallback(uint32_t pc);
void rr16_note_ram_instruction(const M68KInstr *instruction);

/* An instruction can start anywhere in work RAM, including the final word.
 * Guard its actual extent, not the maximum possible instruction size. Keep
 * cross-bus-boundary fetches on the reference path until supported explicitly. */
static inline int rr_md_ram_instruction_recordable(const M68KInstr *ins) {
    return ins->addr >= 0xff0000u && ins->addr <= 0xfffffeu && !(ins->addr & 1u)
        && ins->word_count >= 1 && ins->word_count <= 8
        && ins->byte_length == (unsigned)ins->word_count * 2u
        && ins->byte_length <= 0x1000000u - ins->addr;
}
