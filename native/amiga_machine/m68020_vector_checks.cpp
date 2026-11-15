// Retro-Recomp Amiga (MIT, ours): the Amiga 1200's CPU, Moira's 68EC020 as vAmiga builds it, against an independent 68EC020 (gate G10).
//
// The oracle is Musashi (Karl Stenerud, MIT), compiled for this check only, as a 68EC020, from the copy the workspace already holds; it is
// another author's model of the same CPU, not the hardware. The program under test is the Moira that vAmiga's Core compiles (MIT; the pinned
// revision, adapted by retrorecomp/amiga_vamiga.py), set to the 68EC020, with its client API replaced by the same flat 24-bit memory (as
// amiga_vector_checks.cpp does for the 68000; the harness is linked with --allow-multiple-definition so these definitions come first).
//
// Each case: a random state (data and address registers, both stack pointers, a supervisor or user SR with T and M clear and a random
// interrupt mask, an even PC), a random opcode at the PC followed by the random bytes of the memory, which supply the extension words. Both
// CPUs run one instruction from that same state and that same memory. Compared: D0-D7, A0-A6, USP, ISP, SR, PC and every byte either one
// wrote. Not compared: the clocks (Musashi's 68020 timings are tables of its own), the prefetch queue, the cache. A case where either
// CPU stops (STOP) or halts is counted apart. The output is one JSON line per case that differs (the opcode, Moira's handler, the fields),
// then the counts; the classification into families with written reasons is tools/amiga_m68020_vectors.py's.
#include "vaconfig.h"
#include "Emulator.h"
#include "Amiga.h"

extern "C" {
#include "m68k.h"
}

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>

using namespace vamiga;
using namespace vamiga::moira;

static unsigned char ram[1 << 24];
static std::vector<unsigned char> base;
static std::map<unsigned, unsigned char> written;     // the bytes the CPU of the current run wrote, by address

static void store(unsigned a, unsigned char v) { a &= 0xffffff; written[a] = v; ram[a] = v; }

// ------------------------------------------------------------------------------------------------- Musashi's memory
extern "C" {
unsigned int m68k_read_memory_8(unsigned int a) { return ram[a & 0xffffff]; }
unsigned int m68k_read_memory_16(unsigned int a) { return (unsigned)ram[a & 0xffffff] << 8 | ram[(a + 1) & 0xffffff]; }
unsigned int m68k_read_memory_32(unsigned int a) { return m68k_read_memory_16(a) << 16 | m68k_read_memory_16(a + 2); }
unsigned int m68k_read_disassembler_8(unsigned int a) { return m68k_read_memory_8(a); }
unsigned int m68k_read_disassembler_16(unsigned int a) { return m68k_read_memory_16(a); }
unsigned int m68k_read_disassembler_32(unsigned int a) { return m68k_read_memory_32(a); }
void m68k_write_memory_8(unsigned int a, unsigned int v) { store(a, (unsigned char)v); }
void m68k_write_memory_16(unsigned int a, unsigned int v) { store(a, (unsigned char)(v >> 8)); store(a + 1, (unsigned char)v); }
void m68k_write_memory_32(unsigned int a, unsigned int v) { m68k_write_memory_16(a, v >> 16); m68k_write_memory_16(a + 2, v & 0xffff); }
}

namespace vamiga::moira {

extern const char *rr_moira_exec_name[65536];

// ------------------------------------------------------------------------------------------------- Moira's memory, the same bytes
void Moira::sync(int cycles) { clock += cycles; }
u8 Moira::read8(u32 addr) const { return ram[addr & 0xffffff]; }
u16 Moira::read16(u32 addr) const { return (u16)(ram[addr & 0xffffff] << 8 | ram[(addr + 1) & 0xffffff]); }
u32 Moira::read32(u32 addr) const { return (u32)read16(addr) << 16 | read16(addr + 2); }
void Moira::write8(u32 addr, u8 val) const { store(addr, val); }
void Moira::write16(u32 addr, u16 val) const { store(addr, (u8)(val >> 8)); store(addr + 1, (u8)val); }
void Moira::write32(u32 addr, u32 val) const { write16(addr, (u16)(val >> 16)); write16(addr + 2, (u16)val); }
void Moira::didExecute(const char *, Instr, Mode, Size, u16) {}

struct RrAmigaSteps {
    static void clear(Moira &m) { m.flags = 0; m.reg.ipl = 0; m.ipl = 0; }
    static bool stopped(Moira &m) { return (m.flags & (State::STOPPED | State::HALTED)) != 0; }
};

}  // namespace vamiga::moira

// ------------------------------------------------------------------------------------------------- the cases
static unsigned long long rng_state = 0x243F6A8885A308D3ull;
static unsigned rnd() { rng_state ^= rng_state << 13; rng_state ^= rng_state >> 7; rng_state ^= rng_state << 17; return (unsigned)(rng_state >> 16); }

struct Regs { unsigned d[8], a[7], usp, isp, sr, pc; bool stopped; };
static const char *NAMES[18] = {"d0","d1","d2","d3","d4","d5","d6","d7","a0","a1","a2","a3","a4","a5","a6","usp","isp","sr"};

static unsigned random_address() { unsigned a = rnd() & 0xffffff; if (rnd() & 3) a &= ~1u; return a; }

static void restore() { for (auto &w : written) ram[w.first] = base[w.first]; written.clear(); }

int main(int argc, char **argv) {
    const long cases = argc > 1 ? atol(argv[1]) : 100000;
    if (argc > 2) rng_state ^= strtoull(argv[2], nullptr, 10) * 0x9E3779B97F4A7C15ull;
    Emulator emu;
    emu.initialize();
    emu.set(ConfigScheme::A500_ECS_1MB);
    Moira &cpu = emu.rrMain().cpu;
    cpu.setModel(Model::M68EC020, Model::M68EC020);
    for (size_t i = 0; i < sizeof ram; i++) ram[i] = (unsigned char)rnd();
    base.assign(ram, ram + sizeof ram);
    m68k_init();
    m68k_set_cpu_type(M68K_CPU_TYPE_68EC020);
    m68k_pulse_reset();
    restore();
    long equal = 0, differ = 0, stopped = 0;
    std::map<std::string, long> by_handler;
    for (long n = 0; n < cases; n++) {
        Regs s{};
        for (auto &v : s.d) v = rnd();
        if (n & 1) for (auto &v : s.d) v &= 0xff;          // small values too: shifts, bit numbers, divisors, bounds
        for (auto &v : s.a) v = random_address();
        s.usp = random_address(); s.isp = random_address() & ~1u;
        s.sr = (rnd() & 0x271f) | ((rnd() & 3) ? 0x2000u : 0u);   // T1, T0 and M clear; S set three times in four
        s.pc = (rnd() & 0xfffffe) | 0x1000;
        const unsigned op = rnd() & 0xffff;
        // Opcode at the PC, the following bytes as the memory has them; the same for both CPUs.
        const unsigned pc = s.pc & 0xffffff;
        const unsigned char was0 = ram[pc], was1 = ram[(pc + 1) & 0xffffff];
        ram[pc] = (unsigned char)(op >> 8); ram[(pc + 1) & 0xffffff] = (unsigned char)op;
        base[pc] = ram[pc]; base[(pc + 1) & 0xffffff] = ram[(pc + 1) & 0xffffff];

        // Moira
        RrAmigaSteps::clear(cpu);
        cpu.setClock(0);
        cpu.setSR((u16)s.sr);
        for (int i = 0; i < 8; i++) cpu.setD(i, s.d[i]);
        for (int i = 0; i < 7; i++) cpu.setA(i, s.a[i]);
        cpu.setUSP(s.usp); cpu.setISP(s.isp);
        cpu.setPC(s.pc); cpu.setPC0(s.pc);
        cpu.setIRD((u16)op); cpu.setIRC((u16)(ram[(pc + 2) & 0xffffff] << 8 | ram[(pc + 3) & 0xffffff]));
        cpu.execute();
        Regs mo{};
        for (int i = 0; i < 8; i++) mo.d[i] = cpu.getD(i);
        for (int i = 0; i < 7; i++) mo.a[i] = cpu.getA(i);
        mo.usp = cpu.getUSP(); mo.isp = cpu.getISP(); mo.sr = cpu.getSR(); mo.pc = cpu.getPC() & 0xffffff;
        mo.stopped = RrAmigaSteps::stopped(cpu);
        std::map<unsigned, unsigned char> mo_written = written;
        restore();

        // Musashi, from a reset each time (a STOP or a halt would otherwise stay for every later case)
        m68k_pulse_reset();
        m68k_execute(0);          // the reset's own cycles, eaten here (an execute after a reset runs no instruction otherwise)
        m68k_set_reg(M68K_REG_SR, s.sr);
        for (int i = 0; i < 8; i++) m68k_set_reg((m68k_register_t)(M68K_REG_D0 + i), s.d[i]);
        for (int i = 0; i < 7; i++) m68k_set_reg((m68k_register_t)(M68K_REG_A0 + i), s.a[i]);
        m68k_set_reg(M68K_REG_USP, s.usp);
        m68k_set_reg(M68K_REG_ISP, s.isp);
        m68k_set_reg(M68K_REG_PC, s.pc);
        m68k_set_reg(M68K_REG_PREF_ADDR, 0xffffffff);
        m68k_execute(1);
        Regs mu{};
        for (int i = 0; i < 8; i++) mu.d[i] = m68k_get_reg(nullptr, (m68k_register_t)(M68K_REG_D0 + i));
        for (int i = 0; i < 7; i++) mu.a[i] = m68k_get_reg(nullptr, (m68k_register_t)(M68K_REG_A0 + i));
        mu.usp = m68k_get_reg(nullptr, M68K_REG_USP); mu.isp = m68k_get_reg(nullptr, M68K_REG_ISP);
        mu.sr = m68k_get_reg(nullptr, M68K_REG_SR); mu.pc = m68k_get_reg(nullptr, M68K_REG_PC) & 0xffffff;
        mu.stopped = op == 0x4e72 && (s.sr & 0x2000);     // this Musashi does not report STOP: a supervisor STOP stops it
        std::map<unsigned, unsigned char> mu_written = written;
        restore();
        ram[pc] = was0; ram[(pc + 1) & 0xffffff] = was1; base[pc] = was0; base[(pc + 1) & 0xffffff] = was1;

        if (mo.stopped || mu.stopped) { stopped++; if (mo.stopped == mu.stopped) continue; }
        std::string fields;
        const unsigned *a = &mo.d[0], *b = &mu.d[0];
        for (int i = 0; i < 18; i++) if (a[i] != b[i]) { fields += fields.empty() ? "" : ","; fields += NAMES[i]; }
        if (mo.pc != mu.pc) fields += fields.empty() ? "pc" : ",pc";
        if (mo.stopped != mu.stopped) fields += fields.empty() ? "stopped" : ",stopped";
        // The bytes written: the same addresses with the same final values (a byte both wrote and left as it was counts as written by both).
        std::map<unsigned, unsigned char> wa = mo_written, wb = mu_written;
        for (auto &w : wa) if (!wb.count(w.first) && w.second == base[w.first]) wb[w.first] = w.second;
        for (auto &w : wb) if (!wa.count(w.first) && w.second == base[w.first]) wa[w.first] = w.second;
        if (wa != wb) fields += fields.empty() ? "memory" : ",memory";
        if (fields.empty()) { equal++; continue; }
        differ++;
        const char *handler = rr_moira_exec_name[op] ? rr_moira_exec_name[op] : "?";
        by_handler[handler]++;
        // The first bytes that differ, address:moira/musashi (a byte one CPU did not write shows the memory's own).
        std::string bytes;
        int shown = 0;
        std::map<unsigned, int> all;
        for (auto &w : wa) all[w.first] = 1;
        for (auto &w : wb) all[w.first] = 1;
        for (auto &e : all) {
            const unsigned x = wa.count(e.first) ? wa[e.first] : base[e.first], y = wb.count(e.first) ? wb[e.first] : base[e.first];
            if (x == y || shown++ >= 8) continue;
            char item[32];
            snprintf(item, sizeof item, "%s%06x:%02x/%02x", bytes.empty() ? "" : " ", e.first, x, y);
            bytes += item;
        }
        printf("{\"case\":%ld,\"opcode\":\"%04x\",\"handler\":\"%s\",\"fields\":\"%s\",\"sr_in\":\"%04x\",\"sr_moira\":\"%04x\",\"sr_musashi\":\"%04x\","
               "\"pc_moira\":\"%06x\",\"pc_musashi\":\"%06x\",\"bytes\":\"%s\",\"sp_in\":\"%06x\",\"pc_in\":\"%06x\"}\n", n, op, handler, fields.c_str(), s.sr, mo.sr,
               mu.sr, mo.pc, mu.pc, bytes.c_str(), (s.sr & 0x2000) ? s.isp : s.usp, s.pc);
    }
    printf("{\"cases\":%ld,\"equal\":%ld,\"differ\":%ld,\"stopped\":%ld}\n", cases, equal, differ, stopped);
    std::_Exit(0);
}
