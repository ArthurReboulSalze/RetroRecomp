/* Static ROM-PC dispatch. The operation bodies retain their upstream licences. */
#ifndef RR_SNES_NATIVE_STEPS_H
#define RR_SNES_NATIVE_STEPS_H
#include "snes/interp816.h"
typedef struct RrSnesNativeOp {
    uint8_t opcode;
    void (*execute)(Interp816 *cpu);
} RrSnesNativeOp;
const RrSnesNativeOp *rr_snes_native_lookup(Interp816 *cpu);
void rr_snes_native_set_enabled(bool enabled);
void rr16_snes_note_native(void);
void rr16_snes_note_interpreted(uint32_t pc);
void rr16_snes_observe_fallback(uint32_t pc);
bool rr_snes_read_ram_code(uint32_t pc, uint8_t bytes[4]);
#endif
