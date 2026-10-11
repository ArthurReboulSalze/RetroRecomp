/* Authored CPU fixtures. No game assets; no SDL, video capture or network. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "md_native_steps.h"
#include "md_prefetch.h"
uint32_t rr_md_rom_fetch_offset;
uint32_t rr_md_cart_code_offset(uint32_t pc,const uint16_t *words,unsigned count) { (void)words;(void)count;return pc; }
/* Flat instruction fixtures deliberately exclude the machine bus scheduler. */
void rr_md_cpu_fetch_cycles(unsigned words,int locked) { (void)words;(void)locked; }
unsigned rr_md_cpu_retire_cycles(unsigned cycles) { return cycles; }
unsigned rr_md_cpu_stop_cycles(void) { return 4; }
/* These suites isolate CPU semantics/totals. Dedicated prefetch tests enable bus phases. */
int rr_md_prefetch_active(void) { return 0; }
void rr_md_cpu_iack(unsigned level) { (void)level; }
void rr_md_cpu_idle(unsigned clocks) { (void)clocks; }
void rr_md_cpu_bus_lock(int locked) { (void)locked; }
uint16_t rr_md_read_instruction_word(uint32_t pc) { return m68k_read16(pc); }
#include "fixture_data.h"

M68KState g_cpu;
uint8_t g_rom[0x400000], g_ram[0x10000];
uint64_t g_native_insn_count;
uint32_t g_cycle_accumulator, g_audio_cycle_counter, g_vblank_threshold = 0xffffffffu;
int g_rte_pending;
uint32_t rr_md_cpu_stopped;
#include "md_cpu_snapshot_fixture.h"
static int force_reference;
static unsigned fallback, cases, exception_cases;
static unsigned bus_reads;
static unsigned watched_writes;
static uint32_t write_addresses[4];
static int watch_writes;
int genesis_force_interp(void) { return force_reference; }
void rr16_note_interpreted(void) { ++fallback; }
void rr16_note_rom_fallback(uint32_t pc) { (void)pc; }
void rr16_note_ram_instruction(const M68KInstr *ins) { (void)ins; }
static void (*on_scheduler)(void);
void glue_check_vblank(void) { if (on_scheduler) on_scheduler(); }
int game_instruction_hook_site(uint32_t pc) { (void)pc; return 0; }
int genesis_game_instruction_hook(uint32_t pc) { (void)pc; return 0; }
uint8_t m68k_read8(uint32_t pc) {
    ++bus_reads;
    pc &= 0xffffffu;
    return pc >= 0xe00000u ? g_ram[pc & 65535] : pc < sizeof g_rom ? g_rom[pc] : 0;
}
uint16_t m68k_read16(uint32_t pc) { return ((unsigned)m68k_read8(pc) << 8) | m68k_read8(pc + 1); }
uint32_t m68k_read32(uint32_t pc) { return ((uint32_t)m68k_read16(pc) << 16) | m68k_read16(pc + 2); }
void m68k_write8(uint32_t pc, uint8_t v) {
    pc &= 0xffffffu;
    if (watch_writes) {
        if (watched_writes < 4) write_addresses[watched_writes] = pc;
        ++watched_writes;
    }
    if (pc >= 0xe00000u) g_ram[pc & 65535] = v;
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
    m68k_write16(0xff80a0, 0x6008);
    m68k_write16(0xff80b0, 0x6108);
    m68k_write32(0xff80c0, 0x51c80008);
    m68k_write32(0xff80d0, 0x41fa0008);
    m68k_write16(0xfffff4, 0x4ef9); m68k_write32(0xfffff6, 0x800);
    m68k_write16(0xfffffa, 0x4ef9); m68k_write32(0xfffffc, 0x800);
    if ((pc & 0xffffu) == 0xfffe && pc != 0xfffffe)
        m68k_write32(pc, 0x4eba0008);
    if (pc == 0xfffffe) m68k_write16(pc, 0x4e71);
    M68KState initial = g_cpu; memcpy(before, g_ram, sizeof before);
    force_reference = 0; fallback = 0; rr_md_cpu_stopped = 0;
    M68kiStatus ns = m68k_interp_step();
    uint32_t native_stop = rr_md_cpu_stopped;
    M68KState native = g_cpu; memcpy(native_ram, g_ram, sizeof native_ram);
    if (fallback) fprintf(stderr,"unexpected fallback pc=%06x seed=%u status=%d\n",pc,seed,ns);
    REQUIRE(fallback == 0, "covered instruction must execute native body");
    g_cpu = initial; memcpy(g_ram, before, sizeof before);
    force_reference = 1; rr_md_cpu_stopped = 0;
    M68kiStatus rs = m68k_interp_step();
    if (ns != rs || native_stop != rr_md_cpu_stopped || memcmp(&native, &g_cpu, sizeof native) || memcmp(native_ram, g_ram, sizeof g_ram)) {
        fprintf(stderr, "CPU mismatch pc=%06x seed=%u native=%d reference=%d\n", pc, seed, ns, rs); exit(1);
    }
    ++cases;
}
static void mirror_checks(void) {
    /* Independent PC/stack expectations, besides differential comparisons. */
    for (unsigned base = 0xe00000; base <= 0xff0000; base += 0x10000) {
        for (int reference = 0; reference <= 1; ++reference) {
            force_reference = reference;
            memset(&g_cpu, 0, sizeof g_cpu); memset(g_ram, 0, sizeof g_ram);
            g_cpu.SR = 0x2000; g_cpu.A[7] = base + 0xc000;
            g_cpu.PC = base + 0x8040; m68k_write32(g_cpu.PC, 0x4eba0008);
            fallback = 0;
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == base + 0x804a
                    && m68k_read32(g_cpu.A[7]) == base + 0x8044
                    && fallback == (unsigned)reference, "alias PC-relative JSR and stacked return PC");
            g_cpu.PC = base + 0x80b0; m68k_write16(g_cpu.PC, 0x6108);
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == base + 0x80ba
                    && m68k_read32(g_cpu.A[7]) == base + 0x80b2, "alias BSR relocation");
            g_cpu.PC = base + 0x80c0; g_cpu.D[0] = 2; m68k_write32(g_cpu.PC, 0x51c80008);
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == base + 0x80ca
                    && g_cpu.D[0] == 1, "alias DBcc relocation");
            g_cpu.PC = base + 0x80d0; m68k_write32(g_cpu.PC, 0x41fa0008);
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.A[0] == base + 0x80da,
                    "alias PC-relative LEA preserves architectural address");
            g_cpu.PC = base + 0x8040; m68k_write32(g_cpu.PC, 0x4eba000a); fallback = 0;
            REQUIRE(!rr_md_native_lookup(g_cpu.PC), "every alias guards changed extension bytes");
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == base + 0x804c
                    && fallback == 1, "modified alias instruction uses truthful fallback");
        }
        const unsigned offsets[] = {0x8000,0x8040,0x8060,0x8080,0x80a0,0x80b0,0x80c0,0x80d0};
        for (unsigned i=0; i<sizeof offsets/sizeof *offsets; ++i)
            for (unsigned seed=1; seed<=8; ++seed) differential(base+offsets[i],seed);
        if (base != 0xff0000)
            for (unsigned seed=1; seed<=8; ++seed) differential(base+0xfffe,seed);
    }
    m68k_write32(0xe0fffe,0x4eba0008);
    REQUIRE(rr_md_native_lookup(0xe0fffe) != NULL, "RAM instruction can cross a 64 KiB alias boundary");
    REQUIRE(rr_md_native_lookup(0xfffffe) == NULL, "guard refuses an instruction crossing the 24-bit bus end");
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
                g_cpu.D[0] = 0x89abcdef; g_cpu.SR = 0x271f;
                uint32_t address = g_cpu.A[0] - 16;
                g_ram[address & 65535] = 0x12; g_ram[(address + 2) & 65535] = 0x34;
                g_ram[(address + 4) & 65535] = 0x56; g_ram[(address + 6) & 65535] = 0x78;
                watched_writes = 0; watch_writes = 1; fallback = 0;
                g_cycle_accumulator = g_audio_cycle_counter = 0;
                REQUIRE(m68k_interp_step() == M68KI_OK, "MOVEP executes");
                watch_writes = 0;
                REQUIRE(g_cpu.PC == TEST_MOVEP + form * 16 + 4 && g_cpu.A[0] == 0xff0110 + odd
                        && g_cpu.SR == 0x271f && fallback == (unsigned)reference,
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
        g_cpu.PC = TEST_STOP;
        REQUIRE(m68k_interp_step() == M68KI_OK && !rr_md_cpu_stopped
                && g_cpu.PC == TEST_RTE && g_cpu.SR == 0x2700
                && g_cpu.A[7] == 0xffbffa && rr_md_user_sp() == 0xffd000
                && m68k_read16(g_cpu.A[7]) == 0x0700
                && m68k_read32(g_cpu.A[7] + 2) == TEST_STOP,
                "user STOP takes vector 8 on SSP without loading its immediate SR");
    }
    uint8_t image[128]; memset(&g_cpu, 0, sizeof g_cpu);
    g_cpu.SR = 0x0305; g_cpu.A[7] = 0xffd000; g_cpu.USP = 0xffc000; g_cpu.PC = TEST_STOP + 4;
    rr_md_cpu_stopped = 1; M68KState original = g_cpu;
    REQUIRE(sec_cpu_save(NULL, 0) == sizeof g_cpu + 4 + sizeof rr_md_prefetch
            && sec_cpu_save(image, sizeof g_cpu) == 0,
            "snapshot bounds include STOP and the pointer-free queue");
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
    g_cpu.PC=0x200;rr_md_prefetch=(RrMdPrefetch){0x200,2,{0x7001,0x4e71}};
    length=sec_cpu_save(image,sizeof image);
    rr_md_prefetch.words[0]=0x7002;
    REQUIRE(sec_cpu_load(image,length) && rr_md_prefetch.words[0]==0x7001,
            "snapshot retains stale prefetched words");
    RrMdPrefetch bad_queue=rr_md_prefetch;
    for(unsigned error=0;error<4;++error) {
        bad_queue=rr_md_prefetch;
        if(error==0)bad_queue.valid=1;
        if(error==1)bad_queue.valid=3;
        if(error==2)bad_queue.pc=0x202;
        if(error==3)bad_queue.pc=0x201;
        memcpy(image+sizeof g_cpu+4,&bad_queue,sizeof bad_queue);
        REQUIRE(!sec_cpu_load(image,length) && rr_md_prefetch.words[0]==0x7001 && g_cpu.PC==0x200,
                "malformed queue rejects before CPU/queue mutation");
    }
    REQUIRE(sec_cpu_load(image,sizeof g_cpu+4) && !rr_md_prefetch.valid,
            "old CPU section explicitly migrates to an empty queue");
}
/* Independent Motorola exception-frame and timing values, not just agreement
 * between two adapters that share semantic helpers. TRAP vectors 32..47. */
static void trap_checks(void) {
    for (int reference = 0; reference <= 1; ++reference) {
        force_reference = reference;
        for (unsigned vector = 0; vector < 16; ++vector) {
            memset(&g_cpu, 0, sizeof g_cpu); memset(g_ram, 0, sizeof g_ram);
            uint32_t pc = TEST_TRAP + vector * 16;
            g_cpu.PC = pc; g_cpu.A[7] = 0xffc000; g_cpu.USP = 0xffd000; g_cpu.SR = 0x2315;
            g_cycle_accumulator = g_audio_cycle_counter = 0;
            fallback = 0;
            REQUIRE(m68k_interp_step() == M68KI_OK, "TRAP enters vector");
            REQUIRE(g_cpu.PC == TEST_RTE && g_cpu.A[7] == 0xffbffa && g_cpu.SR == 0x2315,
                    "TRAP selects vector and clears trace without changing IRQ mask or CCR");
            REQUIRE(m68k_read16(0xffbffa) == 0x2315 && m68k_read32(0xffbffc) == pc + 2,
                    "TRAP frame contains old SR and following instruction PC");
            REQUIRE(g_cpu.USP == 0xffd000 && g_audio_cycle_counter == 34 && g_cycle_accumulator == 34,
                    "TRAP preserves USP and takes 34 clocks");
            REQUIRE(fallback == (unsigned)reference, "TRAP uses covered native body or explicit reference");
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == pc + 2 && g_cpu.SR == 0x2315
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
            /* Privilege faults save the faulting PC and do not read operands. */
            const uint32_t privileged[] = {TEST_RTE, TEST_SR_MOVE, TEST_SR_AND, TEST_SR_EOR, TEST_USP_MOVE};
            for (unsigned p = 0; p < sizeof privileged / sizeof *privileged; ++p) {
                g_cpu.PC = privileged[p]; uint32_t clocks = g_audio_cycle_counter;
                REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_RTE
                        && g_cpu.SR == 0x2315 && rr_md_user_sp() == 0xffffd000u
                        && g_cpu.A[7] == 0xffffffbau
                        && m68k_read16(g_cpu.A[7]) == 0x0315
                        && m68k_read32(g_cpu.A[7] + 2) == privileged[p]
                        && g_audio_cycle_counter - clocks == 34,
                        "privilege fault selects vector 8, saved current PC and 34 clocks");
                REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == privileged[p]
                        && g_cpu.SR == 0x0315 && g_cpu.A[7] == 0xffffd000u,
                        "privilege handler can return to the original user instruction");
            }
        }
    }
}
static void exception_checks(void) {
    /* Independently specified vector/stack/PC/cost expectations. Invalid and
     * privileged instructions save their first word's PC; DIV saves the next
     * PC. No decoder or native/reference equality provides these expectations. */
    const uint32_t fault_pcs[] = {TEST_EXCEPTION, TEST_EXCEPTION + 16, TEST_EXCEPTION + 32,
        TEST_EXCEPTION + 48, TEST_EXCEPTION + 64, TEST_EXCEPTION + 80,
        TEST_EXCEPTION + 96, TEST_EXCEPTION + 112, TEST_STOP, TEST_RTE,
        TEST_SR_MOVE, TEST_SR_AND, TEST_SR_EOR, TEST_USP_MOVE};
    for (int reference = 0; reference <= 1; ++reference) {
        force_reference = reference;
        for (unsigned n = 0; n < sizeof fault_pcs / sizeof *fault_pcs; ++n) {
            for (unsigned trace = 0; trace <= 1; ++trace) {
                memset(&g_cpu, 0, sizeof g_cpu); memset(g_ram, 0, sizeof g_ram);
                g_cpu.SR = (uint16_t)(0x0315 | (trace ? 0x8000 : 0));
                g_cpu.A[7] = 0xffd000; g_cpu.USP = 0xffc000; g_cpu.A[0] = 0xff4000;
                g_cpu.D[0] = 0x76543210; g_cpu.PC = fault_pcs[n];
                uint16_t saved_sr = g_cpu.SR; fallback = 0;
                g_cycle_accumulator = g_audio_cycle_counter = 0;
                REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_RTE
                    && g_cpu.SR == 0x2315 && g_cpu.A[7] == 0xffbffa
                    && rr_md_user_sp() == 0xffd000 && g_cpu.A[0] == 0xff4000
                    && g_cpu.D[0] == 0x76543210 && !rr_md_cpu_stopped,
                    "synchronous fault switches to SSP, clears trace and preserves operands");
                REQUIRE(m68k_read16(g_cpu.A[7]) == saved_sr
                    && m68k_read32(g_cpu.A[7] + 2) == fault_pcs[n]
                    && g_audio_cycle_counter == 34 && g_cycle_accumulator == 34
                    && !rr_md_exception_cycles && fallback == (unsigned)reference,
                    "fault stacks original SR/current PC and consumes 34 clocks exactly once");
                ++exception_cases;
            }
        }
        for (unsigned n = 0; n < 6; ++n) {
            memset(&g_cpu, 0, sizeof g_cpu); memset(g_ram, 0, sizeof g_ram);
            g_cpu.SR = 0x2310; g_cpu.A[7] = 0xffc000; g_cpu.USP = 0xffd000;
            g_cpu.A[0] = 0xff4000; g_cpu.D[0] = 0x87654321;
            g_cpu.PC = TEST_EXCEPTION + 128 + n * 16;
            uint32_t pc = g_cpu.PC; fallback = 0;
            g_cycle_accumulator = g_audio_cycle_counter = 0;
            const unsigned cycles[] = {42, 42, 42, 42, 44, 46};
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_RTE
                && g_cpu.D[0] == 0x87654321 && (g_cpu.SR & 0xfff0) == 0x2310,
                "DIV by zero takes vector 5 and preserves destination, X and interrupt mask");
            uint32_t sp = n == 4 ? 0xffbff8 : 0xffbffa;
            REQUIRE(g_cpu.A[7] == sp && m68k_read16(sp) == 0x2310
                && m68k_read32(sp + 2) == pc + (n < 2 || n == 4 ? 2 : 4)
                && g_cpu.A[0] == (n < 2 ? 0xff4002 : 0xff4000)
                && g_audio_cycle_counter == cycles[n] && !rr_md_exception_cycles
                && fallback == (unsigned)reference,
                "DIV reads EA once, keeps predecrement before framing and charges exception plus EA");
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == pc + (n < 2 || n == 4 ? 2 : 4)
                && g_cpu.A[7] == (n == 4 ? 0xffbffe : 0xffc000),
                "divide handler RTE returns after the faulting instruction");
            ++exception_cases;
        }
        /* Every alias uses the real execution PC, including PC-relative EA. */
        for (unsigned base = 0xe00000; base <= 0xff0000; base += 0x10000) {
            const uint16_t opcodes[] = {0x4afc, 0xa123, 0xf123, 0x46d8, 0x80d8, 0x81d8, 0x80fa};
            for (unsigned n = 0; n < 7; ++n) {
                memset(&g_cpu, 0, sizeof g_cpu); memset(g_ram, 0, sizeof g_ram);
                g_cpu.SR = n == 3 ? 0x0310 : 0x2310;
                g_cpu.A[7] = base + (n == 3 ? 0xd000 : 0xc000);
                g_cpu.USP = base + (n == 3 ? 0xc000 : 0xd000);
                g_cpu.A[0] = base + 0x4000; g_cpu.D[0] = 0x80000000;
                g_cpu.PC = base + 0x9000 + n * 16;
                m68k_write16(g_cpu.PC, opcodes[n]);
                if (n == 6) m68k_write16(g_cpu.PC + 2, 6);
                uint32_t pc = g_cpu.PC; fallback = 0;
                g_cycle_accumulator = g_audio_cycle_counter = 0;
                REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_RTE
                    && g_cpu.A[7] == base + 0xbffa && g_cpu.D[0] == 0x80000000
                    && m68k_read32(g_cpu.A[7] + 2) == pc + (n < 4 ? 0 : n < 6 ? 2 : 4)
                    && g_audio_cycle_counter == (n < 4 ? 34 : n < 6 ? 42 : 46)
                    && !rr_md_exception_cycles && fallback == (unsigned)reference,
                    "guarded RAM faults preserve actual alias PC, following PC and exception cost");
                ++exception_cases;
            }
        }
    }
    force_reference = 0;
    /* Distinct ROM vectors prove selection rather than a shared RTE target. */
    for (unsigned vector = 4; vector <= 11; ++vector)
        if (vector == 4 || vector == 5 || vector == 8 || vector == 10 || vector == 11) {
            uint32_t value = 0x1000 + vector * 16;
            g_rom[vector * 4] = value >> 24; g_rom[vector * 4 + 1] = value >> 16;
            g_rom[vector * 4 + 2] = value >> 8; g_rom[vector * 4 + 3] = value;
        }
    for (unsigned n = 0; n < 7; ++n) {
        g_cpu.SR = n == 5 ? 0x0310 : 0x2310; g_cpu.A[7] = 0xffc000; g_cpu.USP = 0xffd000;
        g_cpu.PC = TEST_EXCEPTION + (n < 5 ? n * 16 : n == 5 ? 112 : 160);
        const unsigned vectors[] = {4, 4, 4, 10, 11, 8, 5};
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == 0x1000 + vectors[n] * 16,
                "illegal, line A, line F and privilege select distinct vector addresses");
        ++exception_cases;
    }
    for (int reference = 0; reference <= 1; ++reference) {
        force_reference = reference;
        memset(&g_cpu, 0, sizeof g_cpu); memset(g_ram, 0, sizeof g_ram);
        g_cpu.SR = 0x0310; g_cpu.A[7] = 0xffd000; g_cpu.USP = 0xffc000;
        g_cpu.D[0] = 0x76543210; g_cpu.PC = TEST_EXCEPTION + 160;
        g_audio_cycle_counter = g_cycle_accumulator = 0;
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == 0x1050
            && g_cpu.SR == 0x2310 && g_cpu.A[7] == 0xffbffa && rr_md_user_sp() == 0xffd000
            && g_cpu.D[0] == 0x76543210 && m68k_read16(g_cpu.A[7]) == 0x0310
            && m68k_read32(g_cpu.A[7] + 2) == TEST_EXCEPTION + 164 && g_audio_cycle_counter == 42,
            "user divide exception selects SSP and vector 5, retaining USP and destination");
        ++exception_cases;
    }
    memcpy(g_rom, fixture_rom, sizeof fixture_rom);
}
static void set_vector(unsigned vector, uint32_t target) {
    unsigned a = vector * 4;
    g_rom[a] = target >> 24; g_rom[a + 1] = target >> 16;
    g_rom[a + 2] = target >> 8; g_rom[a + 3] = target;
}
static void bounds_reset(uint32_t pc, uint16_t sr) {
    memset(&g_cpu, 0, sizeof g_cpu); memset(g_ram, 0, sizeof g_ram);
    g_cpu.PC = pc; g_cpu.SR = sr;
    g_cpu.A[7] = sr & SR_S ? 0xffc000 : 0xffd000;
    g_cpu.USP = sr & SR_S ? 0xffd000 : 0xffc000;
    g_cycle_accumulator = g_audio_cycle_counter = fallback = rr_md_cpu_stopped = 0;
    rr_md_exception_cycles = rr_md_trace_suppressed = 0;
}
static void trace_before_irq(void) {
    REQUIRE(g_cpu.PC == TEST_BOUNDS + 160 && g_cpu.A[7] == 0xffbff4
        && m68k_read32(0xffbff6) == TEST_RTE
        && m68k_read32(0xffbffc) == TEST_TRAP + 2
        && g_audio_cycle_counter == 68 && !rr_md_exception_cycles && !rr_md_trace_suppressed,
        "TRAP and trace finish with both frames and clocks before scheduler/IRQ entry");
    rr_md_exception_frame(g_cpu.SR, g_cpu.PC, 0x2615);
    REQUIRE(g_cpu.A[7] == 0xffbfee && m68k_read32(0xffbff0) == TEST_BOUNDS + 160,
            "pending IRQ stacks the trace-handler address after both previous exceptions");
    on_scheduler = NULL;
}
static void bounds_trace_checks(void) {
    set_vector(6, TEST_RTE); set_vector(7, TEST_BOUNDS + 176);
    set_vector(9, TEST_BOUNDS + 160); set_vector(32, TEST_RTE);
    for (int reference = 0; reference <= 1; ++reference) {
        force_reference = reference;
        /* Signed word CHK: valid interval, negative values, inverted/negative
         * bound, upper-half Dn retention, EA exactly once and A7 predecrement. */
        const int values[] = {0, 10, 11, -1, -20, 0, -1, -15513, 32767, -32768};
        const int bounds[] = {10, 10, 10, 10, -10, -1, -2, 21984, -32768, 32767};
        for (unsigned mode = 0; mode < 2; ++mode)
        for (unsigned form = 0; form < 4; ++form)
        for (unsigned n = 0; n < sizeof values / sizeof *values; ++n) {
            bounds_reset(TEST_BOUNDS + form * 16, mode ? 0x231b : 0x031b);
            int bound = form == 3 ? 10 : bounds[n], value = values[n];
            uint32_t reg = 0xdead0000u | (uint16_t)value;
            g_cpu.D[0] = reg; g_cpu.D[1] = (uint16_t)bound; g_cpu.A[0] = 0xff4000;
            uint32_t old_sp = g_cpu.A[7];
            m68k_write16(form == 2 ? old_sp - 2 : 0xff4000, (uint16_t)bound);
            unsigned fault = value > bound || value < 0;
            unsigned ea = form == 0 ? 0 : form == 1 || form == 3 ? 4 : 6;
            unsigned clocks = (fault ? value > bound || value - bound < -32768 ? 38 : 40 : 10) + ea;
            uint16_t result_sr = (uint16_t)((mode ? 0x2310 : 0x0310) | (!value ? SR_Z : 0));
            if (fault) result_sr = (result_sr & ~SR_N) | (value < 0 ? SR_N : 0);
            unsigned sp = old_sp - (form == 2 ? 2 : 0);
            unsigned ssp = (mode ? sp : 0xffc000) - (fault ? 6 : 0);
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.D[0] == reg
                && g_cpu.PC == (fault ? TEST_RTE : TEST_BOUNDS + form * 16 + (form == 3 ? 4 : 2))
                && rr_md_supervisor_sp() == ssp && rr_md_user_sp() == (mode ? 0xffd000 : sp)
                && g_cpu.SR == (result_sr | (fault ? SR_S : 0))
                && g_cpu.A[0] == 0xff4000 + (form == 1 ? 2 : 0)
                && g_audio_cycle_counter == clocks && g_cycle_accumulator == clocks
                && !rr_md_exception_cycles && !rr_md_trace_suppressed && fallback == (unsigned)reference,
                "CHK compares signed words, consumes one EA, selects vector 6 and charges the actual branch");
            if (fault) REQUIRE(m68k_read16(ssp) == result_sr
                && m68k_read32(ssp + 2) == TEST_BOUNDS + form * 16 + (form == 3 ? 4 : 2),
                "CHK frame saves result SR and following PC on the real SSP");
            ++exception_cases;
        }
        for (unsigned mode = 0; mode < 2; ++mode)
        for (unsigned overflow = 0; overflow < 2; ++overflow) {
            uint16_t sr = (mode ? 0x231d : 0x031d) | (overflow ? SR_V : 0);
            bounds_reset(TEST_BOUNDS + 64, sr);
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == (overflow ? TEST_BOUNDS + 176 : TEST_BOUNDS + 66)
                && g_cpu.SR == (sr | (overflow ? SR_S : 0))
                && rr_md_supervisor_sp() == 0xffc000 - (overflow ? 6 : 0)
                && g_audio_cycle_counter == (overflow ? 34 : 4),
                "TRAPV selects vector 7 only when V is set and otherwise leaves SR unchanged");
            ++exception_cases;
        }
        /* Architectural trace cases from Motorola 6.3.8, independent of the
         * single-instruction oracle (which does not deliver trace boundaries). */
        for (unsigned mode = 0; mode < 2; ++mode) {
            uint16_t sr = mode ? 0xa315 : 0x8315;
            bounds_reset(TEST_BOUNDS + 80, sr);
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_BOUNDS + 160
                && g_cpu.SR == 0x2315 && g_cpu.A[7] == 0xffbffa && rr_md_user_sp() == 0xffd000
                && m68k_read16(0xffbffa) == sr && m68k_read32(0xffbffc) == TEST_BOUNDS + 82
                && g_audio_cycle_counter == 38 && fallback == (unsigned)reference,
                "NOP traces from user or supervisor mode after execution with 4 + 34 clocks");
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_BOUNDS + 82
                && g_cpu.SR == sr && g_cpu.A[7] == (mode ? 0xffc000 : 0xffd000),
                "trace RTE restores T but does not trace itself when T was clear at entry");
            ++exception_cases;
        }
        bounds_reset(TEST_BOUNDS + 96, 0xa315); /* MOVE #2315,SR clears T. */
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_BOUNDS + 160
            && m68k_read16(g_cpu.A[7]) == 0x2315 && m68k_read32(g_cpu.A[7] + 2) == TEST_BOUNDS + 100
            && g_audio_cycle_counter == 50, "clearing T during an instruction still traces its completion");
        ++exception_cases;
        bounds_reset(TEST_BOUNDS + 112, 0x2315); /* ORI #8000,SR sets T. */
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_BOUNDS + 116
            && g_cpu.SR == 0xa315 && g_cpu.A[7] == 0xffc000 && g_audio_cycle_counter == 20,
            "setting T during an instruction does not trace that same instruction");
        g_cpu.PC = TEST_BOUNDS + 80;
        REQUIRE(m68k_interp_step() == M68KI_OK && g_audio_cycle_counter == 58,
                "the next instruction traces with the new T value");
        ++exception_cases;
        bounds_reset(TEST_BOUNDS + 128, 0xa315); /* STOP #2300 */
        REQUIRE(m68k_interp_step() == M68KI_OK && !rr_md_cpu_stopped
            && g_cpu.PC == TEST_BOUNDS + 160 && m68k_read16(g_cpu.A[7]) == 0x2300
            && m68k_read32(g_cpu.A[7] + 2) == TEST_BOUNDS + 132 && g_audio_cycle_counter == 38,
            "trace wakes a STOP executed with T set at instruction entry");
        ++exception_cases;
        bounds_reset(TEST_TRAP, 0xa315);
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_BOUNDS + 160
            && g_cpu.A[7] == 0xffbff4 && m68k_read16(0xffbff4) == 0x2315
            && m68k_read32(0xffbff6) == TEST_RTE && m68k_read16(0xffbffa) == 0xa315
            && m68k_read32(0xffbffc) == TEST_TRAP + 2 && g_audio_cycle_counter == 68,
            "TRAP stacks its own frame before the trace frame");
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_RTE && g_cpu.A[7] == 0xffbffa,
            "trace RTE returns to the instruction-exception handler");
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_TRAP + 2
            && g_cpu.A[7] == 0xffc000 && g_cpu.SR == 0xa315,
            "second RTE unwinds the instruction-exception frame without an immediate trace");
        ++exception_cases;
        bounds_reset(TEST_TRAP, 0xa315);
        g_vblank_threshold = 1; on_scheduler = trace_before_irq;
        REQUIRE(m68k_interp_step() == M68KI_OK && !on_scheduler, "pending IRQ observes the completed trace");
        g_vblank_threshold = 0xffffffffu; ++exception_cases;
        for (unsigned n = 0; n < 4; ++n) {
            /* Trace after CHK, zero divide and both TRAPV branches. */
            unsigned pcs[] = {TEST_BOUNDS, TEST_EXCEPTION + 160, TEST_BOUNDS + 64, TEST_BOUNDS + 64};
            unsigned targets[] = {TEST_RTE, TEST_RTE, TEST_BOUNDS + 176, TEST_BOUNDS + 66};
            unsigned costs[] = {72, 76, 68, 38};
            bounds_reset(pcs[n], n == 2 ? 0xa317 : 0xa315);
            g_cpu.D[0] = n == 0 ? 11 : 0x80000000; g_cpu.D[1] = 10;
            unsigned sp = n == 3 ? 0xffbffa : 0xffbff4;
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_BOUNDS + 160
                && g_cpu.A[7] == sp && m68k_read32(sp + 2) == targets[n]
                && g_audio_cycle_counter == costs[n] && !rr_md_trace_suppressed,
                "completed CHK, DIV zero and TRAPV trace after their instruction exception");
            ++exception_cases;
        }
        bounds_reset(TEST_RTE, 0xa315);
        m68k_write16(0xffc000, 0x0315); m68k_write32(0xffc002, TEST_BOUNDS + 80);
        REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_BOUNDS + 160
            && g_cpu.A[7] == 0xffc000 && rr_md_user_sp() == 0xffd000
            && m68k_read16(0xffc000) == 0x0315 && m68k_read32(0xffc002) == TEST_BOUNDS + 80
            && g_audio_cycle_counter == 54,
            "RTE entered with T set traces after restoring user mode and the popped SSP");
        ++exception_cases;
        bounds_reset(TEST_BOUNDS + 144, 0x0315);
        rr_md_exception_frame(g_cpu.SR, TEST_BOUNDS + 80, 0x2615);
        REQUIRE(m68k_interp_run_handler(TEST_BOUNDS + 144) == M68KI_OK
            && g_cpu.PC == TEST_BOUNDS + 80 && g_cpu.SR == 0x0315
            && g_cpu.A[7] == 0xffd000 && rr_md_supervisor_sp() == 0xffc000
            && g_audio_cycle_counter == 74 && fallback == 3u * (unsigned)reference,
            "IRQ runner executes a nested TRAP RTE before popping the outer interrupt frame");
        ++exception_cases;
        for (unsigned base = 0xe00000; base <= 0xff0000; base += 0x10000) {
            bounds_reset(base + 0x9200, 0x2315); m68k_write16(g_cpu.PC, 0x4198);
            g_cpu.A[0] = base + 0x4000; g_cpu.D[0] = 11; m68k_write16(g_cpu.A[0], 10);
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_RTE
                && m68k_read32(g_cpu.A[7] + 2) == base + 0x9202 && g_audio_cycle_counter == 42,
                "CHK RAM variant preserves the executing alias PC");
            bounds_reset(base + 0x9210, 0x2317); m68k_write16(g_cpu.PC, 0x4e76);
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_BOUNDS + 176
                && m68k_read32(g_cpu.A[7] + 2) == base + 0x9212 && g_audio_cycle_counter == 34,
                "TRAPV RAM variant preserves the executing alias PC");
            bounds_reset(base + 0x9220, 0xa315); m68k_write16(g_cpu.PC, 0x4e71);
            REQUIRE(m68k_interp_step() == M68KI_OK && g_cpu.PC == TEST_BOUNDS + 160
                && m68k_read32(g_cpu.A[7] + 2) == base + 0x9222 && g_audio_cycle_counter == 38,
                "trace after a guarded native RAM body saves the actual alias PC");
            exception_cases += 3;
        }
    }
    force_reference = 0;
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
    exception_checks();
    bounds_trace_checks();
    timer_checks();
    mirror_checks();
    printf("{\"instruction_state_comparisons\":%u,\"exception_cases\":%u,\"architecture_checks\":\"passed\",\"movep_checks\":\"passed\",\"ym_timer_checks\":\"passed\",\"passed\":true}\n", cases, exception_cases);
    return 0;
}
