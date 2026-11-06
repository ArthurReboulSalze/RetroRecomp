// Original code of Retro-Recomp, MIT licence (the repository's LICENSE).
//
// Emits one generated function per sampled vector of the SingleStepTests/ARM7TDMI files, with the engine's own `ArmCodegen::emit_instr`
// (the call the engine's recompiler makes for every instruction of a game), plus the table that ss_run.cpp walks. The vector is not
// embedded: it only chooses the instruction (its opcode and the address it executes at); ss_run supplies the state and the data.
//
// usage: ss_gen out.cpp stride max_per_file file1.json.bin file2.json.bin ...
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <string>
#include <unordered_set>

#include "arm_codegen.h"
#include "arm_decode.h"
#include "arm_ir.h"
#include "thumb_decode.h"
#include "ss_common.h"

int main(int argc, char** argv) {
    if (argc < 5) { std::fputs("usage: ss_gen out.cpp stride max_per_file files...\n", stderr); return 2; }
    FILE* out = std::fopen(argv[1], "wb");
    if (!out) return 2;
    const uint32_t stride = std::atoi(argv[2]), max_per_file = std::atoi(argv[3]);
    std::fprintf(out, "#include \"runtime_arm.h\"\nextern \"C\" void codegen_test_fellthrough(void);\n");
    std::string table;
    unsigned not_implemented = 0, total = 0;
    const std::unordered_set<uint32_t> no_immediate_overrides;
    for (int fi = 4; fi < argc; ++fi) {
        SsFile f;
        if (!f.open(argv[fi])) { std::fprintf(stderr, "cannot open %s\n", argv[fi]); return 2; }
        for (uint32_t ti : ss_sample(f.count, stride, max_per_file)) {
            const SsTest t = f.get(ti);
            const bool thumb = (t.init.cpsr >> 5) & 1;
            const uint32_t pc = t.init.R[15] - (thumb ? 4 : 8);        // the vector records the pipeline-visible PC
            armv4t::Instr ins = thumb ? armv4t::ThumbDecoder::decode((uint16_t)t.opcode, pc) : armv4t::ArmDecoder::decode(t.opcode, pc);
            armv4t::CodegenCtx ctx{};
            ctx.current_function_addr = pc;
            ctx.current_function_end_addr = pc + (thumb ? 2u : 4u);
            ctx.alu_immediate_override_pcs = &no_immediate_overrides;
            bool unimplemented = false;
            std::string body;
            try { body = armv4t::ArmCodegen::emit_instr(ins, ctx, &unimplemented); }
            catch (const std::exception&) { body = "    runtime_unimplemented_op(\"emit exception\", 0);\n"; unimplemented = true; }
            not_implemented += unimplemented; ++total;
            const std::string name = "ss_" + std::to_string(fi - 4) + "_" + std::to_string(ti);
            std::fprintf(out, "extern \"C\" void %s(void) {\n%s    codegen_test_fellthrough();\n}\n", name.c_str(), body.c_str());
            table += "    {" + std::to_string(fi - 4) + "," + std::to_string(ti) + "," + name + "},\n";
        }
    }
    // The table, after the functions it names; ss_run.cpp declares the same struct.
    std::fprintf(out, "struct SsEntry { int file; unsigned test; void (*fn)(void); };\nextern \"C\" const SsEntry kSsTable[] = {\n%s    {-1,0,0}\n};\n",
                 table.c_str());
    std::fclose(out);
    std::fprintf(stderr, "emitted %u functions, %u not implemented\n", total, not_implemented);
    return 0;
}
