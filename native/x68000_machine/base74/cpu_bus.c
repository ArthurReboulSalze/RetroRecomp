/* Retro-Recomp X68000: Musashi binding for the 2014 machine code.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Written from docs/X68000_PHASE3_PORTING.md section 2 and the Musashi API
 * (m68k.h). Replaces m68000/m68000.c (not used in this build).
 */
#include "common.h"
#include "m68000/m68000.h"
#include "memory.h"
#if defined(RR_X68000_EXTENDED_CPU_STATE) || defined(RR_X68000_BASE74)
#include "m68k.h"
#else
#include "musashi/m68k.h"
#endif

int ICount = 0;
int m68000_ICountBk = 0;
rr_c68k_compat C68K;

extern void *IRQH_CallBack[8];
/* Present in both Musashi copies; not every m68k.h declares them. */
int m68k_cycles_remaining(void);
void m68k_modify_timeslice(int cycles);

/* Musashi memory interface onto the X68000 bus (x68k/mem_wrap.c). */
unsigned m68k_read_memory_8(unsigned address) { return cpu_readmem24(address); }
unsigned m68k_read_memory_16(unsigned address) { return cpu_readmem24_word(address); }
unsigned m68k_read_memory_32(unsigned address) { return cpu_readmem24_dword(address); }
unsigned m68k_read_immediate_16(unsigned address) { return cpu_readmem24_word(address); }
unsigned m68k_read_immediate_32(unsigned address) { return cpu_readmem24_dword(address); }
unsigned m68k_read_pcrelative_8(unsigned address) { return cpu_readmem24(address); }
unsigned m68k_read_pcrelative_16(unsigned address) { return cpu_readmem24_word(address); }
unsigned m68k_read_pcrelative_32(unsigned address) { return cpu_readmem24_dword(address); }
void m68k_write_memory_8(unsigned address, unsigned value) { cpu_writemem24(address, (BYTE)value); }
void m68k_write_memory_16(unsigned address, unsigned value) { cpu_writemem24_word(address, (WORD)value); }
void m68k_write_memory_32(unsigned address, unsigned value) { cpu_writemem24_dword(address, value); }

void m68000_init(void)
{
   m68k_set_cpu_type(M68K_CPU_TYPE_68000);
   m68k_init();
}

void m68000_reset(void)
{
   m68k_pulse_reset();
}

DWORD rr_cpu_get_pc(void)
{
   return (DWORD)m68k_get_reg(NULL, M68K_REG_PC);
}

void rr_cpu_set_irq(int level)
{
   int remaining;
   m68k_set_irq((unsigned)level);
   /* End the running slice after the current instruction: the caller of
    * m68k_execute still receives the cycles actually used. */
   remaining = m68k_cycles_remaining();
   if (level && remaining > 0)
      m68k_modify_timeslice(-remaining);
}

/* Interrupt acknowledge (M68K_INT_ACK_CALLBACK): the device routine of the
 * pending level returns its vector, or (DWORD)-1 for the autovector. */
int my_irqh_callback(int level)
{
   typedef DWORD (*Vector)(BYTE);
   Vector handler = (Vector)IRQH_CallBack[level & 7];
   DWORD vector = handler ? handler((BYTE)level) : (DWORD)-1;
   return vector == (DWORD)-1 ? (int)M68K_INT_ACK_AUTOVECTOR : (int)vector;
}

/* Diagnostics required by the machine code; never stop emulation. */
void Error(const char *message)
{
   (void)message;
}

void p6logd(const char *format, ...)
{
   (void)format;
}

DWORD timeGetTime(void)
{
   return 0;
}

int hddtrace = 0;
