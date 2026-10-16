/* Eight indexed pixels from immutable presentation-plane bytes. MIT.
 * Logical lane n holds bit n; callers retain their own flip/palette rules.
 * These reads do not replace or batch guest bus transactions. */
#ifndef RR_PLANAR_ROWS_H
#define RR_PLANAR_ROWS_H
#include <stdint.h>
static inline uint64_t rr_plane_lanes(uint8_t byte) {
    uint64_t x=byte;
    x=(x|(x<<28))&UINT64_C(0x0000000f0000000f);
    x=(x|(x<<14))&UINT64_C(0x0003000300030003);
    return (x|(x<<7))&UINT64_C(0x0101010101010101);
}
static inline uint64_t rr_planar_pair(uint16_t planes) {
    return rr_plane_lanes((uint8_t)planes)|(rr_plane_lanes((uint8_t)(planes>>8))<<1);
}
static inline unsigned rr_planar_pixel(uint64_t row,unsigned bit) {
    return (unsigned)((row>>(bit*8u))&255u);
}
#endif
