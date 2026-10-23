/* OKI MSM6295 ADPCM voice chip, adapted from MAME's okim6295.cpp and
 * okiadpcm.cpp (BSD-3-Clause, copyright-holders: Mirko Buffoni, Aaron Giles,
 * Andrew Gardner) at revision 61a222977fd29f22ce11fbea3f7c290fd7ced091.
 * Integer output: each sample is the sum of the four voices' 12-bit signals
 * scaled by their 5-bit volume (full scale = 2048 * 32 per voice).
 */
#ifndef CPS1_OKI_H
#define CPS1_OKI_H

#include <stddef.h>
#include <stdint.h>

typedef struct cps1_oki_voice {
    uint8_t playing;
    uint32_t base, sample, count;
    int32_t signal, step, volume;
} cps1_oki_voice;

typedef struct cps1_oki {
    const uint8_t *rom; size_t rom_size;
    int command;
    uint8_t pin7;
    cps1_oki_voice voice[4];
} cps1_oki;

void cps1_oki_init(cps1_oki *chip, const uint8_t *rom, size_t rom_size, int pin7);
void cps1_oki_reset(cps1_oki *chip);
uint8_t cps1_oki_status(const cps1_oki *chip);
void cps1_oki_write(cps1_oki *chip, uint8_t command);
int32_t cps1_oki_sample(cps1_oki *chip);
/* Master-clock divider for the current pin 7 state (132 high, 165 low). */
unsigned cps1_oki_divider(const cps1_oki *chip);

#endif
