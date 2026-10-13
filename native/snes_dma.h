#ifndef RR_SNES_DMA_H
#define RR_SNES_DMA_H
#include "snes/snes.h"
#include "snes/dma.h"
#include "cpu_state.h"
/* A-bus DMA does not address CPU/B-bus registers, including their mirrors. */
static inline bool rr_snes_dma_valid_a(uint32_t address) {
    return (address&0x40ff00u)!=0x2100u && (address&0x40fe00u)!=0x4000u &&
        (address&0x40ffe0u)!=0x4200u && (address&0x40ff80u)!=0x4300u;
}
static inline bool rr_snes_dma_valid_b(uint32_t a,uint8_t b) {
    return b!=0x80 || ((a&0xfe0000u)!=0x7e0000u && (a&0x40e000u)!=0);
}
void rr_snes_dma_charge(Snes *snes,uint32_t clocks);
void rr_snes_dma_run(Dma *dma,uint8_t mask);
/* Beam edges latch requests; service only at a completed bus-byte boundary.
 * A true return means the guest clock was stalled, not CPU instructions run. */
bool rr_snes_hdma_service(Dma *dma,bool dma_boundary);
#endif
