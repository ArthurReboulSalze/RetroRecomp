// Original code of Retro-Recomp, MIT licence (the repository's LICENSE).
//
// Runs the engine's interpreter (`Interpreter::step`, the fallback of every converted game and the reference its generated code is
// compared with) on SingleStepTests/ARM7TDMI vectors: R0-R15, every bank, CPSR, the SPSRs and the ordered data transactions are
// compared (see ss_common.h). The files are read in place and nothing is written.
//
// What the harness does for the instruction the way a caller of the interpreter must: a software interrupt is entered with
// `Interpreter::enter_swi`, a step that returns Undefined or NotImplemented is a failure that cannot be compared (the caller takes the
// undefined-instruction trap, this harness does not), and a step that falls through leaves the PC after the instruction.
//
// usage: ss_interp stride max_per_file file1.json.bin file2.json.bin ...   (stride 1 and a large maximum: every vector)
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "arm_decode.h"
#include "arm_ir.h"
#include "bus.h"
#include "cpu_state.h"
#include "interpreter.h"
#include "thumb_decode.h"
#include "ss_common.h"

using namespace armv4t;

static uint32_t pack(const CPSR& c) {
    return (c.n << 31) | (c.z << 30) | (c.c << 29) | (c.v << 28) | (c.i << 7) | (c.f << 6) | (c.t << 5) | (c.mode & 0x1f);
}
static void unpack(CPSR& c, uint32_t v) {
    c.n = v >> 31 & 1; c.z = v >> 30 & 1; c.c = v >> 29 & 1; c.v = v >> 28 & 1;
    c.i = v >> 7 & 1; c.f = v >> 6 & 1; c.t = v >> 5 & 1; c.mode = v & 0x1f;
}
static int bank_of(uint32_t mode) {
    switch (mode & 0x1f) { case 0x11: return Bank_FIQ; case 0x12: return Bank_IRQ; case 0x13: return Bank_Supervisor;
        case 0x17: return Bank_Abort; case 0x1b: return Bank_Undefined; default: return Bank_User; }
}

static void to_cpu(const SsState& s, CPUState& c) {
    std::memset(&c, 0, sizeof c);
    for (int i = 0; i < 16; ++i) c.R[i] = s.R[i];
    for (int i = 0; i < 5; ++i) { c.r8_12_user[i] = s.R[8 + i]; c.r8_12_fiq[i] = s.fiq[i]; }
    c.banked_sp[Bank_User] = s.R[13]; c.banked_lr[Bank_User] = s.R[14];
    c.banked_sp[Bank_FIQ] = s.fiq[5]; c.banked_lr[Bank_FIQ] = s.fiq[6];
    c.banked_sp[Bank_Supervisor] = s.svc[0]; c.banked_lr[Bank_Supervisor] = s.svc[1];
    c.banked_sp[Bank_Abort] = s.abt[0]; c.banked_lr[Bank_Abort] = s.abt[1];
    c.banked_sp[Bank_IRQ] = s.irq[0]; c.banked_lr[Bank_IRQ] = s.irq[1];
    c.banked_sp[Bank_Undefined] = s.und[0]; c.banked_lr[Bank_Undefined] = s.und[1];
    c.banked_spsr[Bank_FIQ] = s.spsr[0]; c.banked_spsr[Bank_Supervisor] = s.spsr[1]; c.banked_spsr[Bank_Abort] = s.spsr[2];
    c.banked_spsr[Bank_IRQ] = s.spsr[3]; c.banked_spsr[Bank_Undefined] = s.spsr[4];
    unpack(c.cpsr, s.cpsr);
    const int b = bank_of(s.cpsr);                  // the registers visible in the current mode
    c.R[13] = c.banked_sp[b]; c.R[14] = c.banked_lr[b];
    if (b == Bank_FIQ) for (int i = 0; i < 5; ++i) c.R[8 + i] = s.fiq[i];
    c.thumb = c.cpsr.t;
}

// The CPU back into the layout of the vectors (the visible registers written back to their bank).
static SsState from_cpu(const CPUState& c0, const SsState& like) {
    CPUState c = c0;
    const int b = bank_of(pack(c.cpsr));
    c.banked_sp[b] = c.R[13]; c.banked_lr[b] = c.R[14];
    if (b == Bank_FIQ) for (int i = 0; i < 5; ++i) c.r8_12_fiq[i] = c.R[8 + i];
    else for (int i = 0; i < 5; ++i) c.r8_12_user[i] = c.R[8 + i];
    SsState s = like;
    for (int i = 0; i < 16; ++i) s.R[i] = c.R[i];
    for (int i = 0; i < 5; ++i) { s.R[8 + i] = c.r8_12_user[i]; s.fiq[i] = c.r8_12_fiq[i]; }
    s.R[13] = c.banked_sp[Bank_User]; s.R[14] = c.banked_lr[Bank_User];
    s.fiq[5] = c.banked_sp[Bank_FIQ]; s.fiq[6] = c.banked_lr[Bank_FIQ];
    s.svc[0] = c.banked_sp[Bank_Supervisor]; s.svc[1] = c.banked_lr[Bank_Supervisor];
    s.abt[0] = c.banked_sp[Bank_Abort]; s.abt[1] = c.banked_lr[Bank_Abort];
    s.irq[0] = c.banked_sp[Bank_IRQ]; s.irq[1] = c.banked_lr[Bank_IRQ];
    s.und[0] = c.banked_sp[Bank_Undefined]; s.und[1] = c.banked_lr[Bank_Undefined];
    s.spsr[0] = c.banked_spsr[Bank_FIQ]; s.spsr[1] = c.banked_spsr[Bank_Supervisor]; s.spsr[2] = c.banked_spsr[Bank_Abort];
    s.spsr[3] = c.banked_spsr[Bank_IRQ]; s.spsr[4] = c.banked_spsr[Bank_Undefined];
    s.cpsr = pack(c.cpsr);
    return s;
}

struct VBus : Bus {
    SsReplay replay;
    uint8_t read8(uint32_t a) override { return (uint8_t)replay.read(a, 1); }
    uint16_t read16(uint32_t a) override { return (uint16_t)replay.read(a, 2); }
    uint32_t read32(uint32_t a) override { return replay.read(a, 4); }
    void write8(uint32_t a, uint8_t v) override { replay.write(a, 1, v); }
    void write16(uint32_t a, uint16_t v) override { replay.write(a, 2, v); }
    void write32(uint32_t a, uint32_t v) override { replay.write(a, 4, v); }
};

static const char* result_name(Interpreter::Result r) {
    switch (r) {
        case Interpreter::Result::Normal: return "normal";
        case Interpreter::Result::Branched: return "branched";
        case Interpreter::Result::ExceptionReturn: return "exception_return";
        case Interpreter::Result::Swi: return "swi";
        case Interpreter::Result::Undefined: return "undefined";
        default: return "not_implemented";
    }
}

int main(int argc, char** argv) {
    if (argc < 4) { std::fputs("usage: ss_interp stride max_per_file files...\n", stderr); return 2; }
    const uint32_t stride = std::atoi(argv[1]), max_per_file = std::atoi(argv[2]);
    uint32_t total_run = 0, total_pass = 0;
    for (int fi = 3; fi < argc; ++fi) {
        SsFile f;
        if (!f.open(argv[fi])) { std::fprintf(stderr, "cannot open %s\n", argv[fi]); return 2; }
        const std::string name = ss_name(argv[fi]);
        uint32_t ran = 0, passed = 0;
        for (uint32_t ti : ss_sample(f.count, stride, max_per_file)) {
            const SsTest t = f.get(ti);
            ++ran;
            const bool thumb = (t.init.cpsr >> 5) & 1;
            const uint32_t pc = t.init.R[15] - (thumb ? 4 : 8);        // the vector records the pipeline-visible PC
            Instr ins = thumb ? ThumbDecoder::decode((uint16_t)t.opcode, pc) : ArmDecoder::decode(t.opcode, pc);
            CPUState c; to_cpu(t.init, c); c.R[15] = pc;
            VBus bus; bus.replay.begin(t);
            const Interpreter::Result r = Interpreter::step(c, bus, ins, nullptr);
            const char* kind = result_name(r);
            if (r == Interpreter::Result::Swi) Interpreter::enter_swi(c, pc + (thumb ? 2 : 4), thumb);
            else if (r == Interpreter::Result::Undefined || r == Interpreter::Result::NotImplemented) {
                ss_print_failure(name, ti, t, kind, t.fin.cpsr, "STEP");
                continue;
            }
            else if (r == Interpreter::Result::Normal) c.R[15] = pc + (thumb ? 2 : 4);
            SsState got = from_cpu(c, t.fin);
            got.R[15] = c.R[15] + (c.cpsr.t ? 4 : 8);       // the vectors hold the pipeline-visible PC
            std::string why = ss_compare_state(got, t.fin);
            if (!ss_transactions_match(t, bus.replay)) ss_add_cause(why, "TRANS");
            if (why.empty()) { ++passed; continue; }
            ss_print_failure(name, ti, t, kind, got.cpsr, why);
        }
        ss_print_file(name, ran, passed);
        total_run += ran; total_pass += passed;
    }
    std::fprintf(stderr, "ran %u passed %u\n", total_run, total_pass);
    return 0;
}
