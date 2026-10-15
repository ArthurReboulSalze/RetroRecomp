/* Authored MVS sound latch/banking expectations; no game or firmware bytes. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "engine/geo_z80.c"
static unsigned checks;
static void expect(int ok,const char *name) {
    ++checks;if(!ok){fprintf(stderr,"sound: %s\n",name);exit(2);}
}
int main(void) {
    static uint8_t synthetic[0x80000],system[0x20000];
    for(unsigned n=0;n<sizeof synthetic;++n)synthetic[n]=(uint8_t)(n/0x800);
    romdata_t *data=geo_romdata_ptr();data->m=synthetic;data->msz=sizeof synthetic;
    data->sm=system;data->smsz=sizeof system;ngsys.sys=SYSTEM_MVS;
    geo_z80_init();geo_z80_reset();geo_z80_set_mrom(1);
    const unsigned ports[]={0x0b,0x0a,0x09,0x08},addresses[]={0x8000,0xc000,0xe000,0xf000};
    const unsigned units[]={0x4000,0x2000,0x1000,0x800};
    // This is our compatible deterministic startup policy, not a hardware
    // guarantee: cartridge power-on bank register values are undefined.
    for(unsigned n=0;n<4;++n)expect(geo_z80_mem_rd(NULL,(uint16_t)addresses[n])==synthetic[addresses[n]],"compatible linear startup mapping");
    unsigned startup_checks=checks;checks=0;
    const unsigned banks[]={0,1,7,14,30,63,127,128,243,255};
    for(unsigned n=0;n<4;++n)for(unsigned b=0;b<sizeof banks/sizeof *banks;++b) {
        unsigned bank=banks[b];
        geo_z80_port_rd(NULL,(uint16_t)(ports[n]|bank<<8));
        expect(geo_z80_mem_rd(NULL,(uint16_t)addresses[n])==synthetic[(bank*units[n])%sizeof synthetic],"port high byte selects physical bank");
    }
    ngsys.sound_code=0x53;geo_z80_nmi();
    expect(rr_ng_sound_pending && !z80ctx.nmi_pending,"masked command retained without CPU edge");
    geo_z80_port_wr(NULL,0x08,0);
    expect(z80ctx.nmi_pending,"unmask raises pending command edge");
    z80ctx.nmi_pending=0;geo_z80_port_wr(NULL,0x08,0);geo_z80_nmi();
    expect(!z80ctx.nmi_pending,"unacknowledged high latch does not pulse again");
    expect(geo_z80_port_rd(NULL,0)==0x53 && !rr_ng_sound_pending,"read returns and acknowledges command");
    ngsys.sound_code=0x82;geo_z80_nmi();expect(z80ctx.nmi_pending,"new command raises new edge");
    geo_z80_port_wr(NULL,0x0c,0xa5);expect(ngsys.sound_reply==0xa5,"reply latch independent of command");
    geo_z80_port_wr(NULL,0,0);expect(!ngsys.sound_code,"write clears command data");
    geo_z80_port_wr(NULL,0x18,0);z80ctx.nmi_pending=0;
    geo_z80_port_rd(NULL,0);geo_z80_nmi();expect(!z80ctx.nmi_pending,"mask suppresses subsequent edge");
    rr_ng_sound_latch_restore(1);expect(rr_ng_sound_latch()==1,"snapshot command latch restored");
    geo_z80_reset();expect(!rr_ng_sound_pending && !nmi_enabled,"reset clears mask and command latch");
    printf("{\"passed\":true,\"sound_spec_checks\":%u,\"sound_startup_regressions\":%u,\"synthetic_inputs_only\":true}\n",checks,startup_checks);
    return 0;
}
