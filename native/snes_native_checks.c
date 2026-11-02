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
#include "snes_cart.h"
#include "fixture_rom.h"

uint8_t g_ram[0x20000];
static uint8_t bus_data[0x10000];
static uint8_t original_ram[0x20000], original_bus[0x10000], original_cart_ram[0x2000];
static uint8_t result_ram[0x20000], result_bus[0x10000], result_cart_ram[0x2000];
static uint8_t cartridge[sizeof fixture_rom];
static Cart cart;
static Snes machine;
Snes *g_snes = &machine;
static uint64_t native_count, fallback_count, unobserved_count, bus_trace;
static uint8_t cart_ram[0x2000];
static bool mutate_fetch;
void rr16_snes_note_native(void) { ++native_count; }
/* As in the game: a compiled body at an unobserved RAM position is also a native one. */
void rr16_snes_note_compiled_unobserved(void) { ++unobserved_count; }
void rr16_snes_note_interpreted(uint32_t pc) { (void)pc; ++fallback_count; }
void rr16_snes_observe_fallback(uint32_t pc) { (void)pc; }
int interp816_opcode_hook(uint32_t pc) { (void)pc; return 0; }
uint8_t *cart_getRomPtr(Cart *c, uint8_t bank, uint16_t address) {
    if (bank == 0x7e || bank == 0x7f || (address < 0x8000 && (bank & 0x7f) < 0x40)) return NULL;
    /* As the engine: the LoROM save RAM sits in banks $70-$7D and $F0-$FF below $8000 and is not ROM. */
    if (c->type == CART_LOROM && ((bank >= 0x70 && bank < 0x7e) || bank >= 0xf0) && address < 0x8000 && c->ramSize > 0)
        return NULL;
    if (c->type == CART_HIROM)
        return c->rom + ((((uint32_t)(bank & 0x3f) << 16) | address) % c->romSize);
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
    int32_t sram = offset < 0 ? rr_snes_cart_ram_offset(&cart, (uint8_t)(address >> 16), (uint16_t)address) : -1;
    uint8_t value = offset >= 0 ? g_ram[offset] : sram >= 0 ? cart_ram[sram] : rom ? *rom : bus_data[address & 0xffff];
    if(mutate_fetch && (address==0x7e0100 || address==0x008000)) {
        value=0xea;if(offset>=0)g_ram[offset]=value;
    }
    trace(address, value, false); return value;
}
static void write_byte(void *mem, uint32_t address, uint8_t value) {
    (void)mem;
    int32_t offset = cpu_wram_offset((uint8_t)(address >> 16), (uint16_t)address);
    int32_t sram = offset < 0 ? rr_snes_cart_ram_offset(&cart, (uint8_t)(address >> 16), (uint16_t)address) : -1;
    if (offset >= 0) g_ram[offset] = value;
    else if (sram >= 0) cart_ram[sram] = value;
    else if (!cart_getRomPtr(&cart, (uint8_t)(address >> 16), (uint16_t)address))
        bus_data[address & 0xffff] = value;
    trace(address, value, true);
}
/* `unobserved`: the instruction is RAM code at a position the generated table does not hold, so it runs through the
 * body of its live opcode and is counted as compiled and not observed; otherwise it must not be. */
static void compare_kind(Interp816 input, bool should_native, bool unobserved) {
    memcpy(original_ram, g_ram, sizeof g_ram); memcpy(original_bus, bus_data, sizeof bus_data);
    memcpy(original_cart_ram, cart_ram, sizeof cart_ram);
    Interp816 compiled = input, reference = input;
    native_count = fallback_count = unobserved_count = 0; bus_trace = 14695981039346656037ull;
    rr_snes_native_set_enabled(true);
    int native_cycles = interp816_runOpcode(&compiled);
    uint64_t compiled_trace = bus_trace;
    memcpy(result_ram, g_ram, sizeof g_ram); memcpy(result_bus, bus_data, sizeof bus_data);
    memcpy(result_cart_ram, cart_ram, sizeof cart_ram);
    if (unobserved_count != ((should_native && unobserved) ? 1u : 0u)) {
        fprintf(stderr, "Incorrect compiled-and-unobserved counter at %02x:%04x\n", input.k, input.pc); exit(1);
    }
    if (native_count != (should_native ? 1u : 0u) || fallback_count != (should_native ? 0u : 1u)) {
        fprintf(stderr, "Incorrect execution counter at %02x:%04x\n", input.k, input.pc); exit(1);
    }
    memcpy(g_ram, original_ram, sizeof g_ram); memcpy(bus_data, original_bus, sizeof bus_data);
    memcpy(cart_ram, original_cart_ram, sizeof cart_ram);
    bus_trace = 14695981039346656037ull;
    rr_snes_native_set_enabled(false);
    int reference_cycles = interp816_runOpcode(&reference);
    if (native_cycles != reference_cycles || memcmp(&compiled, &reference, sizeof compiled) ||
        compiled_trace != bus_trace || memcmp(result_ram, g_ram, sizeof g_ram) ||
        memcmp(result_bus, bus_data, sizeof bus_data) || memcmp(result_cart_ram, cart_ram, sizeof cart_ram)) {
        fprintf(stderr, "Instruction/bus mismatch at %02x:%04x (e=%d m=%d x=%d)\n",
                input.k, input.pc, input.e, input.mf, input.xf); exit(2);
    }
}
static void compare(Interp816 input, bool should_native) { compare_kind(input, should_native, false); }
int main(void) {
    memcpy(cartridge, fixture_rom, sizeof cartridge);
    cart.type = FIXTURE_CART_TYPE; cart.rom = cartridge; cart.romSize = sizeof cartridge;
    cart.romImageSize = FIXTURE_IMAGE_BYTES;
    cart.ram = cart_ram; cart.ramSize = sizeof cart_ram;
    machine.cart = &cart;
    rr_snes_native_bind();
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
        /* An opcode nobody has seen executing at this address runs through the body of the opcode it has, counted as
         * compiled and not observed; changed operands retain the observed native operation and read their current
         * values on the timed bus. */
        g_ram[0x100] = 0xea; compare_kind(cpu, true, true); ++cases;
        g_ram[0x100] = 0xa9; g_ram[0x101] ^= 0x40; compare(cpu, true); ++cases;
        /* A changed ROM opcode must not run the original compiled operation. */
        cpu.k = 0; cpu.pc = 0x8000;
        uint8_t *start = cart_getRomPtr(&cart, cpu.k, cpu.pc);
        uint8_t saved = *start; *start = 0xea;
        compare(cpu, false); ++cases; *start = saved;
        /* RAM code at positions no table holds, every opcode in this register mode: WRAM, and the cartridge's RAM. */
        for (unsigned opcode = 0; opcode < 256; ++opcode) {
            for (unsigned i = 0; i < sizeof g_ram; ++i) g_ram[i] = (uint8_t)(i * 19 + 7);
            for (unsigned i = 0; i < sizeof bus_data; ++i) bus_data[i] = (uint8_t)(i * 13 + 9);
            for (unsigned i = 0; i < sizeof cart_ram; ++i) cart_ram[i] = (uint8_t)(i * 29 + 3);
            cpu.k = 0x7e; cpu.pc = (uint16_t)(0x6000 + opcode * 8);
            memcpy(g_ram + cpu.pc, (uint8_t[]){(uint8_t)opcode, 0x34, 0x12, 0}, 4);
            compare_kind(cpu, true, true); ++cases;
            cpu.k = cart.type == CART_LOROM ? 0x70 : 0x20; cpu.pc = (uint16_t)((cart.type == CART_LOROM ? 0x0000 : 0x6000) + opcode * 8);
            int32_t at = rr_snes_cart_ram_offset(&cart, cpu.k, cpu.pc);
            if (at < 0) { fprintf(stderr, "cartridge RAM fixture is not mapped\n"); return 20; }
            memcpy(cart_ram + at, (uint8_t[]){(uint8_t)opcode, 0x34, 0x12, 0}, 4);
            compare_kind(cpu, true, true); ++cases;
        }
    }
    /* The first byte of mirrored storage remains natively covered; changing
     * that byte must reject its original operation. */
    Interp816 cpu = {0}; cpu.read = read_byte; cpu.write = write_byte;
    cpu.sp = 0x1ff; cpu.e = cpu.mf = cpu.xf = true;
    cpu.k = cart.type == CART_LOROM ? 0xc3 : 0xc1; cpu.pc = 0x8000;
    if (cart_getRomPtr(&cart, cpu.k, cpu.pc) != cartridge + FIXTURE_IMAGE_BYTES) return 3;
    compare(cpu, true); ++cases;
    uint8_t *mirror = cart_getRomPtr(&cart, cpu.k, cpu.pc);
    uint8_t saved = *mirror; *mirror = 0xa9;
    compare(cpu, false); ++cases; *mirror = saved;
    /* Mapping and both image/storage lengths must match the generated map. The board is checked
     * when the cartridge is bound, so each change is followed by a new bind. */
    cpu.k = 0; cpu.pc = 0x8000;
    cart.type = cart.type == CART_LOROM ? CART_HIROM : CART_LOROM;
    rr_snes_native_bind(); compare(cpu, false); ++cases; cart.type = FIXTURE_CART_TYPE;
    ++cart.romImageSize; rr_snes_native_bind(); compare(cpu, false); ++cases; --cart.romImageSize;
    ++cart.romSize; rr_snes_native_bind(); compare(cpu, false); ++cases; --cart.romSize;
    rr_snes_native_bind();
    cpu.k=0x7e;cpu.pc=0x100;memcpy(g_ram+0x100,"\xa9\x34\x12\xea",4);
    /* The byte read at the fetch is not the one the table saw: the body of the opcode the CPU actually has runs, as
     * the interpreter would run it, and it is a compiled and unobserved one. */
    mutate_fetch=true;compare_kind(cpu,true,true);++cases;
    cpu.k=0;cpu.pc=0x8000;compare(cpu,false);++cases;mutate_fetch=false;
    /* An unsorted observation input beyond the old 2,048-entry ceiling must
     * dispatch every exact PC, read live operands and reject unknown opcodes/PCs. */
    rr_snes_native_set_enabled(true);cpu.k=0x7e;
    for(unsigned n=0;n<4096;n++) {
        cpu.pc=(uint16_t)(0x1000+4*n);memcpy(g_ram+cpu.pc,"\xa9\x34\x12\xea",4);
        if(!rr_snes_native_lookup(&cpu))return 4;
        g_ram[cpu.pc+1]^=1;if(!rr_snes_native_lookup(&cpu))return 5;
        /* Another opcode in place of the observed one, and a position nobody observed: the live opcode's own body. */
        g_ram[cpu.pc]^=1;{const RrSnesNativeOp *other=rr_snes_native_lookup(&cpu);if(!other||other->opcode!=g_ram[cpu.pc])return 7;}
        ++cpu.pc;{const RrSnesNativeOp *next=rr_snes_native_lookup(&cpu);if(!next||next->opcode!=g_ram[cpu.pc])return 6;}
    }
    /* The direct WRAM table must answer like the exact (PC, opcode) list: the authored
     * observations are $7E:2000 with two opcodes, $00:0300 and $7E:0300 (the same WRAM byte under
     * two banks, one opcode each). Operands are live; the fetched opcode must agree. */
    {
        /* `observed`: the generated table holds this position and opcode; otherwise the live opcode's body runs, counted
         * as compiled and not observed. Either way a WRAM instruction is compiled. */
        static const struct { uint8_t bank; uint16_t pc; uint8_t opcode; bool observed; } cases_ram[] = {
            {0x7e,0x2000,0xa9,true}, {0x7e,0x2000,0xea,true}, {0x7e,0x2000,0xa5,false},
            {0x00,0x0300,0xa9,true}, {0x00,0x0300,0xea,false},
            {0x7e,0x0300,0xea,true}, {0x7e,0x0300,0xa9,false},
            {0x80,0x0300,0xa9,false}, {0x7f,0x2000,0xa9,false}, {0x7e,0x2001,0xa9,false},
        };
        for (unsigned n = 0; n < sizeof cases_ram / sizeof *cases_ram; ++n) {
            cpu.k = cases_ram[n].bank; cpu.pc = cases_ram[n].pc;
            int32_t at = cpu_wram_offset(cpu.k, cpu.pc);
            g_ram[at] = cases_ram[n].opcode; g_ram[at + 1] = 0x34; g_ram[at + 2] = 0x12; g_ram[at + 3] = 0xea;
            const RrSnesNativeOp *found = rr_snes_native_lookup(&cpu);
            if (!found) return 10 + n;
            if (found->opcode != cases_ram[n].opcode) return 30 + n;
            compare_kind(cpu, true, !cases_ram[n].observed); ++cases;
            rr_snes_native_set_enabled(true);   /* the comparison ends with the reference run, native off */
            /* A fetched opcode that differs from the live byte never selects the operation. */
            if (rr_snes_native_lookup_fetched(((uint32_t)cpu.k << 16) | cpu.pc, (uint8_t)(cases_ram[n].opcode ^ 1))) return 50 + n;
            if (!rr_snes_native_lookup_fetched(((uint32_t)cpu.k << 16) | cpu.pc, cases_ram[n].opcode)) return 70 + n;
        }
        /* What is not RAM is not compiled: a fetch from the device registers stays on the counted interpreter. */
        cpu.k = 0; cpu.pc = 0x2100;
        if (rr_snes_native_lookup(&cpu)) return 90;
    }
    printf("{\"instruction_state_bus_comparisons\":%u,\"ram_guards\":\"passed\","
           "\"rom_mutation_guard\":\"passed\",\"mapping_and_size_guards\":\"passed\","
           "\"mirrored_storage\":\"passed\",\"guarded_positions_checked\":4096,"
           "\"wram_table_cases\":\"passed\",\"passed\":true}\n", cases);
    return cases != 32945;
}
