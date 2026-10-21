/* Original RetroRecomp hardware accounting, MIT. No wall clock dependence. */
#include "hardware_clock.h"
#include <string.h>
static uint64_t counters[8];
void rr_x68k_hardware_snapshot(uint64_t out[8]) { if(out) memcpy(out,counters,sizeof(counters)); }
void rr_x68k_hardware_restore(const uint64_t in[8]) {
    memcpy(counters,in,sizeof(counters)); rr_x68k_set_clock(counters[2]/10);
}
void rr_x68k_hardware_frame(unsigned budget) { ++counters[0]; counters[7]=budget; }
void rr_x68k_hardware_tick(unsigned cpu,unsigned peripheral) {
    counters[1]+=cpu; counters[2]+=peripheral;
    rr_x68k_set_clock(counters[2]/10);
}
void rr_x68k_hardware_line(void) { ++counters[3]; }
void rr_x68k_hardware_audio(unsigned pairs) { counters[4]+=pairs; if(pairs>counters[6]) counters[6]=pairs; }
void rr_x68k_hardware_audio_error(void) { ++counters[5]; }
