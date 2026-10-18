/* Authored cartridge, linked to actual backend/CPU/VDP objects. No game ROM. */
#include "platform_io.h"
#include <wchar.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "retro_console16.h"
#include "console16_state.h"
#include "md_cart.h"
#include "md_native_steps.h"
#include "runtime_feedback.h"
#include "glue.c"
#include "genesis_machine.c"
static unsigned checks;
#define CHECK(ok) do { ++checks;if(!(ok)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#ok);exit(1);}}while(0)
static void mapped_reads(void) {
    GenesisBus *b=&g_machine.bus;
    for(unsigned slot=1;slot<8;++slot)for(unsigned page=0;page<16;++page) {
        uint32_t reg=0xa130f1u+slot*2,pc=(slot<<19)+0x500;
        gbus_write8(b,reg,(uint8_t)page);
        CHECK(rr_md_cart_rom_offset(pc)==(page<<19)+0x500);
        CHECK(gbus_read16(b,pc)==(page<10?0xa000+page:0xffff));
        CHECK(gbus_peek16(b,pc)==gbus_read16(b,pc));
        CHECK(gbus_read16(b,0x500)==0xa000); /* bank zero fixed */
        b->z80_bank=(uint16_t)(pc>>15);
        CHECK(gbus_z80_read(b,0x8500)==(page<10?0xa0:0xff));
        CHECK(gbus_z80_read(b,0x8501)==(page<10?page:0xff));
        gbus_write8(b,reg-1,9);CHECK(rr_md_cart_rom_offset(pc)==(page<<19)+0x500);
        gbus_write16(b,reg-1,8);CHECK(gbus_read16(b,pc)==0xa008);
    }
    gbus_write8(b,0xa130f1,9);CHECK(rr_md_cart_rom_offset(0x500)==0x500);
    CHECK(rr_md_cart_rom_offset(0x400000)==UINT32_MAX);
    CHECK(rr_md_cart_rom_offset(0xff0000)==UINT32_MAX);
}
static void native_banks(void) {
    GenesisBus *b=&g_machine.bus;rr_md_prefetch_reset();g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
    gbus_write8(b,0xa130f3,8);
    const unsigned pcs[]={0x80400,0x80410,0x80420};
    for(unsigned i=0;i<3;++i) {
        g_cpu.PC=pcs[i];g_cpu.D[0]=2;uint32_t next=0;
        const RrMdNativeStep *op=rr_md_native_lookup(pcs[i]);CHECK(op && op->instruction.addr==0x400400+i*16);
        CHECK(op->execute(&next)==M68KI_OK);
        CHECK(i==0?next==0x8040a:i==1?g_cpu.A[0]==0x8041a:next==0x8042a && g_cpu.D[0]==1);
    }
    for(unsigned page=1;page<=9;page+=page==1?7:1) {
        gbus_write8(b,0xa130f3,(uint8_t)page);g_cpu.PC=0x80430;uint32_t next;
        const RrMdNativeStep *op=rr_md_native_lookup(g_cpu.PC);CHECK(op);
        CHECK(op->execute(&next)==M68KI_OK && next==0x80432);
        CHECK(g_cpu.D[0]==(page==1?1:page==8?0xffffffffu:2));
    }
    /* Keep the old fetched opcode while selecting another physical page. */
    rr_md_prefetch_reset();rr_step_running=1;
    rr_md_prefetch=(RrMdPrefetch){0x80430,2,{0x7001,0x4e71}};
    const RrMdNativeStep *old=rr_md_native_lookup(0x80430);
    CHECK(old && old->instruction.addr==0x80430);
    CHECK(rr_md_cart_code_offset(0x80430,old->instruction.words,old->instruction.word_count)==0x80430);
    rr_step_running=0;rr_md_prefetch_reset();
    const uint16_t mixed[]={0x7001,0x1234};
    CHECK(rr_md_cart_code_offset(0x80430,mixed,2)==UINT32_MAX);
    /* An unmatched prefetched image has no physical ROM source. Its sentinel
     * must not wrap the eight-byte bound and read past the embedded ROM. */
    rr_feedback_start(1);if(!rr_feedback_enabled())rr_feedback_toggle();
    CHECK(rr_feedback_enabled() && !rr_feedback_pending());
    rr_md_rom_fetch_offset=UINT32_MAX;rr16_note_rom_fallback(0x80430);
    CHECK(!rr_feedback_pending());
    rr_md_rom_fetch_offset=RR_MD_ROM_BYTES-7u;rr16_note_rom_fallback(0x80430);
    CHECK(!rr_feedback_pending());
    rr_md_rom_fetch_offset=RR_MD_ROM_BYTES-8u;rr16_note_rom_fallback(0x80430);
    CHECK(rr_feedback_pending());rr_feedback_toggle(); /* fixture writes no hints */
    gbus_write8(b,0xa130f3,8);g_cpu.PC=0x80440;uint32_t next;
    const RrMdNativeStep *self=rr_md_native_lookup(g_cpu.PC);CHECK(self);
    uint32_t physical=rr_md_cart_code_offset(g_cpu.PC,self->instruction.words,self->instruction.word_count);
    CHECK(self->execute(&next)==M68KI_OK && next==0x80448);
    CHECK(physical==0x400440 && rr_md_cart_rom_offset(next)==0x480448);
    /* DMA reads the same live mapped shadow as both processors. */
    GVDP *v=&g_machine.vdp;gvdp_reset(v);gbus_write8(b,0xa130fd,8);
    uint32_t src=0x300500>>1;v->reg[1]=0x10;v->reg[15]=2;v->reg[19]=1;v->reg[20]=0;
    v->reg[21]=(uint8_t)src;v->reg[22]=(uint8_t)(src>>8);v->reg[23]=(uint8_t)(src>>16);
    gvdp_write_control(v,0x4000);gvdp_write_control(v,0x0080);gvdp_fifo_advance(v,3420);
    CHECK(v->vram[0]==0xa0 && v->vram[1]==8 && !v->dma_active);
}
static int checks_main(int argc,wchar_t **argv) {
    CHECK(argc==3 && rr16_init(true));CHECK(RR_MD_SEGA_MAPPER && !rr_md_cart_legacy_allowed());
    if(!wcscmp(argv[1],L"create")) {
        mapped_reads();native_banks();rr16_reset();
        CHECK(rr_md_cart_state()->pages[1]==1);
        gbus_write8(&g_machine.bus,0xa130f3,8);gbus_write8(&g_machine.bus,0xa130ff,9);
        CHECK(rr16_state_file(argv[2],false));
        gbus_write8(&g_machine.bus,0xa130f3,9);CHECK(rr16_state_file(argv[2],true));
        CHECK(gbus_read16(&g_machine.bus,0x80500)==0xa008);
    } else {
        CHECK(!wcscmp(argv[1],L"restore"));CHECK(rr16_state_file(argv[2],true));
        CHECK(gbus_read16(&g_machine.bus,0x80500)==0xa008 && gbus_read16(&g_machine.bus,0x380500)==0xa009);
    }
    size_t size;uint8_t *state=rr16_state_capture(&size);CHECK(state && size>=sizeof(RrMdCartState));
    RrMdCartState before=*rr_md_cart_state();state[size-sizeof(RrMdCartState)+offsetof(RrMdCartState,pages)]=1;
    CHECK(!rr16_state_restore(state,size) && !memcmp(&before,rr_md_cart_state(),sizeof before));free(state);
    rr16_shutdown();printf("{\"checks\":%u,\"passed\":true}\n",checks);return 0;
}
#ifdef _WIN32
int wmain(int argc,wchar_t **argv) { return checks_main(argc,argv); }
#else
int main(int argc,char **argv) {
    wchar_t mode[32],path[4096];
    CHECK(argc==3 && rr_from_utf8(argv[1],mode,32) && rr_from_utf8(argv[2],path,4096));
    wchar_t *args[]={L"checks",mode,path};return checks_main(argc,args);
}
#endif
