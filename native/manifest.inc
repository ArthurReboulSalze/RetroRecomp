/* Included inside the runtime, where the bank registers and bus are visible. */
#include "learning.h"
typedef struct { uint16_t addr; uint8_t b0,b1,b2; uint32_t crc; } ManifestSig;
#define MANIFEST_MAX 16384
static ManifestSig g_manifest[MANIFEST_MAX];
static int g_manifest_n;

static int manifest_has(uint16_t addr, uint8_t b0, uint8_t b1, uint8_t b2, uint32_t crc) {
    for (int i = 0; i < g_manifest_n; ++i) {
        ManifestSig *m = &g_manifest[i];
        if (m->addr == addr && m->b0 == b0 && m->b1 == b1 && m->b2 == b2 && m->crc == crc) return 1;
    }
    return 0;
}

static void manifest_load(void) {
    g_manifest_n = 0;
    FILE *file = smsrecomp_observations_read();
    if (!file) return;
    char line[160], extra;
    unsigned a, b0, b1, b2, crc;
    while (fgets(line, sizeof(line), file)) {
        if (sscanf(line, "%x %x %x %x %x %c", &a, &b0, &b1, &b2, &crc, &extra) != 5 ||
            a > 0xFFFF || b0 > 0xFF || b1 > 0xFF || b2 > 0xFF || g_manifest_n >= MANIFEST_MAX) continue;
        if (!manifest_has((uint16_t)a, (uint8_t)b0, (uint8_t)b1, (uint8_t)b2, crc)) {
            ManifestSig *m = &g_manifest[g_manifest_n++];
            m->addr = (uint16_t)a; m->b0 = (uint8_t)b0; m->b1 = (uint8_t)b1; m->b2 = (uint8_t)b2; m->crc = crc;
        }
    }
    fclose(file);
}

static void manifest_record(uint16_t addr) {
    if (!smsrecomp_learning_enabled()) return;
    uint8_t b0 = (uint8_t)g_bank[0], b1 = (uint8_t)g_bank[1], b2 = (uint8_t)g_bank[2];
    uint32_t crc = mb_code_crc(addr);
    if (manifest_has(addr, b0, b1, b2, crc) || g_manifest_n >= MANIFEST_MAX) return;
    ManifestSig *m = &g_manifest[g_manifest_n++];
    m->addr = addr; m->b0 = b0; m->b1 = b1; m->b2 = b2; m->crc = crc;
    smsrecomp_observe(addr, b0, b1, b2, crc);
}
