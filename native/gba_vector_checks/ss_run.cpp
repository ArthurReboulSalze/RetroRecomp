// Original code of Retro-Recomp, MIT licence (the repository's LICENSE).
//
// Runs the functions ss_gen.cpp generated, one per sampled vector, on the vector's initial state, against the SingleStepTests/ARM7TDMI
// expectations: R0-R15, every bank, CPSR, the SPSRs and the ordered data transactions (see ss_common.h). The functions are the
// engine's own generated code for one instruction; what surrounds them here is a recording bus and a few stubs of the runtime, modelled
// on the engine's own code generator tests (a dispatch to another address, a fall through, an unimplemented instruction are recorded,
// not executed).
//
// Divergences this runner knows about, and the harness rules that keep them out of the numbers (the categories of the rest are
// named by tools/gba_vector_selftest.py, from the opcode and the failing words):
//   * kSwiReadWord: the engine's software interrupt entry reads one word of the BIOS data area, which the vectors do not record.
//   * a branch the code leaves to the dispatcher is read as the PC it targets (ARM: any, Thumb: bit 0 cleared).
//   * a fall through is read as the next instruction's address.
//
// usage: ss_run stride max_per_file file1.json.bin file2.json.bin ...   (the selection ss_gen was given)
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "arm_ir.h"
#include "gba_waitstates.h"
#include "runtime_arm.h"
#include "ss_common.h"

static RuntimeWaitTable power_on_waits() { RuntimeWaitTable t{}; gba::waits_reset(t); return t; }
RuntimeWaitTable g_runtime_waits = power_on_waits();

extern "C" uint32_t runtime_prefetch_stall_delta(uint32_t wait, uint32_t pc, uint32_t thumb) {
    const int32_t w = static_cast<int32_t>(wait);
    return static_cast<uint32_t>(rwt_prefetch_stall(&g_runtime_waits, w, pc, thumb) - w);
}

namespace {
constexpr uint32_t kSwiVector = 8;                  // the dispatch target of a software interrupt
constexpr uint32_t kSwiReadWord = 0x03007FF8u;      // BIOS interrupt flags word that the SWI entry reads and the vectors do not record

SsReplay g_bus;
bool g_dispatch = false, g_fell = false, g_unimplemented = false;
uint32_t g_target = 0;
}

// The generated code's links to the rest of the runtime, as recorders or no-ops.
extern "C" const unsigned kDispatchTableLen = 0u;
struct DispatchEntry { uint32_t addr; uint8_t thumb; uint8_t resume; void (*fn)(void); };
extern "C" const DispatchEntry kDispatchTable[1] = {{0xFFFFFFFFu, 0u, 0u, nullptr}};
extern "C" const DispatchEntry kBiosDispatchTable[1] = {{0xFFFFFFFFu, 0u, 0u, nullptr}};
extern "C" const unsigned kBiosDispatchTableLen = 0u;
extern "C" unsigned long long g_runtime_vblank_starts = 0;
extern "C" unsigned long long g_runtime_cycles = 0;
extern "C" int g_force_interp = 0;
extern "C" void runtime_force_interp_step(void) {}
extern "C" int runtime_bridge_interpret(uint32_t, bool, uint32_t, uint64_t) { return 0; }
extern "C" uint8_t bus_read_u8(uint32_t a) { return (uint8_t)g_bus.read(a, 1); }
extern "C" uint16_t bus_read_u16(uint32_t a) { return (uint16_t)g_bus.read(a, 2); }
extern "C" uint32_t bus_read_u32(uint32_t a) { return g_bus.read(a, 4); }
extern "C" void bus_write_u8(uint32_t a, uint8_t v) { g_bus.write(a, 1, v); }
extern "C" void bus_write_u16(uint32_t a, uint16_t v) { g_bus.write(a, 2, v); }
extern "C" void bus_write_u32(uint32_t a, uint32_t v) { g_bus.write(a, 4, v); }
extern "C" void codegen_test_fellthrough(void) { g_fell = true; }
extern "C" void runtime_dispatch_miss(uint32_t t) { g_dispatch = true; g_target = t; }
extern "C" int overlay_try_dispatch(uint32_t, int) { return 0; }
extern "C" void runtime_unimplemented_op(const char*, uint32_t) { g_unimplemented = true; }
extern "C" void runtime_tick(uint32_t) {}
extern "C" bool runtime_should_yield(void) { return false; }
extern "C" uint32_t runtime_mem_cycles(uint32_t, uint32_t, uint32_t) { return 1u; }
extern "C" uint32_t runtime_mul_cycles(uint32_t rs, uint32_t sv, uint32_t extra) { return armv4t::mul_wait_cycles(rs, sv != 0u, extra); }
extern "C" int gba_mod_function_entry(uint32_t, int, ArmCpuState*) { return 0; }

struct SsEntry { int file; unsigned test; void (*fn)(void); };
extern "C" const SsEntry kSsTable[];

// Register bank index of a mode in ArmCpuState (0 user/system, 1 FIQ, 2 IRQ, 3 supervisor, 4 abort, 5 undefined).
static int bank_of(uint32_t mode) {
    switch (mode & 0x1f) { case 0x11: return 1; case 0x12: return 2; case 0x13: return 3; case 0x17: return 4; case 0x1b: return 5; default: return 0; }
}

static void seed(const SsState& s) {
    std::memset(&g_cpu, 0, sizeof g_cpu);
    for (int i = 0; i < 16; ++i) g_cpu.R[i] = s.R[i];
    for (int i = 0; i < 5; ++i) { g_cpu.r8_12_user[i] = s.R[8 + i]; g_cpu.r8_12_fiq[i] = s.fiq[i]; }
    g_cpu.banked_sp[0] = s.R[13]; g_cpu.banked_lr[0] = s.R[14];
    g_cpu.banked_sp[1] = s.fiq[5]; g_cpu.banked_lr[1] = s.fiq[6];
    g_cpu.banked_sp[3] = s.svc[0]; g_cpu.banked_lr[3] = s.svc[1];
    g_cpu.banked_sp[4] = s.abt[0]; g_cpu.banked_lr[4] = s.abt[1];
    g_cpu.banked_sp[2] = s.irq[0]; g_cpu.banked_lr[2] = s.irq[1];
    g_cpu.banked_sp[5] = s.und[0]; g_cpu.banked_lr[5] = s.und[1];
    g_cpu.banked_spsr[1] = s.spsr[0]; g_cpu.banked_spsr[3] = s.spsr[1]; g_cpu.banked_spsr[4] = s.spsr[2];
    g_cpu.banked_spsr[2] = s.spsr[3]; g_cpu.banked_spsr[5] = s.spsr[4];
    g_cpu.cpsr = s.cpsr;
    const int b = bank_of(s.cpsr);                  // the registers visible in the current mode
    g_cpu.R[13] = g_cpu.banked_sp[b]; g_cpu.R[14] = g_cpu.banked_lr[b];
    if (b == 1) for (int i = 0; i < 5; ++i) g_cpu.R[8 + i] = s.fiq[i];
}

// The CPU back into the layout of the vectors (the visible registers written back to their bank).
static SsState flatten(const SsState& like) {
    ArmCpuState c = g_cpu;
    const int b = bank_of(c.cpsr);
    c.banked_sp[b] = c.R[13]; c.banked_lr[b] = c.R[14];
    if (b == 1) for (int i = 0; i < 5; ++i) c.r8_12_fiq[i] = c.R[8 + i]; else for (int i = 0; i < 5; ++i) c.r8_12_user[i] = c.R[8 + i];
    SsState s = like;
    for (int i = 0; i < 16; ++i) s.R[i] = c.R[i];
    for (int i = 0; i < 5; ++i) { s.R[8 + i] = c.r8_12_user[i]; s.fiq[i] = c.r8_12_fiq[i]; }
    s.R[13] = c.banked_sp[0]; s.R[14] = c.banked_lr[0];
    s.fiq[5] = c.banked_sp[1]; s.fiq[6] = c.banked_lr[1];
    s.svc[0] = c.banked_sp[3]; s.svc[1] = c.banked_lr[3];
    s.abt[0] = c.banked_sp[4]; s.abt[1] = c.banked_lr[4];
    s.irq[0] = c.banked_sp[2]; s.irq[1] = c.banked_lr[2];
    s.und[0] = c.banked_sp[5]; s.und[1] = c.banked_lr[5];
    s.spsr[0] = c.banked_spsr[1]; s.spsr[1] = c.banked_spsr[3]; s.spsr[2] = c.banked_spsr[4]; s.spsr[3] = c.banked_spsr[2];
    s.spsr[4] = c.banked_spsr[5];
    s.cpsr = c.cpsr;
    return s;
}

int main(int argc, char** argv) {
    if (argc < 4) { std::fputs("usage: ss_run stride max_per_file files...\n", stderr); return 2; }
    const uint32_t stride = std::atoi(argv[1]), max_per_file = std::atoi(argv[2]);
    const SsEntry* entry = kSsTable;
    uint32_t total_run = 0, total_pass = 0;
    for (int fi = 3; fi < argc; ++fi) {
        SsFile f;
        if (!f.open(argv[fi])) { std::fprintf(stderr, "cannot open %s\n", argv[fi]); return 2; }
        const std::string name = ss_name(argv[fi]);
        uint32_t ran = 0, passed = 0;
        for (uint32_t ti : ss_sample(f.count, stride, max_per_file)) {
            if (entry->file != fi - 3 || entry->test != ti) { std::fputs("the generated table and the selection disagree\n", stderr); return 3; }
            const SsTest t = f.get(ti);
            g_bus.begin(t); g_dispatch = g_fell = g_unimplemented = false; g_target = 0;
            const bool thumb0 = (t.init.cpsr >> 5) & 1;
            const uint32_t pc = t.init.R[15] - (thumb0 ? 4 : 8);
            seed(t.init); g_cpu.R[15] = pc;
            (entry++)->fn(); ++ran;
            if (g_unimplemented) { ss_print_failure(name, ti, t, "unimplemented", t.fin.cpsr, "STEP"); continue; }
            const bool thumb_after = (g_cpu.cpsr >> 5) & 1;
            uint32_t next;                                  // where the instruction left the PC
            if (g_dispatch) next = g_target & (thumb_after ? ~1u : ~0u);
            else if (g_fell) next = pc + (thumb0 ? 2 : 4);
            else next = g_cpu.R[15];
            SsState got = flatten(t.fin);
            got.R[15] = next + (thumb_after ? 4 : 8);       // the vectors hold the pipeline-visible PC
            std::string why = ss_compare_state(got, t.fin);
            if (g_dispatch && g_target == kSwiVector) {
                std::vector<SsTrans> kept;
                for (const SsTrans& x : g_bus.reads) if (x.addr != kSwiReadWord) kept.push_back(x);
                g_bus.reads = kept;
                if (kept.empty()) g_bus.starved = false;
            }
            if (!ss_transactions_match(t, g_bus)) ss_add_cause(why, "TRANS");
            if (why.empty()) { ++passed; continue; }
            ss_print_failure(name, ti, t, "ran", got.cpsr, why);
        }
        ss_print_file(name, ran, passed);
        total_run += ran; total_pass += passed;
    }
    std::fprintf(stderr, "ran %u passed %u\n", total_run, total_pass);
    return 0;
}
