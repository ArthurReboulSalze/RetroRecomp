/* The instruction AOT driver uses the real guest PC and stack. Legacy
 * C-function dispatch must never be entered for these cartridges. */
#include "genesis_runtime.h"
#include "md_native_steps.h"
#include <stddef.h>
extern void rr16_note_fault(void);
int g_split_sp_popped;
uint32_t rr_md_cpu_stopped;
int game_instruction_hook_site(uint32_t pc) { (void)pc; return 0; }
void recomp_call_addr(uint32_t pc) { (void)pc; rr16_note_fault(); }
void recomp_call_func(RecompFuncPtr fn) { (void)fn; rr16_note_fault(); }
void recomp_tail_call(uint32_t pc) { (void)pc; rr16_note_fault(); }
void call_by_address(uint32_t pc) { (void)pc; rr16_note_fault(); }
void *recomp_tail_frame_get(void) { return NULL; }
void recomp_tail_frame_set(void *frame) { if (frame) rr16_note_fault(); }
void recomp_tail_frame_walk(void (*visit)(int, uint32_t, void *), void *user) {
    (void)visit; (void)user;
}
int game_dispatch_table_size(void) { return 0; }
uint32_t game_dispatch_table_addr(int i) { (void)i; return 0; }
