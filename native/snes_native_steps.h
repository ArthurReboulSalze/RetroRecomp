/* Static ROM-PC dispatch. The operation bodies retain their upstream licences. */
#ifndef RR_SNES_NATIVE_STEPS_H
#define RR_SNES_NATIVE_STEPS_H
#include "snes/interp816.h"
#define RR_SN_RAM_VARIANT_LIMIT 16384u
/* RR_SN_SA1 is 1 only in a game whose cartridge has an SA-1 (retro_snes_game.h); the fixtures do not have it. */
#if defined(__has_include)
#if __has_include("retro_snes_game.h")
#include "retro_snes_game.h"
#endif
#endif
#ifndef RR_SN_SA1
#define RR_SN_SA1 0
#endif
typedef struct RrSnesNativeOp {
    uint8_t opcode;
    void (*execute)(Interp816 *cpu);
} RrSnesNativeOp;
const RrSnesNativeOp *rr_snes_native_lookup(Interp816 *cpu);
const RrSnesNativeOp *rr_snes_native_lookup_fetched(uint32_t pc, uint8_t opcode);
void rr_snes_native_set_enabled(bool enabled);
/* Checks the loaded cartridge against the generated map once; call after the cartridge is loaded. */
bool rr_snes_native_bind(void);
#if RR_SN_SA1
bool rr_snes_is_sa1_cpu(const Interp816 *cpu);
/* How far behind the S-CPU the SA-1 stood (master clocks, negative: ahead) when the S-CPU reached it, before and after the sync. */
void rr_snes_sa1_before(int64_t behind);
void rr_snes_sa1_after(int64_t behind);
#endif
void rr16_snes_note_native(void);
void rr16_snes_note_interpreted(uint32_t pc);
void rr16_snes_observe_fallback(uint32_t pc);
bool rr_snes_read_ram_code(uint32_t pc, uint8_t bytes[4]);
#endif
