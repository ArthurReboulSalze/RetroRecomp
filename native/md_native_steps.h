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
