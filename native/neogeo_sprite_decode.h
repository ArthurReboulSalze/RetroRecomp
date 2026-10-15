/* Exact planar-to-packed sprite row conversion. Original contribution: MIT.
 * Palette, clipping, priority, shrinking and raster scheduling stay in LSPC. */
#ifndef RR_NEOGEO_SPRITE_DECODE_H
#define RR_NEOGEO_SPRITE_DECODE_H
#include <stdint.h>
static inline int rr_ng_sprite_offscreen(unsigned x,unsigned shrink) {
    x&=511u;
    return x>=320u && x+shrink<512u;
}
static inline uint32_t rr_ng_sprite_plane(uint8_t bits) {
    static const uint16_t spread[16]={0x0000,0x0001,0x0010,0x0011,
        0x0100,0x0101,0x0110,0x0111,0x1000,0x1001,0x1010,0x1011,
        0x1100,0x1101,0x1110,0x1111};
    return spread[bits&15u]|((uint32_t)spread[bits>>4]<<16);
}
static inline uint32_t rr_ng_sprite_row(const uint8_t *row,unsigned cd) {
    unsigned a=cd?1:0,b=cd?0:2,c=cd?3:1,d=cd?2:3;
    return rr_ng_sprite_plane(row[a]) | (rr_ng_sprite_plane(row[b])<<1) |
        (rr_ng_sprite_plane(row[c])<<2) | (rr_ng_sprite_plane(row[d])<<3);
}
#endif
