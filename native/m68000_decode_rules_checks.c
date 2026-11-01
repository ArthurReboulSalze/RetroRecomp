/* The decoding rules of the original MC68000 (native/md_exception_decode.h), checked on all 65,536 opcode words and on
 * a few hand-written byte sequences. No ROM and no machine: the pinned decoder reads a 16-byte buffer.
 *
 * The expectation below is independent of the header: it is written from the addressing-mode tables of the Motorola
 * M68000 Programmer's Reference Manual (the control modes of JMP, JSR, LEA and PEA by their six-bit EA field), not by
 * calling the header's predicate. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "m68k_decoder.h"
#include "m68k_validator.h"
#include "rom_parser.h"
#include "md_exception_decode.h"

#define BASE 0x1000u
static uint8_t image[16];
static uint8_t fetch(uint32_t pc, void *user) {
    (void)user;
    return pc >= BASE && pc - BASE < sizeof image ? image[pc - BASE] : 0xff;
}
static unsigned checks;
#define CHECK(ok) do { ++checks; if (!(ok)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #ok); exit(1); } } while (0)

static int decode_bytes(const uint8_t *bytes, unsigned length, M68KInstr *ins, int normalize) {
    memset(image, 0, sizeof image);
    memcpy(image, bytes, length);
    GenesisRom rom = {0};
    rom.rom_size = BASE + sizeof image;
    rom.read8_override = fetch;
    if (!m68k_decode(&rom, BASE, ins)) return 0;
    if (normalize) rr_md_normalize_exception(ins);
    return 1;
}
static int decode_word(unsigned word, M68KInstr *ins, int normalize) {
    /* Extension words that make every multi-word form long enough to be taken whole. */
    const uint8_t bytes[16] = {(uint8_t)(word >> 8), (uint8_t)word, 0x12, 0x34, 0x56, 0x78, 0x00, 0x20,
                               0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
    return decode_bytes(bytes, sizeof bytes, ins, normalize);
}

/* Control addressing by the EA field (mode in bits 5-3, register in bits 2-0): (An) $10-$17, d16(An) $28-$2F,
 * d8(An,Xn) $30-$37, abs.W $38, abs.L $39, d16(PC) $3A, d8(PC,Xn) $3B. */
static int manual_control(unsigned ea) {
    return (ea >= 0x10 && ea <= 0x17) || (ea >= 0x28 && ea <= 0x3b);
}
enum { NONE, MOVEC, BKPT, JMP, JSR, LEA, PEA };
static int family(unsigned w) {
    if (w == 0x4e7a || w == 0x4e7b) return MOVEC;
    if (w >= 0x4848 && w <= 0x484f) return BKPT;
    if ((w & 0xffc0) == 0x4ec0) return JMP;
    if ((w & 0xffc0) == 0x4e80) return JSR;
    if ((w & 0xf1c0) == 0x41c0) return LEA;
    if ((w & 0xffc0) == 0x4840 && (w & 0x38) != 0) return PEA;   /* mode 0 is SWAP */
    return NONE;
}
static int manual_illegal(unsigned w) {
    int f = family(w);
    if (f == MOVEC || f == BKPT) return 1;
    return f != NONE && !manual_control(w & 0x3f);
}

typedef struct { const char *name; uint8_t bytes[6]; unsigned length; M68KMnemonic mnemonic; unsigned byte_length; } Written;
static const Written written[] = {
    {"MOVEC Rc,Rn",       {0x4e, 0x7a, 0x08, 0x01}, 4, MN_ILLEGAL, 2},
    {"MOVEC Rn,Rc",       {0x4e, 0x7b, 0x08, 0x01}, 4, MN_ILLEGAL, 2},
    {"BKPT #0",           {0x48, 0x48},             2, MN_ILLEGAL, 2},
    {"BKPT #7",           {0x48, 0x4f},             2, MN_ILLEGAL, 2},
    {"LEA D0,A0",         {0x41, 0xc0},             2, MN_ILLEGAL, 2},
    {"LEA #imm,A0",       {0x41, 0xfc, 0, 0, 0, 1}, 6, MN_ILLEGAL, 2},
    {"LEA (A0)+,A1",      {0x43, 0xd8},             2, MN_ILLEGAL, 2},
    {"LEA (A0),A1",       {0x43, 0xd0},             2, MN_LEA, 2},
    {"LEA d16(PC),A0",    {0x41, 0xfa, 0x00, 0x08}, 4, MN_LEA, 4},
    {"JMP D0",            {0x4e, 0xc0},             2, MN_ILLEGAL, 2},
    {"JMP -(A0)",         {0x4e, 0xe0},             2, MN_ILLEGAL, 2},
    {"JMP (A0)",          {0x4e, 0xd0},             2, MN_JMP, 2},
    {"JMP abs.L",         {0x4e, 0xf9, 0, 0, 0x02, 0}, 6, MN_JMP, 6},
    {"JSR A0",            {0x4e, 0x88},             2, MN_ILLEGAL, 2},
    {"JSR #imm",          {0x4e, 0xbc, 0, 0, 0, 1}, 6, MN_ILLEGAL, 2},
    {"JSR abs.L",         {0x4e, 0xb9, 0, 0, 0x02, 0}, 6, MN_JSR, 6},
    {"PEA A0",            {0x48, 0x48},             2, MN_ILLEGAL, 2},
    {"PEA (A0)+",         {0x48, 0x58},             2, MN_ILLEGAL, 2},
    {"PEA (A0)",          {0x48, 0x50},             2, MN_PEA, 2},
    {"SWAP D0 (not PEA)", {0x48, 0x40},             2, MN_SWAP, 2},
    {"RTS",               {0x4e, 0x75},             2, MN_RTS, 2},
    {"BRA.B $FF",         {0x60, 0xff, 0, 0, 0, 0}, 6, MN_BRA, 2},
    {"BSR.B $FF",         {0x61, 0xff, 0, 0, 0, 0}, 6, MN_BSR, 2},
    {"BNE.B $FF",         {0x66, 0xff, 0, 0, 0, 0}, 6, MN_Bcc, 2},
    {"BRA.W (word 0)",    {0x60, 0x00, 0x00, 0x10}, 4, MN_BRA, 4},
};

int main(void) {
    unsigned words_total = 0, illegal_words = 0, per_family[7] = {0}, accepted_before[7] = {0}, branch_words = 0;
    M68KValidatorOptions options = {0};
    for (unsigned w = 0; w < 0x10000; ++w) {
        M68KInstr raw, now;
        int raw_ok = decode_word(w, &raw, 0), now_ok = decode_word(w, &now, 1);
        CHECK(raw_ok == now_ok);
        if (!raw_ok) continue;
        ++words_total;
        if (w == 0x4afa || w == 0x4afb) {
            /* The reserved words of the earlier rule: one word, the illegal instruction. */
            CHECK(now.mnemonic == MN_ILLEGAL && now.word_count == 1 && now.byte_length == 2);
            continue;
        }
        if (manual_illegal(w)) {
            int f = family(w);
            ++illegal_words; ++per_family[f];
            if (raw.mnemonic != MN_ILLEGAL) ++accepted_before[f];
            CHECK(now.mnemonic == MN_ILLEGAL && now.size == M68K_SIZE_NONE);
            CHECK(now.addr == BASE && now.words[0] == w && now.word_count == 1 && now.byte_length == 2);
            for (unsigned i = 1; i < M68K_MAX_WORDS; ++i) CHECK(now.words[i] == 0);
            CHECK(!now.has_target && now.reg == -1);
            CHECK(m68k_validate(&now, &options) == M68K_LEGAL);
            continue;
        }
        if ((w & 0xf0ff) == 0x60ff) {
            /* A one-word branch with the displacement -1: the target is the odd address after the opcode word. */
            ++branch_words;
            unsigned condition = (w >> 8) & 15;
            CHECK(now.mnemonic == (condition == 0 ? MN_BRA : condition == 1 ? MN_BSR : MN_Bcc));
            CHECK(now.word_count == 1 && now.byte_length == 2 && now.has_target && now.target_addr == BASE + 1);
            for (unsigned i = 1; i < M68K_MAX_WORDS; ++i) CHECK(now.words[i] == 0);
            /* The validator still refuses it as speculative code: scans do not translate it. */
            CHECK(m68k_validate(&now, &options) == M68K_ILLEGAL_NON_MC68000);
            continue;
        }
        /* Every other word is decoded exactly as before: no collateral change. */
        CHECK(!memcmp(&raw, &now, sizeof raw));
    }
    fprintf(stderr, "words not of the MC68000: %u (LEA %u, JSR %u, JMP %u, PEA %u, BKPT %u, MOVEC %u)\n", illegal_words,
            per_family[LEA], per_family[JSR], per_family[JMP], per_family[PEA], per_family[BKPT], per_family[MOVEC]);
    CHECK(illegal_words == 288 + 36 + 36 + 28 + 2);        /* LEA, JSR, JMP, PEA (20 + the 8 of BKPT), MOVEC */
    CHECK(per_family[LEA] == 288 && per_family[JSR] == 36 && per_family[JMP] == 36);
    CHECK(per_family[PEA] == 20 && per_family[BKPT] == 8 && per_family[MOVEC] == 2);
    CHECK(branch_words == 16);                                /* $60FF to $6FFF */
    for (unsigned i = 0; i < sizeof written / sizeof *written; ++i) {
        M68KInstr ins;
        CHECK(decode_bytes(written[i].bytes, written[i].length, &ins, 1));
        if (ins.mnemonic != written[i].mnemonic || ins.byte_length != written[i].byte_length) {
            fprintf(stderr, "FAIL %s: mnemonic %d length %u\n", written[i].name, ins.mnemonic, ins.byte_length);
            exit(1);
        }
        ++checks;
    }
    printf("{\"passed\":true,\"checks\":%u,\"opcode_words\":65536,\"decoded_words\":%u,\"not_mc68000_words\":%u,"
           "\"accepted_by_the_pinned_decoder\":{\"LEA\":%u,\"JSR\":%u,\"JMP\":%u,\"PEA\":%u,\"BKPT\":%u,\"MOVEC\":%u},"
           "\"branch_words_ff\":%u,\"written_cases\":%u}\n",
           checks, words_total, illegal_words, accepted_before[LEA], accepted_before[JSR], accepted_before[JMP],
           accepted_before[PEA], accepted_before[BKPT], accepted_before[MOVEC], branch_words,
           (unsigned)(sizeof written / sizeof *written));
    return 0;
}
