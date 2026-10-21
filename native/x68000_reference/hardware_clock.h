/* Original RetroRecomp hardware accounting, MIT. Integer guest clocks only. */
#ifndef RR_X68000_HARDWARE_CLOCK_H
#define RR_X68000_HARDWARE_CLOCK_H
#include "probe.h"
/* frames, cpu cycles, peripheral 10MHz ticks, lines, emitted stereo pairs,
 * audio errors, maximum batch, most recent frame budget. */
RR_X68K_EXPORT void rr_x68k_hardware_snapshot(uint64_t counters[8]);
void rr_x68k_hardware_restore(const uint64_t counters[8]);
void rr_x68k_hardware_frame(unsigned budget);
void rr_x68k_hardware_tick(unsigned cpu, unsigned peripheral);
void rr_x68k_hardware_line(void);
void rr_x68k_hardware_audio(unsigned pairs);
void rr_x68k_hardware_audio_error(void);
#endif
