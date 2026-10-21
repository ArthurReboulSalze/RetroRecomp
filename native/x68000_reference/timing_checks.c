/* Original authored hardware assertions, not hashes of a second CPU. MIT.
 * MC68901UM sections 4 and 6 supply counter, prescaler and interrupt rules.
 * DMAC checks assert transfer/count/status semantics, not electrical bus timing.
 * Run only after capture/reports: diagnostic instructions are not gameplay.
 */
#include "timing_checks.h"
#include "libretro.h"
#include "m68000.h"
#include "winx68k.h"
#include "x68k/crtc.h"
#include "x68k/mfp.h"
#include "x68k/dmac.h"
#include "x68k/irqh.h"
#include "x68k/x68kmemory.h"
#include "check_compat.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern int32_t my_irqh_callback(int32_t level);
extern uint32_t BusErrHandling;
extern int m68ki_remaining_cycles, m68ki_initial_cycles;
extern unsigned m68ki_tracing;
extern int VID_MODE, CHANGEAV_TIMING;

static void mw(unsigned reg, uint8_t value) { MFP_Write(0xe88001u + reg * 2u, value); }
static void cw(unsigned reg, uint16_t value) {
    CRTC_Write(0xe80000u + reg * 2u, (uint8_t)(value >> 8));
    CRTC_Write(0xe80001u + reg * 2u, (uint8_t)value);
}
static void mfp_clean(void) {
    IRQH_Init(); MFP_Init();
    mw(MFP_IERA,0); mw(MFP_IERB,0); mw(MFP_IMRA,0); mw(MFP_IMRB,0);
    mw(MFP_TACR,0); mw(MFP_TBCR,0); mw(MFP_TCDCR,0);
    mw(MFP_IPRA,0); mw(MFP_IPRB,0); mw(MFP_ISRA,0); mw(MFP_ISRB,0);
    for (unsigned c=0;c<4;++c) mw(MFP_TADR+c,0);
}
static void timer_mode(unsigned channel, unsigned mode) {
    if(channel<2) mw(MFP_TACR+channel,(uint8_t)mode);
    else {
        unsigned other=MFP[MFP_TCDCR];
        mw(MFP_TCDCR,(uint8_t)(channel==2 ? ((other&15u)|(mode<<4)) : ((other&240u)|mode)));
    }
}
static int crtc_cold(void) {
    CRTC_Init();
    return CRTC_HSTART==28 && CRTC_HEND==124 && CRTC_VSTART==40 && CRTC_VEND==552;
}
static int crtc_modes(void) {
    cw(2,16); cw(3,80); cw(4,567); cw(6,40); cw(7,552);
    cw(20,0x10);
    int ok=TextDotX==512 && TextDotY==256 && CRTC_VStep==1;
    cw(20,0x14); ok &= TextDotY==512 && CRTC_VStep==2;
    cw(20,0x04); ok &= TextDotY==1024 && CRTC_VStep==4;
    cw(20,0x00); return ok && TextDotY==512 && CRTC_VStep==2;
}
static int crtc_zero_divisor(void) {
    cw(0,0); cw(4,0); cw(20,0x10);
    (void)MFP_Read(0xe88001u);
    int ok=VLINE_TOTAL>=1 && HSYNC_CLK>0;
    cw(0,137); cw(4,567);
    return ok;
}
static int timer_prescalers(void) {
    /* 4 MHz MFP / 10 MHz board clock: divisors 4..200 become 10..500 cycles. */
    static const unsigned clocks[8]={0,10,25,40,125,160,250,500};
    for(unsigned c=0;c<4;++c) for(unsigned mode=1;mode<=7;++mode) {
        mfp_clean(); mw(MFP_TADR+c,3); timer_mode(c,mode);
        MFP_Timer((int)clocks[mode]-1);
        if(MFP[MFP_TADR+c]!=3) return 0;
        MFP_Timer(1); if(MFP[MFP_TADR+c]!=2) return 0;
        MFP_Timer((int)clocks[mode]*2); if(MFP[MFP_TADR+c]!=3) return 0;
    }
    return 1;
}
static int timer_zero(void) {
    mfp_clean(); mw(MFP_IERA,0x20); mw(MFP_TADR,0); timer_mode(0,1);
    MFP_Timer(2550);
    if(MFP[MFP_TADR]!=1 || MFP[MFP_IPRA]) return 0;
    MFP_Timer(10);
    return MFP[MFP_TADR]==0 && MFP[MFP_IPRA]==0x20;
}
static int timer_running_reload(void) {
    for(unsigned c=0;c<4;++c) {
        mfp_clean(); mw(MFP_TADR+c,3); timer_mode(c,1); MFP_Timer(10);
        mw(MFP_TADR+c,5);
        if(MFP[MFP_TADR+c]!=2) return 0;
        MFP_Timer(20); if(MFP[MFP_TADR+c]!=5) return 0;
    }
    return 1;
}
static int timer_stop_residual(void) {
    for(unsigned c=0;c<4;++c) {
        mfp_clean(); mw(MFP_TADR+c,3); timer_mode(c,1); MFP_Timer(5);
        timer_mode(c,0); MFP_Timer(1000); timer_mode(c,1); MFP_Timer(5);
        if(MFP[MFP_TADR+c]!=3) return 0;
        MFP_Timer(5); if(MFP[MFP_TADR+c]!=2) return 0;
    }
    return 1;
}
static int irq_auto(void) {
    mfp_clean(); mw(MFP_VR,0x40); mw(MFP_IERA,0x20); mw(MFP_IMRA,0x20);
    mw(MFP_TADR,1); timer_mode(0,1); MFP_Timer(10);
    if(MFP[MFP_IPRA]!=0x20) return 0;
    return my_irqh_callback(6)==0x4d && MFP[MFP_IPRA]==0 && MFP[MFP_ISRA]==0;
}
static int irq_software(void) {
    mfp_clean(); mw(MFP_VR,0x48); mw(MFP_IERA,0x20); mw(MFP_IMRA,0x20);
    mw(MFP_TADR,1); timer_mode(0,1); MFP_Timer(10);
    if(my_irqh_callback(6)!=0x4d || MFP[MFP_IPRA] || MFP[MFP_ISRA]!=0x20) return 0;
    mw(MFP_ISRA,0xdf); return MFP[MFP_ISRA]==0;
}
static int timer_a_event(void) {
    mfp_clean(); cw(4,567); cw(6,40); cw(7,552);
    mw(MFP_AER,0x10); mw(MFP_TADR,2); timer_mode(0,8);
    vline=39; MFP_TimerA(); if(MFP[MFP_TADR]!=2) return 0;
    vline=40; MFP_TimerA(); if(MFP[MFP_TADR]!=1) return 0;
    vline=41; MFP_TimerA(); if(MFP[MFP_TADR]!=1) return 0;
    vline=40; MFP_TimerA(); if(MFP[MFP_TADR]!=2) return 0;
    mw(MFP_AER,0); vline=551; MFP_TimerA(); if(MFP[MFP_TADR]!=2) return 0;
    vline=552; MFP_TimerA(); return MFP[MFP_TADR]==1;
}
static void dw(unsigned reg, uint8_t value) { DMA_Write(0xe84080u+reg,value); }
static void dword(unsigned reg, uint32_t value) {
    dw(reg,(uint8_t)(value>>24)); dw(reg+1,(uint8_t)(value>>16));
    dw(reg+2,(uint8_t)(value>>8)); dw(reg+3,(uint8_t)value);
}
static void dma_case(unsigned size, unsigned count, int irq) {
    IRQH_Init(); DMA_Init(); BusErrFlag=0;
    for(unsigned i=0;i<32;++i) {
        dma_writemem24(0xbff800u+i,(uint8_t)(0x31u+i*7u));
        dma_writemem24(0xbff840u+i,0);
    }
    dw(4,8); dw(5,(uint8_t)((size<<4)|1)); dw(6,5);
    dw(10,(uint8_t)(count>>8)); dw(11,(uint8_t)count);
    dword(12,0xbff800u); dword(20,0xbff840u);
    dw(0x25,0x4b); dw(0x27,0x4c);
    if(irq) dw(7,0x88);
}
static int dma_transfer(unsigned size) {
    unsigned width=1u<<size; dma_case(size,3,1);
    for(unsigned i=0;i<3*width;++i)
        if(dma_readmem24(0xbff840u+i)!=(uint8_t)(0x31u+i*7u)) return 0;
    return DMA[2].MTC==0 && DMA[2].MAR==0xbff800u+3*width
        && DMA[2].DAR==0xbff840u+3*width && (DMA[2].CSR&0xf8)==0x80 && !DMA[2].CER;
}
static int dma_byte(void) { return dma_transfer(0); }
static int dma_word(void) { return dma_transfer(1); }
static int dma_long(void) { return dma_transfer(2); }
static int dma_halt(void) {
    dma_case(0,3,0);
    /* Active/halted state: a scheduler service must not transfer any byte. */
    DMA[2].CSR=8; DMA[2].CCR=0xa0; DMA_Exec(2);
    if(DMA[2].MTC!=3 || dma_readmem24(0xbff840u)!=0) return 0;
    dw(7,0x88);
    return DMA[2].MTC==0 && dma_readmem24(0xbff842u)==0x3f;
}
static int dma_zero(void) {
    dma_case(0,0,0); dw(7,0x88);
    return DMA[2].CER==0x0d && (DMA[2].CSR&0x18)==0x10 && !(DMA[2].CCR&0x80)
        && my_irqh_callback(3)==0x4c;
}
static int dma_address_error(void) {
    dma_case(1,3,0); dword(12,0xbff801u); dw(7,0x88);
    return DMA[2].CER==5 && (DMA[2].CSR&0x18)==0x10 && DMA[2].MTC==3
        && DMA[2].MAR==0xbff801u && DMA[2].DAR==0xbff840u
        && dma_readmem24_word(0xbff840u)==0
        && my_irqh_callback(3)==0x4c;
}
static int dma_irq(void) {
    dma_case(0,3,1);
    return my_irqh_callback(3)==0x4b && DMA[2].MTC==0 && (DMA[2].CSR&0x80);
}
static int cpu_elapsed(void) {
    /* MC68000 NOP is four clocks even when the caller supplies a one-clock slice. */
    m68k_pulse_reset(); (void)m68k_execute(1); /* Consume RESET latency only. */
    dma_writemem24_word(0xbffeb0u,0x4e71);
    m68k_set_reg(M68K_REG_SR,0x2700); m68k_set_reg(M68K_REG_PC,0xbffeb0u);
    int used=m68k_execute(1);
    return used==4 && m68k_get_reg(NULL,M68K_REG_PC)==0xbffeb2u;
}
static int timer_partition(void) {
    uint8_t counters[4];
    mfp_clean();
    for(unsigned c=0;c<4;++c) { mw(MFP_TADR+c,(uint8_t)(31+c)); timer_mode(c,c+1); }
    MFP_Timer(10000); memcpy(counters,MFP+MFP_TADR,4);
    mfp_clean();
    for(unsigned c=0;c<4;++c) { mw(MFP_TADR+c,(uint8_t)(31+c)); timer_mode(c,c+1); }
    for(unsigned i=0;i<1000;++i) MFP_Timer(10);
    return memcmp(counters,MFP+MFP_TADR,4)==0;
}
static int crtc_coordinates(void) {
    cw(9,0x05ff); cw(10,0x0d23); cw(11,0x0c56);
    cw(12,0x0d23); cw(13,0x0c56); cw(14,0x03ff); cw(15,0x03fe);
    return CRTC_IntLine==511 && TextScrollX==0x123 && TextScrollY==0x56
        && GrphScrollX[0]==0x123 && GrphScrollY[0]==0x56
        && GrphScrollX[1]==0x1ff && GrphScrollY[1]==0x1fe;
}
RR_X68K_EXPORT uint32_t rr_x68k_timing_checks(const char *json_path) {
    static const struct { const char *name; int (*run)(void); } cases[]={
        {"crtc_cold_geometry",crtc_cold},{"crtc_mode_transitions",crtc_modes},
        {"crtc_unprogrammed_divisors",crtc_zero_divisor},{"mfp_28_prescalers",timer_prescalers},
        {"mfp_zero_means_256",timer_zero},{"mfp_4_running_reload",timer_running_reload},
        {"mfp_4_stop_prescaler_reset",timer_stop_residual},{"mfp_auto_eoi_vector",irq_auto},
        {"mfp_software_eoi_vector",irq_software},{"mfp_timer_a_display_edges",timer_a_event},
        {"dma_byte_count_and_increment",dma_byte},{"dma_word_count_and_increment",dma_word},
        {"dma_long_count_and_increment",dma_long},{"dma_halt_resume",dma_halt},
        {"dma_zero_count_error_vector",dma_zero},{"dma_odd_word_error_vector",dma_address_error},
        {"dma_completion_vector",dma_irq},{"cpu_slice_instruction_overshoot",cpu_elapsed},
        {"mfp_chunk_partition",timer_partition},{"crtc_coordinates_and_masks",crtc_coordinates}
    };
    uint32_t mask=0;
    FILE *out=json_path?fopen(json_path,"wb"):NULL;
    if(json_path && !out) return 0;
    size_t size=retro_serialize_size(); void *state=size?malloc(size):NULL;
    unsigned context_size=m68k_context_size(); void *cpu=malloc(context_size);
    uint8_t memory[256]; memcpy(memory,MEM+0xbff800u,sizeof memory);
    uint8_t opcode[2]; memcpy(opcode,MEM+0xbffeb0u,2);
    int remaining=m68ki_remaining_cycles,initial=m68ki_initial_cycles;
    unsigned tracing=m68ki_tracing;
    uint32_t bus=BusErrFlag,handling=BusErrHandling;
    uint32_t saved_vline=vline;
    int saved_video_mode=VID_MODE,saved_timing_change=CHANGEAV_TIMING;
    if(!state || !cpu || !retro_serialize(state,size)) {
        if(out) { fputs("{\"schema\":1,\"error\":\"cannot save diagnostic state\",\"mask\":0}\n",out); fclose(out); }
        free(state); free(cpu); return 0;
    }
    m68k_get_context(cpu); m68k_set_reg(M68K_REG_SR,0x2700);
    if(out) fputs("{\"schema\":1,\"kind\":\"authored-device-assertions\",\"cases\":[",out);
    for(unsigned n=0;n<sizeof cases/sizeof cases[0];++n) {
        int ok=cases[n].run(); if(ok) mask|=UINT32_C(1)<<n;
        if(out) fprintf(out,"%s{\"name\":\"%s\",\"passed\":%s}",n?",":"",cases[n].name,ok?"true":"false");
    }
    int restored=retro_unserialize(state,size);
    m68k_set_context(cpu); m68ki_remaining_cycles=remaining; m68ki_initial_cycles=initial; m68ki_tracing=tracing;
    memcpy(MEM+0xbff800u,memory,sizeof memory); memcpy(MEM+0xbffeb0u,opcode,2);
    BusErrFlag=bus; BusErrHandling=handling;
    vline=saved_vline; VID_MODE=saved_video_mode; CHANGEAV_TIMING=saved_timing_change;
    if(!restored) mask=0;
    if(out) { fprintf(out,"],\"mask\":%u,\"expected_mask\":%u,\"state_restored\":%s,\"passed\":%s}\n",mask,RR_X68K_TIMING_EXPECTED,restored?"true":"false",mask==RR_X68K_TIMING_EXPECTED?"true":"false"); fclose(out); }
    free(state); free(cpu); return mask;
}
