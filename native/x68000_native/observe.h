/* Original RetroRecomp private X68000 CPU diagnostics, MIT. */
#ifndef RR_X68000_OBSERVE_H
#define RR_X68000_OBSERVE_H
#include <stdint.h>
#include <stdio.h>
#include "probe.h"
RR_X68K_EXPORT int rr_x68k_cpu_configure(int force_reference,int observations);
RR_X68K_EXPORT int rr_x68k_cpu_report(const char *path);
RR_X68K_EXPORT void rr_x68k_cpu_stats(uint64_t values[8]);
RR_X68K_EXPORT int rr_x68k_trace_configure(unsigned limit);
RR_X68K_EXPORT int rr_x68k_trace_report(const char *path);
void rr_x68k_before(uint32_t pc);
int rr_x68k_trace_active(void);
void rr_x68k_before_sr(uint32_t pc,uint32_t sr);
void rr_x68k_note_native(unsigned ram,unsigned ipl);
void rr_x68k_note(uint32_t pc,int native);
int rr_x68k_code_word(uint32_t pc,uint16_t *value);
extern int rr_x68k_force_reference;
#endif
