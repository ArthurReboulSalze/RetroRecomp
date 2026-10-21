/* Retro-Recomp X68000 compat: CPU interface expected by the 2014 machine code.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * The 2014 sources were written for the C68K core. This build uses Musashi;
 * native/x68000_machine/base74/cpu_bus.c provides the binding. Interrupt
 * raising in irqh.c is redirected to rr_cpu_* by the build adapter.
 */
#ifndef RR_BASE74_M68000_H
#define RR_BASE74_M68000_H

#include "common.h"
#include "m68k.h" /* register ids, as the PX68k header provides */

#ifdef __cplusplus
extern "C" {
#endif

extern int ICount;          /* frame cycle credit, decremented per slice */
extern int m68000_ICountBk; /* cycles not consumed by the last slice */

void m68000_init(void);
void m68000_reset(void);

/* Interrupt line of the CPU (0 clears). Cuts the current slice so the next
 * m68k_execute samples the new level at once, as the 2014 core did. */
void rr_cpu_set_irq(int level);
DWORD rr_cpu_get_pc(void);

/* Remaining C68K names in the kept sources (trace output only). */
typedef struct { int ICount; } rr_c68k_compat;
extern rr_c68k_compat C68K;
#define C68K_PC 0
#define HOLD_LINE 1
#define C68k_Get_Reg(cpu, reg) rr_cpu_get_pc()

#ifdef __cplusplus
}
#endif

#endif
