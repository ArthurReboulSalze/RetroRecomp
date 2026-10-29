/* Authored MMC1 register and PPU A12 activity; prints a digest of the bank tables after every step so that
 * the machine with the A12 rebuild skipped can be compared with the original. No commercial game data. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cyc_core.h"
#include "cyc_run.h"
#include "cpu6502.h"
#include "hw_internal.h"
#include "hw_mapper.h"
#include "retro_nes.h"

bool cyc_native_has(uint16_t pc) { (void)pc; return false; }
void cyc_native_run(void) { abort(); }
static uint32_t seed;
static uint32_t next_value(void) { seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5; return seed; }
static uint64_t fold(uint64_t h, const void *data, size_t size) {
    const unsigned char *p = data;
    while (size--) h = (h ^ *p++) * 1099511628211ULL;
    return h;
}
/* Everything the mapper derives from its registers and A12: the PRG and CHR windows, mirroring, the work RAM
 * bank and its enables, and the pin itself. */
static uint64_t tables(void) {
    uint64_t h = 14695981039346656037ULL;
    h = fold(h, hw_cart.prg_off, sizeof hw_cart.prg_off);
    h = fold(h, hw_cart.chr_off, sizeof hw_cart.chr_off);
    h = fold(h, &hw_cart.mirroring, 1);
    h = fold(h, &hw_cart.wram_bank, sizeof hw_cart.wram_bank);
    h = fold(h, &hw_cart.wram_readable, 1);
    h = fold(h, &hw_cart.wram_writable, 1);
    h = fold(h, &hw_cart.m.a12, 1);
    return h;
}
static void serial_write(uint16_t address, uint8_t value) {
    /* The chip ignores a write one cycle after the last; two idle cycles keep every write. */
    (void)cpu_read(0, 0); (void)cpu_read(0, 0);
    cpu_write(address, value, 0);
}
static void load_register(uint16_t address, uint8_t value) {
    for (unsigned bit = 0; bit < 5; bit++) serial_write(address, (uint8_t)((value >> bit) & 1));
}

/* argv: mapper submapper prg_units chr_units(0 = CHR RAM) ram_shift (NES 2.0 PRG RAM size byte) */
int main(int argc, char **argv) {
    unsigned mapper = argc > 1 ? (unsigned)atoi(argv[1]) : 1, submapper = argc > 2 ? (unsigned)atoi(argv[2]) : 0;
    unsigned prg_units = argc > 3 ? (unsigned)atoi(argv[3]) : 8, chr_units = argc > 4 ? (unsigned)atoi(argv[4]) : 0;
    unsigned ram = argc > 5 ? (unsigned)atoi(argv[5]) : 0;
    size_t prg = (size_t)prg_units * 16384, chr = (size_t)chr_units * 8192, size = 16 + prg + chr;
    uint8_t *rom = calloc(1, size);
    if (!rom) return 2;
    memcpy(rom, "NES\032", 4);
    rom[4] = (uint8_t)(prg_units & 255); rom[5] = (uint8_t)(chr_units & 255);
    rom[6] = (uint8_t)((mapper & 15) << 4); rom[7] = (uint8_t)((mapper & 0xF0) | 8);
    rom[8] = (uint8_t)(((mapper >> 8) & 15) | (submapper << 4));
    rom[9] = (uint8_t)(((prg_units >> 8) & 15) | (((chr_units >> 8) & 15) << 4));
    rom[10] = (uint8_t)ram;
    if (!chr_units) rom[11] = 7;   /* 8 KiB of CHR RAM */
    memset(rom + 16, 0xea, prg);
    for (size_t pos = 16; pos < 16 + prg; pos += 4096) {
        rom[pos + 4090] = rom[pos + 4092] = rom[pos + 4094] = 0;
        rom[pos + 4091] = rom[pos + 4093] = rom[pos + 4095] = 0x80;
    }
    if (!cyc_load_ines(rom, size)) return 3;
    free(rom);
    cyc_run_native = false;
    printf("mapper %u submapper %u prg_slots %u chr_pages %u wram_len %u\n", mapper, submapper,
           (unsigned)hw_cart.prg_slots, (unsigned)hw_cart.chr_pages, (unsigned)hw_cart.wram_len);
    for (unsigned run = 0; run < 4; run++) {
        cyc_power_on((uint8_t)run); cyc_run_power_on();
        seed = 0x9e3779b9u * (run + 1);
        for (unsigned step = 0; step < 6000; step++) {
            uint32_t value = next_value();
            switch (value & 7) {
            case 0: load_register(0x8000, (uint8_t)(value >> 8)); break;   /* control */
            case 1: load_register(0xA000, (uint8_t)(value >> 8)); break;   /* CHR 0 */
            case 2: load_register(0xC000, (uint8_t)(value >> 8)); break;   /* CHR 1 */
            case 3: load_register(0xE000, (uint8_t)(value >> 8)); break;   /* PRG */
            case 4: serial_write(0x8000 + (value >> 16 & 0x7FFF), (uint8_t)(value >> 8) | 0x80); break; /* reset */
            default: /* A12 moves, with the same value often (a repeated address is not a change) */
                hw_cart_ppu_addr_watched((uint16_t)((value >> 8 & 0x1FFF) ^ ((value >> 4 & 1) << 12)));
                break;
            }
            if (!(value & 7) || value % 5 == 0) hw_cart_ppu_addr_watched((uint16_t)(0x1000 * (value >> 3 & 1)));
            uint64_t h = tables();
            if (step % 50 == 0 || (value & 7) < 5) printf("%u %u %016llx\n", run, step, (unsigned long long)h);
        }
    }
    return 0;
}
