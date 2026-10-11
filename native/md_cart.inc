/* Included in the adapted bus. Wiring follows published cartridge circuit
 * identities, not a guessed name or an emulator's serial implementation. */
#include "md_cart.h"
static RrMdCartState rr_cart;
static const uint8_t *rr_cart_rom;
static size_t rr_cart_rom_size;
uint32_t rr_md_rom_fetch_offset=UINT32_MAX;
void rr_md_cart_attach_rom(const uint8_t *rom,size_t size) { rr_cart_rom=rom;rr_cart_rom_size=size; }
static void rr_cart_map(unsigned slot) {
    if(!RR_MD_SEGA_MAPPER || !rr_cart_rom)return;
    size_t offset=(size_t)rr_cart.pages[slot]<<19;
    size_t bytes=offset<rr_cart_rom_size?rr_cart_rom_size-offset:0;
    if(bytes>0x80000u)bytes=0x80000u;
    if(bytes)memcpy(g_rom+(slot<<19),rr_cart_rom+offset,bytes);
    if(bytes<0x80000u)memset(g_rom+(slot<<19)+bytes,0xff,0x80000u-bytes);
}
uint32_t rr_md_cart_rom_offset(uint32_t pc) {
    if(pc>=0x400000u)return UINT32_MAX;
    return RR_MD_SEGA_MAPPER?((uint32_t)rr_cart.pages[pc>>19]<<19)|(pc&0x7ffffu):pc;
}
static int rr_cart_code_matches(uint32_t offset,const uint16_t *words,unsigned count) {
    if(!rr_cart_rom || !count || offset>=rr_cart_rom_size || count*2u>rr_cart_rom_size-offset)return 0;
    for(unsigned i=0;i<count;++i)if(((unsigned)rr_cart_rom[offset+i*2]<<8|rr_cart_rom[offset+i*2+1])!=words[i])return 0;
    return 1;
}
uint32_t rr_md_cart_code_offset(uint32_t pc,const uint16_t *words,unsigned count) {
    uint32_t current=rr_md_cart_rom_offset(pc);
    if(!RR_MD_SEGA_MAPPER)return current;
    if(current==UINT32_MAX)return current;
    if(rr_cart_code_matches(current,words,count))return current;
    /* Already fetched words can outlive a register write. Learn their actual
     * physical image, never the newly selected page's unrelated bytes. */
    for(uint32_t page=0;page<rr_cart_rom_size;page+=0x80000u) {
        uint32_t offset=page+(pc&0x7ffffu);
        if(rr_cart_code_matches(offset,words,count))return offset;
    }
    return UINT32_MAX;
}
void rr_md_cart_setup(GenesisBus *bus) {
    memset(&rr_cart,0,sizeof rr_cart);
    rr_ee_init(&rr_cart.eeprom,RR_MD_EEPROM_KIND,RR_MD_MASTER_HZ);
    rr_cart.mapper=RR_MD_SEGA_MAPPER;
    for(unsigned i=0;i<8;++i)rr_cart.pages[i]=(uint8_t)i;
    for(unsigned i=0;i<8;++i)rr_cart_map(i);
    if(RR_MD_EEPROM_KIND) {
        /* The nonvolatile bytes use the existing portable/battery buffer;
         * stride zero explicitly prevents access as parallel SRAM. */
        unsigned size=rr_ee_size(RR_MD_EEPROM_KIND);
        memset(bus->sram,0xff,sizeof bus->sram);
        bus->sram_present=bus->sram_battery=1;
        bus->sram_enabled=bus->sram_stride=0;
        bus->sram_size=size;bus->sram_base=0x200000u;bus->sram_end=0x200000u+size-1;
    }
}
void rr_md_cart_advance(GenesisBus *bus,uint64_t now) {
    if(RR_MD_EEPROM_KIND)rr_ee_advance(&rr_cart.eeprom,bus->sram,now);
}
const RrMdCartState *rr_md_cart_state(void) { return &rr_cart; }
int rr_md_cart_valid(const RrMdCartState *state) {
    if(!rr_ee_valid(&state->eeprom,RR_MD_EEPROM_KIND,RR_MD_MASTER_HZ) ||
       state->acclaim_rom>1 || state->mapper!=RR_MD_SEGA_MAPPER || state->pages[0])return 0;
    if(RR_MD_EEPROM_WIRING!=3 && state->acclaim_rom)return 0;
    for(unsigned i=0;i<8;++i)if(!RR_MD_SEGA_MAPPER && state->pages[i]!=i)return 0;
    for(unsigned i=0;i<sizeof state->reserved;++i)if(state->reserved[i])return 0;
    return 1;
}
int rr_md_cart_restore(const RrMdCartState *state) {
    if(!rr_md_cart_valid(state))return 0;rr_cart=*state;
    for(unsigned i=0;i<8;++i)rr_cart_map(i);return 1;
}
int rr_md_cart_legacy_allowed(void) { return !RR_MD_EEPROM_KIND && !RR_MD_SEGA_MAPPER; }
static int rr_cart_serial_range(uint32_t a) {
    return RR_MD_EEPROM_KIND && a>=0x200000u &&
        a<(RR_MD_EEPROM_WIRING==3?0x300000u:0x400000u);
}
static int rr_cart_read(GenesisBus *bus,uint32_t a,unsigned *value,int peek) {
    if(!rr_cart_serial_range(a) || (RR_MD_EEPROM_WIRING==3 && rr_cart.acclaim_rom))return 0;
    if(!peek)rr_md_cart_advance(bus,machine_cart_stamp());
    *value=rr_ee_out(&rr_cart.eeprom)<<(RR_MD_EEPROM_WIRING==2?1:0);return 1;
}
static int rr_cart_write(GenesisBus *bus,uint32_t a,unsigned value,unsigned width) {
    if(RR_MD_SEGA_MAPPER && a>=0xa130f2u && a<=0xa130ffu) {
        if(width==2 || (a&1)) {
            unsigned slot=(a-0xa130f0u)>>1;
            rr_cart.pages[slot]=(uint8_t)value;rr_cart_map(slot);
        }
        return 1;
    }
    if(!rr_cart_serial_range(a))return 0;
    unsigned scl=(value>>1)&1,sda=value&1;
    if(RR_MD_EEPROM_WIRING==1 && width==1 && !(a&1))return 1;
    if(RR_MD_EEPROM_WIRING==3) {
        if(width==2) { rr_cart.acclaim_rom=(uint8_t)(value&1);return 1; }
        scl=a&1?rr_cart.eeprom.scl:value&1;
        sda=a&1?value&1:rr_cart.eeprom.host_sda;
    }
    rr_ee_lines(&rr_cart.eeprom,bus->sram,machine_cart_stamp(),scl,sda);return 1;
}
