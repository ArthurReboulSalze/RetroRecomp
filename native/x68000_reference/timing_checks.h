/* Original authored X68000 timing/device checks. MIT. */
#ifndef RR_X68000_TIMING_CHECKS_H
#define RR_X68000_TIMING_CHECKS_H
#include "probe.h"
#define RR_X68K_TIMING_EXPECTED UINT32_C(1048575)
#ifdef __cplusplus
extern "C" {
#endif
/* Diagnostic only, after gameplay evidence. Restores serialized state and CPU. */
RR_X68K_EXPORT uint32_t rr_x68k_timing_checks(const char *json_path);
#ifdef __cplusplus
}
#endif
#endif
