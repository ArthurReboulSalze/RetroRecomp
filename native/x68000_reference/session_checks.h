/* Original RetroRecomp authored state-continuation diagnostics, MIT. */
#ifndef RR_X68000_SESSION_CHECKS_H
#define RR_X68000_SESSION_CHECKS_H
#include "probe.h"
#define RR_X68K_SESSION_EXPECTED UINT32_C(2047)
#ifdef __cplusplus
extern "C" {
#endif
/* Destructive fixture suite: invoke only after normal reports and capture. */
RR_X68K_EXPORT uint32_t rr_x68k_session_checks(const char *json_path);
#ifdef __cplusplus
}
#endif
#endif
