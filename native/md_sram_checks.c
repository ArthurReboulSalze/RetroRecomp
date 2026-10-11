/* Authored bus expectations and actual Windows battery-file lifecycle. No ROM. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "md_battery.h"
static unsigned checks;
#define CHECK(ok) do { ++checks; if (!(ok)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#ok); exit(1); } } while(0)
uint8_t g_rom[0x400000],g_ram[0x10000],g_sndwatch[0x2000];
uint32_t g_audio_cycle_counter,g_68k_stamp_rebase;
unsigned long g_snd_frame;
unsigned g_snd_pcz;
uint32_t machine_z80_stamp(void) { return 0; }
uint32_t machine_z80_pc(void) { return 0; }
void glue_charge_68k_stall(uint32_t cycles) { (void)cycles; }
void snd_trace_68k_write(uint16_t o,uint8_t a,uint8_t n,int b,int r) {}
void snd_trace_z80(uint16_t o,uint8_t v,int w) {}
void snd_trace_busreq(const char *w,int v) {}
void audio_event_push(uint32_t t,uint8_t p,uint8_t v) {}
uint16_t gvdp_read_data(GVDP *v) { return 0; }
uint16_t gvdp_read_control(GVDP *v) { return 0; }
uint16_t gvdp_read_hv_counter(const GVDP *v) { return 0; }
uint16_t gvdp_peek_data(const GVDP *v) { return 0; }
uint16_t gvdp_peek_status(const GVDP *v) { return 0; }
void gvdp_write_data(GVDP *v,uint16_t n) {}
void gvdp_write_control(GVDP *v,uint16_t n) {}
uint32_t gvdp_consume_68k_stall(GVDP *v) { return 0; }
static GenesisBus bus;
static void be32(uint8_t *p,uint32_t n) { for(unsigned i=0;i<4;++i) p[i]=(uint8_t)(n>>(24-8*i)); }
static void setup(unsigned type,uint32_t base,uint32_t end) {
    gbus_init(&bus,NULL);
    g_rom[0x1b0]='R'; g_rom[0x1b1]='A'; g_rom[0x1b2]=(uint8_t)type; g_rom[0x1b3]=0x20;
    be32(g_rom+0x1b4,base); be32(g_rom+0x1b8,end); gbus_sram_setup(&bus);
}
static void bus_checks(void) {
    gbus_init(&bus,NULL); memset(g_ram,0,sizeof g_ram);
    for (uint32_t base=0xe00000; base<=0xff0000; base+=0x10000) {
        gbus_write8(&bus,base+0x1234,0x56); gbus_write8(&bus,base+0x1235,0x78);
        CHECK(gbus_read16(&bus,0xff1234)==0x5678 && gbus_peek16(&bus,base+0x1234)==0x5678);
        gbus_write16(&bus,base+0x1234,0xabcd);
        CHECK(gbus_read8(&bus,base+0x1234)==0xab && gbus_peek8(&bus,base+0x1235)==0xcd);
        CHECK(gbus_read16(&bus,0xe01234)==0xabcd);
        bus.z80_bank=(uint16_t)(base>>15);
        CHECK(gbus_z80_read(&bus,0x9234)==0xab);
        gbus_z80_write(&bus,0x9235,0x34); CHECK(gbus_peek16(&bus,0xff1234)==0xab34);
    }
    gbus_write16(&bus,0xe0ffff,0x1234);
    CHECK(gbus_peek8(&bus,0xe1ffff)==0x12 && gbus_peek8(&bus,0xff0000)==0x34);
    gbus_write16(&bus,0x01e01234,0x4321);
    CHECK(gbus_read16(&bus,0xff1234)==0x4321);
    CHECK(gbus_peek16(&bus,0xdffffe)==0xffff); /* below RAM stays unmapped */
    const unsigned types[]={0xa0,0xb0,0xb8,0xe0,0xf0,0xf8};
    for(unsigned t=0;t<6;++t) {
        unsigned type=types[t],stride=(type&0x10)?2:1,lane=(type>>3)&1;
        uint32_t start=0x200000u+(stride==2?lane:0),end=0x200007u-(stride==2?!lane:0);
        setup(type,start,end);
        CHECK(bus.sram_present && bus.sram_stride==stride && bus.sram_battery==!!(type&0x40));
        CHECK(bus.sram_size==(stride==2?4u:8u));
        CHECK(bus.sram_enabled==1 && gbus_read16(&bus,0x200000)==0xffff);
        gbus_write16(&bus,0x200000,0x1234);
        CHECK(gbus_read16(&bus,0x200000)==(stride==1?0x1234:lane?0xff34:0x12ff));
        CHECK(gbus_peek16(&bus,0x200000)==gbus_read16(&bus,0x200000));
        CHECK(gbus_read8(&bus,start)==(stride==1 || !lane?0x12:0x34));
        CHECK(gbus_peek8(&bus,start)==gbus_read8(&bus,start));
        CHECK(gbus_read8(&bus,0x1200000)==gbus_read8(&bus,0x200000));
        gbus_write8(&bus,end,0x65); CHECK(gbus_read8(&bus,end)==0x65);
        gbus_write16(&bus,0xa130f0,3); gbus_write8(&bus,end,0x99);
        CHECK(gbus_read8(&bus,end)==0x65); /* bit 1 protects connected bytes */
        gbus_write8(&bus,0xa130f0,0); CHECK(bus.sram_enabled==3);
        gbus_write8(&bus,0xa130f1,0); CHECK(bus.sram_enabled==0);
        CHECK(gbus_read8(&bus,start)==g_rom[start]);
        gbus_write8(&bus,end,0xa5); gbus_write8(&bus,0xa130f1,1);
        CHECK(gbus_read8(&bus,end)==0x65); /* disabled writes cannot alter SRAM */
    }
    setup(0xf8,0x80001,0x80007); CHECK(bus.sram_enabled==0);
    g_rom[0x80000]=0x71;g_rom[0x80001]=0x72;
    CHECK(gbus_read16(&bus,0x80000)==0x7172);
    gbus_write8(&bus,0xa130f1,1);gbus_write8(&bus,0x80001,0x44);
    CHECK(gbus_read16(&bus,0x80000)==0xff44);
    gbus_write8(&bus,0xa130f1,0); CHECK(gbus_read16(&bus,0x80000)==0x7172);
    setup(0xf8,0x200001,0x21ffff); CHECK(bus.sram_size==65536);
    gbus_write16(&bus,0x21fffe,0x1357); CHECK(bus.sram[65535]==0x57);
    CHECK(gbus_read16(&bus,0x21fffe)==0xff57 && bus.sram[0]==0xff);
    setup(0xf8,0x200001,0x200001); CHECK(bus.sram_size==1);
    gbus_write16(&bus,0x200000,0x1379); CHECK(bus.sram[0]==0x79);
    setup(0xf8,0x200000,0x200007); CHECK(!bus.sram_present); /* wrong declared lane */
    setup(0xe0,0x200000,0x21ffff); CHECK(!bus.sram_present); /* capacity */
    setup(0xe8,0x200001,0x200001);g_rom[0x1b3]=0x40;gbus_sram_setup(&bus);
    CHECK(!bus.sram_present);gbus_sram_set_geometry(&bus,0x200001,0x203fff);CHECK(!bus.sram_present);
    setup(0xf8,0x200001,0x203fff);
    GenesisBus copy=bus; CHECK(rr_md_sram_geometry_matches(&copy,&bus));
    copy.sram_enabled=3; CHECK(rr_md_sram_geometry_matches(&copy,&bus));
    copy.sram_size=0xffffffffu; CHECK(!rr_md_sram_geometry_matches(&copy,&bus));
    CHECK(sizeof(GenesisBus)==73816);
}
int wmain(int argc,wchar_t **argv) {
    if(argc==1) { bus_checks(); printf("{\"bus_checks\":%u,\"passed\":true}\n",checks);return 0; }
    CHECK(argc==3);
    const wchar_t *mode=argv[1],*path=argv[2];
    setup(!wcscmp(mode,L"volatile")?0xb8:0xf8,0x200001,0x203fff);
    bool headless=!wcscmp(mode,L"headless"),invalid=!wcscmp(mode,L"invalid");
    bool opened=rr_md_battery_open(&bus,headless?NULL:path);
    CHECK(opened!=invalid);
    if(!wcscmp(mode,L"read")) {
        CHECK(bus.sram[0]==0x72 && bus.sram[8191]==0x19 && bus.sram[1]==0xff);
    } else if(wcscmp(mode,L"unchanged")) {
        gbus_write8(&bus,0x200001,0x72); gbus_write8(&bus,0x203fff,0x19);
    }
    if(!wcscmp(mode,L"deferred") || !wcscmp(mode,L"reverted")) {
        CHECK(rr_md_battery_flush(&bus,500,false));
        CHECK(GetFileAttributesW(path)==INVALID_FILE_ATTRIBUTES);
        if(!wcscmp(mode,L"reverted")) memset(bus.sram,0xff,bus.sram_size);
        CHECK(rr_md_battery_flush(&bus,2000,false));
        CHECK(GetFileAttributesW(path)==INVALID_FILE_ATTRIBUTES);
        CHECK(rr_md_battery_flush(&bus,2500,false));
        if(!wcscmp(mode,L"deferred")) CHECK(GetFileAttributesW(path)!=INVALID_FILE_ATTRIBUTES);
    }
    bool flushed=rr_md_battery_flush(&bus,5000,true);
    CHECK(flushed==!!wcscmp(mode,L"blocked"));
    printf("{\"checks\":%u,\"passed\":true}\n",checks);return 0;
}
