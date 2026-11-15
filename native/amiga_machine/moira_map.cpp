// Retro-Recomp Amiga (MIT): for every opcode, the Moira instruction template vAmiga's CPU dispatches it to; the conversion reads it (retrorecomp/amiga_codegen.load_opcode_map).
// Output, one line per opcode with a handler: "<opcode hex> <handler name> <Instr> <Mode> <Size> <words>" (enum values).
// With the argument 68ec020 (the A1200's CPU) a seventh field follows: the positions (word indexes after the opcode, comma separated, '-' for
// none) of the words that are an indexed mode's extension word. On a 68020 that word may be a full one, followed by base and outer
// displacements, so the instruction is longer than <words> (which counts brief extension words); a position is found by asking Moira's
// disassembler for the length with a full extension word there.
#include "vaconfig.h"
#include "Emulator.h"
#include "Amiga.h"

#include <cstdio>
#include <cstring>

namespace vamiga::moira {

extern const char *rr_moira_exec_name[65536];

struct RrAmigaSteps {
    static unsigned length(Moira &m, Memory &mem, int id, const u16 *words, int count) {
        for (int k = 0; k < count; k++) mem.patch((u32)(0x1000 + 2 * k), (u16)words[k]);
        const InstrInfo &i = m.info[id];
        char text[256];
        StrWriter writer(text, m.instrStyle);
        u32 pc = 0x1000;
        (m.*m.dasm[id])(writer, pc, (u16)id, i.I, i.M, i.S);
        return (pc - 0x1000) / 2 + 1;
    }
    static int dump(Moira &m, Memory &mem, FILE *out, bool positions) {
        int n = 0;
        for (int id = 0; id < 65536; id++) {
            const char *name = rr_moira_exec_name[id];
            if (!name || !m.info) continue;
            const InstrInfo &i = m.info[id];
            // The instruction's words: what Moira's disassembler consumes (on a 68000 the opcode alone decides how many).
            u16 words[12] = {(u16)id};
            unsigned brief = length(m, mem, id, words, 12);
            fprintf(out, "%04x %s %d %d %d %u", id, name, (int)i.I, (int)i.M, (int)i.S, brief);
            if (positions) {
                // A full extension word with a long base displacement and no memory indirection ($0130) makes an indexed mode two words longer.
                char list[64] = "";
                for (unsigned k = 1; k < brief && k < 12; k++) {
                    u16 probe[12] = {(u16)id};
                    probe[k] = 0x0130;
                    if (length(m, mem, id, probe, 12) == brief + 2)
                        snprintf(list + strlen(list), sizeof list - strlen(list), "%s%u", *list ? "," : "", k);
                }
                fprintf(out, " %s", *list ? list : "-");
            }
            fputc('\n', out);
            n++;
        }
        return n;
    }
};

}

using namespace vamiga;

int main(int argc, char **argv) {
    bool ec020 = argc > 2 && !strcmp(argv[2], "68ec020");
    if (argc > 2 && !ec020) { fprintf(stderr, "Unknown CPU: %s\n", argv[2]); return 2; }
    Emulator emu;
    emu.initialize();
    if (ec020) {
        emu.set(ConfigScheme::A1200_2MB);
        emu.set(Opt::CPU_DASM_REVISION, (i64)DasmRev::DASM_68EC020);
    } else {
        emu.set(ConfigScheme::A500_ECS_1MB);
    }
    FILE *out = argc > 1 ? fopen(argv[1], "w") : stdout;
    int n = moira::RrAmigaSteps::dump(emu.rrMain().cpu, emu.rrMain().mem, out, ec020);
    fprintf(stderr, "%d opcodes with a handler\n", n);
    if (out != stdout) fclose(out);
    if (ec020 && argc > 3) {
        // Samples for tests/test_m68020_lengths.py (tools/amiga_lengths_selftest.py): random words, every other one a full extension
        // word, and the length Moira's disassembler gives: "<words hex> <words>". A fixed generator, the same file every time.
        FILE *samples = fopen(argv[3], "w");
        uint32_t seed = 0x1200;
        auto next = [&]() { seed = seed * 1103515245u + 12345u; return (u16)(seed >> 8); };
        for (int k = 0; k < 20000; k++) {
            u16 words[12];
            for (auto &w : words) { w = next(); if (next() & 1) w = (u16)((w & 0xFEFF) | 0x0100); }
            unsigned count = moira::RrAmigaSteps::length(emu.rrMain().cpu, emu.rrMain().mem, words[0], words, 12);
            for (unsigned i = 0; i < 12; i++) fprintf(samples, "%04x", words[i]);
            fprintf(samples, " %u\n", count);
        }
        fclose(samples);
    }
    fflush(stderr);
    std::_Exit(0);
}
