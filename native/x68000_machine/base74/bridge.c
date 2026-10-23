/* Retro-Recomp X68000: host bridge for the 2014 machine base.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * State identity, frame buffer and media readiness for our host.
 */
#include <stdio.h>
#include <stdint.h>

#include "probe.h"

extern uint16_t *videoBuffer;
extern unsigned RR_FDD_MediaMask(void);
extern unsigned RR_FDD_BlinkMask(void);
extern int FDC_IsDataReady(void);
extern unsigned RR_FDC_DriveInterest(unsigned drive);

RR_X68K_EXPORT const char *rr_x68k_state_compatibility(void) { return RR_X68K_STATE_ABI; }
RR_X68K_EXPORT const void *rr_x68k_framebuffer(void) { return videoBuffer; }

unsigned rr_x68000_media_ready(void)
{
   return RR_FDD_MediaMask() | (RR_FDD_BlinkMask() << 8);
}

unsigned rr_x68000_media_activity(void)
{
   return FDC_IsDataReady() ? 2u : 0u;
}

unsigned rr_x68000_media_interest(unsigned drive)
{
   return RR_FDC_DriveInterest(drive);
}
