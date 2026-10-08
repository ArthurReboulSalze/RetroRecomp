/* RetroRecomp host adapter for the pinned segagenesisrecomp runtime.
 * The linked engine and generated code retain their upstream licences. */
#include <windows.h>
#include <string.h>
#include <stdlib.h>
#include "retro_console16.h"
#include "retro_md_game.h"
#include "game_spec.h"
#include "genesis_runtime.h"
#include "glue.h"
#include "sim_step.h"
#include "audio.h"
#include "audio/mixer.h"
#include "m68k_interp.h"
#include "m68k_decoder.h"
#include "runtime_evidence.h"
#include "crash_report.h"
#include "rb_state.h"

static uint32_t pixels[RR16_WIDTH * RR16_HEIGHT];
static bool audible, headless_mode;
static uint64_t interpreted;
static void *cold_state;
static size_t cold_length;
static bool reset_ok = true;
static bool execution_fault;
uint64_t g_cosim_cycle;
void rr16_note_interpreted(void) { ++interpreted; }
void rr16_note_fault(void) { execution_fault = true; }
extern uint64_t glue_miss_count_any(void);
static void entry(void) { recomp_call_addr(RR_MD_ENTRY); }
static void interrupt(uint32_t pc) {
#if RR_MD_STEP_AOT
    M68kiStatus status = m68k_interp_run_handler(pc);
    if (status != M68KI_OK) {
        fprintf(stderr, "[68000 IRQ] HALT status=%d entry=%06x pc=%06x opcode=%04x\n",
                status, pc, g_m68ki_bad_pc, g_m68ki_bad_op);
        rr16_note_fault();
    }
#else
    recomp_call_addr(pc);
#endif
}
static void vblank(void) { interrupt(RR_MD_VBLANK); }
static void hblank(void) { interrupt(RR_MD_HBLANK); }
#if RR_MD_SONIC && !RR_MD_STEP_AOT
static void periodic(void) { recomp_call_addr(0x001642u); }
static void post_reset(void) { g_ram[0xf009] = 0x80; }
#endif
const GameSpec g_game_spec = {
    .display_name = RR_MD_TITLE, .short_name = RR_MD_KEY,
    .expected_rom_crc32 = RR_MD_CRC32, .expected_rom_size = RR_MD_ROM_BYTES,
    .logical_players = 2, .tier3_floor_default = RR_MD_STEP_AOT || !RR_MD_SONIC,
    .call_entry_point = entry, .call_vblank = vblank, .call_hblank = hblank,
#if RR_MD_SONIC && !RR_MD_STEP_AOT
    .call_periodic = periodic, .on_post_reset = post_reset,
    .resume_main_loop_pc = 0x003ae2u, .dispatch_main_loop_pc = 0x000388u,
#endif
};

/* Evidence is in memory only. Conversion probes explicitly request reports;
 * launching a game never creates or rotates another game's sidecar files. */
static uint8_t evidence[RT_EVIDENCE_KIND_COUNT][0x40000];
static int evidence_counts[RT_EVIDENCE_KIND_COUNT];
static uint64_t rom_fallback, ram_fallback;
#define RAM_VARIANT_LIMIT 2048
static M68KInstr ram_variants[RAM_VARIANT_LIMIT];
static unsigned ram_variant_count;
void rr16_note_ram_instruction(const M68KInstr *ins) {
    if (ins->addr < 0xff0000u || ins->addr > 0xfffff0u || (ins->addr & 1u)
        || ins->word_count < 1 || ins->word_count > 8) return;
    for (unsigned i = 0; i < ram_variant_count; ++i) {
        const M68KInstr *other = &ram_variants[i];
        if (other->addr == ins->addr && other->word_count == ins->word_count &&
            !memcmp(other->words, ins->words, ins->word_count * sizeof(uint16_t))) return;
    }
    if (ram_variant_count < RAM_VARIANT_LIMIT) ram_variants[ram_variant_count++] = *ins;
}
void rr16_note_rom_fallback(uint32_t pc) {
    pc &= 0xffffffu;
    if (pc < RR_MD_ROM_BYTES) {
        ++rom_fallback;
        runtime_evidence_add(RT_EVIDENCE_FLOOR_COVERAGE, pc, 0, "retired ROM instruction");
    } else if (pc >= 0xff0000u) ++ram_fallback;
}
void runtime_evidence_request_fresh(void) {}
void runtime_evidence_init(const char *s, const char *n, const uint8_t *r, size_t z) {}
int runtime_evidence_has(RuntimeEvidenceKind k, uint32_t a) {
    return k < RT_EVIDENCE_KIND_COUNT && a < 0x400000 &&
        (evidence[k][a >> 4] & (1u << ((a >> 1) & 7))) != 0;
}
int runtime_evidence_add(RuntimeEvidenceKind k, uint32_t a, uint64_t f, const char *n) {
    if (k >= RT_EVIDENCE_KIND_COUNT || a >= 0x400000) return 0;
    /* One byte per aligned group of eight PCs. */
    unsigned index = a >> 4, mask = 1u << ((a >> 1) & 7);
    if (evidence[k][index] & mask) return 0;
    evidence[k][index] |= (uint8_t)mask; ++evidence_counts[k]; return 1;
}
void runtime_evidence_sync(RuntimeEvidenceKind k) {}
int runtime_evidence_count(RuntimeEvidenceKind k) { return k < RT_EVIDENCE_KIND_COUNT ? evidence_counts[k] : 0; }
void runtime_evidence_tick(void) {}
void runtime_evidence_flush(void) {}
uint32_t genesis_build_exe_fingerprint(void) { return 1; }
const char *genesis_build_info_string(void) { return "RetroRecomp pinned Mega Drive proof"; }
const char *exe_relative(const char *name) { return name; }

static void line_sink(void *ctx, int line, const uint32_t *row, int width) {
    if (line >= 0 && line < RR16_HEIGHT && width <= RR16_WIDTH)
        memcpy(pixels + line * RR16_WIDTH, row, width * sizeof(uint32_t));
}
bool rr16_init(bool headless) {
    headless_mode = headless;
    HRSRC resource = FindResourceW(NULL, MAKEINTRESOURCEW(103), MAKEINTRESOURCEW(10));
    const uint8_t *rom = resource ? LockResource(LoadResource(NULL, resource)) : NULL;
    if (!rom || SizeofResource(NULL, resource) != RR_MD_ROM_BYTES) return false;
    machine_init(); glue_init(rom, RR_MD_ROM_BYTES); audio_mixer_init();
    rr16_gun_reset();
    genesis_sim_set_tick_count(0);
    crash_report_set_log_path(NULL);
    size_t size = genesis_rb_bound();
    cold_state = malloc(size);
    cold_length = cold_state ? genesis_rb_save(cold_state, size) : 0;
    /* Restore once at boot too: the engine rebuilds derived palette caches
     * on load, giving cold start and F1 the same initial presentation state. */
    if (!cold_length || !genesis_rb_load(cold_state, cold_length)) {
        free(cold_state); cold_state = NULL; glue_shutdown(); return false;
    }
    audible = !headless && audio_init(223721) == 0;
    return true;
}
void rr16_reset(void) {
    rr16_gun_reset();
    /* The engine snapshot includes private scheduler globals and the live
     * fiber. Reinitializing only CPU/RAM would leave old timing behind. */
    reset_ok = cold_length && genesis_rb_load(cold_state, cold_length);
    execution_fault = false;
    interpreted = rom_fallback = ram_fallback = 0;
    ram_variant_count = 0;
    memset(evidence, 0, sizeof evidence);
    memset(evidence_counts, 0, sizeof evidence_counts);
    if (audible) audio_discard_playback();
    memset(pixels, 0, sizeof(pixels));
}
bool rr16_frame(uint16_t p1, uint16_t p2) {
    if (!reset_ok) return false;
    GenesisSimInput in = {0}; in.pad[0] = p1; in.pad[1] = p2; in.human_mask = 1;
    int16_t fm[8192], psg[16384]; size_t fn = 0, pn = 0;
    GenesisSimAudio audio = {fm, 4096, &fn, psg, 16384, &pn};
    GenesisSimHooks hooks = {0}; hooks.sink = line_sink;
    int ok = genesis_sim_step(&in, &audio, &hooks);
    if (audible) audio_flush(genesis_sim_tick_count(), 1, fm, fn, psg, pn);
    return ok != 0 && !execution_fault;
}
const uint32_t *rr16_pixels(void) { return pixels; }
uint64_t rr16_interpreted(void) { return interpreted; }
uint64_t rr16_native_entries(void) {
    extern uint64_t g_native_insn_count;
    /* The upstream interpreter increments the total too. Report only actual
     * generated instructions, not interpreted opcodes disguised as native. */
    return g_native_insn_count >= interpreted ? g_native_insn_count - interpreted : 0;
}
unsigned rr16_game_mode(void) { return RR_MD_SONIC ? g_ram[0xf600] : 0; }
unsigned rr16_player_x(void) { return RR_MD_SONIC ? (g_ram[0xd008] << 8) | g_ram[0xd009] : 0; }
int rr16_visible_width(void) { return (g_machine.vdp.reg[12] & 1) ? 320 : 256; }
static uint64_t bytes_hash(const void *data, size_t size) {
    uint64_t hash = 14695981039346656037ull;
    const uint8_t *bytes = data;
    for (size_t i = 0; i < size; ++i) { hash ^= bytes[i]; hash *= 1099511628211ull; }
    return hash;
}
void rr16_report_details(FILE *file) {
    rr16_gun_report(file);
    fprintf(file, ",\"visible_width\":%d,\"cpu_pc\":%u,\"execution_fault\":%s,"
            "\"rom_fallback_opcodes\":%llu,\"ram_fallback_opcodes\":%llu,"
            "\"cpu_hash\":\"%016llx\",\"ram_hash\":\"%016llx\",\"vram_hash\":\"%016llx\","
            "\"cram_hash\":\"%016llx\",\"vsram_hash\":\"%016llx\",\"vdp_register_hash\":\"%016llx\",\"rom_entries\":[",
            rr16_visible_width(), g_cpu.PC & 0xffffffu, execution_fault ? "true" : "false",
            rom_fallback, ram_fallback, bytes_hash(&g_cpu, sizeof g_cpu), bytes_hash(g_ram, sizeof g_ram),
            bytes_hash(g_machine.vdp.vram, sizeof g_machine.vdp.vram),
            bytes_hash(g_machine.vdp.cram, sizeof g_machine.vdp.cram),
            bytes_hash(g_machine.vdp.vsram, sizeof g_machine.vdp.vsram),
            bytes_hash(g_machine.vdp.reg, sizeof g_machine.vdp.reg));
    bool comma = false;
    for (uint32_t address = 0x200; address + 8 <= RR_MD_ROM_BYTES; address += 2) {
        if (!runtime_evidence_has(RT_EVIDENCE_FLOOR_COVERAGE, address)) continue;
        fprintf(file, "%s%u", comma ? "," : "", address); comma = true;
    }
    fputs("],\"ram_variants\":[", file);
    for (unsigned i = 0; i < ram_variant_count; ++i) {
        const M68KInstr *ins = &ram_variants[i];
        fprintf(file, "%s{\"address\":%u,\"bytes\":\"", i ? "," : "", ins->addr);
        for (int n = 0; n < ins->word_count; ++n) fprintf(file, "%04x", ins->words[n]);
        fputs("\"}", file);
    }
    fputs("]", file);
}
size_t rr16_audio(int16_t *pcm, size_t capacity) { return 0; }
void rr16_pause(bool paused) { if (audible) audio_set_playback_enabled(!paused); }
void rr16_shutdown(void) { if (audible) audio_close(); free(cold_state); cold_state = NULL; cold_length = 0; glue_shutdown(); }
bool rr16_state_file(const wchar_t *path, bool load) { return false; }
