/* Shared by the files of native/hostkit/shell only; machine adapters use hostkit.h. */
#ifndef RR_HOSTKIT_INTERNAL_H
#define RR_HOSTKIT_INTERNAL_H
#include "hostkit.h"
#include "audio_cushion.h"
#include "scanline_sdl.h"
#include "xbr_sdl.h"

/* Menu numbers (options.c checks them against game_options.h). */
#define RRHK_MENU_HELP 1
#define RRHK_MENU_CONTROLS 2
#define RRHK_MENU_PAGE 4
#define RRHK_MENU_OPTIONS 5
#define RRHK_COMBO_ROWS 2

extern RrhkUi rrhk;

/* Everything the windowed loop keeps between its steps. One instance, in main.c. */
typedef struct RrhkRun {
    const RrhkMachine *machine;
    const char *title;
    char caption[256];
    SDL_Window *win;
    SDL_Renderer *ren;
    SDL_Texture *tex;
    uint32_t *upscaled;
    unsigned test_frames;
    bool video_clock_test;
    wchar_t state_path[32768];
    int pending_state;             /* 1 save, 2 load; serviced at a safe CPU boundary */
    SDL_AudioDeviceID audio;
    SDL_AudioSpec have;
    Uint32 audio_preroll, audio_target;
    bool audio_playing;
    RrAudioCushion cushion;
    Uint64 frequency, next, test_started;
    uint64_t frame;
    int title_state;
    bool running;
    RrScanlineMask scanlines;
    RrXbr xbr;
} RrhkRun;

/* timing.c: explicit diagnostic only; accumulated in memory, written once. */
typedef struct {
    uint64_t frames;
    double total[6], maximum[6], thread_cpu;
} RrhkTiming;
double rrhk_thread_cpu(void);
void rrhk_timing_write(const RrhkMachine *machine, const char *path, const RrhkTiming *timing,
                       SDL_Renderer *renderer, Uint64 frequency);

/* input.c */
void rrhk_settings_path(void);
void rrhk_store_binding(void);
void rrhk_open_pads(void);
void rrhk_close_pads(void);
/* The Gamepad row of each player's gamepad page (divergence 10): which pad the player uses. */
void rrhk_pad_next(int player);          /* Enter: Automatic, each connected pad, None */
void rrhk_pad_automatic(int player);     /* Delete: back to Automatic */
void rrhk_pad_value(char *out, size_t size, int player);

/* video.c */
void rrhk_scale2x(const uint32_t *source, uint32_t *target);
SDL_Rect rrhk_game_rect(SDL_Renderer *renderer);
SDL_Texture *rrhk_texture_create(RrhkRun *run);
void rrhk_present_picture(RrhkRun *run);

/* pointer.c */
void rrhk_pointer_sample(SDL_Window *window, SDL_Renderer *renderer, uint16_t pad);
void rrhk_pointer_draw(SDL_Renderer *renderer, const SDL_Rect *dst);

/* menu.c */
int rrhk_page_rows(void);
bool rrhk_device_row(void);          /* the selected row is the Gamepad row of a gamepad page */
void rrhk_turn_page(int step);
void rrhk_toggle_settings(void);
void rrhk_menu_draw(SDL_Renderer *renderer);

/* options.c: the only file that includes game_options.h, whose settings are
 * one set of statics per translation unit. */
void rrhk_options_init(const wchar_t *console);
bool rrhk_options_event(const SDL_Event *event, int *menu, bool binding_capture);
bool rrhk_options_quit(int menu);
bool rrhk_options_restart(int menu);
void rrhk_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate);
void rrhk_options_audio_reset(void);
int rrhk_pages_count(void);
int rrhk_pages_index(void);
int rrhk_pages_goto(int page, int *control);
bool rrhk_pages_open(int menu);
int rrhk_pages_step(const SDL_Event *event);
int rrhk_option_page_event(const SDL_Event *event);
void rrhk_option_page_draw(SDL_Renderer *renderer);
int rrhk_combo_rows(void);
void rrhk_combo_start(int index, bool gamepad);
bool rrhk_combo_capturing_pad(void);     /* a gamepad combination waits for its buttons */
void rrhk_combo_clear(int index, bool gamepad);
void rrhk_combo_value(char *out, size_t size, int index, bool gamepad);
const char *rrhk_combo_label(int index);
const char *rrhk_combo_hint(int index);
void rrhk_menu_page_header(const RrhkMenuCtx *ctx, const char *title);

/* audio.c */
void rrhk_audio_open(RrhkRun *run);
void rrhk_audio_pause_output(RrhkRun *run);
void rrhk_audio_idle(RrhkRun *run);
void rrhk_audio_wait_room(RrhkRun *run);
void rrhk_audio_push(RrhkRun *run, int16_t *pcm, size_t samples);
void rrhk_audio_frame(RrhkRun *run);
unsigned rrhk_audio_queued(const RrhkRun *run);
void rrhk_audio_pace(RrhkRun *run, Uint64 now);
void rrhk_audio_close(RrhkRun *run);

/* ring.c: the callback-ring output (RRHK_AUDIO_RING). */
bool rrhk_ring_open(unsigned rate);
void rrhk_ring_start(void);
void rrhk_ring_submit(const int16_t *pcm, uint32_t count);
void rrhk_ring_clear(void);
void rrhk_ring_close(void);
SDL_AudioDeviceID rrhk_ring_device(void);

/* events.c */
void rrhk_poll_events(RrhkRun *run);
#endif
