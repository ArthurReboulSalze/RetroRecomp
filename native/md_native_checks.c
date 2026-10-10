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
uint32_t rr_md_cpu_stopped;
#include "md_cpu_snapshot_fixture.h"
static int force_reference;
static unsigned fallback, cases;
static unsigned bus_reads;
static unsigned watched_writes;
static uint32_t write_addresses[4];
static int watch_writes;
int genesis_force_interp(void) { return force_reference; }
void rr16_note_interpreted(void) { ++fallback; }
void rr16_note_rom_fallback(uint32_t pc) { (void)pc; }
void rr16_note_ram_instruction(const M68KInstr *ins) { (void)ins; }
void glue_check_vblank(void) {}
int game_instruction_hook_site(uint32_t pc) { (void)pc; return 0; }
int genesis_game_instruction_hook(uint32_t pc) { (void)pc; return 0; }
uint8_t m68k_read8(uint32_t pc) {
    ++bus_reads;
    pc &= 0xffffffu;
    return pc >= 0xff0000u ? g_ram[pc & 65535] : pc < sizeof g_rom ? g_rom[pc] : 0;
}
uint16_t m68k_read16(uint32_t pc) { return ((unsigned)m68k_read8(pc) << 8) | m68k_read8(pc + 1); }
uint32_t m68k_read32(uint32_t pc) { return ((uint32_t)m68k_read16(pc) << 16) | m68k_read16(pc + 2); }
void m68k_write8(uint32_t pc, uint8_t v) {
    pc &= 0xffffffu;
    if (watch_writes) {
        if (watched_writes < 4) write_addresses[watched_writes] = pc;
        ++watched_writes;
    }
    if (pc >= 0xff0000u) g_ram[pc & 65535] = v;
}
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
    m68k_write16(0xff8080, 0x4e40);
    m68k_write16(0xfffff4, 0x4ef9); m68k_write32(0xfffff6, 0x800);
    m68k_write16(0xfffffa, 0x4ef9); m68k_write32(0xfffffc, 0x800);
    if (pc == 0xfffffe) m68k_write16(pc, 0x4e71);
    M68KState initial = g_cpu; memcpy(before, g_ram, sizeof before);
    force_reference = 0; fallback = 0; rr_md_cpu_stopped = 0;
    M68kiStatus ns = m68k_interp_step();
    uint32_t native_stop = rr_md_cpu_stopped;
    M68KState native = g_cpu; memcpy(native_ram, g_ram, sizeof native_ram);
    REQUIRE(fallback == 0, "covered instruction must execute native body");
    g_cpu = initial; memcpy(g_ram, before, sizeof before);
    force_reference = 1; rr_md_cpu_stopped = 0;
    M68kiStatus rs = m68k_interp_step();
    if (ns != rs || native_stop != rr_md_cpu_stopped || memcmp(&native, &g_cpu, sizeof native) || memcmp(native_ram, g_ram, sizeof g_ram)) {
        fprintf(stderr, "CPU mismatch pc=%06x seed=%u native=%d reference=%d\n", pc, seed, ns, rs); exit(1);
    }
    ++cases;
}
/* Independent byte lanes, ordering, register and clock expectations from
 * the Motorola programming manual, beyond the shared reference semantics. */
static void movep_checks(void) {
    for (int reference = 0; reference <= 1; ++reference) {
        force_reference = reference;
        for (unsigned form = 0; form < 4; ++form) {
            unsigned count = (form & 1) ? 4 : 2;
            for (unsigned odd = 0; odd < 2; ++odd) {
                memset(&g_cpu, 0, sizeof g_cpu); memset(g_ram, 0x5a, sizeof g_ram);
                g_cpu.PC = TEST_MOVEP + form * 16; g_cpu.A[0] = 0xff0110 + odd;
                g_cpu.D[0] = 0x89abcdef; g_cpu.SR = 0xa71f;
                uint32_t address = g_cpu.A[0] - 16;
                g_ram[address & 65535] = 0x12; g_ram[(address + 2) & 65535] = 0x34;
                g_ram[(address + 4) & 65535] = 0x56; g_ram[(address + 6) & 65535] = 0x78;
                watched_writes = 0; watch_writes = 1; fallback = 0;
                g_cycle_accumulator = g_audio_cycle_counter = 0;
                REQUIRE(m68k_interp_step() == M68KI_OK, "MOVEP executes");
                watch_writes = 0;
                REQUIRE(g_cpu.PC == TEST_MOVEP + form * 16 + 4 && g_cpu.A[0] == 0xff0110 + odd
                        && g_cpu.SR == 0xa71f && fallback == (unsigned)reference,
                        "MOVEP preserves address and flags, advances past displacement");
                REQUIRE(g_audio_cycle_counter == (count == 2 ? 16 : 24)
                        && g_cycle_accumulator == g_audio_cycle_counter, "MOVEP takes 16/24 clocks");
                if (form < 2) {
                    REQUIRE(g_cpu.D[0] == (count == 2 ? 0x89ab1234u : 0x12345678u)
                            && !watched_writes, "MOVEP load and word upper-half preservation");
                } else {
                    REQUIRE(g_cpu.D[0] == 0x89abcdef && watched_writes == count, "MOVEP store byte count");
                    for (unsigned i = 0; i < count; ++i)
                        REQUIRE(write_addresses[i] == address + i * 2
                                && g_ram[(address + i * 2) & 65535] ==
                                   (uint8_t)(0x89abcdefu >> ((count - 1 - i) * 8))
                                && g_ram[(address + i * 2 + 1) & 65535] == 0x5a,
                                "MOVEP writes big-endian bytes in order, preserving intervening lanes");
                }
            }
        }
        memset(&g_cpu, 0, sizeof g_cpu);
        g_cpu.PC = TEST_MOVEP + 48; g_cpu.SR = 0x2015;
        g_cpu.A[0] = 0x0100000d; g_cpu.D[0] = 0x12345678;
        watched_writes = 0; watch_writes = 1;
        REQUIRE(m68k_interp_step() == M68KI_OK, "MOVEP wrapped peripheral address");
        watch_writes = 0;
        REQUIRE(watched_writes == 4 && write_addresses[0] == 0xfffffd
                && write_addresses[1] == 0xffffff && write_addresses[2] == 1 && write_addresses[3] == 3
                && g_cpu.A[0] == 0x0100000d && g_cpu.SR == 0x2015,
                "MOVEP sign-extends displacement and wraps the 24-bit bus, keeping 32-bit An");
    }
}
static void stop_checks(void) {
    for (int reference = 0; reference <= 1; ++reference) {
        force_reference = reference; rr_md_cpu_stopped = 0;
        memset(&g_cpu, 0, sizeof g_cpu);
        g_cpu.PC = TEST_STOP; g_cpu.SR = 0x2700; g_cpu.A[7] = 0xffc000; g_cpu.USP = 0xffd000;
        g_cycle_accumulator = g_audio_cycle_counter = 0; g_native_insn_count = 0; fallback = 0;
        REQUIRE(m68k_interp_step() == M68KI_OK && rr_md_cpu_stopped == 1
                && g_cpu.PC == TEST_STOP + 4 && g_cpu.SR == 0x2500,
                "STOP loads immediate SR and retains the following PC");
        REQUIRE(g_audio_cycle_counter == 4 && g_native_insn_count == 1 && fallback == (unsigned)reference,
                "STOP retires once in four clocks, through native or requested reference");
        unsigned reads = bus_reads;
        for (unsigned n = 0; n < 100; ++n) REQUIRE(m68k_interp_step() == M68KI_OK, "STOP clock wait");
        REQUIRE(g_audio_cycle_counter == 404 && g_native_insn_count == 1
                && fallback == (unsigned)reference && g_cpu.PC == TEST_STOP + 4 && bus_reads == reads,
                "STOP wait advances time without fetching or inventing retired instructions");
        rr_md_exception_frame(g_cpu.SR, g_cpu.PC, 0x2600);
        REQUIRE(rr_md_cpu_stopped == 0 && m68k_read32(g_cpu.A[7] + 2) == TEST_STOP + 4,
                "accepted IRQ wakes STOP with the following PC in its frame");
        g_cpu.PC = TEST_RTE;
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_STOP + 4
                && g_cpu.SR == 0x2500 && g_cpu.A[7] == 0xffc000 && !rr_md_cpu_stopped,
                "IRQ RTE resumes after STOP without stopping again");
        g_cpu.PC = TEST_STOP_USER; g_cpu.SR = 0x2700;
        REQUIRE(m68k_interp_step() == M68KI_OK && rr_md_cpu_stopped && g_cpu.SR == 0x0700
                && g_cpu.A[7] == 0xffd000 && rr_md_supervisor_sp() == 0xffc000,
                "STOP can select user mode before entering its stopped state");
        rr_md_exception_frame(g_cpu.SR, g_cpu.PC, 0x2700);
        g_cpu.PC = TEST_RTE;
        REQUIRE(m68k_interp_step() == M68KI_OK && !rr_md_cpu_stopped && g_cpu.SR == 0x0700
                && g_cpu.A[7] == 0xffd000, "exception return restores the STOP-selected user stack");
        g_cpu.PC = TEST_STOP; M68KState before = g_cpu;
        REQUIRE(m68k_interp_step() == M68KI_HALT_UNIMPL && !rr_md_cpu_stopped
                && !memcmp(&before, &g_cpu, sizeof before), "user STOP privilege violation refuses unchanged");
    }
    uint8_t image[128]; memset(&g_cpu, 0, sizeof g_cpu);
    g_cpu.SR = 0x0305; g_cpu.A[7] = 0xffd000; g_cpu.USP = 0xffc000; g_cpu.PC = TEST_STOP + 4;
    rr_md_cpu_stopped = 1; M68KState original = g_cpu;
    REQUIRE(sec_cpu_save(NULL, 0) == sizeof g_cpu + 4
            && sec_cpu_save(image, sizeof g_cpu) == 0,
            "snapshot bounds include the STOP latch");
    size_t length = sec_cpu_save(image, sizeof image);
    memset(&g_cpu, 0, sizeof g_cpu); rr_md_cpu_stopped = 0;
    REQUIRE(sec_cpu_load(image, length) && rr_md_cpu_stopped == 1
            && !memcmp(&g_cpu, &original, sizeof g_cpu)
            && rr_md_supervisor_sp() == 0xffc000 && rr_md_user_sp() == 0xffd000,
            "snapshot restores STOP and both mode stacks");
    uint32_t invalid = 2; memcpy(image + sizeof g_cpu, &invalid, sizeof invalid);
    REQUIRE(!sec_cpu_load(image, length) && rr_md_cpu_stopped == 1
            && !memcmp(&g_cpu, &original, sizeof g_cpu), "invalid STOP latch rejects without mutation");
    REQUIRE(!sec_cpu_load(image, length - 1) && !sec_cpu_load(image, length + 1),
            "snapshot rejects incomplete or extra CPU bytes");
    rr_md_cpu_stopped = 0;
}
/* Independent Motorola exception-frame and timing values, not just agreement
 * between two adapters that share semantic helpers. TRAP vectors 32..47. */
static void trap_checks(void) {
    for (int reference = 0; reference <= 1; ++reference) {
        force_reference = reference;
        for (unsigned vector = 0; vector < 16; ++vector) {
            memset(&g_cpu, 0, sizeof g_cpu); memset(g_ram, 0, sizeof g_ram);
            uint32_t pc = TEST_TRAP + vector * 16;
            g_cpu.PC = pc; g_cpu.A[7] = 0xffc000; g_cpu.USP = 0xffd000; g_cpu.SR = 0xa315;
            g_cycle_accumulator = g_audio_cycle_counter = 0;
            fallback = 0;
            REQUIRE(m68k_interp_step() == M68KI_OK, "TRAP enters vector");
            REQUIRE(g_cpu.PC == TEST_RTE && g_cpu.A[7] == 0xffbffa && g_cpu.SR == 0x2315,
                    "TRAP selects vector and clears trace without changing IRQ mask or CCR");
            REQUIRE(m68k_read16(0xffbffa) == 0xa315 && m68k_read32(0xffbffc) == pc + 2,
                    "TRAP frame contains old SR and following instruction PC");
            REQUIRE(g_cpu.USP == 0xffd000 && g_audio_cycle_counter == 34 && g_cycle_accumulator == 34,
                    "TRAP preserves USP and takes 34 clocks");
            REQUIRE(fallback == (unsigned)reference, "TRAP uses covered native body or explicit reference");
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == pc + 2 && g_cpu.SR == 0xa315
                    && g_cpu.A[7] == 0xffc000, "RTE resumes after TRAP with original stack and status");
        }
        /* Trap from a RAM stub and a nested exception must use the same stack. */
        g_cpu.PC = 0xff8080; g_cpu.A[7] = 0; g_cpu.SR = 0x2611;
        m68k_write16(0xff8080, 0x4e40);
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.A[7] == 0xfffffffa,
                "RAM TRAP frame wraps zero stack onto work RAM");
        g_cpu.PC = TEST_TRAP + 16;
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.A[7] == 0xfffffff4,
                "nested TRAP stacks a second frame");
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.A[7] == 0xfffffffa
                && g_cpu.PC == TEST_TRAP + 18, "first RTE pops only the inner frame");
        g_cpu.PC = TEST_RTE;
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == 0xff8082 && g_cpu.A[7] == 0
                && g_cpu.SR == 0x2611, "second RTE resumes the RAM caller");
        /* Enter user mode with each legal SR-writing instruction. Neither
         * stack contents nor the complete 32-bit stack registers are lost. */
        const uint32_t transitions[] = {TEST_SR_AND, TEST_SR_MOVE, TEST_SR_EOR};
        for (unsigned n = 0; n < sizeof transitions / sizeof *transitions; ++n) {
            memset(&g_cpu, 0, sizeof g_cpu); memset(g_ram, 0, sizeof g_ram);
            g_cpu.PC = transitions[n]; g_cpu.SR = 0x2315;
            g_cpu.A[7] = 0xffffffc0u; g_cpu.USP = 0xffffd000u;
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.SR == 0x0315
                    && g_cpu.A[7] == 0xffffd000u && rr_md_supervisor_sp() == 0xffffffc0u,
                    "SR mode transition selects USP and retains SSP");
            g_cpu.PC = TEST_TRAP;
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_RTE
                    && g_cpu.SR == 0x2315 && g_cpu.A[7] == 0xffffffbau
                    && rr_md_user_sp() == 0xffffd000u,
                    "user TRAP switches to the supervisor stack before saving its frame");
            REQUIRE(m68k_read16(0xffffffbau) == 0x0315
                    && m68k_read32(0xffffffbcu) == TEST_TRAP + 2
                    && m68k_read32(0xffffcffcu) == 0,
                    "user TRAP saves old status and following PC on SSP, leaving USP untouched");
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_TRAP + 2
                    && g_cpu.SR == 0x0315 && g_cpu.A[7] == 0xffffd000u
                    && rr_md_supervisor_sp() == 0xffffffc0u,
                    "RTE reads both frame fields on SSP before returning to user mode");
            /* The IRQ adapter uses this exact frame helper for levels 2/4/6. */
            for (unsigned level = 2; level <= 6; level += 2) {
                rr_md_exception_frame(g_cpu.SR, 0x876, (uint16_t)(0x2000u | level << 8 | 0x15));
                REQUIRE(g_cpu.A[7] == 0xffffffbau && rr_md_user_sp() == 0xffffd000u
                        && m68k_read16(g_cpu.A[7]) == 0x0315 && m68k_read32(g_cpu.A[7] + 2) == 0x876,
                        "IRQ from user mode saves an exception frame on SSP");
                g_cpu.PC = TEST_RTE;
                REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.A[7] == 0xffffd000u
                        && g_cpu.SR == 0x0315 && g_cpu.PC == 0x876,
                        "IRQ RTE restores user mode and stack");
            }
            /* Do not silently permit still-unimplemented privilege traps. */
            const uint32_t privileged[] = {TEST_RTE, TEST_SR_MOVE, TEST_SR_AND, TEST_SR_EOR, TEST_USP_MOVE};
            for (unsigned p = 0; p < sizeof privileged / sizeof *privileged; ++p) {
                g_cpu.PC = privileged[p]; M68KState before = g_cpu;
                REQUIRE(m68k_interp_step() == M68KI_HALT_UNIMPL && !memcmp(&g_cpu, &before, sizeof before),
                        "unsupported privilege violation refuses without changing CPU state");
            }
        }
    }
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
    for (int reference = 0; reference <= 1; ++reference) {
        force_reference = reference;
        g_cpu.PC = TEST_JSR; g_cpu.A[7] = 0;
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.A[7] == 0xfffffffcu
                && m68k_read32(0xfffffcu) == TEST_JSR + 6,
                "zero initial SSP wraps a predecrement push to work RAM");
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.A[7] == 0 && g_cpu.PC == TEST_JSR + 6,
                "wrapped stack return restores the full address register");
    }
    force_reference = 0;
    g_cpu.PC = TEST_RTE; g_cpu.A[7] = 0xffbffau; g_cpu.SR = 0x2300;
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
    /* Real interrupt stubs can occupy the very last six bytes of work RAM. */
    M68KInstr tail = {0}; tail.addr = 0xfffffau; tail.word_count = 3; tail.byte_length = 6;
    REQUIRE(rr_md_ram_instruction_recordable(&tail), "final six-byte RAM instruction can be learned");
    tail.addr = 0xfffffeu; tail.word_count = 1; tail.byte_length = 2;
    REQUIRE(rr_md_ram_instruction_recordable(&tail), "final RAM word can be learned");
    tail.word_count = 2; tail.byte_length = 4;
    REQUIRE(!rr_md_ram_instruction_recordable(&tail), "RAM observation must not cross bus end");
    tail.addr = 0xff8000u; tail.byte_length = 2;
    REQUIRE(!rr_md_ram_instruction_recordable(&tail), "inconsistent decoded lengths rejected");
    g_cpu.PC = 0xfffffa; m68k_write16(g_cpu.PC, 0x4ef9); m68k_write32(g_cpu.PC + 2, 0x800);
    fallback = 0;
    REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == 0x800 && !fallback,
            "final RAM interrupt jump executes a native body");
    g_cpu.PC = 0xfffffa; m68k_write32(g_cpu.PC + 2, 0x822); fallback = 0;
    REQUIRE(rr_md_native_lookup(g_cpu.PC) == NULL, "last operand word participates in the live guard");
    REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == 0x822 && fallback == 1,
            "modified final RAM operand uses reference fallback");
}
/* These tests use independent boundary values from the documented clocks,
 * including flag clears that must not reload a running counter. */
#include "md_ym_timers.h"
static void timer_checks(void) {
    RrMdYmTimers t = {0};
    rr_md_ym_write(&t, 0x24, 0xff, 0); rr_md_ym_write(&t, 0x25, 0xff, 0);
    REQUIRE(t.a == 1023, "timer A is ten bits");
    rr_md_ym_write(&t, 0x27, 0x05, 0);
    rr_md_ym_advance(&t, 1007); REQUIRE(t.status == 0, "A before first overflow");
    rr_md_ym_advance(&t, 1008); REQUIRE(t.status == 1, "A at first overflow");
    rr_md_ym_write(&t, 0x27, 0x15, 1500);
    REQUIRE(t.status == 0 && t.deadline[0] == 2016, "clear A flag without postponing overflow");
    rr_md_ym_advance(&t, 2016); REQUIRE(t.status == 1, "A continues after flag clear");
    rr_md_ym_write(&t, 0x24, 0, 2016); rr_md_ym_write(&t, 0x25, 0, 2016);
    REQUIRE(t.deadline[0] == 3024, "frequency write preserves current counter");
    rr_md_ym_write(&t, 0x27, 0x15, 2500); rr_md_ym_advance(&t, 3024);
    REQUIRE(t.deadline[0] == 3024 + 1024 * 1008ull, "new A period used at reload");
    rr_md_ym_write(&t, 0x27, 0x10, 3024); rr_md_ym_advance(&t, 100000000);
    REQUIRE(!t.running[0] && t.status == 0, "stopped A cannot overflow");
    memset(&t, 0, sizeof t);
    rr_md_ym_write(&t, 0x26, 0xff, 0); rr_md_ym_write(&t, 0x27, 0x02, 0);
    rr_md_ym_advance(&t, 16128); REQUIRE(t.status == 0, "B flag disabled but timer runs");
    rr_md_ym_write(&t, 0x27, 0x0a, 20000);
    REQUIRE(t.deadline[1] == 32256, "enabling B flag does not reload");
    rr_md_ym_advance(&t, 32255); REQUIRE(t.status == 0, "B before enabled overflow");
    rr_md_ym_advance(&t, 32256); REQUIRE(t.status == 2, "B overflow after sixteen FM ticks");
    rr_md_ym_write(&t, 0x27, 0x2a, 40000);
    REQUIRE(t.status == 0 && t.deadline[1] == 48384, "clear B without reload");
    rr_md_ym_advance(&t, 48384 + 16128ull * 100000000);
    REQUIRE(t.status == 2 && t.deadline[1] > 48384 + 16128ull * 100000000,
            "bounded 64-bit timer catch-up");
    memset(&t, 0, sizeof t);
    rr_md_ym_write(&t, 0x24, 0xff, 0); rr_md_ym_write(&t, 0x25, 3, 0);
    rr_md_ym_write(&t, 0x26, 0xff, 0); rr_md_ym_write(&t, 0x27, 0x0f, 0);
    rr_md_ym_advance(&t, 16128); REQUIRE(t.status == 3, "both flags coexist");
    rr_md_ym_write(&t, 0x27, 0x1f, 16128); REQUIRE(t.status == 2, "A reset preserves B flag");
    rr_md_ym_write(&t, 0x27, 0x2f, 16128); REQUIRE(t.status == 0, "B reset preserves A state");
}
int main(void) {
    memcpy(g_rom, fixture_rom, sizeof fixture_rom);
    for (unsigned i = 0; i < sizeof fixture_pcs / sizeof *fixture_pcs; ++i)
        for (unsigned seed = 1; seed <= 64; ++seed) differential(fixture_pcs[i], seed);
    for (unsigned seed = 1; seed <= 64; ++seed) differential(0xff8000, seed);
    for (unsigned seed = 1; seed <= 64; ++seed) differential(0xff8040, seed);
    for (unsigned seed = 1; seed <= 64; ++seed) differential(0xff8060, seed);
    for (unsigned seed = 1; seed <= 64; ++seed) differential(0xff8080, seed);
    for (unsigned seed = 1; seed <= 64; ++seed) differential(0xfffff4, seed);
    for (unsigned seed = 1; seed <= 64; ++seed) differential(0xfffffa, seed);
    for (unsigned seed = 1; seed <= 64; ++seed) differential(0xfffffe, seed);
    architectural_checks();
    movep_checks();
    trap_checks();
    stop_checks();
    timer_checks();
    printf("{\"instruction_state_comparisons\":%u,\"architecture_checks\":\"passed\",\"movep_checks\":\"passed\",\"ym_timer_checks\":\"passed\",\"passed\":true}\n", cases);
    return 0;
}
