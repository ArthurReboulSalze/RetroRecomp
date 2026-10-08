/* Private NESRecomp generator extension, included by nes_codegen.py.
 *
 * Compile every physical PRG byte once, irrespective of the CPU slot in which
 * a mapper exposes it. Equal (opcode, known operands) share a native body.
 * There is no opcode decoder or interpreter call in this generated path.
 * Bus cycles still run through the normal CPU/PPU/APU helpers. Only operands
 * in the opcode's own 4 KiB bank can be constants: boundary operands are read
 * from the live bus, including $FFFF wrapping into RAM.
 *
 * A body ends after one instruction. Dispatch rechecks the live bank, so a
 * mapper write, interrupt, or jump cannot continue in an obsolete mapping.
 * Discovered hot paths retain the upstream multi-instruction native blocks.
 */
#define DENSE_GROUP_SHIFT 9
#define DENSE_GROUP_SIZE (1u << DENSE_GROUP_SHIFT)

static void emit_dense_rom(const Program *p, FILE *main_file, const char *prefix) {
    uint32_t positions = p->banks * SLOT_SIZE;
    size_t capacity = 1;
    while (capacity < (size_t)positions * 2) capacity <<= 1;
    uint32_t *keys = (uint32_t *)calloc(capacity, sizeof(uint32_t));
    uint32_t *ids = (uint32_t *)calloc(capacity, sizeof(uint32_t));
    uint32_t *body_keys = (uint32_t *)malloc((size_t)positions * sizeof(uint32_t));
    uint32_t *entries = (uint32_t *)malloc((size_t)positions * sizeof(uint32_t));
    if (!keys || !ids || !body_keys || !entries) {
        fprintf(stderr, "[cyc] out of memory for dense ROM generation\n");
        exit(1);
    }
    uint32_t count = 0;
    for (uint32_t i = 0; i < positions; i++) {
        uint32_t bank = i >> SLOT_SHIFT, k = i & (SLOT_SIZE - 1);
        uint8_t op = prg_byte(p, bank, k);
        int len = op_length(op);
        uint32_t key = op;
        for (int delta = 1; delta < len; delta++) {
            if (k + (uint32_t)delta >= SLOT_SIZE) continue;
            key |= (uint32_t)prg_byte(p, bank, k + delta) << (8 * delta);
            key |= 1u << (23 + delta);
        }
        size_t h = ((uint64_t)key * 2654435761u) & (capacity - 1);
        while (ids[h] && keys[h] != key) h = (h + 1) & (capacity - 1);
        if (!ids[h]) {
            keys[h] = key;
            body_keys[count] = key;
            ids[h] = ++count; /* zero is the hash-table empty marker */
        }
        entries[i] = ids[h] - 1;
    }

    uint32_t groups = (count + DENSE_GROUP_SIZE - 1) / DENSE_GROUP_SIZE;
    for (uint32_t group = 0; group < groups; group++) {
        char path[512];
        snprintf(path, sizeof(path), "generated/%s_cyc_dense_%03u.c", prefix, group);
        FILE *f = open_out(path);
        fprintf(f, "/* ROM-specialized native instruction bodies. Generated, do not edit. */\n"
                   "#include \"cyc_recomp.h\"\n\n");
        uint32_t first = group * DENSE_GROUP_SIZE;
        uint32_t end = first + DENSE_GROUP_SIZE;
        if (end > count) end = count;
        for (uint32_t id = first; id < end; id++) {
            uint32_t key = body_keys[id];
            Emit e = {0};
            e.f = f;
            e.p = p;
            e.dense = true;
            e.opcode = (uint8_t)key;
            e.dense_known = (uint8_t)(key >> 24);
            e.dense_bytes[0] = (uint8_t)(key >> 8);
            e.dense_bytes[1] = (uint8_t)(key >> 16);
            fprintf(f, "static void body_%u(void) {\n"
                       "    uint16_t pc = cpu.pc;\n"
                       "    uint8_t b1 = 0, b2 = 0;\n"
                       "    if (cpu_fetch_rom(pc, 0x%02X)) { cpu_interrupt(false); return; }\n",
                    id, e.opcode);
            emit_body(&e);
            fprintf(f, "    (void)pc; (void)b1; (void)b2;\n}\n\n");
        }
        fprintf(f, "void (*const cyc_dense_group_%u[])(void) = {\n", group);
        for (uint32_t id = first; id < end; id++) fprintf(f, "    body_%u,\n", id);
        fprintf(f, "};\n");
        fclose(f);
        fprintf(main_file, "extern void (*const cyc_dense_group_%u[])(void);\n", group);
    }
    fprintf(main_file, "\nstatic void (*const *const dense_groups[])(void) = {\n");
    for (uint32_t group = 0; group < groups; group++)
        fprintf(main_file, "    cyc_dense_group_%u,\n", group);
    fprintf(main_file, "};\nstatic const %s dense_entries[%u] = {",
            count <= 65536 ? "uint16_t" : "uint32_t", positions);
    for (uint32_t i = 0; i < positions; i++)
        fprintf(main_file, "%s%u,", i % 16 ? "" : "\n    ", entries[i]);
    fprintf(main_file,
        "\n};\n\n"
        "static bool dense_has(uint16_t pc) {\n"
        "    return pc >= 0x8000 && hw_prg_bank4(pc) < %uu;\n"
        "}\n"
        "static void dense_step(uint16_t pc) {\n"
        "    unsigned physical = (hw_prg_bank4(pc) << 12) | (pc & 0xFFF);\n"
        "    unsigned id = dense_entries[physical];\n"
        "    dense_groups[id >> %u][id & %uu]();\n"
        "}\n\n", p->banks, DENSE_GROUP_SHIFT, DENSE_GROUP_SIZE - 1);
    printf("[NESRecomp] Native PRG ROM positions: %u/%u; %u shared native bodies\n",
           p->prg_len, p->prg_len, count);
    free(keys); free(ids); free(body_keys); free(entries);
}
