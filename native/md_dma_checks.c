/* Independent authored expectations, synthetic sources, no commercial ROM. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "video/genesis_vdp.h"
#include "md_timing.h"
static unsigned checks, phase, reads, pulse, assertions, releases;
static uint32_t addresses[8];
unsigned machine_vdp_phase(void) { return phase; }
void machine_vdp_z80_irq(int value) { pulse=!!value;if(value)++assertions;else ++releases; }
#define CHECK(ok) do { ++checks;if(!(ok)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#ok);exit(1);} }while(0)
static uint16_t read_bus(void *user,uint32_t addr) {
    (void)user;if(reads<8)addresses[reads]=addr; ++reads;
    return addr?0x7654:0xabcd;
}
static void command(GVDP *v,unsigned code,unsigned addr) {
    gvdp_write_control(v,((code&3)<<14)|(addr&0x3fff));
    gvdp_write_control(v,((code&0x3c)<<2)|(addr>>14));
}
static void init(GVDP *v,int h40,int on) {
    phase=reads=pulse=assertions=releases=0;gvdp_init(v);v->bus_read=read_bus;
    v->reg[1]=0x10|(on?0x40:0);v->reg[12]=h40?0x81:0;v->reg[15]=2;
}
static void setup(GVDP *v,unsigned n,unsigned mode) {
    v->reg[19]=(uint8_t)n;v->reg[20]=(uint8_t)(n>>8);v->reg[23]=(uint8_t)mode;
}
static unsigned word(GVDP *v,unsigned a) { return 256u*v->vram[a]+v->vram[a+1]; }
int main(void) {
    GVDP v;
#ifdef RR_DMA_BASELINE
    init(&v,1,1);setup(&v,2,0);command(&v,0x21,0);
    v.vint_pending=1;gvdp_read_control(&v);
    printf("{\"bulk_dma_immediate\":%s,\"status_discards_vint\":%s}\n",
        word(&v,0)==0xabcd?"true":"false",!v.vint_pending?"true":"false");return 0;
#else
    for(int h40=0;h40<2;++h40) {
        unsigned first=h40?352:230, second=h40?820:510;
        unsigned third=h40?948:810, fourth=h40?1076:970;
        init(&v,h40,1);setup(&v,2,0);command(&v,0x21,0);
        CHECK(v.dma_active && gvdp_dma_blocks_cpu(&v) && !reads && !word(&v,0));
        CHECK(gvdp_peek_status(&v)&2);CHECK(!gvdp_consume_68k_stall(&v));
        unsigned fetch=h40?16:20, fetched=h40?33:40;
        phase=fetch-1;gvdp_read_control(&v);CHECK(!reads && !word(&v,0));
        phase=fetch;gvdp_read_control(&v);CHECK(reads==1 && !word(&v,0) && v.rr_fifo.count==1);
        CHECK(v.rr_dma.remaining==1 && v.reg[19]==1 && v.reg[21]==1 && v.address==2);
        phase=fetched;CHECK(gvdp_dma_wait_until(&v,200)==fetched);
        CHECK(reads==2 && !v.dma_active && !gvdp_dma_blocks_cpu(&v) && v.rr_fifo.count==2);
        CHECK(v.reg[21]==2 && v.address==4 && !word(&v,0));
        /* The CPU's bus is free while the destination still has two words. */
        phase=first;gvdp_read_control(&v);CHECK(word(&v,0)==0xcd && v.rr_fifo.half);
        phase=second;gvdp_fifo_advance(&v,phase);CHECK(word(&v,0)==0xabcd && v.rr_fifo.count==1);
        phase=third;gvdp_fifo_advance(&v,phase);GVDP partial=v;
        phase=fourth;gvdp_fifo_advance(&v,phase);CHECK(word(&v,2)==0x7654 && !v.dma_active);
        GVDP finished=v;v=partial;gvdp_fifo_advance(&v,phase);CHECK(!memcmp(&v,&finished,sizeof v));
        CHECK(gvdp_timing_valid(&v));
        /* CRAM is a word per slot, unlike byte-wide VRAM. */
        init(&v,h40,1);setup(&v,2,0);command(&v,0x23,0);
        phase=fetched;gvdp_fifo_advance(&v,phase);CHECK(!v.cram[0] && !v.dma_active && v.rr_fifo.count==2);
        phase=first;gvdp_fifo_advance(&v,phase);CHECK(v.cram[0]==(0xabcd&0xeee) && v.rr_fifo.count==1);
        phase=second;gvdp_fifo_advance(&v,phase);CHECK(!v.dma_active && v.cram[1]==(0x7654&0xeee));
        /* Main-bus source wraps within 128 KiB, preserving its upper bank. */
        init(&v,h40,1);setup(&v,2,0);v.reg[21]=v.reg[22]=255;command(&v,0x23,0);
        phase=second;gvdp_fifo_advance(&v,phase);CHECK(addresses[0]==0x1fffe && addresses[1]==0);
        /* Older queued words retain their own command/address and win slots. */
        init(&v,h40,1);command(&v,1,0);gvdp_write_data(&v,0x1234);setup(&v,1,0);command(&v,0x21,0);
        phase=fetched;gvdp_fifo_advance(&v,phase);CHECK(reads==1 && v.rr_fifo.count==2 && !v.dma_active);
        phase=second;gvdp_fifo_advance(&v,phase);CHECK(word(&v,0)==0x1234 && reads==1);
        phase=fourth;gvdp_fifo_advance(&v,phase);CHECK(word(&v,0)==0xabcd && reads==1);
        /* Fetches stop at four entries until a complete destination word frees
         * space. A low-byte retirement alone must not free an entry. */
        init(&v,h40,1);setup(&v,8,0);command(&v,0x21,0);
        phase=first;gvdp_fifo_advance(&v,phase);
        CHECK(reads==4 && v.rr_fifo.count==4 && v.rr_fifo.half && v.rr_dma.remaining==4);
        phase=second;gvdp_fifo_advance(&v,phase);
        CHECK(reads==4 && v.rr_fifo.count==3 && !v.rr_fifo.half);
        phase=third;gvdp_fifo_advance(&v,phase);CHECK(reads==5 && v.rr_fifo.count==4);
        GVDP congested=v;phase=9000;gvdp_fifo_advance(&v,phase);
        CHECK(reads==8 && !v.dma_active && !v.rr_fifo.count);
        GVDP drained=v;v=congested;reads=5;gvdp_fifo_advance(&v,phase);
        CHECK(reads==8 && !memcmp(&v,&drained,sizeof v));
        /* Migrate an old directly fetched half-word without fetching it twice. */
        init(&v,h40,1);setup(&v,2,0);command(&v,0x21,0);
        v.rr_dma.half=1;v.rr_dma.value=0xabcd;v.vram[1]=0xcd;v.rr_fifo.clock=first;
        CHECK(gvdp_dma_migrate(&v) && v.rr_fifo.count==1 && v.rr_fifo.half);
        CHECK(v.rr_dma.remaining==1 && v.rr_dma.source==2 && !reads);
        phase=second;gvdp_fifo_advance(&v,phase);
        CHECK(word(&v,0)==0xabcd && reads==1 && addresses[0]==2);
        phase=fourth;gvdp_fifo_advance(&v,phase);CHECK(word(&v,2)==0x7654);
        init(&v,h40,1);setup(&v,1,0);command(&v,0x21,0);
        v.rr_dma.half=1;v.rr_dma.value=0xabcd;v.vram[1]=0xcd;
        CHECK(gvdp_dma_migrate(&v) && !v.dma_active && v.rr_fifo.count==1 && v.rr_fifo.half);
        phase=first;gvdp_fifo_advance(&v,phase);CHECK(word(&v,0)==0xabcd && !reads);
        /* Both modes and all starting phases: no immediate memory commit,
         * bounded FIFO, phase-partition independence and deterministic tail. */
        for(unsigned at=0;at<3420;at+=37) {
            init(&v,h40,1);phase=at;gvdp_fifo_advance(&v,phase);setup(&v,7,0);command(&v,0x21,0);
            GVDP start=v;gvdp_fifo_advance(&v,at+7000);GVDP finish=v;
            CHECK(!v.dma_active && !v.rr_fifo.count && reads==7);
            v=start;reads=0;
            for(unsigned t=at+1;t<=at+7000;++t) { gvdp_fifo_advance(&v,t);CHECK(v.rr_fifo.count<=4); }
            CHECK(reads==7 && !memcmp(&v,&finish,sizeof v));
        }
        /* Fill starts on its data word and runs asynchronously without CPU hold. */
        init(&v,h40,1);setup(&v,2,0x80);command(&v,0x21,0);CHECK(v.dma_fill_pending && !v.dma_active);
        gvdp_write_data(&v,0x5678);CHECK(v.dma_active && !gvdp_dma_blocks_cpu(&v));
        phase=second;gvdp_fifo_advance(&v,phase);CHECK(word(&v,0)==0x5678 && !v.vram[3]);
        phase=third;gvdp_fifo_advance(&v,phase);CHECK(v.vram[3]==0x56 && v.rr_dma.remaining==1);
        phase=fourth;gvdp_fifo_advance(&v,phase);CHECK(v.vram[5]==0x56 && !v.dma_active);
        /* Copy reads and writes in separate slots; overlapping reads are live. */
        init(&v,h40,1);v.vram[0]=0x91;setup(&v,2,0xc0);v.reg[15]=1;command(&v,0x21,1);
        phase=first;gvdp_fifo_advance(&v,phase);CHECK(!v.vram[1] && v.rr_dma.half);
        GVDP copied=v;phase=second;gvdp_fifo_advance(&v,phase);CHECK(v.vram[1]==0x91 && v.dma_active);
        phase=fourth;gvdp_fifo_advance(&v,phase);CHECK(v.vram[2]==0x91 && !v.dma_active);
        v=copied;gvdp_fifo_advance(&v,phase);CHECK(v.vram[2]==0x91);
        /* A transfer crosses the active/blank boundary, rather than picking
         * one bandwidth for its whole length at command time. */
        init(&v,h40,1);v.scanline=223;phase=3400;gvdp_fifo_advance(&v,phase);
        setup(&v,8,0);command(&v,0x23,0);CHECK(!reads);
        gvdp_fifo_advance(&v,3420);gvdp_begin_scanline(&v,224);
        phase=200;gvdp_fifo_advance(&v,phase);CHECK(reads==8 && !v.dma_active);
        /* Zero length is 65536 units, not an absent transfer. */
        init(&v,h40,0);setup(&v,0,0x80);command(&v,0x21,0);gvdp_write_data(&v,0x1122);
        CHECK(v.rr_dma.remaining==65536);gvdp_fifo_advance(&v,3420);
        CHECK(v.dma_active && v.rr_dma.remaining<65536 && v.rr_dma.remaining>65000);
        /* Pending IRQs survive both the VDP enable bits and status reads. */
        init(&v,h40,1);v.reg[10]=7;gvdp_begin_scanline(&v,0);
        CHECK(v.rr_irq.hint_pending && !gvdp_irq_level(&v));
        v.reg[0]=0x10;CHECK(gvdp_irq_level(&v)==4);gvdp_read_control(&v);CHECK(gvdp_irq_level(&v)==4);
        gvdp_begin_scanline(&v,224);v.reg[1]|=0x20;
        unsigned edge=h40?812:800;phase=edge-1;gvdp_read_control(&v);CHECK(!v.vint_pending && !pulse);
        phase=edge;gvdp_read_control(&v);CHECK(v.vint_pending && pulse && gvdp_irq_level(&v)==6);
        gvdp_read_control(&v);CHECK(v.vint_pending && assertions==1);
        gvdp_irq_ack(&v,6);CHECK(!v.vint_pending && gvdp_irq_level(&v)==4);
        gvdp_irq_ack(&v,4);CHECK(!gvdp_irq_level(&v));
        gvdp_fifo_advance(&v,3420);gvdp_begin_scanline(&v,225);
        phase=edge-1;gvdp_fifo_advance(&v,phase);CHECK(pulse);
        phase=edge;gvdp_fifo_advance(&v,phase);CHECK(!pulse && releases==1);
        /* Display enable does not mask either IRQ or the Z80's pulse. */
        init(&v,h40,0);gvdp_begin_scanline(&v,224);phase=edge;gvdp_fifo_advance(&v,phase);
        CHECK(v.vint_pending && pulse && !gvdp_irq_level(&v));v.reg[1]|=0x20;CHECK(gvdp_irq_level(&v)==6);
        GVDP clean=v;v.rr_dma.mode=4;CHECK(!gvdp_timing_valid(&v));v=clean;
        v.rr_dma.remaining=65537;CHECK(!gvdp_timing_valid(&v));v=clean;
        v.rr_irq.hint_pending=2;CHECK(!gvdp_timing_valid(&v));v=clean;
        v.rr_irq.vint_stage=3;CHECK(!gvdp_timing_valid(&v));
        gvdp_reset(&v);CHECK(gvdp_timing_valid(&v) && !gvdp_irq_level(&v));
    }
    printf("{\"checks\":%u,\"passed\":true,\"standard\":\"%s\"}\n",checks,RR_MD_PAL?"pal":"ntsc");return 0;
#endif
}
