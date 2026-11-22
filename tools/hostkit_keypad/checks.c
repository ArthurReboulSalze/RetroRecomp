/* The on-screen keypad (native/hostkit/adapters/rrhk_keypad.inc) through the host kit's real loop, with no game
 * (tools/hostkit_keypad_selftest.py).
 *
 * The kit's shell is compiled as an export compiles it, around a small fake machine of this file that includes the keypad
 * as an adapter does: a ColecoVision-like controller (a stick, two fire buttons, twelve keypad rows whose bits are the key's
 * 4-bit code in bits 6-9, the open row's flag in bit 11 on gamepad Y). Two virtual game controllers are attached before the
 * window opens (dummy video and audio drivers, a hidden window). It checks that
 *   - closed, the pad plays as usual (A is fire 1) and the word carries no flag;
 *   - Y opens player 1's keypad: the flag is in the word while it is open; the D-pad moves on the grid (wrapping), A holds the
 *     selected key's code in the word for as long as A is held, every frame (autofire on: never pulsed);
 *   - B closes it, and the flag stays until every button of that pad is released (the chat's release rule);
 *   - a menu (F2) closes it, nothing held comes back after the menu;
 *   - player 2's pad opens player 2's keypad, apart from player 1's; both drawn, numbered; a restart's close call closes both;
 *   - the grid is drawn over the picture at the right (player 1) and the left (player 2), nothing once closed (pixels read back);
 *   - the title and the hint follow the game language (five languages, in the keypad's own table).
 * Two captures are written beside the executable (keypad-one.bmp, keypad-two.bmp). No ROM, no visible window, no sound device.
 * Original Retro-Recomp code: MIT. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include "platform_io.h"
#include "retro_menu.h"
#include "hostkit/hostkit_internal.h"
#include "hostkit/adapters/rrhk_keypad.inc"

static int failures, checks;
#define CHECK(condition) do { ++checks; if (!(condition)) { fprintf(stderr, "FAIL %s:%d (step %d): %s\n", __FILE__, __LINE__, step, #condition); ++failures; } } while (0)

/* The fallback recording of an export is not part of the kit. */
int rr_feedback_toggle(void) { return 0; }
const char *rr_feedback_label(void) { return "F12 Record fallback hints: OFF"; }
int rr_feedback_pending(void) { return 0; }
void rr_feedback_finish(void) {}
#ifndef _WIN32
const void *rr_resource(unsigned id, size_t *size) { (void)id; *size = 0; return NULL; }
#endif

static int step;

/* ---- the fake machine ---- */
enum { A_UP, A_DOWN, A_LEFT, A_RIGHT, A_FIRE1, A_FIRE2, A_KEY1, A_KEY2, A_KEY3, A_KEY4, A_KEY5, A_KEY6, A_KEY7, A_KEY8, A_KEY9,
       A_STAR, A_KEY0, A_HASH, A_KEYPAD, ACTIONS };
enum { UP_BIT = 1, DOWN_BIT = 2, LEFT_BIT = 4, RIGHT_BIT = 8, FIRE1_BIT = 16, FIRE2_BIT = 32, CODE_SHIFT = 6, CODE_MASK = 0x3c0,
       FLAG_BIT = 0x800 };
#define NO_PAD ((SDL_GameControllerButton)SDL_CONTROLLER_BUTTON_INVALID)
#define NO_KEY SDL_SCANCODE_UNKNOWN
#define ROW(name, ini, bit, group, k1, b1, b2) {name, ini, bit, group, 0, {k1, NO_KEY}, {b1, b2}}
/* a keypad row: its bit is the key's code (1..12) in bits 6-9, the keyboard's digit key by position */
#define KEY(name, ini, code, k1) ROW(name, ini, (uint16_t)((code) << CODE_SHIFT), RRHK_SYSTEM, k1, NO_PAD, NO_PAD)
static const RrhkAction actions[ACTIONS] = {
    ROW("Up", L"Up", UP_BIT, RRHK_DIR, SDL_SCANCODE_UP, SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP),
    ROW("Down", L"Down", DOWN_BIT, RRHK_DIR, SDL_SCANCODE_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN),
    ROW("Left", L"Left", LEFT_BIT, RRHK_DIR, SDL_SCANCODE_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT),
    ROW("Right", L"Right", RIGHT_BIT, RRHK_DIR, SDL_SCANCODE_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT),
    ROW("Button A", L"Fire1", FIRE1_BIT, RRHK_FACE, SDL_SCANCODE_D, SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A),
    ROW("Button B", L"Fire2", FIRE2_BIT, RRHK_FACE, SDL_SCANCODE_S, SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B),
    KEY("Keypad 1", L"Key1", 1, SDL_SCANCODE_1), KEY("Keypad 2", L"Key2", 2, SDL_SCANCODE_2), KEY("Keypad 3", L"Key3", 3, SDL_SCANCODE_3),
    KEY("Keypad 4", L"Key4", 4, SDL_SCANCODE_4), KEY("Keypad 5", L"Key5", 5, SDL_SCANCODE_5), KEY("Keypad 6", L"Key6", 6, SDL_SCANCODE_6),
    KEY("Keypad 7", L"Key7", 7, SDL_SCANCODE_7), KEY("Keypad 8", L"Key8", 8, SDL_SCANCODE_8), KEY("Keypad 9", L"Key9", 9, SDL_SCANCODE_9),
    KEY("Keypad *", L"KeyStar", 10, SDL_SCANCODE_LEFTBRACKET), KEY("Keypad 0", L"Key0", 11, SDL_SCANCODE_0),
    KEY("Keypad #", L"KeyHash", 12, SDL_SCANCODE_RIGHTBRACKET),
    /* the open row: gamepad Y on both pads, no key; its bit is the flag */
    ROW("On-screen keypad", L"Keypad", FLAG_BIT, RRHK_SYSTEM, NO_KEY, SDL_CONTROLLER_BUTTON_Y, SDL_CONTROLLER_BUTTON_Y)};

static const char *const labels[12] = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"};
static const int cells[12] = {A_KEY1, A_KEY2, A_KEY3, A_KEY4, A_KEY5, A_KEY6, A_KEY7, A_KEY8, A_KEY9, A_STAR, A_KEY0, A_HASH};
static const RrhkKeypad keypad = {4, 3, labels, cells, A_KEYPAD};
static int code_of(int cell) { return actions[cells[cell]].bit >> CODE_SHIFT; }

#define PIC_W 256
#define PIC_H 192
#define GREEN 0x00ff00u
static uint32_t picture[PIC_W * PIC_H];
static uint64_t frames;
static uint16_t last_pad[2];
static bool stop;
static int resets;
/* the code of player 1's word, every frame of a window of the script (autofire on: never pulsed) */
static bool watch_code;
static int watched_frames, steady_frames, watched_code;

static int players(void) { return 2; }
static void reset(void) { ++resets; rrhk_keypad_close(); }
static void pause_machine(bool paused) { (void)paused; }
static size_t audio(int16_t *pcm, size_t capacity) { (void)pcm; (void)capacity; return 0; }
static uint64_t zero(void) { return 0; }
static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) { (void)ui; (void)ctx; (void)y; }
static int width(void) { return PIC_W; }
static int height(void) { return PIC_H; }
static const uint32_t *pixels(void) { return picture; }
static bool run_frame(uint16_t p1, uint16_t p2) {
    ++frames;
    last_pad[0] = p1; last_pad[1] = p2;
    if (watch_code) { ++watched_frames; steady_frames += ((p1 & CODE_MASK) >> CODE_SHIFT) == watched_code && (p1 & FLAG_BIT); }
    return !stop;
}
/* the machine's hooks, as an adapter calls the keypad */
static bool event_hook(const SDL_Event *event, bool *running) { (void)running; return rrhk_keypad_event(&keypad, event); }
static bool action_held(int player, int action) { return rrhk_keypad_held(&keypad, player, action); }

/* What reached the window, read back after the keypad drew (the machine's before_present). */
static const char *capture_name;
static int sample_player = -1;      /* read a point of this player's panel */
static Uint32 sampled;
static Uint32 read_pixel(SDL_Renderer *renderer, int x, int y) {
    Uint32 value = 0;
    SDL_Rect area = {x, y, 1, 1};
    SDL_RenderReadPixels(renderer, &area, SDL_PIXELFORMAT_ARGB8888, &value, 4);
    return value & 0xffffffu;
}
static void capture(SDL_Renderer *renderer, const char *name) {
    int w = 0, h = 0;
    SDL_GetRendererOutputSize(renderer, &w, &h);
    SDL_Surface *surface = SDL_CreateRGBSurfaceWithFormat(0, w, h, 32, SDL_PIXELFORMAT_ARGB8888);
    CHECK(surface != NULL);
    if (!surface) return;
    CHECK(SDL_RenderReadPixels(renderer, NULL, SDL_PIXELFORMAT_ARGB8888, surface->pixels, surface->pitch) == 0);
    CHECK(SDL_SaveBMP(surface, name) == 0);
    SDL_FreeSurface(surface);
}
static void before_present(SDL_Renderer *renderer) {
    rrhk_keypad_draw(&keypad, renderer);
    if (sample_player >= 0) {
        int ox, oy, unit;
        rr_menu_layout(renderer, &ox, &oy, &unit);
        /* inside the panel, between its title and its grid: the panel's colour only */
        const int left = sample_player == 0 ? 256 - 6 - RRHK_KEYPAD_PANEL_W : 6;
        sampled = read_pixel(renderer, ox + (left + 2) * unit + unit / 2, oy + (RRHK_KEYPAD_TOP + 14) * unit + unit / 2);
        sample_player = -1;
    }
    if (capture_name) { capture(renderer, capture_name); capture_name = NULL; }
}

/* ---- the two controllers ---- */
static SDL_Joystick *stick[2];
static void button(int pad, SDL_GameControllerButton which, bool down) {
    if (stick[pad]) CHECK(SDL_JoystickSetVirtualButton(stick[pad], which, down ? 1 : 0) == 0);
}
static void key(SDL_Scancode code) {
    SDL_Event event;
    memset(&event, 0, sizeof event);
    event.type = SDL_KEYDOWN; event.key.state = SDL_PRESSED;
    event.key.keysym.scancode = code; event.key.keysym.sym = SDL_GetKeyFromScancode(code);
    SDL_PushEvent(&event);
    event.type = SDL_KEYUP; event.key.state = SDL_RELEASED;
    SDL_PushEvent(&event);
}

/* ---- the script, one step per loop iteration (frame_start runs before the events, the pad words and the present) ---- */
static void script(void) {
    RrhkUi *ui = rrhk_ui();
    const int cell5 = 4, cell1 = 0;
    switch (step++) {
    case 0: CHECK(ui->pads[0] && ui->pads[1] && !ui->autofire); button(0, SDL_CONTROLLER_BUTTON_A, true); break;
    case 1: break;
    case 2: CHECK(last_pad[0] == FIRE1_BIT && !rrhk_keypad_state[0].open);   /* closed: A is fire 1, no flag */
            button(0, SDL_CONTROLLER_BUTTON_A, false); break;
    case 3: key(SDL_SCANCODE_F6); break;                                       /* autofire on: the keypad's key never pulses */
    case 4: CHECK(ui->autofire); sample_player = 0; break;
    case 5: CHECK(last_pad[0] == 0); CHECK(sampled == GREEN); button(0, SDL_CONTROLLER_BUTTON_Y, true); break;   /* open */
    case 6: break;
    case 7: CHECK(rrhk_keypad_state[0].open && !rrhk_keypad_state[1].open); CHECK(last_pad[0] & FLAG_BIT);
            button(0, SDL_CONTROLLER_BUTTON_Y, false); break;
    case 8: break;
    case 9: CHECK(rrhk_keypad_state[0].open && last_pad[0] == FLAG_BIT);       /* open, nothing held: the flag alone */
            button(0, SDL_CONTROLLER_BUTTON_DPAD_RIGHT, true); break;
    case 10: button(0, SDL_CONTROLLER_BUTTON_DPAD_RIGHT, false); break;
    case 11: button(0, SDL_CONTROLLER_BUTTON_DPAD_DOWN, true); break;
    case 12: button(0, SDL_CONTROLLER_BUTTON_DPAD_DOWN, false); break;
    case 13: CHECK(rrhk_keypad_state[0].row == 1 && rrhk_keypad_state[0].column == 1);   /* « 5 » */
             CHECK((last_pad[0] & FLAG_BIT) && !(last_pad[0] & CODE_MASK));
             button(0, SDL_CONTROLLER_BUTTON_A, true); break;
    case 14: break;
    case 15: CHECK(((last_pad[0] & CODE_MASK) >> CODE_SHIFT) == code_of(cell5) && (last_pad[0] & FLAG_BIT));
             watched_code = code_of(cell5); watched_frames = steady_frames = 0; watch_code = true;
             capture_name = "keypad-one.bmp"; sample_player = 0; break;
    case 16: CHECK(sampled != GREEN); break;                                   /* the panel covers the picture */
    case 17: case 18: case 19: case 20: break;
    case 21: watch_code = false; CHECK(watched_frames >= 5 && steady_frames == watched_frames);
             button(0, SDL_CONTROLLER_BUTTON_A, false); break;
    case 22: break;
    case 23: CHECK(rrhk_keypad_state[0].open && last_pad[0] == FLAG_BIT); button(0, SDL_CONTROLLER_BUTTON_B, true); break;   /* close */
    case 24: break;
    case 25: CHECK(!rrhk_keypad_state[0].open && rrhk_keypad_state[0].release);
             CHECK(last_pad[0] & FLAG_BIT);                                    /* B still held: its fire 2 is not the game's */
             button(0, SDL_CONTROLLER_BUTTON_B, false); break;
    case 26: break;
    case 27: CHECK(last_pad[0] == 0 && !rrhk_keypad_state[0].release); sample_player = 0; break;
    case 28: CHECK(sampled == GREEN); break;                                   /* nothing drawn once closed */
    /* wrapping: Up from the top row goes to the bottom one, Left from the first column to the last */
    case 29: button(0, SDL_CONTROLLER_BUTTON_Y, true); break;
    case 30: button(0, SDL_CONTROLLER_BUTTON_Y, false); rrhk_keypad_state[0].row = rrhk_keypad_state[0].column = 0; break;
    case 31: button(0, SDL_CONTROLLER_BUTTON_DPAD_UP, true); break;
    case 32: button(0, SDL_CONTROLLER_BUTTON_DPAD_UP, false); break;
    case 33: button(0, SDL_CONTROLLER_BUTTON_DPAD_LEFT, true); break;
    case 34: button(0, SDL_CONTROLLER_BUTTON_DPAD_LEFT, false); break;
    case 35: CHECK(rrhk_keypad_state[0].open && rrhk_keypad_state[0].row == 3 && rrhk_keypad_state[0].column == 2);   /* « # » */
             key(SDL_SCANCODE_F2); break;                                      /* a menu closes it */
    case 36: break;
    case 37: CHECK(ui->menu != 0 && !rrhk_keypad_state[0].open); key(SDL_SCANCODE_ESCAPE); break;
    case 38: break;
    case 39: CHECK(ui->menu == 0 && !rrhk_keypad_state[0].open && last_pad[0] == 0); break;
    /* player 2's pad: player 2's keypad, apart from player 1's */
    case 40: button(1, SDL_CONTROLLER_BUTTON_Y, true); break;
    case 41: button(1, SDL_CONTROLLER_BUTTON_Y, false); break;
    case 42: CHECK(rrhk_keypad_state[1].open && !rrhk_keypad_state[0].open);
             CHECK((last_pad[1] & FLAG_BIT) && !(last_pad[0] & FLAG_BIT));
             rrhk_keypad_state[1].row = rrhk_keypad_state[1].column = 0;
             button(1, SDL_CONTROLLER_BUTTON_A, true); button(0, SDL_CONTROLLER_BUTTON_Y, true); break;
    case 43: button(0, SDL_CONTROLLER_BUTTON_Y, false); break;
    case 44: CHECK(rrhk_keypad_state[0].open && rrhk_keypad_state[1].open);
             CHECK(((last_pad[1] & CODE_MASK) >> CODE_SHIFT) == code_of(cell1) && !(last_pad[0] & CODE_MASK));
             capture_name = "keypad-two.bmp"; sample_player = 1; break;
    case 45: CHECK(sampled != GREEN); button(1, SDL_CONTROLLER_BUTTON_A, false); break;
    case 46: rrhk_keypad_close(); break;                                       /* what the machine's reset and state load call */
    case 47: break;
    case 48: CHECK(!rrhk_keypad_state[0].open && !rrhk_keypad_state[1].open && last_pad[0] == 0 && last_pad[1] == 0); break;
    case 49: {      /* the texts follow the game language */
        const int english = rr_language_get();
        rr_language_set(rr_language_from_code("fr"));
        CHECK(!strcmp(rrhk_text(&rrhk_keypad_title), "Pave numerique"));
        CHECK(!strcmp(rrhk_text(&rrhk_keypad_hint), "A : appuyer | B : fermer"));
        rr_language_set(rr_language_from_code("de"));
        CHECK(!strcmp(rrhk_text(&rrhk_keypad_title), "Tastenfeld"));
        rr_language_set(rr_language_from_code("it"));
        CHECK(!strcmp(rrhk_text(&rrhk_keypad_title), "Tastierino"));
        rr_language_set(rr_language_from_code("es"));
        CHECK(!strcmp(rrhk_text(&rrhk_keypad_hint), "A: pulsar | B: cerrar"));
        {   /* rrhk_text.h's fallback: a missing or empty translation reads the English one, a present one its own */
            static const RrhkText partial = {"English", "Francais", NULL, "", "Deutsch"};
            CHECK(!strcmp(rrhk_text(&partial), "English"));                         /* es: empty */
            rr_language_set(rr_language_from_code("it"));
            CHECK(!strcmp(rrhk_text(&partial), "English"));                         /* it: missing */
            rr_language_set(rr_language_from_code("de"));
            CHECK(!strcmp(rrhk_text(&partial), "Deutsch"));
        }
        rr_language_set(english);
        CHECK(!strcmp(rrhk_text(&rrhk_keypad_title), "Keypad"));
        stop = true;
        break;
    }
    default: break;
    }
}
static void frame_start(void *window, void *renderer) { (void)window; (void)renderer; script(); }

static RrhkMachine machine = {
    .ini_section = L"TestKeypad", .console_name = "Test keypad", .table_players = 2, .players = players,
    .actions = actions, .action_count = ACTIONS, .up = A_UP, .down = A_DOWN, .left = A_LEFT, .right = A_RIGHT, .start = A_FIRE1,
    .max_width = PIC_W, .max_height = PIC_H, .frame_seconds = 1.0 / 60.0,
    .reset = reset, .run_frame = run_frame, .pause = pause_machine, .pixels = pixels,
    .visible_width = width, .visible_height = height, .raster_height = height, .display_width = width,
    .audio = audio, .interpreted = zero, .audio_interpreted = zero, .help_controls = help_controls,
    .frame_start = frame_start, .before_present = before_present, .event = event_hook, .action_held = action_held,
    .native_caption = RRHK_CORE_CAPTION};
const RrhkMachine *rrhk_adapter(void) { return &machine; }

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    SDL_SetMainReady();
    if (SDL_Init(SDL_INIT_GAMECONTROLLER) != 0) { fprintf(stderr, "SDL: %s\n", SDL_GetError()); return 2; }
    for (int i = 0; i < PIC_W * PIC_H; ++i) picture[i] = 0xff000000u | GREEN;
    CHECK(ACTIONS <= RRHK_MAX_ACTIONS && keypad.rows * keypad.columns <= RRHK_KEYPAD_MAX_CELLS);
    for (int p = 0; p < 2; ++p) {
        SDL_VirtualJoystickDesc desc;
        SDL_zero(desc);
        desc.version = SDL_VIRTUAL_JOYSTICK_DESC_VERSION;
        desc.type = SDL_JOYSTICK_TYPE_GAMECONTROLLER;
        desc.naxes = SDL_CONTROLLER_AXIS_MAX; desc.nbuttons = SDL_CONTROLLER_BUTTON_MAX;
        desc.name = p ? "Virtual pad 2" : "Virtual pad 1";
        const int index = SDL_JoystickAttachVirtualEx(&desc);
        CHECK(index >= 0);
        stick[p] = index >= 0 ? SDL_JoystickOpen(index) : NULL;
        CHECK(stick[p] != NULL);
        if (stick[p]) {
            SDL_JoystickSetVirtualAxis(stick[p], SDL_CONTROLLER_AXIS_TRIGGERLEFT, -32768);
            SDL_JoystickSetVirtualAxis(stick[p], SDL_CONTROLLER_AXIS_TRIGGERRIGHT, -32768);
        }
    }
    CHECK(rrhk_main(&machine, "Keypad", 2) == 0);
    CHECK(step >= 50);
    for (int p = 0; p < 2; ++p) if (stick[p]) SDL_JoystickClose(stick[p]);
    SDL_Quit();
    if (failures) { fprintf(stderr, "%d of %d checks failed\n", failures, checks); return 1; }
    printf("PASS: %d checks\n", checks);
    return 0;
}
