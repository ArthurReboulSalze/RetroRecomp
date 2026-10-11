/* Linked to the ACTUAL adapted cartridge bus, with ROM-free host stubs. */
#include <windows.h>
#include "md_cart.h"
#include "md_battery.h"
static GenesisBus fixture_bus;
static uint64_t guest_clock;
uint64_t machine_cart_stamp(void) { return guest_clock; }
static unsigned word_access, parity;
static void wire(unsigned scl,unsigned sda) {
    guest_clock+=101;
    if(RR_MD_EEPROM_WIRING==3) {
        gbus_write8(&fixture_bus,0x200001,(uint8_t)sda);
        gbus_write8(&fixture_bus,0x200000,(uint8_t)scl);
    } else if(word_access)gbus_write16(&fixture_bus,0x200000,(uint16_t)((scl<<1)|sda));
    else {
        unsigned a=RR_MD_EEPROM_WIRING==1?0x200001:0x200000+(parity++&1);
        gbus_write8(&fixture_bus,a,(uint8_t)((scl<<1)|sda));
    }
}
static unsigned out(void) {
    unsigned bit=RR_MD_EEPROM_WIRING==2?2:1;
    unsigned value=gbus_read8(&fixture_bus,0x200001)&bit;
    CHECK((gbus_read8(&fixture_bus,0x200000)&bit)==value);
    CHECK((gbus_read16(&fixture_bus,0x200000)&bit)==value);
    CHECK(gbus_peek8(&fixture_bus,0x200001)==gbus_read8(&fixture_bus,0x200001));
    fixture_bus.z80_bank=0x40;CHECK((gbus_z80_read(&fixture_bus,0x8001)&bit)==value);
    return !!value;
}
static void start(void) { wire(0,1);wire(1,1);wire(1,0);wire(0,0); }
static void stop(void) { wire(0,0);wire(1,0);wire(1,1); }
static unsigned send(unsigned value) {
    for(unsigned i=0;i<8;++i) { unsigned b=(value>>(7-i))&1;wire(0,b);wire(1,b);wire(0,b); }
    wire(0,1);wire(1,1);unsigned ack=!out();wire(0,1);return ack;
}
static unsigned receive(void) {
    unsigned value=0;
    for(unsigned i=0;i<8;++i) { wire(0,1);wire(1,1);value=(value<<1)|out();wire(0,1); }
    wire(0,1);wire(1,1);wire(0,1);return value;
}
static void write_byte(unsigned address,unsigned value) {
    start();CHECK(send(RR_MD_EEPROM_KIND==1?address<<1:0xa0|((address>>7)&2)));
    if(RR_MD_EEPROM_KIND!=1)CHECK(send(address&255));
    CHECK(send(value));stop();
}
static unsigned read_byte(unsigned address) {
    if(RR_MD_EEPROM_KIND!=1) {
        start();CHECK(send(0xa0|((address>>7)&2)));CHECK(send(address&255));
    }
    start();CHECK(send(RR_MD_EEPROM_KIND==1?(address<<1)|1:0xa1|((address>>7)&2)));
    unsigned value=receive();stop();return value;
}
int wmain(int argc,wchar_t **argv) {
    gbus_init(&fixture_bus,NULL);gbus_sram_setup(&fixture_bus);rr_md_cart_setup(&fixture_bus);
    CHECK(fixture_bus.sram_size==rr_ee_size(RR_MD_EEPROM_KIND) && !fixture_bus.sram_stride);
    CHECK(rr_md_cart_valid(rr_md_cart_state()));
    if(argc>1) {
        CHECK(argc==3 && rr_md_battery_open(&fixture_bus,argv[2]));
        if(!wcscmp(argv[1],L"write")) {
            write_byte(0x63,0x96);CHECK(fixture_bus.sram[0x63]==0xff);
            /* Host flushing before programming finishes cannot persist staged bytes. */
            CHECK(rr_md_battery_flush(&fixture_bus,20000,true));CHECK(GetFileAttributesW(argv[2])==INVALID_FILE_ATTRIBUTES);
            guest_clock+=rr_md_cart_state()->eeprom.write_ticks;
            rr_md_cart_advance(&fixture_bus,guest_clock);CHECK(fixture_bus.sram[0x63]==0x96);
        } else if(!wcscmp(argv[1],L"read"))CHECK(read_byte(0x63)==0x96);
        else CHECK(!wcscmp(argv[1],L"clean"));
        CHECK(rr_md_battery_flush(&fixture_bus,30000,true));
    } else {
        CHECK(!rr_md_cart_legacy_allowed());
        if(RR_MD_EEPROM_WIRING==1) { RrMdCartState old=*rr_md_cart_state();
            gbus_write8(&fixture_bus,0x200000,0);CHECK(!memcmp(&old,rr_md_cart_state(),sizeof old)); }
        for(word_access=0;word_access<2;++word_access) {
            if(RR_MD_EEPROM_WIRING==3) {
                g_rom[0x200000]=0xb1;g_rom[0x200001]=0xc6;
                gbus_write16(&fixture_bus,0x200000,1);CHECK(gbus_read16(&fixture_bus,0x200000)==0xb1c6);
                gbus_write16(&fixture_bus,0x200000,0);CHECK(gbus_read16(&fixture_bus,0x200000)==1);
            }
            unsigned address=word_access?0x53:0x63;
            write_byte(address,0x96+word_access);CHECK(fixture_bus.sram[address]==0xff);
            RrMdCartState saved=*rr_md_cart_state(),bad=saved;
            bad.eeprom.address=0xffff;CHECK(!rr_md_cart_restore(&bad));
            CHECK(!memcmp(&saved,rr_md_cart_state(),sizeof saved));
            guest_clock+=saved.eeprom.write_ticks-1;
            rr_md_cart_advance(&fixture_bus,guest_clock);CHECK(fixture_bus.sram[address]==0xff);
            CHECK(rr_md_cart_restore(&saved));
            rr_md_cart_advance(&fixture_bus,++guest_clock);CHECK(fixture_bus.sram[address]==0x96+word_access);
            CHECK(read_byte(address)==0x96+word_access);
            gbus_write8(&fixture_bus,0xa130f1,1);CHECK(!fixture_bus.sram_enabled);
        }
    }
    printf("{\"checks\":%u,\"passed\":true,\"actual_68000_z80_bus\":true}\n",checks);return 0;
}
