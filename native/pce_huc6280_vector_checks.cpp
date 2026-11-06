// Independent HuC6280 vectors (SingleStepTests/huc6280, MIT) against the pinned engine's interpreter (gate G10).
// Developer check, never built into a game: tools/pce_huc6280_vector_selftest.py builds it against the pinned runtime
// (`pce-runtime`) and prints one JSON line per opcode file. The vectors are one instruction on a flat 2 MiB bus, with the
// registers, the eight MPRs and the RAM cells the instruction touches before and after, and the cycle count. The corpus is
// expectations from another emulator, not a measurement of the chip.
//
//     retro_pce_huc6280_vector_checks V1_DIR
//
// Classes per opcode (a vector can fall in several):
//   refused          the engine stops on the opcode (the 22 reserved ones; the vectors give them as 2-cycle NOPs)
//   not_comparable   the vector's cycle list hit the corpus cap (500 cycles), so its final state is cut (block transfers)
//   registers/flags/pc/mpr/memory   the final state differs (flags = P with the B bit)
//   cycles_different the instruction's cycle count differs
//   both_equal       state and cycle count equal
#include "pce/runtime.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace {

struct State {
    std::uint8_t a, x, y, s, p;
    std::uint16_t pc;
    std::uint8_t mpr[8];
    std::vector<std::pair<std::uint32_t, std::uint8_t>> ram;
};

struct Vector {
    std::string name;
    State init, fin;
    std::uint32_t num_cycles;
    std::size_t recorded_cycles;
};

struct Reader {
    const std::vector<char>& bytes;
    std::size_t at = 0;
    template <class T>
    T get() {
        T value;
        std::memcpy(&value, &bytes[at], sizeof(T));
        at += sizeof(T);
        return value;
    }
};

State read_state(Reader& in) {
    State s{};
    in.get<std::int32_t>();
    s.a = in.get<std::uint8_t>();
    s.x = in.get<std::uint8_t>();
    s.y = in.get<std::uint8_t>();
    s.s = in.get<std::uint8_t>();
    s.p = in.get<std::uint8_t>();
    s.pc = in.get<std::uint16_t>();
    for (auto& m : s.mpr) m = in.get<std::uint8_t>();
    const auto n = in.get<std::int32_t>();
    for (int i = 0; i < n; ++i) {
        const auto address = in.get<std::uint32_t>();
        s.ram.emplace_back(address, in.get<std::uint8_t>());
    }
    return s;
}

std::vector<Vector> read_file(const std::string& path) {
    std::ifstream file(path, std::ios::binary);
    std::vector<char> buffer((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    std::vector<Vector> vectors;
    if (buffer.size() < 4) return vectors;
    Reader in{buffer};
    const auto count = in.get<std::uint32_t>();
    for (std::uint32_t i = 0; i < count; ++i) {
        Vector v;
        in.get<std::int32_t>();
        char name[51] = {};
        std::memcpy(name, &buffer[in.at], 50);
        in.at += 50;
        v.name = name;
        while (!v.name.empty() && (v.name.back() == ' ' || v.name.back() == '\0')) v.name.pop_back();
        in.get<std::uint32_t>();                       // the opcode
        v.init = read_state(in);
        v.fin = read_state(in);
        v.num_cycles = in.get<std::uint32_t>();
        v.recorded_cycles = in.get<std::uint32_t>();
        in.at += v.recorded_cycles * sizeof(std::uint32_t);
        vectors.push_back(std::move(v));
    }
    return vectors;
}

constexpr std::size_t kCorpusCap = 500;               // cycles the corpus records per vector at most

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "usage: retro_pce_huc6280_vector_checks V1_DIR\n");
        return 2;
    }
    auto bus = std::make_unique<pce::Bus>();
    bus->enable_vdc();                                // so ST0/ST1/ST2 do not fault
    for (auto& kind : bus->kind) kind = pce::BankKind::ram;
    int files = 0;
    for (unsigned opcode = 0; opcode < 256; ++opcode) {
        char path[1024];
        std::snprintf(path, sizeof path, "%s/%02x.json.bin", argv[1], opcode);
        if (!std::ifstream(path, std::ios::binary)) continue;
        ++files;
        unsigned n = 0, executed = 0, refused = 0, faulted = 0, not_comparable = 0, state_equal = 0, both_equal = 0;
        unsigned registers = 0, flags = 0, pc = 0, mpr = 0, memory = 0, cycles_equal = 0, cycles_different = 0;
        std::string first_state, first_cycles;
        for (const auto& v : read_file(path)) {
            ++n;
            pce::Cpu cpu;
            cpu.a = v.init.a; cpu.x = v.init.x; cpu.y = v.init.y; cpu.sp = v.init.s; cpu.p = v.init.p; cpu.pc = v.init.pc;
            for (int i = 0; i < 8; ++i) cpu.mpr[i] = v.init.mpr[i];
            cpu.clock_divisor = 3;
            cpu.mpr_latch = 0;
            for (const auto& cell : v.init.ram) (*bus->bytes)[cell.first] = cell.second;
            pce::Exit exit = pce::Exit::unsupported;
            bool fault = false;
            try {
                exit = pce::interpret_step(*bus, cpu, UINT64_MAX);
            } catch (const std::exception&) {
                fault = true;
            }
            if (fault) {
                ++faulted;
            } else if (exit != pce::Exit::executed) {
                ++refused;
            } else {
                ++executed;
                const bool comparable = v.recorded_cycles < kCorpusCap;
                bool different = false;
                if (!comparable) {
                    ++not_comparable;
                } else {
                    if (cpu.a != v.fin.a || cpu.x != v.fin.x || cpu.y != v.fin.y || cpu.sp != v.fin.s) { ++registers; different = true; }
                    if (cpu.p != v.fin.p) { ++flags; different = true; }
                    if (cpu.pc != v.fin.pc) { ++pc; different = true; }
                    if (std::memcmp(cpu.mpr.data(), v.fin.mpr, 8) != 0) { ++mpr; different = true; }
                    bool memory_differs = false;
                    for (const auto& cell : v.fin.ram)
                        if ((*bus->bytes)[cell.first] != cell.second) { memory_differs = true; break; }
                    if (memory_differs) { ++memory; different = true; }
                    if (different) { if (first_state.empty()) first_state = v.name; } else { ++state_equal; }
                }
                if (static_cast<std::uint32_t>(cpu.cycles) == v.num_cycles) {
                    ++cycles_equal;
                    if (comparable && !different) ++both_equal;
                } else {
                    ++cycles_different;
                    if (first_cycles.empty()) first_cycles = v.name;
                }
            }
            for (const auto& cell : v.init.ram) (*bus->bytes)[cell.first] = 0;
            for (const auto& cell : v.fin.ram) (*bus->bytes)[cell.first] = 0;
        }
        std::printf("{\"opcode\":\"%02X\",\"vectors\":%u,\"executed\":%u,\"refused\":%u,\"faulted\":%u,\"not_comparable\":%u,"
                    "\"state_equal\":%u,\"both_equal\":%u,\"registers\":%u,\"flags\":%u,\"pc\":%u,\"mpr\":%u,\"memory\":%u,"
                    "\"cycles_equal\":%u,\"cycles_different\":%u,\"first_state\":\"%s\",\"first_cycles\":\"%s\"}\n",
                    opcode, n, executed, refused, faulted, not_comparable, state_equal, both_equal, registers, flags, pc, mpr,
                    memory, cycles_equal, cycles_different, first_state.c_str(), first_cycles.c_str());
        std::fflush(stdout);
    }
    std::printf("{\"files\":%d}\n", files);
    return files == 256 ? 0 : 1;
}
