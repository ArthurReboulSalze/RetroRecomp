/* Neo Geo instruction AOT. The reference scheduler owns the canonical state;
 * translated bodies use the same qualified architectural ABI as Mega Drive.
 * No guest opcode decoder is called on a covered execution path. */
#ifndef RR_NEOGEO_NATIVE_H
#define RR_NEOGEO_NATIVE_H
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
extern uint32_t rr_ng_cpu_stopped,g_m68ki_bad_pc;
extern uint16_t g_m68ki_bad_op;
extern unsigned rr_ng_exception_cycles,rr_ng_trace_suppressed,rr_ng_arithmetic_cycles;
extern int rr_ng_illegal_ea,g_rte_pending;
extern int rr_ng_force_reference;
void rr_ng_set_sr(uint16_t);
M68kiStatus rr_ng_instruction_exception(uint32_t*,unsigned,uint32_t,unsigned);
/* This initial Neo Geo profile uses Geolith's instruction-boundary schedule,
 * with prefetch disabled. Extensions are real board reads made once before
 * the native body; these hooks do not pretend to model sub-instruction phases. */
static inline uint16_t rr_ng_operand_extension(uint32_t pc,unsigned index,uint16_t original) {
    (void)pc;(void)index;return original;
}
static inline void rr_ng_move_source_done(void) {}
static inline void rr_ng_prefetch_target(uint32_t pc) {(void)pc;}
static inline int rr_ng_prefetch_active(void) {return 0;}
static inline void rr_ng_cpu_idle(unsigned clocks) {(void)clocks;}
unsigned rr_ng_multiply_clocks(uint16_t,int);
unsigned rr_ng_divide_clocks(uint32_t,uint16_t,int);
void rr_ng_arithmetic_phase(unsigned,unsigned,int);
/* The reference keeps all 32 PC bits after a jump through a pointer whose
 * high byte carries a flag; return addresses and branch targets keep them. */
static inline void rr_ng_relocate_instruction(M68KInstr *ins,uint32_t pc) {
    if(ins->mnemonic==MN_BRA || ins->mnemonic==MN_BSR ||
       ins->mnemonic==MN_Bcc || ins->mnemonic==MN_DBcc)
        ins->target_addr=(pc&0xff000000u)|((ins->target_addr+pc-ins->addr)&0xffffffu);
    ins->addr=pc;
}
typedef struct { M68KInstr instruction; M68kiStatus (*execute)(const M68KInstr*,uint32_t*); } RrNgNativeStep;
const RrNgNativeStep *rr_ng_native_lookup(uint32_t region,uint32_t offset);
const RrNgNativeStep *rr_ng_ram_native_lookup(uint32_t pc,uint32_t offset,unsigned available);
/* Called before opcode fetch. Return 0 only before changing guest state/bus. */
int rr_ng_native_execute(uint32_t pc,unsigned *clocks);
void rr_ng_note_instruction(uint32_t pc,int native);
int rr_ng_code_word(uint32_t pc,uint16_t *word);
void rr_ng_native_bind(void);
#endif
