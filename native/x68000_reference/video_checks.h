/* Original RetroRecomp authored hardware vectors, MIT. */
#ifndef RR_X68000_VIDEO_CHECKS_H
#define RR_X68000_VIDEO_CHECKS_H
#include "probe.h"

#define RR_X68K_VIDEO_CHECK_COUNT 21u
#define RR_X68K_VIDEO_EXPECTED UINT32_C(2097151)

/* Developer diagnostics only, after gameplay reports/captures.  No guest CPU
 * instructions run.  The full machine snapshot is restored before returning.
 * Expected vectors are authored from the documented address/bit/pixel model;
 * they are not captured from a second run of this renderer. */
RR_X68K_EXPORT uint32_t rr_x68k_video_checks(const char *json_path);
#endif
