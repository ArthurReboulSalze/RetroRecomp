/* Included in the shared execution wrapper. The two words are guest state;
 * the prepared image/cursor are instruction-local and never serialized.
 * Bus reads use the same suspendable path as operands. No opcode decode is
 * needed by a covered body, including stale prefetched RAM variants. */
#include "md_prefetch.h"
RrMdPrefetch rr_md_prefetch;
static uint32_t rr_pf_image_pc;
static unsigned rr_pf_image_count, rr_pf_pending, rr_pf_before_write, rr_pf_control;
static unsigned rr_pf_control_cycles, rr_pf_condition;
static unsigned rr_pf_image_valid,rr_pf_move,rr_pf_dst_advance,rr_pf_dst_idle;
static uint16_t rr_pf_image[8];
static void rr_pf_cache(void) {
    if(!rr_pf_image_count)return;
    for(unsigned j=0;j<2;++j) {
        unsigned n=((rr_md_prefetch.pc+j*2u-rr_pf_image_pc)&0xffffffu)/2u;
        if(n<rr_pf_image_count && !(rr_pf_image_valid&(1u<<n))) {
            rr_pf_image[n]=rr_md_prefetch.words[j];rr_pf_image_valid|=1u<<n;
        }
    }
}
static void rr_pf_advance(void) {
    rr_pf_cache();
    uint16_t word=rr_md_read_instruction_word((rr_md_prefetch.pc+4u)&0xffffffu);
    rr_md_prefetch.words[0]=rr_md_prefetch.words[1];
    rr_md_prefetch.words[1]=word;
    rr_md_prefetch.pc=(rr_md_prefetch.pc+2u)&0xffffffu;
    rr_pf_cache();
}
void rr_md_prefetch_reset(void) {
    memset(&rr_md_prefetch,0,sizeof rr_md_prefetch);
    rr_pf_image_count=rr_pf_pending=rr_pf_before_write=rr_pf_control=0;
    rr_pf_control_cycles=0;
    rr_pf_image_valid=rr_pf_move=rr_pf_dst_advance=rr_pf_dst_idle=0;
}
static uint16_t rr_pf_live_word(uint32_t pc) {
    pc&=0xffffffu;
    return ((uint16_t)busview_fetch8(pc,NULL)<<8)|busview_fetch8((pc+1u)&0xffffffu,NULL);
}
uint16_t rr_md_instruction_word(uint32_t pc) {
    pc&=0xffffffu;
    if(rr_md_prefetch_active()) {
        unsigned n=((pc-rr_pf_image_pc)&0xffffffu)/2u;
        if(n<rr_pf_image_count && (rr_pf_image_valid&(1u<<n)))return rr_pf_image[n];
        n=((pc-rr_md_prefetch.pc)&0xffffffu)/2u;
        if(n<rr_md_prefetch.valid)return rr_md_prefetch.words[n];
    }
    return rr_pf_live_word(pc);
}
static uint8_t rr_pf_fetch8(uint32_t pc,void *user) {
    (void)user;uint16_t word=rr_md_instruction_word(pc&~1u);
    return (uint8_t)((pc&1u)?word:word>>8);
}
void rr_md_prefetch_target(uint32_t pc) {
    if(!rr_md_prefetch_active())return;
    rr_md_prefetch.pc=pc&0xffffffu;rr_md_prefetch.valid=0;
    rr_md_prefetch.words[0]=rr_md_read_instruction_word(rr_md_prefetch.pc);
    rr_md_prefetch.valid=1;
}
static void rr_pf_fill(void) {
    if(rr_md_prefetch.valid==1) {
        rr_md_prefetch.words[1]=rr_md_read_instruction_word((rr_md_prefetch.pc+2u)&0xffffffu);
        rr_md_prefetch.valid=2;
    }
}
void rr_md_prefetch_refill(uint32_t pc) { rr_md_prefetch_target(pc);rr_pf_fill(); }
static void rr_pf_begin(uint32_t pc) {
    rr_pf_image_count=rr_pf_pending=rr_pf_before_write=rr_pf_control=0;
    rr_pf_control_cycles=0;
    rr_pf_image_valid=rr_pf_move=rr_pf_dst_advance=rr_pf_dst_idle=0;
    rr_md_cpu_fetch_cycles(0,0);
    if(!rr_md_prefetch_active())return;
    pc&=0xffffffu;
    if(rr_md_prefetch.valid!=2 || rr_md_prefetch.pc!=pc) {
        /* Cold reset/legacy states have no queue. Prime it once; these startup
         * reads consume clocks, but are not charged to the following opcode. */
        rr_md_prefetch_target(pc);rr_pf_fill();
        rr_md_cpu_fetch_cycles(0,0);
    }
}
static int rr_pf_is_control(const M68KInstr *ins) {
    switch(ins->mnemonic) {
    case MN_JMP:case MN_JSR:case MN_BRA:case MN_BSR:case MN_Bcc:case MN_DBcc:
    case MN_RTS:case MN_RTE:case MN_RTR:return 1;
    default:return 0;
    }
}
static unsigned rr_pf_ea_idle(int ea) {
    unsigned mode=(ea>>3)&7u,reg=ea&7u;
    return mode==4 || mode==6 || (mode==7 && reg==3)?2u:0u;
}
static unsigned rr_pf_extensions(int ea,M68KSize size) {
    unsigned mode=(ea>>3)&7u,reg=ea&7u;
    return mode==5 || mode==6?1u:mode!=7?0u:reg==1?2u:
        reg==4?(size==M68K_SIZE_L?2u:1u):reg<4?1u:0u;
}
uint16_t rr_md_operand_extension(uint32_t pc,unsigned index,uint16_t original) {
    return rr_md_prefetch_active() && rr_pf_move?
        rr_md_instruction_word(pc+index*2u):original;
}
void rr_md_move_source_done(void) {
    if(!rr_md_prefetch_active() || !rr_pf_move)return;
    if(rr_pf_dst_idle)rr_md_cpu_idle(rr_pf_dst_idle);
    while(rr_pf_dst_advance) { --rr_pf_dst_advance;rr_pf_advance(); }
}
void rr_md_exception_bus_begin(void) {
    if(!rr_md_prefetch_active())return;
    rr_pf_pending=rr_pf_control=0;rr_md_cpu_idle(4);
}
void rr_md_interrupt_entry(unsigned level,uint32_t vector) {
    /* Autovector entry: no host-side frame writes and no extra cold refill.
     * The IACK callback is a CPU-space bus cycle, never a RAM read. */
    uint16_t sr=g_cpu.SR;uint32_t pc=g_cpu.PC;
    rr_pf_image_count=rr_pf_image_valid=rr_pf_pending=rr_pf_control=rr_pf_move=0;
    rr_md_cpu_fetch_cycles(0,0);rr_md_cpu_stopped=0;
    rr_md_set_sr((uint16_t)((sr&~0x8700u)|SR_S|(level<<8)));
    uint32_t sp=g_cpu.A[7];g_cpu.A[7]=sp-6;
    rr_md_cpu_idle(6);
    m68k_write16(sp-2,(uint16_t)pc);
    rr_md_cpu_iack(level);rr_md_cpu_idle(4);
    m68k_write16(sp-6,sr);m68k_write16(sp-4,(uint16_t)(pc>>16));
    g_cpu.PC=m68k_read32(vector)&0xffffffu;
    rr_md_prefetch_target(g_cpu.PC);rr_md_cpu_idle(2);rr_pf_fill();
    unsigned tail=rr_md_cpu_retire_cycles(44);
    if(tail)rr_md_cpu_idle(tail);
    rr_md_cpu_fetch_cycles(0,0);
}
static void rr_pf_prepare(const M68KInstr *ins) {
    if(!rr_md_prefetch_active()) {
        rr_md_cpu_fetch_cycles(ins->mnemonic==MN_STOP?1u:(unsigned)ins->word_count,ins->mnemonic==MN_TAS);
        return;
    }
    rr_pf_image_pc=ins->addr;rr_pf_control=rr_pf_is_control(ins);
    unsigned count=(unsigned)ins->word_count;
    int privilege=!(g_cpu.SR&SR_S) && (ins->mnemonic==MN_STOP || ins->mnemonic==MN_RTE ||
        ins->mnemonic==MN_RESET || ins->mnemonic==MN_MOVE_USP ||
        (ins->mnemonic==MN_MOVE_SR && !ins->dst_is_ea) || ins->mnemonic==MN_ORI_TO_SR ||
        ins->mnemonic==MN_ANDI_TO_SR || ins->mnemonic==MN_EORI_TO_SR);
    if(privilege || ins->mnemonic==MN_ILLEGAL || ins->mnemonic==MN_TRAP) {
        rr_pf_image_count=count;
        for(unsigned i=0;i<count;++i)rr_pf_image[i]=ins->words[i];
        rr_pf_image_valid=(1u<<count)-1u;return;
    }
    if(ins->mnemonic==MN_MOVE || ins->mnemonic==MN_MOVEM) {
        rr_pf_image_count=count;rr_pf_image_valid=0;rr_pf_cache();
        rr_pf_pending=1;rr_pf_before_write=0;
        if(ins->mnemonic==MN_MOVE) {
            rr_pf_move=1;
            unsigned src=rr_pf_extensions(ins->src_ea,ins->size);
            rr_pf_dst_advance=count-1u-src;
            unsigned dm=(ins->dst_ea>>3)&7u;
            unsigned sm=(ins->src_ea>>3)&7u;
            if(ins->dst_ea==0x39 && sm>=2 && ins->src_ea!=0x3c) {
                --rr_pf_dst_advance;rr_pf_pending=2;
            }
            rr_pf_dst_idle=dm==6?2u:0u;
            rr_pf_before_write=dm==4;
            unsigned idle=rr_pf_ea_idle(ins->src_ea);if(idle)rr_md_cpu_idle(idle);
            while(src--)rr_pf_advance();
        } else {
            /* Consume mask first; index calculation follows that stream read. */
            rr_pf_advance();
            unsigned idle=((ins->src_ea>>3)&7u)==6 || ins->src_ea==0x3b?2u:0u;
            if(idle)rr_md_cpu_idle(idle);
            for(unsigned i=2;i<count;++i)rr_pf_advance();
        }
        return;
    }
    unsigned advance=count?count-1u:0;
    if(rr_pf_control || ins->mnemonic==MN_STOP)advance=count>2?count-2u:0;
    /* Address calculation before the first operand transaction. This block
     * qualifies ordinary single-EA operations; multi-EA and MOVEM microphases
     * retain explicit qualification limits. */
    unsigned idle=rr_pf_ea_idle(ins->src_ea);
    if(ins->mnemonic==MN_JMP || ins->mnemonic==MN_JSR) {
        unsigned mode=(ins->src_ea>>3)&7u,reg=ins->src_ea&7u;
        idle=mode==6 || (mode==7 && reg==3)?6u:
             mode==5 || (mode==7 && (reg==0 || reg==2))?2u:0u;
    } else if(ins->mnemonic==MN_BSR)idle=2;
    else if(rr_pf_control || ins->mnemonic==MN_STOP)idle=0;
    if(idle)rr_md_cpu_idle(idle);
    for(unsigned n=0;n<count && n<8;++n) {
        if(n<=advance) {
            rr_pf_image[n]=rr_md_prefetch.words[0];
            if(n<advance)rr_pf_advance();
        } else rr_pf_image[n]=rr_md_prefetch.words[1];
    }
    rr_pf_image_count=count;
    rr_pf_image_valid=(1u<<count)-1u;
    rr_pf_pending=!rr_pf_control && ins->mnemonic!=MN_STOP;
    rr_pf_before_write=ins->mnemonic!=MN_MOVE && ins->mnemonic!=MN_MOVEM && !rr_pf_control;
    if(ins->mnemonic==MN_MOVE && ((ins->dst_ea>>3)&7)==4)rr_pf_before_write=1;
    if(ins->mnemonic==MN_PEA && (ins->src_ea==0x38 || ins->src_ea==0x39))rr_pf_before_write=0;
    if(ins->mnemonic==MN_LEA || ins->mnemonic==MN_PEA) {
        if(rr_pf_ea_idle(ins->src_ea))rr_md_cpu_idle(2);
    }
    rr_pf_condition=eval_cond((ins->words[0]>>8)&15u);
    if(ins->mnemonic==MN_Bcc)rr_pf_control_cycles=rr_pf_condition?10:count==1?8:12;
    if(ins->mnemonic==MN_DBcc)rr_pf_control_cycles=rr_pf_condition?12:
        (g_cpu.D[ins->reg]&0xffffu)?10:14;
    rr_md_cpu_bus_lock(ins->mnemonic==MN_TAS);
}
void rr_md_prefetch_before_write(void) {
    if(rr_md_prefetch_active() && rr_pf_pending && rr_pf_before_write && !rr_md_exception_cycles) {
        rr_pf_pending=0;rr_pf_advance();
    }
}
static void rr_pf_finish(const M68KInstr *ins,uint32_t next) {
    if(!rr_md_prefetch_active())return;
    if(ins->mnemonic==MN_STOP && rr_md_cpu_stopped) {
        rr_md_prefetch.valid=0;rr_pf_pending=0;return;
    }
    if(rr_md_exception_cycles) {
        rr_md_prefetch_target(next);rr_md_cpu_idle(2);rr_pf_fill();rr_pf_pending=0;
    } else if(rr_pf_control) {
        if(ins->mnemonic==MN_Bcc && !rr_pf_condition && ins->word_count==1) {
            rr_md_cpu_idle(4);rr_pf_advance();rr_pf_image_count=0;return;
        }
        if(ins->mnemonic==MN_BRA || ins->mnemonic==MN_Bcc)
            rr_md_cpu_idle(ins->mnemonic==MN_Bcc && !rr_pf_condition?4:2);
        if(ins->mnemonic==MN_DBcc) {
            rr_md_cpu_idle(rr_pf_condition?4:2);
            /* Expiry still fetches and discards the branch target. */
            if(!rr_pf_condition && rr_pf_control_cycles==14)
                (void)rr_md_read_instruction_word(ins->target_addr);
        }
        if(rr_md_prefetch.valid!=1 || rr_md_prefetch.pc!=(next&0xffffffu))rr_md_prefetch_target(next);
        rr_pf_fill();
    } else if(rr_pf_pending) {
        while(rr_pf_pending) {--rr_pf_pending;rr_pf_advance();}
    }
    rr_pf_image_count=0;
}
unsigned rr_md_multiply_clocks(uint16_t source,int is_signed) {
    unsigned bits=is_signed?(source^(source<<1))&0xffffu:source;
    unsigned clocks=38;
    while(bits) {clocks+=2;bits&=bits-1u;}
    return clocks;
}
unsigned rr_md_divide_clocks(uint32_t dividend,uint16_t divisor,int is_signed) {
    if(!divisor)return 38; /* The caller takes vector 5 instead. */
    if(!is_signed) {
        if((dividend>>16)>=divisor)return 10;
        unsigned half=38;uint32_t shifted=(uint32_t)divisor<<16;
        for(unsigned i=0;i<15;++i) {
            uint32_t previous=dividend;dividend<<=1;
            if(previous&0x80000000u)dividend-=shifted;
            else {
                half+=2;
                if(dividend>=shifted) {dividend-=shifted;--half;}
            }
        }
        return half*2;
    }
    /* Use unsigned magnitudes, including INT_MIN/-1. Divisor sign selects
     * equally long setup paths; dividend negation costs two clocks. Late
     * signed-range overflow still pays the full quotient loop. */
    unsigned negative=dividend>>31,negative_src=divisor>>15;
    uint32_t magnitude=negative?0u-dividend:dividend;
    unsigned denominator=negative_src?(0u-divisor)&0xffffu:divisor;
    uint32_t quotient=magnitude/denominator;
    unsigned half=6+negative;
    if(quotient>=0x10000u)return (half+2)*2;
    half+=55;
    if(!negative_src)half=negative?half+1:half-1;
    for(unsigned i=0;i<15;++i) {
        if(!(quotient&0x8000u))++half;
        quotient=(quotient<<1)&0xffffu;
    }
    return half*2;
}
void rr_md_arithmetic_phase(unsigned base,unsigned ea,int multiply) {
    rr_pf_control_cycles=base+ea;
    if(!rr_md_prefetch_active())return;
    /* MUL stream read precedes its internal loop. DIV refills afterwards. */
    if(!multiply)rr_md_cpu_idle(base-4);
    while(rr_pf_pending) {--rr_pf_pending;rr_pf_advance();}
    if(multiply)rr_md_cpu_idle(base-4);
}
