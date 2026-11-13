/* Shared by the files of native/hostkit/shell only; machine adapters use hostkit.h. */
#ifndef RR_HOSTKIT_INTERNAL_H
#define RR_HOSTKIT_INTERNAL_H
#include "hostkit.h"
#include "audio_cushion.h"
#include "scanline_sdl.h"
#include "xbr_sdl.h"

#define RRHK_COMBO_ROWS 2

extern RrhkUi rrhk;

/* timing.c: explicit diagnostic only; accumulated in memory, written once. */
typedef struct {
    uint64_t frames;
    double total[6], maximum[6], thread_cpu;
} RrhkTiming;

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
    bool fast;                     /* the machine's fast-forward hook was true at the start of this iteration */
    int speed;                     /* percent of the machine's speed this iteration runs at: 100, 250 (Tab held) or 500 (max speed) */
    unsigned device_serial;        /* the output device asked for, as the loop last opened it */
    bool device_lost;              /* the device the sound plays on was removed */
    RrScanlineMask scanlines;
    RrXbr xbr;
    /* One iteration is begin (events, state requests, pads, the machine's frame) then end (sound, picture, pacing); a guest
     * that owns the loop runs between the end of one and the begin of the next. What the two halves share: */
    bool ran;                      /* this iteration ran the machine (no menu, no pause) */
    bool driven;                   /* the guest owns the loop */
    bool timing_enabled;
    RrhkTiming timing;
    Uint64 work_started, ticks[7];
    double cpu_started;
    bool ran_frame;                /* timing: a frame was run in this iteration */
    const char *timing_path;
    /* The picture's store (1.7.0): max_width x max_height at open; a machine with pixel_pitch grows it, up to the renderer's
     * largest texture (limit_w x limit_h, 0: not known). upscaled holds upscaled_pixels pixels (Scale2x). */
    int store_w, store_h, limit_w, limit_h;
    size_t upscaled_pixels;
    int refused_w, refused_h;      /* the last picture size the store could not grow to: not tried again until the size changes */
    bool double_refused;           /* Scale2x's buffer could not be made for this store: the picture is shown without it */
} RrhkRun;

/* Pseudo-keys of the kit's own option rows: past every scancode and past the machines' own rows (rrhk_computer.inc uses
 * SDL_NUM_SCANCODES + 1), so that no keyboard sends them. */
#define RRHK_KEY_RUMBLE (SDL_NUM_SCANCODES + 16)
#define RRHK_KEY_START_HELP (SDL_NUM_SCANCODES + 17)   /* the "Start-up reminders" row (1.7.4) */

double rrhk_thread_cpu(void);
void rrhk_timing_write(const RrhkMachine *machine, const char *path, const RrhkTiming *timing,
                       SDL_Renderer *renderer, Uint64 frequency);

/* input.c */
void rrhk_settings_path(void);
void rrhk_store_binding(void);
void rrhk_assign(int player, int action, bool pad, int value);   /* F2: bind, swapping with an action that had it; kept */
void rrhk_clear_binding(void);
const wchar_t *rrhk_autofire_section(void);
void rrhk_open_pads(void);
void rrhk_close_pads(void);
/* The Gamepad row of each player's gamepad page (divergence 10): which pad the player uses. */
void rrhk_pad_next(int player);          /* Enter: Automatic, each connected pad, None */
void rrhk_pad_automatic(int player);     /* Delete: back to Automatic */
void rrhk_pad_value(char *out, size_t size, int player);
/* 1.7.0: the stick dead zone row, the graphics options, the Vibration row (their preferences). */
void rrhk_deadzone_step(int player, bool reset);   /* Enter: next step of 5 %, after the largest 0; Delete: 0 */
void rrhk_gfx_start(bool test_run);      /* window opening: the values in force (defaults in a test run, then --gfx), applied */
void rrhk_gfx_set(int option, int value);   /* the page: apply and keep */
void rrhk_gfx_defaults(void);            /* the page's Restore defaults: every option to its default, applied and kept */
void rrhk_toggle_rumble(void);           /* the Vibration row: flip, keep, stop a vibration in progress */
void rrhk_rumble_stop(void);
bool rrhk_trigger_bound(int side);       /* 0 right, 1 left: player 1 has a control on that trigger (trigger_buttons) */

/* main.c: the plates a game shows for a few seconds when it opens (D17), and the options row that turns them off. */
bool rrhk_start_help(void);
void rrhk_toggle_start_help(void);       /* flip, keep in [Interface] start_help (shared by the games of the folder, like the language) */

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
bool rrhk_deadzone_row(void);        /* the selected row is the Stick dead zone row (a machine with analog sticks) */
int rrhk_page_scroll(void);          /* the first row an F2 control page shows (0 up to fifteen rows; past them it scrolls) */
int rrhk_graphics_rows(void);        /* the graphics page: the machine's options, Filter, Restore defaults */
void rrhk_graphics_draw(SDL_Renderer *renderer);
void rrhk_turn_page(int step);
void rrhk_toggle_settings(void);
void rrhk_hub_key(SDL_Scancode key);  /* the F2 tiles: arrows choose, Enter opens the page */
void rrhk_quit_ask(void);            /* open "Quit?" (No selected) */
bool rrhk_quit_key(SDL_Scancode key);   /* a key on "Quit?"; true: Yes was chosen */
void rrhk_toggle_menu(int kind);     /* Help or Pause: open it, or return to the menu it was opened from */
void rrhk_close_menu(void);          /* Esc, B: back to the menu this one was opened from, or to the game */
void rrhk_menu_draw(SDL_Renderer *renderer);

/* options.c: the only file that includes game_options.h, whose settings are
 * one set of statics per translation unit. */
void rrhk_options_init(const wchar_t *console);
void rrhk_options_keyboard(const char *machine, int count);
bool rrhk_options_event(const SDL_Event *event, int *menu, bool binding_capture);
bool rrhk_options_quit(int menu);
bool rrhk_options_restart(int menu);
bool rrhk_options_component(int key, int button);   /* a key or button that belongs to a quit/restart combination being captured or held */
void rrhk_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate);
void rrhk_options_audio_reset(void);
bool rrhk_sound_toggle_mute(void);   /* M: flip, keep in the preferences, true when muted */
bool rrhk_sound_muted(void);
void rrhk_sound_hold(bool held);     /* the speed is not 100%: the output is silent */
unsigned rrhk_audio_device_serial(void);   /* moves when the output device asked for changes */
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
bool rrhk_combo_capturing(int index, bool gamepad);   /* this combination waits for its keys or buttons */
bool rrhk_combo_set(int index, bool gamepad);         /* this combination has keys or buttons */
void rrhk_combo_clear(int index, bool gamepad);
void rrhk_combo_value(char *out, size_t size, int index, bool gamepad);
const char *rrhk_combo_label(int index);
const char *rrhk_combo_hint(int index);
void rrhk_menu_page_header(const RrhkMenuCtx *ctx, const char *title);
const char *rrhk_filter_name(int filter);
const char *rrhk_display_name(int mode);    /* "Windowed", "Pixel perfect", "Fit to screen", "Stretched" (translated) */   /* the translated name of a picture filter, as the options page shows it */
int rrhk_option_scroll(void);               /* the first row the options page shows (0 up to fourteen rows; past them it scrolls) */
int rrhk_option_selected(void);             /* the selected row of the options page */

/* audio.c */
void rrhk_audio_open(RrhkRun *run);
void rrhk_audio_pause_output(RrhkRun *run);
void rrhk_audio_idle(RrhkRun *run);
void rrhk_audio_wait_room(RrhkRun *run);
void rrhk_audio_push(RrhkRun *run, int16_t *pcm, size_t samples);
void rrhk_audio_frame(RrhkRun *run);
unsigned rrhk_audio_queued(const RrhkRun *run);
bool rrhk_audio_reopen(RrhkRun *run);
SDL_AudioDeviceID rrhk_audio_device_id(const RrhkRun *run);
void rrhk_audio_pace(RrhkRun *run, Uint64 now);
void rrhk_audio_close(RrhkRun *run);

/* ring.c: the callback-ring output (RRHK_AUDIO_RING). */
bool rrhk_ring_open(unsigned rate, unsigned channels, unsigned margin_ms);
void rrhk_ring_start(void);
bool rrhk_ring_reopen(void);     /* another output device: same ring, same reserve */
void rrhk_ring_submit(const int16_t *pcm, uint32_t count);
void rrhk_ring_clear(void);
void rrhk_ring_close(void);
SDL_AudioDeviceID rrhk_ring_device(void);

/* events.c */
void rrhk_poll_events(RrhkRun *run);
bool rrhk_set_filter(RrhkRun *run, int filter);   /* a new texture for the filter, kept in the preferences; false: no texture */
#endif
