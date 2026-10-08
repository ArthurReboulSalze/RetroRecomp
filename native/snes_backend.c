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

static uint32_t pixels[RR16_WIDTH * 240];
static uint64_t interpreted, native_entries;
static double audio_fraction;
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
static void interpreted_pc(uint32_t pc, int m, int x) { ++interpreted; }
static void native_pc(uint32_t pc, int m, int x) { ++native_entries; }
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
    g_interp_bridge_pc_hook = interpreted_pc;
    g_interp_bridge_bounce_hook = native_pc;
    RtlEnableExtendedFrameTiming(); RtlSetAudioOutputRate(48000);
    return true;
}
void rr16_reset(void) { RtlReset(1); audio_fraction = 0; }
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
