#ifndef RR_MD_BUS_SCHEDULER_H
#define RR_MD_BUS_SCHEDULER_H
#include <stdbool.h>
#include <stdint.h>
/* Host stacks are live only inside this process, never in portable states. */
bool rr_md_bus_busy(void);
void rr_md_z80_bus_reset(void);
void machine_z80_bus_wait(void);
void machine_z80_bus_barrier(void);
void machine_z80_cycles(unsigned cycles);
void machine_z80_boundary(void);
void machine_z80_instruction_boundary(void);
void machine_z80_bus_control(void);
bool machine_z80_bus_acknowledged(void);
void machine_z80_bus_released(void);
/* The 68000 is about to touch Z80 RAM or bus/reset control. */
void machine_z80_main_access(void);
void rr_md_cpu_control_yield(void);
unsigned machine_vdp_phase(void);
/* Nominal bus cycles are paid within the instruction, not again at retirement. */
void rr_md_cpu_fetch_cycles(unsigned words, int locked);
unsigned rr_md_cpu_retire_cycles(unsigned cycles);
unsigned rr_md_cpu_stop_cycles(void);
bool machine_main_bus_split(void);
extern uint64_t rr_md_bus_budget_misses;
extern uint32_t rr_md_bus_budget_pc;
#endif
