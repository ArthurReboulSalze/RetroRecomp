/* Retro-Recomp Nintendo 64: the native blocks and the observation of the VR4300 (n64_cpu.c). Original Retro-Recomp code, MIT. */
#ifndef RR_N64_CPU_H
#define RR_N64_CPU_H
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

struct r4300_core;

/* One generated block: its address, its words (delay slot included), the function that runs it (returns the instructions it
 * ran, counted as the interpreter's loop counts them: a jump and its delay slot are one). */
typedef struct RrN64Block {
    uint32_t pc, len;
    int (*run)(struct r4300_core *r4300, const uint32_t *live);
    const uint32_t *words;
} RrN64Block;
extern const RrN64Block rr_n64_blocks[];
extern const uint32_t rr_n64_block_count;

/* 0: the core's cached interpreter (nothing here); 1: pure interpreter with observation; 2: native blocks, the pure interpreter
 * for the rest. Set before the game starts. */
extern int rr_n64_cpu_mode;
/* Instructions run by the interpreters (both count), by native blocks; block entries; guard misses (a block's words were not
 * the live ones: the interpreter ran instead). */
extern uint64_t rr_n64_interpreted, rr_n64_native, rr_n64_block_entries, rr_n64_guard_misses;

int rr_n64_set_observe(int enabled);   /* 1: ready (allocates the table) */
size_t rr_n64_observation_count(void);
int rr_n64_observation_overflow(void); /* 1: the table filled up and later leaders were not kept */
int rr_n64_write_observations(FILE *out);

int rr_n64_is_flow(uint32_t op);
int rr_n64_has_delay(uint32_t op);

/* FNV-1a 64 of the general registers, HI/LO, the PC and the COP0 registers. */
uint64_t rr_n64_cpu_state_hash(void);
uint32_t rr_n64_cpu_pc(void);

#ifdef __cplusplus
}
#endif
#endif
