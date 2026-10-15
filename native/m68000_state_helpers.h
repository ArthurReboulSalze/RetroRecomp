/* Console-independent MC68000 stack selection and normal exception frame.
 * Active A7 plus an inactive stack slot preserves our existing snapshot ABI. */
#ifndef RR_M68000_STATE_HELPERS_H
#define RR_M68000_STATE_HELPERS_H
#include <stdint.h>
static inline uint32_t rr_m68000_user_sp(uint16_t sr,uint32_t a7,uint32_t inactive) {
    return (sr&0x2000u)?inactive:a7;
}
static inline uint32_t rr_m68000_supervisor_sp(uint16_t sr,uint32_t a7,uint32_t inactive) {
    return (sr&0x2000u)?a7:inactive;
}
static inline void rr_m68000_select_sr(uint16_t *sr,uint32_t *a7,uint32_t *inactive,uint16_t value) {
    if((*sr^value)&0x2000u) {
        uint32_t previous=*a7;*a7=*inactive;*inactive=previous;
    }
    *sr=value&0xa71fu;
}
static inline void rr_m68000_push_normal_frame(uint32_t *a7,uint16_t sr,uint32_t pc,
                                               void (*write16)(uint32_t,uint16_t)) {
    uint32_t sp=*a7;*a7=sp-6;
    /* Actual bus order, not simply the final in-memory frame order. */
    write16(sp-2,(uint16_t)pc);write16(sp-6,sr);write16(sp-4,(uint16_t)(pc>>16));
}
#endif
