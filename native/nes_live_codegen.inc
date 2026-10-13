/* AOT bodies for observed RAM entries and PPU-dependent ROM mappings.
 * Opcode fetch happens once on the real bus. Only precompiled, guarded
 * entries dispatch here; operand reads retain their individual bus cycles. */
static void emit_live_native(const Program *p, FILE *main_file, const char *prefix) {
    bool used[256] = {0};
    for (uint32_t i = 0; i < p->banks * SLOT_SIZE; i++)
        used[prg_byte(p, i >> SLOT_SHIFT, i & (SLOT_SIZE - 1))] = true;
    char path[512];
    snprintf(path, sizeof(path), "generated/%s_cyc_live.c", prefix);
    FILE *f = open_out(path);
    fprintf(f, "/* AOT live-operand bodies. Generated, do not edit. */\n#include \"cyc_recomp.h\"\n");
    for (unsigned op = 0; op < 256; op++) {
        if (!used[op]) continue;
        Emit e = {0}; e.f = f; e.p = p; e.dense = true; e.opcode = (uint8_t)op;
        fprintf(f, "static void live_%02X(void) {\n    uint16_t pc = cpu.pc;\n    uint8_t b1 = 0, b2 = 0;\n", op);
        emit_body(&e);
        fprintf(f, "    (void)pc; (void)b1; (void)b2;\n}\n");
    }
    fprintf(f, "void (*const cyc_live_bodies[256])(void) = {\n");
    for (unsigned op = 0; op < 256; op++) {
        if (used[op]) fprintf(f, "    live_%02X,\n", op);
        else fprintf(f, "    0,\n");
    }
    fprintf(f, "};\n"); fclose(f);
    fprintf(main_file, "#include \"cyc_core.h\"\nextern void (*const cyc_live_bodies[256])(void);\n"
        "/* RR_NES_RAM_GUARD_BEGIN */\n"
        "static bool ram_guard(uint16_t pc, uint8_t op) { (void)pc; (void)op; return false; }\n"
        "/* RR_NES_RAM_GUARD_END */\n"
        "static const uint8_t live_rom_opcodes[%u] = {", p->banks * SLOT_SIZE);
    for (uint32_t i = 0; i < p->banks * SLOT_SIZE; i++)
        fprintf(main_file, "%s%u,", i % 32 ? "" : "\n    ", prg_byte(p, i >> SLOT_SHIFT, i & (SLOT_SIZE - 1)));
    fprintf(main_file,
        "\n};\n"
        "static bool ram_has(uint16_t pc) {\n"
        "    uint8_t op; return rr_nes_ram_peek(pc, &op) && ram_guard(pc, op) && cyc_live_bodies[op];\n"
        "}\n"
        "static void live_step(uint16_t pc) {\n"
        "    uint64_t before = cyc_cycle_count();\n"
        "    hw_cycle_start(pc, HW_READ);\n"
        "    if (cyc_trace_enabled) cpu_trace_instruction(pc);\n"
        "    unsigned bank = 0; bool rom = rr_nes_rom_bank4(pc, &bank);\n"
        "    unsigned physical = (bank << 12) | (pc & 0xFFF);\n"
        "    uint8_t ignored; bool ram = rr_nes_ram_peek(pc, &ignored);\n"
        "    uint8_t op = hw_read(pc);\n"
        "    bool known = rom ? physical < %uu && live_rom_opcodes[physical] == op : ram && ram_guard(pc, op);\n"
        "    hw_cycle_finish(false);\n"
        "    if (cpu.do_nmi | cpu.do_irq | cpu.do_reset) { cpu_interrupt(false); return; }\n"
        "    rr_nes_note_ram(pc, op);\n"
        "    if (known && cyc_live_bodies[op]) cyc_live_bodies[op]();\n"
        "    else rr_nes_interp_fetched(pc, op, before, rom, bank);\n"
        "}\n\n", p->banks * SLOT_SIZE);
}
