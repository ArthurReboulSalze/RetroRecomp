/* Retro-Recomp X68000: frame buffer and presentation state for the 2014 code.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Replaces the presentation half of x11/windraw.c (SDL/GLES/PSP, menus).
 * The line composition itself is the original code, extracted at build time.
 * Behaviour from docs/X68000_GLUE_SPEC.md 3.6 step 12 and 3.10.
 */
#include <stdlib.h>

#include "common.h"
#include "windraw.h"
#include "winui.h"
#include "keyboard.h"
#include "prop.h"
#include "../x68k/crtc.h"

WORD *ScrBuf = NULL;
BYTE Draw_DrawFlag = 1;
WORD WinDraw_Pal16B = 0x001f, WinDraw_Pal16R = 0xf800, WinDraw_Pal16G = 0x07e0;
BYTE Debug_Text = 1, Debug_Grp = 1, Debug_Sp = 1;
char filepath[MAX_PATH] = ".";

extern uint16_t *videoBuffer;
extern uint32_t retrow, retroh;
extern int CHANGEAV;

static DWORD presented_x, presented_y;

int WinDraw_Init(void)
{
   /* RGB565, as the glue announces; Pal_Init derives every colour from these. */
   WinDraw_Pal16B = 0x001f;
   WinDraw_Pal16R = 0xf800;
   WinDraw_Pal16G = 0x07e0;
   free(ScrBuf);
   ScrBuf = (WORD *)calloc(800 * 600, sizeof(WORD));
   videoBuffer = ScrBuf;
   return ScrBuf != NULL;
}

void WinDraw_Cleanup(void)
{
   free(ScrBuf);
   ScrBuf = NULL;
   videoBuffer = NULL;
}

void WinDraw_Draw(void)
{
   if (TextDotX != presented_x || TextDotY != presented_y) {
      presented_x = TextDotX;
      presented_y = TextDotY;
      CHANGEAV = 1;
   }
   if (CHANGEAV == 1) {
      retrow = TextDotX;
      retroh = TextDotY;
   }
   videoBuffer = ScrBuf;
   Draw_DrawFlag = 0;
}

/* The 2014 CRTC announces geometry changes here; the next WinDraw_Draw
 * compares TextDotX/TextDotY itself, so nothing else is needed. */
void WinDraw_ChangeSize(void)
{
}

int WinDraw_MenuInit(void)
{
   return 1;
}

void WinUI_Init(void)
{
}

/* No software keyboard in this host. */
int Keyboard_IsSwKeyboard(void)
{
   return 0;
}
