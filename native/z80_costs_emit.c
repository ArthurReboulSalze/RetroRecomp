/* The banked emitter's bodies for every Z80 encoding, for the ROM-free check of a machine's instruction costs
 * (tools/z80_costs_selftest.py, native/z80_costs_checks.c). MIT, Retro-Recomp. Built for a check, never into a game.
 *
 * It includes the generator's source as the converter patches it for one machine (core.patched_generator_source: the pinned
 * code_generator.c with native/banked_emitter.inc rendered for that machine, its Z80Costs included), interns one encoding of
 * each opcode of the seven groups (no prefix, CB, DD, FD, ED, DD CB d, FD CB d) and a redundant prefix, and writes:
 *   argv[1]: the bodies the emitter writes for them, then `bodies[]` and `cases[]` (bytes and body, a fragment with the body
 *            of the instruction it precedes);
 * nothing else. The encodings the decoder refuses are left out: a conversion leaves them to the reference CPU. */
#include "code_generator.c"

static void encoding(int group, int opcode, uint8_t bytes[4]) {
    static const uint8_t first[7] = {0, 0xCB, 0xDD, 0xFD, 0xED, 0xDD, 0xFD};
    memset(bytes, 0, 4);
    switch (group) {
    case 0: bytes[0] = (uint8_t)opcode; bytes[1] = 0x05; bytes[2] = 0x34; bytes[3] = 0x12; break;
    case 1: bytes[0] = 0xCB; bytes[1] = (uint8_t)opcode; break;
    case 2: case 3: bytes[0] = first[group]; bytes[1] = (uint8_t)opcode; bytes[2] = 0x05; bytes[3] = 0x34; break;
    case 4: bytes[0] = 0xED; bytes[1] = (uint8_t)opcode; bytes[2] = 0x34; bytes[3] = 0x12; break;
    default: bytes[0] = first[group]; bytes[1] = 0xCB; bytes[2] = 0x05; bytes[3] = (uint8_t)opcode; break;
    }
}

int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "usage: z80_costs_emit bodies.inc\n"); return 2; }
    BankedOps pool;
    banked_pool_open(&pool, 4096);
    static uint8_t case_bytes[7 * 256 + 1][4];
    static uint32_t case_id[7 * 256 + 1], case_next[7 * 256 + 1];
    unsigned cases = 0;
    for (int group = 0; group < 7; ++group) {
        for (int opcode = 0; opcode < 256; ++opcode) {
            if ((group == 0 || group == 2 || group == 3) && (opcode == 0xCB || opcode == 0xDD || opcode == 0xED || opcode == 0xFD))
                continue;                                   /* a prefix: its own group, or a fragment below */
            uint8_t bytes[4];
            encoding(group, opcode, bytes);
            uint32_t id = banked_intern(&pool, bytes);
            if (!id) continue;
            memcpy(case_bytes[cases], bytes, 4); case_id[cases] = id; case_next[cases] = 0; ++cases;
        }
    }
    /* A redundant DD before DD 00: the fragment's body, then the body of DD 00 (the reference runs both in one step). */
    const uint8_t fragment[4] = {0xDD, 0xDD, 0x00, 0x00}, after[4] = {0xDD, 0x00, 0x00, 0x00};
    uint32_t fragment_id = banked_intern(&pool, fragment), after_id = banked_intern(&pool, after);
    if (!fragment_id || !after_id) { fprintf(stderr, "the fragment was not interned\n"); return 1; }
    memcpy(case_bytes[cases], fragment, 4); case_id[cases] = fragment_id; case_next[cases] = after_id; ++cases;

    FILE *o = fopen(argv[1], "w");
    if (!o) return 1;
    fprintf(o, "/* Written by native/z80_costs_emit.c: the banked emitter's bodies, one per encoding. */\n");
    for (uint32_t id = 1; id <= pool.count; ++id) banked_body(o, &pool.ops[id], id);
    fprintf(o, "static void (*const bodies[])(void) = {0,\n");
    for (uint32_t id = 1; id <= pool.count; ++id) fprintf(o, "game_banked_op_%u,\n", id);
    fprintf(o, "};\nstatic const struct { uint8_t bytes[4]; uint32_t body, then; } cases[] = {\n");
    for (unsigned i = 0; i < cases; ++i)
        fprintf(o, "{{0x%02X,0x%02X,0x%02X,0x%02X},%u,%u},\n", case_bytes[i][0], case_bytes[i][1], case_bytes[i][2],
                case_bytes[i][3], case_id[i], case_next[i]);
    fprintf(o, "};\n");
    fclose(o);
    printf("encodings=%u bodies=%u\n", cases, pool.count);
    return 0;
}
