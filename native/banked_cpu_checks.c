/* Differential one-instruction checks against the pinned reference CPU.
 * This translation unit owns the glue, so it can reset bus state between
 * native and reference execution without adding a public save-state API. */
#include "runtime_glue.c"
#include <stdio.h>

static unsigned errors[7][256], checks, misses;
static uint8_t reference_ram[8192];
static Z80State initial_cpu(uint16_t pc, unsigned seed) {
    Z80State s = {0}; s.pc = pc; s.sp = 0xDFF0;
    s.a = seed ? 0xA5 : 0x31; s.f = seed ? 0xFF : 0;
    s.b = 2; s.c = 0x13; s.d = 0xC5; s.e = 0x10; s.h = 0xC2; s.l = 0x10;
    s.a_ = 0x56; s.f_ = 0x12; s.b_ = 0x23; s.c_ = 0x67; s.d_ = 0x34;
    s.e_ = 0x78; s.h_ = 0x45; s.l_ = 0x89;
    s.ix = 0xC400; s.iy = 0xC600; s.wz = 0x2834; s.i = 0x17; s.r = 0xFD;
    s.iff1 = s.iff2 = true; s.im = 1;
    s.q = seed ? s.f : 0; s.p = seed;
    return s;
}
static void reset_case(Z80State s) {
    g_z80 = s; g_bank[0] = 0; g_bank[1] = 1; g_bank[2] = 2;
    g_frame = 0; g_next_line_cyc = SMS_CYC_PER_LINE; g_sync_deadline = SMS_CYC_PER_LINE;
    g_pad1 = g_pad2 = 0;
    for (unsigned i = 0; i < sizeof(g_ram); ++i) g_ram[i] = (uint8_t)(i*13+7);
    vdp_reset(false); psg_init();
}
static int same_cpu(const Z80State *a, const Z80State *b) {
    return a->pc == b->pc && a->sp == b->sp && a->a == b->a && a->f == b->f &&
        a->b == b->b && a->c == b->c && a->d == b->d && a->e == b->e &&
        a->h == b->h && a->l == b->l && a->a_ == b->a_ && a->f_ == b->f_ &&
        a->b_ == b->b_ && a->c_ == b->c_ && a->d_ == b->d_ && a->e_ == b->e_ &&
        a->h_ == b->h_ && a->l_ == b->l_ && a->ix == b->ix && a->iy == b->iy &&
        a->i == b->i && a->r == b->r && a->iff1 == b->iff1 && a->iff2 == b->iff2 &&
        a->im == b->im && a->halted == b->halted && a->cyc == b->cyc &&
        a->wz == b->wz && a->q == b->q && a->p == b->p && a->ei_block == b->ei_block;
}
static unsigned reference_writes;
static void counted_write(void *u, uint16_t a, uint8_t v) {
    ++reference_writes; hyb_write(u, a, v);
}
static unsigned check_bit_bus(void) {
    unsigned failed = 0, cases = 0;
    /* Assert bus transactions as well as RAM contents. A write of the same
     * value to FFFE changes the mapped bank, so a final-RAM check misses it.
     * BIT b,(HL) and every DD/FD CB BIT alias must remain read-only; RES/SET
     * and rotates must still perform their memory write. */
    for (unsigned family = 0; family < 3; ++family) {
        for (unsigned address = 0xfffc; address <= 0xffff; ++address) {
            for (unsigned bit = 0; bit < 8; ++bit) {
                for (unsigned reg = 0; reg < (family ? 8u : 1u); ++reg) {
                    reset_case(initial_cpu(0xc100, 0));
                    g_z80.h = 0xff; g_z80.l = (uint8_t)address;
                    g_z80.ix = g_z80.iy = (uint16_t)address;
                    g_bank[0] = 5; g_bank[1] = 6; g_bank[2] = 7;
                    unsigned i = 0;
                    if (family) g_ram[0x100 + i++] = family == 1 ? 0xdd : 0xfd;
                    g_ram[0x100 + i++] = 0xcb;
                    if (family) g_ram[0x100 + i++] = 0;
                    g_ram[0x100 + i] = (uint8_t)(0x40 | (bit << 3) | (family ? reg : 6));
                    state_to_hz(); g_hz.pc = g_z80.pc; g_hz.cyc = 0;
                    g_hz.write_byte = counted_write; reference_writes = 0;
                    z80_step(&g_hz); ++cases;
                    if (reference_writes || g_bank[0] != 5 || g_bank[1] != 6 || g_bank[2] != 7 ||
                            g_hz.cyc != (family ? 20u : 12u)) ++failed;
                }
            }
        }
    }
    for (unsigned opcode = 0; opcode < 256; ++opcode) {
        if ((opcode & 7) != 6 || (opcode >> 6) == 1) continue;
        reset_case(initial_cpu(0xc100, 0));
        g_ram[0x100] = 0xcb; g_ram[0x101] = (uint8_t)opcode;
        state_to_hz(); g_hz.pc = g_z80.pc; g_hz.cyc = 0;
        g_hz.write_byte = counted_write; reference_writes = 0;
        z80_step(&g_hz); ++cases;
        if (reference_writes != 1 || g_hz.cyc != 15) ++failed;
    }
    g_hz.write_byte = hyb_write;
    printf("BIT_BUS_CHECKS=%u FAILED=%u\n", cases, failed);
    return failed;
}
static unsigned check_irq_bus(void) {
    unsigned failed = 0;
    for (unsigned line_irq = 0; line_irq < 2; ++line_irq) {
        for (unsigned withdraw = 0; withdraw < 2; ++withdraw) {
            reset_case(initial_cpu(0xc100, 0));
            g_vdp.reg[0] = 0x10; g_vdp.reg[1] = 0x20;
            g_vdp.line_irq = line_irq != 0; g_vdp.frame_irq = line_irq == 0;
            /* DI; [IN A,(VDP status)]; EI; NOP. A withdrawn interrupt must
             * stay withdrawn. A held level must interrupt after EI's delay. */
            unsigned length = 0;
            g_ram[0x100 + length++] = 0xf3;
            if (withdraw) { g_ram[0x100 + length++] = 0xdb; g_ram[0x100 + length++] = 0xbf; }
            g_ram[0x100 + length++] = 0xfb; g_ram[0x100 + length++] = 0;
            state_to_hz(); g_hz.pc = g_z80.pc; g_hz.cyc = 0; reference_cycle_base = 0;
            for (unsigned step = 0; step < (withdraw ? 4u : 3u); ++step) {
                reference_sample_irq(); z80_step(&g_hz);
            }
            if (withdraw ? (g_hz.pc != 0xc100 + length || g_hz.sp != 0xdff0 ||
                            !g_hz.iff1 || g_hz.cyc != 23 || g_hz.int_pending) :
                           (g_hz.pc != 0x38 || g_hz.sp != 0xdfee ||
                            g_hz.iff1 || g_hz.cyc != 25)) ++failed;
        }
    }
    printf("IRQ_BUS_CHECKS=4 FAILED=%u\n", failed);
    return failed;
}
/* The acceptance of an interrupt (banked_after_step) against the reference CPU, state by state. The instruction that precedes it
 * is run by the reference alone (so its flags, WZ, Q and P are the reference's); then the same state takes the interrupt in the
 * native run-loop code and, from the same start, in the reference. Registers, WZ, Q, P, the clock, the stack bytes and the RAM must
 * agree. Covers IM 0, 1 and 2, IFF1, a halted CPU, the PV flag after LD A,I / LD A,R, EI's delay, and each stage of a repeating
 * block instruction (its first, a middle and its last iteration, with the return address that follows). */
static unsigned check_irq_acceptance(void) {
    static const struct { const char *name; uint8_t code[4]; unsigned length; unsigned bc; } program[] = {
        {"NOP", {0x00}, 1, 2}, {"LD A,I", {0xed, 0x57}, 2, 2}, {"LD A,R", {0xed, 0x5f}, 2, 2}, {"EI", {0xfb}, 1, 2},
        {"HALT", {0x76}, 1, 2}, {"RETI", {0xed, 0x4d}, 2, 2},
        {"LDIR bc=3", {0xed, 0xb0}, 2, 3}, {"LDIR bc=1", {0xed, 0xb0}, 2, 1}, {"LDDR bc=2", {0xed, 0xb8}, 2, 2},
        {"CPIR bc=3", {0xed, 0xb1}, 2, 3}, {"CPDR bc=1", {0xed, 0xb9}, 2, 1},
        {"INIR b=2", {0xed, 0xb2}, 2, 0x0213}, {"OTIR b=2", {0xed, 0xb3}, 2, 0x0213},
        {"INDR b=1", {0xed, 0xba}, 2, 0x0113}, {"OTDR b=1", {0xed, 0xbb}, 2, 0x0113}};
    unsigned failed = 0, cases = 0, accepted = 0;
    for (unsigned item = 0; item < sizeof program / sizeof *program; ++item) {
        for (unsigned im = 0; im < 3; ++im) for (unsigned iff = 0; iff < 2; ++iff) for (unsigned halted = 0; halted < 2; ++halted)
        for (unsigned seed = 0; seed < 2; ++seed) for (unsigned reg_i = 0; reg_i < 2; ++reg_i) {
            Z80State start = initial_cpu(0xc100, seed);
            start.im = (uint8_t)im; start.iff1 = start.iff2 = iff != 0; start.halted = halted != 0;
            start.i = reg_i ? 0xc1 : 0x17; start.r = reg_i ? 0x7f : 0xfd;
            if (program[item].bc > 0xff) { start.b = (uint8_t)(program[item].bc >> 8); start.c = (uint8_t)program[item].bc; }
            else { start.b = 0; start.c = (uint8_t)program[item].bc; }
            start.sp = reg_i ? 0xc001 : 0xdff0;
            /* the instruction alone */
            reset_case(start);
            for (unsigned i = 0; i < program[item].length; ++i) g_ram[0x100 + i] = program[item].code[i];
            g_ram[0x102] = 0x00;
            uint8_t after_ram[8192]; Z80State after;
            state_to_hz(); g_hz.pc = 0xc100; g_hz.cyc = 0; g_hz.int_pending = 0;
            z80_step(&g_hz); state_from_hz(); g_z80.pc = g_hz.pc; g_z80.cyc = g_hz.cyc;
            after = g_z80; memcpy(after_ram, g_ram, sizeof after_ram);
            /* the reference takes the interrupt after the same instruction */
            reset_case(start);
            for (unsigned i = 0; i < program[item].length; ++i) g_ram[0x100 + i] = program[item].code[i];
            g_ram[0x102] = 0x00;
            g_vdp.reg[1] = 0x20; g_vdp.frame_irq = true;
            state_to_hz(); g_hz.pc = 0xc100; g_hz.cyc = 0; reference_cycle_base = 0;
            reference_sample_irq(); z80_step(&g_hz); state_from_hz(); g_z80.pc = g_hz.pc; g_z80.cyc = g_hz.cyc;
            Z80State expected = g_z80; uint8_t expected_ram[8192]; memcpy(expected_ram, g_ram, sizeof expected_ram);
            /* the reference keeps EI's delay marker until the next step consumes it; the native loop consumes it at the completion */
            expected.ei_block = 0;
            if (expected.sp != after.sp) ++accepted;   /* the interrupt pushed a return address */
            /* the native loop takes it from the state the instruction left */
            reset_case(start);
            g_z80 = after; memcpy(g_ram, after_ram, sizeof g_ram);
            banked_after_step(1);   /* the level the loop latched at the start of the step */
            ++cases;
            if (item == 0 && !halted && iff && !reg_i) {   /* the stack in RAM: SP $DFF0 */
                /* The documented acceptance after a NOP, from the Zilog manual and the Sega documents rather than from the
                 * reference: 13 clocks (19 in IM 2) after the NOP's 4, the return address pushed low byte first, two refresh
                 * increments, IFF1 and IFF2 cleared, WZ the new PC. */
                uint16_t vector = sms_read16((uint16_t)((start.i << 8) | 0xff));
                uint16_t target = im == 2 ? vector : 0x0038;
                uint8_t refresh = (uint8_t)((start.r & 0x80) | ((start.r + 2) & 0x7f));
                uint16_t sp = (uint16_t)(start.sp - 2);
                if (g_z80.pc != target || g_z80.wz != target || g_z80.sp != sp || g_z80.r != refresh || g_z80.iff1 || g_z80.iff2 ||
                        g_z80.cyc != 4u + (im == 2 ? 19u : 13u) ||
                        g_ram[sp & 0x1fff] != 0x01 || g_ram[(sp + 1) & 0x1fff] != 0xc1) {
                    ++failed;
                    printf("IRQ FAIL documented values after NOP im=%u: pc=%04X sp=%04X r=%02X cyc=%llu\n", im, g_z80.pc, g_z80.sp,
                           g_z80.r, (unsigned long long)g_z80.cyc);
                }
            }
            if (!same_cpu(&g_z80, &expected) || memcmp(g_ram, expected_ram, sizeof g_ram)) {
                if (failed++ < 12)
                    printf("IRQ FAIL %s im=%u iff=%u halted=%u seed=%u: native pc=%04X sp=%04X af=%04X r=%02X cyc=%llu wz=%04X q=%02X p=%u iff1=%u ei=%u / reference pc=%04X sp=%04X af=%04X r=%02X cyc=%llu wz=%04X q=%02X p=%u iff1=%u ei=%u ram=%d\n",
                        program[item].name, im, iff, halted, seed, g_z80.pc, g_z80.sp, z80_af(&g_z80), g_z80.r,
                        (unsigned long long)g_z80.cyc, g_z80.wz, g_z80.q, g_z80.p, g_z80.iff1, g_z80.ei_block,
                        expected.pc, expected.sp, z80_af(&expected), expected.r, (unsigned long long)expected.cyc,
                        expected.wz, expected.q, expected.p, expected.iff1, expected.ei_block,
                        memcmp(g_ram, expected_ram, sizeof g_ram) != 0);
            }
        }
    }
    printf("IRQ_ACCEPT_CHECKS=%u ACCEPTED=%u FAILED=%u\n", cases, accepted, failed);
    return failed;
}
int main(void) {
    if (!glue_load_rom("embedded")) return 2;
    z80_init(&g_hz); g_hz_init = true;
    g_hz.read_byte = hyb_read; g_hz.write_byte = hyb_write;
    g_hz.port_in = hyb_in; g_hz.port_out = hyb_out;
    /* Test positions in each physical bank, mapped into slot 2. Avoid seams
     * here: the authored integration tests separately exercise those cases. */
    unsigned period = (unsigned)((g_rom_size + 16383) / 16384);
    for (unsigned bank = 0; bank < period; ++bank) {
        for (unsigned off = 0; off < 0x3FFD; ++off) {
            size_t physical = bank*0x4000u+off; if (physical >= g_rom_size) break;
            uint16_t pc = (uint16_t)(0x8000+off);
            unsigned pfx = 0, opcode = g_rom[physical];
            if (opcode == 0xCB) { pfx = 1; opcode = g_rom[(physical+1)%g_rom_size]; }
            else if (opcode == 0xED) { pfx = 2; opcode = g_rom[(physical+1)%g_rom_size]; }
            else if (opcode == 0xDD || opcode == 0xFD) {
                pfx = opcode == 0xDD ? 3 : 4; opcode = g_rom[(physical+1)%g_rom_size];
                if (opcode == 0xCB) { pfx += 2; opcode = g_rom[(physical+3)%g_rom_size]; }
            }
            for (unsigned seed = 0; seed < 2; ++seed) {
                Z80State initial = initial_cpu(pc, seed);
                reset_case(initial); g_bank[2] = bank;
                int covered;
                do { covered = game_banked_step(0, 1, (uint8_t)bank); } while (covered >= 3);
                if (!covered) { misses++; continue; }
                Z80State native = g_z80;
                uint8_t native_ram[8192]; memcpy(native_ram, g_ram, sizeof native_ram);
                reset_case(initial); g_bank[2] = bank;
                state_to_hz(); g_hz.pc = pc; g_hz.cyc = 0;
                z80_step(&g_hz); state_from_hz(); g_z80.pc = g_hz.pc; g_z80.cyc = g_hz.cyc;
                checks++;
                if (!same_cpu(&native, &g_z80) || memcmp(native_ram, g_ram, sizeof native_ram)) {
                    if (errors[pfx][opcode]++ == 0) {
                        printf("FAIL bank=%u pc=%04X pfx=%u op=%02X native/ref: pc=%04X/%04X af=%04X/%04X hl=%04X/%04X r=%02X/%02X cyc=%llu/%llu ram=%d wz=%04X/%04X q=%02X/%02X p=%u/%u ei=%u/%u\n",
                            bank, pc, pfx, opcode, native.pc, g_z80.pc, z80_af(&native), z80_af(&g_z80), z80_hl(&native), z80_hl(&g_z80),
                            native.r, g_z80.r, (unsigned long long)native.cyc, (unsigned long long)g_z80.cyc,
                            memcmp(native_ram, g_ram, sizeof native_ram) != 0, native.wz, g_z80.wz,
                            native.q, g_z80.q, native.p, g_z80.p, native.ei_block, g_z80.ei_block);
                    }
                }
            }
        }
    }
    unsigned kinds = 0, failed = 0;
    for (unsigned p = 0; p < 7; ++p) for (unsigned op = 0; op < 256; ++op) {
        if (errors[p][op]) { kinds++; failed += errors[p][op]; }
    }
    printf("CHECKS=%u MISSES=%u FAILED=%u OPCODE_KINDS=%u\n", checks, misses, failed, kinds);
    failed += check_bit_bus();
    failed += check_irq_bus();
    failed += check_irq_acceptance();
    return failed || misses ? 1 : 0;
}
