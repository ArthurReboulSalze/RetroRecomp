#ifndef RETRO_RECOMP_LIGHTPHASER_H
#define RETRO_RECOMP_LIGHTPHASER_H
#include <stdbool.h>
#include <stdint.h>

/* Machine state only: independent of SDL, display filters and reticle size. */
void lightphaser_reset(bool enabled, int hcounter_offset);
bool lightphaser_enabled(void);
void lightphaser_pointer(int x, int y, bool trigger);
void lightphaser_position(int *x, int *y, bool *trigger);
uint8_t lightphaser_dc(uint8_t pad1, uint8_t pad2);
uint8_t lightphaser_dd(uint8_t pad2, uint64_t cycles);
uint8_t lightphaser_hcounter(uint64_t cycles);
void lightphaser_control(uint8_t value, uint64_t cycles, uint8_t free_hcounter);
void lightphaser_observations(uint64_t *low_reads, uint64_t *counter_reads);
#endif
