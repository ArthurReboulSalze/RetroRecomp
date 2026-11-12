/* Appended to the pinned C emitter in its build copy. No runtime decoder:
 * every ROM byte position selects a precompiled, byte-specific instruction.
 * Identical encodings share a native body; PC-relative effects use the live PC.
 * This backend deliberately makes the guest stack explicit instead of using
 * the host C call stack, so arbitrary computed transfers and paging are safe. */
#include <inttypes.h>

/* The machine this generator is built for. Its values come from the machine's profile (retrorecomp/z80_chain.py writes
 * BANKED_MACHINE above this file): nothing below names a mapper or an address of its own. */
typedef struct {
    unsigned mapped;        /* 0: keyed by bank registers (the four fields below); 1: keyed by the machine's region map */
    unsigned slot_bits;     /* log2 of the size of one switchable slot (one region of the map) */
    unsigned slots;         /* registers: slots from address 0, one bank register each, the bank key of game_banked_step */
    unsigned fixed_bytes;   /* registers: start of slot 0 that never pages (0: none) */
    unsigned ram_from;      /* registers: first PC that only runs through the byte guards */
    unsigned sources;       /* map: how many sources (cartridge, firmware...) a region can show */
    unsigned bank_values;   /* values of a bank register */
    int m1_wait;            /* wait states per M1 cycle, added to the Z80's own T-states */
    const char *scope;      /* support_scope of the coverage report */
} BankedMachine;
static const BankedMachine banked_machine = BANKED_MACHINE;

typedef struct { uint64_t key; uint32_t id; } BankedHash;
typedef struct {
    BankedHash *hash;
    size_t mask;
    Z80Insn *ops;
    uint32_t count, capacity;
} BankedOps;

static int banked_key_order(const void *a, const void *b) {
    const BankedHash *x = (const BankedHash*)a, *y = (const BankedHash*)b;
    return (x->key > y->key) - (x->key < y->key);
}

static uint32_t banked_intern(BankedOps *pool, const uint8_t bytes[4]) {
    Z80Insn in;
    bool fragment = (bytes[0] == 0xDD || bytes[0] == 0xFD) &&
        (bytes[1] == 0xDD || bytes[1] == 0xFD || bytes[1] == 0xED);
    if (fragment) {
        /* A redundant index prefix is an M1 fragment, not an instruction.
         * The following prefix supersedes it. Verify BOTH bytes before using
         * this fragment in mutable memory; consume only the first byte.
         * This permits arbitrarily long streams without a runtime decoder. */
        memset(&in, 0, sizeof in);
        in.length = 1; in.illegal = true; /* private fragment tag */
        snprintf(in.text, sizeof in.text, "redundant %02X prefix before %02X", bytes[0], bytes[1]);
    } else {
        z80_decode(bytes, 4, 0, &in);
        if (in.illegal || !in.length || in.length > 4) return 0;
    }
    if (in.prefix == Z80_PFX_ED && (in.opcode & 0xC7) == 0x45)
        in.cf = Z80_CF_RET; /* include all RETN/RETI aliases */
    if ((in.prefix == Z80_PFX_NONE || in.prefix == Z80_PFX_DD ||
         in.prefix == Z80_PFX_FD) && in.opcode == 0x76) in.is_halt = true;
    unsigned verified = fragment ? 2 : in.length;
    uint64_t key = (uint64_t)verified << 32;
    for (unsigned i = 0; i < verified; ++i) key |= (uint64_t)bytes[i] << (8*i);
    size_t h = (size_t)((key * UINT64_C(11400714819323198485)) >> 17) & pool->mask;
    while (pool->hash[h].id && pool->hash[h].key != key) h = (h + 1) & pool->mask;
    if (pool->hash[h].id) return pool->hash[h].id;
    if (pool->count + 1 >= pool->capacity) {
        pool->capacity = pool->capacity ? pool->capacity * 2 : 1024;
        pool->ops = (Z80Insn*)realloc(pool->ops, pool->capacity * sizeof(*pool->ops));
        if (!pool->ops) { fprintf(stderr, "[banked] out of memory\n"); exit(1); }
    }
    uint32_t id = ++pool->count;
    pool->ops[id] = in;
    pool->hash[h].key = key; pool->hash[h].id = id;
    return id;
}

static void banked_cf(FILE *o, const Z80Insn *in) {
    const char *target = "";
    char value[80];
    bool relative = in->prefix != Z80_PFX_ED &&
        (in->opcode == 0x10 || in->opcode == 0x18 || (in->opcode & 0xE7) == 0x20);
    if (relative) snprintf(value, sizeof value, "(uint16_t)(s->pc + (%d))", (int8_t)in->imm);
    else snprintf(value, sizeof value, "0x%04X", in->target);
    target = value;
    switch (in->cf) {
    case Z80_CF_RET:
        if (in->prefix == Z80_PFX_ED) fprintf(o, "    s->iff1 = s->iff2;\n");
        fprintf(o, "    s->pc = sms_read16(s->sp); s->wz = s->pc; s->sp = (uint16_t)(s->sp + 2);\n");
        break;
    case Z80_CF_RET_COND:
        fprintf(o, "    if (%s) { s->cyc += 6; s->pc = sms_read16(s->sp); s->wz = s->pc; s->sp = (uint16_t)(s->sp + 2); }\n", cond((in->opcode >> 3) & 7));
        break;
    case Z80_CF_JUMP:
        if (in->has_target) fprintf(o, "    s->pc = %s; s->wz = s->pc;\n", target);
        else fprintf(o, "    s->pc = %s;\n", in->prefix == Z80_PFX_DD ? "s->ix" : in->prefix == Z80_PFX_FD ? "s->iy" : "z80_hl(s)");
        break;
    case Z80_CF_JUMP_COND:
        if (in->opcode == 0x10) {
            fprintf(o, "    s->b = (uint8_t)(s->b - 1);\n    if (s->b) { s->cyc += 5; s->pc = %s; s->wz = s->pc; }\n", target);
        } else if (relative) {
            fprintf(o, "    if (%s) { s->cyc += 5; s->pc = %s; s->wz = s->pc; }\n", cond((in->opcode >> 3) & 3), target);
        } else {
            fprintf(o, "    s->wz = %s; if (%s) s->pc = %s;\n", target, cond((in->opcode >> 3) & 7), target);
        }
        break;
    case Z80_CF_CALL:
        fprintf(o, "    s->sp = (uint16_t)(s->sp - 2); sms_write16(s->sp, s->pc); s->pc = %s; s->wz = s->pc;\n", target);
        break;
    case Z80_CF_CALL_COND:
        fprintf(o, "    s->wz = %s; if (%s) { s->cyc += 7; s->sp = (uint16_t)(s->sp - 2); sms_write16(s->sp, s->pc); s->pc = %s; }\n", target, cond((in->opcode >> 3) & 7), target);
        break;
    default: break;
    }
}

/* MEMPTR changes are part of the emitted instruction, including operations
 * which do not immediately expose WZ in a documented register. */
static void banked_wz(FILE *o, const Z80Insn *in) {
    unsigned op = in->opcode;
    const char *index = in->prefix == Z80_PFX_FD ? "s->iy" : "s->ix";
    if (in->uses_disp) {
        fprintf(o, "    s->wz = (uint16_t)(%s + (%d));\n",
            in->prefix == Z80_PFX_FD || in->prefix == Z80_PFX_FDCB ? "s->iy" : "s->ix", in->disp);
    } else if (in->prefix == Z80_PFX_ED) {
        if ((op & 0xC6) == 0x40) fprintf(o, "    s->wz = (uint16_t)(z80_bc(s) + 1);\n");
        else if ((op & 0xC7) == 0x42 || op == 0x67 || op == 0x6F)
            fprintf(o, "    s->wz = (uint16_t)(z80_hl(s) + 1);\n");
        else if ((op & 0xC7) == 0x43) fprintf(o, "    s->wz = 0x%04X;\n", (in->imm + 1) & 0xFFFF);
        else if ((op & 0xE4) == 0xA0) {
            int delta = (op & 8) ? -1 : 1;
            if ((op & 3) == 1) fprintf(o, "    s->wz = (uint16_t)(s->wz + (%d));\n", delta);
            else if ((op & 3) == 2) fprintf(o, "    s->wz = (uint16_t)(z80_bc(s) + (%d));\n", delta);
            else if ((op & 3) == 3) fprintf(o, "    s->wz = (uint16_t)(z80_bc(s) - 0x100 + (%d));\n", delta);
        }
    } else if (in->prefix == Z80_PFX_NONE || in->prefix == Z80_PFX_DD || in->prefix == Z80_PFX_FD) {
        if ((op & 0xCF) == 0x09) fprintf(o, "    s->wz = (uint16_t)(%s + 1);\n",
            in->prefix == Z80_PFX_NONE ? "z80_hl(s)" : index);
        else if (op == 0x02 || op == 0x12) fprintf(o, "    s->wz = (uint16_t)((s->a << 8) | ((%s + 1) & 255));\n", op == 2 ? "z80_bc(s)" : "z80_de(s)");
        else if (op == 0x0A || op == 0x1A) fprintf(o, "    s->wz = (uint16_t)(%s + 1);\n", op == 0xA ? "z80_bc(s)" : "z80_de(s)");
        else if (op == 0x22 || op == 0x2A || op == 0x3A) fprintf(o, "    s->wz = 0x%04X;\n", (in->imm + 1) & 0xFFFF);
        else if (op == 0x32 || op == 0xD3) fprintf(o, "    s->wz = (uint16_t)((s->a << 8) | 0x%02X);\n", (in->imm + 1) & 255);
        else if (op == 0xDB) fprintf(o, "    s->wz = (uint16_t)((s->a << 8) + 0x%02X + 1);\n", in->imm & 255);
    }
}

static bool banked_sets_flags(const Z80Insn *in) {
    unsigned op = in->opcode;
    if (in->prefix == Z80_PFX_CB || in->prefix == Z80_PFX_DDCB || in->prefix == Z80_PFX_FDCB) return op < 0x80;
    if (in->prefix == Z80_PFX_ED) return (op & 0xC7) == 0x40 || (op & 0xC7) == 0x42 ||
        (op & 0xC7) == 0x44 || op == 0x57 || op == 0x5F || op == 0x67 || op == 0x6F || (op & 0xE4) == 0xA0;
    return (op >= 0x80 && op < 0xC0) || (op & 0xC7) == 0xC6 ||
        (op < 0x40 && ((op & 7) == 4 || (op & 7) == 5 || (op & 7) == 7 || (op & 0xCF) == 9));
}

static void banked_body(FILE *o, const Z80Insn *in, uint32_t id) {
    fprintf(o, "void game_banked_op_%u(void) { /* %s */\n    Z80State *s = &g_z80;\n", id, in->text);
    if (in->illegal) {
        fprintf(o, "    s->pc++; s->r = (s->r & 0x80) | ((s->r + 1) & 0x7F); s->cyc += %d;\n}\n", 4 + banked_machine.m1_wait);
        return;
    }
    /* M1 cycles of the instruction: one, or two behind a prefix. R counts them, and so do the machine's wait states. */
    int m1 = in->prefix == Z80_PFX_NONE ? 1 : 2;
    fprintf(o, "    s->r = (uint8_t)((s->r & 0x80) | ((s->r + %d) & 0x7F));\n", m1);
    fprintf(o, "    s->pc = (uint16_t)(s->pc + %u);\n", in->length);
    banked_wz(o, in);
    if (in->prefix == Z80_PFX_DD || in->prefix == Z80_PFX_FD)
        fprintf(o, "    s->q = 0; /* index prefix resets the Q latch */\n");
    if (flat_is_repeat_block(in)) {
        const char *more = (in->opcode & 3) == 0 ? "z80_bc(s) != 0" :
            (in->opcode & 3) == 1 ? "z80_bc(s) != 0 && !(s->f & Z80_FLAG_Z)" : "s->b != 0";
        fprintf(o, "    s->cyc += %d;\n", 16 + m1 * banked_machine.m1_wait);
        emit_block_body(o, in->opcode, "    ");
        fprintf(o, "    if (%s) { s->cyc += 5; s->pc = (uint16_t)(s->pc - 2);", more);
        fprintf(o, " s->wz = (uint16_t)(s->pc + 1); s->f = (s->f & ~0x28) | ((s->pc >> 8) & 0x28);");
        /* NMOS repeat-cycle flags, visible when an IRQ interrupts the block.
         * See hoglet67/Z80Decoder, Undocumented-Flags; tested independently. */
        if ((in->opcode & 3) >= 2) fprintf(o,
            " uint8_t b = s->b; if (s->f & Z80_FLAG_C) {"
            " int neg = (s->f & Z80_FLAG_N) != 0;"
            " z80f_set(s, Z80_FLAG_H, (b & 15) == (neg ? 0 : 15));"
            " b = (uint8_t)(b + (neg ? -1 : 1)); }"
            " if (!z80_parity8(b & 7)) s->f ^= Z80_FLAG_P;");
        fprintf(o, " }\n");
    } else {
        fprintf(o, "    s->cyc += %d;\n", cyc_base(in) + m1 * banked_machine.m1_wait);
        if (in->is_halt) fprintf(o, "    s->halted = true;\n");
        else if (in->cf != Z80_CF_NONE) banked_cf(o, in);
        else if (in->prefix == Z80_PFX_CB && (in->opcode >> 6) == 1 && (in->opcode & 7) == 6) {
            /* BIT (HL) takes undocumented X/Y from the internal WZ register,
             * not the address in HL. Indexed BIT sets WZ to its effective EA. */
            fprintf(o, "    z80_bit(s, %d, sms_read8(z80_hl(s)), (uint8_t)(s->wz >> 8));\n", (in->opcode >> 3) & 7);
        } else emit_op(o, in);
    }
    fprintf(o, "    s->q = %s; s->p = %d;\n}\n", banked_sets_flags(in) ? "s->f" : "0",
        in->prefix == Z80_PFX_ED && (in->opcode == 0x57 || in->opcode == 0x5F));
}

static void banked_array(FILE *o, const char *name, const uint32_t *ids, size_t n) {
    fprintf(o, "static const uint32_t %s[%zu] = {\n", name, n);
    for (size_t i = 0; i < n; ++i) {
        fprintf(o, "%u,", ids[i]); if ((i & 15) == 15) fputc('\n', o);
    }
    fprintf(o, "\n};\n");
}

/* The bank key of game_banked_step on a machine keyed by registers: one register value per slot. */
static void banked_key(FILE *o) {
    for (unsigned slot = 0; slot < banked_machine.slots; ++slot) fprintf(o, "%suint8_t b%u", slot ? ", " : "", slot);
}

/* The prototype of game_banked_step, without its end: the bank registers, or the machine's region map. */
static void banked_step_signature(FILE *o) {
    fprintf(o, "int game_banked_step(");
    if (banked_machine.mapped) fprintf(o, "const BankedRegion *map");
    else banked_key(o);
    fprintf(o, ")");
}

/* How many banks of one slot a source of `size` bytes shows before it repeats. Mapper register values are bytes. For
 * partial final banks, use the exact modulo-ROM mapping of the bus, not ceil(size/slot) as a mirror period. */
static size_t banked_period(size_t size, size_t slot_size) {
    size_t x = size, y = slot_size;
    while (y) { size_t t = x % y; x = y; y = t; }
    size_t period = size / x;
    if (period > banked_machine.bank_values) { fprintf(stderr, "[banked] ROM bank period exceeds the mapper's bank registers\n"); exit(1); }
    return period;
}

static size_t banked_pool_open(BankedOps *pool, size_t entries) {
    size_t hash_size = 1024;
    while (hash_size < 2 * entries) hash_size *= 2;
    memset(pool, 0, sizeof *pool); pool->mask = hash_size - 1;
    pool->hash = (BankedHash*)calloc(hash_size, sizeof(*pool->hash));
    if (!pool->hash) exit(1);
    return hash_size;
}

/* Conversion-time observations contain data, never generated code. Decode
 * here and intern a byte-specific native body with the current compiler.
 * Execution is permitted only after comparing every instruction byte. */
static void banked_learn(BankedOps *pool, const char *dir, size_t *profile_windows, size_t *profile_unsupported) {
    char learned_path[600];
    snprintf(learned_path, sizeof learned_path, "%s/../native.patterns", dir);
    FILE *learned = fopen(learned_path, "r");
    *profile_windows = *profile_unsupported = 0;
    if (learned) {
        char line[80], extra; unsigned b[4];
        while (*profile_windows < 4096 && fgets(line, sizeof line, learned)) {
            if (sscanf(line, "%2x%2x%2x%2x %c", &b[0], &b[1], &b[2], &b[3], &extra) != 4) continue;
            uint8_t bytes[4] = {(uint8_t)b[0], (uint8_t)b[1], (uint8_t)b[2], (uint8_t)b[3]};
            ++*profile_windows;
            if (!banked_intern(pool, bytes)) ++*profile_unsupported;
        }
        fclose(learned);
    }
}

/* game_layout.c, game_banked.h and the native bodies. */
static void banked_write_bodies(const BankedOps *pool, const GameConfig *cfg, const char *dir) {
    char path[600];
    snprintf(path, sizeof path, "%s/game_layout.c", dir);
    write_layout(path, "game", cfg);
    snprintf(path, sizeof path, "%s/game_banked.h", dir);
    FILE *h = fopen(path, "w"); if (!h) exit(1);
    fprintf(h, "#pragma once\n#include <stddef.h>\n#include \"sms_runtime.h\"\n#include \"z80_ops.h\"\n");
    if (banked_machine.mapped) fprintf(h,
        "/* What one region of the address space shows now: the source (in the order the machine declares them), the bank\n"
        " * of that source in units of one region, or RAM. The machine's bus keeps the map; the step only reads it. */\n"
        "typedef struct { uint8_t source, bank, ram; } BankedRegion;\n");
    banked_step_signature(h);
    fprintf(h, ";\nint game_banked_guarded_step(void);\n");
    for (uint32_t id = 1; id <= pool->count; ++id) fprintf(h, "void game_banked_op_%u(void);\n", id);
    fclose(h);
    /* Small translation units keep MSVC memory and optimization time bounded. */
    for (uint32_t first = 1, chunk = 0; first <= pool->count; first += 256, ++chunk) {
        snprintf(path, sizeof path, "%s/game_banked_ops_%04u.c", dir, chunk);
        FILE *o = fopen(path, "w"); if (!o) exit(1);
        fprintf(o, "/* Generated byte-specific native bodies; no opcode decoding. */\n#include \"game_banked.h\"\n");
        for (uint32_t id = first; id <= pool->count && id < first+256; ++id) banked_body(o, &pool->ops[id], id);
        fclose(o);
    }
}

/* The tables every step uses and the guarded step; returns the number of guarded encodings. */
static size_t banked_write_tables(FILE *o, const BankedOps *pool, size_t hash_size) {
    fprintf(o, "static void (*const bodies[])(void) = {0,\n");
    for (uint32_t id = 1; id <= pool->count; ++id) fprintf(o, "game_banked_op_%u,\n", id);
    fprintf(o, "};\nstatic const uint8_t lengths[] = {0,\n");
    for (uint32_t id = 1; id <= pool->count; ++id) fprintf(o, "%u,", pool->ops[id].length);
    fprintf(o, "\n};\n");
    fprintf(o, "static const uint8_t fragments[] = {0,\n");
    for (uint32_t id = 1; id <= pool->count; ++id) fprintf(o, "%u,", pool->ops[id].illegal ? 1 : 0);
    fprintf(o, "\n};\n");
    BankedHash *guards = (BankedHash*)malloc(pool->count * sizeof(*guards));
    if (!guards) exit(1);
    size_t guard_n = 0;
    for (size_t i = 0; i < hash_size; ++i) if (pool->hash[i].id) guards[guard_n++] = pool->hash[i];
    qsort(guards, guard_n, sizeof(*guards), banked_key_order);
    fprintf(o, "static const uint64_t guard_keys[%zu] = {\n", guard_n);
    for (size_t i = 0; i < guard_n; ++i) fprintf(o, "UINT64_C(0x%llX),%s", (unsigned long long)guards[i].key, (i & 7) == 7 ? "\n" : "");
    fprintf(o, "\n};\nstatic const uint32_t guard_ids[%zu] = {\n", guard_n);
    for (size_t i = 0; i < guard_n; ++i) fprintf(o, "%u,%s", guards[i].id, (i & 15) == 15 ? "\n" : "");
    fprintf(o, "\n};\n"
        "/* Exact encodings, not an opcode decoder. Bytes may change between\n"
        " * instructions, so every visit checks them again through the bus. */\n"
        "int game_banked_guarded_step(void) {\n"
        "    uint64_t raw = 0; uint16_t pc = g_z80.pc;\n"
        "    for (unsigned length = 1; length <= 4; ++length) {\n"
        "        raw |= (uint64_t)sms_read8((uint16_t)(pc + length - 1)) << (8*(length-1));\n"
        "        uint64_t key = ((uint64_t)length << 32) | raw;\n"
        "        size_t lo = 0, hi = %zu;\n"
        "        while (lo < hi) { size_t mid = lo + (hi-lo)/2;\n"
        "            if (guard_keys[mid] < key) lo = mid+1; else hi = mid; }\n"
        "        if (lo < %zu && guard_keys[lo] == key) { uint32_t id = guard_ids[lo]; bodies[id](); return fragments[id] ? 4 : 2; }\n"
        "    }\n"
        "    return 0;\n}\n", guard_n, guard_n);
    free(guards);
    return guard_n;
}

static void banked_write_coverage(const char *dir, size_t positions, size_t covered, size_t period, const BankedOps *pool,
                                  size_t seam_n, size_t fixed_n, size_t guard_n, size_t profile_windows,
                                  size_t profile_unsupported, uint32_t rom_bodies) {
    char path[600];
    snprintf(path, sizeof path, "%s/banked-coverage.json", dir);
    FILE *o = fopen(path, "w"); if (!o) exit(1);
    fprintf(o, "{\n  \"backend\": \"banked-aot-v3\",\n  \"support_status\": \"supported\",\n"
        "  \"support_scope\": \"%s\",\n"
        "  \"native_redundant_prefixes\": true,\n  \"runtime_prefix_recursion\": false,\n"
        "  \"rom_positions\": %zu,\n"
        "  \"compiled_positions\": %zu,\n  \"unsupported_positions\": %zu,\n"
        "  \"bank_register_period\": %zu,\n  \"unique_native_bodies\": %u,\n"
        "  \"rom_seam_variants\": %zu,\n  \"fixed_seam_variants\": %zu,\n"
        "  \"ram_compiled\": true,\n  \"ram_strategy\": \"exact_byte_guards\",\n"
        "  \"guarded_native_encodings\": %zu,\n  \"profile_windows_loaded\": %zu,\n"
        "  \"profile_unsupported_windows\": %zu,\n  \"profile_added_native_bodies\": %u,\n"
        "  \"native_runtime_opcode_decoder\": false,\n  \"reference_fallback_available\": true\n}\n",
        banked_machine.scope, positions, covered, positions-covered, period, pool->count, seam_n, fixed_n,
        guard_n, profile_windows, profile_unsupported, pool->count-rom_bodies);
    fclose(o);
    printf("[banked] %zu/%zu ROM positions, %u native bodies, %zu bank seam variants\n", covered, positions, pool->count, seam_n+fixed_n);
}

/* A machine keyed by a region map (BankedMachine.mapped): every region of the address space shows a bank of one of several
 * sources, or RAM, and the map changes at run time. A position is keyed by (source, bank, offset). An instruction that
 * starts in the last three bytes of a region, and any instruction in RAM, runs through the byte guards: the guards hold
 * the encodings of every pair of banks that can meet at an edge, so the bytes of the next region are compared, not assumed.
 * Source 0 is the cartridge of game.toml; the others are the files named, one per line, in `banked.sources` beside it. */
typedef struct { uint8_t *data; size_t size, period; uint32_t *ids; } BankedSource;

static void banked_emit_mapped(const SmsRom *rom, const GameConfig *cfg, const char *dir) {
    const BankedMachine *machine = &banked_machine;
    const size_t slot_size = (size_t)1 << machine->slot_bits, slot_tail = slot_size - 3;
    BankedSource sources[16];
    char path[600], line[600];
    if (machine->sources < 1 || machine->sources > 16) { fprintf(stderr, "[banked] 1 to 16 sources\n"); exit(1); }
    sources[0].data = rom->data; sources[0].size = rom->size;
    snprintf(path, sizeof path, "%s/../banked.sources", dir);
    FILE *list = machine->sources > 1 ? fopen(path, "r") : NULL;
    for (unsigned s = 1; s < machine->sources; ++s) {
        if (!list || !fgets(line, sizeof line, list)) { fprintf(stderr, "[banked] banked.sources names fewer sources than the machine\n"); exit(1); }
        line[strcspn(line, "\r\n")] = 0;
        FILE *f = fopen(line, "rb");
        long size = 0;
        if (!f || fseek(f, 0, SEEK_END) || (size = ftell(f)) <= 0 || fseek(f, 0, SEEK_SET)) { fprintf(stderr, "[banked] unreadable source %u\n", s); exit(1); }
        sources[s].size = (size_t)size; sources[s].data = (uint8_t*)malloc(sources[s].size);
        if (!sources[s].data || fread(sources[s].data, 1, sources[s].size, f) != sources[s].size) exit(1);
        fclose(f);
    }
    if (list) fclose(list);
    size_t positions = 0, pairs = 0, periods = 0, covered = 0, seam_n = 0;
    for (unsigned s = 0; s < machine->sources; ++s) {
        sources[s].period = banked_period(sources[s].size, slot_size);
        positions += sources[s].size; periods += sources[s].period;
    }
    pairs = 3 * periods * periods;
    BankedOps pool;
    size_t hash_size = banked_pool_open(&pool, positions + pairs);
    for (unsigned s = 0; s < machine->sources; ++s) {
        BankedSource *source = &sources[s];
        source->ids = (uint32_t*)malloc(source->size * sizeof(*source->ids));
        if (!source->ids) exit(1);
        for (size_t a = 0; a < source->size; ++a) {
            uint8_t bytes[4];
            for (unsigned i = 0; i < 4; ++i) bytes[i] = source->data[(a+i) % source->size];
            source->ids[a] = banked_intern(&pool, bytes); if (source->ids[a]) ++covered;
        }
    }
    /* Every (source, bank) that can precede every (source, bank) at an edge: guarded encodings only, no table. */
    for (unsigned s = 0; s < machine->sources; ++s) for (size_t b = 0; b < sources[s].period; ++b)
        for (unsigned t = 0; t < machine->sources; ++t) for (size_t c = 0; c < sources[t].period; ++c)
            for (size_t a = 0; a < 3; ++a) {
                uint8_t bytes[4];
                for (unsigned i = 0; i < 4; ++i) {
                    size_t off = slot_tail + a + i;
                    bytes[i] = off < slot_size ? sources[s].data[(b*slot_size + off) % sources[s].size]
                                               : sources[t].data[(c*slot_size + off - slot_size) % sources[t].size];
                }
                banked_intern(&pool, bytes); ++seam_n;
            }
    size_t profile_windows, profile_unsupported;
    uint32_t rom_bodies = pool.count;
    banked_learn(&pool, dir, &profile_windows, &profile_unsupported);
    banked_write_bodies(&pool, cfg, dir);
    snprintf(path, sizeof path, "%s/game_banked_index.c", dir);
    FILE *o = fopen(path, "w"); if (!o) exit(1);
    fprintf(o, "/* Generated positions of every source; region edges and RAM run through the byte guards. */\n#include \"game_banked.h\"\n");
    for (unsigned s = 0; s < machine->sources; ++s) {
        char name[32];
        snprintf(name, sizeof name, "positions_%u", s);
        banked_array(o, name, sources[s].ids, sources[s].size);
    }
    size_t guard_n = banked_write_tables(o, &pool, hash_size);
    banked_step_signature(o);
    fprintf(o, " {\n    uint16_t pc = g_z80.pc; const BankedRegion *region = &map[pc >> %u];\n"
        "    uint32_t off = pc & 0x%zX, id;\n"
        "    if (region->ram || off >= 0x%zX) return game_banked_guarded_step();\n"
        "    switch (region->source) {\n", machine->slot_bits, slot_size - 1, slot_tail);
    for (unsigned s = 0; s < machine->sources; ++s)
        fprintf(o, "    case %u: id = positions_%u[((uint32_t)region->bank*0x%zX+off) %% %zu]; break;\n", s, s, slot_size, sources[s].size);
    fprintf(o, "    default: return game_banked_guarded_step();\n    }\n"
        "    if (!id) return game_banked_guarded_step();\n"
        "    bodies[id](); return fragments[id] ? 3 : 1;\n}\n");
    fclose(o);
    banked_write_coverage(dir, positions, covered, periods, &pool, seam_n, 0, guard_n, profile_windows, profile_unsupported, rom_bodies);
    free(pool.hash); free(pool.ops);
    for (unsigned s = 0; s < machine->sources; ++s) { free(sources[s].ids); if (s) free(sources[s].data); }
}

void cg_emit_banked_step(const SmsRom *rom, const GameConfig *cfg, const char *dir) {
    CG_MKDIR(dir);
    const BankedMachine *machine = &banked_machine;
    if (machine->mapped) { banked_emit_mapped(rom, cfg, dir); return; }
    /* The last three bytes of a slot (and of the fixed start) begin instructions that end in the next region. */
    const size_t slot_size = (size_t)1 << machine->slot_bits, slot_tail = slot_size - 3;
    const size_t fixed = machine->fixed_bytes, fixed_tail = fixed ? fixed - 3 : 0;
    size_t period = banked_period(rom->size, slot_size);
    size_t seam_n = 3 * period * period, fixed_n = fixed ? 3 * period : 0;
    BankedOps pool;
    size_t hash_size = banked_pool_open(&pool, rom->size + seam_n + fixed_n);
    uint32_t *ids = (uint32_t*)malloc(rom->size * sizeof(*ids));
    uint32_t *seams = (uint32_t*)malloc(seam_n * sizeof(*seams));
    uint32_t *fixed_ids = (uint32_t*)malloc((fixed_n ? fixed_n : 1) * sizeof(*fixed_ids));
    if (!ids || !seams || !fixed_ids) exit(1);
    size_t covered = 0;
    for (size_t a = 0; a < rom->size; ++a) {
        uint8_t bytes[4];
        for (unsigned i = 0; i < 4; ++i) bytes[i] = rom->data[(a+i) % rom->size];
        ids[a] = banked_intern(&pool, bytes); if (ids[a]) ++covered;
    }
    for (size_t a = 0; a < 3; ++a) {
        for (size_t b = 0; b < period; ++b) {
            uint8_t bytes[4];
            for (unsigned i = 0; fixed && i < 4; ++i) {
                size_t pc = fixed_tail + a + i;
                bytes[i] = rom->data[(pc < fixed ? pc : b*slot_size + pc) % rom->size];
            }
            if (fixed) fixed_ids[a*period+b] = banked_intern(&pool, bytes);
            for (size_t c = 0; c < period; ++c) {
                for (unsigned i = 0; i < 4; ++i) {
                    size_t off = slot_tail + a + i;
                    size_t phys = off < slot_size ? b*slot_size + off : c*slot_size + off - slot_size;
                    bytes[i] = rom->data[phys % rom->size];
                }
                seams[(a*period+b)*period+c] = banked_intern(&pool, bytes);
            }
        }
    }
    size_t profile_windows, profile_unsupported;
    uint32_t rom_bodies = pool.count;
    banked_learn(&pool, dir, &profile_windows, &profile_unsupported);
    banked_write_bodies(&pool, cfg, dir);
    char path[600];
    snprintf(path, sizeof path, "%s/game_banked_index.c", dir);
    FILE *o = fopen(path, "w"); if (!o) exit(1);
    fprintf(o, "/* Generated ROM positions and mapper seam variants. */\n#include \"game_banked.h\"\n");
    banked_array(o, "positions", ids, rom->size);
    banked_array(o, "seams", seams, seam_n);
    if (fixed) banked_array(o, "fixed_seams", fixed_ids, fixed_n);
    size_t guard_n = banked_write_tables(o, &pool, hash_size);
    /* The step: RAM goes to the guards; an instruction that starts in the last bytes of the fixed start or of a slot is a
     * seam variant keyed by the two banks it reads; any other position is keyed by the bank of its slot. */
    const unsigned last = machine->slots - 1;
    banked_step_signature(o);
    fprintf(o, " {\n    uint16_t pc = g_z80.pc; if (pc >= 0x%X) return game_banked_guarded_step();\n", machine->ram_from);
    fprintf(o, "    uint32_t b[%u] = { ", machine->slots);
    for (unsigned slot = 0; slot <= last; ++slot) fprintf(o, "%sb%u %% %zu", slot ? ", " : "", slot, period);
    fprintf(o, " };\n    uint32_t slot = pc >> %u, off = pc & 0x%zX, id;\n    if (", machine->slot_bits, slot_size - 1);
    if (fixed) fprintf(o, "pc >= 0x%zX && pc < 0x%zX) id = fixed_seams[(pc-0x%zX)*%zu+b[0]];\n    else if (",
        fixed_tail, fixed, fixed_tail, period);
    fprintf(o, "off >= 0x%zX && slot < %u) id = seams[((off-0x%zX)*%zu+b[slot])*%zu+b[slot+1]];\n",
        slot_tail, last, slot_tail, period, period);
    if (fixed) fprintf(o, "    else id = positions[((pc < 0x%zX ? 0 : b[slot]*0x%zX)+off) %% %zu];\n", fixed, slot_size, rom->size);
    else fprintf(o, "    else id = positions[(b[slot]*0x%zX+off) %% %zu];\n", slot_size, rom->size);
    fprintf(o, "    if (!id || (slot == %u && off + lengths[id] + fragments[id] > 0x%zX)) return game_banked_guarded_step();\n"
        "    bodies[id](); return fragments[id] ? 3 : 1;\n}\n", last, slot_size);
    fclose(o);
    banked_write_coverage(dir, rom->size, covered, period, &pool, seam_n, fixed_n, guard_n, profile_windows, profile_unsupported, rom_bodies);
    free(pool.hash); free(pool.ops); free(ids); free(seams); free(fixed_ids);
}
