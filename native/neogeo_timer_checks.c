/* Authored ROM-free expectations from NeoGeoDev timing/IRQ documentation and
 * MAME neogeo.cpp display counter period N+1. Not a same-core CPU comparison. */
#include <stdio.h>
#include <stdlib.h>
#include "engine/geo.c"
#include "m68k/m68k.h"
#include "m68000_backend.h"
static unsigned checks;
static void expect(int ok,const char *name) {
    ++checks;if(!ok){fprintf(stderr,"timer: %s\n",name);exit(2);}
}
static void begin(uint32_t remaining,unsigned control,unsigned reload) {
    ngsys.irq2_counter=remaining;ngsys.irq2_reload=reload;
    ngsys.irq2_ctrl=control;ngsys.irq2_frags=0;oc=0;irq2_fragmask=1;
    rr_m68000_set_irq(2,0);
}
int main(void) {
    rr_ng_reference_bind();geo_m68k_init();
    expect(MCYC_PER_LINE==1536 && MCYC_PER_FRAME==405504,"384 pixels x 264 lines x 4 master clocks");
    ngsys.irq2_ctrl=0x30;ngsys.irq2_counter=99;
    m68k_write_memory_16(0x3c0008,0);m68k_write_memory_16(0x3c000a,0);
    expect(ngsys.irq2_counter==1,"zero register schedules one pixel through real bus");
    m68k_write_memory_16(0x3c0008,0xffff);m68k_write_memory_16(0x3c000a,0xffff);
    expect(!ngsys.irq2_counter && ngsys.irq2_reload==0xffffffffu,"maximum register is full unsigned period");
    const unsigned periods[]={1,2,5,768,16384,41017};
    for(unsigned n=0;n<sizeof periods/sizeof *periods;++n) {
        unsigned period=periods[n];
        begin(period,0x10,period-1);
        rr_ng_irq2_advance((period-1)*2);
        expect(!rr_m68000_get_irq(2),"IRQ not early");
        rr_ng_irq2_advance(1);expect(!rr_m68000_get_irq(2),"half pixel retained");
        rr_ng_irq2_advance(1);expect(rr_m68000_get_irq(2),"IRQ at N+1 pixels");
        expect(ngsys.irq2_counter==0,"one-shot reaches terminal count");
        rr_m68000_set_irq(2,0);rr_ng_irq2_advance(10);
        expect(!rr_m68000_get_irq(2),"one-shot does not retrigger");
        begin(period,0x90,period-1);
        rr_ng_irq2_advance(period*2);
        expect(rr_m68000_get_irq(2) && ngsys.irq2_counter==period,"repeat reload includes terminal pixel");
        rr_m68000_set_irq(2,0);rr_ng_irq2_advance(period*2);
        expect(rr_m68000_get_irq(2) && ngsys.irq2_counter==period,"repeat cadence stable");
    }
    begin(1,0x80,0);rr_ng_irq2_advance(20);
    expect(!rr_m68000_get_irq(2) && ngsys.irq2_counter==1,"disabled IRQ still reloads timer");
    begin(0,0x10,0xffffffffu);rr_ng_irq2_advance(2);
    expect(!rr_m68000_get_irq(2) && ngsys.irq2_counter==0xffffffffu,"maximum period wraps unsigned 32 bits");
    begin(2,0x10,1);oc=1;irq2_fragmask=3;
    rr_ng_irq2_advance(7);expect(!rr_m68000_get_irq(2),"divider fractional clocks preserved");
    rr_ng_irq2_advance(1);expect(rr_m68000_get_irq(2),"divider period uses real pixel clock");
    /* Extra 68000 capacity must not alter the raster/RTC clock or make the
     * watchdog expire twice as fast. Odd bus costs carry across instructions. */
    mcycs=0;geo_set_div68k(1);watchdog_enabled=1;watchdog_cycs=1000;ngsys.watchdog=0;
    expect(rr_ng_master_step(5)==5 && mcycs==10 && ngsys.watchdog==10,
        "standard CPU clocks advance peripherals and watchdog at master rate");
    mcycs=0;geo_set_div68k(0);ngsys.watchdog=0;
    const unsigned costs[]={3,3,1,1,5,7,9,11};unsigned cpu_total=0,peripheral_total=0;
    for(unsigned i=0;i<sizeof costs/sizeof *costs;++i) {
        cpu_total+=costs[i];peripheral_total+=rr_ng_master_step(costs[i]);
        expect(mcycs==cpu_total && peripheral_total==cpu_total/2,
            "enhanced odd costs retain every half peripheral cycle");
        expect(ngsys.watchdog==cpu_total,"enhanced watchdog uses master rather than CPU divider");
    }
    mcycs=MCYC_PER_FRAME-1;watchdog_enabled=0;
    expect(rr_ng_master_step(3)==2 && mcycs==MCYC_PER_FRAME+2,
        "fractional peripheral phase crosses even frame boundary");
    mcycs%=MCYC_PER_FRAME;
    expect(rr_ng_master_step(3)==1 && (mcycs&1)==1,"serialized master remainder carries next frame phase");
    ngsys.irq2_frags=1;geo_set_div68k(1);
    expect(!oc && irq2_fragmask==1 && ngsys.irq2_frags==0,"enhanced-to-standard switch bounds IRQ fraction");
    ngsys.irq2_frags=1;geo_set_div68k(0);
    expect(oc==1 && irq2_fragmask==3 && ngsys.irq2_frags==2,"standard-to-enhanced switch rebases IRQ fraction");
    geo_set_div68k(0);expect(ngsys.irq2_frags==2,"same clock mode keeps fractional IRQ state");
    geo_set_div68k(1);expect(ngsys.irq2_frags==1,"clock roundtrip retains representable IRQ phase");
    printf("{\"passed\":true,\"timer_spec_checks\":%u,\"synthetic_inputs_only\":true}\n",checks);
    return 0;
}
