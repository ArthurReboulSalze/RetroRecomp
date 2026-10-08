/* Authored CPU fixtures. No game assets; no SDL, video capture or network. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "md_native_steps.h"
#include "fixture_data.h"

M68KState g_cpu;
uint8_t g_rom[0x400000], g_ram[0x10000];
uint64_t g_native_insn_count;
uint32_t g_cycle_accumulator, g_audio_cycle_counter, g_vblank_threshold = 0xffffffffu;
int g_rte_pending;
static int force_reference;
static unsigned fallback, cases;
int genesis_force_interp(void) { return force_reference; }
void rr16_note_interpreted(void) { ++fallback; }
void rr16_note_rom_fallback(uint32_t pc) { (void)pc; }
void rr16_note_ram_instruction(const M68KInstr *ins) { (void)ins; }
void glue_check_vblank(void) {}
int game_instruction_hook_site(uint32_t pc) { (void)pc; return 0; }
int genesis_game_instruction_hook(uint32_t pc) { (void)pc; return 0; }
uint8_t m68k_read8(uint32_t pc) {
    pc &= 0xffffffu;
    return pc >= 0xff0000u ? g_ram[pc & 65535] : pc < sizeof g_rom ? g_rom[pc] : 0;
}
uint16_t m68k_read16(uint32_t pc) { return ((unsigned)m68k_read8(pc) << 8) | m68k_read8(pc + 1); }
uint32_t m68k_read32(uint32_t pc) { return ((uint32_t)m68k_read16(pc) << 16) | m68k_read16(pc + 2); }
void m68k_write8(uint32_t pc, uint8_t v) { pc &= 0xffffffu; if (pc >= 0xff0000u) g_ram[pc & 65535] = v; }
void m68k_write16(uint32_t pc, uint16_t v) { m68k_write8(pc, v >> 8); m68k_write8(pc + 1, v); }
void m68k_write32(uint32_t pc, uint32_t v) { m68k_write16(pc, v >> 16); m68k_write16(pc + 2, v); }

#define REQUIRE(ok, name) do { if (!(ok)) { fprintf(stderr, "FAIL: %s\n", name); exit(1); } } while (0)
static uint32_t random_word(uint32_t *seed) { *seed = *seed * 1664525u + 1013904223u; return *seed; }
static void differential(uint32_t pc, unsigned seed) {
    static uint8_t before[65536], native_ram[65536];
    memset(&g_cpu, 0, sizeof g_cpu);
    uint32_t rng = seed;
    for (int i = 0; i < 8; ++i) {
        g_cpu.D[i] = random_word(&rng);
        g_cpu.A[i] = 0xff0400u + i * 0x400u;
    }
    g_cpu.A[7] = 0xffc000u; g_cpu.USP = 0xffe000u;
    g_cpu.SR = 0x2000u | (random_word(&rng) & 31u); g_cpu.PC = pc;
    for (unsigned i = 0; i < sizeof g_ram; ++i) g_ram[i] = (uint8_t)random_word(&rng);
    /* Two byte-guarded variants at the same RAM PC. */
    m68k_write16(0xff8000, seed & 1 ? 0x70ff : 0x7001);
    m68k_write32(0xff8040, 0x4eba0008u);
    m68k_write16(0xff8060, 0x4eb9); m68k_write32(0xff8062, 0x800);
    M68KState initial = g_cpu; memcpy(before, g_ram, sizeof before);
    force_reference = 0; fallback = 0;
    M68kiStatus ns = m68k_interp_step();
    M68KState native = g_cpu; memcpy(native_ram, g_ram, sizeof native_ram);
    REQUIRE(fallback == 0, "covered instruction must execute native body");
    g_cpu = initial; memcpy(g_ram, before, sizeof before);
    force_reference = 1;
    M68kiStatus rs = m68k_interp_step();
    if (ns != rs || memcmp(&native, &g_cpu, sizeof native) || memcmp(native_ram, g_ram, sizeof g_ram)) {
        fprintf(stderr, "CPU mismatch pc=%06x seed=%u native=%d reference=%d\n", pc, seed, ns, rs); exit(1);
    }
    ++cases;
}
static void architectural_checks(void) {
    memset(g_ram, 0, sizeof g_ram); memset(&g_cpu, 0, sizeof g_cpu); force_reference = 0;
    g_cpu.PC = TEST_JSR; g_cpu.A[7] = 0xffc000u;
    REQUIRE(m68k_interp_step() == M68KI_OK, "JSR");
    REQUIRE(g_cpu.PC == 0x800 && g_cpu.A[7] == 0xffbffcu && m68k_read32(g_cpu.A[7]) == TEST_JSR + 6,
            "JSR stores real return PC on the guest stack");
    /* Callee changes its caller's return address, as several real games do. */
    m68k_write32(g_cpu.A[7], 0x812);
    REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == 0x812 && g_cpu.A[7] == 0xffc000,
            "RTS honours changed stack return address");
    g_cpu.PC = TEST_RTE; g_cpu.A[7] = 0xffbffau;
    m68k_write16(g_cpu.A[7], 0x2305); m68k_write32(g_cpu.A[7] + 2, 0x822);
    REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == 0x822 && g_cpu.SR == 0x2305 && g_cpu.A[7] == 0xffc000,
            "RTE restores real PC and SR exception frame");
    g_cpu.PC = TEST_A7_POST; g_cpu.A[7] = 0xffc000;
    m68k_write8(g_cpu.A[7], 0x80);
    REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.A[7] == 0xffc002 && (g_cpu.D[0] & 255) == 0x80,
            "byte stack postincrement stays word aligned");
    g_cpu.PC = TEST_A7_PRE; g_cpu.A[7] = 0xffc002;
    REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.A[7] == 0xffc000,
            "byte stack predecrement stays word aligned");
    g_cpu.PC = 0xff8000; m68k_write16(g_cpu.PC, 0x7001);
    REQUIRE(rr_md_native_lookup(g_cpu.PC) != NULL, "learned RAM variant found");
    REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.D[0] == 1, "first RAM native variant");
    g_cpu.PC = 0xff8000; m68k_write16(g_cpu.PC, 0x70ff);
    REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.D[0] == 0xffffffffu, "second RAM native variant");
    /* Unseen modification MUST fall back to the current bytes, not frozen C. */
    g_cpu.PC = 0xff8000; m68k_write16(g_cpu.PC, 0x7002); fallback = 0;
    REQUIRE(rr_md_native_lookup(g_cpu.PC) == NULL, "unseen RAM modification rejected");
    REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.D[0] == 2 && fallback == 1,
            "unseen RAM modification uses live interpreter and counts it");
    g_cpu.PC = 0xff8040; g_cpu.A[7] = 0xffc000;
    m68k_write32(g_cpu.PC, 0x4eba0008u);
    REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == 0xff804au && m68k_read32(g_cpu.A[7]) == 0xff8044u,
            "native RAM PC-relative call retains actual guest address");
    g_cpu.PC = 0xff8060; g_cpu.A[7] = 0xffc000;
    m68k_write16(g_cpu.PC, 0x4eb9); m68k_write32(g_cpu.PC + 2, 0x800);
    REQUIRE(rr_md_native_lookup(g_cpu.PC) != NULL, "multiword RAM variant found");
    m68k_write32(g_cpu.PC + 2, 0x822); fallback = 0;
    REQUIRE(rr_md_native_lookup(g_cpu.PC) == NULL, "changed extension operand rejected");
    REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == 0x822 && fallback == 1,
            "changed extension operand executes live bytes");
}
int main(void) {
    memcpy(g_rom, fixture_rom, sizeof fixture_rom);
    for (unsigned i = 0; i < sizeof fixture_pcs / sizeof *fixture_pcs; ++i)
        for (unsigned seed = 1; seed <= 64; ++seed) differential(fixture_pcs[i], seed);
    for (unsigned seed = 1; seed <= 64; ++seed) differential(0xff8000, seed);
    for (unsigned seed = 1; seed <= 64; ++seed) differential(0xff8040, seed);
    for (unsigned seed = 1; seed <= 64; ++seed) differential(0xff8060, seed);
    architectural_checks();
    printf("{\"instruction_state_comparisons\":%u,\"architecture_checks\":\"passed\",\"passed\":true}\n", cases);
    return 0;
}
