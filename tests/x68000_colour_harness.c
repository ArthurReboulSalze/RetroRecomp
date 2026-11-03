/* Authored cases for the colour word of the X68000 machine: the masks the machine gives the 2014 palette code
 * (native/x68000_machine/base74/host_draw.c, included as it is), the table that code builds from them
 * (x68k/palette.c, as adapted by tools/x68000_base74.py) and the widening to the picture
 * (native/x68000_machine/colour.h). No ROM, disk or firmware. Each line printed is "name key=value ...";
 * tests/test_x68000_colour.py reads them. */
#include <stdio.h>
#include <string.h>

#include "common.h"
#include "palette.h"
#include "memory.h"

DWORD TextDotX = 0, TextDotY = 0;
DWORD MemByteAccess = 0;
uint16_t *videoBuffer = NULL;
uint32_t retrow = 800, retroh = 600;
int CHANGEAV = 0;
void TVRAM_SetAllDirty(void) {}

#include "../native/x68000_machine/base74/host_draw.c"
#include "../native/x68000_machine/colour.h"

static void palette_word(unsigned address, unsigned word)
{
   Pal_Write(address, (BYTE)(word >> 8));
   Pal_Write(address + 1, (BYTE)word);
}

static unsigned count_not_identity(void)
{
   unsigned i, different = 0;
   for (i = 0; i < 65536; ++i)
      different += Pal16[i] != (WORD)i;
   return different;
}

int main(void)
{
   unsigned i;
   static uint32_t table[65536];

   WinDraw_Init();
   Pal_Init();
   printf("layout green=%04x red=%04x blue=%04x ibit=%04x halfmask=%04x ix2=%04x\n",
          WinDraw_Pal16G, WinDraw_Pal16R, WinDraw_Pal16B, Ibit, Pal_HalfMask, Pal_Ix2);
   printf("identity different=%u\n", count_not_identity());

   /* The palette registers: a GRBI word written to the graphic and text palettes comes back as it is. */
   palette_word(0xe82000, 0x07c0); palette_word(0xe82002, 0xf800); palette_word(0xe82004, 0x003e);
   palette_word(0xe82006, 0x0001); palette_word(0xe82200 + 6, 0x07c1); palette_word(0xe82200 + 8, 0xffff);
   printf("written graphic0=%04x graphic1=%04x graphic2=%04x graphic3=%04x text3=%04x text4=%04x\n",
          GrphPal[0], GrphPal[1], GrphPal[2], GrphPal[3], TextPal[3], TextPal[4]);

   /* Full contrast changes nothing, the intensity bit included; half contrast scales the five-bit primaries. */
   Pal_ChangeContrast(15);
   printf("contrast15 different=%u graphic3=%04x text3=%04x\n", count_not_identity(), GrphPal[3], TextPal[3]);
   Pal_ChangeContrast(8);
   printf("contrast8 graphic0=%04x graphic1=%04x graphic2=%04x graphic3=%04x text3=%04x\n",
          GrphPal[0], GrphPal[1], GrphPal[2], GrphPal[3], TextPal[3]);

   rr_x68k_colour_table(table);
   for (i = 0; i < 65536; ++i)
      printf("c%04x v=%06x\n", i, (unsigned)table[i]);
   WinDraw_Cleanup();
   return 0;
}
