/* Development check (MIT, ours), never built into a game: tools/megadrive_moira_vectors.py (Mega Drive gate G10, slice 1).
 *
 * Every state of the register form of ABCD, SBCD or NBCD through the Mega Drive's generated native step (and through the same interpreter
 * text with every instruction interpreted: the reference path), against the table the Moira vector maker wrote for the same states
 * (native/amiga_machine/moira_vector_maker.cpp, `--bcd`: the result byte and the CCR). Flat 24-bit bus like native/md_prefetch_checks.c, whose
 * stubs this file repeats; no bus transaction and no clock is compared here, only the result byte, X, C, N, Z and V, and that nothing else
 * of the registers moved.
 *
 *   md_bcd_checks <abcd|sbcd|nbcd> <table> <pc> <opcode>
 *
 * Prints one JSON line per path. The decimal instructions are defined on two decimal digits per operand; for other operands the 68000
 * manual leaves the result undefined, and the pinned interpreter and Moira then compute different things. The counts are therefore split
 * by whether the operands are decimal ("valid"), and by which fields differ ("R" result, "X", "C", "N", "Z", "V"). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "md_native_steps.h"
#include "md_prefetch.h"
static unsigned paid;
void rr_md_cpu_fetch_cycles(unsigned words,int locked) { (void)words;(void)locked;paid=0; }
unsigned rr_md_cpu_stop_cycles(void) { return 4; }
unsigned rr_md_cpu_retire_cycles(unsigned cycles) { return paid>cycles?0:cycles-paid; }
int rr_md_prefetch_active(void) { return 1; }
void rr_md_cpu_bus_lock(int locked) { (void)locked; }
M68KState g_cpu;
uint8_t g_rom[0x400000], g_ram[0x10000];
static uint8_t flat_bus[0x1000000];
uint64_t g_native_insn_count;
uint32_t g_cycle_accumulator, g_audio_cycle_counter, g_vblank_threshold = 0xffffffffu;
uint32_t rr_md_cpu_stopped;
int g_rte_pending;
static int force_reference;
static unsigned fallback;
static void tick(unsigned n) {paid+=n;g_audio_cycle_counter+=n;g_cycle_accumulator+=n;}
void rr_md_cpu_idle(unsigned n) {tick(n);}
int genesis_force_interp(void) { return force_reference; }
void rr_md_cpu_iack(unsigned level) { (void)level; }
void rr16_note_interpreted(void) { ++fallback; }
void rr16_note_rom_fallback(uint32_t pc) { (void)pc; }
uint32_t rr_md_rom_fetch_offset;
uint32_t rr_md_cart_code_offset(uint32_t pc,const uint16_t *words,unsigned count) { (void)words;(void)count;return pc; }
void rr16_note_ram_instruction(const M68KInstr *ins) { (void)ins; }
void glue_check_vblank(void) {}
int game_instruction_hook_site(uint32_t pc) { (void)pc; return 0; }
int genesis_game_instruction_hook(uint32_t pc) { (void)pc; return 0; }
uint8_t m68k_read8(uint32_t a) {tick(4);return flat_bus[a&0xffffffu];}
uint16_t m68k_read16(uint32_t a) {a&=0xffffffu;tick(4);return ((unsigned)flat_bus[a]<<8)|flat_bus[(a+1)&0xffffffu];}
uint16_t rr_md_read_instruction_word(uint32_t a) {return m68k_read16(a);}
uint32_t m68k_read32(uint32_t a) {uint32_t hi=m68k_read16(a);uint32_t lo=m68k_read16(a+2);return (hi<<16)|lo;}
void m68k_write8(uint32_t a,uint8_t v) {rr_md_prefetch_before_write();tick(4);flat_bus[a&0xffffffu]=v;}
void m68k_write16(uint32_t a,uint16_t v) {rr_md_prefetch_before_write();tick(4);flat_bus[a&0xffffffu]=v>>8;flat_bus[(a+1)&0xffffffu]=v;}
void m68k_write32(uint32_t a,uint32_t v) {m68k_write16(a,v>>16);m68k_write16(a+2,v);}

static int is_decimal(unsigned v) { return (v >> 4) <= 9 && (v & 15) <= 9; }
/* The fields that differ, as bits: 1 result, 2 X, 4 C, 8 N, 16 Z, 32 V. */
enum { F_R = 1, F_X = 2, F_C = 4, F_N = 8, F_Z = 16, F_V = 32 };
static unsigned long long combo[2][64];      /* [operands are decimal][fields that differ] */
static unsigned long long states, valid_states, upper_changed, queue_wrong, status_wrong, path_wrong, first_shown;
static const char *name;

int main(int argc, char **argv) {
    if (argc < 5) return 2;
    int nbcd = !strcmp(argv[1], "nbcd");
    name = argv[1];
    unsigned pc = (unsigned)strtoul(argv[3], NULL, 0), opcode = (unsigned)strtoul(argv[4], NULL, 0);
    FILE *in = fopen(argv[2], "rb");
    if (!in) return 2;
    static uint8_t table[2 * 2 * 2 * 2 * 256 * 256];
    unsigned long long expected = (unsigned long long)(nbcd ? 2 * 2 * 2 * 256 : 2 * 2 * 2 * 256 * 256) * 2;
    if (fread(table, 1, sizeof table, in) != expected) { fprintf(stderr, "the table has not the expected size\n"); return 2; }
    fclose(in);
    const uint8_t code[6] = {(uint8_t)(opcode >> 8), (uint8_t)opcode, 0x4e, 0x71, 0x4e, 0x71};
    for (force_reference = 0; force_reference <= 1; ++force_reference) {
        memset(combo, 0, sizeof combo);
        states = valid_states = upper_changed = queue_wrong = status_wrong = path_wrong = 0;
        unsigned long long index = 0;
        memset(flat_bus, 0, sizeof flat_bus); memset(g_rom, 0, sizeof g_rom);
        memcpy(flat_bus + pc, code, sizeof code); memcpy(g_rom + pc, code, sizeof code);
        for (unsigned nvc = 0; nvc < 2; nvc++)
        for (unsigned x = 0; x < 2; x++)
        for (unsigned z = 0; z < 2; z++)
        for (unsigned src = 0; src < (nbcd ? 1u : 256u); src++)
        for (unsigned dst = 0; dst < 256; dst++, index++) {
            memset(&g_cpu, 0, sizeof g_cpu);
            for (int i = 0; i < 8; i++) g_cpu.D[i] = 0x11223300u * (i + 1);
            g_cpu.D[1] = 0xA5A5A500u | src;
            g_cpu.D[0] = 0x5A5A5A00u | dst;
            for (int i = 0; i < 7; i++) g_cpu.A[i] = 0x00200000u + 0x100u * i;
            g_cpu.USP = 0x00300000u; g_cpu.A[7] = 0x00310000u;
            g_cpu.SR = 0x2700u | (x << 4) | (z << 2) | (nvc ? 0x0bu : 0u);
            g_cpu.PC = pc;
            rr_md_prefetch_reset(); rr_md_prefetch.pc = g_cpu.PC; rr_md_prefetch.valid = 2;
            rr_md_prefetch.words[0] = (uint16_t)opcode; rr_md_prefetch.words[1] = 0x4e71;
            rr_md_cpu_stopped = 0; g_audio_cycle_counter = g_cycle_accumulator = 0; g_native_insn_count = 0; fallback = 0; paid = 0;
            M68kiStatus status = m68k_interp_step();
            states++;
            if (status != M68KI_OK) status_wrong++;
            if (fallback != (unsigned)force_reference) path_wrong++;
            if (g_cpu.PC != pc + 2 || rr_md_prefetch.valid != 2 || rr_md_prefetch.pc != g_cpu.PC) queue_wrong++;
            if ((g_cpu.D[0] & 0xffffff00u) != 0x5A5A5A00u || (!nbcd && g_cpu.D[1] != (0xA5A5A500u | src))) upper_changed++;
            unsigned want_result = table[2 * index], want_ccr = table[2 * index + 1];
            unsigned got_result = g_cpu.D[0] & 0xff, got_ccr = g_cpu.SR & 0x1f;
            unsigned fields = (got_result != want_result ? F_R : 0) | (((got_ccr ^ want_ccr) & 0x10) ? F_X : 0) | (((got_ccr ^ want_ccr) & 1) ? F_C : 0) |
                              (((got_ccr ^ want_ccr) & 8) ? F_N : 0) | (((got_ccr ^ want_ccr) & 4) ? F_Z : 0) | (((got_ccr ^ want_ccr) & 2) ? F_V : 0);
            int valid = is_decimal(dst) && (nbcd || is_decimal(src));
            valid_states += valid;
            combo[valid][fields]++;
            if (fields && valid && first_shown < 3) {
                first_shown++;
                fprintf(stderr, "valid operands differ: %s src=%02x dst=%02x x=%u z=%u nvc=%u: step %02x/%02x moira %02x/%02x\n", name, src, dst, x, z, nvc,
                        got_result, got_ccr, want_result, want_ccr);
            }
        }
        printf("{\"instruction\":\"%s\",\"path\":\"%s\",\"states\":%llu,\"valid_states\":%llu,\"upper_bits_changed\":%llu,\"queue_or_pc_wrong\":%llu,"
               "\"status_wrong\":%llu,\"wrong_path\":%llu,\"combos\":{", name, force_reference ? "reference" : "native", states, valid_states, upper_changed,
               queue_wrong, status_wrong, path_wrong);
        int first = 1;
        for (unsigned v = 0; v < 2; v++)
            for (unsigned f = 0; f < 64; f++)
                if (combo[v][f]) {
                    printf("%s\"%s:%u\":%llu", first ? "" : ",", v ? "valid" : "undefined", f, combo[v][f]);
                    first = 0;
                }
        printf("}}\n");
        fflush(stdout);
    }
    return 0;
}
