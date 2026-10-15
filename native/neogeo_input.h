#ifndef RR_NG_INPUT_H
#define RR_NG_INPUT_H
#include <stdint.h>
#include <stddef.h>
static uint32_t rr_ng_le32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1]<<8) | ((uint32_t)p[2]<<16) | ((uint32_t)p[3]<<24);
}
/* Shared host masks use bit 8 for Start and bit 9 for Coin on each pad.
 * MVS STATUS_B has P1 Start at bit 0 and P2 Start at bit 2 (bit 1 is Select). */
static unsigned rr_ng_start_bits(uint16_t p1,uint16_t p2) {return ((p1&256)?1u:0u)|((p2&256)?4u:0u);}
static unsigned rr_ng_coin_bits(uint16_t p1,uint16_t p2) {return ((p1&512)?1u:0u)|((p2&512)?2u:0u);}
/* Present, writable 2 KiB card: status bits 4/5 and write protect bit 6
 * clear. Select lines stay inactive; MVS Start bits remain independent. */
static unsigned rr_ng_status_b(unsigned start) {return 0x0fu&~start;}
/* Validate before Geolith dereferences regions; it expects trusted input. */
static int rr_ng_container_valid(const uint8_t *p, size_t size) {
    static const uint32_t limits[6] = {16u<<20,512u<<10,512u<<10,128u<<20,128u<<20,128u<<20};
    if (!p || size < 4096 || size > (512u<<20) || p[0]!='N' || p[1]!='E' || p[2]!='O' || p[3]!=1) return 0;
    uint64_t total = 4096;
    for (unsigned i=0; i<6; ++i) {
        uint32_t n = rr_ng_le32(p+4+i*4);
        if (n > limits[i] || ((!i || i==1 || i==2 || i==5) && !n)) return 0;
        total += n;
    }
    uint32_t program=rr_ng_le32(p+4),fixed=rr_ng_le32(p+8),sound=rr_ng_le32(p+12);
    return total == size && program>=0x200 && !(program&1) && fixed>=0x20000 && !(fixed%0x20000)
        && sound>=0x10000 && !(sound&(sound-1)) && !(rr_ng_le32(p+24)%128);
}
#endif
