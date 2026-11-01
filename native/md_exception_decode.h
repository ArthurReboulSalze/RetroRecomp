/* Decoding rules of the original MC68000 that the pinned decoder does not apply.
 * It is written for the 68010 and 68020 as well and stays permissive; the
 * Mega Drive, Neo Geo, CPS-1 and X68000 all hold a 68000. Each rule below
 * comes from the Motorola M68000 Programmer's
 * Reference Manual (instruction set summary, the addressing-mode tables of
 * JMP, JSR, LEA and PEA, the Bcc displacement field), not from any other
 * implementation. A decoder miss or a later-CPU instruction is never turned
 * into a supported operation: a word the 68000 does not know is the illegal
 * instruction exception (vector 4), the same as $4AFC.
 *
 *  - $4AFA and $4AFB are reserved words, one word each.
 *  - MOVEC ($4E7A, $4E7B) and BKPT ($4848 to $484F) belong to the 68010.
 *  - JMP, JSR, LEA and PEA take a control addressing mode only: (An), d16(An),
 *    d8(An,Xn), abs.W, abs.L, d16(PC), d8(PC,Xn). Dn, An, (An)+, -(An), the
 *    immediate and the reserved modes 5 to 7 of mode 7 are not defined.
 *  - The Bcc, BRA and BSR displacement is the 8 bits of the opcode word, or
 *    the following word when they are zero. $FF is the displacement -1 of a
 *    one-word instruction (a 32-bit displacement exists from the 68020). */
#pragma once
#include <string.h>
#include "m68k_decoder.h"

/* Control addressing: modes 2 (An), 5, 6, and mode 7 with registers 0 to 3. */
static inline int rr_md_control_ea(unsigned ea) {
    unsigned mode = (ea >> 3) & 7u, reg = ea & 7u;
    return mode == 2u || mode == 5u || mode == 6u || (mode == 7u && reg <= 3u);
}

/* 1 when the opcode word is not an instruction of the MC68000. Only words that
 * the pinned decoder reads as a valid instruction of a later CPU, or as one of
 * the four instructions above with an undefined addressing mode, are listed. */
static inline int rr_md_not_mc68000(uint16_t word) {
    if (word == 0x4e7au || word == 0x4e7bu) return 1;                    /* MOVEC */
    if ((word & 0xfff8u) == 0x4848u) return 1;                          /* BKPT #n */
    if ((word & 0xffc0u) == 0x4ec0u || (word & 0xffc0u) == 0x4e80u)     /* JMP, JSR */
        return !rr_md_control_ea(word & 0x3fu);
    if ((word & 0xf1c0u) == 0x41c0u) return !rr_md_control_ea(word & 0x3fu); /* LEA */
    if ((word & 0xffc0u) == 0x4840u && (word & 0x38u) != 0u)            /* PEA; SWAP is mode 0 */
        return !rr_md_control_ea(word & 0x3fu);
    return 0;
}

static inline void rr_md_normalize_exception(M68KInstr *ins) {
    if (ins->words[0] == 0x4afau || ins->words[0] == 0x4afbu) {
        ins->mnemonic = MN_ILLEGAL;
        ins->size = M68K_SIZE_NONE;
        ins->word_count = 1;
        ins->byte_length = 2;
        ins->has_target = 0;
        for (unsigned i = 1; i < 8; ++i) ins->words[i] = 0;
    } else if (rr_md_not_mc68000((uint16_t)ins->words[0])) {
        /* The instruction the decoder built (and its extension words) does not
         * exist: keep the first word and the address, as the decoder does for $4AFC. */
        uint32_t address = ins->addr;
        uint16_t word = ins->words[0];
        memset(ins, 0, sizeof *ins);
        ins->addr = address;
        ins->mnemonic = MN_ILLEGAL;
        ins->size = M68K_SIZE_NONE;
        ins->words[0] = word;
        ins->word_count = 1;
        ins->byte_length = 2;
        ins->reg = -1;
    } else if ((ins->words[0] & 0xf0ffu) == 0x60ffu) {
        /* The decoder read the 32-bit displacement form of the 68020. */
        ins->word_count = 1;
        ins->byte_length = 2;
        ins->target_addr = ins->addr + 2u - 1u;
        ins->has_target = 1;
        for (unsigned i = 1; i < 8; ++i) ins->words[i] = 0;
    }
}
