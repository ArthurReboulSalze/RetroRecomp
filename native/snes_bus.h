#ifndef RR_SNES_BUS_H
#define RR_SNES_BUS_H
#include "snes_dma.h"
extern Snes *g_snes;
void rr_snes_cpu_context(bool active);
void rr_snes_cpu_read_begin(uint32_t address);
void rr_snes_cpu_read_end(void);
void rr_snes_cpu_write_begin(uint32_t address);
void rr_snes_cpu_idle(unsigned cycles);
void rr_snes_dma_request(Dma *dma,uint8_t mask);
void rr_snes_refresh_service(Dma *dma);
void rr_snes_parked_hdma(void);
uint32_t rr_snes_cpu_interrupt(uint32_t pc,uint16_t vector);
#endif
