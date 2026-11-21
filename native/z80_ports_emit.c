/* The banked emitter's bodies for every Z80 I/O encoding of a machine with 16-bit ports, for the ROM-free check of the ports
 * (tools/z80_ports_selftest.py, native/z80_ports_checks.c). MIT, Retro-Recomp. Built for a check, never into a game.
 *
 * It includes the generator's source as the converter patches it for a machine with `Z80Machine.port_bits = 16` (its banked
 * emitter re-spells the I/O calls of each file of bodies, banked_io16_file), interns the encodings, writes their bodies and the
 * table of cases to argv[1], then has that file re-spelled as a conversion's are. */
#include "code_generator.c"

static const uint8_t encodings[][4] = {
    {0xDB, 0x7F, 0, 0}, {0xD3, 0xFE, 0, 0},                              /* IN A,(n), OUT (n),A */
    {0xDD, 0xDB, 0x1F, 0}, {0xFD, 0xD3, 0xFD, 0},                        /* the same behind a prefix that does nothing */
    {0xED, 0x40}, {0xED, 0x48}, {0xED, 0x50}, {0xED, 0x58}, {0xED, 0x60}, {0xED, 0x68}, {0xED, 0x70}, {0xED, 0x78},
    {0xED, 0x41}, {0xED, 0x49}, {0xED, 0x51}, {0xED, 0x59}, {0xED, 0x61}, {0xED, 0x69}, {0xED, 0x71}, {0xED, 0x79},
    {0xED, 0xA2}, {0xED, 0xAA}, {0xED, 0xB2}, {0xED, 0xBA},              /* INI, IND, INIR, INDR */
    {0xED, 0xA3}, {0xED, 0xAB}, {0xED, 0xB3}, {0xED, 0xBB},              /* OUTI, OUTD, OTIR, OTDR */
};

int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "usage: z80_ports_emit bodies.inc\n"); return 2; }
    BankedOps pool;
    banked_pool_open(&pool, 256);
    unsigned count = sizeof encodings / sizeof encodings[0];
    uint32_t ids[sizeof encodings / sizeof encodings[0]];
    for (unsigned i = 0; i < count; ++i) {
        ids[i] = banked_intern(&pool, encodings[i]);
        if (!ids[i]) { fprintf(stderr, "encoding %u was not interned\n", i); return 1; }
    }
    FILE *o = fopen(argv[1], "w");
    if (!o) return 1;
    fprintf(o, "/* Written by native/z80_ports_emit.c: the banked emitter's bodies of the I/O encodings, 16-bit ports. */\n");
    for (uint32_t id = 1; id <= pool.count; ++id) banked_body(o, &pool.ops[id], id);
    fprintf(o, "static void (*const bodies[])(void) = {0,\n");
    for (uint32_t id = 1; id <= pool.count; ++id) fprintf(o, "game_banked_op_%u,\n", id);
    fprintf(o, "};\nstatic const struct { uint8_t bytes[4]; uint32_t body; } cases[] = {\n");
    for (unsigned i = 0; i < count; ++i)
        fprintf(o, "{{0x%02X,0x%02X,0x%02X,0x%02X},%u},\n", encodings[i][0], encodings[i][1], encodings[i][2], encodings[i][3], ids[i]);
    fprintf(o, "};\n");
    fclose(o);
    banked_io16_file(argv[1]);                    /* the re-spelling a conversion's files of bodies get */
    printf("encodings=%u bodies=%u\n", count, pool.count);
    return 0;
}
