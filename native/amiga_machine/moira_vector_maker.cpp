// Retro-Recomp development tool (MIT, ours): the "Moira vector maker" of tools/megadrive_moira_vectors.py (Mega Drive gate G10).
//
// It runs the Moira that vAmiga's Core compiles (MIT; the pinned revision, adapted by retrorecomp/amiga_vamiga.py) on states a driver chooses
// and prints what Moira did, so that the driver can write SingleStepTests-format vectors from it and replay them through the Mega Drive's
// native 68000 steps. Same client API as native/amiga_machine/amiga_vector_checks.cpp (read it first): only Moira's `sync`, `read*` and
// `write*` are replaced, by a flat 24-bit memory that logs every access with the clock at which Moira makes it (precise timing: the access
// is made two clocks into its bus cycle). It is a development check, never built into a game, and says what Moira does, not what the chip
// does: Moira is a model, and so is the Mega Drive's step.
//
// Mode 1, `--states <in> <out>`: one instruction per input line, decimal integers,
//   idx  d0-d7 (8)  a0-a6 (7)  usp ssp sr pc   nwords w0 ... w(n-1)   seed   nover [addr byte]*
//   (pc is the address of the instruction; w0 is its first word, w1 the one the prefetch queue holds as IRC, the rest follow in memory;
//    every other byte of the 24-bit space reads as a hash of (seed, address), the `nover` pairs set chosen bytes first.)
// and one output line per input line,
//   idx  clock  d0-d7 a0-a6 usp ssp sr pc ird irc (23)   naccess [kind clock addr size value]*   nbytes [addr initial final]*
//   (pc is architectural, the address of the next instruction; kind is 0 read, 1 write; `bytes` lists every byte the run touched.)
// Mode 2, `--bcd <abcd|sbcd|nbcd> <out>`: every state of the register form of that decimal instruction (ABCD D1,D0; SBCD D1,D0; NBCD D0)
//   over X and Z and the initial N, V, C (all clear or all set) and both operand bytes, the upper 24 bits of each register a fixed
//   pattern; two bytes per state, the low byte of D0 and the CCR, in the order
//   ((((nvc * 2 + x) * 2 + z) * 256 + src) * 256 + dst)  (NBCD has no src: (((nvc * 2 + x) * 2 + z) * 256 + dst)).
#include "vaconfig.h"
#include "Emulator.h"
#include "Amiga.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

using namespace vamiga;
using namespace vamiga::moira;

struct Access { char kind; long long clock; unsigned addr; unsigned size; unsigned value; };

static unsigned char mem[1 << 24];
static unsigned char known[1 << 24];      // 1: the byte has a value for this run (and its initial value is in `initial`)
static unsigned char initial[1 << 24];
static std::vector<Access> accesses;
static std::vector<unsigned> touched;
static unsigned long long run_seed = 0;

static unsigned long long splitmix(unsigned long long x) {
    x += 0x9E3779B97F4A7C15ull;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ull;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBull;
    return x ^ (x >> 31);
}

// The byte at an address, given its value on first use: chosen bytes were set before, every other byte is a hash of the seed and the address.
static unsigned char &byte_at(u32 address) {
    address &= 0xffffff;
    if (!known[address]) {
        known[address] = 1;
        mem[address] = (unsigned char)(splitmix(run_seed * 0x100000001B3ull + address) >> 24);
        initial[address] = mem[address];
        touched.push_back(address);
    }
    return mem[address];
}

static void set_initial(u32 address, unsigned char value) {
    address &= 0xffffff;
    if (!known[address]) { known[address] = 1; touched.push_back(address); }
    mem[address] = initial[address] = value;
}

static void forget() {
    for (unsigned a : touched) known[a] = 0;
    touched.clear();
}

namespace vamiga::moira {

extern bool (*rr_moira_native)(Moira &, u32 pc, u16 opcode);

// ---------------------------------------------------------------------------------------------- the CPU's client API, flat
void Moira::sync(int cycles) { clock += cycles; }

u8 Moira::read8(u32 addr) const {
    u8 v = byte_at(addr);
    accesses.push_back({'r', (long long)clock, addr & 0xffffff, 1, v});
    return v;
}
u16 Moira::read16(u32 addr) const {
    u16 v = (u16)(byte_at(addr) << 8 | byte_at(addr + 1));
    accesses.push_back({'r', (long long)clock, addr & 0xffffff, 2, v});
    return v;
}
u32 Moira::read32(u32 addr) const { return (u32)read16(addr) << 16 | read16(addr + 2); }
void Moira::write8(u32 addr, u8 val) const {
    accesses.push_back({'w', (long long)clock, addr & 0xffffff, 1, val});
    byte_at(addr) = val;
}
void Moira::write16(u32 addr, u16 val) const {
    accesses.push_back({'w', (long long)clock, addr & 0xffffff, 2, val});
    byte_at(addr) = (u8)(val >> 8); byte_at(addr + 1) = (u8)val;
}
void Moira::write32(u32 addr, u32 val) const { write16(addr, (u16)(val >> 16)); write16(addr + 2, (u16)val); }
// vAmiga's RESET handler soft-resets the whole Amiga; a stand-alone CPU has nothing to reset.
void Moira::didExecute(const char *, Instr, Mode, Size, u16) {}

// Access to the internals the harness needs, through the friend declaration the adaptation adds to class Moira.
struct RrAmigaSteps {
    // The state a run starts from: no pending flags, no interrupt, no leftover trace or stop from the previous run.
    static void clear(Moira &m) { m.flags = 0; m.reg.ipl = 0; m.ipl = 0; }
};

}  // namespace vamiga::moira

struct Start { u32 d[8], a[7], usp, ssp, sr, pc; std::vector<unsigned> words; unsigned long long seed; std::vector<std::pair<unsigned, unsigned>> over; };

static void begin(Moira &cpu, const Start &s) {
    forget();
    accesses.clear();
    run_seed = s.seed;
    for (size_t i = 0; i < s.over.size(); i++) set_initial(s.over[i].first, (unsigned char)s.over[i].second);
    for (size_t i = 0; i < s.words.size(); i++) {
        set_initial(s.pc + 2 * i, (unsigned char)(s.words[i] >> 8));
        set_initial(s.pc + 2 * i + 1, (unsigned char)s.words[i]);
    }
    RrAmigaSteps::clear(cpu);
    cpu.setClock(0);
    cpu.setSR((u16)s.sr);
    for (int i = 0; i < 8; i++) cpu.setD(i, s.d[i]);
    for (int i = 0; i < 7; i++) cpu.setA(i, s.a[i]);
    cpu.setUSP(s.usp);
    cpu.setISP(s.ssp);
    cpu.setPC(s.pc);
    cpu.setPC0(s.pc);
    cpu.setIRD((u16)s.words[0]);
    cpu.setIRC((u16)(s.words.size() > 1 ? s.words[1] : 0));
}

static bool read_start(FILE *f, long &idx, Start &s) {
    static std::vector<char> line(1 << 20);
    if (!fgets(line.data(), (int)line.size(), f)) return false;
    char *p = line.data();
    idx = strtol(p, &p, 10);
    for (auto &v : s.d) v = (u32)strtoul(p, &p, 10);
    for (auto &v : s.a) v = (u32)strtoul(p, &p, 10);
    s.usp = (u32)strtoul(p, &p, 10); s.ssp = (u32)strtoul(p, &p, 10); s.sr = (u32)strtoul(p, &p, 10); s.pc = (u32)strtoul(p, &p, 10);
    long n = strtol(p, &p, 10);
    s.words.clear();
    for (long i = 0; i < n; i++) s.words.push_back((unsigned)strtoul(p, &p, 10));
    s.seed = strtoull(p, &p, 10);
    n = strtol(p, &p, 10);
    s.over.clear();
    for (long i = 0; i < n; i++) { unsigned a = (unsigned)strtoul(p, &p, 10), b = (unsigned)strtoul(p, &p, 10); s.over.push_back({a, b}); }
    return true;
}

static int make_states(Moira &cpu, const char *in_path, const char *out_path) {
    FILE *in = fopen(in_path, "rb"), *out = fopen(out_path, "wb");
    if (!in || !out) return 2;
    Start s;
    long idx;
    long runs = 0;
    while (read_start(in, idx, s)) {
        begin(cpu, s);
        rr_moira_native = nullptr;
        cpu.execute();
        fprintf(out, "%ld %lld", idx, (long long)cpu.getClock());
        for (int i = 0; i < 8; i++) fprintf(out, " %u", (unsigned)cpu.getD(i));
        for (int i = 0; i < 7; i++) fprintf(out, " %u", (unsigned)cpu.getA(i));
        fprintf(out, " %u %u %u %u %u %u", (unsigned)cpu.getUSP(), (unsigned)cpu.getISP(), (unsigned)cpu.getSR(), (unsigned)(cpu.getPC() & 0xffffff),
                (unsigned)cpu.getIRD(), (unsigned)cpu.getIRC());
        fprintf(out, " %zu", accesses.size());
        for (auto &a : accesses) fprintf(out, " %d %lld %u %u %u", a.kind == 'w' ? 1 : 0, a.clock, a.addr, a.size, a.value);
        fprintf(out, " %zu", touched.size());
        for (unsigned a : touched) fprintf(out, " %u %u %u", a, (unsigned)initial[a], (unsigned)mem[a]);
        fprintf(out, "\n");
        runs++;
    }
    fclose(out);
    fclose(in);
    fprintf(stderr, "%ld states run\n", runs);
    return 0;
}

static int make_bcd(Moira &cpu, const std::string &kind, const char *out_path) {
    unsigned word;
    bool nbcd = false;
    if (kind == "abcd") word = 0xC101;           // ABCD D1,D0
    else if (kind == "sbcd") word = 0x8101;      // SBCD D1,D0
    else if (kind == "nbcd") { word = 0x4800; nbcd = true; }   // NBCD D0
    else return 2;
    FILE *out = fopen(out_path, "wb");
    if (!out) return 2;
    long long runs = 0;
    for (unsigned nvc = 0; nvc < 2; nvc++)
        for (unsigned x = 0; x < 2; x++)
            for (unsigned z = 0; z < 2; z++)
                for (unsigned src = 0; src < (nbcd ? 1u : 256u); src++)
                    for (unsigned dst = 0; dst < 256; dst++) {
                        Start s;
                        for (int i = 0; i < 8; i++) s.d[i] = 0x11223300u * (i + 1);
                        s.d[1] = 0xA5A5A500u | src;
                        s.d[0] = 0x5A5A5A00u | dst;
                        for (int i = 0; i < 7; i++) s.a[i] = 0x00200000u + 0x100u * i;
                        s.usp = 0x00300000u; s.ssp = 0x00310000u;
                        s.sr = 0x2700u | (x << 4) | (z << 2) | (nvc ? 0x0bu : 0u);
                        s.pc = 0x1000;
                        s.words = {word, 0x4e71, 0x4e71};
                        s.seed = 1;
                        begin(cpu, s);
                        rr_moira_native = nullptr;
                        cpu.execute();
                        unsigned char pair[2] = {(unsigned char)(cpu.getD(0) & 0xff), (unsigned char)(cpu.getSR() & 0x1f)};
                        // The upper 24 bits of D0 and all of D1 are not changed by the instruction.
                        if ((cpu.getD(0) & 0xffffff00u) != 0x5A5A5A00u || (!nbcd && cpu.getD(1) != (0xA5A5A500u | src)) || cpu.getPC() != 0x1002) {
                            fprintf(stderr, "unexpected state after %s %u %u\n", kind.c_str(), src, dst);
                            return 5;
                        }
                        fwrite(pair, 1, 2, out);
                        runs++;
                    }
    fclose(out);
    fprintf(stderr, "%lld states run\n", runs);
    return 0;
}

int main(int argc, char **argv) {
    Emulator emu;
    emu.initialize();
    emu.set(ConfigScheme::A500_ECS_1MB);
    Moira &cpu = emu.rrMain().cpu;
    cpu.setModel(Model::M68000, Model::M68000);
    if (argc < 4) return 2;
    // The harness must be running its own bus: a NOP at address 0x1000 executes, takes four clocks and reads one word from the flat memory.
    {
        Start s;
        for (auto &v : s.d) v = 0;
        for (auto &v : s.a) v = 0;
        s.usp = 0; s.ssp = 0x2000; s.sr = 0x2700; s.pc = 0x1000; s.words = {0x4e71, 0x4e71}; s.seed = 1;
        begin(cpu, s);
        rr_moira_native = nullptr;
        cpu.execute();
        if (cpu.getClock() != 4 || accesses.size() != 1 || accesses[0].addr != 0x1004 || cpu.getPC() != 0x1002) {
            fprintf(stderr, "the harness's bus is not in use (clock %lld, %zu accesses)\n", (long long)cpu.getClock(), accesses.size());
            return 4;
        }
    }
    int status;
    if (!strcmp(argv[1], "--states")) status = make_states(cpu, argv[2], argv[3]);
    else if (!strcmp(argv[1], "--bcd")) status = make_bcd(cpu, argv[2], argv[3]);
    else status = 2;
    fflush(stdout);
    fflush(stderr);
    std::_Exit(status);
}
