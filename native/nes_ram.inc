#include "runtime_feedback.h"
#include "cyc_run.h"
#include "hw.h"
/* Identify a ROM byte without touching the bus or modifying mapper state.
 * The lower cartridge window is absent from the normal $8000 slot table. */
bool rr_nes_rom_bank4(uint16_t pc, unsigned *bank) {
    if (pc >= 0x8000) {
        if (!hw_prg_is_rom(pc)) return false;
        *bank = hw_prg_bank4(pc);
    } else if (pc >= 0x6000 && hw_cart.mapper == 40) {
        *bank = (12u & (hw_cart.prg_slots - 1)) + ((pc >> 12) & 1);
    } else if (pc >= 0x6000 && hw_cart.mapper == 69 && !(hw_cart.m.fme7.prg[0] & 0x40)) {
        unsigned page = (hw_cart.m.fme7.prg[0] & 0x3F) & (hw_cart.prg_slots / 2 - 1);
        *bank = page * 2 + ((pc >> 12) & 1);
    } else return false;
    return *bank < hw_cart.prg_slots;
}

/* Side-effect-free code guards. Never read PPU/APU/mapper registers to probe
 * an entry. Only the explicitly modelled plain RAM windows are eligible. */
bool rr_nes_ram_peek(uint16_t pc, uint8_t *value) {
    if (pc < 0x2000) { *value = hw.ram[pc & 0x7FF]; return true; }
    /* A deferred MMC1 A12 can still select the RAM bank. */
    if (hw_cart.watch_ppu_addr && pc < 0x8000) rr_ppu_sync();
    if (hw_cart.mapper == 5 && pc >= 0x6000) {
        uint32_t offset = pc < 0x8000 ? mmc5_ram_bank(hw_cart.m.mmc5.prg[0]) | (pc & 8191) :
            hw_cart.prg_off[(pc >> 12) & 7] | (pc & 4095);
        if ((offset & MMC5_PRG_OPEN) || !(offset & MMC5_PRG_RAM)) return false;
        *value = hw_cart.wram[offset & 0x1FFFF]; return true;
    }
    if (pc >= 0x6000 && pc < 0x8000 && (hw_cart.mapper == 80 || hw_cart.mapper == 207 ||
            hw_cart.mapper == 82 || hw_cart.mapper == 552)) {
        if (!hw_cart.has_wram || !hw_cart.wram_len) return false;
        int offset = taito_x1_ram(pc);
        if (offset < 0) return false;
        *value = hw_cart.wram[(unsigned)offset % hw_cart.wram_len]; return true;
    }
    if (pc < 0x6000 || pc >= 0x8000 || !hw_cart.has_wram ||
        !hw_cart.wram_readable || !hw_cart.wram_len) return false;
    if (hw_cart.mapper == 21 || hw_cart.mapper == 22 || hw_cart.mapper == 23 || hw_cart.mapper == 25) {
        /* VRC2 without RAM drives a protection latch, never code RAM. The
         * initial has_wram test rejects it. VRC4's 2 KiB boards leave $7000+
         * unmapped; VRC2 RAM boards retain the hardware's mirrors. */
        if (!vrc2_board() && hw_cart.wram_len == 2048 && pc >= 0x7000) return false;
        *value = hw_cart.wram[(hw_cart.wram_bank + (pc & 8191)) % hw_cart.wram_len]; return true;
    }
    /* FME-7 command 8 selects ROM, RAM or open bus. Only enabled RAM is
     * eligible; selecting a ROM bank must not reuse an old RAM guard. */
    if (hw_cart.mapper == 69) {
        if ((hw_cart.m.fme7.prg[0] & 0xC0) != 0xC0) return false;
        *value = hw_cart.wram[(hw_cart.wram_bank + (pc & 8191)) % hw_cart.wram_len];
        return true;
    }
    /* BA-JUMP2 can also drive SDA onto D4. That bus contention is not a
     * plain RAM read, even if the RAM enable bit is set. */
    if (hw_cart.mapper == 153) {
        if (hw_cart.m.ctrl & 0x80) return false;
        *value = hw_cart.wram[pc & 8191];
        return true;
    }
    switch (hw_cart.mapper) {
    case 0: case 1: case 2: case 3: case 4: case 7: case 9: case 11:
    case 24: case 26: case 66: case 71: case 78: case 118: case 119: case 155:
        *value = hw_cart.wram[(hw_cart.wram_bank + (pc & 8191)) % hw_cart.wram_len];
        return true;
    default: return false;
    }
}

void rr_nes_feedback(uint16_t pc,uint8_t op) {
    if(!rr_feedback_enabled() || !cyc_run_native)return;
    unsigned bank;uint8_t value;
    if(rr_nes_rom_bank4(pc,&bank))rr_feedback_note(RR_FB_NES_ROM,pc,bank,&op,1);
    else if(rr_nes_ram_peek(pc,&value) && value==op)rr_feedback_note(RR_FB_NES_RAM,pc,0,&op,1);
}
/* Allocated only for the converter's explicit --miss-log probe. No normal
 * launch, menu, save/load or interpreted instruction creates a log/folder. */
static uint8_t *rr_ram_trace;
static unsigned rr_ram_trace_count;
static void rr_ram_trace_add(unsigned pc, unsigned op) {
    uint8_t *slot = rr_ram_trace + (size_t)pc * 32 + (op >> 3);
    uint8_t bit = (uint8_t)(1u << (op & 7));
    if (!(*slot & bit) && rr_ram_trace_count < 65536) { *slot |= bit; rr_ram_trace_count++; }
}
void rr_nes_ram_trace_enable(void) { if (!rr_ram_trace) rr_ram_trace = calloc(65536, 32); }
void rr_nes_note_ram(uint16_t pc, uint8_t op) {
    uint8_t value;
    if (rr_ram_trace && rr_nes_ram_peek(pc, &value) && value == op)
        rr_ram_trace_add(pc, op);
}
void rr_nes_ram_trace_merge(const char *path) {
    if (!rr_ram_trace) return;
    FILE *file = fopen(path, "r"); if (!file) return;
    char line[128]; unsigned pc, op;
    while (fgets(line, sizeof(line), file)) {
        if (sscanf(line, "# ram:%x:%x", &pc, &op) != 2 || pc > 65535 || op > 255) continue;
        if (pc >= 0x2000 && pc < 0x6000) continue;
        rr_ram_trace_add(pc, op);
    }
    fclose(file);
}
/* Instructions that follow from the observed ones. A routine copied into RAM runs along paths a run may not take: the
 * branch that was never taken, the code after a call. At the end of a run, from every recorded entry whose opcode is
 * still in RAM, the documented instructions it leads to are followed through the image (the next instruction, a branch
 * target, a JSR or JMP target) and added as entry/opcode pairs. A pair is only a permission: the guard still checks the
 * opcode in RAM when the entry is reached, and the operands stay live. Illegal and unknown opcodes, indirect jumps,
 * returns and a window edge end a path; addresses outside internal RAM and $6000-$7FFF are not followed. */
static const uint8_t rr_op_length[256] = {
    1, 2, 0, 0, 0, 2, 2, 0, 1, 2, 1, 0, 0, 3, 3, 0,
    2, 2, 0, 0, 0, 2, 2, 0, 1, 3, 0, 0, 0, 3, 3, 0,
    3, 2, 0, 0, 2, 2, 2, 0, 1, 2, 1, 0, 3, 3, 3, 0,
    2, 2, 0, 0, 0, 2, 2, 0, 1, 3, 0, 0, 0, 3, 3, 0,
    1, 2, 0, 0, 0, 2, 2, 0, 1, 2, 1, 0, 3, 3, 3, 0,
    2, 2, 0, 0, 0, 2, 2, 0, 1, 3, 0, 0, 0, 3, 3, 0,
    1, 2, 0, 0, 0, 2, 2, 0, 1, 2, 1, 0, 3, 3, 3, 0,
    2, 2, 0, 0, 0, 2, 2, 0, 1, 3, 0, 0, 0, 3, 3, 0,
    0, 2, 0, 0, 2, 2, 2, 0, 1, 0, 1, 0, 3, 3, 3, 0,
    2, 2, 0, 0, 2, 2, 2, 0, 1, 3, 1, 0, 0, 3, 0, 0,
    2, 2, 2, 0, 2, 2, 2, 0, 1, 2, 1, 0, 3, 3, 3, 0,
    2, 2, 0, 0, 2, 2, 2, 0, 1, 3, 1, 0, 3, 3, 3, 0,
    2, 2, 0, 0, 2, 2, 2, 0, 1, 2, 1, 0, 3, 3, 3, 0,
    2, 2, 0, 0, 0, 2, 2, 0, 1, 3, 0, 0, 0, 3, 3, 0,
    2, 2, 0, 0, 2, 2, 2, 0, 1, 2, 1, 0, 3, 3, 3, 0,
    2, 2, 0, 0, 0, 2, 2, 0, 1, 3, 0, 0, 0, 3, 3, 0
};
typedef struct { uint16_t *stack; uint8_t *seen; unsigned top; } RrSweep;
static void rr_sweep_add(RrSweep *s, unsigned pc) {
    uint8_t op;
    if (pc >= 0x10000 || !(pc < 0x2000 || (pc >= 0x6000 && pc < 0x8000))) return;
    if (s->seen[pc >> 3] & (1u << (pc & 7))) return;
    if (!rr_nes_ram_peek((uint16_t)pc, &op) || !rr_op_length[op]) return;
    s->seen[pc >> 3] |= (uint8_t)(1u << (pc & 7));
    rr_ram_trace_add(pc, op);
    s->stack[s->top++] = (uint16_t)pc;
}
void rr_nes_ram_sweep(void) {
    if (!rr_ram_trace) return;
    RrSweep s = { malloc(65536 * sizeof(uint16_t)), calloc(8192, 1), 0 };
    if (!s.stack || !s.seen) { free(s.stack); free(s.seen); return; }
    for (unsigned pc = 0; pc < 0x8000; pc++) {
        uint8_t op;
        if (!(pc < 0x2000 || pc >= 0x6000) || !rr_nes_ram_peek((uint16_t)pc, &op)) continue;
        if ((rr_ram_trace[(size_t)pc * 32 + (op >> 3)] >> (op & 7)) & 1) {
            s.seen[pc >> 3] |= (uint8_t)(1u << (pc & 7));
            s.stack[s.top++] = (uint16_t)pc;
        }
    }
    while (s.top) {
        unsigned pc = s.stack[--s.top], length;
        uint8_t op, a1 = 0, a2 = 0;
        if (!rr_nes_ram_peek((uint16_t)pc, &op) || !(length = rr_op_length[op])) continue;
        if (length > 1 && !rr_nes_ram_peek((uint16_t)(pc + 1), &a1)) continue;
        if (length > 2 && !rr_nes_ram_peek((uint16_t)(pc + 2), &a2)) continue;
        bool falls = op != 0x00 && op != 0x40 && op != 0x4C && op != 0x60 && op != 0x6C;
        if (falls) rr_sweep_add(&s, (pc + length) & 0xFFFF);
        if ((op & 0x1F) == 0x10) rr_sweep_add(&s, (pc + 2u + (unsigned)(int)(int8_t)a1) & 0xFFFF);
        else if (op == 0x20 || op == 0x4C) rr_sweep_add(&s, (unsigned)a1 | (unsigned)a2 << 8);
    }
    free(s.stack); free(s.seen);
}
void rr_nes_ram_trace_write(void *output) {
    if (!rr_ram_trace) return;
    rr_nes_ram_sweep();
    FILE *file = (FILE *)output;
    for (unsigned pc = 0; pc < 65536; pc++) for (unsigned byte = 0; byte < 32; byte++) {
        unsigned bits = rr_ram_trace[(size_t)pc * 32 + byte];
        if (!bits) continue;
        for (unsigned bit = 0; bit < 8; bit++) if (bits & (1u << bit))
            fprintf(file, "# ram:%04X:%02X\n", pc, byte * 8 + bit);
    }
}
