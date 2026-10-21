/* Original RetroRecomp authored hardware diagnostics, MIT. */
#ifndef RR_X68000_AUDIO_CHECKS_H
#define RR_X68000_AUDIO_CHECKS_H
#include "probe.h"
#define RR_X68K_AUDIO_EXPECTED UINT32_C(262143)
/* Destructive diagnostics: call only after gameplay capture/report, then quit.
 * No guest instructions run; results do not enter native/fallback counters. */
RR_X68K_EXPORT uint32_t rr_x68k_audio_checks(const char *json_path);
#endif
