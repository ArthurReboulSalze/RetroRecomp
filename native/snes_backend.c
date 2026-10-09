/* RetroRecomp's presentation adapter; CPU/PPU/APU remain in snesrecomp. */
#include <windows.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include "retro_console16.h"
#include "common_cpu_infra.h"
#include "common_rtl.h"
#include "cpu_state.h"
#include "beam_frame_driver.h"
#include "snes/ppu.h"
#include "snes/interp_bridge.h"
#include "snes/snes.h"
#include "desktop/config.h"
#include "snes_native_steps.h"
#include "snes_spc_native.h"
#include "audio_trace.h"
#include "retro_snes_game.h"
#include "console16_state.h"
#include "snes/saveload.h"

static uint32_t pixels[RR16_WIDTH * 240];
static uint64_t interpreted, native_entries;
static double audio_fraction;
static bool headless_mode;
static bool overscan_seen, interlace_seen, hires_seen;
static uint64_t visible_frames;
static bool field_visible;
static uint64_t pcm_samples, pcm_nonzero, pcm_hash = 14695981039346656037ull;
static unsigned pcm_peak;
static uint64_t frame_audio_hash;
static struct { uint32_t pc; uint8_t bytes[4]; } ram_variants[2048];
static unsigned ram_variant_count;
void debug_on_wram_write_byte(uint32_t addr, uint8_t old_val, uint8_t val) {}
void debug_on_wram_write_word(uint32_t addr, uint16_t old_val, uint16_t val) {}
void debug_on_block_enter(uint32_t pc, uint32_t a, uint32_t x, uint32_t y) {}
void Die(const char *message) {
    fprintf(stderr, "%s\n", message); exit(5);
}
struct SpcPlayer *g_spc_player;
/* Audio is consumed on this same thread, so there is no cross-thread lock. */
void RtlApuLock(void) {}
void RtlApuUnlock(void) {}
void rr16_snes_note_interpreted(uint32_t pc) { ++interpreted; }
void rr16_snes_note_native(void) { ++native_entries; }
void rr16_snes_observe_fallback(uint32_t pc) {
    uint8_t bytes[4];
    if (!rr_snes_read_ram_code(pc, bytes)) return;
    for (unsigned n = 0; n < ram_variant_count; ++n)
        if (ram_variants[n].pc == pc && !memcmp(bytes, ram_variants[n].bytes, 4)) return;
    if (ram_variant_count == 2048) return;
    ram_variants[ram_variant_count].pc = pc;
    memcpy(ram_variants[ram_variant_count++].bytes, bytes, 4);
}
static void save_state_extra(SaveLoadInfo *sli);
static void load_state_extra(SaveLoadInfo *sli, uint32_t version);
static void state_loaded(uint32_t version);
static const RtlGameInfo game_info = {
    .title = RR_SN_TITLE,
    .run_frame = snes_beam_frame_driver_run_frame,
    .draw_ppu_frame = snes_beam_frame_driver_draw_ppu_frame,
    .hardware_reset = snes_beam_frame_driver_reset,
    .session_reset = snes_beam_frame_driver_reset,
    .save_name_prefix = RR_SN_TITLE,
    .state_save_extra = save_state_extra,
    .state_load_extra = load_state_extra,
    .on_state_loaded = state_loaded,
};
static void start_audio_timeline(void) {
    /* The APU clock runs from power-on, even before the first CPU port write.
     * Leaving this mapping invalid makes frame-boundary sync a no-op during
     * loaders that do not touch $2140 yet, gradually starving the DSP ring. */
    Apu *apu = g_snes->apu;
    apu->portGuestAnchor = apu->portLastGuest = 0;
    apu->portTargetAnchor = apu->portLastTarget = apu->portClock;
    apu->portTimeValid = true;
    rr_snes_reset_audio_delivery();
}
bool rr16_init(bool headless) {
    headless_mode = headless;
    const char *reference = getenv("RR_SNES_FORCE_INTERP");
    bool native = !reference || reference[0] != '1';
    rr_spc_reset_evidence();
    rr_spc_set_mode(native, headless);
    rr_snes_native_set_enabled(native);
    HRSRC resource = FindResourceW(NULL, MAKEINTRESOURCEW(103), MAKEINTRESOURCEW(10));
    const uint8_t *rom = resource ? LockResource(LoadResource(NULL, resource)) : NULL;
    if (!rom || SizeofResource(NULL, resource) != RR_SN_ROM_BYTES) return false;
    RtlRegisterGame(&game_info);
    if (!SnesInit(rom, RR_SN_ROM_BYTES)) return false;
    rr16_gun_reset();
    g_interp_bridge_pc_hook = NULL;
    g_interp_bridge_bounce_hook = NULL;
    RtlEnableExtendedFrameTiming(); RtlSetAudioOutputRate(48000);
    start_audio_timeline();
    return true;
}
void rr16_reset(void) {
    rr_spc_reset_evidence();
    /* A new session starts both the architectural CPU state and its clocks.
     * RtlReset alone retains the previous CpuState, shifting APU bus timing. */
    /* MEMSEL is guest hardware state kept in an upstream host global. A cold
     * restart must not fetch boot code at the previous session's FastROM speed. */
    g_memsel = 0;
    cpu_state_init(&g_cpu, g_ram);
    RtlReset(1); start_audio_timeline(); rr16_gun_reset(); audio_fraction = 0;
    pcm_samples = pcm_nonzero = pcm_peak = 0; pcm_hash = 14695981039346656037ull;
    interpreted = native_entries = 0; ram_variant_count = 0;
    overscan_seen = interlace_seen = hires_seen = false;
    visible_frames = 0;
}
static void observe_video_mode(const Ppu *ppu, unsigned line, void *context) {
    /* Boot code can briefly write every mode bit while the screen is off.
     * Observe the replayed visible lines, not that unused register state. */
    if (PPU_forcedBlank(ppu) || !PPU_brightness(ppu)) return;
    field_visible = true;
    overscan_seen |= PPU_overscan(ppu);
    interlace_seen |= PPU_interlace(ppu);
    hires_seen |= PPU_pseudoHires(ppu) || PPU_mode(ppu) == 5 || PPU_mode(ppu) == 6;
}
bool rr16_frame(uint16_t p1, uint16_t p2) {
    RtlRunFrame(p1 | ((uint32_t)p2 << 12));
    PpuBeginDrawing(g_ppu, (uint8_t *)pixels, RR16_WIDTH * 4, 0);
    field_visible = false;
    snes_beam_frame_driver_draw_ppu_frame_observed(observe_video_mode, NULL);
    visible_frames += field_visible;
    /* Probes consume the same one-frame audio block as the interactive host,
     * without opening a sound device. This exercises the live SPC/DSP clock. */
    if (headless_mode) { int16_t pcm[4096]; rr16_audio(pcm, sizeof pcm / sizeof *pcm); }
    return !g_fail;
}
const uint32_t *rr16_pixels(void) { return pixels; }
uint64_t rr16_interpreted(void) { return interpreted; }
uint64_t rr16_native_entries(void) { return native_entries; }
uint64_t rr16_audio_interpreted(void) { return rr_spc_interpreted_opcodes(); }
const char *rr16_audio_cpu(void) {
    return rr_spc_interpreted_opcodes() ? (rr_spc_native_opcodes() ? "hybrid" : "interpreted") :
           rr_spc_native_opcodes() ? "native" : "not_run";
}
uint64_t rr16_audio_fingerprint(void) { return pcm_hash ^ pcm_samples; }
unsigned rr16_game_mode(void) { return RR_SN_SMW ? g_ram[0x100] : 0; }
unsigned rr16_player_x(void) { return RR_SN_SMW ? g_ram[0x94] | (g_ram[0x95] << 8) : 0; }
static uint64_t bytes_hash(const void *data, size_t size) {
    uint64_t hash = 14695981039346656037ull;
    const uint8_t *bytes = data;
    for (size_t i = 0; i < size; ++i) { hash ^= bytes[i]; hash *= 1099511628211ull; }
    return hash;
}
typedef struct { SaveLoadInfo stream; uint64_t hash; } HashStream;
static void hash_state(SaveLoadInfo *stream, void *data, size_t size) {
    HashStream *out = (HashStream *)stream;
    const uint8_t *bytes = data;
    for (size_t i = 0; i < size; ++i) { out->hash ^= bytes[i]; out->hash *= 1099511628211ull; }
}
void rr16_report_details(FILE *file) {
    fprintf(file, ",\"video_standard\":\"%s\",\"field_lines\":%u,\"ppu_pal\":%u,"
        "\"overscan_seen\":%u,\"interlace_seen\":%u,\"hires_seen\":%u,"
        "\"beam_line\":%u,\"beam_column\":%u,\"irq_latches\":%u,\"irq_overshot\":%u,"
        "\"visible_frames\":%llu",
        RR_SN_PAL ? "pal" : "ntsc", RR_SN_LINES, RR_SN_PAL,
        overscan_seen, interlace_seen, hires_seen, g_snes->vPos, g_snes->hPos,
        g_snes->dbgIrqLatches, g_snes->dbgIrqOvershot, visible_frames);
    rr16_gun_report(file);
    rr_spc_report(file);
    AudioTraceStats audio;
    audio_trace_get_stats(&audio);
    fprintf(file, ",\"audio_output_underflows\":%llu,\"audio_output_missing_frames\":%llu,"
        "\"audio_output_priming\":%llu,\"audio_ring_dropped\":%llu,\"audio_ring_dropped_audible\":%llu,"
        "\"audio_ring_highwater\":%u,\"audio_ring_current\":%u",
        audio.output_underflows, audio.output_missing_frames, audio.output_priming,
        audio.dropped, audio.dropped_audible, audio.occupancy_highwater, audio.occupancy_current);
    Spc *spc = g_snes->apu->spc;
    Apu *apu = g_snes->apu;
    uint16_t spc_registers[] = {spc->pc, spc->a, spc->x, spc->y, spc->sp,
        spc->c, spc->z, spc->v, spc->n, spc->i, spc->h, spc->p, spc->b,
        spc->stopped, spc->cyclesUsed};
    /* Deterministic upstream DSP snapshot excludes both host pointers. */
    HashStream dsp = {{hash_state, NULL}, 14695981039346656037ull};
    dsp_saveload(apu->dsp, &dsp.stream);
    uint64_t apu_values[] = {apu->romReadable, apu->dspAdr, apu->cpuCyclesLeft,
        apu->portClock, apu->portGuestAnchor, apu->portTargetAnchor, apu->portLastGuest,
        apu->portLastTarget, apu->portTimeValid, apu->portQTail - apu->portQHead,
        apu->timer[0].cycles, apu->timer[0].divider, apu->timer[0].target, apu->timer[0].counter, apu->timer[0].enabled,
        apu->timer[1].cycles, apu->timer[1].divider, apu->timer[1].target, apu->timer[1].counter, apu->timer[1].enabled,
        apu->timer[2].cycles, apu->timer[2].divider, apu->timer[2].target, apu->timer[2].counter, apu->timer[2].enabled};
    HashStream apu_hash = {{hash_state, NULL}, 14695981039346656037ull};
    hash_state(&apu_hash.stream, apu_values, sizeof apu_values);
    hash_state(&apu_hash.stream, apu->inPorts, sizeof apu->inPorts);
    hash_state(&apu_hash.stream, apu->outPorts, sizeof apu->outPorts);
    for (uint32_t n = apu->portQHead; n != apu->portQTail; ++n) {
        const ApuPortWrite *event = apu->portQueue + (n & (APU_PORT_QUEUE_LEN - 1));
        uint64_t fields[] = {event->target_cycle, event->port, event->val};
        hash_state(&apu_hash.stream, fields, sizeof fields);
    }
    fprintf(file, ",\"spc_pc\":%u,\"spc_cpu_hash\":\"%016llx\",\"apu_state_hash\":\"%016llx\","
        "\"dsp_state_hash\":\"%016llx\",\"pcm_samples\":%llu,\"pcm_nonzero\":%llu,"
        "\"pcm_peak\":%u,\"pcm_hash\":\"%016llx\"", spc->pc, bytes_hash(spc_registers, sizeof spc_registers),
        apu_hash.hash, dsp.hash, pcm_samples, pcm_nonzero, pcm_peak, pcm_hash);
    /* Explicit architectural fields: never hash pointers or host padding. */
    uint16_t registers[] = {g_cpu.A, g_cpu.X, g_cpu.Y, g_cpu.S, g_cpu.D,
        g_cpu.DB, g_cpu.PB, g_cpu.P, g_cpu.m_flag, g_cpu.x_flag, g_cpu.emulation,
        g_cpu._flag_N, g_cpu._flag_V, g_cpu._flag_Z, g_cpu._flag_C,
        g_cpu._flag_I, g_cpu._flag_D, g_cpu.open_bus};
    fprintf(file, ",\"cpu_hash\":\"%016llx\",\"ram_hash\":\"%016llx\","
        "\"vram_hash\":\"%016llx\",\"cram_hash\":\"%016llx\",\"oam_hash\":\"%016llx\","
        "\"high_oam_hash\":\"%016llx\",\"apu_ram_hash\":\"%016llx\","
        "\"cpu_cycles\":%llu,\"master_cycles\":%llu,\"cpu_pc\":%u,\"apu_cycles\":%u",
        bytes_hash(registers, sizeof registers), bytes_hash(g_ram, sizeof g_ram),
        bytes_hash(g_ppu->vram, sizeof g_ppu->vram), bytes_hash(g_ppu->cgram, sizeof g_ppu->cgram),
        bytes_hash(g_ppu->oam, sizeof g_ppu->oam), bytes_hash(g_ppu->highOam, sizeof g_ppu->highOam),
        bytes_hash(g_snes->apu->ram, sizeof g_snes->apu->ram),
        (unsigned long long)g_cpu.cycles, (unsigned long long)g_cpu.master_cycles,
        interp_bridge_lle_resume_pc(), g_snes->apu->cycles);
    fputs(",\"ram_variants\":[", file);
    for (unsigned n = 0; n < ram_variant_count; ++n) {
        fprintf(file, "%s{\"address\":%u,\"bytes\":\"%02x%02x%02x%02x\"}", n ? "," : "",
            ram_variants[n].pc, ram_variants[n].bytes[0], ram_variants[n].bytes[1],
            ram_variants[n].bytes[2], ram_variants[n].bytes[3]);
    }
    fputs("]", file);
}
size_t rr16_audio(int16_t *pcm, size_t capacity) {
    /* Consume exactly one guest frame, carrying fractional host samples. */
    audio_fraction += 48000.0 * RR16_FRAME_SECONDS * RtlLastFramePeriods();
    size_t frames = (size_t)audio_fraction;
    if (frames > capacity / 2) frames = capacity / 2;
    audio_fraction -= frames;
    RtlRenderAudio(pcm, (int)frames, 2);
    if (headless_mode) {
        frame_audio_hash = 14695981039346656037ull;
        pcm_samples += frames * 2;
        for (size_t i = 0; i < frames * 2; ++i) {
            unsigned amplitude = pcm[i] < 0 ? -(int)pcm[i] : pcm[i];
            pcm_nonzero += amplitude != 0;
            if (amplitude > pcm_peak) pcm_peak = amplitude;
            pcm_hash ^= (uint16_t)pcm[i]; pcm_hash *= 1099511628211ull;
            frame_audio_hash ^= (uint16_t)pcm[i]; frame_audio_hash *= 1099511628211ull;
        }
    }
    return frames * 2;
}
void rr16_pause(bool paused) {}
uint64_t rr16_audio_frame_fingerprint(void) { return frame_audio_hash; }
void rr16_shutdown(void) { if (g_snes) snes_free(g_snes); }
extern void rr_snes_save_delivery(SaveLoadInfo *sli);
extern void rr_snes_load_delivery(SaveLoadInfo *sli);
extern void rr_snes_apply_delivery(void);
extern void rr_snes_driver_save(uint32_t state[2]);
extern bool rr_snes_driver_load(const uint32_t state[2]);
static bool loaded_execution_ok;
static uint8_t loaded_gun[256];
static uint32_t loaded_driver[2];
static double loaded_fraction;
static void save_state_extra(SaveLoadInfo *sli) {
    uint32_t magic=0x31535252; sli->func(sli,&magic,4);
    RtlSaveExecutionState(sli); rr_snes_save_delivery(sli);
    uint32_t driver[2]; rr_snes_driver_save(driver); sli->func(sli,driver,sizeof driver);
    sli->func(sli,&audio_fraction,sizeof audio_fraction);
    uint8_t gun[256]; size_t n=rr16_gun_state_save(NULL,0);
    if (n<=sizeof gun) { rr16_gun_state_save(gun,n); sli->func(sli,gun,n); }
}
static void load_state_extra(SaveLoadInfo *sli, uint32_t version) {
    uint32_t magic=0; sli->func(sli,&magic,4);
    loaded_execution_ok=magic==0x31535252 && RtlLoadExecutionState(sli);
    if (!loaded_execution_ok) return;
    rr_snes_load_delivery(sli); sli->func(sli,loaded_driver,sizeof loaded_driver);
    sli->func(sli,&loaded_fraction,sizeof loaded_fraction);
    size_t n=rr16_gun_state_save(NULL,0);
    if (n>sizeof loaded_gun) { loaded_execution_ok=false; return; }
    sli->func(sli,loaded_gun,n);
}
static void state_loaded(uint32_t version) {
    if (!loaded_execution_ok) return;
    RtlApuLock(); RtlApplyExecutionState(); rr_snes_apply_delivery(); RtlApuUnlock();
    loaded_execution_ok=rr_snes_driver_load(loaded_driver) &&
        rr16_gun_state_load(loaded_gun,rr16_gun_state_save(NULL,0));
    audio_fraction=loaded_fraction;
}
uint8_t *rr16_state_capture(size_t *size) {
    *size=RtlSaveSnapshotToMemory(NULL,0);
    uint8_t *data=*size ? malloc(*size) : NULL;
    if (data && RtlSaveSnapshotToMemory(data,*size)!=*size) { free(data); data=NULL; *size=0; }
    return data;
}
bool rr16_state_restore(const uint8_t *data, size_t size) {
    loaded_execution_ok=false;
    return RtlLoadSnapshotFromMemory(data,size) && loaded_execution_ok;
}
