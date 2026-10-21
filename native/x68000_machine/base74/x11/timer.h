/* Retro-Recomp X68000 compat: frame pacing gate (implemented in machine.c).
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 */
#ifndef RR_BASE74_TIMER_H
#define RR_BASE74_TIMER_H

#include <stdint.h>

extern uint32_t tick;
extern uint32_t timercnt;
void Timer_Init(void);
uint16_t Timer_GetCount(void);

#endif
