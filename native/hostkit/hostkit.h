/* Retro-Recomp host kit: the contract between the shared player shell
 * (native/hostkit/shell) and one machine adapter (native/hostkit/adapters).
 *
 * The kit owns everything an exported game does around the machine: window,
 * picture presentation, controls, menus, languages, audio output, quick-state
 * and battery requests, preferences and command-line/headless options. The
 * machine provides picture, audio, a pad word per player and honesty counters.
 * The kit contains no machine header and no machine licence text: the adapter
 * is the only file that sees both sides. MIT, like the other shells.
 *
 * This is the first realisation of docs/HOST_KIT.md section 2 (phase 1: Mega
 * Drive, Super Nintendo, Neo Geo, CPS-1; phase 2: NES; phase 3: X68000; phase 4:
 * Master System and Game Gear). The machine functions of the 16-bit consoles are
 * still the rr16_* link-time symbols of the 16-bit contract (retro_console16.h) and
 * those of the NES are the cyc_* functions of its runner; the adapter wraps them
 * in the table below, and nothing in the kit looks at a machine macro. */
#ifndef RR_HOSTKIT_H
#define RR_HOSTKIT_H
#include <SDL.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <wchar.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RRHK_MAX_PLAYERS 4
#define RRHK_CORE_CAPTION "Native CPU, emulated hardware"   /* RrhkMachine.native_caption of a game on a complete emulator core */
/* Controls of a machine, in menu order (1.7.0: 20, so that a PlayStation pad's 17 fit; 12 before). The pad word given to the
 * machine stays 16 bits: host-side actions (`bit` 0) do not use one. An F2 page shows fifteen rows at once and scrolls past. */
#define RRHK_MAX_ACTIONS 20
/* A gamepad binding may name a trigger, held past the stick threshold (D1): on every machine since 1.7.5. The two
 * values are fixed, outside any range of SDL's buttons (SDL 2 has 21, SDL 3 fewer than 32), and stored as such in the
 * preferences: a saved binding means the same trigger after an SDL update. */
#define RRHK_PAD_LEFT_TRIGGER ((SDL_GameControllerButton)64)
#define RRHK_PAD_RIGHT_TRIGGER ((SDL_GameControllerButton)65)
/* 1.7.6: a stick direction as a binding of a digital control, on every machine (66..73, fixed and stored as such): pushed past
 * the stick threshold of D1, released under half of it (rr_trigger_step). It only adds a press: what a machine reads of the
 * sticks themselves (rrhk_pad_axes) is unchanged. A host-side action (bit 0) refuses it, as it refuses a trigger. */
#define RRHK_PAD_LSTICK_UP ((SDL_GameControllerButton)66)
#define RRHK_PAD_LSTICK_DOWN ((SDL_GameControllerButton)67)
#define RRHK_PAD_LSTICK_LEFT ((SDL_GameControllerButton)68)
#define RRHK_PAD_LSTICK_RIGHT ((SDL_GameControllerButton)69)
#define RRHK_PAD_RSTICK_UP ((SDL_GameControllerButton)70)
#define RRHK_PAD_RSTICK_DOWN ((SDL_GameControllerButton)71)
#define RRHK_PAD_RSTICK_LEFT ((SDL_GameControllerButton)72)
#define RRHK_PAD_RSTICK_RIGHT ((SDL_GameControllerButton)73)
#define RRHK_PAD_IS_STICK(value) ((int)(value) >= 66 && (int)(value) <= 73)

/* Menu numbers of RrhkUi.menu (options.c checks them against game_options.h). */
#define RRHK_MENU_HELP 1
#define RRHK_MENU_CONTROLS 2
#define RRHK_MENU_PAUSE 3          /* a machine with a host-side Pause/Menu action (Master System, Game Gear) */
#define RRHK_MENU_PAGE 4
#define RRHK_MENU_OPTIONS 5
#define RRHK_MENU_GRAPHICS 6       /* decision D14: F3 on a machine that declares gfx_options */
#define RRHK_MENU_HUB 7            /* 1.7.4: F2 opens tiles, one per page (controls of each player, the machine's page, options) */
#define RRHK_MENU_QUIT 8           /* 1.7.4: "Quit?" Yes / No, asked by Esc in play and by the Quit combination */
#define RRHK_MENU_GIVE 9           /* 1.9.0: multiplayer, turns: the host gives the controller to a seat (from the F2 tiles) */

/* The sticks of a player (RrhkMachine.analog_sticks, rrhk_pad_axes): -32767..32767 since 1.7.6 (SDL's -32768 is given as -32767, a
 * recorded replay's axes as recorded), centre 0, SDL's axes (Y down positive). */
#define RRHK_AXIS_LX 0
#define RRHK_AXIS_LY 1
#define RRHK_AXIS_RX 2
#define RRHK_AXIS_RY 3
#define RRHK_AXES 4
#define RRHK_DEADZONE_MAX 30       /* percent: the largest dead zone the F2 row offers */
#define RRHK_MAX_GFX_OPTIONS 12    /* rows of the graphics page before its Filter and Restore rows */

/* Kinds of pointing device; the numbers are those of the guns in gun16.h
 * (the adapters check it). */
enum { RRHK_POINTER_NONE, RRHK_POINTER_MENACER, RRHK_POINTER_JUSTIFIER, RRHK_POINTER_SCOPE, RRHK_POINTER_ZAPPER,
       RRHK_POINTER_PHASER };

/* How the machine's sound reaches the device: pushed into a device queue as 48 kHz stereo (the
 * 16-bit consoles), or kept in a ring that the device callback drains, the machine's own mono rate
 * converted by the callback (the NES; the model HOST_KIT.md decision D5 chooses for every family). */
enum { RRHK_AUDIO_QUEUE, RRHK_AUDIO_RING };
/* DIR: the four directions; FACE: autofire-eligible buttons, always listed
 * first after nothing else; SYSTEM: every other button (Start, Coin, Mode,
 * shoulders...). */
typedef enum { RRHK_DIR, RRHK_FACE, RRHK_SYSTEM } RrhkGroup;

/* One control of the machine, in menu order. `bit` is the bit of the pad word
 * given to the machine. Player 1's default keys listed with a `letter` follow
 * the keyboard layout (W means W on AZERTY and QWERTY alike); every other
 * default is a physical scancode. */
typedef struct {
    const char    *name;      /* English label, translated by the catalogue */
    const wchar_t *ini_key;   /* key under [<Console>.Keyboard.PlayerN] / .Gamepad.PlayerN */
    uint16_t       bit;
    RrhkGroup      group;
    SDL_Keycode    letter;    /* layout-aware default of player 1, 0 = none */
    SDL_Scancode   key[RRHK_MAX_PLAYERS];
    SDL_GameControllerButton pad[RRHK_MAX_PLAYERS];
    /* 1.7.6: what the gamepad page shows for a row the pad does not bind (a host-side row the machine reads otherwise, as the
     * Nintendo 64's keyboard stick, which is the pad's left stick): English, translated; NULL shows "-". */
    const char    *pad_label;
    /* 1.7.6: player 1's letter default before 1.7.6 (W X C A S D, layout-aware), when the row's default moved (to S D F E R T, by
     * position): a saved key still equal to it on this layout moves to the new default by itself; a key the player chose stays. */
    SDL_Keycode    former_letter;
} RrhkAction;

/* One option of a 3D machine's graphics page (decision D14), declared by the adapter. Changing it changes only what the
 * player sees, never the machine's timing: an option that changes the guest's speed (CPU or disc speed, overclock) is not
 * declared. */
typedef struct {
    const char    *name;      /* English, translated by the catalogue ("Internal resolution") */
    const wchar_t *ini_key;   /* key under [<ini_section>.Video]; also the name of `--gfx <ini_key>=<index>`. Plain ASCII only:
                               * the timing report prints it with %ls, which glibc converts by the locale */
    const char *const *values;   /* English labels, translated ("1x (native)", "2x", ...) */
    int count, def;           /* number of values, index of the default: the reference setting, the one every gate uses */
} RrhkGfxOption;

/* Mouse converted to picture coordinates, for light guns and scopes. */
typedef struct {
    int x, y;
    bool fire, aux, secondary, start, turbo, pause, offscreen;
} RrhkPointer;

typedef struct RrhkUi {
    const struct RrhkMachine *machine;
    wchar_t ini_file[32768], data_dir[32768];
    wchar_t read_file[32768];  /* where the preferences are read from: ini_file, or the machine's former file until the first write */
    wchar_t video_section[64], pointer_section[64];
    int menu, parent_menu, player, row, gamepad_page, capturing, filter, fullscreen, language, autofire;
    /* parent_menu: the menu a menu opened from the Pause menu returns to (Help or F2 from Pause, then back to Pause) */
    int paused;                /* F11 (X68000): the machine does not run, the picture stays, "Paused" is drawn */
    /* The sound and speed controls of every console (decision D12). The sound values are those read at start, from the
     * preferences or from the machine's former file; after the start they live in the options (the audio callback reads
     * them). max_speed is the toggle of the backquote key (5x), fast_hold the Tab key or the right trigger (2.5x) held. */
    int audio_volume, audio_muted, max_speed, fast_hold;
    char audio_device[256];
    char status[80];
    Uint64 status_until;
    int pointer_shape, pointer_size, pointer_color, pointer_turbo;
    RrhkPointer mouse;
    SDL_Scancode keys[RRHK_MAX_PLAYERS][RRHK_MAX_ACTIONS];
    SDL_GameControllerButton buttons[RRHK_MAX_PLAYERS][RRHK_MAX_ACTIONS];
    SDL_GameController *pads[RRHK_MAX_PLAYERS];
    /* 1.7.0 (HOST_KIT.md section 2.4): what a machine that declares sticks, graphics options or rumble keeps. */
    int deadzone[RRHK_MAX_PLAYERS];        /* percent, 0..RRHK_DEADZONE_MAX: the F2 row of each player's gamepad page */
    int gfx[RRHK_MAX_GFX_OPTIONS];         /* the value index in force of each graphics option */
    int gfx_row;                           /* the selected row of the graphics page */
    int rumble;                            /* the shared Vibration row: [Manettes] rumble, default on */
    int widescreen;                        /* 1.7.6: this game shown at 16:9 ([<Console>.Widescreen] <game>=1) */
} RrhkUi;

/* Where the loop is, for the machine hooks that run inside it. */
typedef struct {
    bool audio_playing;
    unsigned audio_queued;     /* bytes in the device queue, 0 without a device */
    unsigned audio_rate, audio_period;
} RrhkAudioProbe;

typedef struct RrhkMenuCtx {
    SDL_Renderer *renderer;
    int ox, oy, unit;
} RrhkMenuCtx;
typedef struct RrhkOptionRows RrhkOptionRows;

/* A machine's own row at the top of one player's gamepad page (1.7.5: the Amiga's mouse port): a setting of that pad with a few
 * values. Enter (A) chooses the next value, - the previous one; the machine applies and keeps it in `set` (and says so with its
 * own notice if it wants one). The texts are English, looked up in the game catalogue. */
typedef struct {
    int player;                    /* 1-based: the player whose gamepad page shows the row */
    const char *label;             /* "Mouse port" */
    int count;                     /* number of values */
    const char *const *values;     /* {"Auto (last used)", "Mouse", "Pad 2"} */
    int (*get)(void);              /* the value now, 0 .. count - 1 */
    void (*set)(int value);
    int (*icon)(void);             /* the row's icon now (retro_menu.h RR_ICON_ROW_*); NULL: the generic one */
} RrhkPadRow;

/* An extra F2 page of the machine, after the controls (DIP switches, guns). */
typedef struct {
    const char *title;                                   /* English, translated */
    bool (*available)(void);                             /* NULL: always */
    void (*draw)(RrhkUi *ui, const RrhkMenuCtx *ctx);    /* the page body */
    void (*key)(RrhkUi *ui, SDL_Scancode key);           /* a key while the page is open */
    bool run_changing;                                   /* its settings change the run (DIP switches): read-only in a
                                                          * multiplayer session, the host sets them */
} RrhkPage;

typedef struct RrhkMachine {
    /* identity and layout */
    const wchar_t *ini_section;    /* "MegaDrive", "SNES", "NeoGeo", "CPS1": legacy names kept */
    const char *console_name;      /* "Mega Drive" */
    int table_players;             /* rows of the binding tables */
    int (*players)(void);          /* controllers in play (CPS-1 boards read up to four) */
    const RrhkAction *actions;
    int action_count;
    int up, down, left, right, start;   /* indices into actions */
    int max_width, max_height;     /* backing store of the picture */
    double frame_seconds;
    int pointer;                   /* RR_GUN_* kind of the game, 0 without a pointer */
    bool own_audio;                /* the engine opens its own audio device (Mega Drive) */
    int audio_model;               /* RRHK_AUDIO_QUEUE (default) or RRHK_AUDIO_RING */
    unsigned audio_rate;           /* ring: source rate of the mono 16-bit PCM */
    bool (*audio_enable)(unsigned rate);   /* ring: the machine starts producing sound; false closes the device */
    unsigned audio_channels;       /* ring: 1 (default, mono) or 2 (interleaved stereo; `audio` and the ring count frames) */
    unsigned audio_margin_ms;      /* ring: margin before a period may start, on top of the adaptive reserve; 0: 30 ms (the NES) */

    /* behaviours the kit keeps per machine until HOST_KIT.md settles them. Settled on 28 October 2026 and
     * therefore no longer settings: F2 pad capture takes the selected player's pad only (divergence 3) and F6
     * autofire shows one shared notice from the catalogue (divergence 11), both in the shell for every machine. */
    bool pointer_keeps_player2;    /* a pointer game still reads the second pad (Zapper) */
    const wchar_t *pointer_section;   /* preferences section of the pointer page, NULL: <ini_section>.Gun */
    int pointer_max;               /* largest reticle size of the page, 0: 12 */
    const char *save_failed_en, *save_failed_fr;   /* F8 failure notice, NULL: the kit's */
    /* Where the machine keeps settings its own way (X68000, phase 3: preferences layout is divergence 14/15, still the
     * legacy one there). NULL / false: the kit's layout. */
    const wchar_t *video_section;     /* section of filter and display mode, NULL: <ini_section>.Video */
    const wchar_t *autofire_section;  /* section of the autofire key, NULL: Manettes */
    bool indexed_bindings;            /* bindings are [<ini_section>] p<player>_key<action index> / p<player>_pad<action index> */
    bool bindings_clearable;          /* before 1.7.6, Delete / X cleared a binding on these machines only; every machine now (unread) */
    int machine_fkeys;                /* a computer's own F1..Fn: the options page offers to hand them to the guest, 0: none */
    bool audio_chunked;               /* queue model: the machine may hold more than one buffer of sound per frame */
    /* The guest owns the loop (Master System, Game Gear: the recompiled code calls the host once per frame). The adapter
     * does not call rrhk_main: it calls rrhk_open, then rrhk_frame_done from the guest's frame callback, then rrhk_close.
     * `run_frame` then only hands the pad words over (the guest runs after the callback returns) and `audio` is not used
     * when `own_audio` is set. The kit starts SDL without the audio subsystem: the machine opens its own device. */
    bool driven;
    int host_pause;                   /* 1 + the index of a host-side Pause/Menu action (its `bit` is 0), 0: none */
    bool minimum_window;              /* the window cannot be made smaller than the picture it opened with */
    int open_width, open_height;      /* the machine's usual picture when it only reports it after its first frame (Mega Drive: 320 x 240); 0: what it reports at open */
    bool state_deferred;              /* state_file only requests; the machine reports the outcome with rrhk_state_done */
    const wchar_t *legacy_ini;        /* the machine's former preferences file name, beside the executable (read until the first write) */
    void (*window_icon)(SDL_Window *window);   /* NULL: the shared embedded icon */

    /* the machine (still the rr16_* functions) */
    void (*reset)(void);
    bool (*run_frame)(uint16_t p1, uint16_t p2);
    void (*pause)(bool paused);
    const uint32_t *(*pixels)(void);           /* NULL (or a 0 x 0 visible size): no picture yet, shown black (1.7.7) */
    int (*visible_width)(void);
    int (*visible_height)(void);
    int (*raster_height)(void);
    int (*display_width)(void);
    size_t (*audio)(int16_t *pcm, size_t capacity);
    uint64_t (*interpreted)(void);
    uint64_t (*audio_interpreted)(void);
    uint64_t (*device_interpreted)(void);   /* NULL without a cartridge device */
    bool (*state_path)(wchar_t *path, size_t capacity);
    bool (*state_ready)(void);
    bool (*state_file)(const wchar_t *path, bool load);
    void (*pointer_input)(RrhkPointer pointer);
    uint64_t (*input_frame)(void);          /* guest frame counter; NULL: the kit counts */

    /* optional capabilities (NULL when the machine has none) */
    const RrhkPage *page;                   /* gun page or DIP switches */
    void (*settings_loaded)(RrhkUi *ui);    /* preferences read: machine options */
    void (*option_rows)(int slot, RrhkOptionRows *rows);   /* slot 0 after F4, 1 after F7 */
    void (*help_lines)(int slot, const char **lines, int *count);   /* slot 0 after F4, 1 after F9 */
    void (*help_controls)(RrhkUi *ui, const RrhkMenuCtx *ctx, int y);
    bool (*key_event)(RrhkUi *ui, SDL_Scancode key, bool *running);  /* true: handled */
    void (*timing_report)(FILE *file, Uint64 frequency);   /* extra JSON fields */
    unsigned (*frame_limit)(void);          /* hidden-window test frame count */
    void (*frame_start)(void *window, void *renderer);
    void (*before_frame)(const RrhkAudioProbe *audio, uint64_t input_frame);
    bool (*cost_enabled)(void);
    void (*cost)(double busy_ms, double present_ms);
    void (*before_present)(SDL_Renderer *renderer);
    void (*finished)(double elapsed_seconds);
    /* Computers (X68000, phase 3). */
    bool (*event)(const SDL_Event *event, bool *running);   /* first look at every event; true: consumed */
    bool (*keyboard_pad)(void);             /* false: the keyboard bindings are not read (the guest has the keyboard) */
    bool (*action_held)(int player, int action);   /* a device of the machine (a captured mouse) also holds this action */
    bool (*fast_forward)(void);             /* true: no pacing, no sound, a picture every eighth frame */
    bool (*game_rect)(int canvas_w, int canvas_h, int display_mode, SDL_Rect *rect);   /* the machine's own placement */
    bool (*help_page)(RrhkUi *ui, const RrhkMenuCtx *ctx);   /* true: drew the whole help page */
    /* Master System, Game Gear (phase 4). */
    void (*pause_page)(RrhkUi *ui, const RrhkMenuCtx *ctx);   /* the body of the Pause menu (RRHK_MENU_PAUSE) */
    /* Sound controls (1.6.3). A machine that opens its own sound device (own_audio: Mega Drive, Master System, Game Gear)
     * closes it and opens it again with rrhk_audio_device() when the player chooses another output; false: it could not. */
    bool (*audio_reopen)(void);
    SDL_AudioDeviceID (*audio_device_id)(void);   /* the id SDL gave that device, 0 when it has none: an SDL_AUDIODEVICEREMOVED for it reopens it */
    /* 1.7.7 (D30, Sync to display): while the game is locked to the display, the factor its own sound output applies to the
     * length of what the machine made, base = machine_hz / refresh_hz (audio_cushion.h rr_drc_ratio adds the fill's
     * correction); exactly 1.0 otherwise, the output then as before. Called when the value changes. NULL: a machine that
     * opens its own device and cannot follow is never locked. */
    void (*audio_ratio)(double base);
    /* Called once the preferences and the sound controls are read, after the kit opened its own sound output: a machine that
     * opened its device before that (Mega Drive) attaches the kit's sound stage (rrhk_options_audio) to it here. */
    void (*sound_ready)(void);
    /* Game Boy (phase 5). */
    bool even_scale2x;                /* Scale2x shows the picture at an even whole multiple (the Game Boy sets it; the Master System and Game Gear apply the same rule in their own game_rect) */
    bool lcd_screen;                  /* a handheld's LCD: F3 also offers the LCD grid (HOST_KIT D35) */
    /* Sticks, the graphics page, larger pictures, rumble and discs (1.7.0, HOST_KIT.md section 2.4 and D14). Every field is
     * off when left out (0, false, NULL): a machine that declares none of them behaves exactly as before. */
    int analog_sticks;                /* sticks per player the machine reads with rrhk_pad_axes (1 or 2). Not 0: the left stick no
                                       * longer drives the four directions (the d-pad still does), and each gamepad page of F2 has
                                       * a "Stick dead zone" row */
    /* A machine that replays a script inside the window gives its recorded axes here; true: rrhk_pad_axes returns them as they
     * are (no dead zone). NULL or false: the gamepad's. */
    bool (*script_axes)(int player, uint64_t frame, int16_t axes[RRHK_AXES]);
    /* Actions that push the left stick to an edge from keys or buttons (a host-side action, bit 0): LX left, LX right, LY up,
     * LY down, -1 for none. In a multiplayer session the kit folds them into the sticks this PC sends, so a keyboard player's
     * stick reaches the other seats; alone the machine applies them as before. NULL: none. */
    const int *stick_actions;
    /* The triggers are buttons of the machine's own pad (a PlayStation's L2 and R2), which its default bindings use. Since 1.7.5
     * every machine accepts a trigger binding (RRHK_PAD_LEFT_TRIGGER, RRHK_PAD_RIGHT_TRIGGER: F2 captures a trigger pulled on
     * the selected player's pad, the one trigger reading holds it), so the field only says so; a trigger that player 1 has
     * bound is no longer a speed control (D12), an unbound one still is. */
    bool trigger_buttons;
    /* The graphics page (D14). NULL: F3 cycles the 2D filters as on every other machine. Otherwise F3 opens the page; gfx_apply
     * is called between two frames, never inside run_frame: once per option when the window opens (the saved value, or the
     * default in a hidden-window test run) and then at each change. */
    const RrhkGfxOption *gfx_options;
    int gfx_option_count;             /* at most RRHK_MAX_GFX_OPTIONS */
    void (*gfx_apply)(int option, int value);
    /* The picture may grow past max_width x max_height (an internal resolution): the rows of pixels() are pixel_pitch() pixels
     * apart, and the kit makes its texture larger when visible_width/visible_height exceed it, up to rrhk_picture_limit. NULL:
     * the store is max_width x max_height and the rows are max_width apart, as before. */
    int (*pixel_pitch)(void);
    bool rumble;                      /* the machine calls rrhk_rumble: the options page shows the shared Vibration row */
    /* The window title's words while nothing is interpreted. NULL: "Native code". A game that runs on a complete emulator core, with
     * native code for its main CPU only, says RRHK_CORE_CAPTION: its picture, sound and chips are the core's (docs/ARCHITECTURE.md). */
    const char *native_caption;
    /* Discs. host_media: 1 + the index of a host-side "Change disc" action (its `bit` is 0, like host_pause), 0: none. Pressed in
     * play, it asks media_select for the next disc (after the last, the first) and shows "Disc 2/3". The swap itself (lid,
     * eject, insert over several frames) is the machine's. */
    int host_media;
    /* 1.7.6: the machine's games may draw an anamorphic widescreen picture (squeezed by their own 16:9 option): the options page
     * offers "Screen format: 4:3 / 16:9", kept per game, and at 16:9 the kit shows the picture 16 wide for 9 high. Only the
     * displayed rectangle changes; the machine and its picture do not. false: no row. */
    bool widescreen;
    /* Rows of the machine on a player's gamepad page, above its controls (RrhkPadRow). NULL / 0: none. */
    const RrhkPadRow *pad_rows;
    int pad_row_count;
    int (*media_count)(void);
    int (*media_current)(void);       /* 0-based */
    bool (*media_select)(int index);  /* false: refused (the notice then names the disc in place) */
    /* Multiplayer (hostkit_session.h). Every field is NULL when left out, and none is called outside a session. */
    /* An in-process snapshot for rollback: never a file, never sent, no envelope, no allocation per call, valid after any
     * run_frame. NULL: the machine plays on the delay tier only. snap_save returns the bytes written, 0 on failure. */
    size_t (*snap_bound)(void);
    size_t (*snap_save)(void *buffer, size_t capacity);
    bool (*snap_load)(const void *buffer, size_t size);
    /* The guest's deterministic state after the last frame, as named fields in a fixed byte order (never a raw struct), the
     * same on Windows and Linux. A machine without it is not offered in multiplayer. */
    uint64_t (*digest)(void);
    /* What a frame may do outside the guest (cartridge save writes, fallback recording): off for silent frames, and for a
     * guest's cartridge save during the whole session. NULL: none. */
    void (*side_effects)(bool allowed);
    /* A run-changing option the host pushes before frame 0, from the machine's declared list. false: cannot honour it. */
    bool (*session_option)(const char *key, const char *value);
    /* This PC's values of those options as "key=value" lines separated by '\n' (plain ASCII, what session_option takes),
     * written into `out` (at most `capacity` bytes), returning the length: the host's are sent to every seat and locked for the
     * match (Arthur, 17 Nov 2026: the options that change the run are the host's, never forced off). NULL: none. */
    size_t (*session_options)(char *out, size_t capacity);
    /* The game's own saves in a session (cartridge battery, memory card, EEPROM, a disk's save files): the host's travel to every
     * seat for the match (Arthur, 17 Nov 2026). session_save writes this PC's save image into `out` and returns its size
     * (`out` NULL: only the size; 0: none; at most RRHK_SESSION_MAX_SAVE). session_save_put makes the machine play on the
     * host's bytes, in memory only (a guest never writes its own save), before the boot digest and after a restart. NULL:
     * none (each seat keeps its own, and two different saves are refused by the boot digest). */
    size_t (*session_save)(void *out, size_t capacity);
    bool (*session_save_put)(const void *in, size_t size);
    /* The host, when a match ends cleanly (it ended, or the host closed the room or quit its game; never after a desync, a
     * refused boot or a lost connection): write the machine's save as it is now in memory to this PC's own save file, the one
     * the game reads alone, atomically (a temporary file, then a rename) and keeping the previous file as a one-step backup.
     * Nobody writes a save file during a match: the kit holds every seat's side effects off from SETUP to the end (Arthur,
     * 19 Nov 2026: « Oui, réécris la carte de l'hôte à la fin »). true: written (the host is told). NULL: the machine has no
     * save to write back. */
    bool (*session_save_commit)(void);
    /* The session starts (after SETUP and its options, before the boot digest and frame 0): a machine with a real-time clock
     * sets it from `clock` (seconds since 1970, the same on every seat) instead of this PC's time, here and at every restart
     * of the session. NULL: nothing to do. */
    void (*session_begin)(uint64_t clock);
    bool session_no_restart;          /* the machine cannot restart inside a session (its restart relaunches the process): the kit
                                       * refuses Shift+F1 and the pad's Restart there with a notice, and asks nothing of the others */
    /* A computer whose keyboard the host may type on in a session (session ABI 9; Arthur, 19 Nov 2026: the host types, guests
     * stay on their pads): the keys this PC types now, packed with rrhk_keys_pack into `bits` (RRHK_SESSION_KEY_BYTES), when its
     * keyboard mode (Ctrl+Alt+K) is on; false when it is off. Called for the host's LOCAL only. Every seat, the host
     * included, then types what rrhk_session_keys gives for the frame. NULL: a machine without a keyboard. */
    bool (*session_keys)(uint8_t *bits);
    /* A handheld whose link cable plays in a session (docs/MULTIPLAYER.md, the link contract of 20 Nov 2026): the most consoles
     * it can run linked (2, or 4), 0 for none. The kit then says RRHK_CAP_LINK in HELLO; in a link session
     * (rrhk_session_link()) the adapter runs rrhk_session_ports() consoles, console i reading port i's pad, all of them in its
     * snapshots and digest in seat order, and shows and hears console rrhk_session_seat(). */
    int link_consoles;
} RrhkMachine;

/* The loop of every windowed game: returns the process exit status. */
int rrhk_main(const RrhkMachine *machine, const char *title, int scale);

/* The same loop for a machine whose guest owns it (RrhkMachine.driven): open the window, then call rrhk_frame_done at the end
 * of every guest frame (it presents the picture, paces, handles the events and the menus, and returns false when the guest must
 * stop: quit, reset), then close. A menu is a loop inside rrhk_frame_done: the guest does not run meanwhile. */
bool rrhk_open(const RrhkMachine *machine, const char *title, int scale);
bool rrhk_frame_done(void);
void rrhk_stop(void);          /* the next rrhk_frame_done returns false (a reset the guest must unwind) */
void rrhk_close(void);
/* The pad words are sampled again in the middle of a guest frame (a guest that polls its ports): the pointer too. */
void rrhk_pointer_poll(uint16_t pad1);
/* The outcome of a deferred quick-state request: 0 done, 1 nothing saved, 2 incompatible, 3 invalid, 4 input/output error. */
void rrhk_state_done(bool load, int result);

/* Services for machine adapters. */
const char *rrhk_audio_device(void);               /* the output device asked for (the name SDL lists), NULL for the system default */
bool rrhk_audio_held(void);                        /* the speed is not 100%: the machine's sound is dropped, not played */
RrhkUi *rrhk_ui(void);
void rrhk_bind(const RrhkMachine *machine);        /* default bindings; rrhk_main does it */
void rrhk_load_bindings(void);                     /* preferences, after SDL video init */
uint16_t rrhk_pad_word(int player, uint64_t frame);
/* The sticks of a player for the frame being run (RrhkMachine.analog_sticks), after the player's dead zone (0 % by default: the
 * raw values). false: no gamepad for that player, the axes are 0 (centred). Never a cost for a machine that does not call it. */
bool rrhk_pad_axes(int player, uint64_t frame, int16_t axes[RRHK_AXES]);
/* An action the machine handles itself instead of reading it in the pad word: its row in RrhkMachine.actions, as the player bound it.
 * Pressed: the players who pressed it in this event, in play (bit 0 = first player; 0 in a menu, during a capture, on a repeating key).
 * Held: on the keyboard while the window has the focus, or on that player's gamepad. */
unsigned rrhk_action_pressed(const SDL_Event *event, int action);
bool rrhk_action_held(int player, int action);
/* A vibration on a player's gamepad: low = large motor, high = small motor (0..65535), for `milliseconds`. Nothing without a
 * gamepad, without RrhkMachine.rumble, or with the Vibration row off; never fed back to the machine. */
void rrhk_rumble(int player, uint16_t low, uint16_t high, uint32_t milliseconds);
/* `--gfx <ini_key>=<index>` of the command line, before rrhk_main / rrhk_open: that value for this run (a capture), over the
 * saved one and over the default of a test run; not saved. false: no such option or value. */
bool rrhk_gfx_override(const RrhkMachine *machine, const char *assignment);
int rrhk_gfx_value(int option);                    /* the value index in force (the page's) */
/* The largest picture the renderer can show in one texture, once the window is open (SDL_RendererInfo); false before. A machine
 * with pixel_pitch offers no picture beyond it (the kit would show only the part that fits). */
bool rrhk_picture_limit(int *width, int *height);
void rrhk_autofire_reset(void);
void rrhk_notice(const char *text, Uint64 milliseconds);
const char *rrhk_tr(const char *english, const char *french);
SDL_Window *rrhk_window(void);
void rrhk_cycle_display(void);                     /* F4 */
bool rrhk_write_ready(void);                       /* before a write to the preferences: the folder exists, and the machine's former file is copied if it was the only one */
void rrhk_toggle_autofire(void);                   /* F6: flip, forget held buttons, shared notice, keep in the preferences */
void rrhk_options_observe(const SDL_Event *event); /* keys and buttons held, for the quit/restart combinations */
bool rrhk_options_host_fkey(int key, SDL_Keymod mod, bool menu);
void rrhk_menu_line(const RrhkMenuCtx *ctx, int y, const char *text);
/* Row icons (1.7.5): a 9 x 9 pictogram drawn at (x, y) in menu units, at the left of a menu row: one of retro_menu.h's
 * RR_ICON_ROW_*. A page an adapter draws itself puts one before each of its rows; RR_ICON_ROW_GENERIC is the one for a row with
 * no picture of its own. */
void rrhk_menu_icon(const RrhkMenuCtx *ctx, int x, int y, int icon);
void rrhk_help_sound_line(const RrhkMenuCtx *ctx, int y);
/* The key of the computers' keyboard row on the options page (rrhk_computer.inc): the kit gives it the keyboard icon. */
#define RRHK_ROW_KEYBOARD (SDL_NUM_SCANCODES + 1)
/* The key of the « sprite flicker reduction » row on a computer whose F5 is « fast loading » (rrhk_sprite_option.inc, the MSX family). */
#define RRHK_ROW_SPRITES (SDL_NUM_SCANCODES + 22)
void rrhk_option_row(RrhkOptionRows *rows, int key, const char *format, const char *value);
/* 1.7.5: an options row with its own icon (RR_ICON_ROW_*); rrhk_option_row lets the kit choose by the row's key (D20). */
void rrhk_option_row_icon(RrhkOptionRows *rows, int key, int icon, const char *format, const char *value);
/* The same row for an option that changes the run (keep it in line with RrhkMachine.session_option): in a multiplayer
 * session the host sets it, the row is faded and its key refused with a notice. */
void rrhk_option_row_run(RrhkOptionRows *rows, int key, int icon, const char *format, const char *value);
extern const RrhkPage rrhk_pointer_page;

/* Multiplayer: true only while the game plays in a session the converter started (hostkit_session.h); silent while a frame is
 * re-simulated (an adapter that delivers its own sound drops that frame's). */
bool rrhk_session_active(void);
bool rrhk_session_silent(void);
/* In a session: this seat is a guest (the host sets the options of the match and types on a computer, a guest does not). */
bool rrhk_session_guest(void);
/* Session ABI 9, a computer's keyboard: the host's keys of the frame being run, unpacked into `state` (SDL_NUM_SCANCODES bytes,
 * 1 for a key held); false (and `state` all zero) when the host does not type this frame. */
bool rrhk_session_keys(uint8_t *state);
/* A link session (SETUP said RRHK_SETUP_LINK, known before session_begin): one console per seat, rrhk_session_ports() of them. */
bool rrhk_session_link(void);
/* The shared controls of a session (session ABI 9), for the F2 tiles, a pad combination and the badge: the mode in force
 * (RRHK_SHARING_*, -1 outside a session or before the worker said it), the seat holding them in turns (-1: none), this
 * PC's seat, the seats and their names. rrhk_session_pass: the holder passes to the next seat (to = -1), the host gives them
 * to seat `to` (or passes too); rrhk_session_set_sharing: the host switches everyone / turns. false: not asked (a notice
 * says why); the change itself comes back from the worker at the same frame on every PC. */
int rrhk_session_sharing(void);
int rrhk_session_holder(void);
int rrhk_session_seat(void);
int rrhk_session_seats(void);
const char *rrhk_session_seat_name(int seat);
bool rrhk_session_pass(int to);
bool rrhk_session_set_sharing(int mode);
#define RRHK_SESSION_KEY_BYTES 16     /* hostkit_session.h RRHK_KEY_BYTES */
/* The typing keys of `state` (SDL_GetKeyboardState's array) as RRHK_SESSION_KEY_BYTES bits, and back. */
void rrhk_keys_pack(const uint8_t *state, uint8_t *bits);
void rrhk_keys_unpack(const uint8_t *bits, uint8_t *state);
/* The ports of the session's frames (SETUP: one per seat, or one in input sharing), 0 outside a session. A machine whose
 * extra-player adapter changes how the game reads its pads plugs it in from session_begin only when the session needs more
 * pads than the machine has without it (a SNES multitap from 3, a PC Engine one from 2), so a match plays as the game alone
 * does with that many players. */
int rrhk_session_ports(void);

/* Each adapter returns its machine; the link has exactly one. */
const RrhkMachine *rrhk_adapter(void);

#ifdef __cplusplus
}
#endif
#endif
