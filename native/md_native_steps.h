/* Runtime ABI for individually translated ROM instructions. */
#pragma once
#include "m68k_interp.h"
#include "m68k_decoder.h"
typedef struct {
    M68KInstr instruction;
    unsigned cycles;
    M68kiStatus (*execute)(uint32_t *next_pc);
} RrMdNativeStep;
const RrMdNativeStep *rr_md_native_lookup(uint32_t pc);
extern int rr_md_illegal_ea;
void rr16_note_rom_fallback(uint32_t pc);
void rr16_note_ram_instruction(const M68KInstr *instruction);
