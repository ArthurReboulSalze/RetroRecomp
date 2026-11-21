/* The SN76489A sound generator of the SG-1000 and the ColecoVision (Texas Instruments: three square tones and one noise channel, four-bit
 * attenuation). MIT, Retro-Recomp. Shared by the machines that have it, one module of native/sn76489.
 *
 * The chip knows nothing of the machine: the machine writes a data byte (`sn76489_write`) after bringing the chip up to the CPU's
 * cycle (`sn76489_run`), and takes the finished samples (`sn76489_take`). The clock is the CPU's, 3,579,545 Hz; the chip advances in
 * ticks of 16 CPU cycles, and the stream is the same whatever the steps it is produced in. This is the TI chip: the noise register is
 * 15 bits wide, white noise taps bits 0 and 1 (the Master System's, Game Gear's and Mega Drive's PSG is the Sega variant: 16 bits, taps
 * bits 0 and 3).
 *
 * Why it is not the Master System's PSG (native/psg_runs.inc, psg_state.inc, the engine's runner/audio/sn76489.c): that one is a file of the
 * pinned smsggrecomp runner (no declared licence, the owner's noncommercial permission), staged and patched at conversion, cycle-stamped by
 * the Sega runner, stereo for the Game Gear and low-passed, and it is the 16-bit variant; its output would not be identical with this one's
 * and the two stay apart. The SG-1000 and the ColecoVision share this module. */
#ifndef SN76489_H
#define SN76489_H

#include <stdint.h>

enum { SN_CPU_CLOCK = 3579545, SN_AUDIO_RATE = 44100, SN_AUDIO_BUFFER = 8192 };

typedef struct {
    uint16_t tone[3];          /* the three 10-bit period registers */
    uint8_t noise;             /* bit 2: white (else periodic), bits 0-1: the rate (3: the third tone's period) */
    uint8_t volume[4];         /* the attenuation of the three tones and of the noise, 0 (loudest) to 15 (off) */
    uint8_t latch;             /* the register a data byte goes to: bits 6-4 of the last latch byte */
    uint16_t count[4];
    uint8_t out[4];
    uint16_t lfsr;
    uint64_t time;             /* the CPU cycle the chip is brought to */
    unsigned tick_rest;        /* cycles of the tick in progress */
    uint32_t ticks;
    uint64_t next_sample;      /* in CPU cycles x 65536 */
    int32_t acc;
    uint32_t acc_ticks;
    int16_t samples[SN_AUDIO_BUFFER];
    unsigned sample_count;     /* samples waiting; the machine takes them with sn76489_take */
    uint64_t dropped;          /* samples lost because the machine did not take them */
} Sn76489;

void sn76489_reset(Sn76489 *s, uint64_t cycle);
void sn76489_write(Sn76489 *s, uint8_t value);
void sn76489_run(Sn76489 *s, uint64_t cycle);
unsigned sn76489_take(Sn76489 *s, int16_t *out, unsigned max);

#endif
