/* Authored RAM routines, run on the interpreter with the entry trace on: the entries the end-of-run sweep adds to
 * the ones executed. No commercial game data. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cyc_core.h"
#include "cyc_run.h"
#include "cpu6502.h"
#include "hw_internal.h"
#include "retro_nes.h"

bool cyc_native_has(uint16_t pc) { (void)pc; return false; }
void cyc_native_run(void) { abort(); }
static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); exit(1); } } while (0)

typedef struct { unsigned pc; unsigned op; } Entry;
typedef void (*Poke)(unsigned address, uint8_t value);

/* One routine at `base`. Executed: LDA #0, BEQ (taken), JSR, INX, BNE (taken), RTS, JMP, NOP.
 *   +00 A9 00        LDA #$00
 *   +02 F0 05        BEQ +09        taken: skips the three instructions below
 *   +04 A2 01        LDX #$01       never executed, reached by falling through
 *   +06 86 10        STX $10        never executed
 *   +08 EA           NOP            never executed, falls into the JSR
 *   +09 20 lo hi     JSR +20
 *   +0C 4C lo hi     JMP +40
 *   +0F A9 11        data after an unconditional jump: no path leads here
 *   +20 E8           INX
 *   +21 D0 02        BNE +25        taken
 *   +23 D0 2B        BNE +50        never executed: its target holds an illegal opcode
 *   +25 60           RTS
 *   +26 EA           data after a return
 *   +40 EA           NOP            executed, then the run stops
 *   +41 4C 00 90     JMP $9000      never executed: outside the windows the sweep follows
 *   +50 02           KIL            illegal: the path ends */
static void place(unsigned base, Poke poke) {
    static const uint8_t body[][5] = {   /* offset, length, bytes */
        {0x00, 2, 0xA9, 0x00}, {0x02, 2, 0xF0, 0x05}, {0x04, 2, 0xA2, 0x01}, {0x06, 2, 0x86, 0x10}, {0x08, 1, 0xEA},
        {0x0F, 2, 0xA9, 0x11}, {0x20, 1, 0xE8}, {0x21, 2, 0xD0, 0x02}, {0x23, 2, 0xD0, 0x2B}, {0x25, 1, 0x60},
        {0x26, 1, 0xEA}, {0x40, 1, 0xEA}, {0x41, 3, 0x4C, 0x00, 0x90}, {0x50, 1, 0x02}};
    for (unsigned i = 0; i < sizeof body / sizeof body[0]; i++)
        for (unsigned k = 0; k < body[i][1]; k++) poke(base + body[i][0] + k, body[i][2 + k]);
    poke(base + 0x09, 0x20); poke(base + 0x0A, (uint8_t)((base + 0x20) & 255)); poke(base + 0x0B, (uint8_t)((base + 0x20) >> 8));
    poke(base + 0x0C, 0x4C); poke(base + 0x0D, (uint8_t)((base + 0x40) & 255)); poke(base + 0x0E, (uint8_t)((base + 0x40) >> 8));
}
static void poke_ram(unsigned address, uint8_t value) { hw.ram[address & 0x7FF] = value; }
static void poke_cart(unsigned address, uint8_t value) { hw_cart.wram[address - 0x6000] = value; }

static unsigned read_trace(Entry *entries, unsigned limit) {
    FILE *file = tmpfile();
    CHECK(file);
    rr_nes_ram_trace_write(file);
    rewind(file);
    char line[64]; unsigned count = 0, pc, op;
    while (fgets(line, sizeof line, file)) {
        CHECK(sscanf(line, "# ram:%x:%x", &pc, &op) == 2);
        CHECK(count < limit);
        entries[count].pc = pc; entries[count].op = op; count++;
    }
    fclose(file);
    return count;
}
static bool has(const Entry *entries, unsigned count, unsigned pc, unsigned op) {
    for (unsigned i = 0; i < count; i++) if (entries[i].pc == pc && entries[i].op == op) return true;
    return false;
}

int main(void) {
    size_t prg = 32768, size = 16 + prg;
    uint8_t *rom = calloc(1, size);
    if (!rom) return 2;
    memcpy(rom, "NES\032", 4);
    rom[4] = 2; rom[7] = 8; rom[10] = 7; rom[11] = 7;   /* NES 2.0, 8 KiB work RAM, 8 KiB CHR RAM */
    memset(rom + 16, 0xea, prg);
    for (size_t pos = 16; pos < size; pos += 4096) {
        rom[pos + 4090] = rom[pos + 4092] = rom[pos + 4094] = 0;
        rom[pos + 4091] = rom[pos + 4093] = rom[pos + 4095] = 0x80;
    }
    CHECK(cyc_load_ines(rom, size));
    free(rom);
    cyc_run_native = false;
    static Entry entries[4096];
    /* No RAM code run: nothing recorded, nothing added. */
    cyc_power_on(0); cyc_run_power_on();
    cpu_interp_step();   /* the power-on reset sequence, before any RAM code */
    rr_nes_ram_trace_enable();
    CHECK(read_trace(entries, 4096) == 0);
    /* The routine in internal RAM and the same routine in the cartridge RAM, each run up to its NOP. */
    const unsigned bases[2] = {0x0300, 0x6100};
    for (unsigned w = 0; w < 2; w++) {
        unsigned base = bases[w];
        place(base, w ? poke_cart : poke_ram);
        cpu.pc = (uint16_t)base;
        for (unsigned step = 0; step < 7; step++) cpu_interp_step();
        CHECK(cpu.pc == base + 0x40);
    }
    unsigned count = read_trace(entries, 4096);
    for (unsigned w = 0; w < 2; w++) {
        unsigned base = bases[w];
        static const unsigned executed[][2] = {{0, 0xA9}, {2, 0xF0}, {9, 0x20}, {0x0C, 0x4C}, {0x20, 0xE8}, {0x21, 0xD0}, {0x25, 0x60}};
        for (unsigned i = 0; i < sizeof executed / sizeof executed[0]; i++) CHECK(has(entries, count, base + executed[i][0], executed[i][1]));
        /* Reachable and never executed: the fall-through past the taken branch, and the paths after the others. */
        static const unsigned reached[][2] = {{4, 0xA2}, {6, 0x86}, {8, 0xEA}, {0x23, 0xD0}, {0x40, 0xEA}, {0x41, 0x4C}};
        for (unsigned i = 0; i < sizeof reached / sizeof reached[0]; i++) CHECK(has(entries, count, base + reached[i][0], reached[i][1]));
        /* Not reachable from any entry, or not followable. */
        CHECK(!has(entries, count, base + 0x0F, 0xA9));    /* after the unconditional jump */
        CHECK(!has(entries, count, base + 0x26, 0xEA));    /* after the return */
        CHECK(!has(entries, count, base + 0x50, 0x02));    /* illegal opcode */
        CHECK(!has(entries, count, 0x9000, 0xEA));         /* outside the windows */
    }
    CHECK(count == 26);   /* 13 entries in each window and nothing else */
    /* Running the sweep again changes nothing. */
    CHECK(read_trace(entries, 4096) == count);
    printf("{\"entries\":%u,\"checks\":%u}\n", count, checks);
    return 0;
}
