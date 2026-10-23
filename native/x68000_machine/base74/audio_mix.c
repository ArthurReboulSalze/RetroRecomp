/* Retro-Recomp X68000: sound ring for the 2014 machine code.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Written from docs/history/x68000/X68000_PHASE3_PORTING.md section 5 and our glue contract
 * (docs/X68000_GLUE_SPEC.md 3.9). Samples are produced only from elapsed
 * machine clocks (never on host demand), 44.1 kHz stereo 16-bit.
 */
#include <string.h>

#include "common.h"
#include "dswin.h"
#include "../x68k/adpcm.h"
#include "../fmgen/fmg_wrap.h"
#include "rr_state.h"

#define RING_BYTES (2 * 2 * 48000)
#define CLOCK_UNIT 10000000

static BYTE ring[RING_BYTES];
/* Ring bounds and positions; the authored session checks drive them directly. */
BYTE *pbsp = ring, *pbep = ring + RING_BYTES, *pbrp = ring, *pbwp = ring;
static int32_t precounter = 0;
static int playing = 0;

void DSound_Play(void) { playing = 1; }
void DSound_Stop(void) { playing = 0; }

void DSound_Send0(long clock)
{
   int32_t frames;
   if (!playing || clock <= 0)
      return;
   precounter += RR_SOUND_RATE * (int32_t)clock;
   frames = precounter / CLOCK_UNIT;
   if (frames <= 0)
      return;
   precounter -= frames * CLOCK_UNIT;
   /* ADPCM writes the frames, OPM adds to them; both wrap at ring_end. */
   ADPCM_Update((short *)pbwp, (DWORD)frames, 0, pbsp, pbep);
   OPM_Update((short *)pbwp, frames, 0, pbsp, pbep);
   pbwp = pbsp + ((DWORD)(pbwp - pbsp) + (DWORD)frames * 4) % RING_BYTES;
}

int audio_samples_avail(void)
{
   DWORD bytes = ((DWORD)(pbwp - pbsp) + RING_BYTES - (DWORD)(pbrp - pbsp)) % RING_BYTES;
   return (int)(bytes / 4);
}

void raudio_callback(void *userdata, unsigned char *stream, int len)
{
   BYTE *out = (BYTE *)userdata;
   (void)stream;
   while (len > 0) {
      DWORD chunk = (DWORD)(pbep - pbrp);
      if (chunk > (DWORD)len)
         chunk = (DWORD)len;
      memcpy(out, pbrp, chunk);
      out += chunk;
      len -= (int)chunk;
      pbrp += chunk;
      if (pbrp >= pbep)
         pbrp = pbsp;
   }
}

/* Snapshot section DSND (RRX68MS1). */
void rr_state_dswin(RRState *s)
{
   DWORD read_offset = (DWORD)(pbrp - pbsp), write_offset = (DWORD)(pbwp - pbsp);
   rr_state_bytes(s, ring, sizeof ring);
   rr_state_i32(s, &precounter);
   rr_state_offset(s, &read_offset, RING_BYTES - 1);
   rr_state_offset(s, &write_offset, RING_BYTES - 1);
   rr_state_bool(s, &playing);
   if (s->loading && !s->error && ((read_offset & 3) || (write_offset & 3) ||
                                   precounter < 0 || precounter >= CLOCK_UNIT))
      rr_state_fail(s, "audio ring position is invalid");
   else if (s->loading && !s->error) {
      pbrp = pbsp + read_offset;
      pbwp = pbsp + write_offset;
   }
}
