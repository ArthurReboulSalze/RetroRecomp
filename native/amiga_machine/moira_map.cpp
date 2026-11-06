// Retro-Recomp Amiga (MIT): for every 68000 opcode, the Moira instruction template vAmiga's CPU dispatches it to; the conversion reads it (retrorecomp/amiga_codegen.load_opcode_map).
// Output, one line per opcode with a handler: "<opcode hex> <handler name> <Instr> <Mode> <Size>" (enum values).
#include "vaconfig.h"
#include "Emulator.h"
#include "Amiga.h"

#include <cstdio>

namespace vamiga::moira {

extern const char *rr_moira_exec_name[65536];

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
};

}

using namespace vamiga;

int main(int argc, char **argv) {
    Emulator emu;
    emu.initialize();
    emu.set(ConfigScheme::A500_ECS_1MB);
    FILE *out = argc > 1 ? fopen(argv[1], "w") : stdout;
    int n = moira::RrAmigaSteps::dump(emu.rrMain().cpu, out);
    fprintf(stderr, "%d opcodes with a handler\n", n);
    if (out != stdout) fclose(out);
    fflush(stderr);
    std::_Exit(0);
}
