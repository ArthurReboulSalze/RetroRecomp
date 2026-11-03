/* Retro-Recomp X68000: from the machine's colour word to the picture the player receives.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * The palette registers hold GGGGGRRRRRBBBBBI: five bits per primary and one intensity bit that lifts the three
 * primaries together (a half step of the 6-bit DAC each). The 2014 code keeps that word as it is in its frame buffer
 * (host_draw.c gives it the masks of this layout, so Pal_SetColor builds the identity table and Ibit is bit 0) and the
 * machine presents it as XRGB8888, each primary being (primary << 1 | I) widened from 6 to 8 bits. The earlier
 * RGB565 buffer had no room for a sixth bit on red and blue, so the intensity bit only reached green.
 */
#ifndef RR_X68000_COLOUR_H
#define RR_X68000_COLOUR_H

#include <stdint.h>

#define RR_X68K_COLOUR_G 0xf800u
#define RR_X68K_COLOUR_R 0x07c0u
#define RR_X68K_COLOUR_B 0x003eu
#define RR_X68K_COLOUR_I 0x0001u

/* 6-bit DAC level to 8 bits: the top bits repeat below. */
static uint32_t rr_x68k_dac8(uint32_t level6)
{
   return (level6 << 2) | (level6 >> 4);
}

/* One colour word to 0x00RRGGBB (the top byte stays zero, so a black picture is all zero bytes). */
static uint32_t rr_x68k_colour_xrgb(uint16_t word)
{
   const uint32_t intensity = word & RR_X68K_COLOUR_I;
   const uint32_t g = rr_x68k_dac8(((uint32_t)(word >> 11) << 1) | intensity);
   const uint32_t r = rr_x68k_dac8(((uint32_t)((word >> 6) & 31u) << 1) | intensity);
   const uint32_t b = rr_x68k_dac8(((uint32_t)((word >> 1) & 31u) << 1) | intensity);
   return (r << 16) | (g << 8) | b;
}

static void rr_x68k_colour_table(uint32_t table[65536])
{
   uint32_t word;
   for (word = 0; word < 65536u; ++word)
      table[word] = rr_x68k_colour_xrgb((uint16_t)word);
}

#endif
