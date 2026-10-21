/* Retro-Recomp X68000 compat: sound output ring (implemented in audio_mix.c).
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 */
#ifndef RR_BASE74_DSWIN_H
#define RR_BASE74_DSWIN_H

#include "common.h"

#define RR_SOUND_RATE 44100

void DSound_Play(void);
void DSound_Stop(void);
void DSound_Send0(long clock);
int audio_samples_avail(void);
void raudio_callback(void *userdata, unsigned char *stream, int len);

#endif
