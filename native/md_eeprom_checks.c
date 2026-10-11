/* Independent bus-master fixtures: manufacturer wire transactions, no ROM. */
#include <stdio.h>
#include <stdlib.h>
#include "md_eeprom.h"
static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x); exit(1); } } while(0)
static RrMdEeprom chip, resumed;
static uint8_t memory[512], replay[512];
static uint64_t clock_tick;
static unsigned hz;
static void wire(unsigned scl,unsigned sda) {
    /* Portable chip state copied at EVERY edge, then continued independently. */
    memcpy(&resumed,&chip,sizeof chip); memcpy(replay,memory,sizeof memory);
    clock_tick += 311;
    rr_ee_lines(&chip,memory,clock_tick,scl,sda);
    rr_ee_lines(&resumed,replay,clock_tick,scl,sda);
    CHECK(!memcmp(&chip,&resumed,sizeof chip) && !memcmp(memory,replay,sizeof memory));
    if(!rr_ee_valid(&chip,chip.kind,hz))fprintf(stderr,"kind=%u phase=%u bits=%u addr=%u page=%u mask=%u busy=%llu\n",chip.kind,chip.phase,chip.bits,chip.address,chip.page_base,chip.pending_mask,(unsigned long long)chip.busy_left);
    CHECK(rr_ee_valid(&chip,chip.kind,hz));
}
static void start(void) { wire(0,1);wire(1,1);wire(1,0);wire(0,0); }
static void stop(void) { wire(0,0);wire(1,0);wire(1,1); }
static unsigned send(unsigned value) {
    for (unsigned i=0;i<8;++i) { unsigned bit=(value>>(7-i))&1;wire(0,bit);wire(1,bit);wire(0,bit); }
    wire(0,1);wire(1,1);unsigned ack=!rr_ee_out(&chip);wire(0,1);return ack;
}
static unsigned receive(unsigned ack) {
    unsigned value=0;
    for(unsigned i=0;i<8;++i) { wire(0,1);wire(1,1);value=(value<<1)|rr_ee_out(&chip);wire(0,1); }
    wire(0,!ack);wire(1,!ack);wire(0,!ack);wire(0,1);return value;
}
static unsigned command(unsigned address,unsigned read) {
    return chip.kind==1 ? (address<<1)|read : 0xa0|((address>>7)&2)|read;
}
static void address_write(unsigned address) {
    start();CHECK(send(command(address,0)));
    if(chip.kind!=1)CHECK(send(address&255));
}
static void address_read(unsigned address) {
    if(chip.kind!=1)address_write(address);
    start();CHECK(send(command(address,1)));
}
static void wait_write(void) {
    CHECK(chip.busy_left && chip.pending_mask);
    RrMdEeprom before=chip;
    rr_ee_advance(&chip,memory,clock_tick+chip.busy_left-1);clock_tick=chip.last_tick;
    CHECK(chip.busy_left==1 && chip.completed_writes==before.completed_writes);
    rr_ee_advance(&chip,memory,++clock_tick);CHECK(!chip.busy_left && !chip.pending_mask);
}
static void suite(unsigned kind,unsigned rate) {
    hz=rate;clock_tick=0;memset(memory,0xff,sizeof memory);rr_ee_init(&chip,kind,hz);
    unsigned size=rr_ee_size(kind),page=rr_ee_page(kind);
    for(unsigned a=0;a<size;++a) {
        unsigned value=(a*73+0x96)&255;address_write(a);CHECK(send(value));
        CHECK(memory[a]==0xff);stop();wait_write();
        CHECK(memory[a]==value);address_read(a);CHECK(receive(0)==value);stop();
    }
    for(unsigned a=0;a<size;++a) {
        address_read(a);CHECK(receive(1)==((a*73+0x96)&255));
        CHECK(receive(0)==((((a+1)%size)*73+0x96)&255));stop();
    }
    memset(memory,0x77,sizeof memory);
    address_write(page-1);
    for(unsigned n=0;n<page+3;++n)CHECK(send(0xa0+n));
    CHECK(memory[0]==0x77);stop();
    /* Poll at the same guest time while busy: the address must be NACKed. */
    uint64_t deadline=clock_tick+chip.busy_left;
    start();CHECK(!send(command(0,0)));stop();
    rr_ee_advance(&chip,memory,deadline);clock_tick=deadline;
    for(unsigned n=0;n<page;++n) {
        unsigned last=n;
        while(last+page<page+3)last+=page;
        CHECK(memory[(page-1+n)%page]==0xa0+last);
    }
    CHECK(memory[page]==0x77);
    /* Interrupted receive and dummy address writes never program memory. */
    unsigned unchanged=memory[9];
    address_write(9);wire(0,1);wire(1,1);wire(0,1);stop();
    CHECK(!chip.busy_left && memory[9]==unchanged);
    address_write(7);start();CHECK(send(command(7,1)));CHECK(receive(0)==memory[7]);stop();
    CHECK(!chip.busy_left);
    if(kind!=1) { start();CHECK(!send(0xb0));stop(); }
    /* Self-held ACK is not a false START when the host changes its output. */
    RrMdEeprom valid=chip,bad=chip;bad.address=(uint16_t)size;CHECK(!rr_ee_valid(&bad,kind,hz));
    if(page<16) { bad=valid;bad.pending_mask=(uint16_t)(1u<<page);CHECK(!rr_ee_valid(&bad,kind,hz)); }
    bad=valid;bad.busy_left=chip.write_ticks+1;CHECK(!rr_ee_valid(&bad,kind,hz));
    bad=valid;bad.phase=RR_EE_READ;bad.bits=8;bad.scl=0;CHECK(!rr_ee_valid(&bad,kind,hz));
    bad.scl=1;CHECK(rr_ee_valid(&bad,kind,hz));
    bad.phase=RR_EE_COMMAND;CHECK(!rr_ee_valid(&bad,kind,hz));
    bad.phase=RR_EE_ADDRESS;CHECK(!rr_ee_valid(&bad,kind,hz));
    bad.phase=RR_EE_WRITE;CHECK(!rr_ee_valid(&bad,kind,hz));
}
int main(void) {
    for(unsigned kind=1;kind<=3;++kind) { suite(kind,53693175);suite(kind,53203424); }
    printf("{\"checks\":%u,\"passed\":true,\"independent_wire_fixtures\":true,\"physical_chip_measured\":false}\n",checks);
    return 0;
}
