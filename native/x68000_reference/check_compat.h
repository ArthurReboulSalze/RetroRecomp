/* Retro-Recomp X68000 checks: call shapes of the 74ddbb3 machine base. MIT.
 *
 * The authored checks are written against the current base. The 2014 base
 * takes the output rate explicitly (0 = machine rate, as base74/audio_mix.c
 * passes it) and an unused OPM read address. Include after the device headers.
 */
#ifndef RR_X68000_CHECK_COMPAT_H
#define RR_X68000_CHECK_COMPAT_H
#ifdef RR_X68000_BASE74
#include "dswin.h"
#include "m68k.h" /* x68k/m68000.h of 2014 does not include it */
#define ADPCM_Init() ADPCM_Init(RR_SOUND_RATE)
#define OPM_Read() OPM_Read(0)
#define OPM_Update(buffer, length, start, end) OPM_Update(buffer, length, 0, start, end)
#define ADPCM_Update(buffer, length, start, end) ADPCM_Update(buffer, length, 0, start, end)
#endif
#endif
