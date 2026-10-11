/* MC68000 instruction stream, independent of the native body dispatcher. */
#pragma once
#include <stdint.h>
typedef struct RrMdPrefetch {
    uint32_t pc, valid;
    uint16_t words[2];
} RrMdPrefetch;
extern RrMdPrefetch rr_md_prefetch;
int rr_md_prefetch_active(void);
void rr_md_cpu_idle(unsigned clocks);
void rr_md_cpu_bus_lock(int locked);
void rr_md_prefetch_reset(void);
uint16_t rr_md_instruction_word(uint32_t pc);
void rr_md_prefetch_before_write(void);
void rr_md_prefetch_target(uint32_t pc);
void rr_md_prefetch_refill(uint32_t pc);
uint16_t rr_md_read_instruction_word(uint32_t pc);
/* MOVE extensions are consumed around the source operand, not all at decode. */
uint16_t rr_md_operand_extension(uint32_t pc,unsigned index,uint16_t original);
void rr_md_move_source_done(void);
void rr_md_exception_bus_begin(void);
void rr_md_interrupt_entry(unsigned level,uint32_t vector);
void rr_md_cpu_iack(unsigned level);
/* Runtime operands affect cost, without decoding or interpreting the opcode. */
unsigned rr_md_multiply_clocks(uint16_t source,int is_signed);
unsigned rr_md_divide_clocks(uint32_t dividend,uint16_t divisor,int is_signed);
void rr_md_arithmetic_phase(unsigned base,unsigned ea,int multiply);
