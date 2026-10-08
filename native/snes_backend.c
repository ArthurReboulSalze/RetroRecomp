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

static uint32_t pixels[RR16_WIDTH * 240];
static uint64_t interpreted, native_entries;
static double audio_fraction;
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
static const RtlGameInfo game_info = {
    .title = "Super Mario World",
    .run_frame = snes_beam_frame_driver_run_frame,
    .draw_ppu_frame = snes_beam_frame_driver_draw_ppu_frame,
    .hardware_reset = snes_beam_frame_driver_reset,
    .session_reset = snes_beam_frame_driver_reset,
    .save_name_prefix = "Super Mario World",
};
bool rr16_init(bool headless) {
    HRSRC resource = FindResourceW(NULL, MAKEINTRESOURCEW(103), MAKEINTRESOURCEW(10));
    const uint8_t *rom = resource ? LockResource(LoadResource(NULL, resource)) : NULL;
    if (!rom || SizeofResource(NULL, resource) != 0x80000) return false;
    RtlRegisterGame(&game_info);
    if (!SnesInit(rom, 0x80000)) return false;
    g_interp_bridge_pc_hook = NULL;
    g_interp_bridge_bounce_hook = NULL;
    const char *reference = getenv("RR_SNES_FORCE_INTERP");
    rr_snes_native_set_enabled(!reference || reference[0] != '1');
    RtlEnableExtendedFrameTiming(); RtlSetAudioOutputRate(48000);
    return true;
}
void rr16_reset(void) { RtlReset(1); audio_fraction = 0; interpreted = native_entries = 0; ram_variant_count = 0; }
bool rr16_frame(uint16_t p1, uint16_t p2) {
    RtlRunFrame(p1 | ((uint32_t)p2 << 12));
    PpuBeginDrawing(g_ppu, (uint8_t *)pixels, RR16_WIDTH * 4, 0);
    snes_beam_frame_driver_draw_ppu_frame();
    return !g_fail;
}
const uint32_t *rr16_pixels(void) { return pixels; }
uint64_t rr16_interpreted(void) { return interpreted; }
uint64_t rr16_native_entries(void) { return native_entries; }
unsigned rr16_game_mode(void) { return g_ram[0x100]; }
unsigned rr16_player_x(void) { return g_ram[0x94] | (g_ram[0x95] << 8); }
static uint64_t bytes_hash(const void *data, size_t size) {
    uint64_t hash = 14695981039346656037ull;
    const uint8_t *bytes = data;
    for (size_t i = 0; i < size; ++i) { hash ^= bytes[i]; hash *= 1099511628211ull; }
    return hash;
}
void rr16_report_details(FILE *file) {
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
    RtlRenderAudio(pcm, (int)frames, 2); return frames * 2;
}
void rr16_pause(bool paused) {}
void rr16_shutdown(void) { if (g_snes) snes_free(g_snes); }
bool rr16_state_file(const wchar_t *path, bool load) { return false; }
