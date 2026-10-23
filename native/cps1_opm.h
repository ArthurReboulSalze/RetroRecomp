/* YM2151 (OPM) through ymfm (BSD-3-Clause, Aaron Giles), pinned in
 * smsrecomp/cps1_build.py. The chip clock is the Z80 clock, so the caller
 * passes elapsed Z80 cycles; one output sample is 64 chip clocks. */
#ifndef CPS1_OPM_H
#define CPS1_OPM_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct cps1_opm cps1_opm;
typedef void (*cps1_opm_irq)(void *context, int asserted);

cps1_opm *cps1_opm_create(cps1_opm_irq irq, void *context);
void cps1_opm_destroy(cps1_opm *chip);
void cps1_opm_reset(cps1_opm *chip);
/* now = chip clocks since reset; used for the busy flag. */
uint8_t cps1_opm_read(cps1_opm *chip, uint32_t offset, uint64_t now);
void cps1_opm_write(cps1_opm *chip, uint32_t offset, uint8_t data, uint64_t now);
/* Generate one stereo sample (64 chip clocks), advancing the timers. */
void cps1_opm_generate(cps1_opm *chip, int32_t *left, int32_t *right);
/* Opaque state image (ymfm's own save/restore plus timers and busy end). */
size_t cps1_opm_save(cps1_opm *chip, uint8_t *buffer, size_t capacity);
int cps1_opm_load(cps1_opm *chip, const uint8_t *buffer, size_t size);

#ifdef __cplusplus
}
#endif
#endif
