/* CPS-1 Z80 structural instruction AOT, keyed by physical sound ROM offsets
 * (fixed 0x0000-0x7fff and both banks) plus guarded RAM variants. */
#ifndef RR_CPS1_Z80_NATIVE_H
#define RR_CPS1_Z80_NATIVE_H
#include <stdint.h>
#include "z80.h"
typedef struct { unsigned mask; uint8_t bytes[4]; unsigned (*execute)(z80*); } RrCps1Z80Step;
int rr_cps1_z80_code_location(uint16_t pc,uint32_t *offset);
int rr_cps1_z80_code_byte(uint16_t pc,uint8_t *byte);
void rr_cps1_z80_note_fallback(uint16_t pc);
extern int rr_cps1_force_reference,rr_cps1_force_z80_reference;
extern uint64_t rr_cps1_native_z80;
#endif
