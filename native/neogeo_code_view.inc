/* Side-effect-free code mapping in Geolith's private board translation unit.
 * Original RetroRecomp contributions: MIT. Actual reads/writes still use the
 * pinned board handlers; this view never consumes a protection response. */
#include <string.h>
#include <stdbool.h>
static int rr_ng_code_before_port(uint32_t address,uint32_t port,unsigned bytes,uint32_t *boundary) {
    if(address>=port && address-port<bytes)return 0;
    if(address<port && port-address<*boundary)*boundary=port-address;
    return 1;
}
static int rr_ng_cart_code_known(void) {
    return boardtype==BOARD_DEFAULT || boardtype==BOARD_LINKABLE || boardtype==BOARD_CT0 ||
           boardtype==BOARD_KOF98 || boardtype==BOARD_SMA ||
           boardtype==BOARD_MSLUGX || boardtype==BOARD_PVC;
}
/* PVC RAM is volatile protection/bank state, not battery-backed SRAM. The
 * pinned serializer only includes battery RAM; keep this separate predicate. */
bool rr_ng_board_cart_state(void) {return ngsys.sram_present || boardtype==BOARD_PVC;}
int rr_ng_code_location(uint32_t address,RrM68000CodeLocation *out) {
    if(!out || !romdata || ngsys.cdmode)return 0;
    address&=0xffffffu;
    uint32_t region=0,offset=0,size=0,boundary=0;unsigned mutable_code=0;
    if(address<0x80u && !vectable) {
        region=RR_M68000_CODE_BIOS;offset=address;size=(uint32_t)romdata->bsz;boundary=0x80u-address;
    } else if(address<0x100000u) {
        if(!rr_ng_cart_code_known())return 0;
        region=RR_M68000_CODE_CART;offset=address;size=(uint32_t)romdata->psz;boundary=0x100000u-address;
        if(boardtype==BOARD_KOF98) {
            /* Only the four header bytes are overlaid by the protection write.
             * No immutable instruction may straddle this mutable island. */
            if(address<0x100u)boundary=0x100u-address;
            else if(address<0x104u) {boundary=0x104u-address;mutable_code=1;}
        }
    } else if(address<0x200000u) {
        region=RR_M68000_CODE_RAM;offset=address&0xffffu;size=0x10000u;boundary=size-offset;mutable_code=1;
    } else if(address<0x300000u) {
        if(!rr_ng_cart_code_known())return 0;
        region=RR_M68000_CODE_CART;offset=(address&0xfffffu)+banksw_addr;
        size=(uint32_t)romdata->psz;boundary=0x300000u-address;
        if(boardtype==BOARD_LINKABLE) {
            /* The link status byte at 0x200000 toggles cartreg[0]. Keep
             * this word outside code guards; ordinary P ROM stays native. */
            if(!rr_ng_code_before_port(address,0x200000,2,&boundary))return 0;
        } else if(boardtype==BOARD_CT0) {
            static const uint32_t ports[]={0x200000,0x236000,0x236004,0x236008,
                                          0x23600c,0x255550,0x2ff000,0x2ffff0};
            for(unsigned n=0;n<sizeof ports/sizeof *ports;++n)
                if(!rr_ng_code_before_port(address,ports[n],2,&boundary))return 0;
        } else if(boardtype==BOARD_SMA) {
            if(!rr_ng_code_before_port(address,0x2fe446,2,&boundary))return 0;
            for(unsigned n=0;n<2;++n)
                if(!rr_ng_code_before_port(address,sma_prn_addr[n],2,&boundary))return 0;
        } else if(boardtype==BOARD_MSLUGX) {
            /* A real response read advances cartreg[1]. Guards must never
             * read this challenge window, even with the command inactive. */
            if(!rr_ng_code_before_port(address,0x2fffe0,16,&boundary))return 0;
        } else if(boardtype==BOARD_PVC) {
            /* The upper 8 KiB is cartridge RAM, including colour protection
             * and bank registers. It is never immutable P ROM. */
            if(!rr_ng_code_before_port(address,0x2fe000,0x2000,&boundary))return 0;
        }
    } else if(address>=0xc00000u && address<0xd00000u) {
        region=RR_M68000_CODE_BIOS;offset=address&0x1ffffu;size=(uint32_t)romdata->bsz;boundary=0x20000u-offset;
    } else return 0;
    if(offset>=size)return 0;
    out->region=region;out->physical_offset=offset;
    out->available_bytes=size-offset<boundary?size-offset:boundary;out->mutable_code=mutable_code;
    return 1;
}
int rr_ng_code_word(uint32_t pc,uint16_t *word) {
    RrM68000CodeLocation loc;
    if(!word || (pc&1u) || !rr_ng_code_location(pc,&loc) || loc.available_bytes<2)return 0;
    const uint8_t *data=loc.region==RR_M68000_CODE_CART?romdata->p:
                        loc.region==RR_M68000_CODE_BIOS?romdata->b:ram;
    *word=read16((uint8_t*)data,loc.physical_offset);return 1;
}
/* Use the bounded mapping resolved immediately before dispatch. No emulated
 * bus operation may occur between resolving it and this complete word guard.
 * Reuse that mapping, never a cached validation from an earlier instruction. */
int rr_ng_code_matches(const RrM68000CodeLocation *loc,const uint16_t *words,unsigned count) {
    if(!loc || !words || !romdata || !count || count>8 ||
       (loc->physical_offset&1u) || count*2u>loc->available_bytes)return 0;
    const uint8_t *data;size_t size;
    if(loc->region==RR_M68000_CODE_CART) {data=romdata->p;size=romdata->psz;}
    else if(loc->region==RR_M68000_CODE_BIOS) {data=romdata->b;size=romdata->bsz;}
    else if(loc->region==RR_M68000_CODE_RAM) {data=ram;size=sizeof ram;}
    else return 0;
    if(!data || loc->physical_offset>=size || count*2u>size-loc->physical_offset)return 0;
    for(unsigned n=0;n<count;++n)
        if(read16((uint8_t*)data,loc->physical_offset+n*2u)!=words[n])return 0;
    return 1;
}
/* The pinned serializer omits the SMA PRN and cannot reconstruct a KOF98
 * overlay after an unrelated last protection write. Store device latches,
 * never P-ROM bytes or host pointers, in the frame-state extension. */
size_t rr_ng_board_extra_save(uint8_t *data,size_t size) {
    if(!data || size<16)return 0;
    memset(data,0,16);memcpy(data,"NGB1",4);data[4]=(uint8_t)boardtype;
    if(boardtype==BOARD_KOF98)data[5]=rr_ng_kof98_overlay;
    if(boardtype==BOARD_SMA) {data[6]=(uint8_t)sma_prn;data[7]=(uint8_t)(sma_prn>>8);}
    data[8]=(uint8_t)rr_ng_sound_latch();
    return 16;
}
bool rr_ng_board_extra_valid(const uint8_t *data,size_t size) {
    if(!data || size!=16 || memcmp(data,"NGB1",4) || data[4]!=boardtype || data[5]>1 ||
       (boardtype!=BOARD_KOF98 && data[5]) || (boardtype!=BOARD_SMA && (data[6] || data[7])))return false;
    if(data[8]>1)return false;
    for(unsigned n=9;n<16;++n)if(data[n])return false;
    return true;
}
bool rr_ng_board_extra_restore(const uint8_t *data,size_t size) {
    if(!rr_ng_board_extra_valid(data,size))return false;
    rr_ng_sound_latch_restore(data[8]);
    if(boardtype==BOARD_SMA)sma_prn=(uint16_t)(data[6]|((unsigned)data[7]<<8));
    if(boardtype==BOARD_KOF98) {
        uint16_t last_write=cartreg[0];
        geo_m68k_write_banksw_16_kof98(0x20aaaa,data[5]?0x0090:0x00f0);
        cartreg[0]=last_write;
    }
    return true;
}
