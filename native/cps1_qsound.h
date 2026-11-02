/* Capcom QSound (DL-1425) of the CPS-1.5 boards: a high-level model of its DSP16.
 *
 * Adapted from MAME's src/devices/sound/qsoundhle.cpp at the revision the CPS-1 catalogue is pinned to (BSD-3-Clause,
 * copyright-holders: superctr, Valley Bell; see licenses/cps1-machine.md). That model was written from the disassembled DSP
 * program; it does not run the DSP16, so no DSP16 instruction is executed or counted here. It reads the chip's internal ROM
 * (`dl-1425.bin`, 4,096 words: the player's own dump, never shipped with the converter) for the filter, pan and ADPCM tables,
 * and the sample ROM for the voices. One sample every 1,248 cycles of a 30 MHz DSP clock: 24,038.46 Hz, stereo. */
#ifndef RR_CPS1_QSOUND_H
#define RR_CPS1_QSOUND_H
#include <stddef.h>
#include <stdint.h>

#define CPS1_QSOUND_DSP_BYTES 0x2000      /* the first 8 KiB of dl-1425.bin: the DSP's internal ROM */
#define CPS1_QSOUND_RATE_NUM 5            /* samples per Z80 clock at 8 MHz: 5 / 1664 */
#define CPS1_QSOUND_RATE_DEN 1664

typedef struct { uint16_t bank; int16_t addr; uint16_t phase, rate; int16_t loop_len, end_addr, volume, echo; } cps1_qs_voice;
typedef struct { uint16_t start_addr, end_addr, bank; int16_t volume; uint16_t flag; int16_t cur_vol, step_size; uint16_t cur_addr; } cps1_qs_adpcm;
typedef struct { int32_t tap_count, delay_pos; uint16_t table_pos; int16_t taps[95], delay_line[95]; } cps1_qs_fir;
typedef struct { int16_t delay, volume, write_pos, read_pos, delay_line[51]; } cps1_qs_delay;
typedef struct { uint16_t end_pos; int16_t feedback, length, last_sample, delay_line[1024], delay_pos; } cps1_qs_echo;

typedef struct cps1_qsound {
    uint16_t dsp_rom[0x1000];             /* from the player's dl-1425.bin, little-endian words (not part of a state) */
    const uint8_t *samples; size_t sample_bytes;   /* the sample ROM (not part of a state) */
    uint16_t data_latch;
    int16_t out[2];
    cps1_qs_voice voice[16];
    cps1_qs_adpcm adpcm[3];
    uint16_t voice_pan[19];
    int16_t voice_output[19];
    cps1_qs_echo echo;
    cps1_qs_fir filter[2], alt_filter[2];
    cps1_qs_delay wet[2], dry[2];
    uint16_t state, next_state, delay_update;
    int32_t state_counter, ready_flag;
} cps1_qsound;

/* `dsp_rom` is CPS1_QSOUND_DSP_BYTES bytes. */
void cps1_qsound_init(cps1_qsound *chip, const uint8_t *dsp_rom, const uint8_t *samples, size_t sample_bytes);
void cps1_qsound_reset(cps1_qsound *chip);                     /* the DSP boots again; not ready until it has initialised */
void cps1_qsound_write(cps1_qsound *chip, unsigned offset, uint8_t data);   /* Z80 d000 (high), d001 (low), d002 (register) */
uint8_t cps1_qsound_ready(const cps1_qsound *chip);            /* d007: 0x80 ready, 0x00 busy */
void cps1_qsound_sample(cps1_qsound *chip, int16_t out[2]);    /* one more sample, left and right */

/* Quick state: every field of the chip but the two ROM references, little-endian, no padding. */
size_t cps1_qsound_state_bytes(void);
size_t cps1_qsound_state_put(const cps1_qsound *chip, uint8_t *out);
int cps1_qsound_state_get(cps1_qsound *chip, const uint8_t *in);   /* 0 when a field is out of its range; the chip is then untouched */
#endif
