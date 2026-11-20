/* Shared by the files of native/hostkit/shell only; machine adapters use hostkit.h. */
#ifndef RR_HOSTKIT_INTERNAL_H
#define RR_HOSTKIT_INTERNAL_H
#include "hostkit.h"
#include "audio_cushion.h"
#include "scanline_sdl.h"
#include "xbr_sdl.h"

bool rrhk_options_hidden(int button);  /* options.c: a button of the Options combination still held from the menu's press */
#define RRHK_COMBO_ROWS 7     /* Quit, Restart, Quick save, Quick load (1.7.5), Fast forward, Max speed (1.7.6), Options (1.9.0) */
#define RRHK_COMBO_FAST 4
#define RRHK_COMBO_MAX 5

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
    Uint64 presented;              /* 1.7.7: when the last present returned */
} RrhkRun;

/* 1.7.7 (HOST_KIT D30): Sync to display, the row of the options page kept per machine ([<Console>.Video] sync).
 * Auto: locked when the screen's measured refresh is within 1 % of the machine's rate, otherwise as before 1.7.7 (Windows
 * presents without waiting, Linux with the vsync hint). Locked: the same up to 3 %. Free: the machine's own clock, vsync off on
 * both systems. Variable refresh: free, vsync off, and on Windows the Direct3D 12 renderer, whose presents allow tearing so a
 * FreeSync / G-Sync screen follows the game (DXGI cannot tell whether the screen and the driver do: the player's choice).
 * Locked, the present paces the game (the machine runs at the refresh) and every sound path follows by its rate
 * (audio_cushion.h rr_drc_ratio). Never locked: a hidden-window test run, SDL_RENDER_VSYNC set, the menus and pause (vsync stays
 * on), fast forward and any speed but 100 % (vsync off meanwhile). */
enum { RRHK_SYNC_AUTO, RRHK_SYNC_LOCKED, RRHK_SYNC_FREE, RRHK_SYNC_VARIABLE, RRHK_SYNC_MODES };
#define RRHK_SYNC_AUTO_GAP 0.01
typedef struct {
    int mode;                      /* the row's value */
    bool active;                   /* not a test run, no SDL_RENDER_VSYNC: the kit drives vsync */
    bool vsync;                    /* the renderer presents on the refresh now */
    bool lock;                     /* the decision: locked while playing */
    bool remeasure, announce;      /* measure the refresh at the next iteration (start, row, other display); then say the outcome */
    bool vrr_renderer;             /* the window was opened with Direct3D 12 for Variable refresh */
    const char *why;               /* the English reason the decision is free, NULL when locked or Free/Variable asked */
    double refresh_hz;             /* measured, 0: unknown */
    double machine_hz;             /* the machine's rate the decision was made for */
    int quick_presents;            /* locked presents in a row that did not wait for a refresh */
    uint64_t held[4];              /* locked frames held 1, 2, 3, 4 or more refreshes (the cadence; not a latency) */
} RrhkSync;
extern RrhkSync rrhk_sync;
bool rrhk_sync_decide(int mode, double refresh_hz, double machine_hz);   /* pure: lock or not */
void rrhk_sync_load(bool test_run);       /* the row's value, before the renderer (Variable refresh: the renderer hint) */
void rrhk_sync_next(void);                /* the row: Auto, Locked, Free, Variable refresh; kept */
void rrhk_sync_value(char *out, size_t size);   /* the row's value as shown */
void rrhk_sync_notice(void);              /* the outcome, named by a notice */

/* Pseudo-keys of the kit's own option rows: past every scancode and past the machines' own rows (rrhk_computer.inc uses
 * SDL_NUM_SCANCODES + 1), so that no keyboard sends them. */
#define RRHK_KEY_RUMBLE (SDL_NUM_SCANCODES + 16)
#define RRHK_KEY_START_HELP (SDL_NUM_SCANCODES + 17)   /* the "Start-up reminders" row (1.7.4) */
#define RRHK_KEY_WIDESCREEN (SDL_NUM_SCANCODES + 19)   /* the "Screen format: 4:3 / 16:9" row (1.7.6) */
#define RRHK_KEY_SYNC (SDL_NUM_SCANCODES + 20)         /* the "Sync to display" row (1.7.7, D30) */
#define RRHK_KEY_TURN_BADGE (SDL_NUM_SCANCODES + 21)   /* the "Turn badge" row (1.9.0, in a session) */

/* menu.c: the row icons (1.7.5) */
int rrhk_action_icon(const char *name, char letters[4]);   /* the icon of a control by its English name; a face button's letters */
int rrhk_option_icon(int key);                              /* the icon of an options row by its key */
int rrhk_combo_icon(int index);                             /* Quit, Restart, Quick save, Quick load */
int rrhk_gfx_icon(const char *name);                        /* a graphics option by its English name */
void rrhk_draw_icon(SDL_Renderer *renderer, int ox, int oy, int unit, int x, int y, int icon, const char *letters);

double rrhk_thread_cpu(void);
void rrhk_timing_write(const RrhkMachine *machine, const char *path, const RrhkTiming *timing,
                       SDL_Renderer *renderer, Uint64 frequency);

/* input.c */
void rrhk_settings_path(void);
void rrhk_store_binding(void);
void rrhk_assign(int player, int action, bool pad, int value);   /* F2: bind, swapping with an action that had it; kept */
void rrhk_clear_binding(void);
void rrhk_restore_page(void);
bool rrhk_restore_row(void);
bool rrhk_combo_plain(int index, bool gamepad);
void rrhk_combo_restore(bool gamepad);
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
int rrhk_pad_rows_here(void);            /* the machine's own rows at the top of the page shown (RrhkMachine.pad_rows) */
const RrhkPadRow *rrhk_pad_row_at(int row);   /* the machine row at this page row, NULL for a row of the kit */
int rrhk_action_row(void);               /* the selected row as an action / combination index (the machine rows come first) */
bool rrhk_trigger_step(bool down, int value);
int rrhk_stick_direction(int axis, int value);    /* input.c: the RRHK_PAD_*STICK_* a stick axis value pushes past the threshold, else -1 */
const char *rrhk_pad_binding_name(int value);     /* "A", "L2", "L stick up" (English, for rr_tr), NULL for none */   /* L2/R2 as a button: game_options.h's one reading (threshold, hysteresis) */
bool rrhk_options_fast_forward(int menu);   /* 1.7.6: player 1's pad combination held (R2 by default) */
bool rrhk_options_max_speed(int menu);      /* 1.7.6: pressed once (L2 by default) */
unsigned rrhk_combo_triggers(int index);    /* the triggers of a combination's buttons: 1 right, 2 left */
void rrhk_speed_combos(void);
void rrhk_open_graphics(void);
void rrhk_widescreen_load(const char *title);   /* input.c: this game's screen format, at start */
void rrhk_widescreen_toggle(void);              /* input.c: 4:3 <-> 16:9, kept for this game, named by a notice */              /* events.c: the graphics page, back to the menu it was opened from */               /* events.c: the pad's speed combinations, each frame */
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
void rrhk_options_notice(void);           /* shows why a combination was not taken, once */
bool rrhk_options_quick_save(int menu);     /* 1.7.5: player 1's pad combination, once per hold */
bool rrhk_options_quick_load(int menu);
bool rrhk_options_component(int key, int button);   /* a key or button that belongs to a quit/restart combination being captured or held */
/* 1.8.2: where a pad button stands in the restart combination (a bit set): 1 a member of it (a combination of two buttons or more),
 * 2 another member is held on that pad now, 4 this very button is held. 0: not a member. rrhk_events.c defers the host Pause on
 * such a button, so that Start+Select (Pause on Start) resets instead of pausing. */
unsigned rrhk_restart_combo_state(SDL_JoystickID pad, int button);
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
const char *rrhk_combo_hint(int index, bool gamepad);
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
void rrhk_audio_set_base(RrhkRun *run, double base);   /* 1.7.7 (D30): machine_hz / refresh_hz while locked, else 1.0 */
double rrhk_audio_base(void);

/* ring.c: the callback-ring output (RRHK_AUDIO_RING). */
bool rrhk_ring_open(unsigned rate, unsigned channels, unsigned margin_ms);
void rrhk_ring_start(void);
bool rrhk_ring_reopen(void);     /* another output device: same ring, same reserve */
void rrhk_ring_submit(const int16_t *pcm, uint32_t count);
void rrhk_ring_clear(void);
void rrhk_ring_close(void);
SDL_AudioDeviceID rrhk_ring_device(void);
void rrhk_ring_set_base(double base);   /* 1.7.7 (D30) */

/* events.c */
void rrhk_poll_events(RrhkRun *run);
bool rrhk_set_filter(RrhkRun *run, int filter);   /* a new texture for the filter, kept in the preferences; false: no texture */

/* main.c, 1.7.6 (HOST_KIT D29): a Linux game's launcher `<game>.desktop`, healed after its folder moved. The text: -1 not ours
 * (no X-RetroRecomp-Identity line), 0 ours and current (or a path too long to write), 1 ours and stale: `healed` (malloc'd) has
 * its Exec, Path and Icon lines for `exe`, every other byte as it was. The file (not on Windows): the same, read and written
 * atomically (mode 0755), then our line taken out of the folder's .hidden; -1 also for any failure. */
int rrhk_launcher_text(const char *text, size_t len, const char *exe, char **healed, size_t *healed_len);
#ifndef _WIN32
int rrhk_heal_launcher(const char *exe);
#endif

/* session.c: multiplayer (hostkit_session.h). rrhk_session_on is false unless the converter started the game in a session:
 * then and only then does any of the functions below do anything. */
extern bool rrhk_session_on;
bool rrhk_session_open(RrhkRun *run);          /* at open; false: the session could not start (the run stops, the reason said) */
/* Before the machine's frame: report the local pad, execute the worker's commands (silent frames included); 1: run the live
 * frame now with the session's port words, 0: nothing to run this iteration (waiting or paused), -1: the session ended. */
int rrhk_session_frame(RrhkRun *run, uint64_t input_frame);
void rrhk_session_frame_done(RrhkRun *run, Uint64 cost_ticks);   /* after the live frame ran */
bool rrhk_session_silent_done(RrhkRun *run);   /* a driven machine's silent frame just ended: not presented, not paced */
uint16_t rrhk_session_port(int port);         /* the word of a port for the frame being run */
Uint64 rrhk_session_period(Uint64 period);    /* the frame period with the worker's time sync applied */
double rrhk_session_audio_base(void);         /* the sound's factor under that time sync (rrhk_audio_set_base) */
bool rrhk_option_key_run(int key);            /* options.c: this key is the shortcut of a row that changes the run */
bool rrhk_session_paused(void);
/* The player asked to restart in a session: the host's request goes to the worker, which restarts every game at the same
 * frame (RRHK_RUN_RESET); a guest is told only the host can. true: the request was taken (the host). */
bool rrhk_session_restart(void);
void rrhk_session_state(bool load);          /* F8 / F9 in a session: the host's for everyone, this match only */
bool rrhk_session_states(void);             /* this seat is the host and its machine keeps the match's state */
void rrhk_session_close(RrhkRun *run, int reason);
/* input.c: the pad word of this PC's player as today's solo game reads it (player `player`'s bindings, autofire applied). */
uint16_t rrhk_local_pad_word(int player, uint64_t frame);
bool rrhk_local_pad_axes(int player, uint64_t frame, int16_t axes[RRHK_AXES]);   /* this PC's sticks, never the session's */
void rrhk_session_axes(int port, int16_t axes[RRHK_AXES]);                         /* a port's sticks of the frame being run */
/* chat.inc (in session.inc): the in-game chat of a session. rrhk_chat_event comes before every other handler; rrhk_chat_draw
 * after the menus and notices; the notices' line moves above the chat while it is open. */
bool rrhk_chat_open(void);
bool rrhk_chat_holds_word(void);               /* open, or closed with a key or button still held from then: neutral word */
void rrhk_give_key(SDL_Scancode key);         /* a key on « Give the controller » (the host, in turns) */
bool rrhk_turn_badge(void);                    /* the turn badge shown ([Interface] turn_badge, the options row) */
void rrhk_toggle_turn_badge(void);
bool rrhk_relaunch_ask(SDL_Scancode key);     /* the host's « Change this option? » (session): true while asked, the key held */
bool rrhk_relaunch_asking(void);
bool rrhk_hub_take_restart(void);              /* the F2 Restart tile was chosen (once): the loop restarts as the combination does */
bool rrhk_chat_offered(void);                  /* a session is running: the F2 Chat tile and the keys are there */
void rrhk_chat_begin(bool grid);               /* open the entry (grid: with the on-screen keyboard) */
bool rrhk_chat_event(const SDL_Event *event);
void rrhk_chat_draw(SDL_Renderer *renderer);
int rrhk_chat_notice_line(void);
/* audio.c: take the machine's sound of the frame just run and drop it (a silent frame). */
void rrhk_audio_discard(RrhkRun *run);
#endif
