/* Retro-Recomp X68000 compat: mouse to SCC interface.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 */
#ifndef RR_BASE74_MOUSE_H
#define RR_BASE74_MOUSE_H

#include "common.h"

extern BYTE MouseStat;
extern BYTE MouseSW;

void Mouse_Init(void);
void Mouse_Event(int wparam, float dx, float dy);
void Mouse_SetData(void);
void Mouse_StartCapture(int flag);
void Mouse_ChangePos(void);

#endif
