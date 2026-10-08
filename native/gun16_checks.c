/* Authored protocol and real peripheral bridge fixtures; no ROM required. */
#include <stdlib.h>
#include <string.h>
#include "retro_console16.h"
static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x); exit(1); } } while (0)
#if RR16_MD
#include "video/genesis_machine.h"
GenesisMachine g_machine;
int rr16_visible_width(void) { return (g_machine.vdp.reg[12] & 1) ? 320 : 256; }
#else
#include "snes/snes.h"
#include "snes/ppu.h"
#include "snes/joypad.h"
static Snes machine;
static Ppu ppu;
Snes *g_snes = &machine;
Ppu *g_ppu = &ppu;
#endif
int main(void) {
    Rr16GunInput in = {.x = 100, .y = 80};
    CHECK(rr_md_gun_port(RR_GUN_MENACER, &in, 0, 0x80, false) == 0x40);
    in.fire = in.aux = in.secondary = in.start = true;
    CHECK(rr_md_gun_port(RR_GUN_MENACER, &in, 0, 0x80, false) == 0x4f);
    CHECK(rr_md_gun_port(RR_GUN_MENACER, &in, 0, 0x80, true) == 0x0f);
    CHECK(rr_md_gun_port(RR_GUN_MENACER, &in, 0x10, 0x90, false) == 0x5f);
    CHECK(rr_md_gun_port(RR_GUN_JUSTIFIER, &in, 0x40, 0xc0, false) == 0x70);
    CHECK(rr_md_gun_port(RR_GUN_JUSTIFIER, &in, 0, 0x80, false) == 0x70);
    CHECK(rr_md_gun_port(RR_GUN_JUSTIFIER, &in, 0x20, 0xa0, false) == 0x73);
    in.fire = in.start = false;
    CHECK(rr_md_gun_port(RR_GUN_JUSTIFIER, &in, 0, 0x80, false) == 0x73);
    CHECK(rr_md_gun_hcounter(296,256,0,false) == 0xe9);
    CHECK(rr_md_gun_hcounter(294,256,0,false) == 0x93);
    CHECK(rr_md_gun_hcounter(366,320,0,false) == 0xe5);
    CHECK(rr_md_gun_hcounter(364,320,0,false) == 0xb6);
    CHECK(rr_md_gun_hcounter(160,320,0x52,true) == 154);
    RrMenacer receiver = {0};
    in = (Rr16GunInput){.fire=true, .start=true};
    rr_menacer_write(&receiver, &in, 0x00, 0x40);
    rr_menacer_write(&receiver, &in, 0x40, 0x40);
    CHECK(receiver.buttons == 0); /* T2 identifies the gun while pad Start is held. */
    rr_menacer_write(&receiver, &in, 0xff, 0xb0);
    rr_menacer_write(&receiver, &in, 0xdf, 0xb0);
    CHECK(receiver.buttons == 10);
    in.fire = in.start = false;
    rr_menacer_write(&receiver, &in, 0xff, 0xb0);
    rr_menacer_write(&receiver, &in, 0xcf, 0xb0);
    CHECK(receiver.buttons == 10); /* Short reset retains acquired buttons. */
    rr_menacer_write(&receiver, &in, 0xff, 0xb0);
    rr_menacer_write(&receiver, &in, 0xdf, 0xb0);
    CHECK(receiver.buttons == 0);
    RrScope scope = {0}; in = (Rr16GunInput){.fire=true};
    rr_scope_input(&scope,in); CHECK(rr_scope_latch(&scope) == 0x80ff);
    CHECK(rr_scope_latch(&scope) == 0x00ff); /* one-shot held trigger */
    in.aux=true; rr_scope_input(&scope,in); CHECK(rr_scope_latch(&scope) == 0x40ff);
    in.turbo=true; rr_scope_input(&scope,in); CHECK(rr_scope_latch(&scope) == 0xe0ff);
    CHECK(rr_scope_latch(&scope) == 0xe0ff); /* physical turbo held */
    in=(Rr16GunInput){.pause=true,.offscreen=true}; rr_scope_input(&scope,in);
    CHECK(rr_scope_latch(&scope) == 0x30ff); CHECK(rr_scope_latch(&scope) == 0x20ff);
    in=(Rr16GunInput){.fire=true}; rr_scope_input(&scope,in);
    rr_scope_strobe(&scope,1); CHECK(rr_scope_serial(&scope) == 1);
    rr_scope_strobe(&scope,0);
    unsigned packet=0; for(int n=0;n<16;++n) packet=(packet<<1)|rr_scope_serial(&scope);
    CHECK(packet == 0x80ff); CHECK(rr_scope_serial(&scope)==1);
    rr16_gun_reset();
#if RR16_MD
    CHECK(!rr16_md_instruction_busy()); rr16_md_instruction(true);
    CHECK(rr16_md_instruction_busy()); rr16_md_instruction(false);
    CHECK(!rr16_md_instruction_busy());
    if (RR16_GUN == 0) {
        rr16_md_instruction(true); rr16_gun_reset();
        CHECK(!rr16_md_instruction_busy());
        printf("{\"kind\":0,\"checks\":%u,\"passed\":true}\n", checks);
        return 0;
    }
    if (RR16_GUN==1) {
        rr16_gun_input((Rr16GunInput){.x=100,.y=80,.start=true});
        rr16_md_gun_io_write(0,0x40);
        CHECK(rr16_md_gun_read(0,0x40)==0);
        rr16_md_gun_io_write(0x40,0x40);
        CHECK(rr16_md_gun_read(0x40,0x40)==0x40);
        rr16_md_gun_io_write(0xff,0xb0); rr16_md_gun_io_write(0xdf,0xb0);
        CHECK(rr16_md_gun_read(0xdf,0xb0)==0x58);
        rr16_gun_input((Rr16GunInput){.x=100,.y=80});
        CHECK(rr16_md_gun_read(0xdf,0xb0)==0x58);
        rr16_md_gun_io_write(0xff,0xb0); rr16_md_gun_io_write(0xdf,0xb0);
        CHECK(rr16_md_gun_read(0xdf,0xb0)==0x50);
        rr16_gun_reset();
    }
    memset(&g_machine,0,sizeof g_machine);
    g_machine.vdp.reg[12]=1; g_machine.vdp.reg[11]=8; g_machine.bus.io_ctrl[1]=0x80;
    in=(Rr16GunInput){.x=160,.y=80,.fire=true}; rr16_gun_input(in);
    rr16_md_gun_line(79+RR16_GUN_Y_OFFSET); CHECK(!rr16_md_gun_pending());
    rr16_md_gun_line(80+RR16_GUN_Y_OFFSET); CHECK(rr16_md_gun_pending());
    CHECK(rr16_md_gun_hv(0x1234)==0x1234); /* no M3 latch outside IRQ */
    rr16_md_gun_irq_begin(); CHECK(!rr16_md_gun_pending());
    unsigned expected=((80+RR16_GUN_Y_OFFSET)<<8)|rr_md_gun_hcounter(160,320,RR16_GUN_X_OFFSET,RR16_GUN==1);
    CHECK(rr16_md_gun_hv(0x1234)==expected);
    rr16_md_gun_irq_end(); CHECK(rr16_md_gun_hv(0x1234)==0x1234);
    g_machine.vdp.reg[0]=2; CHECK(rr16_md_gun_hv(0x1234)==expected);
    rr16_gun_reset(); in.offscreen=true; rr16_gun_input(in);
    rr16_md_gun_line(80+RR16_GUN_Y_OFFSET); CHECK(!rr16_md_gun_pending());
    in.offscreen=false; rr16_gun_input(in); g_machine.bus.io_ctrl[1]=0xc0;
    rr16_md_gun_line(80+RR16_GUN_Y_OFFSET); CHECK(!rr16_md_gun_pending());
    if(RR16_GUN==2) {
        g_machine.bus.io_ctrl[1]=0xa0; g_machine.bus.io_data[1]=0x20;
        rr16_md_gun_line(80); CHECK(!rr16_md_gun_pending());
    }
#else
    joypad_reset_state(); joypad_write_iobit(g_snes,0xff);
    in=(Rr16GunInput){.x=100,.y=80,.fire=true}; rr16_gun_input(in);
    joypad_write_strobe(g_snes,1); joypad_write_strobe(g_snes,0);
    packet=0; for(int n=0;n<16;++n) packet=(packet<<1)|(joypad_read_port(g_snes,1)&1);
    CHECK(packet==0x80ff); CHECK(joypad_read_port(g_snes,1)==1);
    rr16_gun_reset(); rr16_gun_input(in); joypad_auto_read(g_snes);
    CHECK(joypad_auto_read_reg_addr(g_snes,0x421a)==0xff);
    CHECK(joypad_auto_read_reg_addr(g_snes,0x421b)==0x80);
    CHECK(joypad_read_port(g_snes,1)==1);
    joypad_auto_read(g_snes); CHECK(joypad_auto_read_reg_addr(g_snes,0x421b)==0);
    g_snes->ppuLatch=false; rr16_scope_beam(439,77,8); CHECK(!g_ppu->countersLatched);
    g_snes->ppuLatch=true; rr16_scope_beam(439,76,8); CHECK(!g_ppu->countersLatched);
    rr16_scope_beam(431,77,8); CHECK(!g_ppu->countersLatched);
    g_ppu->hCountSecond=g_ppu->vCountSecond=true;
    rr16_scope_beam(439,77,8); CHECK(g_ppu->countersLatched);
    CHECK(g_ppu->hCount==110 && g_ppu->vCount==77);
    CHECK(g_ppu->hCountSecond && g_ppu->vCountSecond);
    g_snes->vPos=77; g_snes->hPos=440;
    CHECK(joypad_read_iobit()==0x40);
    g_snes->hPos=448; CHECK(joypad_read_iobit()==0xc0);
    rr16_gun_input((Rr16GunInput){.x=-1,.y=80,.fire=true,.aux=true}); g_ppu->countersLatched=false;
    rr16_scope_beam(0,77,1024); CHECK(!g_ppu->countersLatched);
    joypad_auto_read(g_snes); CHECK(joypad_auto_read_reg_addr(g_snes,0x421b)==0x42);
#endif
    printf("{\"kind\":%d,\"checks\":%u,\"passed\":true}\n",RR16_GUN,checks);
    return 0;
}
