/* CPS-1 native MC68000 run inside Musashi's execute loop. Adapted from
 * native/neogeo_native.c (Retro-Recomp, MIT): same chained run, cycle table
 * and SR/interrupt boundaries, so retired clocks equal the reference's. */
#include <stdio.h>
#include <stdlib.h>
#include "m68k.h"
#include "m68kcpu.h"
#include "cps1_step_semantics.h"
M68KState g_cpu;
uint32_t rr_cps1_cpu_stopped,g_m68ki_bad_pc;
uint16_t g_m68ki_bad_op;
unsigned rr_cps1_exception_cycles,rr_cps1_trace_suppressed,rr_cps1_arithmetic_cycles;
int rr_cps1_illegal_ea,g_rte_pending;
int rr_cps1_force_reference;
uint64_t rr_cps1_native_instructions,rr_cps1_interpreted_instructions;
uint8_t m68k_read8(uint32_t a) {return (uint8_t)m68k_read_memory_8(a&0xffffffu);}
uint16_t m68k_read16(uint32_t a) {return (uint16_t)m68k_read_memory_16(a&0xffffffu);}
uint32_t m68k_read32(uint32_t a) {return ((uint32_t)m68k_read16(a)<<16)|m68k_read16(a+2);}
void m68k_write8(uint32_t a,uint8_t v) {m68k_write_memory_8(a&0xffffffu,v);}
void m68k_write16(uint32_t a,uint16_t v) {m68k_write_memory_16(a&0xffffffu,v);}
void m68k_write32(uint32_t a,uint32_t v) {m68k_write16(a,(uint16_t)(v>>16));m68k_write16(a+2,(uint16_t)v);}
/* D/A registers are Musashi's own; g_cpu keeps SR, PC and the inactive
 * stack pointer while native instructions run. */
void rr_cps1_set_sr(uint16_t value) {rr_m68000_select_sr(&g_cpu.SR,&REG_A[7],&g_cpu.USP,value);}
M68kiStatus rr_cps1_instruction_exception(uint32_t *next_pc,unsigned vector,uint32_t saved_pc,unsigned cycles) {
    uint16_t sr=g_cpu.SR;rr_cps1_exception_cycles=cycles;rr_cps1_cpu_stopped=0;
    rr_cps1_set_sr((uint16_t)((sr&~0x8000u)|SR_S));
    rr_m68000_push_normal_frame(&REG_A[7],sr,saved_pc,m68k_write16);
    *next_pc=m68k_read32(vector*4u);
    rr_cps1_trace_suppressed=vector==4 || vector==8 || vector==10 || vector==11;
    return M68KI_OK;
}
/* Musashi's clock table and its data-dependent forms, never a decoder. */
static unsigned dynamic_cycles(const M68KInstr *ins) {
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
/* Mapping, lookup and complete word guard from one board view. */
static const RrCps1NativeStep *guarded_step(uint32_t pc) {
    uint32_t region,offset;unsigned available;
    const uint8_t *code=rr_cps1_code_bytes(pc,&region,&offset,&available);
    if(!code)return NULL;
    const RrCps1NativeStep *op=region==RR_CPS1_CODE_RAM?rr_cps1_ram_native_lookup(pc,offset,available):
                               region==RR_CPS1_CODE_GFX?rr_cps1_gfx_native_lookup(pc,offset,available):
                                                       rr_cps1_native_lookup(region,offset);
    if(!op || op->instruction.byte_length>available)return NULL;
    for(unsigned n=0;n<(unsigned)op->instruction.word_count;++n)
        if((uint16_t)((code[2*n]<<8)|code[2*n+1])!=op->instruction.words[n])return NULL;
    return op;
}
static uint32_t miss_pc=UINT32_MAX;
/* A loaded state never inherits the last run's failed lookup. */
void rr_cps1_native_discontinuity(void) {miss_pc=UINT32_MAX;}
int rr_cps1_trace_native;   /* diagnostic builds: hook every chained instruction */
int rr_cps1_native_run(void) {
    uint32_t pc=REG_PC;
    /* A run that stopped on an unguarded successor already looked it up. */
    if(pc==miss_pc){miss_pc=UINT32_MAX;return 0;}
    miss_pc=UINT32_MAX;
    if(rr_cps1_force_reference)return 0;
    const RrCps1NativeStep *op=guarded_step(pc);
    if(!op)return 0;
    const int chain=!FLAG_T1;
    const uint16_t mask=(uint16_t)CPU_SR_MASK;
    g_cpu.SR=(uint16_t)m68ki_get_sr();
    const uint16_t system=g_cpu.SR&0xff00u;
    uint32_t *other=FLAG_S?&REG_USP:&REG_ISP;
    g_cpu.USP=*other;
    for(;;) {
        g_cpu.PC=pc;
        rr_cps1_cpu_stopped=0;rr_cps1_exception_cycles=rr_cps1_trace_suppressed=rr_cps1_arithmetic_cycles=0;
        rr_cps1_illegal_ea=g_rte_pending=0;
        unsigned cost=dynamic_cycles(&op->instruction);
        REG_PC=pc+op->instruction.byte_length;REG_IR=op->instruction.words[0];
        uint32_t next_pc=pc+op->instruction.byte_length;
        M68kiStatus status=op->execute(&op->instruction,&next_pc);
        if(status!=M68KI_OK || rr_cps1_illegal_ea) {
            fprintf(stderr,"Native MC68000 failed at %06x / %04x: %u\n",pc,REG_IR,(unsigned)status);exit(4);
        }
        ++rr_cps1_native_instructions;
        const int mn=op->instruction.mnemonic;
        if(rr_cps1_exception_cycles || rr_cps1_cpu_stopped || rr_cps1_trace_suppressed ||
           (g_cpu.SR&0xff00u)!=system || mn==MN_MOVE_SR || mn==MN_RTE || mn==MN_STOP ||
           mn==MN_ORI_TO_SR || mn==MN_ANDI_TO_SR || mn==MN_EORI_TO_SR) {
            m68ki_set_sr_noint_nosp(g_cpu.SR);
            if(FLAG_S)REG_USP=g_cpu.USP;else REG_ISP=g_cpu.USP;
            REG_PC=next_pc;
            if(rr_cps1_cpu_stopped)CPU_STOPPED|=STOP_LEVEL_STOP;
            if(rr_cps1_trace_suppressed)m68ki_clear_trace();
            unsigned clocks=rr_cps1_exception_cycles?rr_cps1_exception_cycles:rr_cps1_arithmetic_cycles?rr_cps1_arithmetic_cycles:cost;
            /* The reference takes an already asserted interrupt inside these
             * SR writes, before the instruction's clocks are charged. */
            switch(mn) {
            case MN_MOVE_SR:if(!op->instruction.dst_is_ea)m68ki_check_interrupts();break;
            case MN_RTE:case MN_STOP:case MN_ORI_TO_SR:case MN_ANDI_TO_SR:case MN_EORI_TO_SR:
                m68ki_check_interrupts();break;
            default:break;
            }
            USE_CYCLES(clocks);
            break;
        }
        g_cpu.SR&=mask;
        *other=g_cpu.USP;
        REG_PC=next_pc;
        USE_CYCLES(rr_cps1_arithmetic_cycles?rr_cps1_arithmetic_cycles:cost);
        if(!chain || GET_CYCLES()<=0) {m68ki_set_sr_noint_nosp(g_cpu.SR);break;}
        pc=next_pc;
        op=guarded_step(pc);
        if(!op) {m68ki_set_sr_noint_nosp(g_cpu.SR);miss_pc=pc;break;}
        if(rr_cps1_trace_native) {m68ki_set_sr_noint_nosp(g_cpu.SR);m68ki_instr_hook(pc);}
        REG_PPC=pc;
    }
    return 1;
}
