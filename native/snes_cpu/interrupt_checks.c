/* BRK ($00) and COP ($02) against the 65816 manual, not only against each other.
 * Native mode stacks K, takes 8 cycles and the $FFE6 (BRK) / $FFE4 (COP) vector;
 * emulation mode stacks no K, takes 7 cycles and the $FFFE (BRK) / $FFF4 (COP)
 * vector. The compiled operation and the reference interpreter must both give
 * exactly that. This is CPU timing and stack behaviour only: it says nothing about
 * hardware fidelity or gameplay.
 *
 * It reuses the fixtures of snes_native_checks.c (included, with its main renamed)
 * and lives in a folder of its own, so that the save-state key of the console,
 * which hashes the files directly below native/, does not move for a test. */
#define main rr_snes_native_base_checks
#include "../snes_native_checks.c"
#undef main

static void check_software_interrupt(unsigned opcode, bool emulation, bool native) {
    Interp816 cpu = {0}; cpu.read = read_byte; cpu.write = write_byte;
    cpu.e = emulation; cpu.mf = cpu.xf = emulation; cpu.sp = 0x1f8;
    cpu.pc = (uint16_t)(0x8000 + opcode * 8);
    /* The authored vectors: native COP $C0E4, native BRK $C0E6, emulation COP $C0F4,
     * emulation BRK $A9FE (its high byte is the $A9 the fixture keeps at $FFFF). */
    uint16_t vector = opcode == 0 ? (emulation ? 0xa9fe : 0xc0e6) : (emulation ? 0xc0f4 : 0xc0e4);
    int cycles = emulation ? 7 : 8;
    unsigned pushed = emulation ? 3 : 4;
    for (unsigned i = 0; i < sizeof g_ram; ++i) g_ram[i] = 0x55;
    for (unsigned i = 0; i < sizeof bus_data; ++i) bus_data[i] = (uint8_t)(i * 13 + 9);
    native_count = fallback_count = 0;
    rr_snes_native_set_enabled(native);
    int used = interp816_runOpcode(&cpu);
    uint64_t counted = native ? native_count : fallback_count;
    /* Stack after the pushes [K,] PCH, PCL, P: the return address follows the signature byte. */
    const uint8_t *top = g_ram + 0x1f8;
    const uint8_t low = (uint8_t)(opcode * 8 + 2);
    bool stacked = emulation ? (top[0] == 0x80 && top[-1] == low)
                             : (top[0] == 0x00 && top[-1] == 0x80 && top[-2] == low);
    if (counted != 1 || used != cycles || cpu.pc != vector || cpu.k != 0 || cpu.sp != 0x1f8 - pushed ||
        !cpu.i || cpu.d || !stacked) {
        fprintf(stderr, "Software interrupt %02x e=%d %s: cycles %d (want %d), pc %04x (want %04x), sp %04x, k %02x\n",
                opcode, emulation, native ? "native" : "reference", used, cycles, cpu.pc, vector, cpu.sp, cpu.k);
        exit(9);
    }
}

int main(void) {
    memcpy(cartridge, fixture_rom, sizeof cartridge);
    cart.type = FIXTURE_CART_TYPE; cart.rom = cartridge; cart.romSize = sizeof cartridge;
    cart.romImageSize = FIXTURE_IMAGE_BYTES;
    machine.cart = &cart;
    for (unsigned opcode = 0; opcode < 3; opcode += 2)
        for (unsigned emulation = 0; emulation < 2; ++emulation)
            for (unsigned native = 0; native < 2; ++native)
                check_software_interrupt(opcode, emulation, native);
    return rr_snes_native_base_checks();
}
