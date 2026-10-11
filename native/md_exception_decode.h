/* The three reserved trap words are one-word instructions on MC68000.
 * Normalize these explicit patterns before extent/legality checks; do not
 * turn decoder misses or later-CPU instructions into supported operations. */
#pragma once
#include "m68k_decoder.h"
static inline void rr_md_normalize_exception(M68KInstr *ins) {
    if (ins->words[0] == 0x4afau || ins->words[0] == 0x4afbu) {
        ins->mnemonic = MN_ILLEGAL;
        ins->size = M68K_SIZE_NONE;
        ins->word_count = 1;
        ins->byte_length = 2;
        ins->has_target = 0;
        for (unsigned i = 1; i < 8; ++i) ins->words[i] = 0;
    }
}
