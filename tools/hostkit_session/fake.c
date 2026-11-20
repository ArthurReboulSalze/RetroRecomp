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
static unsigned effects_on_in_session = 0;     /* frames run with side effects on (never, in a session) */
/* SESSION_FAKE_DRIVEN=1: the fake is a driven machine (RrhkMachine.driven, as the Master System, the Game Boy and the MSX):
 * it calls rrhk_open, runs its own frame each time rrhk_frame_done returns true (run_frame only hands the words over), and
 * restarts by unwinding (rrhk_stop, then the shell closes and opens again). */
static bool driven, reopen;
/* SESSION_FAKE_STICKS=1: a machine with sticks (RrhkMachine.analog_sticks): every port's sticks fold into the state too. */
static bool sticks;
/* SESSION_FAKE_SAVE=n: a 64-byte battery whose bytes come from n (each copy its own save); it folds into the state at
* power-on, and the host's bytes replace it in a session (session ABI 8). */
static uint8_t battery[64];
static bool has_battery;
static uint16_t held1, held2;
/* SESSION_FAKE_MENU_AT=n: the player opens Help (F1) during frame n - 1 and closes it (Esc) thirty iterations later, while
 * the session may be paused and no frame runs: the menu's pause request and its end must both reach the worker. */
static unsigned menu_at, menu_countdown;
/* SESSION_FAKE_RESTART_AT=n: the player presses Shift+F1 during frame n - 1 (alone: the game restarts before frame n; in a
 * session: the host's request goes to the worker, a guest is told only the host can). */
static unsigned restart_at;
/* SESSION_FAKE_LOAD_AT=n: the player presses F9 once, during frame n - 1 (F8 is pressed during frame 9 in every run). In a
 * session the host's F8 / F9 are requests for everyone (session ABI 4); a guest is told only the host can. */
static unsigned load_at;
static bool load_pressed;
/* SESSION_FAKE_CHAT_AT=n: during frame n - 1 the player opens the chat (Y: its own text event is not typed) and types "Hello
 * there"; Enter sends it twenty iterations later, while the frames go on (the chat asks no pause). */
static unsigned chat_at, chat_countdown;
/* SESSION_FAKE_PASS_TILE=1: the pass goes through F2's tile with the keys (F2, Left, Left, Enter: a guest holder's row ends
 * with Chat, Pass, Quit), one key per iteration, instead of the call. */
static bool pass_tile;
static unsigned tile_step;
static void text(const char *t) {
    SDL_Event event; SDL_zero(event);
    event.type = SDL_TEXTINPUT;
    SDL_strlcpy(event.text.text, t, sizeof event.text.text);
    SDL_PushEvent(&event);
}
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
    if (chat_countdown && !--chat_countdown) key(SDL_SCANCODE_RETURN, SDLK_RETURN);
    if (tile_step) {
        static const SDL_Scancode steps[4] = {SDL_SCANCODE_F2, SDL_SCANCODE_LEFT, SDL_SCANCODE_LEFT, SDL_SCANCODE_RETURN};
        static const SDL_Keycode syms[4] = {SDLK_F2, SDLK_LEFT, SDLK_LEFT, SDLK_RETURN};
        key(steps[tile_step - 1], syms[tile_step - 1]);
        tile_step = tile_step < 4 ? tile_step + 1 : 0;
    }
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
static void reset(void) {
    state.acc = mix(state.acc ^ 0x5245534554ull); ++resets;
    if (driven) { reopen = true; rrhk_stop(); }      /* the guest unwinds after this frame, as Shift+F1 on a driven machine */
}
static void pause_machine(bool paused) { (void)paused; }
static size_t audio(int16_t *pcm, size_t capacity) { (void)pcm; (void)capacity; return 0; }
static uint64_t zero(void) { return 0; }
static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) { (void)ui; (void)ctx; (void)y; }   /* F1 draws it */

/* SESSION_FAKE_SLOW_MS=n: every frame (live or silent) costs n ms more, a stand-in for a heavy machine on a slow PC (the
 * rollback tier's safety floor). A sleep, never a busy loop. */
static unsigned slow_ms;
/* SESSION_FAKE_OPTION_AT=n: at frame n the fake's run-changing option changes from speed=1 to speed=2, as the host's F5 on a
 * sprite or clock option does (session ABI 9: the host's game sends RELAUNCH and runs no more frame). */
static unsigned option_at, speed = 1;
/* SESSION_FAKE_KEYS=1: a computer whose keyboard the host types on (session ABI 9): its LOCAL carries this PC's keys (the
 * letter key of frame % 26 while it types), and the keys of every RUN fold into the state. */
static bool typing_keys;
/* SESSION_FAKE_PASS_AT=n: at frame n the player passes the shared controls (rrhk_session_pass(-1): F2's tile or the pad's
 * combination; session ABI 9); the RESULT says who holds them at the end, as the worker's TURNS said. */
static unsigned pass_at;
static bool session_keys(uint8_t *bits) {
    uint8_t state_keys[SDL_NUM_SCANCODES];
    memset(state_keys, 0, sizeof state_keys);
    state_keys[SDL_SCANCODE_A + state.frames % 26] = 1;
    rrhk_keys_pack(state_keys, bits);
    return true;
}
static int last_holder = -9, last_link = -1, last_seat = -9;
static bool step(uint16_t p1, uint16_t p2) {
    last_holder = rrhk_session_holder();
    last_link = rrhk_session_link() ? rrhk_session_ports() : 0;      /* SESSION_FAKE_LINK: the consoles of a link session */
    last_seat = rrhk_session_seat();
    if (slow_ms) SDL_Delay(slow_ms);
    const uint16_t p3 = rrhk_pad_word(2, state.frames), p4 = rrhk_pad_word(3, state.frames);
    const uint64_t words = (uint64_t)p1 | (uint64_t)p2 << 16 | (uint64_t)p3 << 32 | (uint64_t)p4 << 48;
    state.acc = mix(state.acc ^ words ^ ((uint64_t)state.frames << 7));
    if (sticks) for (int p = 0; p < 4; ++p) {
        int16_t axes[RRHK_AXES];
        rrhk_pad_axes(p, state.frames, axes);
        state.acc = mix(state.acc ^ ((uint64_t)(uint16_t)axes[0] | (uint64_t)(uint16_t)axes[1] << 16 |
                                     (uint64_t)(uint16_t)axes[2] << 32 | (uint64_t)(uint16_t)axes[3] << 48));
    }
    if (typing_keys) {
        uint8_t typed[SDL_NUM_SCANCODES], bits[RRHK_SESSION_KEY_BYTES];
        const bool on = rrhk_session_keys(typed);
        rrhk_keys_pack(typed, bits);
        uint64_t low = 0, high = 0;
        for (int b = 0; b < 8; ++b) { low |= (uint64_t)bits[b] << (8 * b); high |= (uint64_t)bits[8 + b] << (8 * b); }
        state.acc = mix(state.acc ^ low ^ (on ? 1u : 0u));
        state.acc = mix(state.acc ^ high);
    }
    if (option_at && state.frames + 1 == option_at && !rrhk_session_silent()) speed = 2;
    if (pass_at && state.frames + 1 == pass_at && !rrhk_session_silent()) {
        if (pass_tile) tile_step = 1;
        else rrhk_session_pass(-1);
    }
    ++state.frames;
    if (rrhk_session_silent()) ++silent_runs; else ++live_runs;
    if (!effects_allowed) ++effects_off_runs;
    else ++effects_on_in_session;                 /* every frame of these scenarios is a session frame */
    picture[state.frames % 256] = (uint32_t)state.acc;
    /* frame 10 of the run: the player presses F8 (alone: the quick-state file; in a session: the host's request for everyone,
     * refused for a guest) */
    if (menu_at && state.frames == menu_at && !rrhk_session_silent()) { key(SDL_SCANCODE_F1, SDLK_F1); menu_countdown = 30; }
    if (restart_at && state.frames == restart_at && !rrhk_session_silent()) key_with(SDL_SCANCODE_F1, SDLK_F1, KMOD_LSHIFT);
    if (load_at && !load_pressed && state.frames == load_at && !rrhk_session_silent()) {
        load_pressed = true;
        key(SDL_SCANCODE_F9, SDLK_F9);
    }
    if (chat_at && state.frames == chat_at && !rrhk_session_silent()) {
        key(SDL_SCANCODE_Y, SDLK_y); text("y"); text("Hello there");
        chat_countdown = 20;
    }
    if (state.frames == 10 && !rrhk_session_silent()) {
        SDL_Event event; SDL_zero(event);
        event.type = SDL_KEYDOWN; event.key.keysym.scancode = SDL_SCANCODE_F8; event.key.keysym.sym = SDLK_F8;
        SDL_PushEvent(&event);
        event.type = SDL_KEYUP; SDL_PushEvent(&event);
    }
    return true;
}

static bool run_frame(uint16_t p1, uint16_t p2) {
    if (!driven) return step(p1, p2);
    held1 = p1; held2 = p2;                  /* the guest runs the frame after rrhk_frame_done returns */
    return true;
}

static bool quick_path(wchar_t *path, size_t capacity) { swprintf(path, capacity, L"session-fake.state"); return true; }
static bool quick_ready(void) { return true; }
static bool quick_file(const wchar_t *path, bool load) { (void)path; (void)load; ++quick_calls; return true; }

static void battery_fold(void) {
    for (size_t i = 0; i < sizeof battery; i += 8) {
        uint64_t word = 0;
        for (int b = 0; b < 8; ++b) word |= (uint64_t)battery[i + b] << (8 * b);
        state.acc = mix(state.acc ^ word);
    }
}
static size_t session_save(void *out, size_t capacity) {
    if (!has_battery) return 0;
    if (out && capacity >= sizeof battery) memcpy(out, battery, sizeof battery);
    return sizeof battery;
}
/* The host's save written back at a clean end of the match: the fake says it, with its battery's first word and whether a
 * frame of the match ever had its side effects on (never, in a session). */
static bool session_save_commit(void) {
    uint64_t word = 0;
    for (int b = 0; b < 8; ++b) word |= (uint64_t)battery[b] << (8 * b);
    fprintf(stderr, "[fake] commit %016llx effects-on-frames %u\n", (unsigned long long)word, effects_on_in_session);
    return true;
}
static bool session_save_put(const void *in, size_t size) {
    if (!has_battery || size != sizeof battery) return false;
    memcpy(battery, in, sizeof battery);
    state.acc = 0x9e3779b97f4a7c15ull; state.frames = 0;      /* power-on again with the host's battery */
    battery_fold();
    return true;
}

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
    if (strcmp(key, "speed") || (strcmp(value, "1") && strcmp(value, "2"))) return false;
    speed = (unsigned)(value[0] - '0');
    return true;
}

/* The fake's run-changing option, as a machine says its own in HELLO (session ABI 6). */
static size_t session_options(char *out, size_t capacity) {
    const int n = snprintf(out, capacity, "speed=%u", speed);
    return n > 0 && (size_t)n < capacity ? (size_t)n : 0;
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
    .side_effects = side_effects, .session_option = session_option, .session_options = session_options, .frame_start = frame_start};
const RrhkMachine *rrhk_adapter(void) { return &machine; }

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    SDL_SetMainReady();
    const char *menu = getenv("SESSION_FAKE_MENU_AT");
    menu_at = menu ? (unsigned)atoi(menu) : 0;
    const char *slow = getenv("SESSION_FAKE_SLOW_MS");
    slow_ms = slow ? (unsigned)atoi(slow) : 0;
    if (slow_ms > 40) slow_ms = 40;
    const char *restart = getenv("SESSION_FAKE_RESTART_AT");
    restart_at = restart ? (unsigned)atoi(restart) : 0;
    const char *load = getenv("SESSION_FAKE_LOAD_AT");
    load_at = load ? (unsigned)atoi(load) : 0;
    const char *chat = getenv("SESSION_FAKE_CHAT_AT");
    chat_at = chat ? (unsigned)atoi(chat) : 0;
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
    const char *seed = getenv("SESSION_FAKE_SAVE");
    if (seed) {
        has_battery = true;
        for (size_t i = 0; i < sizeof battery; ++i) battery[i] = (uint8_t)(atoi(seed) * 31 + i * 7);
        battery_fold();
        machine.session_save = session_save;
        machine.session_save_put = session_save_put;
        machine.session_save_commit = session_save_commit;
    }
    const char *option = getenv("SESSION_FAKE_OPTION_AT");
    option_at = option ? (unsigned)atoi(option) : 0;
    const char *linked = getenv("SESSION_FAKE_LINK");          /* a handheld whose link cable plays (two consoles) */
    if (linked && *linked == '1') machine.link_consoles = 2;
    const char *pass = getenv("SESSION_FAKE_PASS_AT");
    pass_at = pass ? (unsigned)atoi(pass) : 0;
    const char *tile = getenv("SESSION_FAKE_PASS_TILE");
    pass_tile = tile && *tile == '1';
    const char *typing = getenv("SESSION_FAKE_KEYS");
    typing_keys = typing && *typing == '1';
    if (typing_keys) machine.session_keys = session_keys;
    const char *stick = getenv("SESSION_FAKE_STICKS");
    sticks = stick && *stick == '1';
    if (sticks) machine.analog_sticks = 2;
    const char *own_loop = getenv("SESSION_FAKE_DRIVEN");
    driven = own_loop && *own_loop == '1';
    int status = 0;
    if (driven) {
        machine.driven = true;
        do {
            reopen = false;
            if (!rrhk_open(&machine, "Session fake", 1)) { status = 1; break; }
            while (rrhk_frame_done()) step(held1, held2);
            rrhk_close();
        } while (reopen);
    } else status = rrhk_main(&machine, "Session fake", 1);
    printf("RESULT frames=%u live=%u silent=%u quick=%u effects_off=%u options=%u resets=%u digest=%016llx holder=%d link=%d seat=%d\n",
           state.frames, live_runs, silent_runs, quick_calls, effects_off_runs, option_calls, resets,
           (unsigned long long)digest(), last_holder, last_link, last_seat);
    fflush(stdout);
    SDL_Quit();
    return status;
}
