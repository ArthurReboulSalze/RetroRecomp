/* Independent ROM-free prefetch expectations, not a reference CPU comparison. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "video/genesis_vdp.h"
static unsigned checks,phase,pulse;
unsigned machine_vdp_phase(void) { return phase; }
void machine_vdp_z80_irq(int asserted) { pulse=!!asserted; }
#define CHECK(ok) do {++checks;if(!(ok)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#ok);exit(1);}}while(0)
static void command(GVDP *v,unsigned code,unsigned addr) {
    gvdp_write_control(v,((code&3)<<14)|(addr&0x3fff));
    gvdp_write_control(v,((code&0x3c)<<2)|(addr>>14));
}
static void init(GVDP *v,int h40,int on) {
    phase=pulse=0;gvdp_init(v);v->reg[1]=on?0x40:0;v->reg[12]=h40?0x81:0;
    v->reg[15]=2;v->vram[0]=0x12;v->vram[1]=0x34;v->vram[2]=0x56;v->vram[3]=0x78;
}
int main(void) {
    GVDP v;
#ifdef RR_READ_BASELINE
    init(&v,1,1);command(&v,0,0);
    unsigned value=gvdp_read_data(&v),stall=gvdp_consume_68k_stall(&v);
    printf("{\"immediate_read\":%s,\"value\":%u}\n",!stall?"true":"false",value);return 0;
#else
    for(int h40=0;h40<2;++h40)for(int on=0;on<2;++on) {
        unsigned first=on?(h40?352:230):(h40?16:20);
        unsigned second=on?(h40?820:510):(h40?33:40);
        init(&v,h40,on);command(&v,0,0);
        CHECK(v.rr_read.state==1 && !v.rr_read.value && !v.address);
        CHECK(!gvdp_consume_68k_stall(&v));
        gvdp_fifo_advance(&v,first-1);CHECK(v.rr_read.state==1 && !v.address);
        gvdp_fifo_advance(&v,first);CHECK(v.rr_read.state==3 && v.rr_read.value==0x1200 && !v.address);
        gvdp_fifo_advance(&v,second);CHECK(v.rr_read.state==2 && v.rr_read.value==0x1234 && v.address==2);
        v.vram[0]=0xaa;v.vram[1]=0xbb;phase=second;
        CHECK(gvdp_peek_data(&v)==0x1234 && gvdp_read_data(&v)==0x1234);
        CHECK(!gvdp_consume_68k_stall(&v));
        CHECK(v.rr_read.state==1 && v.rr_read.address==2 && v.address==2);
        CHECK(gvdp_read_data(&v)==0x5678);
        CHECK(gvdp_consume_68k_stall(&v)>0 && v.address==4 && v.rr_read.address==4);
        /* A new command cannot return a stale, already latched word. */
        phase=v.rr_fifo.clock;command(&v,0,0);
        CHECK(v.rr_read.state==1 && !v.rr_read.value && !v.address);
        CHECK(gvdp_read_data(&v)==0xaabb);CHECK(gvdp_consume_68k_stall(&v)>0);
        /* Immediate read waits for its access slot, not an arbitrary latency. */
        init(&v,h40,on);command(&v,0,0);CHECK(gvdp_read_data(&v)==0x1234);
        CHECK(v.rr_fifo.clock==second && gvdp_consume_68k_stall(&v)==(second+6)/7);
        /* CRAM/VSRAM use the same external access opportunities. */
        for(unsigned code=4;code<=8;code+=4) {
            init(&v,h40,on);v.cram[0]=0xeee;v.vsram[0]=0x7ff;command(&v,code,0);
            CHECK(v.rr_read.state==1);CHECK(gvdp_read_data(&v)==(code==8?0xeee:0x7ff));
            CHECK(gvdp_consume_68k_stall(&v)==(first+6)/7 && v.address==2);
        }
        /* Odd VRAM address retains existing aligned-word behavior; wraps. */
        init(&v,h40,on);command(&v,0,1);CHECK(gvdp_read_data(&v)==0x1234);
        init(&v,h40,on);v.vram[65534]=0xfe;v.vram[65535]=0xdc;command(&v,0,65534);
        CHECK(gvdp_read_data(&v)==0xfedc && v.address==0 && !v.rr_read.address);
        /* A read never observes a queued word with only its low byte retired. */
        init(&v,h40,on);command(&v,1,0);gvdp_write_data(&v,0xabcd);command(&v,0,0);
        gvdp_fifo_advance(&v,first);CHECK(v.rr_fifo.half && v.rr_read.state==1);
        CHECK(v.vram[0]==0x12 && v.vram[1]==0xcd);
        unsigned result=gvdp_read_data(&v);CHECK(result==0xabcd && !v.rr_fifo.count);
        CHECK(v.rr_read.state==1 && v.address==2 && gvdp_consume_68k_stall(&v)>0);
        /* Both pending and ready states are deterministic across a snapshot. */
        init(&v,h40,on);command(&v,0,0);GVDP pending=v;
        gvdp_fifo_advance(&v,first);GVDP half=v;
        v.vram[0]=0xaa;CHECK(gvdp_peek_data(&v)==0x1234);
        gvdp_fifo_advance(&v,second);CHECK(v.rr_read.value==0x1234);
        v=half;gvdp_fifo_advance(&v,second);GVDP ready=v;
        v=pending;for(unsigned t=1;t<=second;++t)gvdp_fifo_advance(&v,t);
        CHECK(!memcmp(&v,&ready,sizeof v));
        phase=second;v=ready;unsigned expected=gvdp_read_data(&v);GVDP after=v;
        v=ready;CHECK(gvdp_read_data(&v)==expected && !memcmp(&v,&after,sizeof v));
        CHECK(gvdp_timing_valid(&v));v.rr_read.state=4;CHECK(!gvdp_timing_valid(&v));
        v=ready;v.rr_read.address=65536;CHECK(!gvdp_timing_valid(&v));
        v=ready;v.rr_read.code=1;CHECK(!gvdp_timing_valid(&v));
        v=pending;v.rr_read.value=1;CHECK(!gvdp_timing_valid(&v));
        v=half;v.rr_read.value|=1;CHECK(!gvdp_timing_valid(&v));
        v=half;v.rr_read.code=8;CHECK(!gvdp_timing_valid(&v));
        /* Writes and partial control commands cancel a previous read. */
        init(&v,h40,on);command(&v,0,0);gvdp_fifo_advance(&v,second);phase=second;
        gvdp_write_control(&v,0x4000);CHECK(!v.rr_read.state && v.control_pending);
        gvdp_write_data(&v,0xaaaa);CHECK(!v.rr_read.state && !v.control_pending);
        /* Across a line boundary, the same request completes once. */
        init(&v,h40,on);phase=3400;gvdp_fifo_advance(&v,phase);command(&v,0,0);
        GVDP crossing=v;gvdp_fifo_advance(&v,4500);GVDP finished=v;
        v=crossing;for(unsigned t=3401;t<=4500;++t)gvdp_fifo_advance(&v,t);
        CHECK(!memcmp(&v,&finished,sizeof v) && v.rr_read.state==2);
    }
    /* Read/FIFO waits must not skip the IRQ clock. */
    init(&v,1,0);v.scanline=224;v.rr_irq.vint_stage=1;phase=800;command(&v,0,0);
    CHECK(gvdp_read_data(&v)==0x1234 && v.vint_pending && pulse);
    CHECK(v.rr_read.state==1 && gvdp_timing_valid(&v));
    printf("{\"checks\":%u,\"read_buffer_and_slot_waits\":true,\"passed\":true}\n",checks);return 0;
#endif
}
