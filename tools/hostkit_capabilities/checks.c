/* The host kit's 1.7.0 capabilities through its real loop, with no game (tools/hostkit_capabilities_selftest.py).
 *
 * The kit's shell is compiled as an export compiles it, around a small fake machine of this file (no adapter, no ROM): a
 * "3D" machine that declares two analog sticks, two graphics options, a picture that grows with its internal resolution,
 * rumble and three discs, then the same machine with every one of those fields left out. One virtual game controller (with a
 * rumble callback) is attached before the window opens (dummy video and audio drivers, a hidden window); keys are pushed as
 * SDL events, as a player's keys arrive. It checks that
 *   - sticks: the left stick no longer drives the directions (the d-pad still does), rrhk_pad_axes gives the raw axes at 0 %,
 *     the dead zone row of F2 (Enter, Delete) and its preference, the round dead zone and its rescaling, a player without a
 *     pad, a script's axes;
 *   - a pad of seventeen controls (a PlayStation's, eighteen rows with Change disc, past the old limit of twelve): the F2 page
 *     scrolls fifteen rows at a time, the triggers are L2 and R2 (trigger_buttons: held past the threshold, captured by F2,
 *     read back, no longer the speed controls of player 1), and without trigger_buttons they are the speed controls again;
 *   - the graphics page: F3 opens and closes it, the machine does not run meanwhile, Left/Right change and apply an option at
 *     once, the kit's Filter row, Restore defaults, the preferences ([Test3D.Video]), an out-of-range saved value, a
 *     hidden-window test run on the defaults, --gfx, the timing report;
 *   - picture size: the texture grows with the picture (1x, 2x, 4x, with and without Scale2x): the bottom-right pixels of the
 *     picture reach the window;
 *   - rumble: rrhk_rumble reaches the pad, the Vibration row of the options page turns it off (and stops it) and on, kept;
 *   - discs: the Change disc key and pad button select the next disc with a "Disc 2/3" notice, a refused change, nothing in a
 *     menu;
 *   - with the fields left out: F3 cycles the filter, the left stick is the directions, no dead zone row, no rumble, no disc.
 * No ROM, no visible window, no sound device. Original RetroRecomp code: MIT. */
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

static int failures, checks;
#define CHECK(condition) do { ++checks; if (!(condition)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

/* The fallback recording of an export is not part of the kit. */
int rr_feedback_toggle(void) { return 0; }
const char *rr_feedback_label(void) { return "F12 Record fallback hints: OFF"; }
int rr_feedback_pending(void) { return 0; }
void rr_feedback_finish(void) {}
#ifndef _WIN32
const void *rr_resource(unsigned id, size_t *size) { (void)id; *size = 0; return NULL; }
#endif

/* ---- the fake machine ---- */
/* A pad of seventeen controls (a PlayStation's: the sixteen bits of the pad word and the Analog button, a host-side action),
 * and the Change disc action: eighteen rows, more than an F2 page shows at once. */
enum { A_UP, A_DOWN, A_LEFT, A_RIGHT, A_CROSS, A_CIRCLE, A_SQUARE, A_TRIANGLE, A_L1, A_R1, A_L2, A_R2, A_L3, A_R3,
       A_START, A_SELECT, A_ANALOG, A_DISC, ACTIONS };
enum { UP_BIT = 1, DOWN_BIT = 2, LEFT_BIT = 4, RIGHT_BIT = 8, CROSS_BIT = 16, L2_BIT = 0x400, R2_BIT = 0x800 };
#define NO_PAD ((SDL_GameControllerButton)SDL_CONTROLLER_BUTTON_INVALID)
#define ROW(name, key, bit, group, k1, k2, b1) {name, key, bit, group, 0, {k1, k2}, {b1, NO_PAD}}
static const RrhkAction actions[ACTIONS] = {
    ROW("Up", L"Up", UP_BIT, RRHK_DIR, SDL_SCANCODE_UP, SDL_SCANCODE_KP_8, SDL_CONTROLLER_BUTTON_DPAD_UP),
    ROW("Down", L"Down", DOWN_BIT, RRHK_DIR, SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_2, SDL_CONTROLLER_BUTTON_DPAD_DOWN),
    ROW("Left", L"Left", LEFT_BIT, RRHK_DIR, SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_4, SDL_CONTROLLER_BUTTON_DPAD_LEFT),
    ROW("Right", L"Right", RIGHT_BIT, RRHK_DIR, SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_6, SDL_CONTROLLER_BUTTON_DPAD_RIGHT),
    ROW("Button A", L"Cross", CROSS_BIT, RRHK_FACE, SDL_SCANCODE_W, SDL_SCANCODE_KP_0, SDL_CONTROLLER_BUTTON_A),
    ROW("Button B", L"Circle", 0x20, RRHK_FACE, SDL_SCANCODE_X, SDL_SCANCODE_UNKNOWN, SDL_CONTROLLER_BUTTON_B),
    ROW("Button 3", L"Square", 0x40, RRHK_FACE, SDL_SCANCODE_A, SDL_SCANCODE_UNKNOWN, SDL_CONTROLLER_BUTTON_X),
    ROW("Button 4", L"Triangle", 0x80, RRHK_FACE, SDL_SCANCODE_S, SDL_SCANCODE_UNKNOWN, SDL_CONTROLLER_BUTTON_Y),
    ROW("L1", L"L1", 0x100, RRHK_SYSTEM, SDL_SCANCODE_Q, SDL_SCANCODE_UNKNOWN, SDL_CONTROLLER_BUTTON_LEFTSHOULDER),
    ROW("R1", L"R1", 0x200, RRHK_SYSTEM, SDL_SCANCODE_E, SDL_SCANCODE_UNKNOWN, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER),
    ROW("L2", L"L2", L2_BIT, RRHK_SYSTEM, SDL_SCANCODE_1, SDL_SCANCODE_UNKNOWN, RRHK_PAD_LEFT_TRIGGER),
    ROW("R2", L"R2", R2_BIT, RRHK_SYSTEM, SDL_SCANCODE_3, SDL_SCANCODE_UNKNOWN, RRHK_PAD_RIGHT_TRIGGER),
    ROW("L3", L"L3", 0x1000, RRHK_SYSTEM, SDL_SCANCODE_Z, SDL_SCANCODE_UNKNOWN, SDL_CONTROLLER_BUTTON_LEFTSTICK),
    ROW("R3", L"R3", 0x2000, RRHK_SYSTEM, SDL_SCANCODE_V, SDL_SCANCODE_UNKNOWN, SDL_CONTROLLER_BUTTON_RIGHTSTICK),
    ROW("Start", L"Start", 0x4000, RRHK_SYSTEM, SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_ENTER, SDL_CONTROLLER_BUTTON_START),
    ROW("Select", L"Select", 0x8000, RRHK_SYSTEM, SDL_SCANCODE_LSHIFT, SDL_SCANCODE_UNKNOWN, SDL_CONTROLLER_BUTTON_BACK),
    /* Host-side actions (bit 0), like the Pause/Menu row of the Master System. */
    ROW("Analog", L"Analog", 0, RRHK_SYSTEM, SDL_SCANCODE_F, SDL_SCANCODE_UNKNOWN, SDL_CONTROLLER_BUTTON_MISC1),
    ROW("Change disc", L"ChangeDisc", 0, RRHK_SYSTEM, SDL_SCANCODE_C, SDL_SCANCODE_UNKNOWN, SDL_CONTROLLER_BUTTON_PADDLE1)};

static const char *const resolutions[] = {"1x (native)", "2x", "4x"};
static const char *const dithering[] = {"Native", "Off"};
static const RrhkGfxOption options[] = {{"Internal resolution", L"resolution", resolutions, 3, 0},
                                        {"Dithering", L"dither", dithering, 2, 0}};

#define BASE_W 320
#define BASE_H 240
#define RED 0xff0000u
#define GREEN 0x00ff00u
static uint32_t *picture;          /* BASE x 4 at most, `scale` x BASE in use, rows `width` apart */
static int scale = 1;
static uint64_t frames;
static uint16_t last_pad[2];
static int16_t last_axes[2][RRHK_AXES];
static bool last_has[2];
static bool scripted;
static struct { int option, value; } applied[64];
static int apply_count;
static int disc, disc_calls, last_select;
static bool refuse_disc;
static bool stop;
#define EXTRA_KEY (SDL_NUM_SCANCODES + 40)     /* the machine's own option rows (option_rows_hook) */
static bool extra_rows;
static int option_rows_total, machine_key;

static void draw_picture(void) {
    const int w = BASE_W * scale, h = BASE_H * scale;
    for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x)
        picture[(size_t)y * w + x] = 0xff000000u | (x >= w - 8 && y >= h - 8 ? RED : GREEN);
}
static void gfx_apply(int option, int value) {
    if (apply_count < 64) { applied[apply_count].option = option; applied[apply_count].value = value; }
    ++apply_count;
    if (option == 0) { scale = 1 << value; draw_picture(); }
}
static int width(void) { return BASE_W * scale; }
static int height(void) { return BASE_H * scale; }
static int base_width(void) { return BASE_W; }
static int base_height(void) { return BASE_H; }
static const uint32_t *pixels(void) { return picture; }
static int players(void) { return 2; }
static void reset(void) {}
static void pause_machine(bool paused) { (void)paused; }
static size_t audio(int16_t *pcm, size_t capacity) { (void)pcm; (void)capacity; return 0; }
static uint64_t zero(void) { return 0; }
static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) { (void)ui; (void)ctx; (void)y; }
static bool script_axes(int player, uint64_t frame, int16_t axes[RRHK_AXES]) {
    (void)frame;
    if (!scripted || player) return false;
    for (int i = 0; i < RRHK_AXES; ++i) axes[i] = (int16_t)(1000 * (i + 1));
    return true;
}
static int media_count(void) { return 3; }
static int media_current(void) { return disc; }
static bool media_select(int index) {
    ++disc_calls; last_select = index;
    if (refuse_disc) return false;
    disc = index;
    return true;
}

static bool run_frame(uint16_t p1, uint16_t p2) {
    ++frames;
    last_pad[0] = p1; last_pad[1] = p2;
    for (int p = 0; p < 2; ++p) last_has[p] = rrhk_pad_axes(p, frames, last_axes[p]);
    return !stop;
}

/* The picture as it reached the window: read back before each present while a check asks for it. */
static int picture_checks, picture_scale_seen;
static bool picture_ok, want_picture;
static Uint32 read_pixel(SDL_Renderer *renderer, int x, int y) {
    Uint32 value = 0;
    SDL_Rect area = {x, y, 1, 1};
    SDL_RenderReadPixels(renderer, &area, SDL_PIXELFORMAT_ARGB8888, &value, 4);
    return value & 0xffffffu;
}
static void before_present(SDL_Renderer *renderer) {
    if (!want_picture || rrhk_ui()->menu) return;
    const SDL_Rect dst = rrhk_game_rect(renderer);
    picture_ok = dst.w > 0 && read_pixel(renderer, dst.x + dst.w - 1, dst.y + dst.h - 1) == RED &&
        read_pixel(renderer, dst.x, dst.y) == GREEN && read_pixel(renderer, dst.x + dst.w / 2, dst.y + dst.h / 2) == GREEN;
    picture_scale_seen = scale;
    ++picture_checks;
    want_picture = false;
}

/* ---- the controller: one virtual pad with a rumble callback ---- */
static SDL_Joystick *stick;
static int rumble_calls;
static Uint16 rumble_low, rumble_high;
static int SDLCALL rumble(void *userdata, Uint16 low, Uint16 high) {
    (void)userdata; ++rumble_calls; rumble_low = low; rumble_high = high;
    return 0;
}
static void axis(SDL_GameControllerAxis which, int value) { if (stick) CHECK(SDL_JoystickSetVirtualAxis(stick, which, (Sint16)value) == 0); }
static void button(SDL_GameControllerButton which, bool down) { if (stick) CHECK(SDL_JoystickSetVirtualButton(stick, which, down ? 1 : 0) == 0); }

static void key(SDL_Scancode code) {
    SDL_Event event;
    memset(&event, 0, sizeof event);
    event.type = SDL_KEYDOWN; event.key.state = SDL_PRESSED;
    event.key.keysym.scancode = code; event.key.keysym.sym = SDL_GetKeyFromScancode(code);
    SDL_PushEvent(&event);
    event.type = SDL_KEYUP; event.key.state = SDL_RELEASED;
    SDL_PushEvent(&event);
}
static int ini(const wchar_t *section, const wchar_t *name) { return rr_ini_int(section, name, -1000, rrhk_ui()->ini_file); }

/* ---- the scripts, one step per loop iteration (frame_start runs even while a menu is open) ---- */
static int step;
static uint64_t frames_mark;

static void full_script(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0:     /* the window opened: each option applied once, at its default; the renderer's limit is known */
        CHECK(apply_count == 2);
        CHECK(applied[0].option == 0 && applied[0].value == 0 && applied[1].option == 1 && applied[1].value == 0);
        { int w = -1, h = -1; CHECK(rrhk_picture_limit(&w, &h)); CHECK(w >= 0 && h >= 0); }
        CHECK(ui->pads[0] != NULL && ui->pads[1] == NULL);
        CHECK(ui->rumble == 1 && ui->deadzone[0] == 0);
        {   /* an action the machine handles itself: who pressed it, in play only; the binding is put back */
            const SDL_Scancode bound_key = ui->keys[0][A_ANALOG];
            const SDL_GameControllerButton bound_button = ui->buttons[0][A_ANALOG];
            SDL_Event e;
            ui->keys[0][A_ANALOG] = SDL_SCANCODE_F9;
            ui->buttons[0][A_ANALOG] = SDL_CONTROLLER_BUTTON_MISC1;
            memset(&e, 0, sizeof e);
            e.type = SDL_KEYDOWN; e.key.keysym.scancode = SDL_SCANCODE_F9;
            CHECK(rrhk_action_pressed(&e, A_ANALOG) == 1u);
            e.key.repeat = 1;
            CHECK(rrhk_action_pressed(&e, A_ANALOG) == 0);
            e.key.repeat = 0;
            e.key.keysym.scancode = SDL_SCANCODE_F10;
            CHECK(rrhk_action_pressed(&e, A_ANALOG) == 0);
            e.key.keysym.scancode = SDL_SCANCODE_F9;
            ui->menu = RRHK_MENU_OPTIONS;
            CHECK(rrhk_action_pressed(&e, A_ANALOG) == 0);
            ui->menu = 0;
            memset(&e, 0, sizeof e);
            e.type = SDL_CONTROLLERBUTTONDOWN; e.cbutton.button = SDL_CONTROLLER_BUTTON_MISC1;
            e.cbutton.which = SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(ui->pads[0]));
            CHECK(rrhk_action_pressed(&e, A_ANALOG) == 1u);
            e.cbutton.which = -1;      /* a gamepad no player holds */
            CHECK(rrhk_action_pressed(&e, A_ANALOG) == 0);
            ui->keys[0][A_ANALOG] = bound_key;
            ui->buttons[0][A_ANALOG] = bound_button;
        }
        CHECK(!rrhk_action_held(0, A_LEFT));
        axis(SDL_CONTROLLER_AXIS_LEFTX, 20000); axis(SDL_CONTROLLER_AXIS_LEFTY, -30000);
        axis(SDL_CONTROLLER_AXIS_RIGHTX, -12345); axis(SDL_CONTROLLER_AXIS_RIGHTY, 32767);
        break;
    case 3:     /* past D1's threshold, the left stick is no direction on a machine that reads the sticks; the raw axes at 0 % */
        CHECK((last_pad[0] & (UP_BIT | DOWN_BIT | LEFT_BIT | RIGHT_BIT)) == 0);
        CHECK(last_has[0]);
        CHECK(last_axes[0][RRHK_AXIS_LX] == 20000 && last_axes[0][RRHK_AXIS_LY] == -30000);
        CHECK(last_axes[0][RRHK_AXIS_RX] == -12345 && last_axes[0][RRHK_AXIS_RY] == 32767);
        CHECK(!last_has[1]);       /* player 2 has no pad: centred */
        for (int i = 0; i < RRHK_AXES; ++i) CHECK(last_axes[1][i] == 0);
        button(SDL_CONTROLLER_BUTTON_DPAD_LEFT, true);
        break;
    case 6:     /* the d-pad keeps the directions */
        CHECK(last_pad[0] == LEFT_BIT);
        CHECK(rrhk_action_held(0, A_LEFT));
        button(SDL_CONTROLLER_BUTTON_DPAD_LEFT, false);
        rrhk_deadzone_step(0, false); rrhk_deadzone_step(0, false);
        CHECK(ui->deadzone[0] == 10);
        CHECK(ini(L"Test3D.Gamepad.Player1", L"deadzone") == 10);
        axis(SDL_CONTROLLER_AXIS_LEFTX, 2000); axis(SDL_CONTROLLER_AXIS_LEFTY, 0);
        axis(SDL_CONTROLLER_AXIS_RIGHTX, 0); axis(SDL_CONTROLLER_AXIS_RIGHTY, 0);
        break;
    case 9:     /* inside a 10 % dead zone: centred */
        CHECK(last_axes[0][RRHK_AXIS_LX] == 0 && last_axes[0][RRHK_AXIS_LY] == 0);
        axis(SDL_CONTROLLER_AXIS_LEFTX, 32767);
        break;
    case 12:    /* the edge still gives full scale */
        CHECK(last_axes[0][RRHK_AXIS_LX] == 32767 && last_axes[0][RRHK_AXIS_LY] == 0);
        {   /* a square-range pad: its corners still reach full scale on both axes; on the circle, the values stay */
            static const int corners[][4] = {{32767, 32767, 32767, 32767}, {-32768, 32767, -32768, 32767},
                                             {-32768, -32768, -32768, -32768}, {23170, 23170, 23170, 23170}};
            for (size_t c = 0; c < sizeof corners / sizeof corners[0]; ++c) {
                int16_t a[RRHK_AXES];
                axis(SDL_CONTROLLER_AXIS_LEFTX, corners[c][0]); axis(SDL_CONTROLLER_AXIS_LEFTY, corners[c][1]);
                SDL_GameControllerUpdate();
                CHECK(rrhk_pad_axes(0, frames, a));
                CHECK(a[RRHK_AXIS_LX] >= corners[c][2] - 2 && a[RRHK_AXIS_LX] <= corners[c][2] + 2);
                CHECK(a[RRHK_AXIS_LY] >= corners[c][3] - 2 && a[RRHK_AXIS_LY] <= corners[c][3] + 2);
            }
            axis(SDL_CONTROLLER_AXIS_LEFTY, 0);
        }
        axis(SDL_CONTROLLER_AXIS_LEFTX, 18022);       /* 55 %: (55 - 10) / 90 = half the range */
        break;
    case 15:
        CHECK(last_axes[0][RRHK_AXIS_LX] >= 16380 && last_axes[0][RRHK_AXIS_LX] <= 16387);
        scripted = true;
        break;
    case 18:    /* a replay's axes, as recorded */
        CHECK(last_has[0] && last_axes[0][0] == 1000 && last_axes[0][1] == 2000 && last_axes[0][2] == 3000 && last_axes[0][3] == 4000);
        scripted = false;
        axis(SDL_CONTROLLER_AXIS_LEFTX, 0);
        /* F2, the first gamepad page, Up wraps to the last row: the Stick dead zone row; Enter steps it */
        key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_UP); key(SDL_SCANCODE_RETURN);
        break;
    case 19:
        CHECK(ui->menu == RRHK_MENU_CONTROLS && ui->gamepad_page == 1 && ui->player == 0);
        CHECK(rrhk_page_rows() == ACTIONS + RRHK_COMBO_ROWS + 2);
        CHECK(rrhk_deadzone_row() && !rrhk_device_row());
        CHECK(ui->deadzone[0] == 15);
        /* 22 rows: the page shows fifteen, scrolled to the selected last row */
        CHECK(rrhk_page_scroll() == ACTIONS + RRHK_COMBO_ROWS + 2 - 15);
        key(SDL_SCANCODE_UP);      /* the Gamepad row is just above it */
        break;
    case 20:
        CHECK(rrhk_device_row() && !rrhk_deadzone_row());
        key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DELETE);
        break;
    case 21:
        CHECK(ui->deadzone[0] == 0 && ini(L"Test3D.Gamepad.Player1", L"deadzone") == 0);
        /* the window moves only when the selected row would leave it */
        ui->row = 10; CHECK(rrhk_page_scroll() == 7);
        ui->row = 0; CHECK(rrhk_page_scroll() == 0);
        ui->row = 14; CHECK(rrhk_page_scroll() == 0);
        ui->row = 16; CHECK(rrhk_page_scroll() == 2);
        ui->row = 0; CHECK(rrhk_page_scroll() == 0);
        key(SDL_SCANCODE_ESCAPE);
        break;
    case 22:    /* the graphics page: F3 opens it; the machine waits */
        CHECK(ui->menu == 0);
        key(SDL_SCANCODE_F3);
        break;
    case 23:
        CHECK(ui->menu == RRHK_MENU_GRAPHICS && ui->gfx_row == 0);
        CHECK(rrhk_graphics_rows() == 4);
        frames_mark = frames;
        key(SDL_SCANCODE_RIGHT);
        break;
    case 24:    /* applied at once, kept */
        CHECK(apply_count == 3 && applied[2].option == 0 && applied[2].value == 1);
        CHECK(ui->gfx[0] == 1 && rrhk_gfx_value(0) == 1 && ini(L"Test3D.Video", L"resolution") == 1);
        key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_LEFT);    /* backwards wraps: Dithering 0 -> 1 */
        break;
    case 25:
        CHECK(apply_count == 4 && applied[3].option == 1 && applied[3].value == 1 && ini(L"Test3D.Video", L"dither") == 1);
        key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_RIGHT);   /* the kit's Filter row, in the order of F3: sharp -> Scale2x */
        break;
    case 26:
        CHECK(ui->filter == 2 && ini(L"Test3D.Video", L"filter") == 2);
        key(SDL_SCANCODE_LEFT);
        break;
    case 27:
        CHECK(ui->filter == 0 && ini(L"Test3D.Video", L"filter") == 0);
        key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_RETURN);   /* Scale2x, then Restore defaults */
        break;
    case 28:
        CHECK(ui->gfx[0] == 0 && ui->gfx[1] == 0 && ui->filter == 0);
        CHECK(ini(L"Test3D.Video", L"resolution") == 0 && ini(L"Test3D.Video", L"dither") == 0 && ini(L"Test3D.Video", L"filter") == 0);
        CHECK(apply_count == 6 && applied[4].option == 0 && applied[4].value == 0 && applied[5].option == 1 && applied[5].value == 0);
        CHECK(frames == frames_mark);      /* the machine did not run while the page was open */
        key(SDL_SCANCODE_UP); key(SDL_SCANCODE_UP); key(SDL_SCANCODE_UP); key(SDL_SCANCODE_RIGHT);   /* back to row 0: 2x */
        key(SDL_SCANCODE_F3);              /* F3 closes it */
        break;
    case 29:
        CHECK(ui->menu == 0 && ui->gfx[0] == 1 && scale == 2);
        want_picture = true;
        break;
    case 32:    /* the 640 x 480 picture reached the window whole: the texture grew */
        CHECK(picture_checks == 1 && picture_ok && picture_scale_seen == 2);
        CHECK(frames > frames_mark);
        key(SDL_SCANCODE_F3); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_ESCAPE);
        break;
    case 33:
        CHECK(ui->menu == 0 && ui->filter == 2);
        want_picture = true;
        break;
    case 36:    /* the same with Scale2x on the grown store */
        CHECK(picture_checks == 2 && picture_ok && picture_scale_seen == 2);
        key(SDL_SCANCODE_F3); key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_ESCAPE);    /* 4x */
        break;
    case 37:
        CHECK(ui->gfx[0] == 2 && scale == 4);
        want_picture = true;
        break;
    case 40:
        CHECK(picture_checks == 3 && picture_ok && picture_scale_seen == 4);
        key(SDL_SCANCODE_F3); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_LEFT); key(SDL_SCANCODE_ESCAPE);
        break;
    case 41:    /* 4x without Scale2x */
        CHECK(ui->filter == 0);
        want_picture = true;
        break;
    case 44:
        CHECK(picture_checks == 4 && picture_ok && picture_scale_seen == 4);
        /* rumble reaches the pad; player 2 has none */
        rrhk_rumble(0, 1000, 2000, 10000);
        CHECK(rumble_calls == 1 && rumble_low == 1000 && rumble_high == 2000);
        rrhk_rumble(1, 3000, 4000, 10000);
        CHECK(rumble_calls == 1);
        /* the Vibration row of the options page: F3, F4, F6, F7, then Vibration */
        ui->menu = RRHK_MENU_OPTIONS;
        key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_RETURN);
        break;
    case 45:    /* off: the vibration stops, none starts, kept */
        CHECK(ui->menu == RRHK_MENU_OPTIONS && ui->rumble == 0);
        CHECK(rumble_calls == 2 && rumble_low == 0 && rumble_high == 0);
        CHECK(ini(L"Manettes", L"rumble") == 0);
        rrhk_rumble(0, 5000, 6000, 10000);
        CHECK(rumble_calls == 2);
        key(SDL_SCANCODE_RETURN);
        break;
    case 46:
        CHECK(ui->rumble == 1 && ini(L"Manettes", L"rumble") == 1);
        rrhk_rumble(0, 7000, 8000, 10000);
        CHECK(rumble_calls == 3 && rumble_low == 7000 && rumble_high == 8000);
        key(SDL_SCANCODE_ESCAPE);
        break;
    case 47:    /* Change disc: the key */
        CHECK(ui->menu == 0);
        key(SDL_SCANCODE_C);
        break;
    case 48:
        CHECK(disc == 1 && disc_calls == 1 && !strcmp(ui->status, "Disc 2/3"));
        button(SDL_CONTROLLER_BUTTON_PADDLE1, true);
        break;
    case 49:    /* the pad button */
        CHECK(disc == 2 && disc_calls == 2 && !strcmp(ui->status, "Disc 3/3"));
        CHECK(last_pad[0] == 0);   /* a host action is no bit of the pad word */
        button(SDL_CONTROLLER_BUTTON_PADDLE1, false);
        refuse_disc = true;
        key(SDL_SCANCODE_C);
        break;
    case 50:    /* refused: the disc in place */
        CHECK(disc == 2 && disc_calls == 3 && last_select == 0 && !strcmp(ui->status, "Disc 3/3"));
        refuse_disc = false;
        key(SDL_SCANCODE_C);
        break;
    case 51:    /* after the last, the first; in French too */
        CHECK(disc == 0 && disc_calls == 4 && !strcmp(ui->status, "Disc 1/3"));
        rr_language_set(1); ui->language = 1;
        key(SDL_SCANCODE_C);
        break;
    case 52:
        CHECK(disc == 1 && !strcmp(ui->status, "Disque 2/3"));
        CHECK(!strcmp(rr_tr("Stick dead zone: %s"), "Zone morte du stick : %s"));
        CHECK(!strcmp(rr_tr("Retro-Recomp - Graphics"), "Retro-Recomp - Graphismes"));
        rr_language_set(0); ui->language = 0;
        key(SDL_SCANCODE_F1); key(SDL_SCANCODE_C);    /* nothing in a menu */
        break;
    case 53:
        CHECK(ui->menu == RRHK_MENU_HELP && disc == 1 && disc_calls == 5);
        key(SDL_SCANCODE_ESCAPE);
        break;
    case 54:    /* 4x stays saved; a damaged value for the next start */
        CHECK(ui->menu == 0 && ui->gfx[0] == 2 && ini(L"Test3D.Video", L"resolution") == 2);
        CHECK(rr_ini_set(L"Test3D.Video", L"dither", L"7", ui->ini_file));
        /* the triggers are L2 and R2 here: buttons of the pad, no longer the speed controls of player 1 */
        axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 32767);
        break;
    case 57:
        CHECK(last_pad[0] == R2_BIT && ui->fast_hold == 0 && ui->max_speed == 0);
        axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, -32768); axis(SDL_CONTROLLER_AXIS_TRIGGERLEFT, 32767);
        break;
    case 60:
        CHECK(last_pad[0] == L2_BIT && ui->fast_hold == 0 && ui->max_speed == 0);
        axis(SDL_CONTROLLER_AXIS_TRIGGERLEFT, -32768);
        /* F2 captures a trigger: the first gamepad page, the L1 row, Enter, then the left trigger */
        key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RIGHT);
        for (int row = 0; row < A_L1; ++row) key(SDL_SCANCODE_DOWN);
        key(SDL_SCANCODE_RETURN);
        break;
    case 61:
        CHECK(ui->menu == RRHK_MENU_CONTROLS && ui->gamepad_page == 1 && ui->row == A_L1 && ui->capturing);
        axis(SDL_CONTROLLER_AXIS_TRIGGERLEFT, 32767);
        break;
    case 62:    /* bound, swapped with L2 (which had it), kept */
        CHECK(!ui->capturing && ui->buttons[0][A_L1] == RRHK_PAD_LEFT_TRIGGER && ui->buttons[0][A_L2] == SDL_CONTROLLER_BUTTON_LEFTSHOULDER);
        CHECK(ini(L"Test3D.Gamepad.Player1", L"L1") == (int)RRHK_PAD_LEFT_TRIGGER);
        CHECK(ini(L"Test3D.Gamepad.Player1", L"L2") == (int)SDL_CONTROLLER_BUTTON_LEFTSHOULDER);
        axis(SDL_CONTROLLER_AXIS_TRIGGERLEFT, -32768);
        key(SDL_SCANCODE_ESCAPE);      /* L1 stays on the left trigger for the next start */
        break;
    case 63:    /* a trigger is refused on a host-side row (Change disc): the kit's notice, the row still waits for a button */
        CHECK(ui->menu == 0);
        key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RIGHT);
        for (int row = 0; row < A_DISC; ++row) key(SDL_SCANCODE_DOWN);
        key(SDL_SCANCODE_RETURN);
        break;
    case 64:
        CHECK(ui->menu == RRHK_MENU_CONTROLS && ui->row == A_DISC && ui->capturing);
        axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 32767);
        break;
    case 65:
        CHECK(ui->capturing && ui->buttons[0][A_DISC] == SDL_CONTROLLER_BUTTON_PADDLE1 && ui->buttons[0][A_R2] == RRHK_PAD_RIGHT_TRIGGER);
        CHECK(!strcmp(ui->status, "Reserved button or config unavailable"));
        axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, -32768);
        key(SDL_SCANCODE_ESCAPE); key(SDL_SCANCODE_ESCAPE);     /* cancel the binding, close F2 */
        break;
    case 66:    /* the options page with more rows than it shows at once: the machine adds six */
        CHECK(ui->menu == 0 && !ui->capturing);
        extra_rows = true;
        ui->menu = RRHK_MENU_OPTIONS;
        option_rows_total = 17;
        for (int k = rrhk_option_selected(); k < option_rows_total - 1; ++k) key(SDL_SCANCODE_DOWN);
        break;
    case 67:    /* the last row (` Max speed) is reached, the window scrolled; Enter runs it */
        CHECK(rrhk_option_selected() == option_rows_total - 1 && rrhk_option_scroll() == option_rows_total - 14);
        key(SDL_SCANCODE_RETURN);
        break;
    case 68:
        CHECK(ui->max_speed == 1);
        key(SDL_SCANCODE_RETURN);
        for (int k = 0; k < option_rows_total - 1; ++k) key(SDL_SCANCODE_UP);    /* back to the first row */
        break;
    case 69:
        CHECK(ui->max_speed == 0 && rrhk_option_selected() == 0 && rrhk_option_scroll() == 0);
        for (int k = 0; k < 9; ++k) key(SDL_SCANCODE_DOWN);     /* the machine's third row of slot 1 */
        key(SDL_SCANCODE_RETURN);
        break;
    case 70:
        CHECK(machine_key == EXTRA_KEY + 5 && rrhk_option_selected() == 9 && rrhk_option_scroll() == 0);
        for (int k = 0; k < 5; ++k) key(SDL_SCANCODE_DOWN);
        break;
    case 71:
        CHECK(rrhk_option_selected() == 14 && rrhk_option_scroll() == 1);
        key(SDL_SCANCODE_UP);       /* Volume: still inside the window, which does not move */
        break;
    case 72:
        CHECK(rrhk_option_selected() == 13 && rrhk_option_scroll() == 1);
        key(SDL_SCANCODE_ESCAPE);
        break;
    case 73:
        CHECK(ui->menu == 0);
        extra_rows = false;
        stop = true;
        break;
    default:
        break;
    }
}

/* The next start reads the saved values; an out-of-range one keeps the default. */
static void reload_script(void) {
    switch (step++) {
    case 0:
        CHECK(apply_count == 2 && applied[0].option == 0 && applied[0].value == 2 && applied[1].option == 1 && applied[1].value == 0);
        CHECK(scale == 4);
        /* a trigger binding is read back on a machine whose triggers are buttons */
        CHECK(rrhk_ui()->buttons[0][A_L1] == RRHK_PAD_LEFT_TRIGGER && rrhk_ui()->buttons[0][A_L2] == SDL_CONTROLLER_BUTTON_LEFTSHOULDER);
        stop = true;
        break;
    default: break;
    }
}

/* A hidden-window test run (RETRORECOMP_HOST_TEST_FRAMES): the defaults, whatever is saved, then --gfx. */
static void test_run_script(void) {
    if (step++ == 0) {
        CHECK(apply_count == 2 && applied[0].option == 0 && applied[0].value == 0 && applied[1].option == 1 && applied[1].value == 1);
        CHECK(rrhk_ui()->gfx[0] == 0 && rrhk_ui()->gfx[1] == 1);
    }
}

/* Every new field left out: the machine of every console today. */
static int plain_filter;
static void plain_script(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0:
        CHECK(apply_count == 0);
        axis(SDL_CONTROLLER_AXIS_LEFTX, 20000);
        break;
    case 3:     /* the left stick is the four directions (D1) */
        CHECK(last_pad[0] == RIGHT_BIT);
        axis(SDL_CONTROLLER_AXIS_LEFTX, 0);
        plain_filter = ui->filter;
        key(SDL_SCANCODE_F3);
        break;
    case 4:     /* F3 cycles the filters, no page */
        CHECK(ui->menu == 0 && ui->filter == rr_menu_next_filter(plain_filter));
        key(SDL_SCANCODE_C);
        rrhk_rumble(0, 9000, 9001, 10000);
        break;
    case 5:     /* no disc, no rumble */
        CHECK(disc_calls == 0 && rumble_calls == 0);
        key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RIGHT);
        break;
    case 6:     /* no Stick dead zone row */
        CHECK(ui->menu == RRHK_MENU_CONTROLS && ui->gamepad_page == 1);
        CHECK(rrhk_page_rows() == ACTIONS + RRHK_COMBO_ROWS + 1);
        key(SDL_SCANCODE_UP);
        break;
    case 7:
        CHECK(rrhk_device_row() && !rrhk_deadzone_row());
        key(SDL_SCANCODE_ESCAPE);
        /* the triggers are the speed controls: a saved trigger binding is not read, and the right trigger fast-forwards */
        CHECK(ui->buttons[0][A_L1] == SDL_CONTROLLER_BUTTON_LEFTSHOULDER);
        axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 32767);
        break;
    case 10:
        CHECK(ui->fast_hold != 0 && (last_pad[0] & R2_BIT) == 0);
        axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, -32768);
        break;
    case 13:
        CHECK(ui->fast_hold == 0);
        stop = true;
        break;
    default: break;
    }
}

/* The machine's own option rows (slots 0 and 1, three each, while extra_rows is set) and the key hook that receives them. */
static void option_rows_hook(int slot, RrhkOptionRows *rows) {
    if (!extra_rows) return;
    for (int i = 0; i < 3; ++i) rrhk_option_row(rows, EXTRA_KEY + slot * 3 + i, "Machine row: %s", slot ? "B" : "A");
}
static bool key_event(RrhkUi *ui, SDL_Scancode key, bool *running) {
    (void)ui; (void)running;
    if ((int)key < EXTRA_KEY || (int)key >= EXTRA_KEY + 6) return false;
    machine_key = (int)key;
    return true;
}

static void (*script)(void);
static void frame_start(void *window, void *renderer) { (void)window; (void)renderer; if (script) script(); }

static RrhkMachine full = {
    .ini_section = L"Test3D", .console_name = "Test 3D", .table_players = 2, .players = players,
    .actions = actions, .action_count = ACTIONS, .up = A_UP, .down = A_DOWN, .left = A_LEFT, .right = A_RIGHT, .start = A_START,
    .max_width = BASE_W, .max_height = BASE_H, .frame_seconds = 1.0 / 60.0,
    .reset = reset, .run_frame = run_frame, .pause = pause_machine, .pixels = pixels,
    .visible_width = width, .visible_height = height, .raster_height = base_height, .display_width = base_width,
    .audio = audio, .interpreted = zero, .audio_interpreted = zero, .help_controls = help_controls,
    .frame_start = frame_start, .before_present = before_present, .option_rows = option_rows_hook, .key_event = key_event,
    .analog_sticks = 2, .script_axes = script_axes, .trigger_buttons = true,
    .gfx_options = options, .gfx_option_count = 2, .gfx_apply = gfx_apply,
    .pixel_pitch = width, .rumble = true,
    .host_media = 1 + A_DISC, .media_count = media_count, .media_current = media_current, .media_select = media_select};
static const RrhkMachine *current = &full;
const RrhkMachine *rrhk_adapter(void) { return current; }

static void set_env(const char *name, const char *value) {
#ifdef _WIN32
    _putenv_s(name, value);
#else
    if (value[0]) setenv(name, value, 1); else unsetenv(name);
#endif
}

static void begin(void (*next)(void)) { script = next; step = 0; stop = false; apply_count = 0; }

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    SDL_SetMainReady();
    if (SDL_Init(SDL_INIT_GAMECONTROLLER) != 0) { fprintf(stderr, "SDL: %s\n", SDL_GetError()); return 2; }
    picture = (uint32_t *)calloc((size_t)BASE_W * 4 * BASE_H * 4, sizeof(uint32_t));
    if (!picture) return 2;
    draw_picture();
    CHECK(ACTIONS == 18 && ACTIONS <= RRHK_MAX_ACTIONS);
    CHECK((int)RRHK_PAD_LEFT_TRIGGER == 64 && (int)RRHK_PAD_RIGHT_TRIGGER == 65);   /* fixed, whatever SDL's button count */
    SDL_VirtualJoystickDesc desc;
    SDL_zero(desc);
    desc.version = SDL_VIRTUAL_JOYSTICK_DESC_VERSION;
    desc.type = SDL_JOYSTICK_TYPE_GAMECONTROLLER;
    desc.naxes = SDL_CONTROLLER_AXIS_MAX; desc.nbuttons = SDL_CONTROLLER_BUTTON_MAX;
    desc.name = "Virtual rumble pad";
    desc.Rumble = rumble;
    const int index = SDL_JoystickAttachVirtualEx(&desc);
    CHECK(index >= 0);
    stick = index >= 0 ? SDL_JoystickOpen(index) : NULL;
    CHECK(stick != NULL);
    axis(SDL_CONTROLLER_AXIS_TRIGGERLEFT, -32768); axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, -32768);

    /* 1. The 3D machine, from fresh preferences. */
    begin(full_script);
    CHECK(rrhk_main(&full, "Capabilities", 2) == 0);
    CHECK(step >= 74);
    /* 2. Its next start. */
    begin(reload_script);
    CHECK(rrhk_main(&full, "Capabilities", 2) == 0);
    CHECK(step >= 1);
    /* 3. A hidden-window test run with --gfx and a timing report. */
    CHECK(!rrhk_gfx_override(&full, "nope=1") && !rrhk_gfx_override(&full, "resolution=9") && !rrhk_gfx_override(&full, "resolution="));
    CHECK(!rrhk_gfx_override(&full, "=1") && !rrhk_gfx_override(&full, "resolution=1x") && !rrhk_gfx_override(&full, "resolutio=1"));
    CHECK(rrhk_gfx_override(&full, "dither=1"));
    char report[1024];
    snprintf(report, sizeof report, "%s", "capabilities-timing.json");
    remove(report);
    set_env("RETRORECOMP_HOST_TEST_FRAMES", "20");
    set_env("RETRORECOMP_TIMING_REPORT", report);
    begin(test_run_script);
    CHECK(rrhk_main(&full, "Capabilities", 2) == 0);
    set_env("RETRORECOMP_HOST_TEST_FRAMES", "");
    set_env("RETRORECOMP_TIMING_REPORT", "");
    CHECK(step >= 1);
    FILE *file = fopen(report, "rb");
    CHECK(file != NULL);
    if (file) {
        char text[8192]; size_t n = fread(text, 1, sizeof text - 1, file); text[n] = 0; fclose(file);
        CHECK(strstr(text, "\"gfx\":{\"resolution\":0,\"dither\":1}") != NULL);
    }
    remove(report);
    /* 4. The same machine with every new field left out. */
    RrhkMachine plain = full;
    plain.analog_sticks = 0; plain.script_axes = NULL; plain.trigger_buttons = false;
    plain.gfx_options = NULL; plain.gfx_option_count = 0; plain.gfx_apply = NULL;
    plain.pixel_pitch = NULL; plain.rumble = false;
    plain.host_media = 0; plain.media_count = NULL; plain.media_current = NULL; plain.media_select = NULL;
    current = &plain;
    scale = 1; draw_picture(); disc_calls = 0; rumble_calls = 0;
    begin(plain_script);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 14);

    if (stick) SDL_JoystickClose(stick);
    SDL_Quit();
    free(picture);
    printf("%s: %d checks, %llu frames, %d failure(s)\n", failures ? "FAIL" : "PASS", checks, (unsigned long long)frames, failures);
    return failures ? 1 : 0;
}
