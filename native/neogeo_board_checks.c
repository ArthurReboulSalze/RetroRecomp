/* Authored board/guard fixtures against the pinned real board handlers.
 * All ROM bytes below are synthetic. No original cartridge or BIOS is used. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "neogeo_reference.h"
#include "engine/geo_m68k.c"
static unsigned checks;
static void require(int okay,const char *name) {
    ++checks;if(!okay) {fprintf(stderr,"Neo Geo board check: %s\n",name);exit(2);}
}
static void silent(int level,const char *format,...) {(void)level;(void)format;}
static void mapping(uint32_t address,unsigned region,uint32_t offset,unsigned mutable_code) {
    RrM68000CodeLocation loc={0};uint16_t word=0;
    require(rr_ng_code_location(address,&loc),"mapped location");
    require(loc.region==region && loc.physical_offset==offset && loc.mutable_code==mutable_code,"physical identity");
    require(rr_ng_code_word(address,&word),"guarded word");
    uint16_t expected=region==RR_M68000_CODE_BIOS?read16(romdata->b,offset):
        region==RR_M68000_CODE_RAM?read16(ram,offset):address<0x100000?
        geo_m68k_read_fixed_16(address):geo_m68k_read_banksw_16(address);
    require(word==expected,"guard matches actual pinned read handler");
    require(rr_ng_code_matches(&loc,&word,1),"resolved span checks actual word");
    if(loc.available_bytes>=4) {
        uint16_t pair[2]={word,0};require(rr_ng_code_word(address+2,&pair[1]),"extension is mapped");
        require(rr_ng_code_matches(&loc,pair,2),"resolved span checks complete extension");
        pair[1]^=1;require(!rr_ng_code_matches(&loc,pair,2),"changed extension cannot pass guard");
    }
    word^=1;require(!rr_ng_code_matches(&loc,&word,1),"resolved span rejects modified instruction");
    require(!rr_ng_code_matches(&loc,&word,0),"resolved span rejects empty instruction");
    loc.available_bytes=1;require(!rr_ng_code_matches(&loc,&expected,1),"resolved span respects device boundary");
}
int main(void) {
    geo_log_set_callback(silent);geo_set_system(SYSTEM_MVS);rr_ng_reference_bind();geo_init();
    romdata_t *r=geo_romdata_ptr();r->psz=0x900000;r->p=malloc(r->psz);
    r->bsz=0x20000;r->b=malloc(r->bsz);
    r->msz=r->smsz=r->ssz=r->sfixsz=0x20000;
    r->m=r->sm=r->s=r->sfix=calloc(0x20000,1);
    require(r->p && r->b && r->m,"synthetic allocation");
    for(unsigned n=0;n<r->psz;++n)r->p[n]=(uint8_t)(n*73u+(n>>16)*31u);
    for(unsigned n=0;n<r->bsz;++n)r->b[n]=(uint8_t)(n*29u+11u);
    for(unsigned n=0;n<sizeof ram;++n)ram[n]=(uint8_t)(n*17u+7u);
    static const unsigned boards[]={BOARD_DEFAULT,BOARD_CT0,BOARD_KOF98,BOARD_SMA,BOARD_MSLUGX,BOARD_PVC};
    for(unsigned b=0;b<sizeof boards/sizeof *boards;++b) {
        geo_m68k_board_set(boards[b]);banksw_addr=0x123400;vectable=0;
        mapping(0,RR_M68000_CODE_BIOS,0,0);mapping(0xc60200,RR_M68000_CODE_BIOS,0x200,0);
        vectable=1;mapping(0,RR_M68000_CODE_CART,0,0);
        mapping(0x400,RR_M68000_CODE_CART,0x400,0);
        mapping(0x200400,RR_M68000_CODE_CART,0x123800,0);
        mapping(0x10fc00,RR_M68000_CODE_RAM,0xfc00,1);
        mapping(0x1afc00,RR_M68000_CODE_RAM,0xfc00,1);
    }
    RrM68000CodeLocation loc={0};uint16_t word=0;
    geo_m68k_board_set(BOARD_CT0);banksw_addr=0x100000;protreg=0x81422418;
    static const uint32_t ct0[]={0x200000,0x236000,0x236004,0x236008,0x23600c,0x255550,0x2ff000,0x2ffff0};
    for(unsigned n=0;n<sizeof ct0/sizeof *ct0;++n) {
        uint32_t saved=protreg;
        require(!rr_ng_code_location(ct0[n],&loc) && !rr_ng_code_word(ct0[n],&word),"CT0 response is not code ROM");
        require(protreg==saved,"CT0 guard has no protection side effect");
        if(ct0[n]>0x200000)require(rr_ng_code_location(ct0[n]-2,&loc) && loc.available_bytes==2,"clip instruction before CT0 response");
        mapping(ct0[n]+2,RR_M68000_CODE_CART,0x100000+(ct0[n]+2-0x200000),0);
    }
    geo_m68k_board_set(BOARD_SMA);sma_prn_addr[0]=0x2ffff8;sma_prn_addr[1]=0x2ffffa;sma_prn=0x2345;
    static const uint32_t sma[]={0x2fe446,0x2ffff8,0x2ffffa};
    for(unsigned n=0;n<3;++n) {
        uint16_t saved=sma_prn;
        require(!rr_ng_code_word(sma[n],&word) && sma_prn==saved,"SMA guard never consumes PRN/presence");
        if(n!=2)require(rr_ng_code_location(sma[n]-2,&loc) && loc.available_bytes==2,"clip instruction before SMA port");
    }
    require(geo_m68k_read_banksw_16_sma(0x2fe446)==0x9a37,"actual SMA presence read retained");
    uint16_t saved=sma_prn;geo_m68k_read_banksw_16_sma(sma_prn_addr[0]);
    require(sma_prn!=saved,"actual SMA PRN read still advances");
    geo_m68k_board_set(BOARD_KOF98);memcpy(r->p+0x100,"NEO-",4);
    geo_m68k_write_banksw_16_kof98(0x20aaaa,0x0090);
    mapping(0x100,RR_M68000_CODE_CART,0x100,1);
    require(read16(r->p,0x100)==0x00c2 && read16(r->p,0x102)==0x00fd,"actual KOF98 overlay applied");
    require(rr_ng_code_location(0xfe,&loc) && loc.available_bytes==2,"immutable opcode cannot straddle overlay");
    geo_m68k_write_banksw_16_kof98(0x20aaaa,0x00f0);
    require(!memcmp(r->p+0x100,"NEO-",4),"actual KOF98 overlay disabled");
    boardtype=BOARD_BREZZASOFT;
    require(!rr_ng_code_location(0x200,&loc) && !rr_ng_code_location(0x200400,&loc),"unknown cart mapping stays fallback");
    mapping(0xc00200,RR_M68000_CODE_BIOS,0x200,0);mapping(0x10fc00,RR_M68000_CODE_RAM,0xfc00,1);
    boardtype=BOARD_DEFAULT;banksw_addr=(uint32_t)r->psz-2;
    require(rr_ng_code_location(0x200000,&loc) && loc.available_bytes==2,"end of physical ROM bound");
    require(!rr_ng_code_word(0x200002,&word) && !rr_ng_code_word(0x200001,&word),"out of bounds and odd word rejected");
    /* The next random response is guest state, not host-only scratch. */
    uint8_t state[80000]={0};geo_m68k_board_set(BOARD_SMA);sma_prn=0x2345;
    uint8_t extra[16];geo_serial_begin();geo_m68k_state_save(state);
    require(rr_ng_board_extra_save(extra,sizeof extra)==16,"SMA device latches captured");
    uint16_t expected=geo_m68k_read_banksw_16_sma(sma_prn_addr[0]);
    for(unsigned n=0;n<7;++n)geo_m68k_read_banksw_16_sma(sma_prn_addr[0]);
    geo_serial_begin();geo_m68k_state_load(state);
    require(rr_ng_board_extra_restore(extra,sizeof extra),"SMA device latches restored");
    require(geo_m68k_read_banksw_16_sma(sma_prn_addr[0])==expected,"SMA random sequence survives state restore");
    geo_m68k_board_set(BOARD_KOF98);geo_m68k_write_banksw_16_kof98(0x20aaaa,0x0090);
    geo_m68k_write_banksw_16_kof98(0x20aaaa,0x1234);
    geo_serial_begin();geo_m68k_state_save(state);rr_ng_board_extra_save(extra,sizeof extra);
    geo_m68k_write_banksw_16_kof98(0x20aaaa,0x00f0);
    geo_serial_begin();geo_m68k_state_load(state);rr_ng_board_extra_restore(extra,sizeof extra);
    require(cartreg[0]==0x1234 && read16(r->p,0x100)==0x00c2,"KOF98 overlay survives unrelated last write and load");
    geo_m68k_write_banksw_16_kof98(0x20aaaa,0x00f0);geo_serial_begin();geo_m68k_state_save(state);rr_ng_board_extra_save(extra,sizeof extra);
    geo_m68k_write_banksw_16_kof98(0x20aaaa,0x0090);geo_serial_begin();geo_m68k_state_load(state);rr_ng_board_extra_restore(extra,sizeof extra);
    require(!memcmp(r->p+0x100,"NEO-",4),"loading inactive overlay clears the previous process overlay");
    for(unsigned n=0;n<16;++n) {
        uint8_t bad[16];memcpy(bad,extra,16);bad[n]=255;
        require(!rr_ng_board_extra_restore(bad,16) && !memcmp(r->p+0x100,"NEO-",4),"invalid board extension rejected without mutation");
    }
    geo_m68k_board_set(BOARD_MSLUGX);banksw_addr=0x100000;
    geo_m68k_write_banksw_16_mslugx(0x2fffea,0);geo_m68k_write_banksw_16_mslugx(0x2fffe2,1);
    for(unsigned address=0x2fffe0;address<0x2ffff0;address+=2) {
        uint16_t before=cartreg[1];
        require(!rr_ng_code_location(address,&loc) && !rr_ng_code_word(address,&word),"Metal Slug X challenge is not code ROM");
        require(cartreg[1]==before,"Metal Slug X guard never advances response counter");
    }
    require(rr_ng_code_location(0x2fffde,&loc) && loc.available_bytes==2,"Metal Slug X instruction clipped before challenge");
    geo_serial_begin();geo_m68k_state_save(state);
    uint16_t response=geo_m68k_read_banksw_16_mslugx(0x2fffe0),counter=cartreg[1];
    for(unsigned n=0;n<17;++n)geo_m68k_read_banksw_16_mslugx(0x2fffe2);
    geo_serial_begin();geo_m68k_state_load(state);
    require(geo_m68k_read_banksw_16_mslugx(0x2fffe0)==response && cartreg[1]==counter,"Metal Slug X next response survives restore");
    geo_m68k_write_banksw_16_mslugx(0x2ffff0,2);
    mapping(0x200400,RR_M68000_CODE_CART,0x300400,0);
    geo_m68k_board_set(BOARD_PVC);ngsys.sram_present=0;banksw_addr=0x100000;
    require(rr_ng_board_cart_state() && !ngsys.sram_present,"PVC state retained without mislabelling battery RAM");
    memset(ngsys.cartram,0,sizeof ngsys.cartram);
    for(unsigned address=0x2fe000;address<0x300000;address+=0x100) {
        require(!rr_ng_code_location(address,&loc) && !rr_ng_code_word(address,&word),"PVC RAM and registers are not immutable ROM");
    }
    require(rr_ng_code_location(0x2fdffe,&loc) && loc.available_bytes==2,"PVC instruction clipped before cartridge RAM");
    geo_m68k_write_banksw_16_pvc(0x2fffe0,0xace5);
    uint16_t bluegreen=geo_m68k_read_banksw_16_pvc(0x2fffe2),redshade=geo_m68k_read_banksw_16_pvc(0x2fffe4);
    uint8_t protected_ram[8192];memcpy(protected_ram,ngsys.cartram,sizeof protected_ram);
    require(!rr_ng_code_word(0x2fffe2,&word) && !memcmp(protected_ram,ngsys.cartram,sizeof protected_ram),"PVC guard preserves palette/protection RAM");
    geo_m68k_write_banksw_16_pvc(0x2fffe8,bluegreen);geo_m68k_write_banksw_16_pvc(0x2fffea,redshade);
    require(geo_m68k_read_banksw_16_pvc(0x2fffec)==0xace5,"PVC real palette pack/unpack roundtrip");
    geo_m68k_write_banksw_16_pvc(0x2ffff0,0x0000);geo_m68k_write_banksw_16_pvc(0x2ffff2,0x0234);
    uint32_t bank=banksw_addr;require(bank==0x123400,"PVC sub-megabyte bank offset retained");
    mapping(0x200400,RR_M68000_CODE_CART,bank+0x400,0);
    const uint8_t *raw=geo_state_save_raw();size_t full_size=geo_state_size();
    uint8_t *full=malloc(full_size);require(full!=NULL,"PVC synthetic state allocation");memcpy(full,raw,full_size);
    memcpy(protected_ram,ngsys.cartram,sizeof protected_ram);
    geo_m68k_write_banksw_16_pvc(0x2ffff2,0x0004);memset(ngsys.cartram,0x3c,sizeof ngsys.cartram);
    require(geo_state_load_raw(full) && banksw_addr==bank && !memcmp(protected_ram,ngsys.cartram,sizeof protected_ram),"PVC bank and all protection RAM restored together");
    free(full);mapping(0x200400,RR_M68000_CODE_CART,bank+0x400,0);
    printf("{\"passed\":true,\"mapping_and_protection_checks\":%u,\"synthetic_inputs_only\":true}\n",checks);
    geo_deinit();free(r->p);free(r->b);free(r->m);return 0;
}
