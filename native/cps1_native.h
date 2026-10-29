/* CPS-1 MC68000 instruction AOT. Musashi (the reference) owns the canonical
 * scheduling state; translated bodies use the same qualified architectural
 * ABI as the Neo Geo and Mega Drive. No guest opcode decoder runs on a covered
 * path. Adapted from native/neogeo_native.h (Retro-Recomp, MIT). */
#ifndef RR_CPS1_NATIVE_H
#define RR_CPS1_NATIVE_H
#include <stdint.h>
#include "m68k_decoder.h"
#include "m68000_state_helpers.h"
typedef struct { uint32_t D[8], A[8]; uint16_t SR; uint32_t PC, USP; } M68KState;
extern M68KState g_cpu;
typedef enum { M68KI_OK, M68KI_HALT_UNIMPL, M68KI_HALT_GUARD, M68KI_HALT_BADADDR } M68kiStatus;
#define SR_C 1u
#define SR_V 2u
#define SR_Z 4u
#define SR_N 8u
#define SR_X 16u
#define SR_S 0x2000u
uint8_t m68k_read8(uint32_t);
uint16_t m68k_read16(uint32_t);
uint32_t m68k_read32(uint32_t);
void m68k_write8(uint32_t,uint8_t);
void m68k_write16(uint32_t,uint16_t);
void m68k_write32(uint32_t,uint32_t);
static inline uint32_t m68k_brief_index_value(uint16_t ext,uint32_t d,uint32_t a) {
    uint32_t v=ext&0x8000u?a:d;return ext&0x800u?v:(uint32_t)(int32_t)(int16_t)v;
}
extern uint32_t rr_cps1_cpu_stopped,g_m68ki_bad_pc;
extern uint16_t g_m68ki_bad_op;
extern unsigned rr_cps1_exception_cycles,rr_cps1_trace_suppressed,rr_cps1_arithmetic_cycles;
extern int rr_cps1_illegal_ea,g_rte_pending;
extern int rr_cps1_force_reference;
void rr_cps1_set_sr(uint16_t);
M68kiStatus rr_cps1_instruction_exception(uint32_t*,unsigned,uint32_t,unsigned);
/* Instruction-boundary schedule with prefetch disabled, as the reference. */
static inline uint16_t rr_cps1_operand_extension(uint32_t pc,unsigned index,uint16_t original) {
    (void)pc;(void)index;return original;
}
static inline void rr_cps1_move_source_done(void) {}
static inline void rr_cps1_prefetch_target(uint32_t pc) {(void)pc;}
static inline int rr_cps1_prefetch_active(void) {return 0;}
static inline void rr_cps1_cpu_idle(unsigned clocks) {(void)clocks;}
unsigned rr_cps1_multiply_clocks(uint16_t,int);
unsigned rr_cps1_divide_clocks(uint32_t,uint16_t,int);
void rr_cps1_arithmetic_phase(unsigned,unsigned,int);
/* The reference keeps all 32 PC bits after a jump through a pointer whose
 * high byte carries a flag; return addresses and branch targets keep them
 * (same rule as native/neogeo_native.h; code lookups mask to 24 bits). */
static inline void rr_cps1_relocate_instruction(M68KInstr *ins,uint32_t pc) {
    if(ins->mnemonic==MN_BRA || ins->mnemonic==MN_BSR ||
       ins->mnemonic==MN_Bcc || ins->mnemonic==MN_DBcc)
        ins->target_addr=(pc&0xff000000u)|((ins->target_addr+pc-ins->addr)&0xffffffu);
    ins->addr=pc;
}
typedef struct { M68KInstr instruction; M68kiStatus (*execute)(const M68KInstr*,uint32_t*); } RrCps1NativeStep;
enum { RR_CPS1_CODE_ROM=1, RR_CPS1_CODE_RAM=3, RR_CPS1_CODE_GFX=4 };
const RrCps1NativeStep *rr_cps1_native_lookup(uint32_t region,uint32_t offset);
const RrCps1NativeStep *rr_cps1_ram_native_lookup(uint32_t pc,uint32_t offset,unsigned available);
const RrCps1NativeStep *rr_cps1_gfx_native_lookup(uint32_t pc,uint32_t offset,unsigned available);
/* Board code view: mapping and host bytes (big-endian words) of a PC. */
const uint8_t *rr_cps1_code_bytes(uint32_t address,uint32_t *region,uint32_t *offset,unsigned *available);
int rr_cps1_code_word(uint32_t pc,uint16_t *word);
int rr_cps1_native_run(void);
void rr_cps1_note_instruction(uint32_t pc,int native);
#endif
