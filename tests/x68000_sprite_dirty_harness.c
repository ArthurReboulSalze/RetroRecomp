/* Authored cases for the redraw bookkeeping of the X68000 sprites: when a sprite register changes, every screen line
 * the sprite covers before or after the change must be marked for redraw (x68k/bg.c as adapted by
 * tools/x68000_base74.py). "Covered" is decided by the real line drawing, BG_DrawLine, with the line selection of the
 * line composition (x11/windraw.c): the harness never decides coverage itself. No ROM, no firmware: the sprite
 * pattern is authored bytes. Each line printed is "name key=value ..."; tests/test_x68000_sprite_dirty.py reads them. */
#include <stdio.h>
#include <string.h>

#include "common.h"
#include "bg.h"
#include "crtc.h"
#include "palette.h"
#include "tvram.h"
#include "windraw.h"
#include "winx68k.h"

BYTE CRTC_Regs[48];
WORD CRTC_VSTART, CRTC_VEND, CRTC_HSTART, CRTC_HEND;
DWORD TextDotX = 256, TextDotY = 512, TextScrollX, TextScrollY;
DWORD VLINE;
BYTE Draw_DrawFlag;
WORD TextPal[256];

extern BYTE Sprite_Regs[];

#define LINES 512

/* The selection of the background row for a screen line, as WinDraw_DrawLine computes it before BG_DrawLine. */
static void select_line(unsigned line)
{
   int s1 = ((BG_Regs[0x11] & 4) ? 2 : 1) - ((BG_Regs[0x11] & 16) ? 1 : 0);
   int s2 = ((CRTC_Regs[0x29] & 4) ? 2 : 1) - ((CRTC_Regs[0x29] & 16) ? 1 : 0);
   VLINE = line;
   VLINEBG = line;
   VLINEBG <<= s1;
   VLINEBG >>= s2;
   if (!(BG_Regs[0x11] & 16))
      VLINEBG -= ((BG_Regs[0x0f] >> s1) - (CRTC_Regs[0x0d] >> s2));
}

static void covered(unsigned char *lines)
{
   unsigned line, i;
   for (line = 0; line < LINES; line++) {
      lines[line] = 0;
      select_line(line);
      BG_DrawLine(1, 0);
      for (i = 16; i < TextDotX + 16; i++)
         if (BG_LineBuf[i]) { lines[line] = 1; break; }
   }
}

static void bus(unsigned address, unsigned value) { BG_Write(0xeb0000 + address, (BYTE)value); }

static void set_posy(unsigned value)
{
   bus(2, value >> 8);
   bus(3, value);
}

/* One case: the machine's vertical registers, then a sprite that moves from y=100 to y=140. */
static void run(const char *name, unsigned bg_start, unsigned crtc_start, unsigned bg_res, unsigned crtc_res)
{
   unsigned char before[LINES], after[LINES];
   unsigned line, address, missing_old = 0, missing_new = 0, shown = 0;

   memset(BG_Regs, 0, sizeof BG_Regs);
   memset(Sprite_Regs, 0, 0x400);
   memset(TextDirtyLine, 0, sizeof TextDirtyLine);
   CRTC_Regs[0x0d] = (BYTE)crtc_start;
   CRTC_Regs[0x29] = (BYTE)crtc_res;
   CRTC_VSTART = (WORD)crtc_start;
   CRTC_HSTART = 0;
   BG_Write(0xeb0800 + 0x11, (BYTE)bg_res);
   BG_Write(0xeb0800 + 0x0f, (BYTE)bg_start);
   BG_Write(0xeb0800 + 0x0d, 4);                       /* no horizontal adjustment */
   for (address = 0; address < 0x8000; address++)       /* every pattern pixel has colour 1 */
      BG_Write(0xeb8000 + address, 0x11);
   bus(1, 24);                                         /* x */
   bus(5, 0);                                          /* pattern 0 */
   bus(7, 3);                                          /* priority 3: drawn */
   set_posy(100);
   covered(before);
   memset(TextDirtyLine, 0, sizeof TextDirtyLine);
   set_posy(140);
   covered(after);
   for (line = 0; line < LINES; line++) {
      if (before[line] && !TextDirtyLine[line]) ++missing_old;
      if (after[line] && !TextDirtyLine[line]) ++missing_new;
      shown += (unsigned)(before[line] + after[line]);
   }
   printf("%s covered=%u missing_old=%u missing_new=%u bg_vline=%ld\n", name, shown, missing_old, missing_new, BG_VLINE);
}

int main(void)
{
   int i;
   for (i = 0; i < 256; i++)
      TextPal[i] = (WORD)(i ? 0x1000 + i : 0);
   /* Background and display start together: the common case. */
   run("aligned_256", 40, 40, 0, 0);
   /* The background's vertical start is two raster lines after the display's. */
   run("bg_start_late", 42, 40, 0, 0);
   run("bg_start_early", 38, 40, 0, 0);
   /* Same offsets with a 512-line background and display. */
   run("aligned_512", 40, 40, 4, 4);
   run("bg_start_late_512", 44, 40, 4, 4);
   /* A 256-line background on a 512-line display covers twice the lines, a 512-line one on a 256-line display half. */
   run("bg_256_on_display_512", 40, 40, 0, 4);
   run("bg_512_on_display_256", 40, 40, 4, 0);
   run("bg_256_on_display_512_late", 42, 40, 0, 4);
   run("bg_512_on_display_256_late", 44, 40, 4, 0);
   return 0;
}
