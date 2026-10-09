#ifndef RETRO_CONSOLE16_H
#define RETRO_CONSOLE16_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <wchar.h>
#include <stdio.h>
#include "retro_gun_game.h"
#include "gun16.h"
#if RR16_MD
#include "retro_md_game.h"
#include "md_timing.h"
#define RR16_WIDTH 320
/* Storage must fit either VDP active-height mode. The current visible height
 * controls presentation; an NTSC cartridge switching V30 must not overread
 * the 224-line buffer previously used by the host. */
#define RR16_HEIGHT 240
#define RR16_SECTION L"MegaDrive"
#define RR16_CONSOLE "Mega Drive"
#define RR16_FRAME_SECONDS RR_MD_FRAME_SECONDS
#else
#include "retro_snes_game.h"
#include "snes_timing.h"
#define RR16_WIDTH 256
#define RR16_HEIGHT 224
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
#if RR16_MD
int rr16_visible_width(void);
int rr16_visible_height(void);
void rr16_trace_details(FILE *file);
#else
#define rr16_visible_width() RR16_WIDTH
#define rr16_visible_height() RR16_HEIGHT
#endif
void rr16_report_details(FILE *file);
#endif
