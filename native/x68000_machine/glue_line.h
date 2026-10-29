/* Retro-Recomp X68000 MIT host glue: the picture line of a machine line.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * The frame loop chooses the picture line when a machine line begins, from the CRTC as it is then. A game may reprogram
 * the CRTC during that line, so that a line that was outside the picture becomes visible before it is drawn. The
 * "no line" marker must never reach the line tables: it indexes them 4 GiB out on a 64-bit host (the 32-bit original
 * wrapped to the byte before the table and drew into memory it did not own).
 */
#ifndef RR_X68000_MACHINE_GLUE_LINE_H
#define RR_X68000_MACHINE_GLUE_LINE_H

#include <stdint.h>

#define RR_GLUE_NO_LINE 0xffffffffu

/* The picture line of machine line `vline` for the CRTC's vertical start and step. */
static inline uint32_t rr_glue_picture_line(uint32_t vline, uint32_t vstart, uint32_t vstep)
{
   return ((vline - vstart) * vstep) / 2;
}

/* The line to draw for a machine line that the CRTC shows now: the line chosen when it began, or, when none was chosen
 * (the marker), the line the CRTC gives now. A line chosen earlier is never changed. */
static inline uint32_t rr_glue_line_to_draw(uint32_t chosen, uint32_t vline, uint32_t vstart, uint32_t vstep)
{
   return chosen == RR_GLUE_NO_LINE ? rr_glue_picture_line(vline, vstart, vstep) : chosen;
}

#endif
