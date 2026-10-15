#ifndef RR_NEOGEO_REFERENCE_H
#define RR_NEOGEO_REFERENCE_H
#include <stdint.h>
#include <stdio.h>
#include <stdbool.h>
#include "m68000_backend.h"
void rr_ng_reference_bind(void);
void rr_ng_reference_observer_enable(void);
extern int rr_ng_observations;
extern uint64_t rr_ng_z80_instructions;
extern uint64_t rr_ng_native_z80,rr_ng_m1_instructions,rr_ng_sm1_instructions;
extern uint8_t rr_ng_z80_fallback_pc[65536];
typedef struct {uint16_t pc;uint8_t bytes[4];} RrNgZ80Variant;
extern RrNgZ80Variant rr_ng_z80_variants[4096];
extern unsigned rr_ng_z80_variant_count;
void rr_ng_z80_note_fallback(uint16_t);
uint64_t rr_ng_z80_state_hash(void);
extern uint64_t rr_ng_bios_instructions, rr_ng_cart_instructions, rr_ng_ram_instructions;
extern uint8_t rr_ng_reached_pc[0x800000];
extern uint8_t rr_ng_reached_p[0x800000],rr_ng_reached_bios[0x10000];
typedef struct {uint16_t offset,words[8];uint8_t count;} RrNgRamVariant;
extern RrNgRamVariant rr_ng_ram_variants[4096];
extern unsigned rr_ng_ram_variant_count,rr_ng_ram_observations_truncated;
size_t rr_ng_board_extra_save(uint8_t*,size_t);
bool rr_ng_board_extra_valid(const uint8_t*,size_t);
bool rr_ng_board_extra_restore(const uint8_t*,size_t);
bool rr_ng_board_cart_state(void);
unsigned rr_ng_sound_latch(void);
void rr_ng_sound_latch_restore(unsigned);
size_t rr_ng_lspc_extra_save(uint8_t*,size_t);
bool rr_ng_lspc_extra_valid(const uint8_t*,size_t);
bool rr_ng_lspc_extra_restore(const uint8_t*,size_t);
extern int rr_ng_test_clock_enabled;
extern int64_t rr_ng_test_clock;
extern FILE *rr_ng_cpu_trace;
extern uint64_t rr_ng_trace_from,rr_ng_trace_limit;
extern unsigned rr_ng_trace_stride;
void rr_ng_note_instruction(uint32_t pc,int native);
void rr_ng_fallback_report(FILE *file);
const RrM68000Bus *rr_ng_cpu_bus(void);
int rr_ng_code_location(uint32_t address,RrM68000CodeLocation *location);
int rr_ng_code_matches(const RrM68000CodeLocation*,const uint16_t*,unsigned);
#endif
