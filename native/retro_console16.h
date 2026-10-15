#ifndef RETRO_CONSOLE16_H
#define RETRO_CONSOLE16_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <wchar.h>
#include <stdio.h>
#include "retro_gun_game.h"
#include "gun16.h"
#if RR16_NG
#include "ng_game.h"
#include "neogeo_host.h"
#define RR16_WIDTH 320
#define RR16_HEIGHT 224
#define RR16_SECTION L"NeoGeo"
#define RR16_CONSOLE "Neo Geo"
#define RR16_FRAME_SECONDS (1.0 / 59.185606000)
uint64_t rr16_input_frame(void);
unsigned rr16_host_frame_limit(void);
void rr16_host_test_tick(void *window,void *renderer);
void rr16_host_discontinuity(void);
#elif RR16_MD
#include "retro_md_game.h"
#include "md_timing.h"
#define RR16_WIDTH 320
/* V28/V30 interlace mode 2 emits 448/480 woven rows. */
#define RR16_HEIGHT 480
#define RR16_SECTION L"MegaDrive"
#define RR16_CONSOLE "Mega Drive"
#define RR16_FRAME_SECONDS RR_MD_FRAME_SECONDS
#else
#include "retro_snes_game.h"
#include "snes_timing.h"
#define RR16_WIDTH 512
#define RR16_HEIGHT 480
#define RR16_SECTION L"SNES"
#define RR16_CONSOLE "Super Nintendo"
#define RR16_FRAME_SECONDS RR_SN_FRAME_SECONDS
#endif
bool rr16_init(bool headless);
void rr16_reset(void);
bool rr16_frame(uint16_t p1, uint16_t p2);
const uint32_t *rr16_pixels(void);
uint64_t rr16_interpreted(void);
uint64_t rr16_native_entries(void);
unsigned rr16_game_mode(void);
unsigned rr16_player_x(void);
size_t rr16_audio(int16_t *pcm, size_t capacity);
void rr16_pause(bool paused);
void rr16_shutdown(void);
bool rr16_state_file(const wchar_t *path, bool load);
int rr16_sdl_main(const char *title, int scale);
uint64_t rr16_audio_interpreted(void);
const char *rr16_audio_cpu(void);
uint64_t rr16_audio_fingerprint(void);
uint64_t rr16_audio_frame_fingerprint(void);
int rr16_visible_width(void);
int rr16_visible_height(void);
int rr16_raster_height(void);
#if RR16_MD || RR16_NG
#define rr16_display_width() rr16_visible_width()
void rr16_trace_details(FILE *file);
#else
#define rr16_display_width() 256
bool rr16_cartridge_save(const wchar_t *path);
#endif
void rr16_report_details(FILE *file);
#endif
