/* Validate the pinned cartridge serializer before it can mutate the machine.
 * Identity and integrity are checked by the shared disk wrapper first. */
#include <stdint.h>
#include <stddef.h>
#include "geo.h"
#include "neogeo_host.h"
#include "neogeo_reference.h"
/* Constants from the pinned MVS scheduler and LSPC implementation. */
enum { MCYC_PER_FRAME=405504, DIV_YM2610=72, M68K_CYC_PER_LINE=768 };
static uint32_t be32(const uint8_t *p) {return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3];}
static unsigned be16(const uint8_t *p) {return (unsigned)p[0]<<8|p[1];}
bool rr_ng_core_state_valid(const uint8_t *data,size_t size) {
    if(!data || size!=geo_state_size() || size<220000 ||
       be32(data)!=0x47454f02 || data[4]!=geo_get_region() || data[5]!=geo_get_system())return false;
    /* Frame-boundary master/sound remainders and YM clock divider. */
    if(be32(data+6)>=MCYC_PER_FRAME || be32(data+10)>=MCYC_PER_FRAME || be32(data+14)>=DIV_YM2610)return false;
    size_t lspc=35+65536+2048+(rr_ng_board_cart_state()?8192:0)+6;
    size_t fields=lspc+65536+4096+16384;
    if(fields+20+116+65536+19>size)return false;
    if(data[fields]>1 || (be16(data+fields+3)!=0 && be16(data+fields+3)!=0x8000) ||
       data[fields+7]>7 || (data[fields+8]!=0 && data[fields+8]!=8) || data[fields+11]>1 ||
       be32(data+fields+12)>=264 || be32(data+fields+16)>=M68K_CYC_PER_LINE)return false;
    size_t cpu=fields+20;
    if(be32(data+cpu+104)>0x700 || (be32(data+cpu+104)&255) ||
       be32(data+cpu+108)>255 || be32(data+cpu+112)>1)return false;
    size_t latch=cpu+116+65536+12;
    /* Six boolean latches precede REG_POUTPUT, a full eight-bit joypad output
     * register (also mirrored by REG_SLOT in AES mode). */
    for(unsigned n=0;n<6;++n)if(data[latch+n]>1)return false;
    /* Fixed-size Z80 tail (the serializer includes one unused final byte). */
    size_t z=size-2101-1;
    if(data[z+28]>1 || data[z+29]>2)return false;
    for(unsigned n=31;n<=33;++n)if(data[z+n]>1)return false;
    if(data[z+34]>2 || data[z+35]>2 || data[z+36]>1)return false;
    return true;
}
