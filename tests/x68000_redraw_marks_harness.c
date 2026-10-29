/* Authored proof that the redraw marks of the X68000 background and sprites equal a full redraw: the real bg.c, tvram.c
 * and BG_DrawLine (as adapted by tools/x68000_base74.py) draw random authored scenes in two ways, line after line.
 * A redraws a line only when WinDraw_DrawLine would (rr_bg_resolve, then TextDirtyLine) and keeps the line otherwise;
 * B redraws every line. After each line the two must be identical. Between lines, random writes to the tile maps, the
 * patterns, the sprite registers and the scroll registers change the scene, as a game does during a frame.
 * No ROM, no firmware: the patterns, maps and sprites are pseudo-random bytes.
 * Each line printed is "name key=value ..."; tests/test_x68000_redraw_marks.py reads them. */
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
DWORD TextDotX = 96, TextDotY = 512, TextScrollX, TextScrollY;
DWORD VLINE;
BYTE Draw_DrawFlag;
WORD TextPal[256];

extern BYTE Sprite_Regs[];
extern void rr_bg_resolve(void);

#define LINES 300
#define FRAMES 40

static unsigned seed_state;

static unsigned rnd(void)
{
   seed_state ^= seed_state << 13;
   seed_state ^= seed_state >> 17;
   seed_state ^= seed_state << 5;
   return seed_state;
}

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

static void draw(unsigned line, WORD *out, int gd)
{
   select_line(line);
   BG_DrawLine(1, gd);
   memcpy(out, &BG_LineBuf[16], TextDotX * sizeof(WORD));
}

/* Most tiles are numbers 20 to 79, which no pattern write touches (and which are below the map windows, as a game's
 * patterns are); one in 200 is among the first 16 patterns. */
static unsigned tile(void) { return (rnd() % 200 == 0) ? rnd() % 16 : 20 + rnd() % 60; }

static void bus(unsigned address, unsigned value) { BG_Write(0xeb0000 + address, (BYTE)value); }
static void bg(unsigned offset, unsigned value) { BG_Write(0xeb8000 + offset, (BYTE)value); }

static void random_write(unsigned scroll_changes)
{
   unsigned pick = rnd() % (scroll_changes ? 20 : 19);
   if (pick < 6) {                                   /* a tile map entry: attribute byte or tile number */
      unsigned plane = rnd() & 1, offset = rnd() % 0x2000;
      bg((plane ? 0x4000 : 0x6000) + offset, (offset & 1) ? tile() : rnd() % 256);
   } else if (pick < 11) {                           /* a pattern byte of the first 16 patterns */
      bg(rnd() % (BG_CHRSIZE == 8 ? 512 : 2048), (rnd() % 3) ? rnd() % 256 : 0);
   } else if (pick < 18) {                           /* a sprite register of the first 8 sprites */
      unsigned sprite = rnd() % 8, field = rnd() % 4, high = rnd() & 1, value;
      switch (field) {
      case 0: value = high ? (rnd() % 3 == 0) : rnd() % (TextDotX + 24); break;
      case 1: value = high ? (rnd() % 3 == 0) : rnd() % 256; break;
      case 2: value = high ? rnd() % 256 : rnd() % 16; break;
      default: value = high ? 0 : rnd() % 4; break;
      }
      bus(sprite * 8 + field * 2 + (high ? 0 : 1), value);
   } else if (pick == 18) {                          /* a 16-bit write of the same value is a no-op */
      bg(rnd() % 2048, 0);
   } else {                                          /* a scroll register of the background */
      BG_Write(0xeb0800 + rnd() % 8, (BYTE)rnd());
   }
}

static void scenario(const char *name, unsigned r11, unsigned crtc29, unsigned r0f, unsigned crtc0d, unsigned seed,
                     int gd, unsigned scroll_changes)
{
   WORD kept[LINES][96], fresh[96];
   unsigned frame, line, mismatches = 0, drawn = 0, writes = 0, i;

   seed_state = seed;
   BG_Init();
   memset(TextDirtyLine, 0, sizeof TextDirtyLine);
   CRTC_Regs[0x0d] = (BYTE)crtc0d;
   CRTC_Regs[0x29] = (BYTE)crtc29;
   CRTC_VSTART = (WORD)crtc0d;
   CRTC_HSTART = 0;
   BG_Write(0xeb0800 + 0x11, (BYTE)r11);
   BG_Write(0xeb0800 + 0x0f, (BYTE)r0f);
   BG_Write(0xeb0800 + 0x0d, 4);
   BG_Write(0xeb0800 + 0x09, 0x19);                    /* BG0 at 0x4000, BG1 at 0x6000, both on */
   BG_Write(0xeb0800 + 0x08, 3);
   for (i = 0; i < 8; i++)
      BG_Write(0xeb0800 + i, (BYTE)(rnd() % 256));
   for (i = 0; i < 2048; i++)
      bg(i, rnd() % 256);
   for (i = 0; i < 0x4000; i++)                         /* maps: any attribute */
      bg(0x4000 + i, (i & 1) ? tile() : rnd() % 256);
   for (i = 0; i < 8; i++) {                            /* eight sprites, all drawn */
      bus(i * 8 + 1, rnd() % (TextDotX + 24));
      bus(i * 8 + 3, rnd() % 256);
      bus(i * 8 + 5, rnd() % 16);
      bus(i * 8 + 7, 1 + rnd() % 3);
   }
   TVRAM_SetAllDirty();
   memset(kept, 0, sizeof kept);
   for (frame = 0; frame < FRAMES; frame++) {
      for (line = 0; line < LINES; line++) {
         if (rnd() % 60 == 0) {
            unsigned count = 1 + rnd() % 3;
            while (count--) { random_write(scroll_changes); ++writes; }
         }
         rr_bg_resolve();
         if (TextDirtyLine[line]) {
            TextDirtyLine[line] = 0;
            draw(line, kept[line], gd);
            ++drawn;
         }
         draw(line, fresh, gd);
         if (memcmp(kept[line], fresh, TextDotX * sizeof(WORD)))
            ++mismatches;
      }
   }
   printf("%s mismatches=%u lines=%u redrawn=%u writes=%u\n", name, mismatches, FRAMES * LINES, drawn, writes);
}

int main(void)
{
   int i;
   for (i = 0; i < 256; i++)
      TextPal[i] = (WORD)(i ? 0x1000 + i : 0);
   scenario("tiles16_aligned", 0x01, 0x00, 40, 40, 1, 0, 0);
   scenario("tiles16_aligned_ng", 0x01, 0x00, 40, 40, 2, 1, 0);
   scenario("tiles8_512_aligned", 0x04, 0x04, 40, 40, 3, 0, 0);
   scenario("tiles8_512_bg_late", 0x04, 0x04, 46, 40, 4, 1, 0);
   scenario("tiles16_bg_early", 0x01, 0x00, 36, 40, 5, 0, 0);
   scenario("tiles8_bg_256_on_display_512", 0x00 | 0x08, 0x04, 40, 40, 6, 0, 0);
   scenario("tiles16_bg_512_on_display_256", 0x05, 0x00, 44, 40, 7, 1, 0);
   scenario("tiles16_scroll_changes", 0x01, 0x00, 42, 40, 8, 0, 1);
   scenario("tiles8_scroll_changes", 0x04, 0x04, 40, 40, 9, 1, 1);
   return 0;
}
