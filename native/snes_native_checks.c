/* Authored 65816 fixtures: static operations versus the internal reference.
 * This checks the compiler adapter, not independent hardware accuracy. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "types.h"
#include "cpu_state.h"
#include "snes/snes.h"
#include "snes/cart.h"
#include "snes_native_steps.h"
#include "fixture_rom.h"

uint8_t g_ram[0x20000];
static uint8_t bus_data[0x10000];
static uint8_t original_ram[0x20000], original_bus[0x10000];
static uint8_t result_ram[0x20000], result_bus[0x10000];
static uint8_t cartridge[sizeof fixture_rom];
static Cart cart;
static Snes machine;
Snes *g_snes = &machine;
static uint64_t native_count, fallback_count, bus_trace;
void rr16_snes_note_native(void) { ++native_count; }
void rr16_snes_note_interpreted(uint32_t pc) { (void)pc; ++fallback_count; }
void rr16_snes_observe_fallback(uint32_t pc) { (void)pc; }
int interp816_opcode_hook(uint32_t pc) { (void)pc; return 0; }
uint8_t *cart_getRomPtr(Cart *c, uint8_t bank, uint16_t address) {
    if (bank == 0x7e || bank == 0x7f || (address < 0x8000 && (bank & 0x7f) < 0x40)) return NULL;
    return c->rom + ((((uint32_t)(bank & 0x7f) << 15) | (address & 0x7fff)) % c->romSize);
}
static void trace(uint32_t address, uint8_t value, bool write) {
    bus_trace ^= (address & 0xffffffu) | ((uint64_t)value << 24) | ((uint64_t)write << 32);
    bus_trace *= 1099511628211ull;
}
static uint8_t read_byte(void *mem, uint32_t address) {
    (void)mem;
    int32_t offset = cpu_wram_offset((uint8_t)(address >> 16), (uint16_t)address);
    uint8_t *rom = cart_getRomPtr(&cart, (uint8_t)(address >> 16), (uint16_t)address);
    uint8_t value = offset >= 0 ? g_ram[offset] : rom ? *rom : bus_data[address & 0xffff];
    trace(address, value, false); return value;
}
static void write_byte(void *mem, uint32_t address, uint8_t value) {
    (void)mem;
    int32_t offset = cpu_wram_offset((uint8_t)(address >> 16), (uint16_t)address);
    if (offset >= 0) g_ram[offset] = value;
    else if (!cart_getRomPtr(&cart, (uint8_t)(address >> 16), (uint16_t)address))
        bus_data[address & 0xffff] = value;
    trace(address, value, true);
}
static void compare(Interp816 input, bool should_native) {
    memcpy(original_ram, g_ram, sizeof g_ram); memcpy(original_bus, bus_data, sizeof bus_data);
    Interp816 compiled = input, reference = input;
    native_count = fallback_count = 0; bus_trace = 14695981039346656037ull;
    rr_snes_native_set_enabled(true);
    int native_cycles = interp816_runOpcode(&compiled);
    uint64_t compiled_trace = bus_trace;
    memcpy(result_ram, g_ram, sizeof g_ram); memcpy(result_bus, bus_data, sizeof bus_data);
    if (native_count != (should_native ? 1u : 0u) || fallback_count != (should_native ? 0u : 1u)) {
        fprintf(stderr, "Incorrect execution counter at %02x:%04x\n", input.k, input.pc); exit(1);
    }
    memcpy(g_ram, original_ram, sizeof g_ram); memcpy(bus_data, original_bus, sizeof bus_data);
    bus_trace = 14695981039346656037ull;
    rr_snes_native_set_enabled(false);
    int reference_cycles = interp816_runOpcode(&reference);
    if (native_cycles != reference_cycles || memcmp(&compiled, &reference, sizeof compiled) ||
        compiled_trace != bus_trace || memcmp(result_ram, g_ram, sizeof g_ram) ||
        memcmp(result_bus, bus_data, sizeof bus_data)) {
        fprintf(stderr, "Instruction/bus mismatch at %02x:%04x (e=%d m=%d x=%d)\n",
                input.k, input.pc, input.e, input.mf, input.xf); exit(2);
    }
}
int main(void) {
    memcpy(cartridge, fixture_rom, sizeof cartridge);
    cart.type = CART_LOROM; cart.rom = cartridge; cart.romSize = sizeof cartridge;
    machine.cart = &cart;
    unsigned cases = 0;
    for (unsigned mode = 0; mode < 32; ++mode) {
        Interp816 cpu = {0}; cpu.read = read_byte; cpu.write = write_byte;
        cpu.a = 0x9f30; cpu.x = 0xff; cpu.y = 0x101; cpu.sp = 0x201; cpu.dp = (mode & 4) ? 0xff : 0x300;
        cpu.c = !!(mode & 8); cpu.d = !!(mode & 4); cpu.z = cpu.v = cpu.n = !!(mode & 8);
        cpu.e = !!(mode & 16); cpu.mf = cpu.e || (mode & 1); cpu.xf = cpu.e || (mode & 2);
        if (cpu.e) cpu.sp = 0x1f8;
        if (cpu.xf) { cpu.x &= 0xff; cpu.y &= 0xff; }
        for (unsigned mirror = 0; mirror < 2; ++mirror) {
            cpu.k = mirror ? 0x80 : 0;
            for (unsigned opcode = 0; opcode < 256; ++opcode) {
                for (unsigned i = 0; i < sizeof g_ram; ++i) g_ram[i] = (uint8_t)(i * 19 + 7);
                for (unsigned i = 0; i < sizeof bus_data; ++i) bus_data[i] = (uint8_t)(i * 13 + 9);
                cpu.pc = (uint16_t)(0x8000 + opcode * 8);
                compare(cpu, true); ++cases;
            }
        }
        /* LDA operand crosses $FFFF into the live WRAM bus, retaining PB. */
        cpu.k = 0; cpu.pc = 0xffff; compare(cpu, true); ++cases;
        cpu.k = 0x7e; cpu.pc = 0x100;
        memcpy(g_ram + 0x100, "\xa9\x34\x12\xea", 4);
        compare(cpu, true); ++cases;
        /* Both changed opcode and changed extension reject the full RAM guard. */
        g_ram[0x100] = 0xea; compare(cpu, false); ++cases;
        g_ram[0x100] = 0xa9; g_ram[0x101] ^= 0x40; compare(cpu, false); ++cases;
        /* A changed ROM opcode must not run the original compiled operation. */
        cpu.k = 0; cpu.pc = 0x8000; cartridge[0] = 0xea;
        compare(cpu, false); ++cases; cartridge[0] = fixture_rom[0];
    }
    puts("{\"instruction_state_bus_comparisons\":16544,\"ram_guards\":\"passed\",\"rom_mutation_guard\":\"passed\",\"passed\":true}");
    return cases != 16544;
}
