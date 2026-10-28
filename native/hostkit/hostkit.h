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
 * Drive, Super Nintendo, Neo Geo, CPS-1; phase 2: NES). The machine functions
 * of the 16-bit consoles are still the rr16_* link-time symbols of the 16-bit
 * contract (retro_console16.h) and those of the NES are the cyc_* functions of
 * its runner; the adapter wraps them in the table below, and nothing in the
 * kit looks at a machine macro. */
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
#define RRHK_MAX_ACTIONS 12

/* Kinds of pointing device; the numbers are those of the guns in gun16.h
 * (the adapters check it). */
enum { RRHK_POINTER_NONE, RRHK_POINTER_MENACER, RRHK_POINTER_JUSTIFIER, RRHK_POINTER_SCOPE, RRHK_POINTER_ZAPPER };

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
} RrhkAction;

/* Mouse converted to picture coordinates, for light guns and scopes. */
typedef struct {
    int x, y;
    bool fire, aux, secondary, start, turbo, pause, offscreen;
} RrhkPointer;

typedef struct RrhkUi {
    const struct RrhkMachine *machine;
    wchar_t ini_file[32768], data_dir[32768];
    wchar_t video_section[64], pointer_section[64];
    int menu, player, row, gamepad_page, capturing, filter, fullscreen, language, autofire;
    char status[80];
    Uint64 status_until;
    int pointer_shape, pointer_size, pointer_color, pointer_turbo;
    RrhkPointer mouse;
    SDL_Scancode keys[RRHK_MAX_PLAYERS][RRHK_MAX_ACTIONS];
    SDL_GameControllerButton buttons[RRHK_MAX_PLAYERS][RRHK_MAX_ACTIONS];
    SDL_GameController *pads[RRHK_MAX_PLAYERS];
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

/* An extra F2 page of the machine, after the controls (DIP switches, guns). */
typedef struct {
    const char *title;                                   /* English, translated */
    bool (*available)(void);                             /* NULL: always */
    void (*draw)(RrhkUi *ui, const RrhkMenuCtx *ctx);    /* the page body */
    void (*key)(RrhkUi *ui, SDL_Scancode key);           /* a key while the page is open */
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

    /* behaviours the kit keeps per machine until HOST_KIT.md settles them. Settled on 28 October 2026 and
     * therefore no longer settings: F2 pad capture takes the selected player's pad only (divergence 3) and F6
     * autofire shows one shared notice from the catalogue (divergence 11), both in the shell for every machine. */
    bool pointer_keeps_player2;    /* a pointer game still reads the second pad (Zapper) */
    const wchar_t *pointer_section;   /* preferences section of the pointer page, NULL: <ini_section>.Gun */
    int pointer_max;               /* largest reticle size of the page, 0: 12 */
    const char *save_failed_en, *save_failed_fr;   /* F8 failure notice, NULL: the kit's */

    /* the machine (still the rr16_* functions) */
    void (*reset)(void);
    bool (*run_frame)(uint16_t p1, uint16_t p2);
    void (*pause)(bool paused);
    const uint32_t *(*pixels)(void);
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
} RrhkMachine;

/* The loop of every windowed game: returns the process exit status. */
int rrhk_main(const RrhkMachine *machine, const char *title, int scale);

/* Services for machine adapters. */
RrhkUi *rrhk_ui(void);
void rrhk_bind(const RrhkMachine *machine);        /* default bindings; rrhk_main does it */
void rrhk_load_bindings(void);                     /* preferences, after SDL video init */
uint16_t rrhk_pad_word(int player, uint64_t frame);
void rrhk_autofire_reset(void);
void rrhk_notice(const char *text, Uint64 milliseconds);
const char *rrhk_tr(const char *english, const char *french);
void rrhk_menu_line(const RrhkMenuCtx *ctx, int y, const char *text);
void rrhk_help_sound_line(const RrhkMenuCtx *ctx, int y);
void rrhk_option_row(RrhkOptionRows *rows, int key, const char *format, const char *value);
extern const RrhkPage rrhk_pointer_page;

/* Each adapter returns its machine; the link has exactly one. */
const RrhkMachine *rrhk_adapter(void);

#ifdef __cplusplus
}
#endif
#endif
