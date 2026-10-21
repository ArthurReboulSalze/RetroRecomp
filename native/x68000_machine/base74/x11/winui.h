/* Retro-Recomp X68000 compat: layer switches read by the line composition.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 */
#ifndef RR_BASE74_WINUI_H
#define RR_BASE74_WINUI_H

#include "common.h"

extern BYTE Debug_Text, Debug_Grp, Debug_Sp;
extern char filepath[MAX_PATH];

void WinUI_Init(void);

#endif
