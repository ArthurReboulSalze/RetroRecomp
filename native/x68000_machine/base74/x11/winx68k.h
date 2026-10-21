/* Retro-Recomp X68000 compat: frame scheduling globals shared with the machine.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 */
#ifndef RR_BASE74_WINX68K_H
#define RR_BASE74_WINX68K_H

#include "common.h"

/* The machine sources refer to the current scan line as `vline`, a name some
 * C libraries also use; the exported symbol is HOGEvline. */
#define vline HOGEvline

#define SCREEN_WIDTH 768
#define SCREEN_HEIGHT 512
#define FULLSCREEN_WIDTH 800
#define FULLSCREEN_HEIGHT 600

#ifdef __cplusplus
extern "C" {
#endif
extern BYTE *FONT;
extern WORD VLINE_TOTAL;
extern DWORD VLINE;
extern DWORD vline;
extern char winx68k_dir[2048];
extern char winx68k_ini[2048];
void WinX68k_Reset(void);
#ifdef __cplusplus
}
#endif

#endif
