/* Native MC68000 semantic adapter, retaining Geolith's canonical scheduling
 * state for interrupts, reset and later state serialization. Original: MIT. */
#include <stdio.h>
#include <stdlib.h>
#include "m68k/m68kcpu.h"
#include "neogeo_reference.h"
#include "ng_step_semantics.h"
M68KState g_cpu;
uint32_t rr_ng_cpu_stopped,g_m68ki_bad_pc;
uint16_t g_m68ki_bad_op;
unsigned rr_ng_exception_cycles,rr_ng_trace_suppressed,rr_ng_arithmetic_cycles;
int rr_ng_illegal_ea,g_rte_pending;
int rr_ng_force_reference;
uint8_t m68k_read8(uint32_t a) {return (uint8_t)m68k_read_memory_8(a&0xffffffu);}
uint16_t m68k_read16(uint32_t a) {return (uint16_t)m68k_read_memory_16(a&0xffffffu);}
uint32_t m68k_read32(uint32_t a) {return ((uint32_t)m68k_read16(a)<<16)|m68k_read16(a+2);}
void m68k_write8(uint32_t a,uint8_t v) {m68k_write_memory_8(a&0xffffffu,v);}
void m68k_write16(uint32_t a,uint16_t v) {m68k_write_memory_16(a&0xffffffu,v);}
void m68k_write32(uint32_t a,uint32_t v) {m68k_write16(a,(uint16_t)(v>>16));m68k_write16(a+2,(uint16_t)v);}
/* Data and address registers are Musashi's own; g_cpu keeps SR, PC and the
 * inactive stack pointer while a native instruction runs. */
void rr_ng_set_sr(uint16_t value) {rr_m68000_select_sr(&g_cpu.SR,&REG_A[7],&g_cpu.USP,value);}
M68kiStatus rr_ng_instruction_exception(uint32_t *next_pc,unsigned vector,uint32_t saved_pc,unsigned cycles) {
    uint16_t sr=g_cpu.SR;rr_ng_exception_cycles=cycles;rr_ng_cpu_stopped=0;
    rr_ng_set_sr((uint16_t)((sr&~0x8000u)|SR_S));
    rr_m68000_push_normal_frame(&REG_A[7],sr,saved_pc,m68k_write16);
    *next_pc=m68k_read32(vector*4u);
    rr_ng_trace_suppressed=vector==4 || vector==8 || vector==10 || vector==11;
    return M68KI_OK;
}
static unsigned dynamic_cycles(const M68KInstr *ins) {
    /* Keep this prototype's board scheduler on its existing 68000 clock
     * table. Looking up the fixed cost is not opcode execution/decoding.
     * Operand-dependent costs use the qualified shared arithmetic helpers. */
    unsigned op=ins->words[0],base=CYC_INSTRUCTION[op];
    switch(ins->mnemonic) {
    case MN_Bcc:return eval_cond((op>>8)&15)?10:ins->word_count==1?8:12;
    case MN_DBcc:return eval_cond((op>>8)&15)?12:(uint16_t)REG_D[op&7]==0?14:10;
    case MN_Scc:if(((ins->src_ea>>3)&7)==0)return eval_cond((op>>8)&15)?6:4;break;
    case MN_MOVEM:return base+(ins->size==M68K_SIZE_L?8u:4u)*(unsigned)interp_popcount16(ins->words[1]);
    case MN_BSET:case MN_BCLR:case MN_BCHG:
        if(((ins->src_ea>>3)&7)==0) {
            unsigned bit=ins->reg<0?ins->imm32:REG_D[ins->reg];
            if((bit&31u)<16u)return base-2u;
        }
        break;
    case MN_ASL:case MN_ASR:case MN_LSL:case MN_LSR:case MN_ROL:case MN_ROR:case MN_ROXL:case MN_ROXR:
        if(!ins->mem_shift) {
            unsigned count=op&0x20u?REG_D[(op>>9)&7]&63u:(op>>9)&7u;
            if(!(op&0x20u) && !count)count=8;
            return (ins->size==M68K_SIZE_L?8:6)+2*count;
        }
        break;
    default:break;
    }
    return base;
}
int rr_ng_native_execute(uint32_t pc,unsigned *clocks) {
    RrM68000CodeLocation location;
    if(rr_ng_force_reference || !rr_ng_code_location(pc,&location))return 0;
    const RrNgNativeStep *op;
    if(location.region==RR_M68000_CODE_RAM)
        op=rr_ng_ram_native_lookup(pc,location.physical_offset,location.available_bytes);
    else {
        if(location.mutable_code)return 0;
        op=rr_ng_native_lookup(location.region,location.physical_offset);
    }
    if(!op || op->instruction.byte_length>location.available_bytes)return 0;
    if(!rr_ng_code_matches(&location,op->instruction.words,op->instruction.word_count))return 0;
    g_cpu.PC=pc;g_cpu.SR=(uint16_t)m68ki_get_sr();g_cpu.USP=FLAG_S?REG_USP:REG_ISP;
    rr_ng_cpu_stopped=0;rr_ng_exception_cycles=rr_ng_trace_suppressed=rr_ng_arithmetic_cycles=0;
    rr_ng_illegal_ea=g_rte_pending=0;
    unsigned cost=dynamic_cycles(&op->instruction);
    /* Real instruction fetches retain board wait accounting. The guards above
     * are side-effect-free; no IO access is replayed on a dispatch miss. */
    for(unsigned n=0;n<(unsigned)op->instruction.word_count;++n) {
        unsigned word=m68ki_read_imm_16();if(!n)REG_IR=word;
    }
    uint32_t next_pc=pc+op->instruction.byte_length;
    M68kiStatus status=op->execute(&op->instruction,&next_pc);
    if(status!=M68KI_OK || rr_ng_illegal_ea) {
        fprintf(stderr,"Native MC68000 failed at %06x / %04x: %u\n",pc,REG_IR,(unsigned)status);exit(4);
    }
    m68ki_set_sr_noint_nosp(g_cpu.SR);
    if(FLAG_S)REG_USP=g_cpu.USP;else REG_ISP=g_cpu.USP;
    REG_PC=next_pc;
    if(rr_ng_cpu_stopped)CPU_STOPPED|=STOP_LEVEL_STOP;
    if(rr_ng_trace_suppressed)m68ki_clear_trace();
    *clocks=rr_ng_exception_cycles?rr_ng_exception_cycles:rr_ng_arithmetic_cycles?rr_ng_arithmetic_cycles:cost;
    /* The reference checks an already asserted interrupt after a privileged
     * SR change, including RTE. Preserve that entry boundary and its cycles. */
    switch(op->instruction.mnemonic) {
    case MN_MOVE_SR:if(!op->instruction.dst_is_ea)m68ki_check_interrupts();break;
    case MN_RTE:case MN_STOP:case MN_ORI_TO_SR:case MN_ANDI_TO_SR:case MN_EORI_TO_SR:
        m68ki_check_interrupts();break;
    default:break;
    }
    rr_ng_note_instruction(pc,1);return 1;
}
void rr_ng_native_bind(void) {rr_ng_reference_bind();}
/* Chained native run, used by the Neo Geo dispatch (the single step above
 * stays for X68000 generation). Consecutive guarded instructions execute in
 * one call while the system byte of SR is unchanged. Between two instructions
 * Musashi's loop only calls the instruction hook (observation builds) and
 * records REG_PPC; interrupts are still sampled at slice ends and after
 * privileged SR changes, as before. Program words are not read again: the
 * board charges the same fetch wait clocks for the guarded words. */
const uint8_t *rr_ng_code_bytes(uint32_t address,RrM68000CodeLocation *location,unsigned *word_waits);
static uint32_t rr_ng_miss_pc=UINT32_MAX;
/* The same mapping, lookup and complete word guard as rr_ng_native_execute,
 * from one board view; words compare as big-endian bytes (read16). */
static const RrNgNativeStep *guarded_step(uint32_t pc,unsigned *word_waits) {
    RrM68000CodeLocation location;
    const uint8_t *code=rr_ng_code_bytes(pc,&location,word_waits);
    if(!code)return NULL;
    const RrNgNativeStep *op;
    if(location.region==RR_M68000_CODE_RAM)
        op=rr_ng_ram_native_lookup(pc,location.physical_offset,location.available_bytes);
    else {
        if(location.mutable_code)return NULL;
        op=rr_ng_native_lookup(location.region,location.physical_offset);
    }
    if(!op || op->instruction.byte_length>location.available_bytes)return NULL;
    for(unsigned n=0;n<(unsigned)op->instruction.word_count;++n)
        if((uint16_t)((code[2*n]<<8)|code[2*n+1])!=op->instruction.words[n])return NULL;
    return op;
}
int rr_ng_native_run(void) {
    uint32_t pc=REG_PC;
    /* A run that stopped on an unguarded successor already looked it up. */
    if(pc==rr_ng_miss_pc){rr_ng_miss_pc=UINT32_MAX;return 0;}
    rr_ng_miss_pc=UINT32_MAX;
    if(rr_ng_force_reference)return 0;
    unsigned word_waits;
    const RrNgNativeStep *op=guarded_step(pc,&word_waits);
    if(!op)return 0;
    const int chain=!FLAG_T1;
    const uint16_t mask=(uint16_t)CPU_SR_MASK;
    g_cpu.SR=(uint16_t)m68ki_get_sr();
    const uint16_t system=g_cpu.SR&0xff00u;
    uint32_t *other=FLAG_S?&REG_USP:&REG_ISP;
    g_cpu.USP=*other;
    unsigned count=0;
    for(;;) {
        g_cpu.PC=pc;
        rr_ng_cpu_stopped=0;rr_ng_exception_cycles=rr_ng_trace_suppressed=rr_ng_arithmetic_cycles=0;
        rr_ng_illegal_ea=g_rte_pending=0;
        unsigned cost=dynamic_cycles(&op->instruction);
        if(word_waits)rr_m68000_wait((int)(word_waits*(unsigned)op->instruction.word_count));
        REG_PC=pc+op->instruction.byte_length;REG_IR=op->instruction.words[0];
        uint32_t next_pc=pc+op->instruction.byte_length;
        M68kiStatus status=op->execute(&op->instruction,&next_pc);
        if(status!=M68KI_OK || rr_ng_illegal_ea) {
            fprintf(stderr,"Native MC68000 failed at %06x / %04x: %u\n",pc,REG_IR,(unsigned)status);exit(4);
        }
        ++count;
        const int mn=op->instruction.mnemonic;
        if(rr_ng_exception_cycles || rr_ng_cpu_stopped || rr_ng_trace_suppressed ||
           (g_cpu.SR&0xff00u)!=system || mn==MN_MOVE_SR || mn==MN_RTE || mn==MN_STOP ||
           mn==MN_ORI_TO_SR || mn==MN_ANDI_TO_SR || mn==MN_EORI_TO_SR) {
            /* The single-instruction exit, unchanged; it ends the run. */
            m68ki_set_sr_noint_nosp(g_cpu.SR);
            if(FLAG_S)REG_USP=g_cpu.USP;else REG_ISP=g_cpu.USP;
            REG_PC=next_pc;
            if(rr_ng_cpu_stopped)CPU_STOPPED|=STOP_LEVEL_STOP;
            if(rr_ng_trace_suppressed)m68ki_clear_trace();
            unsigned clocks=rr_ng_exception_cycles?rr_ng_exception_cycles:rr_ng_arithmetic_cycles?rr_ng_arithmetic_cycles:cost;
            switch(mn) {
            case MN_MOVE_SR:if(!op->instruction.dst_is_ea)m68ki_check_interrupts();break;
            case MN_RTE:case MN_STOP:case MN_ORI_TO_SR:case MN_ANDI_TO_SR:case MN_EORI_TO_SR:
                m68ki_check_interrupts();break;
            default:break;
            }
            USE_CYCLES(clocks);
            break;
        }
        /* Musashi keeps only the implemented SR bits between instructions. */
        g_cpu.SR&=mask;
        *other=g_cpu.USP;
        REG_PC=next_pc;
        USE_CYCLES(rr_ng_arithmetic_cycles?rr_ng_arithmetic_cycles:cost);
        if(!chain || GET_CYCLES()<=0) {m68ki_set_sr_noint_nosp(g_cpu.SR);break;}
        pc=next_pc;
        op=guarded_step(pc,&word_waits);
        if(!op) {m68ki_set_sr_noint_nosp(g_cpu.SR);rr_ng_miss_pc=pc;break;}
        /* Observation builds see every instruction with the CPU state as
         * Musashi's loop presents it. */
        if(rr_ng_observations) {m68ki_set_sr_noint_nosp(g_cpu.SR);m68ki_instr_hook(pc);}
        REG_PPC=pc;
    }
    rr_m68000_count_native(count);
    return 1;
}
