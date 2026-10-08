/* Guarded PC-directed SPC700 operations; no runtime opcode decoder here.
 * Converter probes retain observations in memory. Normal play records only
 * native/fallback counters and never writes learning files. */
#include "snes_spc_native.h"
#include "snes/spc.h"
#include <string.h>

#define VARIANT_LIMIT 65536u
static bool enabled, probing;
static uint64_t native_ops, fallback_ops, native_cycles, fallback_cycles, idle_cycles, dropped;
static struct { uint16_t pc; uint8_t opcode; } variants[VARIANT_LIMIT];
static uint32_t seen[VARIANT_LIMIT * 2];
static unsigned variant_count, image_count;
static uint8_t images[4][65536];
static uint32_t last_image_cycle;

static void observe(Spc *spc) {
    if (!probing || (spc->pc >= 0xf0 && spc->pc <= 0xff) ||
        (spc->apu->romReadable && spc->pc >= 0xffc0)) return;
    uint8_t opcode = spc->apu->ram[spc->pc];
    uint32_t key = (((uint32_t)spc->pc << 8) | opcode) + 1;
    unsigned slot = (key * 2654435761u) & (VARIANT_LIMIT * 2 - 1);
    while (seen[slot]) {
        if (seen[slot] == key) return;
        slot = (slot + 1) & (VARIANT_LIMIT * 2 - 1);
    }
    if (variant_count == VARIANT_LIMIT) { ++dropped; return; }
    seen[slot] = key;
    variants[variant_count].pc = spc->pc;
    variants[variant_count++].opcode = opcode;
    /* Compile unvisited positions in uploaded sound drivers too. Sparse
     * exact misses preserve later replacements even after the image cap. */
    if (image_count == 4 || (image_count &&
        (uint32_t)(spc->apu->cycles - last_image_cycle) < 65536u)) return;
    for (unsigned i = 0; i < image_count; ++i)
        if (!memcmp(images[i], spc->apu->ram, sizeof images[i])) return;
    memcpy(images[image_count++], spc->apu->ram, sizeof images[0]);
    last_image_cycle = spc->apu->cycles;
}

int spc_runOpcode(Spc *spc) {
    spc->cyclesUsed = 0;
    if (spc->stopped) { ++idle_cycles; return 1; } /* no retired instruction */
    const RrSpcNativeOp *op = rr_spc_native_lookup(spc);
    if (op) {
        op->execute(spc);
        ++native_ops; native_cycles += spc->cyclesUsed;
    } else {
        if (enabled) observe(spc);
        rr_spc_reference_step(spc);
        ++fallback_ops; fallback_cycles += spc->cyclesUsed;
    }
    return spc->cyclesUsed;
}
bool rr_spc_native_enabled(void) { return enabled; }
void rr_spc_set_mode(bool native, bool probe) { enabled = native; probing = probe; }
void rr_spc_reset_evidence(void) {
    native_ops = fallback_ops = native_cycles = fallback_cycles = idle_cycles = dropped = 0;
    variant_count = image_count = last_image_cycle = 0;
    memset(seen, 0, sizeof seen);
}
uint64_t rr_spc_native_opcodes(void) { return native_ops; }
uint64_t rr_spc_interpreted_opcodes(void) { return fallback_ops; }
void rr_spc_report(FILE *file) {
    fprintf(file, ",\"audio_native_opcodes\":%llu,\"audio_interpreted_opcodes\":%llu,"
        "\"audio_native_cycles\":%llu,\"audio_interpreted_cycles\":%llu,"
        "\"spc_idle_cycles\":%llu,\"spc_dropped_variants\":%llu,\"spc_variants\":[",
        native_ops, fallback_ops, native_cycles, fallback_cycles, idle_cycles, dropped);
    for (unsigned i = 0; i < variant_count; ++i)
        fprintf(file, "%s{\"address\":%u,\"opcode\":%u}", i ? "," : "", variants[i].pc, variants[i].opcode);
    fputs("],\"spc_driver_images\":[", file);
    for (unsigned i = 0; i < image_count; ++i) {
        fprintf(file, "%s\"", i ? "," : "");
        for (unsigned n = 0; n < sizeof images[i]; ++n) fprintf(file, "%02x", images[i][n]);
        fputc('"', file);
    }
    fputc(']', file);
}
