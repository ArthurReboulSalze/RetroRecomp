/* Retro-Recomp X68000 compat: line composition and presentation entry points.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 */
#ifndef RR_BASE74_WINDRAW_H
#define RR_BASE74_WINDRAW_H

#include "common.h"

extern BYTE Draw_DrawFlag;
extern WORD WinDraw_Pal16B, WinDraw_Pal16R, WinDraw_Pal16G;

int WinDraw_Init(void);
void WinDraw_Cleanup(void);
void WinDraw_Draw(void);
void WinDraw_DrawLine(void);
void WinDraw_ChangeSize(void);
int WinDraw_MenuInit(void);

#endif
