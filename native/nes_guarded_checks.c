/* Authored CPU/bus differential. No commercial ROM or gameplay assets. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cyc_core.h"
#include "cyc_run.h"
#include "hw_internal.h"
#include "game_cyc.c"

typedef struct {
    Cpu6502 cpu_state;
    uint64_t cycles, bus, memory, hardware;
} Result;
static unsigned cases, rejected, remaps, dmc_fetches, reset_cases;

static void setup(uint16_t pc, unsigned op, unsigned variant, unsigned interrupt, bool unstable) {
    /* Cartridge CHR RAM survives a reset. Each independent comparison must
     * start from the same bytes, including the PPU's first clock tick. */
    if (hw_cart.chr_ram_len) memset(hw_cart.chr + hw_cart.chr_ram_base, 0x55, hw_cart.chr_ram_len);
    cyc_power_on(variant & 3);
    cyc_trace_enabled = false;
    if (hw_cart.mapper == 5) {
        cpu_write(0x5100, 3, 0);
        cpu_write(0x5102, 2, 0); cpu_write(0x5103, 1, 0);
        cpu_write(0x5113, 0, 0);
        cpu_write(0x5114, 0, 0); cpu_write(0x5115, 1, 0);
        cpu_write(0x5116, 2, 0);
    }
    if (hw_cart.mapper == 69) {
        cpu_write(0x8000, 8, 0); cpu_write(0xA000, (uint8_t)(0xC0 | (variant & 1)), 0);
    }
    if (hw_cart.mapper == 153) cpu_write(0x800D, 0x20, 0);
    for (unsigned i = 0; i < 0x800; i++) hw.ram[i] = (uint8_t)(i * 17 + variant * 31);
    if (hw_cart.has_wram) memset(hw_cart.wram, (int)(variant * 31), hw_cart.wram_len);
    if (unstable) {
        if (hw_cart.mapper == 153) {
            hw_cart.m.reg[0] = 0; hw_cart.m.reg[1] = 1;
            hw_cart.m.reg[2] = 0; hw_cart.m.reg[3] = 1;
        } else {
            hw_cart.m.ctrl = 0x1C; hw_cart.m.chr0 = 0; hw_cart.m.chr1 = 16;
        }
        hw_cart_ppu_addr_watched(0);
        cpu_write(0x2000, 0x10, 0); cpu_write(0x2001, 0x18, 0);
        ppu.scanline = 0; ppu.dot = (uint16_t)(variant * 3 + 1);
        ppu.show_bg = ppu.eval_bg = ppu.instant_bg = 1;
        if (hw_prg_is_stable()) { fprintf(stderr, "Unstable fixture is stable\n"); exit(2); }
    } else {
        uint8_t raw[3] = {(uint8_t)op, (uint8_t)(variant & 1 ? 0xFF : 0x01), 0x01};
        for (unsigned i = 0; i < 3; i++) {
            uint16_t addr = (uint16_t)(pc + i); uint8_t ignored;
            if (rr_nes_ram_peek(addr, &ignored)) cpu_write(addr, raw[i], 0);
        }
    }
    if (variant >= 4) {
        /* Leave a real DMC request pending on write cycles. It must steal
         * the opcode-fetch read, including its terminal-sample IRQ. */
        cpu_write(0x4010, 0x8F, 0); cpu_write(0x4012, 0xFF, 0);
        cpu_write(0x4013, 0, 0); cpu_write(0x4015, 0x10, 0);
        ApuDmcView d;
        for (unsigned n = 0; n < 16; n++) {
            apu_debug_dmc(&d); if (d.dma) break;
            cpu_write(0, 0, 0);
        }
        apu_debug_dmc(&d);
        if (!d.dma || !d.playing || d.bytes != 1) { fprintf(stderr, "DMC fixture not armed\n"); exit(2); }
    }
    if (variant >= 8 || (variant < 4 && (variant & 2))) cpu_write(0x4014, 2, 0);
    memset(&cpu, 0, sizeof(cpu)); cpu.pc = pc;
    cpu.a = (uint8_t)(0x13 + variant * 43); cpu.x = (uint8_t)(variant * 85);
    cpu.y = (uint8_t)(255 - cpu.x); cpu.s = (uint8_t)(0xFF - variant);
    cpu_set_p((uint8_t)(variant * 0x55));
    cpu.do_nmi = interrupt & 1; cpu.do_irq = (interrupt >> 1) & 1;
    cpu.do_reset = (interrupt >> 2) & 1;
    cyc_trace_hash = 0; cyc_trace_cycle = 0; cyc_trace_enabled = true;
    cyc_run_interp_rom_cycles = cyc_run_interp_ram_cycles = cyc_run_interp_other_cycles = 0;
}
static Result snapshot(void) {
    Result r = {0}; r.cpu_state = cpu; r.cycles = cyc_cycle_count();
    r.bus = cyc_trace_hash; r.memory = cyc_mem_state_hash(); r.hardware = cyc_hw_state_hash();
    return r;
}
static void compare(uint16_t pc, unsigned op, unsigned variant, unsigned interrupt, bool unstable) {
    setup(pc, op, variant, interrupt, unstable);
    Result initial = snapshot();
    if (!cyc_native_has(pc)) { fprintf(stderr, "Missing native entry %04X/%02X\n", pc, op); exit(2); }
    unsigned before_bank = hw_prg_bank4(pc);
    live_step(pc);
    if (variant >= 4) {
        ApuDmcView d; apu_debug_dmc(&d);
        if (d.dma || d.bytes != 0) { fprintf(stderr, "DMC fetch not exercised\n"); exit(2); }
        dmc_fetches++;
    }
    if (interrupt & 4) reset_cases++;
    if (unstable && before_bank != hw_prg_bank4(pc)) remaps++;
    Result native = snapshot();
    if (cyc_run_interp_rom_cycles || cyc_run_interp_ram_cycles || cyc_run_interp_other_cycles) {
        fprintf(stderr, "Unexpected fallback %04X/%02X\n", pc, op); exit(2);
    }
    setup(pc, op, variant, interrupt, unstable);
    Result initial_reference = snapshot();
    if (memcmp(&initial,&initial_reference,sizeof(initial))) {
        fprintf(stderr,"Fixture initial states differ mapper=%d pc=%04X op=%02X variant=%u irq=%u\n",
                hw_cart.mapper,pc,op,variant,interrupt); exit(2);
    }
    cpu_interp_step();
    Result reference = snapshot();
    if (memcmp(&native, &reference, sizeof(native))) {
        fprintf(stderr, "Divergence mapper=%d pc=%04X op=%02X variant=%u irq=%u cycles=%llu/%llu bus=%llx/%llx mem=%llx/%llx hw=%llx/%llx\n",
                hw_cart.mapper, pc, op, variant, interrupt,
                (unsigned long long)native.cycles, (unsigned long long)reference.cycles,
                (unsigned long long)native.bus, (unsigned long long)reference.bus,
                (unsigned long long)native.memory, (unsigned long long)reference.memory,
                (unsigned long long)native.hardware, (unsigned long long)reference.hardware);
        const uint8_t *a=(const uint8_t *)&native.cpu_state,*b=(const uint8_t *)&reference.cpu_state;
        for(unsigned n=0;n<sizeof(cpu);n++) if(a[n]!=b[n]) fprintf(stderr,"CPU byte %u: %02X/%02X\n",n,a[n],b[n]);
        exit(2);
    }
    cases++;
}
static void unknown(void) {
    for (unsigned variant = 0; variant <= 8; variant += 4) {
    setup(0x0400, 0xEA, variant, 0, false); /* Only LDA was observed at this address. */
    if (cyc_native_has(0x0400)) { fprintf(stderr, "Changed opcode accepted\n"); exit(2); }
    uint64_t before = cyc_cycle_count(); live_step(0x0400); Result native = snapshot();
    if (cyc_run_interp_ram_cycles != cyc_cycle_count() - before) {
        fprintf(stderr, "Fetched fallback hidden from counters\n"); exit(2);
    }
    setup(0x0400, 0xEA, variant, 0, false); cpu_interp_step(); Result reference = snapshot();
    if (memcmp(&native, &reference, sizeof(native))) { fprintf(stderr, "Fetched fallback diverged\n"); exit(2); }
    }
    setup(0x0500, 0xA9, 0, 0, false);
    if (cyc_native_has(0x0500) || cyc_native_has(0x2000) || cyc_native_has(0x4016)) {
        fprintf(stderr, "Unobserved RAM or MMIO accepted\n"); exit(2);
    }
    rejected += 6;
    uint8_t value;
    if (hw_cart.mapper == 69) {
        setup(0x6000, 0xA9, 0, 0, false);
        for (unsigned mode = 0; mode < 3; mode++) {
            const uint8_t select[] = {0, 0x40, 0x80};
            cpu_write(0x8000, 8, 0); cpu_write(0xA000, select[mode], 0);
            bool mapped_rom = select[mode] != 0x40;
            if (rr_nes_ram_peek(0x6000, &value) || cyc_native_has(0x6000) != mapped_rom) {
                fprintf(stderr, "FME-7 ROM/RAM selection mismatch\n"); exit(2);
            }
            if (!mapped_rom) rejected++;
        }
    }
    if (hw_cart.mapper == 153) {
        const uint8_t mode[] = {0, 0x80, 0xA0};
        for (unsigned n = 0; n < 3; n++) {
            setup(0x6000, 0xA9, 0, 0, false); cpu_write(0x800D, mode[n], 0);
            if (rr_nes_ram_peek(0x6000, &value) || cyc_native_has(0x6000)) {
                fprintf(stderr, "Bandai disabled/contended RAM accepted\n"); exit(2);
            }
            rejected++;
        }
    }
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    FILE *file = fopen(argv[1], "rb"); if (!file) return 2;
    fseek(file, 0, SEEK_END); size_t n = ftell(file); rewind(file);
    uint8_t *rom = malloc(n); if (!rom || fread(rom, 1, n, file) != n) return 2; fclose(file);
    if (!cyc_load_ines(rom, n)) return 2; free(rom);
    bool unstable = hw_cart.mapper == 1 || hw_cart.mapper == 153 || hw_cart.mapper == 155;
    if (unstable) {
        for (unsigned op = 0; op < 256; op++) for (unsigned variant = 0; variant < 4; variant++)
            for (unsigned interrupt = 0; interrupt < 8; interrupt++)
                compare((uint16_t)(0x8100 + op * 4), op, variant, interrupt, true);
        if (!remaps) { fprintf(stderr, "No fetch-time PPU remap exercised\n"); return 2; }
    }
    {
        const uint16_t addresses[] = {0x0300, 0x0B00, 0x07FE, 0x1FFE, 0x6000, 0x6FFE, 0x7FFE, 0x8000, 0xBFFE};
        unsigned length = hw_cart.mapper == 5 ? 9 : 7;
        for (unsigned address = 0; address < length; address++)
            for (unsigned op = 0; op < 256; op++) for (unsigned variant = 0; variant < 4; variant++)
                for (unsigned interrupt = 0; interrupt < 8; interrupt++)
                    compare(addresses[address], op, variant, interrupt, false);
    }
    /* Every opcode, both DMC/OAM arbitration modes, all four clock phases,
     * and every combination of pending NMI/IRQ/reset. */
    for (unsigned op = 0; op < 256; op++) for (unsigned variant = 4; variant < 12; variant++)
        for (unsigned interrupt = 0; interrupt < 8; interrupt++) {
            compare(0x0300, op, variant, interrupt, false);
            compare(0x6000, op, variant, interrupt, false);
            if (unstable) compare((uint16_t)(0x8100 + op * 4), op, variant, interrupt, true);
        }
    unknown();
    printf("{\"passed\":true,\"mapper\":%d,\"instruction_cases\":%u,\"rejected_guards\":%u,\"ppu_remaps\":%u,\"dmc_fetches\":%u,\"reset_cases\":%u}\n",
           hw_cart.mapper, cases, rejected, remaps, dmc_fetches, reset_cases);
    return 0;
}
