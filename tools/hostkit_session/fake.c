/* A fake machine for the host kit's multiplayer session (tools/hostkit_session_selftest.py). Its whole state is a 64-bit
 * accumulator that folds every port's word of every frame (players 3 and 4 read through rrhk_pad_word, as CPS-1 and the PC
 * Engine do), so a wrong word, a frame run twice or a snapshot that does not restore changes its digest. The scripted worker
 * computes the same fold in Python. A restart folds a constant into the accumulator (the frame count goes on), so a restart
 * missing, doubled or at another frame changes the digest too. At the end it prints one line: frames, live and silent runs,
 * quick-state calls, restarts, digest.
 *
 * Original Retro-Recomp code, MIT. No ROM. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include "hostkit/hostkit.h"

/* What a game links beside the kit and this fake does not need (as tools/hostkit_capabilities/checks.c). */
int rr_feedback_toggle(void) { return 0; }
const char *rr_feedback_label(void) { return "F12 Record fallback hints: OFF"; }
int rr_feedback_pending(void) { return 0; }
void rr_feedback_finish(void) {}
const void *rr_resource(unsigned id, size_t *size) { (void)id; *size = 0; return NULL; }

enum { A, B, SELECT, START, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const RrhkAction actions[ACTIONS] = {
    {"A", L"A", 128, RRHK_FACE}, {"B", L"B", 64, RRHK_FACE}, {"Select", L"Select", 32, RRHK_SYSTEM},
    {"Start", L"Start", 16, RRHK_SYSTEM}, {"Up", L"Up", 8, RRHK_DIR}, {"Down", L"Down", 4, RRHK_DIR},
    {"Left", L"Left", 2, RRHK_DIR}, {"Right", L"Right", 1, RRHK_DIR}};

typedef struct { uint64_t acc; uint32_t frames; } State;
static State state = {0x9e3779b97f4a7c15ull, 0};
static uint32_t picture[16 * 16];
static unsigned live_runs, silent_runs, quick_calls, effects_off_runs, option_calls, resets;
static bool effects_allowed = true;
/* SESSION_FAKE_MENU_AT=n: the player opens Help (F1) during frame n - 1 and closes it (Esc) thirty iterations later, while
 * the session may be paused and no frame runs: the menu's pause request and its end must both reach the worker. */
static unsigned menu_at, menu_countdown;
/* SESSION_FAKE_RESTART_AT=n: the player presses Shift+F1 during frame n - 1 (alone: the game restarts before frame n; in a
 * session: the host's request goes to the worker, a guest is told only the host can). */
static unsigned restart_at;
static void key_with(SDL_Scancode code, SDL_Keycode sym, Uint16 mod) {
    SDL_Event event; SDL_zero(event);
    event.type = SDL_KEYDOWN; event.key.keysym.scancode = code; event.key.keysym.sym = sym; event.key.keysym.mod = mod;
    SDL_PushEvent(&event);
    event.type = SDL_KEYUP; SDL_PushEvent(&event);
}
static void key(SDL_Scancode code, SDL_Keycode sym) { key_with(code, sym, KMOD_NONE); }
static void frame_start(void *window, void *renderer) {
    (void)window; (void)renderer;
    if (menu_countdown && !--menu_countdown) key(SDL_SCANCODE_ESCAPE, SDLK_ESCAPE);
}

/* The fold the worker repeats: splitmix64 of the accumulator mixed with the four words and the frame. */
static uint64_t mix(uint64_t x) {
    x += 0x9e3779b97f4a7c15ull;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ull;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebull;
    return x ^ (x >> 31);
}

static int players(void) { return 4; }
static int size16(void) { return 16; }
static const uint32_t *pixels(void) { return picture; }
/* The fold's restart: "RESET" mixed into the accumulator, the frame count kept (tools/hostkit_session_selftest.py digest_of). */
static uint64_t mix(uint64_t x);
static void reset(void) { state.acc = mix(state.acc ^ 0x5245534554ull); ++resets; }
static void pause_machine(bool paused) { (void)paused; }
static size_t audio(int16_t *pcm, size_t capacity) { (void)pcm; (void)capacity; return 0; }
static uint64_t zero(void) { return 0; }
static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) { (void)ui; (void)ctx; (void)y; }   /* F1 draws it */

static bool run_frame(uint16_t p1, uint16_t p2) {
    const uint16_t p3 = rrhk_pad_word(2, state.frames), p4 = rrhk_pad_word(3, state.frames);
    const uint64_t words = (uint64_t)p1 | (uint64_t)p2 << 16 | (uint64_t)p3 << 32 | (uint64_t)p4 << 48;
    state.acc = mix(state.acc ^ words ^ ((uint64_t)state.frames << 7));
    ++state.frames;
    if (rrhk_session_silent()) ++silent_runs; else ++live_runs;
    if (!effects_allowed) ++effects_off_runs;
    picture[state.frames % 256] = (uint32_t)state.acc;
    /* frame 10 of the run: the player presses F8, which a session must refuse with a notice */
    if (menu_at && state.frames == menu_at && !rrhk_session_silent()) { key(SDL_SCANCODE_F1, SDLK_F1); menu_countdown = 30; }
    if (restart_at && state.frames == restart_at && !rrhk_session_silent()) key_with(SDL_SCANCODE_F1, SDLK_F1, KMOD_LSHIFT);
    if (state.frames == 10 && !rrhk_session_silent()) {
        SDL_Event event; SDL_zero(event);
        event.type = SDL_KEYDOWN; event.key.keysym.scancode = SDL_SCANCODE_F8; event.key.keysym.sym = SDLK_F8;
        SDL_PushEvent(&event);
        event.type = SDL_KEYUP; SDL_PushEvent(&event);
    }
    return true;
}

static bool quick_path(wchar_t *path, size_t capacity) { swprintf(path, capacity, L"session-fake.state"); return true; }
static bool quick_ready(void) { return true; }
static bool quick_file(const wchar_t *path, bool load) { (void)path; (void)load; ++quick_calls; return true; }

static size_t snap_bound(void) { return sizeof state; }
static size_t snap_save(void *buffer, size_t capacity) {
    if (capacity < sizeof state) return 0;
    memcpy(buffer, &state, sizeof state);
    return sizeof state;
}
static bool snap_load(const void *buffer, size_t size) {
    if (size != sizeof state) return false;
    memcpy(&state, buffer, sizeof state);
    return true;
}
static uint64_t digest(void) { return state.acc ^ state.frames; }
static void side_effects(bool allowed) { effects_allowed = allowed; }
static bool session_option(const char *key, const char *value) {
    ++option_calls;
    return !strcmp(key, "speed") && !strcmp(value, "1");
}

static RrhkMachine machine = {
    .ini_section = L"SessionFake", .console_name = "Session fake", .table_players = 4, .players = players,
    .actions = actions, .action_count = ACTIONS, .up = UP, .down = DOWN, .left = LEFT, .right = RIGHT, .start = START,
    .max_width = 16, .max_height = 16, .frame_seconds = 1.0 / 500.0,
    .reset = reset, .run_frame = run_frame, .pause = pause_machine, .pixels = pixels,
    .visible_width = size16, .visible_height = size16, .raster_height = size16, .display_width = size16,
    .audio = audio, .interpreted = zero, .audio_interpreted = zero, .help_controls = help_controls,
    .state_path = quick_path, .state_ready = quick_ready, .state_file = quick_file,
    .snap_bound = snap_bound, .snap_save = snap_save, .snap_load = snap_load, .digest = digest,
    .side_effects = side_effects, .session_option = session_option, .frame_start = frame_start};
const RrhkMachine *rrhk_adapter(void) { return &machine; }

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    SDL_SetMainReady();
    const char *menu = getenv("SESSION_FAKE_MENU_AT");
    menu_at = menu ? (unsigned)atoi(menu) : 0;
    const char *restart = getenv("SESSION_FAKE_RESTART_AT");
    restart_at = restart ? (unsigned)atoi(restart) : 0;
    /* SESSION_FAKE_BOOT_SALT=n: this copy starts from another state (a stand-in for another battery, an option the seal
     * missed, a damaged export): its digest before frame 0 differs, which the boot-digest check of the worker must refuse. */
    const char *salt = getenv("SESSION_FAKE_BOOT_SALT");
    if (salt) state.acc ^= strtoull(salt, NULL, 0);
    /* SESSION_FAKE_HZ=n: the machine's frame rate (500 by default, so the checks are short; 60 for the checks of a slow link,
     * where the input delay is counted in frames of a real machine). */
    /* SESSION_FAKE_NO_SNAPSHOT=1: a machine that keeps no snapshot (as the Mega Drive and the Master System today): its HELLO
     * reports none, and a worker asked for rollback must keep it on the delay tier. */
    const char *plain = getenv("SESSION_FAKE_NO_SNAPSHOT");
    if (plain && *plain == '1') machine.snap_bound = NULL;
    const char *hz = getenv("SESSION_FAKE_HZ");
    if (hz && atoi(hz) >= 20 && atoi(hz) <= 1000) machine.frame_seconds = 1.0 / atoi(hz);
    const int status = rrhk_main(&machine, "Session fake", 1);
    printf("RESULT frames=%u live=%u silent=%u quick=%u effects_off=%u options=%u resets=%u digest=%016llx\n",
           state.frames, live_runs, silent_runs, quick_calls, effects_off_runs, option_calls, resets,
           (unsigned long long)digest());
    fflush(stdout);
    SDL_Quit();
    return status;
}
