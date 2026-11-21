/* The Amstrad CPC's Gate Array (40007 / 40010) and the 6128's RAM banking PAL, stepped with the CRTC one character (1 us) at a
 * time: pens and the 27 colours, the screen modes, the ROM enables, the 300 Hz interrupt, the RAM configurations, and the
 * picture as a monitor would show it. MIT, Retro-Recomp.
 *
 * Written from the CPC's documented Gate Array functions and timings; floooh/chips am40010.h (zlib) and Clock Signal (MIT)
 * read as documentation, nothing of them copied.
 *
 * Port 7Fxxh (A15 = 0, A14 = 1), bits 7-6 of the byte the function: 00 select a pen (bit 4 the border, else bits 0-3), 01 its
 * colour (bits 0-4, a hardware colour), 10 the mode (bits 0-1, taken at the next HSYNC), the lower ROM off (bit 2), the upper
 * ROM off (bit 3), and bit 4 clearing the interrupt counter; 11 the 6128's RAM configuration (bits 0-2, and bits 3-5 the 64 KiB
 * bank of a larger expansion; a 464 or 664 has no PAL and ignores it).
 *
 * The interrupt: a 6-bit counter steps at the end of each CRTC HSYNC; at 52 it clears and raises the interrupt. Two HSYNCs after
 * a VSYNC starts the counter clears, raising the interrupt if it had reached 32. The Z80's acknowledge clears the counter's
 * bit 5 (so the next one comes no sooner than 32 lines) and drops the request.
 *
 * The picture: 768 x 272 pixels (48 characters of 16 mode-2 pixels, 272 lines), the window a CPC monitor shows of a standard
 * screen with its border. The monitor's beam returns at each CRTC HSYNC and VSYNC, so a program that moves them moves the
 * picture; the window starts 14 characters after the HSYNC starts and 36 lines after the VSYNC starts (the firmware's screen
 * centred with a 4-character, 36-line border). Without an HSYNC for 64 characters or a VSYNC for 320 lines the beam returns by
 * itself, as a monitor's free-running sweep does. These offsets are an approximation of a real monitor, not a measure of one.
 * During the syncs the Gate Array sends black. A frame is complete when the VSYNC starts. */
#ifndef RR_CPC_GATE_ARRAY_H
#define RR_CPC_GATE_ARRAY_H
#include <stdint.h>

#include "cpc_crtc.h"

enum { CPC_SCREEN_WIDTH = 768, CPC_SCREEN_HEIGHT = 272, CPC_BORDER_PEN = 16 };
enum { CPC_GA_INTERRUPT = 1, CPC_GA_FRAME = 2 };

typedef struct {
    uint8_t has_ram_pal;    /* the 6128's banking (set by the machine, not part of a quick state) */
    uint8_t pen;            /* the pen selected, 0-15 or CPC_BORDER_PEN */
    uint8_t ink[17];        /* each pen's hardware colour, 0-31 */
    uint8_t mode;           /* the mode drawing now */
    uint8_t mode_next;      /* the mode written, taken at the next HSYNC */
    uint8_t rom_config;     /* bit 2 lower ROM off, bit 3 upper ROM off */
    uint8_t ram_config;     /* the PAL's byte, bits 0-5 */
    uint8_t counter;        /* the interrupt counter, 0-51 */
    uint8_t interrupt;      /* the request to the Z80 */
    uint8_t vsync_delay;    /* HSYNCs left before the VSYNC clears the counter */
    uint8_t hsync, vsync;   /* the CRTC's syncs at the last character */
    uint16_t beam_x;        /* characters since the beam returned */
    uint16_t beam_y;        /* lines since the beam returned to the top */
} CpcGateArray;

void cpc_ga_reset(CpcGateArray *g);
/* A byte written to port 7Fxxh. */
void cpc_ga_write(CpcGateArray *g, uint8_t value);
/* The Z80 acknowledges the interrupt. */
void cpc_ga_acknowledge(CpcGateArray *g);
/* One character: the CRTC's output for it, the base 64 KiB the screen is read from, and the picture (CPC_SCREEN_WIDTH x
 * CPC_SCREEN_HEIGHT, 0x00RRGGBB; NULL draws nothing). Returns CPC_GA_INTERRUPT when the interrupt was raised, CPC_GA_FRAME when
 * a frame is complete. */
unsigned cpc_ga_tick(CpcGateArray *g, CpcCrtcOut crtc, const uint8_t *ram, uint32_t *picture);
/* The 16 KiB banks (0-7: 0-3 the base 64 KiB, 4-7 the second) seen at 0000h, 4000h, 8000h and C000h for a RAM configuration. */
void cpc_ram_banks(uint8_t ram_config, uint8_t banks[4]);
/* A hardware colour (0-31) as 0x00RRGGBB, each gun at 0, 50 % (80h) or 100 %. */
uint32_t cpc_colour(uint8_t hardware);
/* The pens of the pixels of one screen byte in a mode: 2 (mode 0 and 3), 4 (mode 1) or 8 (mode 2), left first; returns the count. */
unsigned cpc_byte_pens(uint8_t mode, uint8_t byte, uint8_t pens[8]);
#endif
