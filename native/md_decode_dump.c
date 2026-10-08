/* Offline decoder for RetroRecomp's instruction-level 68000 AOT generator.
 * This program is a converter tool; it is not linked into generated games. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "m68k_decoder.h"
#include "m68k_validator.h"
#include "rom_parser.h"
#include "md_cycle_estimate.h"

typedef struct { unsigned pc; uint8_t bytes[16]; } RamBytes;
static uint8_t ram_fetch(unsigned pc, void *user) {
    const RamBytes *ram = user;
    unsigned offset = pc - ram->pc;
    return offset < 16 ? ram->bytes[offset] : 0xff;
}

int main(int argc, char **argv) {
    if (argc != 4) return 2;
    GenesisRom rom = {0};
    if (!rom_parse(argv[1], &rom)) return 3;
    FILE *input = fopen(argv[2], "rb"), *output = fopen(argv[3], "wb");
    if (!input || !output) return 4;
    unsigned pc; int comma = 0;
    char line[80], raw[33];
    M68KValidatorOptions opts = {0};
    fputs("[", output);
    while (fgets(line, sizeof line, input)) {
        M68KInstr ins = {0};
        RamBytes bytes = {0}; GenesisRom view = rom;
        int fields = sscanf(line, "%x:%32s", &pc, raw);
        unsigned available = rom.rom_size - pc;
        if (fields == 2 && pc >= 0xff0000 && pc <= 0xfffff0) {
            bytes.pc = pc; available = (unsigned)strlen(raw) / 2;
            for (unsigned n = 0; n < available && n < 16; ++n) {
                unsigned byte;
                if (sscanf(raw + n * 2, "%2x", &byte) != 1) return 5;
                bytes.bytes[n] = (uint8_t)byte;
            }
            view.read8_override = ram_fetch; view.read8_user = &bytes;
            view.rom_size = 0x1000000;
        } else if (fields != 1 || pc >= rom.rom_size) continue;
        if ((pc & 1) || available < 2 || !m68k_decode(&view, pc, &ins)
            || ins.byte_length > available || m68k_validate(&ins, &opts) != M68K_LEGAL)
            continue;
        fprintf(output, "%s{\"addr\":%u,\"mnemonic\":%d,\"size\":%d,\"words\":[",
                comma ? "," : "", ins.addr, ins.mnemonic, ins.size);
        for (int i = 0; i < 8; ++i) fprintf(output, "%s%u", i ? "," : "", ins.words[i]);
        fprintf(output, "],\"word_count\":%d,\"byte_length\":%u,\"src_ea\":%d,"
            "\"dst_ea\":%d,\"reg\":%d,\"imm32\":%u,\"target_addr\":%u,"
            "\"has_target\":%d,\"dst_is_ea\":%d,\"predec_mem_form\":%d,"
            "\"mem_shift\":%d,\"cycles\":%d}",
            ins.word_count, ins.byte_length, ins.src_ea, ins.dst_ea, ins.reg,
            ins.imm32, ins.target_addr, ins.has_target, ins.dst_is_ea,
            ins.predec_mem_form, ins.mem_shift, interp_estimate_cycles(&ins));
        comma = 1;
    }
    fputs("]", output); fclose(input); fclose(output); rom_free(&rom);
    return 0;
}
