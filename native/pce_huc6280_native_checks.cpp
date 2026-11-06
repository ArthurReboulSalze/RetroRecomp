// Independent HuC6280 vectors (SingleStepTests/huc6280, MIT) against the pinned engine's translated (native) code (gate G10).
// Developer check, never built into a game: tools/pce_huc6280_native_vector_selftest.py builds one copy per generated native
// module (each links the module that translates the instruction bytes of its cases, guarded by the exact mapping and bytes) and
// prints one JSON line per case. The cases file has one line per vector, already moved to the canonical mapping by the tool:
//
//     retro_pce_huc6280_native_checks CASES_FILE
//
//   <name> <opcode> <cycles> <a> <x> <y> <s> <p> <pc> <fa> <fx> <fy> <fs> <fp> <fpc>
//   <n> <instruction byte addresses...> <n> <address value...> (RAM before) <n> <address value...> (RAM after)
//
// Each case is executed twice, on two buses that start the same (the translated step, then the interpreter), and compared with
// the vector and with each other. Per tier, what differs from the vector is listed by class: registers (A, X, Y, S), flags (P),
// pc, mpr, memory (the cells the vector lists) and cycles; "native_vs_interpreter" lists what differs between the two tiers:
// the registers, flags, pc, mapping, cycles, ticks, the VDC wait ticks, the transfer latch and the whole 64 KiB window the
// cases live in. A step that does not execute (a guard miss, an instruction the module does not translate, a fault) is reported
// as such, never counted as equal. The corpus is expectations from another emulator, not a measurement of the chip.
#include "pce/runtime.hpp"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace {

using Cells = std::vector<std::pair<std::uint32_t, std::uint8_t>>;

struct Case {
    std::string name;
    unsigned opcode = 0, cycles = 0;
    unsigned a = 0, x = 0, y = 0, s = 0, p = 0, pc = 0;
    unsigned fa = 0, fx = 0, fy = 0, fs = 0, fp = 0, fpc = 0;
    std::vector<std::uint32_t> site;
    Cells before, after;
};

constexpr std::uint32_t kWindow = 0x40000;                // canonical mapping: pages 0x20..0x27, physical 0x40000..0x4FFFF
constexpr std::size_t kWindowBytes = 0x10000;

Cells read_cells(std::istringstream& line) {
    std::size_t n = 0;
    line >> n;
    Cells cells;
    for (std::size_t i = 0; i < n; ++i) {
        unsigned address = 0, value = 0;
        line >> address >> value;
        cells.emplace_back(address, static_cast<std::uint8_t>(value));
    }
    return cells;
}

std::vector<Case> load(const char* path) {
    std::ifstream file(path);
    std::vector<Case> cases;
    std::string text;
    while (std::getline(file, text)) {
        if (text.empty()) continue;
        std::istringstream line(text);
        Case c;
        line >> c.name >> c.opcode >> c.cycles >> c.a >> c.x >> c.y >> c.s >> c.p >> c.pc >> c.fa >> c.fx >> c.fy >> c.fs >> c.fp >> c.fpc;
        std::size_t n = 0;
        line >> n;
        for (std::size_t i = 0; i < n; ++i) {
            unsigned address = 0;
            line >> address;
            c.site.push_back(address);
        }
        c.before = read_cells(line);
        c.after = read_cells(line);
        cases.push_back(std::move(c));
    }
    return cases;
}

struct Run {
    const char* verdict = "executed";                       // executed, miss, unsupported, budget, fault
    pce::Cpu cpu;
    std::array<std::uint8_t, kWindowBytes> window{};
};

std::unique_ptr<pce::Bus> make_bus() {
    auto bus = std::make_unique<pce::Bus>();
    bus->enable_vdc();                                       // so ST0/ST1/ST2 do not fault
    for (auto& kind : bus->kind) kind = pce::BankKind::ram;
    return bus;
}

Run run(pce::Bus& bus, const Case& c, bool native) {
    Run r;
    pce::Cpu& cpu = r.cpu;
    cpu.a = c.a; cpu.x = c.x; cpu.y = c.y; cpu.sp = c.s; cpu.p = c.p; cpu.pc = c.pc;
    for (int i = 0; i < 8; ++i) cpu.mpr[i] = static_cast<std::uint8_t>(0x20 + i);
    cpu.clock_divisor = 3;
    cpu.mpr_latch = 0;
    for (const auto& cell : c.before) (*bus.bytes)[cell.first] = cell.second;
    try {
        const pce::Exit exit = native ? pce::generated_step(bus, cpu, UINT64_MAX) : pce::interpret_step(bus, cpu, UINT64_MAX);
        r.verdict = exit == pce::Exit::executed ? "executed" : exit == pce::Exit::miss ? "miss"
                  : exit == pce::Exit::budget ? "budget" : "unsupported";
    } catch (const std::exception&) {
        r.verdict = "fault";
    }
    std::memcpy(r.window.data(), bus.bytes->data() + kWindow, kWindowBytes);
    // Every cell of the case lies in the window, and anything else the step wrote stays out of the next case: it is cleared whole.
    std::memset(bus.bytes->data() + kWindow, 0, kWindowBytes);
    return r;
}

// The classes in which a step that executed differs from the vector.
std::string against_vector(const Run& r, const Case& c) {
    std::string out;
    auto add = [&](const char* name) { out += std::string(out.empty() ? "" : ",") + "\"" + name + "\""; };
    const pce::Cpu& cpu = r.cpu;
    if (cpu.a != c.fa || cpu.x != c.fx || cpu.y != c.fy || cpu.sp != c.fs) add("registers");
    if (cpu.p != c.fp) add("flags");
    if (cpu.pc != c.fpc) add("pc");
    bool mapping = false;
    for (int i = 0; i < 8; ++i) mapping |= cpu.mpr[i] != 0x20 + i;     // the selection keeps the mapping unchanged
    if (mapping) add("mpr");
    bool memory = false;
    for (const auto& cell : c.after) memory |= r.window[cell.first - kWindow] != cell.second;
    if (memory) add("memory");
    if (static_cast<std::uint32_t>(cpu.cycles) != c.cycles) add("cycles");
    return "[" + out + "]";
}

// The fields in which two tiers that both executed differ.
std::string between_tiers(const Run& n, const Run& i) {
    std::string out;
    auto add = [&](const char* name) { out += std::string(out.empty() ? "" : ",") + "\"" + name + "\""; };
    if (n.cpu.a != i.cpu.a || n.cpu.x != i.cpu.x || n.cpu.y != i.cpu.y || n.cpu.sp != i.cpu.sp) add("registers");
    if (n.cpu.p != i.cpu.p) add("flags");
    if (n.cpu.pc != i.cpu.pc) add("pc");
    if (n.cpu.mpr != i.cpu.mpr) add("mpr");
    if (n.cpu.mpr_latch != i.cpu.mpr_latch) add("mpr_latch");
    if (n.cpu.cycles != i.cpu.cycles) add("cycles");
    if (n.cpu.ticks != i.cpu.ticks) add("ticks");
    if (n.cpu.vdc_wait_ticks != i.cpu.vdc_wait_ticks) add("vdc_wait_ticks");
    if (n.cpu.clock_divisor != i.cpu.clock_divisor) add("clock_divisor");
    if (n.window != i.window) add("memory");
    return "[" + out + "]";
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "usage: retro_pce_huc6280_native_checks CASES_FILE\n");
        return 2;
    }
    const auto cases = load(argv[1]);
    if (cases.empty()) {
        std::fprintf(stderr, "no cases in %s\n", argv[1]);
        return 2;
    }
    auto native_bus = make_bus();
    auto interpreter_bus = make_bus();
    for (const auto& c : cases) {
        const Run n = run(*native_bus, c, true);
        const Run i = run(*interpreter_bus, c, false);
        const bool n_ok = std::strcmp(n.verdict, "executed") == 0, i_ok = std::strcmp(i.verdict, "executed") == 0;
        std::printf("{\"vector\":\"%s\",\"opcode\":\"%02X\",\"native\":\"%s\",\"interpreter\":\"%s\","
                    "\"native_vs_vector\":%s,\"interpreter_vs_vector\":%s,\"native_vs_interpreter\":%s}\n",
                    c.name.c_str(), c.opcode, n.verdict, i.verdict, n_ok ? against_vector(n, c).c_str() : "null",
                    i_ok ? against_vector(i, c).c_str() : "null", n_ok && i_ok ? between_tiers(n, i).c_str() : "null");
    }
    std::printf("{\"cases\":%zu}\n", cases.size());
    std::fflush(stdout);
    return 0;
}
