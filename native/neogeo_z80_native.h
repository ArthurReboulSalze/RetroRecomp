/* Structural instruction AOT, keyed by physical M1/SM1 ROM locations. */
#ifndef RR_NEOGEO_Z80_NATIVE_H
#define RR_NEOGEO_Z80_NATIVE_H
#include <stdint.h>
#include "z80/z80.h"
typedef struct { unsigned mask;uint8_t bytes[4];unsigned (*execute)(z80*); } RrNgZ80Step;
const RrNgZ80Step *rr_ng_z80_native_lookup(unsigned region,uint32_t offset);
const RrNgZ80Step *rr_ng_z80_ram_lookup(uint16_t pc);
void rr_ng_z80_note_fallback(uint16_t);
int rr_ng_z80_code_location(uint16_t pc,unsigned *region,uint32_t *offset);
int rr_ng_z80_code_byte(uint16_t pc,uint8_t *byte);
extern int rr_ng_force_reference;
extern int rr_ng_force_z80_reference;
extern uint64_t rr_ng_native_z80,rr_ng_z80_instructions;
extern uint64_t rr_ng_m1_instructions,rr_ng_sm1_instructions;
extern uint8_t rr_ng_z80_fallback_pc[65536];
#endif
