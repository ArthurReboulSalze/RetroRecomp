/* Authored YM timer/register/buffer boundaries, using no sample ROM. */
#include <stdio.h>
#include <stdlib.h>
#include "engine/geo_ymfm.c"
static unsigned checks;
static void expect(int ok,const char *name) {
    ++checks;if(!ok){fprintf(stderr,"YM2610: %s\n",name);exit(2);}
}
static void reg(unsigned r,unsigned v){ym2610_write(4,r);ym2610_write(5,v);}
int main(void) {
    static uint8_t a[3]={0x31,0x52,0x75},b[2]={0x24,0x65};
    romdata_t *data=geo_romdata_ptr();data->v1=a;data->v1sz=sizeof a;data->v2=b;data->v2sz=sizeof b;
    geo_ymfm_init();geo_ymfm_reset();
    expect(ymfm_external_read(ACCESS_ADPCM_A,2)==0x75,"last valid A sample");
    expect(!ymfm_external_read(ACCESS_ADPCM_A,3) && !ymfm_external_read(ACCESS_ADPCM_A,4),"A end boundary excluded");
    expect(ymfm_external_read(ACCESS_ADPCM_B,1)==0x65,"last valid B sample");
    expect(!ymfm_external_read(ACCESS_ADPCM_B,2) && !ymfm_external_read(ACCESS_ADPCM_B,3),"B end boundary excluded");
    reg(0x24,255);reg(0x25,3);reg(0x26,255);reg(0x27,0x0f);
    expect(!(ym2610_read(4)&3),"timer flags start clear");
    geo_ymfm_timer_tick();expect((ym2610_read(4)&3)==1,"A minimum period is 144 YM clocks");
    for(unsigned n=1;n<15;++n)geo_ymfm_timer_tick();
    expect((ym2610_read(4)&3)==1,"B not early");
    geo_ymfm_timer_tick();expect((ym2610_read(4)&3)==3,"B minimum period is 2304 YM clocks");
    reg(0x27,0x30);expect(!(ym2610_read(4)&3),"IRQ flag acknowledgement clears both timers");
    printf("{\"passed\":true,\"ym_spec_checks\":%u,\"synthetic_inputs_only\":true}\n",checks);
    return 0;
}
