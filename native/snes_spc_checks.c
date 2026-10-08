/* Authored SPC700 adapter checks. Internal shared semantics, not hardware proof. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "snes/spc.h"
#include "snes_spc_native.h"
#include "fixture_data.h"

static Apu machine;
static Apu initial, compiled_apu;
static uint64_t bus_trace;
static unsigned cases;
static void require(bool valid, const char *message) {
    if (!valid) { fprintf(stderr, "%s (case %u)\n", message, cases); exit(1); }
}
static void trace(uint16_t pc, uint8_t value, bool write) {
    bus_trace ^= pc | ((uint64_t)value << 16) | ((uint64_t)write << 24);
    bus_trace *= 1099511628211ull;
}
uint8_t apu_cpuRead(Apu *apu, uint16_t adr) {
    uint8_t value;
    if (adr >= 0xfd && adr <= 0xff) {
        value = apu->timer[adr - 0xfd].counter; apu->timer[adr - 0xfd].counter = 0;
    } else if (adr >= 0xf4 && adr <= 0xf9) value = apu->inPorts[adr - 0xf4];
    else if (apu->romReadable && adr >= 0xffc0) value = fixture_boot[adr - 0xffc0];
    else value = apu->ram[adr];
    trace(adr, value, false); return value;
}
void apu_cpuWrite(Apu *apu, uint16_t adr, uint8_t value) {
    if (adr >= 0xf4 && adr <= 0xf7) apu->outPorts[adr - 0xf4] = value;
    if (adr == 0xf1) apu->romReadable = (value & 0x80) != 0;
    apu->ram[adr] = value; trace(adr, value, true);
}
static void compare(Spc input, bool expect_native) {
    initial = machine;
    Spc native = input, reference = input;
    rr_spc_set_mode(true, true); rr_spc_reset_evidence();
    bus_trace = 14695981039346656037ull;
    int cost = spc_runOpcode(&native);
    uint64_t native_trace = bus_trace;
    compiled_apu = machine;
    require(rr_spc_native_opcodes() == (expect_native ? 1u : 0u), "native opcode accounting");
    require(rr_spc_interpreted_opcodes() == (expect_native ? 0u : 1u), "fallback opcode accounting");
    machine = initial;
    rr_spc_set_mode(false, false); rr_spc_reset_evidence();
    bus_trace = 14695981039346656037ull;
    int reference_cost = spc_runOpcode(&reference);
    require(reference_cost == cost, "cycle difference");
    require(memcmp(&native, &reference, sizeof native) == 0, "register/flag difference");
    require(memcmp(&machine, &compiled_apu, sizeof machine) == 0, "APU RAM/port/timer difference");
    require(bus_trace == native_trace, "bus read/write order difference");
    require(rr_spc_native_opcodes() == 0 && rr_spc_interpreted_opcodes() == 1, "reference accounting");
    ++cases;
}
static Spc state(uint16_t pc, unsigned flags) {
    Spc cpu = {0}; cpu.apu = &machine; cpu.pc = pc;
    cpu.a = (uint8_t)(flags * 19); cpu.x = flags % 4 ? (uint8_t)(flags * 11) : 0;
    cpu.y = (uint8_t)(flags * 37); cpu.sp = (uint8_t)(255 - flags);
    cpu.c = !!(flags & 1); cpu.z = !!(flags & 2); cpu.i = !!(flags & 4); cpu.h = !!(flags & 8);
    cpu.b = !!(flags & 16); cpu.p = !!(flags & 32); cpu.v = !!(flags & 64); cpu.n = !!(flags & 128);
    return cpu;
}
int main(void) {
    for (unsigned flags = 0; flags < 256; ++flags) {
        for (unsigned opcode = 0; opcode < 256; ++opcode) {
            memset(&machine, 0, sizeof machine);
            for (unsigned i = 0; i < 65536; ++i) machine.ram[i] = (uint8_t)(i * 13 + flags * 7);
            uint16_t pc = (uint16_t)(0x2000 + opcode * 8);
            machine.ram[pc] = (uint8_t)opcode;
            machine.ram[pc + 1] = (uint8_t)(flags % 3 ? 0x34 : 0xff);
            machine.ram[pc + 2] = (uint8_t)(flags % 3 ? 0x12 : 0);
            for (unsigned i = 0; i < 3; ++i) machine.timer[i].counter = (uint8_t)(flags & 15);
            compare(state(pc, flags), true);
        }
    }
    for (unsigned opcode = 0; opcode < 256; ++opcode) {
        memset(&machine, 0, sizeof machine);
        machine.ram[0xffff] = (uint8_t)opcode; machine.ram[0] = 0xfe; machine.ram[1] = 0x34;
        compare(state(0xffff, opcode), true); /* opcode/operand/stack wrapping */
    }
    for (unsigned i = 0; i < 64; ++i) {
        memset(&machine, 0, sizeof machine); machine.romReadable = true;
        compare(state((uint16_t)(0xffc0 + i), i), true);
    }
    memset(&machine, 0, sizeof machine);
    machine.ram[0x2000] = 0xe8; machine.ram[0x2001] = 0x91;
    compare(state(0x2000, 0), false); /* changed opcode rejected */
    machine.ram[0x2000] = 0;
    compare(state(0x2000, 0), true); /* restored opcode */
    compare(state(0xf4, 0), false); /* volatile I/O fetch is read once */
    machine.ram[0xe000] = 0xe8; machine.ram[0xe001] = 0x91;
    compare(state(0xe000, 0), true);
    Spc load = state(0xe000, 0); rr_spc_set_mode(true, false); spc_runOpcode(&load);
    require(load.a == 0x91, "live immediate operand");
    machine.ram[0xe001] = 0x37; load = state(0xe000, 0); spc_runOpcode(&load);
    require(load.a == 0x37, "rewritten immediate stays native");
    machine.ram[0xe100] = 0xd0; machine.ram[0xe101] = 0xfe;
    Spc branch = state(0xe100, 0); int taken = spc_runOpcode(&branch);
    require(taken == 4 && branch.pc == 0xe100, "taken branch penalty");
    branch = state(0xe100, 2); require(spc_runOpcode(&branch) == 2 && branch.pc == 0xe102, "untaken branch cost");
    machine.ram[0xe200] = 0xe4; machine.ram[0xe201] = 0xfd; machine.timer[0].counter = 7;
    Spc timer = state(0xe200, 0); spc_runOpcode(&timer);
    require(timer.a == 7 && machine.timer[0].counter == 0, "read-to-clear timer bus");
    for (unsigned mode = 0; mode < 2; ++mode) {
        rr_spc_set_mode(mode != 0, true); rr_spc_reset_evidence();
        Spc stopped = state(0xe300, 0); stopped.stopped = true;
        require(spc_runOpcode(&stopped) == 1 && stopped.pc == 0xe300, "stopped scheduler tick");
        require(!rr_spc_native_opcodes() && !rr_spc_interpreted_opcodes(), "idle is not a retired opcode");
    }
    printf("{\"passed\":true,\"differential_cases\":%u,\"independent_assertions\":9}\n", cases);
    return 0;
}
