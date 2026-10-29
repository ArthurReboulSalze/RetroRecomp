/* Authored cases for the text line of the X68000 (Text_DrawLine of x68k/tvram.c as adapted by tools/x68000_base74.py):
 * the line is copied in runs that stay inside the 1024-dot row of the text plane. It must give the same dots, flags and
 * palette entries as the plain per-dot formula, for every horizontal scroll value, several line widths, both the opaque and
 * the transparent mode, and the interlaced line step. No ROM: the text plane and the palette are pseudo-random bytes.
 * Each line printed is "name key=value ..."; tests/test_x68000_text_line.py reads them. */
#include <stdio.h>
#include <string.h>

#include "common.h"
#include "bg.h"
#include "crtc.h"
#include "palette.h"
#include "tvram.h"
#include "winx68k.h"

BYTE CRTC_Regs[48];
WORD CRTC_VSTART, CRTC_VEND, CRTC_HSTART, CRTC_HEND;
DWORD TextDotX = 256, TextDotY = 512, TextScrollX, TextScrollY;
DWORD VLINE;
WORD TextPal[256];
WORD BG_LineBuf[1600];
BYTE Draw_DrawFlag;

static unsigned seed_state = 12345;

static unsigned rnd(void)
{
   seed_state ^= seed_state << 13;
   seed_state ^= seed_state >> 17;
   seed_state ^= seed_state << 5;
   return seed_state;
}

/* The line as the machine defines it: dot i of the line is dot (TextScrollX + i) & 0x3ff of the plane's row. */
static void expected(int opaq, WORD *line, BYTE *flags)
{
   DWORD y = TextScrollY + VLINE, i;
   if ((CRTC_Regs[0x29] & 0x1c) == 0x1c)
      y += VLINE;
   y = (y & 0x3ff) << 10;
   for (i = 0; i < TextDotX; i++) {
      BYTE t = TextDrawWork[y + ((TextScrollX + i) & 0x3ff)] & 0xf;
      if (opaq) {
         flags[16 + i] = t ? 1 : 0;
         line[16 + i] = TextPal[t];
      } else if (t) {
         flags[16 + i] |= 1;
         line[16 + i] = TextPal[t];
      }
   }
}

int main(void)
{
   static const DWORD widths[] = {256, 384, 512, 768};   /* the flags array holds 1024 entries from dot 16 */
   static const BYTE steps[] = {0x00, 0x1c};
   unsigned w, s, opaq, scroll, i, cases = 0, bad = 0, wraps = 0;
   WORD want_line[1600];
   BYTE want_flags[1024];

   for (i = 0; i < 256; i++)
      TextPal[i] = (WORD)(i ? 0x2000 + 7 * i : 0);
   for (i = 0; i < sizeof TextDrawWork; i++)               /* about a third of the dots are transparent */
      TextDrawWork[i] = (rnd() % 3) ? (BYTE)(rnd() % 16) : 0;
   for (w = 0; w < sizeof widths / sizeof widths[0]; w++) {
      for (s = 0; s < sizeof steps; s++) {
         for (opaq = 0; opaq < 2; opaq++) {
            for (scroll = 0; scroll < 1024; scroll += (scroll % 64 == 0 || scroll > 960) ? 1 : 7) {
               TextDotX = widths[w];
               TextScrollX = scroll;
               TextScrollY = rnd() % 1024;
               VLINE = rnd() % 512;
               CRTC_Regs[0x29] = steps[s];
               for (i = 0; i < 1600; i++)                  /* a previous line the transparent mode must keep */
                  BG_LineBuf[i] = want_line[i] = (WORD)rnd();
               for (i = 0; i < 1024; i++)
                  Text_TrFlag[i] = want_flags[i] = (BYTE)(rnd() & 3);
               expected((int)opaq, want_line, want_flags);
               Text_DrawLine((int)opaq);
               ++cases;
               if (scroll + TextDotX > 1024)
                  ++wraps;
               if (memcmp(BG_LineBuf, want_line, sizeof want_line) || memcmp(Text_TrFlag, want_flags, sizeof want_flags))
                  ++bad;
            }
         }
      }
   }
   printf("text_line cases=%u wrapping=%u mismatches=%u\n", cases, wraps, bad);
   return 0;
}
