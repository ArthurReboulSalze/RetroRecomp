/* The Kabuki fetch of the CPS-1.5 sound CPU, checked on the patched Geolith Z80 core (tools/cps1_kabuki_selftest.py).
 *
 * The sound ROM is read twice: instruction bytes (opcodes and the prefix byte after CB, ED, DD, FD) from the opcode image,
 * everything else from the data image. The two images are different here on purpose (the bytes that must not be read as the
 * other view are junk or harmless), and every scenario gives a result that only the right view produces. The harness is built
 * twice: against the reference core (every instruction interpreted) and with NATIVE against the core that dispatches the
 * translated bodies generated from the same two images (retrorecomp/cps1_codegen.generate_z80 with the opcode image), where
 * every scenario must run as exactly one native step. The bus is flat; nothing here is a board or a game. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "z80.h"
#ifdef NATIVE
#include "cps1_z80_native.h"
int rr_cps1_force_reference, rr_cps1_force_z80_reference;
uint64_t rr_cps1_native_z80, rr_cps1_interpreted_z80;
#endif

static uint8_t op_view[0x8000], data_view[0x10000];

uint8_t rr_cps1_z80_read_op(uint16_t address) { return address < 0x8000 ? op_view[address] : data_view[address]; }
static uint8_t bus_read(void *u, uint16_t a) { (void)u; return data_view[a]; }
static void bus_write(void *u, uint16_t a, uint8_t v) { (void)u; data_view[a] = v; }
static uint8_t port_in(z80 *z, uint16_t a) { (void)z; (void)a; return 0; }
static void port_out(z80 *z, uint16_t a, uint8_t v) { (void)z; (void)a; (void)v; }
#ifdef NATIVE
int rr_cps1_z80_code_location(uint16_t pc, uint32_t *offset) { if (pc >= 0x8000) return 0; *offset = pc; return 1; }
int rr_cps1_z80_code_byte(uint16_t pc, uint8_t *byte) { *byte = data_view[pc]; return 1; }
int rr_cps1_z80_code_byte_m1(uint16_t pc, int m1, uint8_t *byte) { *byte = (m1 && pc < 0x8000) ? op_view[pc] : data_view[pc]; return 1; }
void rr_cps1_z80_note_fallback(uint16_t pc) { (void)pc; ++rr_cps1_interpreted_z80; }
#endif

static int load(const char *path, uint8_t *destination) {
    FILE *file = fopen(path, "rb");
    if (!file) return 0;
    size_t count = fread(destination, 1, 0x8000, file);
    fclose(file);
    return count == 0x8000;
}

static unsigned passed, failed;
static void expect(const char *what, int ok) {
    if (ok) ++passed; else { ++failed; fprintf(stderr, "FAIL: %s\n", what); }
}

static void start(z80 *z, uint16_t pc) {
    z80_init(z);
    z->read_byte = bus_read; z->write_byte = bus_write; z->port_in = port_in; z->port_out = port_out;
    z->pc = pc; z->sp = 0xf000;
}

int main(int argc, char **argv) {
    if (argc != 3 || !load(argv[1], op_view) || !load(argv[2], data_view)) return 2;
    z80 z;
    /* LD A,* : the opcode is read from the opcode view (3E); the operand from the data view (42, not the opcode view's FF) */
    start(&z, 0x0100); z80_step(&z);
    expect("LD A,*: operand from the data view", z.a == 0x42 && z.pc == 0x0102);
    /* ED 44 (NEG): the prefix byte is an instruction fetch too (data view holds 00 00) */
    start(&z, 0x0110); z.a = 1; z80_step(&z);
    expect("NEG: prefix from the opcode view", z.a == 0xff && z.pc == 0x0112);
    /* DD 21 nn (LD IX,nn): prefix and opcode from the opcode view, nn from the data view */
    start(&z, 0x0120); z80_step(&z);
    expect("LD IX,nn", z.ix == 0x1234 && z.pc == 0x0124);
    /* DD CB d op (BIT 0,(IX+d)): DD and CB from the opcode view, d and the last byte from the data view (46); the opcode view
     * holds 77 there, which would be BIT 6 and set Z */
    start(&z, 0x0130); z.ix = 0x4000; data_view[0x4002] = 0x01; z80_step(&z);
    expect("BIT 0,(IX+d): last byte from the data view", !(z.f & 0x40) && z.pc == 0x0134 && data_view[0x4002] == 0x01);
    /* DD 7E d (LD A,(IX+d)) */
    start(&z, 0x0140); z.ix = 0x4000; data_view[0x4003] = 0x99; z80_step(&z);
    expect("LD A,(IX+d)", z.a == 0x99 && z.pc == 0x0143);
#ifdef NATIVE
    expect("five native steps, none interpreted", rr_cps1_native_z80 == 5 && rr_cps1_interpreted_z80 == 0);
#endif
    printf("{\"passed\":%u,\"failed\":%u}\n", passed, failed);
    return failed ? 1 : 0;
}
