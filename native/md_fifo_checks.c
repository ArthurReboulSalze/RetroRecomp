/* Authored, ROM-free expectations for the actual staged VDP implementation. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "video/genesis_vdp.h"
#include "md_timing.h"
static unsigned phase, checks, callbacks;
unsigned machine_vdp_phase(void) { return phase; }
#define CHECK(ok) do { ++checks; if(!(ok)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#ok); exit(1); } } while(0)
static void colour(void *u,unsigned index,uint16_t value) { (void)u; (void)index; (void)value; ++callbacks; }
static void command(GVDP *v,unsigned code,unsigned address) {
    gvdp_write_control(v,((code&3)<<14)|(address&0x3fff));
    gvdp_write_control(v,((code&0x3c)<<2)|(address>>14));
}
static void init(GVDP *v,int h40) {
    phase=0;callbacks=0;gvdp_init(v);v->reg[1]=0x40;v->reg[12]=h40?0x81:0;
    v->colour_updated=colour;command(v,1,0);
}
static unsigned word(const GVDP *v,unsigned address) { return v->vram[address]*256u+v->vram[address+1]; }
static uint16_t bus_read(void *u,uint32_t a) { (void)u;return a?0x7654:0xabcd; }
int main(void) {
    GVDP v;
#ifdef RR_FIFO_BASELINE
    init(&v,1);gvdp_write_data(&v,0x1234);
    printf("{\"immediate_write\":%s,\"always_empty\":%s}\n",
        word(&v,0)==0x1234?"true":"false",(gvdp_read_control(&v)&0x200)?"true":"false");
    return 0;
#else
    const unsigned expected32[]={230,510,810,970,1130,1450,1610,1770,2090,2250,2410,2730,2890,3050,3350,3370};
    const unsigned expected40[]={352,820,948,1076,1332,1460,1588,1844,1972,2100,2356,2484,2612,2868,2996,3124,3364,3380};
    for(int h40=0;h40<2;++h40) {
        const unsigned *expected=h40?expected40:expected32;
        unsigned n=h40?18:16, slot=0;
        for(unsigned i=0;i<n;++i) { slot=rr_md_fifo_next_slot(slot,h40,0);CHECK(slot==expected[i]); }
        CHECK(rr_md_fifo_next_slot(slot,h40,0)==3420+expected[0]);
        /* Every possible starting phase agrees with separately enumerated facts. */
        for(unsigned start=0;start<3420;++start) {
            unsigned answer=3420+expected[0];
            for(unsigned i=0;i<n;++i) if(expected[i]>start) { answer=expected[i];break; }
            CHECK(rr_md_fifo_next_slot(start,h40,0)==answer);
        }
        slot=0;n=0;
        while((slot=rr_md_fifo_next_slot(slot,h40,1))<=3420) ++n;
        CHECK(n==(h40?205:167));
        unsigned a=expected[0],b=expected[1];
        init(&v,h40); CHECK((gvdp_peek_status(&v)&0x300)==0x200);
        gvdp_write_data(&v,0x1234);CHECK(v.address==2 && !word(&v,0));
        CHECK(!(gvdp_peek_status(&v)&0x300));
        phase=a-1;CHECK(!(gvdp_read_control(&v)&0x300));CHECK(!word(&v,0));
        phase=a;CHECK(!(gvdp_read_control(&v)&0x200));CHECK(word(&v,0)==0x0034 && v.rr_fifo.half==1);
        GVDP partial=v; /* an in-flight low byte is guest state */
        phase=b;gvdp_fifo_advance(&v,phase);CHECK(word(&v,0)==0x1234 && v.rr_fifo.count==0);
        GVDP finished=v;v=partial;gvdp_fifo_advance(&v,phase);CHECK(!memcmp(&v,&finished,sizeof v));
        CHECK(gvdp_fifo_valid(&v));
        init(&v,h40);command(&v,1,1);gvdp_write_data(&v,0x8765);
        phase=a;gvdp_fifo_advance(&v,phase);CHECK(v.vram[0]==0x65 && !v.vram[1]);
        phase=b;gvdp_fifo_advance(&v,phase);CHECK(word(&v,0)==0x6587);
        /* Four accepted writes, fifth waits until the oldest complete word. */
        init(&v,h40);
        for(unsigned i=0;i<4;++i) gvdp_write_data(&v,0x1100+i);
        CHECK((gvdp_read_control(&v)&0x300)==0x100 && !word(&v,0));
        CHECK(!gvdp_consume_68k_stall(&v));
        gvdp_write_data(&v,0x2200);
        unsigned stall=gvdp_consume_68k_stall(&v);
        CHECK(stall==(b+6)/7 && !gvdp_consume_68k_stall(&v));
        CHECK(word(&v,0)==0x1100 && !word(&v,2) && v.rr_fifo.count==4 && v.address==10);
        phase=3420;gvdp_fifo_advance(&v,phase);
        for(unsigned i=0;i<4;++i) CHECK(word(&v,2*i)==0x1100+i);
        CHECK(word(&v,8)==0x2200 && !v.rr_fifo.count);
        /* The first entry keeps its destination when later commands change it. */
        init(&v,h40);command(&v,1,0x100);gvdp_write_data(&v,0x1234);
        command(&v,3,2);gvdp_write_data(&v,0x0eee);
        gvdp_write_control(&v,0x8f10);command(&v,5,4);gvdp_write_data(&v,0xffff);
        CHECK(v.address==20 && !callbacks && !v.cram[1] && !v.vsram[2]);
        phase=b;gvdp_fifo_advance(&v,phase);CHECK(word(&v,0x100)==0x1234 && !callbacks);
        phase=expected[2];gvdp_fifo_advance(&v,phase);CHECK(v.cram[1]==0xeee && callbacks==1 && !v.vsram[2]);
        phase=expected[3];gvdp_fifo_advance(&v,phase);CHECK(v.vsram[2]==0x3ff && !v.rr_fifo.count);
        /* No access creates time: repeated reads and peeks preserve the queue. */
        init(&v,h40);gvdp_write_data(&v,0x1234);
        for(unsigned i=0;i<100;++i) {CHECK(!(gvdp_read_control(&v)&0x200));CHECK(!word(&v,0));}
        GVDP before=v;phase=b;CHECK(!(gvdp_peek_status(&v)&0x200));CHECK(!memcmp(&before,&v,sizeof v));
        CHECK(gvdp_read_control(&v)&0x200);CHECK(word(&v,0)==0x1234);
        /* A data read waits for ordered preceding writes; host peek does not. */
        init(&v,h40);gvdp_write_data(&v,0x1234);command(&v,0,0);
        CHECK(gvdp_peek_data(&v)==0 && gvdp_read_data(&v)==0x1234);
        CHECK(gvdp_consume_68k_stall(&v)==(b+6)/7);
        /* Carry a half word through a raster boundary without dropping it. */
        init(&v,h40);phase=expected[(h40?18:16)-2];gvdp_fifo_advance(&v,phase);
        gvdp_write_data(&v,0xaabb);phase=3420;gvdp_fifo_advance(&v,phase);CHECK(word(&v,0)==0x00bb);
        gvdp_begin_scanline(&v,1);phase=a;gvdp_fifo_advance(&v,phase);CHECK(word(&v,0)==0xaabb);
        /* Entering VBlank releases the restricted slots on the following line. */
        init(&v,h40);v.scanline=223;phase=3400;gvdp_fifo_advance(&v,phase);
        gvdp_write_data(&v,0xaabb);phase=3420;gvdp_fifo_advance(&v,phase);
        gvdp_begin_scanline(&v,224);phase=50;gvdp_fifo_advance(&v,phase);CHECK(word(&v,0)==0xaabb);
        /* Older queued writes finish before the existing bulk DMA paths. */
        init(&v,h40);gvdp_write_data(&v,0x1234);v.bus_read=bus_read;
        v.reg[1]|=0x10;v.reg[0x13]=1;command(&v,0x21,0);
        CHECK(word(&v,0)==0xabcd && !v.rr_fifo.count && gvdp_consume_68k_stall(&v)>0);
        init(&v,h40);gvdp_write_data(&v,0x1234);v.reg[1]|=0x10;
        v.reg[0x13]=1;v.reg[0x17]=0xc0;command(&v,0x21,0x100);CHECK(v.vram[0x100]==0x12);
        init(&v,h40);gvdp_write_data(&v,0x1234);v.reg[1]|=0x10;
        v.reg[0x13]=1;v.reg[0x17]=0x80;command(&v,0x21,0);gvdp_write_data(&v,0xabcd);
        CHECK(word(&v,0)==0xabcd && !v.rr_fifo.count);
        init(&v,h40);gvdp_write_data(&v,0x1234);gvdp_reset(&v);
        CHECK(!v.rr_fifo.count && !word(&v,0) && (gvdp_peek_status(&v)&0x200));
        v.rr_fifo.count=5;CHECK(!gvdp_fifo_valid(&v));v.rr_fifo.count=0;
        v.rr_fifo.half=1;CHECK(!gvdp_fifo_valid(&v));v.rr_fifo.half=0;
        v.rr_fifo.head=4;CHECK(!gvdp_fifo_valid(&v));
    }
    printf("{\"checks\":%u,\"passed\":true,\"standard\":\"%s\"}\n",checks,RR_MD_PAL?"pal":"ntsc");
    return 0;
#endif
}
