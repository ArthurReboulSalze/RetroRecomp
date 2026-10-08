/* Internal differential for ROM-specialized 6502 bodies. No copyrighted ROMs.
 * The umbrella is included here to test one dense instruction, bypassing hot
 * blocks which intentionally run until a frame or control-flow boundary. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cyc_core.h"
#include "hw_internal.h"
#include "game_cyc.c"

typedef struct {
    Cpu6502 cpu_state;
    uint64_t cycles, bus_hash, memory_hash, hardware_hash;
    unsigned bank;
} Result;

static void mmc1_write(uint16_t address, uint8_t value) {
    for (int bit = 0; bit < 5; bit++) {
        cpu_write(address, (value >> bit) & 1, 0);
        cpu_read(0, 0); /* MMC1 ignores writes on consecutive CPU cycles. */
    }
}

static void setup(unsigned mapping, uint16_t pc, unsigned variant) {
    cyc_power_on(variant & 3);
    memset(&cpu, 0, sizeof(cpu));
    if (hw_cart.mapper == 1) {
        cpu_write(0x8000, 0x80, 0);
        cpu_read(0, 0);
        mmc1_write(0x8000, (uint8_t)((mapping & 3) << 2));
        mmc1_write(0xE000, (uint8_t)(mapping & 3));
    } else if (hw_cart.mapper == 2) {
        cpu_write(0xBFF0, mapping & 2, 0); /* ROM=$EA, handles bus conflicts. */
    } else if (hw_cart.mapper == 4) {
        cpu_write(0x8000, (uint8_t)(6 | ((mapping & 1) << 6)), 0);
        cpu_write(0x8001, (uint8_t)(mapping + 1), 0);
        cpu_write(0x8000, (uint8_t)(7 | ((mapping & 1) << 6)), 0);
        cpu_write(0x8001, (uint8_t)(mapping + 2), 0);
    }
    memset(&cpu, 0, sizeof(cpu));
    cpu.pc = pc;
    cpu.a = (uint8_t)(0x13 + variant * 43);
    cpu.x = (uint8_t)(variant * 85);
    cpu.y = (uint8_t)(255 - cpu.x);
    cpu.s = (uint8_t)(0xFF - variant);
    cpu_set_p((uint8_t)(variant * 0x55));
    for (unsigned i = 0; i < 0x800; i++) hw.ram[i] = (uint8_t)(i * 17 + variant * 31);
    cyc_trace_hash = 0;
    cyc_trace_cycle = 0;
    cyc_trace_enabled = true;
}

static Result snapshot(void) {
    Result r = {0};
    r.cpu_state = cpu;
    r.cycles = cyc_cycle_count();
    r.bus_hash = cyc_trace_hash;
    r.memory_hash = cyc_mem_state_hash();
    r.hardware_hash = cyc_hw_state_hash();
    r.bank = hw_prg_bank4(cpu.pc);
    return r;
}

static unsigned checked;
static void compare(unsigned mapping, uint16_t pc, unsigned variant, unsigned interrupt) {
    setup(mapping, pc, variant);
    cpu.do_nmi = interrupt == 1;
    cpu.do_irq = interrupt == 2;
    if (!dense_has(pc) || !cyc_native_has(pc)) {
        fprintf(stderr, "Native entry missing: mapper=%d PC=%04X\n", hw_cart.mapper, pc);
        exit(1);
    }
    dense_step(pc);
    Result native = snapshot();
    setup(mapping, pc, variant);
    cpu.do_nmi = interrupt == 1;
    cpu.do_irq = interrupt == 2;
    cpu_interp_step();
    Result reference = snapshot();
    if (memcmp(&native.cpu_state, &reference.cpu_state, sizeof(Cpu6502)) ||
            native.cycles != reference.cycles || native.bus_hash != reference.bus_hash ||
            native.memory_hash != reference.memory_hash ||
            native.hardware_hash != reference.hardware_hash || native.bank != reference.bank) {
        fprintf(stderr, "Mismatch: mapper=%d map=%u PC=%04X variant=%u IRQ=%u "
                "CPU=%d cycles=%d bus=%d memory=%d hardware=%d bank=%d\n",
                hw_cart.mapper, mapping, pc, variant, interrupt,
                memcmp(&native.cpu_state, &reference.cpu_state, sizeof(Cpu6502)) != 0,
                native.cycles != reference.cycles, native.bus_hash != reference.bus_hash,
                native.memory_hash != reference.memory_hash,
                native.hardware_hash != reference.hardware_hash, native.bank != reference.bank);
        exit(1);
    }
    checked++;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 2;
    fseek(f, 0, SEEK_END);
    size_t length = (size_t)ftell(f);
    rewind(f);
    uint8_t *image = (uint8_t *)malloc(length);
    if (!image || fread(image, 1, length, f) != length) return 2;
    fclose(f);
    if (!cyc_load_ines(image, length)) return 2;
    free(image);
    for (unsigned mapping = 0; mapping < 4; mapping++) {
        for (unsigned variant = 0; variant < 4; variant++) {
            for (unsigned slot = 0; slot < 8; slot++) {
                for (unsigned op = 0; op < 256; op++)
                    compare(mapping, (uint16_t)(0x8100 + slot * 0x1000 + op * 4), variant, 0);
                compare(mapping, (uint16_t)(0x8FFE + slot * 0x1000), variant, 0);
                compare(mapping, (uint16_t)(0x8FFF + slot * 0x1000), variant, 0);
                compare(mapping, (uint16_t)(0x8100 + slot * 0x1000), variant, 1);
                compare(mapping, (uint16_t)(0x8100 + slot * 0x1000), variant, 2);
            }
        }
    }
    printf("{\"mapper\":%d,\"instruction_cases\":%u,\"passed\":true}\n", hw_cart.mapper, checked);
    return 0;
}
