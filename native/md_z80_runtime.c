/* PC-directed Z80 sound AOT. Generated operations have no runtime decoder.
 * Opcode guards permit live RAM operands without executing stale operations.
 * Evidence stays in memory; only explicit conversion probes serialize it. */
#include "md_z80_native.h"
#include <string.h>

static uint64_t native_ops, fallback_ops, native_cycles, fallback_cycles;
typedef struct { uint16_t pc; uint8_t mask, bytes[4]; } Observation;
static Observation variants[RR_MD_Z80_VARIANT_LIMIT];
static uint16_t table[RR_MD_Z80_VARIANT_LIMIT * 2];
static unsigned variant_count;
static uint64_t dropped_variants;
static int in_reference;
static unsigned driver_image_count;
static uint8_t driver_images[4][8192];

void rr_md_z80_capture_driver(void) {
    if (!rr_md_z80_probe() || driver_image_count == 4) return;
    uint8_t image[8192];
    for (unsigned i = 0; i < sizeof image; ++i)
        if (!rr_md_z80_peek((uint16_t)i, &image[i])) return;
    for (unsigned i = 0; i < driver_image_count; ++i)
        if (!memcmp(image, driver_images[i], sizeof image)) return;
    memcpy(driver_images[driver_image_count++], image, sizeof image);
}

static void observe(uint16_t pc) {
    if (pc < 0x4000u) pc &= 0x1fffu;
    uint8_t bytes[4], mask = 0;
    unsigned pos = 0;
    for (unsigned i = 0; i < 4; ++i)
        if (!rr_md_z80_peek((uint16_t)(pc + i), &bytes[i])) return;
    /* Structural decoding is used only to record an interpreter miss. Native
     * execution uses the converter-generated PC table and literal guards. */
    while (pos < 4) {
        unsigned op = bytes[pos]; mask |= 1u << pos++;
        if (op == 0xcb || op == 0xed) {
            if (pos >= 4) return;
            mask |= 1u << pos; break;
        }
        if (op == 0xdd || op == 0xfd) {
            if (pos >= 4) return;
            if (bytes[pos] == 0xcb) {
                if (pos + 2 >= 4) return;
                mask |= (1u << pos) | (1u << (pos + 2)); break;
            }
            continue;
        }
        break;
    }
    if (pos >= 4 && (bytes[3] == 0xdd || bytes[3] == 0xfd)) return;
    uint32_t hash = pc ^ ((uint32_t)mask << 16);
    for (unsigned i = 0; i < 4; ++i) {
        if (!(mask & (1u << i))) bytes[i] = 0;
        hash = (hash ^ bytes[i]) * 16777619u;
    }
    unsigned slot = hash & (RR_MD_Z80_VARIANT_LIMIT * 2 - 1);
    while (table[slot]) {
        Observation *old = &variants[table[slot] - 1];
        if (old->pc == pc && old->mask == mask && !memcmp(old->bytes, bytes, 4)) return;
        slot = (slot + 1) & (RR_MD_Z80_VARIANT_LIMIT * 2 - 1);
    }
    if (variant_count == RR_MD_Z80_VARIANT_LIMIT) { ++dropped_variants; return; }
    Observation *item = &variants[variant_count];
    item->pc = pc; item->mask = mask; memcpy(item->bytes, bytes, 4);
    table[slot] = (uint16_t)++variant_count;
}

void rr_md_z80_step(z80 *z) {
    unsigned long before = z->cyc;
    in_reference = rr_md_z80_force_reference();
    if (!in_reference) {
        if (z->halted) {
            rr_md_z80_halt(z); rr_md_z80_finish(z);
            ++native_ops; native_cycles += z->cyc - before; return;
        }
        unsigned count = 0;
        const RrMdZ80Body *ops = rr_md_z80_bodies(z->pc, &count);
        for (unsigned i = 0; i < count; ++i) {
            int matched = 1;
            for (unsigned b = 0; b < 4; ++b) if (ops[i].mask & (1u << b)) {
                uint8_t value;
                if (!rr_md_z80_peek((uint16_t)(z->pc + b), &value) || value != ops[i].bytes[b]) {
                    matched = 0; break;
                }
            }
            if (matched) {
                uint64_t previous_fallback = fallback_cycles;
                ops[i].run(z); rr_md_z80_finish(z);
                ++native_ops;
                native_cycles += z->cyc - before - (fallback_cycles - previous_fallback);
                return;
            }
        }
        observe(z->pc);
    }
    in_reference = 1; /* z80_step already accounts for an IM0 decode here. */
    z80_step(z);
    ++fallback_ops; fallback_cycles += z->cyc - before;
}

void rr_md_z80_irq_fallback(unsigned long cycles) {
    if (!in_reference) { ++fallback_ops; fallback_cycles += cycles; }
}
void rr_md_z80_reset_evidence(void) {
    native_ops = fallback_ops = native_cycles = fallback_cycles = dropped_variants = 0;
    variant_count = driver_image_count = 0; memset(table, 0, sizeof table);
}
uint64_t rr_md_z80_native_opcodes(void) { return native_ops; }
uint64_t rr_md_z80_fallback_opcodes(void) { return fallback_ops; }
uint64_t rr_md_z80_native_cycles(void) { return native_cycles; }
uint64_t rr_md_z80_fallback_cycles(void) { return fallback_cycles; }
void rr_md_z80_report(FILE *file) {
    fprintf(file, ",\"audio_native_opcodes\":%llu,\"audio_interpreted_opcodes\":%llu,"
                  "\"audio_native_cycles\":%llu,\"audio_interpreted_cycles\":%llu,"
                  "\"z80_dropped_variants\":%llu,\"z80_variants\":[",
            native_ops, fallback_ops, native_cycles, fallback_cycles, dropped_variants);
    for (unsigned i = 0; i < variant_count; ++i) {
        Observation *v = &variants[i];
        fprintf(file, "%s{\"address\":%u,\"bytes\":\"%02x%02x%02x%02x\"}",
                i ? "," : "", v->pc, v->bytes[0], v->bytes[1], v->bytes[2], v->bytes[3]);
    }
    fprintf(file, "],\"z80_driver_images\":[");
    for (unsigned i = 0; i < driver_image_count; ++i) {
        fprintf(file, "%s\"", i ? "," : "");
        for (unsigned b = 0; b < sizeof driver_images[i]; ++b) fprintf(file, "%02x", driver_images[i][b]);
        fprintf(file, "\"");
    }
    fprintf(file, "]");
}
