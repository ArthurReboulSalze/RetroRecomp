#ifndef RR_MD_VDP_DMA_H
#define RR_MD_VDP_DMA_H
#include <stdint.h>
/* Guest state only: one active transfer, retained between slots and frames.
 * Mode 1 owns the main bus until its last fetch into the existing FIFO;
 * mode 2 fills bytes; mode 3 reads then copies bytes. A FIFO tail outlives DMA.
 * The existing FIFO clock is their common line-relative master-clock axis. */
typedef struct RrMdVdpDma {
    uint32_t mode, remaining, source, address, increment, code, value, half;
} RrMdVdpDma;
typedef struct RrMdVdpIrq {
    uint32_t hint_pending, vint_stage;
} RrMdVdpIrq;
#endif
