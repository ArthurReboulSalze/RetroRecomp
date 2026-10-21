/* Original RetroRecomp reference instrumentation, MIT. */
#ifndef RR_X68000_REFERENCE_PROBE_H
#define RR_X68000_REFERENCE_PROBE_H

#include <stdint.h>
#include <time.h>

#if defined(_WIN32)
#define RR_X68K_EXPORT __declspec(dllexport)
#elif defined(__GNUC__)
#define RR_X68K_EXPORT __attribute__((visibility("default")))
#else
#define RR_X68K_EXPORT
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* Stable order: PC, SR, D0..D7, A0..A7; inspect only between retro_run calls. */
RR_X68K_EXPORT void rr_x68k_get_cpu(uint32_t regs[18]);

/* Elapsed emulated microseconds since boot, using 2000-01-01T00:00:00Z. */
RR_X68K_EXPORT void rr_x68k_set_clock(uint64_t simulated_usec);

/* These replace libc functions only in the upstream RTC compilation unit. */
time_t rr_x68k_time(time_t *result);
struct tm *rr_x68k_localtime(const time_t *value);

#ifdef __cplusplus
}
#endif
#endif
