/* The Wisdom Tree mapper of the Game Boy runtime, on a cartridge authored for the check (gb_wisdom_selftest.py writes it): eight
 * 32 KiB banks, each with its own marker at 0x3000 (lower window) and 0x7000 (upper window). No original cartridge bytes. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbrt.h"

static unsigned checks;

static uint8_t* read_file(const char* path, size_t* size) {
    FILE* file = fopen(path, "rb");
    assert(file);
    fseek(file, 0, SEEK_END);
    *size = (size_t)ftell(file);
    fseek(file, 0, SEEK_SET);
    uint8_t* data = (uint8_t*)malloc(*size);
    assert(data && fread(data, 1, *size, file) == *size);
    fclose(file);
    return data;
}

static GBContext* make(const uint8_t* rom, size_t size) {
    GBContext* ctx = gb_context_create(NULL);
    assert(ctx && gb_context_load_rom(ctx, rom, size));
    gb_context_reset(ctx, true);
    return ctx;
}

static void expect_bank(GBContext* ctx, unsigned bank32) {
    assert(gb_resolve_rom_bank(ctx, 0x0000) == 2u * bank32);
    assert(gb_resolve_rom_bank(ctx, 0x3FFF) == 2u * bank32);
    assert(gb_resolve_rom_bank(ctx, 0x4000) == 2u * bank32 + 1u);
    assert(gb_resolve_rom_bank(ctx, 0x7FFF) == 2u * bank32 + 1u);
    assert(gb_read8(ctx, 0x3000) == 0xA0u + bank32);
    assert(gb_read8(ctx, 0x7000) == 0xB0u + bank32);
    checks += 6;
}

int main(int argc, char** argv) {
    assert(argc >= 3);
    size_t size;
    uint8_t* rom = read_file(argv[1], &size);
    assert(size == 8u * 0x8000u);

    /* Detected, and bank 0 at power-on. */
    GBContext* ctx = make(rom, size);
    assert(ctx->rr_wisdom_tree == 1);
    expect_bank(ctx, 0);

    /* The address selects the bank, the value is ignored, and a write to either half of 0000-7FFF counts. */
    for (unsigned bank = 0; bank < 8; ++bank) {
        gb_write8(ctx, (uint16_t)bank, 0x55);
        expect_bank(ctx, bank);
        gb_write8(ctx, (uint16_t)bank, 0x00);
        expect_bank(ctx, bank);
        gb_write8(ctx, (uint16_t)(0x4000u + bank), 0xFF);
        expect_bank(ctx, bank);
    }
    gb_write8(ctx, 0x1203, 0x00);   /* the high address lines do not matter: bank 3 */
    expect_bank(ctx, 3);
    gb_write8(ctx, 0x000B, 0x00);   /* 11 on an eight-bank ROM wraps to 3 */
    expect_bank(ctx, 3);
    gb_write8(ctx, 0x7FFF, 0x00);   /* low byte FF wraps to 7 */
    expect_bank(ctx, 7);
    checks += 4;

    /* Writes above the ROM (VRAM, WRAM) are not mapper writes. */
    gb_write8(ctx, 0xC002, 0x00);
    expect_bank(ctx, 7);

    /* A saved state brings the bank back; a reset returns to bank 0. */
    gb_write8(ctx, 0x0005, 0x00);
    assert(gb_context_save_state_file(ctx, argv[2]));
    gb_write8(ctx, 0x0001, 0x00);
    expect_bank(ctx, 1);
    assert(gb_context_load_state_file(ctx, argv[2]));
    expect_bank(ctx, 5);
    gb_context_reset(ctx, true);
    expect_bank(ctx, 0);
    checks += 4;
    gb_context_destroy(ctx);

    /* What is not a Wisdom Tree cartridge keeps the old behaviour: header type 00 is a fixed second bank. */
    uint8_t* other = (uint8_t*)malloc(size);
    assert(other);
    memcpy(other, rom, size);
    for (size_t i = 0; i + 6 <= size; ++i)
        if (memcmp(other + i, "WISDOM", 6) == 0) other[i] = 'X';
    ctx = make(other, size);
    assert(ctx->rr_wisdom_tree == 0);                       /* the words are missing */
    gb_write8(ctx, 0x0003, 0x00);
    assert(gb_resolve_rom_bank(ctx, 0x0000) == 0 && gb_resolve_rom_bank(ctx, 0x4000) == 1);
    gb_context_destroy(ctx);

    memcpy(other, rom, size);
    ctx = make(other, 0x8000);
    assert(ctx->rr_wisdom_tree == 0);                       /* 32 KiB only: no bank to switch */
    gb_context_destroy(ctx);

    ctx = make(other, size - 0x4000);
    assert(ctx->rr_wisdom_tree == 0);                       /* not whole 32 KiB banks */
    gb_context_destroy(ctx);

    other[0x147] = 0x01;                                    /* a real mapper in the header */
    ctx = make(other, size);
    assert(ctx->rr_wisdom_tree == 0);
    gb_context_destroy(ctx);
    checks += 5;

    printf("{\"checks\":%u,\"wisdom_tree_mapper\":true}\n", checks);
    free(other);
    free(rom);
    return 0;
}
