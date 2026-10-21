/* Original authored CPU/RAM guard checks. Never run during gameplay. MIT. */
#include "cpu.h"
#include "observe.h"
#include "m68kcpu.h"
#ifdef RR_X68000_BASE74
#include "memory.h"
#else
#include "x68k/x68kmemory.h"
#endif
#include <string.h>
static void raw_word(uint32_t pc,uint16_t word) {
    uint8_t *bytes=MEM;
    if(pc>=0xe00000u&&pc<0xe80000u){bytes=TVRAM;pc-=0xe00000u;}
    else if(pc>=0xea0000u&&pc<0xea2000u){bytes=SCSIIPL;pc-=0xea0000u;}
#ifdef MSB_FIRST
    bytes[pc]=(uint8_t)(word>>8);bytes[pc+1]=(uint8_t)word;
#else
    bytes[pc+1]=(uint8_t)(word>>8);bytes[pc]=(uint8_t)word;
#endif
}
static int paired(uint32_t pc,uint16_t sr,unsigned budget,int twice) {
    extern int m68ki_initial_cycles;
    m68ki_cpu_core start=m68ki_cpu;
    uint8_t stack[64],after[64];uint32_t first[18],second[18];
    memcpy(stack,MEM+0xbffec0,64);
    int cycles[2],stopped[2],remaining[2];uint32_t usp[2],isp[2];
    for(unsigned mode=0;mode<2;++mode) {
        m68ki_cpu=start;memcpy(MEM+0xbffec0,stack,64);
        CPU_STOPPED=RESET_CYCLES=CPU_INT_LEVEL=m68ki_cpu.nmi_pending=0;
        FLAG_T1=FLAG_T0=0;m68ki_tracing=0;
        REG_SP=0xbfff00;REG_USP=0xbfff00;REG_ISP=0xbfff00;
        m68ki_set_sr_noint(sr);REG_PC=pc;
        rr_x68k_force_reference=mode==0;
        cycles[mode]=m68k_execute((int)budget);
        if(twice)cycles[mode]+=m68k_execute(1);
        rr_x68k_get_cpu(mode?second:first);
        usp[mode]=REG_USP;isp[mode]=REG_ISP;stopped[mode]=CPU_STOPPED;
        remaining[mode]=m68ki_remaining_cycles;
        if(!mode)memcpy(after,MEM+0xbffec0,64);
    }
    int same=!memcmp(first,second,sizeof first) && cycles[0]==cycles[1] && stopped[0]==stopped[1]
        && remaining[0]==remaining[1] && usp[0]==usp[1] && isp[0]==isp[1]
        && !memcmp(after,MEM+0xbffec0,64);
    memcpy(MEM+0xbffec0,stack,64);m68ki_cpu=start;return same;
}
RR_X68K_EXPORT unsigned rr_x68k_guard_checks(void) {
    const uint32_t pc=0xbffe00u;unsigned result=0,clocks=0;
    m68ki_cpu_core saved=m68ki_cpu;int remaining=m68ki_remaining_cycles;
    extern int m68ki_initial_cycles;
    int initial=m68ki_initial_cycles,force=rr_x68k_force_reference;unsigned tracing=m68ki_tracing;
    uint8_t memory[256],vectors[256],stack[64],text[16],scsi[16];memcpy(text,TVRAM+0x7ffc0,sizeof text);
    memcpy(scsi,SCSIIPL+0x1fc0,sizeof scsi);
    uint32_t bus=BusErrFlag;memcpy(memory,MEM+pc,sizeof memory);memcpy(vectors,MEM,256);memcpy(stack,MEM+0xbffec0,64);
    CPU_STOPPED=RESET_CYCLES=CPU_INT_LEVEL=m68ki_cpu.nmi_pending=0;
    m68ki_set_sr_noint(0x2700);REG_PC=pc;REG_D[0]=0xbeef0000;
    raw_word(pc,0x303c);raw_word(pc+2,0x1234);raw_word(pc+4,0x4e75);
    if(rr_x68k_lookup(pc) && rr_x68k_native_execute(pc,&clocks) && REG_D[0]==0xbeef1234 && REG_PC==pc+4 && clocks==8)result|=1;
    REG_PC=pc;dma_writemem24_word(pc+2,0x5678);
    if(rr_x68k_lookup(pc) && rr_x68k_native_execute(pc,&clocks) && REG_D[0]==0xbeef5678 && REG_PC==pc+4 && clocks==8)result|=2;
    REG_PC=pc;raw_word(pc+2,0x9abc);
    m68ki_cpu_core before=m68ki_cpu;
    if(!rr_x68k_lookup(pc) && !rr_x68k_native_execute(pc,&clocks) && !memcmp(&before,&m68ki_cpu,sizeof before))result|=4;
    raw_word(pc+2,0x1234);if(rr_x68k_lookup(pc))result|=8;
    raw_word(pc,0x7001);REG_PC=pc;
    if(rr_x68k_native_execute(pc,&clocks) && REG_D[0]==1 && REG_PC==pc+2 && clocks==4)result|=16;
    raw_word(pc,0x707f);REG_PC=pc;
    before=m68ki_cpu;
    if(!rr_x68k_native_execute(pc,&clocks) && !memcmp(&before,&m68ki_cpu,sizeof before)) {
        int elapsed=m68k_execute(1);
        if(elapsed==4 && REG_D[0]==0x7f && REG_PC==pc+2)result|=32;
    }
    raw_word(pc+0x20,0x303c);raw_word(pc+0x22,0x1234);REG_PC=pc+0x20;
    if(rr_x68k_native_execute(REG_PC,&clocks) && REG_D[0]==0x1234 && REG_PC==pc+0x24)result|=64;
    if(!rr_x68k_lookup(pc+1) && !rr_x68k_lookup(0xe80000u) && !rr_x68k_lookup(0xfffffeu))result|=128;
    raw_word(pc+0x40,0x4e72);raw_word(pc+0x42,0x2700);raw_word(pc+0x44,0x7001);
    raw_word(pc+0x60,0x4e40);raw_word(pc+0x62,0x4e71);raw_word(pc+0x80,0x4e73);
    raw_word(pc+0xa0,0xff00);raw_word(pc+0xa2,0x4e71);raw_word(pc+0xb0,0x4e71);
    for(unsigned vector=8;vector<=32;++vector) {
        if(vector!=8 && vector!=9 && vector!=11 && vector!=32)continue;
        raw_word(vector*4,0x00bf);raw_word(vector*4+2,0xfe80);
    }
    if(paired(pc+0x40,0x2700,100,0))result|=256; /* STOP consumes the slice, not the following instruction. */
    if(paired(pc+0x60,0x2700,1,1))result|=512; /* TRAP + RTE, including the stack frame. */
    if(paired(pc+0xa0,0x2700,1,1))result|=1024; /* F-line + RTE, no host DOS replacement. */
    if(paired(pc+0x40,0x0000,1,1))result|=2048; /* Privilege exception and separate user/supervisor stacks. */
    if(paired(pc+0xb0,0xa700,1,1))result|=4096; /* T1 trace exception + RTE. */
    raw_word(pc+0x90,0x60fe);raw_word(pc+0x94,0x6000);raw_word(pc+0x96,0xfffe);
    raw_word(pc+0x9a,0x4ef9);raw_word(pc+0x9c,0x00bf);raw_word(pc+0x9e,0xfe9a);
    if(paired(pc+0x90,0x2700,200,0))result|=8192;
    if(paired(pc+0x94,0x2700,200,0))result|=16384;
    if(paired(pc+0x9a,0x2700,200,0))result|=32768;
    raw_word(0xe7ffc0,0x303c);raw_word(0xe7ffc2,0x1234);raw_word(0xe7ffc4,0x4e75);
    if(rr_x68k_lookup(0xe7ffc0)&&paired(0xe7ffc0,0x2700,1,0))result|=65536;
    raw_word(0xe7ffc2,0x5678);
    if(rr_x68k_lookup(0xe7ffc0)&&paired(0xe7ffc0,0x2700,1,0)){
        raw_word(0xe7ffc2,0x9abc);
        if(!rr_x68k_lookup(0xe7ffc0))result|=131072;
    }
    raw_word(0xea1fc0,0x303c);raw_word(0xea1fc2,0x1234);raw_word(0xea1fc4,0x4e75);
    if(rr_x68k_lookup(0xea1fc0)&&paired(0xea1fc0,0x2700,1,0))result|=262144;
    raw_word(0xea1fc2,0x5678);
    if(rr_x68k_lookup(0xea1fc0)&&paired(0xea1fc0,0x2700,1,0)){
        uint16_t value;
        raw_word(0xea1fc2,0x9abc);
        if(!rr_x68k_lookup(0xea1fc0)&&!rr_x68k_code_word(0xea1fff,&value)
            &&!rr_x68k_code_word(0xea2000,&value)&&rr_x68k_code_word(0xea1ffe,&value))result|=524288;
    }
    memcpy(SCSIIPL+0x1fc0,scsi,sizeof scsi);
    memcpy(TVRAM+0x7ffc0,text,sizeof text);
    memcpy(MEM+pc,memory,sizeof memory);BusErrFlag=bus;
    memcpy(MEM,vectors,256);memcpy(MEM+0xbffec0,stack,64);
    rr_x68k_force_reference=force;m68ki_tracing=tracing;
    m68ki_cpu=saved;m68ki_remaining_cycles=remaining;m68ki_initial_cycles=initial;
    return result;
}
