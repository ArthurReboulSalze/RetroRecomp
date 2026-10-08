#ifndef RR_SNES_SPC_NATIVE_H
#define RR_SNES_SPC_NATIVE_H
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
typedef struct Spc Spc;
typedef struct { uint8_t opcode; void (*execute)(Spc *); } RrSpcNativeOp;
const RrSpcNativeOp *rr_spc_native_lookup(Spc *spc);
int rr_spc_reference_step(Spc *spc);
bool rr_spc_native_enabled(void);
void rr_spc_set_mode(bool enabled, bool probe);
void rr_spc_reset_evidence(void);
uint64_t rr_spc_native_opcodes(void);
uint64_t rr_spc_interpreted_opcodes(void);
void rr_spc_report(FILE *file);
void rr_snes_reset_audio_delivery(void);
#endif
