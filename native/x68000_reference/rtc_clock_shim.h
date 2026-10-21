/* Original RetroRecomp reference instrumentation, MIT. */
#ifndef RR_X68000_REFERENCE_RTC_CLOCK_SHIM_H
#define RR_X68000_REFERENCE_RTC_CLOCK_SHIM_H

/* Read the CRT header before redirecting calls. MSVC implements time/localtime
 * as inline wrappers; command-line macro replacement would rename those inline
 * definitions too and silently keep consulting the real host clock. */
#include "probe.h"
#define time rr_x68k_time
#define localtime rr_x68k_localtime

#endif
