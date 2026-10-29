/* Authored cases for the picture line of an X68000 machine line (native/x68000_machine/glue_line.h): the "no line" marker
 * must never be drawn, and a line chosen earlier is never changed. Each line printed is "name key=value ...";
 * tests/test_x68000_picture_line.py reads them. No ROM, no firmware. */
#include <stdio.h>

#include "glue_line.h"

int main(void)
{
   /* The CRTC of a game that reprogrammed it during line 32: picture from line 16, step 2. */
   printf("marker value=%u\n", (unsigned)RR_GLUE_NO_LINE);
   printf("steps one=%u two=%u four=%u\n", (unsigned)rr_glue_picture_line(48, 16, 1), (unsigned)rr_glue_picture_line(48, 16, 2),
          (unsigned)rr_glue_picture_line(48, 16, 4));
   printf("marker_replaced line=%u\n", (unsigned)rr_glue_line_to_draw(RR_GLUE_NO_LINE, 32, 16, 2));
   printf("marker_replaced_step_four line=%u\n", (unsigned)rr_glue_line_to_draw(RR_GLUE_NO_LINE, 20, 16, 4));
   printf("chosen_kept line=%u\n", (unsigned)rr_glue_line_to_draw(5, 32, 16, 2));
   printf("first_line_kept line=%u\n", (unsigned)rr_glue_line_to_draw(0, 32, 16, 2));
   return 0;
}
