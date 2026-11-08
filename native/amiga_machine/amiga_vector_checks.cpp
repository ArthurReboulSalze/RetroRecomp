// Retro-Recomp Amiga (MIT, ours): independent MC68000 vectors replayed through the Amiga's CPU, Moira as vAmiga builds it (gate G10).
//
// The program under test is the Moira that vAmiga's Core compiles (MIT; the pinned revision, adapted by retrorecomp/amiga_vamiga.py): the
// instruction templates, the flags, the exception code and the configuration (precise timing, address errors and function codes on) are
// vAmiga's own, linked from its static library. Only the CPU's client API is replaced, the way a stand-alone Moira host does it: sync()
// advances the clock, and read/write go to a flat 24-bit RAM that logs every access with the clock at which Moira makes it. vAmiga's own
// versions of those functions (Components/CPU/CPU.cpp) drive Agnus and the Amiga's memory map; they are shadowed by the definitions here
// (the harness is linked with --allow-multiple-definition and the first definition wins; the program checks at start that it did).
// That isolates the CPU from the machine: no chip-RAM contention, no custom chips, no ROM overlay. It shows CPU behaviour against a
// MAME-made oracle, not the Amiga's hardware, gameplay or latency.
//
// Two paths run every vector, from the same initial state:
//   interpreter  Moira::execute() with no hook: the jump table, as in the reference run;
//   native step  Moira::execute() with the hook set to the lookup of the steps the converter's own generator wrote (retrorecomp/
//                amiga_codegen.py): rr_amiga_lookup() finds the instruction at the pc for the latched opcode, and the hook runs it. A vector with no step stays on the interpreter and is counted.
// Both are compared with the vector (registers, SR under its mask, PC, the two queue words, the bytes of RAM, the clocks, and the order and
// clock of the bus accesses where the fixture has them), and the two paths with each other on everything, access by access.
//
// Input: one vector per line, decimal integers (written by tools/amiga_vector_selftest.py):
//   idx want_cycles sr_mask want_stopped ntx [kind clock addr size]*ntx  init[21] final[21]  n_in [addr value]*  n_out [addr value]*
// (ntx = -1: the fixture has no transaction list; init/final = d0-d7 a0-a6 usp ssp sr pc ird irc, the pc already architectural.)
// Output: one JSON object per line. `--opcode-map <file>` writes the table the generator needs and exits.
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
static std::vector<Access> accesses;
static std::vector<unsigned> touched;
static bool recording = true;

static unsigned char *flat(u32 address) { return &mem[address & 0xffffff]; }

namespace vamiga::moira {

extern const char *rr_moira_exec_name[65536];
extern bool (*rr_moira_native)(Moira &, u32 pc, u16 opcode);

// ---------------------------------------------------------------------------------------------- the CPU's client API, flat
void Moira::sync(int cycles) { clock += cycles; }

u8 Moira::read8(u32 addr) const {
    u8 v = *flat(addr);
    if (recording) accesses.push_back({'r', (long long)clock, addr & 0xffffff, 1, v});
    return v;
}
u16 Moira::read16(u32 addr) const {
    u16 v = (u16)(*flat(addr) << 8 | *flat(addr + 1));
    if (recording) accesses.push_back({'r', (long long)clock, addr & 0xffffff, 2, v});
    return v;
}
u32 Moira::read32(u32 addr) const { return (u32)read16(addr) << 16 | read16(addr + 2); }
void Moira::write8(u32 addr, u8 val) const {
    if (recording) accesses.push_back({'w', (long long)clock, addr & 0xffffff, 1, val});
    touched.push_back(addr & 0xffffff);
    *flat(addr) = val;
}
void Moira::write16(u32 addr, u16 val) const {
    if (recording) accesses.push_back({'w', (long long)clock, addr & 0xffffff, 2, val});
    touched.push_back(addr & 0xffffff); touched.push_back((addr + 1) & 0xffffff);
    *flat(addr) = (u8)(val >> 8); *flat(addr + 1) = (u8)val;
}
void Moira::write32(u32 addr, u32 val) const { write16(addr, (u16)(val >> 16)); write16(addr + 2, (u16)val); }
// vAmiga's RESET handler soft-resets the whole Amiga; a stand-alone CPU has nothing to reset.
void Moira::didExecute(const char *, Instr, Mode, Size, u16) {}

// Access to what the templates and the harness need, through the friend declaration the adaptation adds to class Moira.
struct RrAmigaSteps {
    static int dump(Moira &m, FILE *out) {
        int n = 0;
        for (int id = 0; id < 65536; id++) {
            const char *name = rr_moira_exec_name[id];
            if (!name || !m.info) continue;
            const InstrInfo &i = m.info[id];
            fprintf(out, "%04x %s %d %d %d\n", id, name, (int)i.I, (int)i.M, (int)i.S);
            n++;
        }
        return n;
    }
    // The state a vector starts from: no pending flags, no interrupt, no leftover trace or stop from the previous vector.
    static void clear(Moira &m) { m.flags = 0; m.reg.ipl = 0; m.ipl = 0; }
    static bool stopped(Moira &m) { return (m.flags & State::STOPPED) != 0; }
};

}  // namespace vamiga::moira

// ------------------------------------------------------------------------------------------------------- the native steps
#ifdef RR_VECTOR_STEPS
typedef void (*RrAmigaCode)(void *);
extern "C" RrAmigaCode rr_amiga_lookup(uint32_t pc, uint16_t opcode);
extern "C" const uint32_t *rr_amiga_run_flags;
// One vector, one instruction: a run-loop flag stays up so that the code never goes on to the next one.
static const uint32_t stop_after_one = 1;
static bool step_ran;
static bool native_hook(Moira &m, u32 pc, u16 op) {
    if (RrAmigaCode run = rr_amiga_lookup(pc, op)) {
        rr_amiga_run_flags = &stop_after_one;
        run(&m);
        step_ran = true;
        return true;
    }
    return false;
}
#endif

// ---------------------------------------------------------------------------------------------------------------- a vector
struct Vector {
    long idx = 0; long long want_cycles = 0; unsigned sr_mask = 0xffff; int want_stopped = 0; long ntx = -1;
    struct Tx { char kind; long long start; unsigned addr; unsigned size; };
    std::vector<Tx> tx;
    unsigned long init[21], fin[21];
    std::vector<std::pair<unsigned, unsigned>> ram_in, ram_out;
};

static const char *REG_NAMES[21] = {"d0","d1","d2","d3","d4","d5","d6","d7","a0","a1","a2","a3","a4","a5","a6","usp","ssp","sr","pc","ird","irc"};

struct Final { unsigned long regs[21]; long long clock; bool stopped; std::vector<Access> log; };

static void load(Moira &cpu, const Vector &v) {
    for (unsigned a : touched) mem[a] = 0;
    touched.clear();
    for (auto &p : v.ram_in) { mem[p.first & 0xffffff] = (unsigned char)p.second; touched.push_back(p.first & 0xffffff); }
    RrAmigaSteps::clear(cpu);
    cpu.setClock(0);
    cpu.setSR((u16)v.init[17]);
    for (int i = 0; i < 8; i++) cpu.setD(i, (u32)v.init[i]);
    for (int i = 0; i < 7; i++) cpu.setA(i, (u32)v.init[8 + i]);
    cpu.setUSP((u32)v.init[15]);
    cpu.setISP((u32)v.init[16]);
    cpu.setPC((u32)v.init[18]);
    cpu.setPC0((u32)v.init[18]);
    cpu.setIRD((u16)v.init[19]);
    cpu.setIRC((u16)v.init[20]);
    accesses.clear();
#ifdef RR_VECTOR_STEPS
    step_ran = false;
#endif
}

static Final capture(Moira &cpu) {
    Final f;
    for (int i = 0; i < 8; i++) f.regs[i] = cpu.getD(i);
    for (int i = 0; i < 7; i++) f.regs[8 + i] = cpu.getA(i);
    f.regs[15] = cpu.getUSP(); f.regs[16] = cpu.getISP(); f.regs[17] = cpu.getSR(); f.regs[18] = cpu.getPC() & 0xffffff;
    f.regs[19] = cpu.getIRD(); f.regs[20] = cpu.getIRC();
    f.clock = cpu.getClock(); f.stopped = RrAmigaSteps::stopped(cpu); f.log = accesses;
    return f;
}

static std::string json_escape(const std::string &s) { return s; }

static bool read_vector(FILE *f, Vector &v) {
    static std::vector<char> line(1 << 22);
    if (!fgets(line.data(), (int)line.size(), f)) return false;
    char *p = line.data();
    v.idx = strtol(p, &p, 10); v.want_cycles = strtoll(p, &p, 10); v.sr_mask = (unsigned)strtoul(p, &p, 10);
    v.want_stopped = (int)strtol(p, &p, 10); v.ntx = strtol(p, &p, 10);
    v.tx.clear();
    for (long i = 0; i < v.ntx; i++) {
        Vector::Tx t; t.kind = (char)strtol(p, &p, 10) ? 'w' : 'r'; t.start = strtoll(p, &p, 10);
        t.addr = (unsigned)strtoul(p, &p, 10); t.size = (unsigned)strtoul(p, &p, 10); v.tx.push_back(t);
    }
    for (int i = 0; i < 21; i++) v.init[i] = strtoul(p, &p, 10);
    for (int i = 0; i < 21; i++) v.fin[i] = strtoul(p, &p, 10);
    long n = strtol(p, &p, 10); v.ram_in.clear();
    for (long i = 0; i < n; i++) { unsigned a = (unsigned)strtoul(p, &p, 10), b = (unsigned)strtoul(p, &p, 10); v.ram_in.push_back({a, b}); }
    n = strtol(p, &p, 10); v.ram_out.clear();
    for (long i = 0; i < n; i++) { unsigned a = (unsigned)strtoul(p, &p, 10), b = (unsigned)strtoul(p, &p, 10); v.ram_out.push_back({a, b}); }
    return true;
}

int main(int argc, char **argv) {
    Emulator emu;
    emu.initialize();
    emu.set(ConfigScheme::A500_ECS_1MB);
    Moira &cpu = emu.rrMain().cpu;
    cpu.setModel(Model::M68000, Model::M68000);
    if (argc > 2 && !strcmp(argv[1], "--opcode-map")) {
        FILE *out = fopen(argv[2], "w");
        if (!out) return 2;
        int n = RrAmigaSteps::dump(cpu, out);
        fclose(out);
        fprintf(stderr, "%d opcodes with a handler\n", n);
        fflush(stderr);
        std::_Exit(n == 65536 ? 0 : 3);
    }
    if (argc < 2) return 2;
    FILE *in = fopen(argv[1], "rb");
    if (!in) return 2;
    bool use_steps = false;
#ifdef RR_VECTOR_STEPS
    use_steps = true;
#endif
    // The harness must be running its own bus: a NOP at address 0x1000 executes, takes four clocks and reads two words from the flat RAM.
    mem[0x1000] = 0x4e; mem[0x1001] = 0x71; mem[0x1002] = 0x4e; mem[0x1003] = 0x71; mem[0x1004] = 0x4e; mem[0x1005] = 0x71;
    {
        cpu.setSR(0x2700); cpu.setClock(0); cpu.setPC(0x1000); cpu.setPC0(0x1000); cpu.setIRD(0x4e71); cpu.setIRC(0x4e71);
        accesses.clear(); rr_moira_native = nullptr;
        cpu.execute();
        if (cpu.getClock() != 4 || accesses.size() != 1 || accesses[0].addr != 0x1004 || cpu.getPC() != 0x1002) {
            fprintf(stderr, "the harness's bus is not in use (clock %lld, %zu accesses)\n", (long long)cpu.getClock(), accesses.size());
            return 4;
        }
        for (int i = 0; i < 6; i++) mem[0x1000 + i] = 0;
        accesses.clear();
    }
    Vector v;
    while (read_vector(in, v)) {
        // ---- the interpreter
        rr_moira_native = nullptr;
        load(cpu, v);
        cpu.execute();
        Final interp = capture(cpu);
        // ram check: the listed final bytes, and every other byte written must still hold its initial value
        long bad_ram = 0;
        for (auto &p : v.ram_out) if (mem[p.first & 0xffffff] != p.second) bad_ram++;
        {
            std::vector<unsigned> seen;
            for (auto &a : interp.log) if (a.kind == 'w') for (unsigned k = 0; k < a.size; k++) seen.push_back((a.addr + k) & 0xffffff);
            for (unsigned a : seen) {
                bool listed = false, initial_known = false; unsigned initial = 0;
                for (auto &p : v.ram_out) if ((p.first & 0xffffff) == a) { listed = true; break; }
                if (listed) continue;
                for (auto &p : v.ram_in) if ((p.first & 0xffffff) == a) { initial_known = true; initial = p.second; break; }
                if (mem[a] != (initial_known ? initial : 0)) bad_ram++;
            }
        }
        std::string bad_regs, detail;
        for (int i = 0; i < 21; i++) {
            unsigned long g = interp.regs[i], w = v.fin[i];
            if (i == 18) { g &= 0xffffff; w &= 0xffffff; }
            if (i == 17) { g &= v.sr_mask; w &= v.sr_mask; }
            if (g != w) {
                bad_regs += REG_NAMES[i]; bad_regs += ' ';
                char text[64]; snprintf(text, sizeof text, "%s=%lx/%lx ", REG_NAMES[i], g, w); detail += text;
            }
        }
        // ---- the bus: kind, word address and size one to one, and the clock of each access against the vector's start of cycle
        long bus_order = 0, bus_time = 0, offset = 0; bool offset_set = false;
        if (v.ntx >= 0) {
            size_t k = 0;
            for (auto &t : v.tx) {
                if (k >= interp.log.size()) { bus_order++; continue; }
                const Access &x = interp.log[k++];
                if (x.kind != t.kind || (x.addr & ~1u) != (t.addr & ~1u) || x.size != t.size) bus_order++;
                long d = (long)(x.clock - t.start);
                if (!offset_set) { offset = d; offset_set = true; } else if (d != offset) bus_time++;
            }
            if (k != interp.log.size()) bus_order++;
        }
        // ---- the native step, from the same initial state
        int native = 0;           // 0: no step for this instruction, 1: the step ran and equals the interpreter, 2: it ran and differs
        std::string native_diff;
        if (use_steps) {
#ifdef RR_VECTOR_STEPS
            rr_moira_native = native_hook;
            load(cpu, v);
            cpu.execute();
            rr_moira_native = nullptr;
            if (step_ran) {
                Final nat = capture(cpu);
                native = 1;
                for (int i = 0; i < 21; i++) if (nat.regs[i] != interp.regs[i]) { native = 2; native_diff += REG_NAMES[i]; native_diff += ' '; }
                if (nat.clock != interp.clock) { native = 2; native_diff += "clock "; }
                if (nat.stopped != interp.stopped) { native = 2; native_diff += "stopped "; }
                if (nat.log.size() != interp.log.size()) { native = 2; native_diff += "bus-count "; }
                else for (size_t i = 0; i < nat.log.size(); i++) {
                    const Access &a = nat.log[i], &b = interp.log[i];
                    if (a.kind != b.kind || a.clock != b.clock || a.addr != b.addr || a.size != b.size || a.value != b.value) { native = 2; native_diff += "bus "; break; }
                }
            }
#endif
        }
        // For a vector that differs on the bus: the accesses Moira made, "kind:address:size:clock" in order, for the report.
        std::string seq;
        if (bus_order || bus_time) for (auto &a : interp.log) {
            char text[64]; snprintf(text, sizeof text, "%c:%x:%u:%lld ", a.kind, a.addr, a.size, a.clock); seq += text;
        }
        printf("{\"i\":%ld,\"regs\":\"%s\",\"detail\":\"%s\",\"ram\":%ld,\"cyc\":%lld,\"bo\":%ld,\"bt\":%ld,\"off\":%ld,\"stop\":%d,\"nat\":%d,\"nd\":\"%s\",\"seq\":\"%s\"}\n",
               v.idx, bad_regs.c_str(), detail.c_str(), bad_ram, interp.clock, bus_order, bus_time, offset, interp.stopped ? 1 : 0, native,
               json_escape(native_diff).c_str(), seq.c_str());
    }
    fflush(stdout);
    std::_Exit(0);
}
