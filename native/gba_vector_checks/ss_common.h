// Original code of Retro-Recomp, MIT licence (the repository's LICENSE). No file of the vector suite and no ROM is part of it.
//
// What the three checks of tools/gba_vector_selftest.py share: the reader of the SingleStepTests/ARM7TDMI `.json.bin` files
// (MIT, generated from NanoBoyAdvance's model of the ARM7TDMI: they say what that model does, not what hardware does), the
// selection of vectors, the replay of a vector's data transactions as the bus of the code under test, the comparison, and the
// text the Python side parses.
//
// File format (little endian words): magic 0xD33DBAE0, vector count, then per vector a total size followed by four blocks, each
// {size, tag, payload}: the initial state, the final state (40 words each: R0-R15, the FIQ bank R8-R14, SVC, ABT, IRQ and UND
// R13-R14, CPSR, the five SPSRs, two pipeline words, the access flag), the transactions (a count, then records of six words:
// kind, size, address, data, cycle, access) and the opcode with its base address.
//
// What is compared, for one instruction: R0-R15, every bank, CPSR, the five SPSRs and the ordered data reads and writes (kind
// kKindRead and kKindWrite). Not compared: instruction fetches (kind kKindFetch), the cycle numbers and the access flags: the
// suite itself says it does not record them reliably.
//
// Output, one line each, parsed by tools/gba_vector_selftest.py (which names the categories of expected divergence):
//   FILE <name> <vectors run> <vectors passed>
//   FAIL <name> <index> <opcode hex> <thumb 0|1> <mode hex> <kind> <CPSR xor hex> <causes, comma separated>
// `kind` says how the instruction ended (the interpreter's result, or "ran" / "unimplemented" for generated code); a cause is a
// register or bank word that differs (R3, fiq5, svc1, spsr2...), CPSR, TRANS (the data transactions) or STEP (the instruction
// did not run to a state that can be compared: undefined or not implemented).
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

constexpr uint32_t kSsMagic = 0xD33DBAE0u;
constexpr uint32_t kKindFetch = 0, kKindRead = 1, kKindWrite = 2;

struct SsState { uint32_t R[16], fiq[7], svc[2], abt[2], irq[2], und[2], cpsr, spsr[5], pipe[2], access; };
struct SsTrans { uint32_t kind, size, addr, data, cycle, access; };
struct SsTest { SsState init, fin; std::vector<SsTrans> tr; uint32_t opcode, base; };

inline uint32_t ss_rd32(const std::vector<uint8_t>& b, size_t p) { uint32_t v; std::memcpy(&v, &b[p], 4); return v; }

inline SsState ss_load_state(const std::vector<uint8_t>& b, size_t p) {
    SsState s;
    p += 8;                                         // the block's size and tag
    uint32_t v[40]; std::memcpy(v, &b[p], sizeof v);
    std::memcpy(s.R, v, 64); std::memcpy(s.fiq, v + 16, 28); std::memcpy(s.svc, v + 23, 8);
    std::memcpy(s.abt, v + 25, 8); std::memcpy(s.irq, v + 27, 8); std::memcpy(s.und, v + 29, 8);
    s.cpsr = v[31]; std::memcpy(s.spsr, v + 32, 20); s.pipe[0] = v[37]; s.pipe[1] = v[38]; s.access = v[39];
    return s;
}

struct SsFile {
    std::vector<uint8_t> b; uint32_t count = 0; std::vector<size_t> offs;
    bool open(const char* path) {
        FILE* f = std::fopen(path, "rb"); if (!f) return false;
        std::fseek(f, 0, SEEK_END); long n = std::ftell(f); std::fseek(f, 0, SEEK_SET);
        b.resize(n);
        if (std::fread(b.data(), 1, n, f) != (size_t)n) { std::fclose(f); return false; }
        std::fclose(f);
        if (b.size() < 8 || ss_rd32(b, 0) != kSsMagic) return false;
        count = ss_rd32(b, 4); size_t p = 8;
        for (uint32_t i = 0; i < count; ++i) { offs.push_back(p); p += ss_rd32(b, p); }
        return p <= b.size();
    }
    SsTest get(uint32_t ti) const {
        SsTest t; size_t q = offs[ti] + 4;
        size_t s1 = ss_rd32(b, q); t.init = ss_load_state(b, q); q += s1;
        size_t s2 = ss_rd32(b, q); t.fin = ss_load_state(b, q); q += s2;
        size_t s3 = ss_rd32(b, q); uint32_t nt = ss_rd32(b, q + 8); size_t tp = q + 12;
        for (uint32_t k = 0; k < nt; ++k) { SsTrans x; std::memcpy(&x, &b[tp], 24); tp += 24; t.tr.push_back(x); }
        q += s3; t.opcode = ss_rd32(b, q + 8); t.base = ss_rd32(b, q + 12);
        return t;
    }
};

// The file's name without its folder and its `.json.bin` suffix: the key of every line of output.
inline std::string ss_name(const char* path) {
    std::string s(path);
    size_t cut = s.find_last_of("/\\"); if (cut != std::string::npos) s.erase(0, cut + 1);
    const std::string suffix = ".json.bin";
    if (s.size() > suffix.size() && s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0) s.resize(s.size() - suffix.size());
    return s;
}

// The evenly spaced selection of one file: every `stride`-th vector, at most `max_per_file` of them. The generator and the
// runner both take it from here, so they cannot disagree on which vectors a generated function belongs to.
inline std::vector<uint32_t> ss_sample(uint32_t count, uint32_t stride, uint32_t max_per_file) {
    std::vector<uint32_t> picked;
    if (stride == 0) stride = 1;
    for (uint32_t ti = 0; ti < count && picked.size() < max_per_file; ti += stride) picked.push_back(ti);
    return picked;
}

// The bus of the code under test: data reads are answered from the vector's recorded reads, in order (a narrower access takes
// its bytes from the recorded wider one), data writes are recorded to be compared. Instruction fetches are not the bus's business.
struct SsReplay {
    const SsTest* test = nullptr; size_t pos = 0; bool starved = false;
    std::vector<SsTrans> reads, writes;
    void begin(const SsTest& t) { test = &t; pos = 0; starved = false; reads.clear(); writes.clear(); }
    uint32_t read(uint32_t addr, uint32_t size) {
        SsTrans r{kKindRead, size, addr, 0, 0, 0};
        while (pos < test->tr.size() && test->tr[pos].kind != kKindRead) ++pos;
        if (pos >= test->tr.size()) { starved = true; reads.push_back(r); return 0; }
        const SsTrans& v = test->tr[pos++];
        uint32_t d = v.data;
        if (size < v.size) { d >>= 8 * (addr & (v.size - 1)); if (size == 1) d &= 0xFF; else if (size == 2) d &= 0xFFFF; }
        r.data = d; reads.push_back(r);
        return d;
    }
    void write(uint32_t addr, uint32_t size, uint32_t value) { writes.push_back({kKindWrite, size, addr, value, 0, 0}); }
};

// Names the words of `got` that differ from `want`, as the causes of a failure ("R3,CPSR,spsr1"); empty when they are equal.
inline std::string ss_compare_state(const SsState& got, const SsState& want) {
    std::string why;
    for (int i = 0; i < 16; ++i) if (got.R[i] != want.R[i]) why += "R" + std::to_string(i) + ",";
    for (int i = 0; i < 7; ++i) if (got.fiq[i] != want.fiq[i]) why += "fiq" + std::to_string(i) + ",";
    for (int i = 0; i < 2; ++i) {
        if (got.svc[i] != want.svc[i]) why += "svc" + std::to_string(i) + ",";
        if (got.abt[i] != want.abt[i]) why += "abt" + std::to_string(i) + ",";
        if (got.irq[i] != want.irq[i]) why += "irq" + std::to_string(i) + ",";
        if (got.und[i] != want.und[i]) why += "und" + std::to_string(i) + ",";
    }
    if (got.cpsr != want.cpsr) why += "CPSR,";
    for (int i = 0; i < 5; ++i) if (got.spsr[i] != want.spsr[i]) why += "spsr" + std::to_string(i) + ",";
    if (!why.empty()) why.pop_back();
    return why;
}

inline void ss_add_cause(std::string& causes, const char* cause) { if (!causes.empty()) causes += ','; causes += cause; }

// Whether the replayed bus saw the recorded data transactions: the same number of reads and of writes, writes at the same
// aligned address, of the same size and value, reads at the same aligned address and size. The suite records the raw address of
// a misaligned access and the engine aligns it, so addresses are compared aligned; a halfword read at an odd address may be
// issued as a byte read (the ARMv4 behaviour of LDRSH), which is accepted.
inline bool ss_transactions_match(const SsTest& t, const SsReplay& bus) {
    std::vector<SsTrans> wr, rd;
    for (const SsTrans& x : t.tr) { if (x.kind == kKindWrite) wr.push_back(x); else if (x.kind == kKindRead) rd.push_back(x); }
    if (bus.starved || wr.size() != bus.writes.size() || rd.size() != bus.reads.size()) return false;
    for (size_t i = 0; i < wr.size(); ++i)
        if ((wr[i].addr & ~(wr[i].size - 1)) != (bus.writes[i].addr & ~(bus.writes[i].size - 1)) || wr[i].size != bus.writes[i].size
            || wr[i].data != bus.writes[i].data) return false;
    for (size_t i = 0; i < rd.size(); ++i) {
        const SsTrans& g = bus.reads[i];
        const bool same_size = rd[i].size == g.size || (rd[i].size == 2 && g.size == 1 && (g.addr & 1));
        if ((rd[i].addr & ~(rd[i].size - 1)) != (g.addr & ~(rd[i].size - 1)) || !same_size) return false;
    }
    return true;
}

inline void ss_print_failure(const std::string& name, uint32_t index, const SsTest& t, const char* kind, uint32_t cpsr_got,
                             const std::string& causes) {
    std::printf("FAIL %s %u %08X %d %02X %s %08X %s\n", name.c_str(), index, t.opcode, (int)((t.init.cpsr >> 5) & 1),
                t.init.cpsr & 31, kind, cpsr_got ^ t.fin.cpsr, causes.empty() ? "-" : causes.c_str());
}

inline void ss_print_file(const std::string& name, uint32_t ran, uint32_t passed) {
    std::printf("FILE %s %u %u\n", name.c_str(), ran, passed);
}
