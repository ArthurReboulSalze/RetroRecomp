/* Authored bank-window fixtures; no cartridge code or assets. */
#undef NDEBUG
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include "gbrt.h"
#include "gb_boundary_generated.inc"

static void (*native_step)(GBContext*);
void gb_dispatch(GBContext* ctx, uint16_t addr) {
    ctx->pc = addr;
    native_step(ctx);
}

static GBContext* setup(unsigned opcode, unsigned addr, unsigned bank,
                        unsigned value, unsigned flags, unsigned phase) {
    GBContext* ctx = gb_context_create(NULL); assert(ctx);
    ctx->rom_size = 4u * 0x4000u;
    ctx->rom = (uint8_t*)calloc(ctx->rom_size, 1); assert(ctx->rom);
    ctx->mbc_type = 1; ctx->rom_bank = bank; ctx->rom_bank_low = bank;
    ctx->pc = (uint16_t)addr; ctx->sp = 0xC700;
    ctx->a = 0x56; ctx->bc = 0x1234; ctx->de = 0x9876; ctx->hl = 0xC200;
    ctx->ime = ctx->ime_pending = ctx->halted = ctx->stopped = 0;
    ctx->f_z = (flags >> 3) & 1; ctx->f_n = (flags >> 2) & 1;
    ctx->f_h = (flags >> 1) & 1; ctx->f_c = flags & 1;
    for (unsigned i = 0; i < 3; ++i) {
        unsigned a = addr + i;
        uint8_t byte = (uint8_t)(i == 0 ? opcode : i == 1 ? value : 0xC2);
        if (a < 0x8000) ctx->rom[(a < 0x4000 ? 0 : bank * 0x4000) + (a & 0x3FFF)] = byte;
        else ctx->vram[a - 0x8000] = byte;
    }
    gb_write8(ctx, 0xC200 | value, 0xA9);
    gb_tick(ctx, phase);
    return ctx;
}

int main(void) {
    unsigned checks = 0;
    const unsigned phases[] = {0, 3, 77, 251};
    const unsigned values[] = {0, 0x42, 0x80, 0xFF};
    for (unsigned f = 0; f < sizeof(fixtures) / sizeof(*fixtures); ++f)
    for (unsigned bank = 1; bank <= 2; ++bank)
    for (unsigned v = 0; v < 4; ++v)
    for (unsigned flags = 0; flags < 16; flags += 1)
    for (unsigned p = 0; p < 4; ++p) {
        const Fixture* fixture = &fixtures[f];
        native_step = fixture->step;
        GBContext* a = setup(fixture->opcode, fixture->address, bank, values[v], flags, phases[p]);
        GBContext* b = setup(fixture->opcode, fixture->address, bank, values[v], flags, phases[p]);
        GBDifferentialOptions options = {0};
        options.max_steps = 1; options.compare_memory = true; options.fail_on_fallback = true;
        GBDifferentialResult result;
        if (!gb_run_differential(a, b, &options, &result)) {
            fprintf(stderr, "Boundary fixture failed: opcode=%02X addr=%04X bank=%u value=%02X phase=%u\n",
                    fixture->opcode, fixture->address, bank, values[v], phases[p]);
            return 1;
        }
        assert(result.steps_completed == 1 && a->total_interpreter_cycles == 0);
        gb_context_destroy(a); gb_context_destroy(b); ++checks;
    }
    GBContext* entry = gb_context_create(NULL); assert(entry);
    for (unsigned pc = 0; pc < 65536u; ++pc) {
        entry->pc = (uint16_t)pc; entry->de = 65535;
        body_authored_entries(entry);
        unsigned expected = 1;
        if (pc >= 3 && (pc - 3) % 29 == 0 && (pc - 3) / 29 < 1024)
            expected = (pc - 3) / 29 + 1;
        assert(entry->de == expected && entry->pc == pc);
    }
    gb_context_destroy(entry);
    printf("{\"bank_boundary_comparisons\":%u,\"entry_selector_checks\":65536,\"fallback_cycles\":0}\n", checks);
    return 0;
}
