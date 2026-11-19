/* The host kit's 1.7.0 capabilities through its real loop, with no game (tools/hostkit_capabilities_selftest.py).
 *
 * The kit's shell is compiled as an export compiles it, around a small fake machine of this file (no adapter, no ROM): a
 * "3D" machine that declares two analog sticks, two graphics options, a picture that grows with its internal resolution,
 * rumble and three discs, then the same machine with every one of those fields left out. One virtual game controller (with a
 * rumble callback) is attached before the window opens (dummy video and audio drivers, a hidden window); keys are pushed as
 * SDL events, as a player's keys arrive. It checks that
 *   - sticks: the left stick no longer drives the directions (the d-pad still does), rrhk_pad_axes gives the raw axes at 0 % (SDL's -32768 as -32767, 1.7.6),
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
 *   - Sync to display (1.7.7): the decision for given rates, the sound's factor and its closed loop, the row, the pacing;
 *   - no picture (1.7.7): a machine whose pixels() is NULL, or 0 x 0, shows a black game area under each filter, no crash;
 *   - F4 (1.7.4): window, pixel-perfect, fit, stretched (the whole output), kept and read back, even by a machine that clamps
 *     its former value to three modes;
 *   - the F2 tiles (1.7.4): F2 opens them, Enter opens a page, Esc comes back to them and then to the game; "Quit?": Esc in play
 *     asks, the machine waits, Enter on No and Esc cancel, Yes ends the loop.
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
#ifndef _WIN32
#include <sys/stat.h>
#include <unistd.h>
#endif

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
static bool no_picture, zero_size; /* 1.7.7: the machine hands no picture (NULL) or a 0 x 0 one, as a session just reopened may */
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
static int width(void) { return zero_size ? 0 : BASE_W * scale; }
static int height(void) { return zero_size ? 0 : BASE_H * scale; }
static int base_width(void) { return BASE_W; }
static int base_height(void) { return BASE_H; }
static const uint32_t *pixels(void) { return no_picture ? NULL : picture; }
static int players(void) { return 2; }
static int resets;
static void reset(void) { ++resets; }
static void pause_machine(bool paused) { (void)paused; }
static size_t audio(int16_t *pcm, size_t capacity) { (void)pcm; (void)capacity; return 0; }
static uint64_t zero(void) { return 0; }
static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) { (void)ui; (void)ctx; (void)y; }
static bool script_axes(int player, uint64_t frame, int16_t axes[RRHK_AXES]) {
    (void)frame;
    if (!scripted || player) return false;
    for (int i = 0; i < RRHK_AXES; ++i) axes[i] = (int16_t)(1000 * (i + 1));
    axes[RRHK_AXIS_RY] = -32768;   /* 1.7.6: a recording is given as recorded, its -32768 too */
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
static int black_seen[4], black_wrong;
static void before_present(SDL_Renderer *renderer) {
    if ((no_picture || zero_size) && !rrhk_ui()->menu) {    /* 1.7.7: no picture, whatever the filter: black (the last one was green) */
        int w = 0, h = 0;
        SDL_GetRendererOutputSize(renderer, &w, &h);
        const int filter = rrhk_ui()->filter;
        if (w > 0 && read_pixel(renderer, w / 2, h / 2) == 0 && read_pixel(renderer, w / 4, h / 4) == 0 &&
            read_pixel(renderer, w * 3 / 4, h * 3 / 4) == 0 && filter >= 0 && filter < 4) ++black_seen[filter];
        else ++black_wrong;
    }
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
        CHECK(strstr(SDL_GetWindowTitle(rrhk_window()), "| " RRHK_CORE_CAPTION) != NULL);
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
        {   /* 1.7.6: SDL's -32768 (left or top edge) is given as -32767, the sticks symmetric for the cores; 32767 stays */
            int16_t a[RRHK_AXES];
            axis(SDL_CONTROLLER_AXIS_LEFTX, -32768); axis(SDL_CONTROLLER_AXIS_LEFTY, -32768);
            axis(SDL_CONTROLLER_AXIS_RIGHTX, -32768); axis(SDL_CONTROLLER_AXIS_RIGHTY, 32767);
            SDL_GameControllerUpdate();
            CHECK(SDL_GameControllerGetAxis(ui->pads[0], SDL_CONTROLLER_AXIS_LEFTX) == -32768);   /* the pad really gives it */
            CHECK(rrhk_pad_axes(0, frames, a));
            CHECK(a[RRHK_AXIS_LX] == -32767 && a[RRHK_AXIS_LY] == -32767);
            CHECK(a[RRHK_AXIS_RX] == -32767 && a[RRHK_AXIS_RY] == 32767);
            for (int i = 0; i < RRHK_AXES; ++i) axis((SDL_GameControllerAxis)(SDL_CONTROLLER_AXIS_LEFTX + i), 0);
        }
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
                CHECK(a[RRHK_AXIS_LX] >= -32767 && a[RRHK_AXIS_LY] >= -32767);   /* the dead zone keeps the sticks symmetric */
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
        CHECK(last_has[0] && last_axes[0][0] == 1000 && last_axes[0][1] == 2000 && last_axes[0][2] == 3000 && last_axes[0][3] == -32768);
        scripted = false;
        axis(SDL_CONTROLLER_AXIS_LEFTX, 0);
        /* F2 opens the tiles (1.7.4): Right is player 1's gamepad, Enter opens its page; Up wraps to the last row (1.7.6: Restore
         * defaults), Up again: the Stick dead zone row; Enter steps it */
        key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_RETURN); key(SDL_SCANCODE_UP); key(SDL_SCANCODE_UP);
        key(SDL_SCANCODE_RETURN);
        break;
    case 19:
        CHECK(ui->menu == RRHK_MENU_CONTROLS && ui->gamepad_page == 1 && ui->player == 0);
        CHECK(rrhk_page_rows() == ACTIONS + RRHK_COMBO_ROWS + 3);
        CHECK(rrhk_deadzone_row() && !rrhk_device_row() && !rrhk_restore_row());
        CHECK(ui->deadzone[0] == 15);
        /* 1.7.6: six combinations and Restore defaults: the page shows fifteen, the selected row (Up twice in one frame) the last */
        CHECK(rrhk_page_scroll() == ACTIONS + RRHK_COMBO_ROWS + 3 - 16);
        key(SDL_SCANCODE_UP);      /* the Gamepad row is just above it */
        break;
    case 20:
        CHECK(rrhk_device_row() && !rrhk_deadzone_row());
        key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DELETE);
        break;
    case 21:
        CHECK(ui->deadzone[0] == 0 && ini(L"Test3D.Gamepad.Player1", L"deadzone") == 0);
        /* the window moves only when the selected row would leave it */
        ui->row = ACTIONS + RRHK_COMBO_ROWS + 3 - 14; CHECK(rrhk_page_scroll() == ACTIONS + RRHK_COMBO_ROWS + 3 - 16);
        ui->row = 0; CHECK(rrhk_page_scroll() == 0);
        ui->row = 14; CHECK(rrhk_page_scroll() == 0);
        ui->row = 16; CHECK(rrhk_page_scroll() == 2);
        ui->row = 0; CHECK(rrhk_page_scroll() == 0);
        key(SDL_SCANCODE_F2);          /* F2 closes its page and its tiles at once */
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
        /* the Vibration row of the options page: F3, F4, Sync to display (1.7.7), F6, F7, then Vibration */
        ui->menu = RRHK_MENU_OPTIONS;
        key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DOWN);
        key(SDL_SCANCODE_RETURN);
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
        key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_RETURN);
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
        key(SDL_SCANCODE_F2);          /* F2 closes its page and its tiles at once; L1 stays on the left trigger for the next start */
        break;
    case 63:    /* a trigger is refused on a host-side row (Change disc): the kit's notice, the row still waits for a button */
        CHECK(ui->menu == 0);
        key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_RETURN);
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
        key(SDL_SCANCODE_ESCAPE); key(SDL_SCANCODE_F2);     /* cancel the binding, close F2 */
        break;
    case 66:    /* the options page with more rows than it shows at once: the machine adds six */
        CHECK(ui->menu == 0 && !ui->capturing);
        extra_rows = true;
        ui->menu = RRHK_MENU_OPTIONS;
        option_rows_total = 19;      /* 1.7.4: the Start-up reminders row, before the last one; 1.7.7: Sync to display */
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
        for (int k = 0; k < 10; ++k) key(SDL_SCANCODE_DOWN);    /* the machine's third row of slot 1 */
        key(SDL_SCANCODE_RETURN);
        break;
    case 70:
        CHECK(machine_key == EXTRA_KEY + 5 && rrhk_option_selected() == 10 && rrhk_option_scroll() == 0);
        for (int k = 0; k < 5; ++k) key(SDL_SCANCODE_DOWN);
        break;
    case 71:
        CHECK(rrhk_option_selected() == 15 && rrhk_option_scroll() == 2);
        key(SDL_SCANCODE_UP);       /* Volume: still inside the window, which does not move */
        break;
    case 72:    /* 1.7.4: the Start-up reminders row, three rows down, is kept in [Interface] start_help */
        CHECK(rrhk_option_selected() == 14 && rrhk_option_scroll() == 2);
        CHECK(ini(L"Interface", L"start_help") == -1000);
        key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_RETURN);
        break;
    case 73:
        CHECK(rrhk_option_selected() == 17 && ini(L"Interface", L"start_help") == 0);
        key(SDL_SCANCODE_RETURN);
        break;
    case 74:
        CHECK(ini(L"Interface", L"start_help") == 1);
        key(SDL_SCANCODE_ESCAPE);
        break;
    case 75:
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
        CHECK(strstr(SDL_GetWindowTitle(rrhk_window()), "| Native code") != NULL);
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
        key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_RETURN);
        break;
    case 6:     /* no Stick dead zone row */
        CHECK(ui->menu == RRHK_MENU_CONTROLS && ui->gamepad_page == 1);
        CHECK(rrhk_page_rows() == ACTIONS + RRHK_COMBO_ROWS + 2);
        key(SDL_SCANCODE_UP); key(SDL_SCANCODE_UP);     /* 1.7.6: Restore defaults, then the Gamepad row */
        break;
    case 7:
        CHECK(rrhk_device_row() && !rrhk_deadzone_row());
        key(SDL_SCANCODE_F2);
        /* 1.7.5: a saved trigger binding is read on every machine (L1 on the left trigger, from the first run); a trigger no
         * control has is still a speed control: the right one fast-forwards (this machine's R2 row has no trigger) */
        CHECK(ui->buttons[0][A_L1] == RRHK_PAD_LEFT_TRIGGER && ui->buttons[0][A_R2] != RRHK_PAD_RIGHT_TRIGGER);
        axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 32767);
        break;
    case 10:
        CHECK(ui->fast_hold != 0 && (last_pad[0] & R2_BIT) == 0);
        axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, -32768);
        break;
    case 13:
        CHECK(ui->fast_hold == 0);
        key(SDL_SCANCODE_F2);
        break;
    case 14:    /* 1.7.4: F2 opens the tiles; Right then Enter open player 1's gamepad page */
        CHECK(ui->menu == RRHK_MENU_HUB);
        key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_RETURN);
        break;
    case 15:    /* Esc comes back to the tiles, Esc again to the game */
        CHECK(ui->menu == RRHK_MENU_CONTROLS && ui->gamepad_page == 1 && ui->player == 0);
        key(SDL_SCANCODE_ESCAPE);
        break;
    case 16:
        CHECK(ui->menu == RRHK_MENU_HUB);
        key(SDL_SCANCODE_ESCAPE);
        break;
    case 17:    /* Esc in play asks "Quit?": the machine waits, No is selected */
        CHECK(ui->menu == 0);
        CHECK(ui->fullscreen == 0);
        key(SDL_SCANCODE_ESCAPE);
        break;
    case 18:
        CHECK(ui->menu == RRHK_MENU_QUIT);
        frames_mark = frames;
        key(SDL_SCANCODE_RETURN);
        break;
    case 19:    /* Enter on No: back to the game, which did not run meanwhile */
        CHECK(ui->menu == 0 && frames <= frames_mark + 1);
        key(SDL_SCANCODE_ESCAPE); key(SDL_SCANCODE_ESCAPE);
        break;
    case 20:    /* Esc on the question cancels it; F4: pixel-perfect */
        CHECK(ui->menu == 0);
        key(SDL_SCANCODE_F4);
        break;
    case 21:
        CHECK(ui->fullscreen == 1 && ini(L"Test3D.Video", L"display_mode") == 1);
        key(SDL_SCANCODE_F4);
        break;
    case 22:    /* fit */
        CHECK(ui->fullscreen == 2 && ini(L"Test3D.Video", L"display_mode") == 2);
        key(SDL_SCANCODE_F4);
        break;
    case 23: {  /* 1.7.4: stretched, named by the notice, the picture over the whole output, kept */
        CHECK(ui->fullscreen == 3 && ini(L"Test3D.Video", L"display_mode") == 3);
        CHECK(!strcmp(ui->status, "Stretched"));
        int w = 0, h = 0;
        SDL_GetRendererOutputSize(SDL_GetRenderer(rrhk_window()), &w, &h);
        const SDL_Rect dst = rrhk_game_rect(SDL_GetRenderer(rrhk_window()));
        CHECK(dst.x == 0 && dst.y == 0 && dst.w == w && dst.h == h && w > 0);
        key(SDL_SCANCODE_ESCAPE); key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_RETURN);     /* Yes: the loop ends */
        break;
    }
    default: break;
    }
}

/* A machine that reads its former display mode in settings_loaded and knows three of them. */
static void three_modes(RrhkUi *ui) { if (ui->fullscreen < 0 || ui->fullscreen > 2) ui->fullscreen = 0; }
static void stretched_script(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0:
        CHECK(ui->fullscreen == 3);
        key(SDL_SCANCODE_F4);
        break;
    case 1:
        CHECK(ui->fullscreen == 0 && ini(L"Test3D.Video", L"display_mode") == 0 && !strcmp(ui->status, "Windowed"));
        break;
    case 2:
        stop = true;
        break;
    default: break;
    }
}

/* 1.7.5: Quick save and Quick load on player 1's pad. The machine counts the requests it receives (F8 and F9's own). */
static int quick_saves, quick_loads;
static Uint64 quick_t0;
static bool quick_path(wchar_t *path, size_t capacity) { swprintf(path, capacity, L"capabilities.state"); return true; }
static bool quick_ready(void) { return true; }
static bool quick_file(const wchar_t *path, bool load) { (void)path; if (load) ++quick_loads; else ++quick_saves; return true; }
#define QUICK_ROW (ACTIONS + 2)      /* player 1's rows: the controls, Quit, Restart, Quick save, Quick load, Gamepad */
static void pad_hold(SDL_GameControllerButton a, SDL_GameControllerButton b, bool down) { button(a, down); button(b, down); }
static void quick_script(void) {
    RrhkUi *ui = rrhk_ui();
    const Uint64 now = SDL_GetTicks64();
    switch (step++) {
    case 0:     /* player 1's gamepad page: the four combinations, the quick ones unassigned */
        key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_RETURN);
        break;
    case 1:
        CHECK(ui->menu == RRHK_MENU_CONTROLS && ui->gamepad_page == 1 && ui->player == 0);
        CHECK(rrhk_page_rows() == ACTIONS + RRHK_COMBO_ROWS + 2);
        CHECK(!rrhk_combo_set(2, true) && !rrhk_combo_set(3, true) && rrhk_combo_set(2, false) && rrhk_combo_set(3, false));
        ui->row = QUICK_ROW; key(SDL_SCANCODE_RETURN);
        break;
    case 2:
        CHECK(rrhk_combo_capturing(2, true) && rrhk_combo_capturing_pad());
        pad_hold(SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_LEFTSHOULDER, true);
        break;
    case 3: pad_hold(SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_LEFTSHOULDER, false); break;
    case 4:
        CHECK(!rrhk_combo_capturing_pad() && rrhk_combo_set(2, true));
        CHECK(ini(L"Test3D.Options", L"quick_save_pad") ==
              ((1 << SDL_CONTROLLER_BUTTON_BACK) | (1 << SDL_CONTROLLER_BUTTON_LEFTSHOULDER)));
        ui->row = QUICK_ROW + 1; key(SDL_SCANCODE_RETURN);
        break;
    case 5: pad_hold(SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_LEFTSHOULDER, true); break;   /* Quick save's: refused */
    case 6: pad_hold(SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_LEFTSHOULDER, false); break;
    case 7:
        CHECK(!rrhk_combo_set(3, true) && !strcmp(ui->status, "Already used by Quick save"));
        /* 1.7.6: L2 is Max speed's by default: L2 alone for Quick load is refused until Max speed is cleared */
        CHECK(rrhk_combo_set(RRHK_COMBO_MAX, true) && rrhk_combo_triggers(RRHK_COMBO_MAX) == 2u);
        rrhk_combo_clear(RRHK_COMBO_MAX, true);
        CHECK(!rrhk_combo_set(RRHK_COMBO_MAX, true) && ini(L"Test3D.Options", L"max_speed_pad") == 0);
        key(SDL_SCANCODE_RETURN);
        break;
    case 8: axis(SDL_CONTROLLER_AXIS_TRIGGERLEFT, 32767); break;      /* L2 alone (an axis in SDL) */
    case 9: axis(SDL_CONTROLLER_AXIS_TRIGGERLEFT, -32768); break;
    case 10: {
        char value[80];
        rrhk_combo_value(value, sizeof value, 3, true);
        CHECK(rrhk_combo_set(3, true) && ini(L"Test3D.Options", L"quick_load_pad") == (1 << 24) && !strcmp(value, "L2"));
        key(SDL_SCANCODE_F2);       /* back to the game */
        break;
    }
    case 11:    /* in play: Back+LB held half a second saves, once */
        CHECK(ui->menu == 0 && !quick_saves && !quick_loads);
        pad_hold(SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_LEFTSHOULDER, true);
        quick_t0 = now;
        break;
    case 12:
        if (!quick_saves && now - quick_t0 < 3000) { --step; break; }
        CHECK(quick_saves == 1 && !quick_loads && now - quick_t0 >= 450);
        CHECK(!strcmp(ui->status, "Quick state saved"));
        quick_t0 = now;
        break;
    case 13:    /* still held: no second save */
        if (now - quick_t0 < 700) { --step; break; }
        CHECK(quick_saves == 1);
        pad_hold(SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_LEFTSHOULDER, false);
        break;
    case 14:    /* L2 held one second loads; bound to a combination, it no longer toggles the maximum speed */
        axis(SDL_CONTROLLER_AXIS_TRIGGERLEFT, 32767);
        quick_t0 = now;
        break;
    case 15:
        if (!quick_loads && now - quick_t0 < 3000) { --step; break; }
        CHECK(quick_loads == 1 && quick_saves == 1 && now - quick_t0 >= 950);
        CHECK(!strcmp(ui->status, "Quick state loaded") && !ui->max_speed);
        axis(SDL_CONTROLLER_AXIS_TRIGGERLEFT, -32768);
        break;
    case 16:    /* in a menu the combination does nothing */
        key(SDL_SCANCODE_F1);
        break;
    case 17:
        CHECK(ui->menu == RRHK_MENU_HELP);
        pad_hold(SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_LEFTSHOULDER, true);
        quick_t0 = now;
        break;
    case 18:
        if (now - quick_t0 < 800) { --step; break; }
        CHECK(quick_saves == 1 && ui->menu == RRHK_MENU_HELP);
        pad_hold(SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_LEFTSHOULDER, false);
        key(SDL_SCANCODE_ESCAPE);
        break;
    case 19:
        stop = true;
        break;
    default: break;
    }
}

/* 1.7.5: on a console profile (no trigger_buttons), a game row bound to R2 by F2, then held in play: the row's bit, no speed. */
static void r2_script(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0: key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_RETURN); break;
    case 1:
        CHECK(ui->menu == RRHK_MENU_CONTROLS && ui->gamepad_page == 1 && ui->player == 0);
        ui->row = A_CROSS; key(SDL_SCANCODE_RETURN);
        break;
    case 2: CHECK(ui->capturing); axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, -10000); break;   /* about 11400 for SDL: under the threshold */
    case 3: CHECK(ui->capturing); axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 32767); break;
    case 4:
        CHECK(!ui->capturing && ui->buttons[0][A_CROSS] == RRHK_PAD_RIGHT_TRIGGER);
        CHECK(ini(L"Test3D.Gamepad.Player1", L"Cross") == (int)RRHK_PAD_RIGHT_TRIGGER);
        axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, -32768);
        key(SDL_SCANCODE_F2);
        break;
    case 5: CHECK(ui->menu == 0); axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 32767); break;
    case 8: CHECK((last_pad[0] & CROSS_BIT) && !ui->fast_hold); axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, -32768); break;
    case 11: CHECK(!(last_pad[0] & CROSS_BIT)); break;
    case 12: stop = true; break;
    default: break;
    }
}

/* 1.7.5: a machine's own row on player 2's gamepad page (RrhkMachine.pad_rows, the Amiga's mouse port). */
static int port_mode, port_sets;
static int port_get(void) { return port_mode; }
static void port_set(int value) { port_mode = value; ++port_sets; }
static int port_icon(void) { return port_mode == 2 ? RR_ICON_ROW_PORT_JOYSTICK : RR_ICON_ROW_PORT_MOUSE; }
static const char *const port_values[] = {"Auto (last used)", "Mouse", "Pad 2"};
static const RrhkPadRow port_row = {2, "Mouse port", 3, port_values, port_get, port_set, port_icon};
static void pad_row_script(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0:     /* the tiles: player 1 keyboard, gamepad, player 2 keyboard, gamepad */
        key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_RETURN);
        break;
    case 1:     /* player 1's gamepad page has no machine row */
        CHECK(ui->menu == RRHK_MENU_CONTROLS && ui->gamepad_page == 1 && ui->player == 0);
        CHECK(rrhk_pad_rows_here() == 0 && rrhk_page_rows() == ACTIONS + RRHK_COMBO_ROWS + 2 && rrhk_action_row() == ui->row);
        key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_RIGHT);      /* player 2's keyboard page, then its gamepad page */
        break;
    case 2:
        CHECK(ui->menu == RRHK_MENU_CONTROLS && ui->gamepad_page == 1 && ui->player == 1);
        CHECK(rrhk_pad_rows_here() == 1 && rrhk_page_rows() == 1 + ACTIONS + 2 && ui->row == 0);
        CHECK(rrhk_pad_row_at(0) == &port_row && !rrhk_pad_row_at(1) && rrhk_action_row() == -1);
        key(SDL_SCANCODE_RETURN);                              /* Enter: the next value */
        break;
    case 3:
        CHECK(port_mode == 1 && port_sets == 1 && !ui->capturing);
        key(SDL_SCANCODE_RETURN); key(SDL_SCANCODE_RETURN);    /* 2, then back to 0 */
        break;
    case 4:
        CHECK(port_mode == 0 && port_sets == 3);
        key(SDL_SCANCODE_MINUS);                               /* -: the previous value, wrapping */
        break;
    case 5:
        CHECK(port_mode == 2 && port_icon() == RR_ICON_ROW_PORT_JOYSTICK);
        key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_RETURN);      /* the next row is player 2's first control */
        break;
    case 6:
        CHECK(ui->row == 1 && rrhk_action_row() == 0 && ui->capturing);
        key(SDL_SCANCODE_ESCAPE);
        break;
    case 7:
        CHECK(!ui->capturing);
        key(SDL_SCANCODE_LEFT);                                /* player 2's keyboard page: no machine row */
        break;
    case 8:
        CHECK(ui->gamepad_page == 0 && ui->player == 1 && rrhk_pad_rows_here() == 0);
        key(SDL_SCANCODE_F2);
        break;
    case 9: stop = true; break;
    default: break;
    }
}

/* 1.8.1: the F2 menu's last tile, Quit: the same "Quit? No / Yes" as Esc (No selected); No and Esc come back to the tiles, a
 * second Esc to the game. (1.7.6 to 1.8.0 had it as the options page's last row.) */
static void quit_row_script(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0: key(SDL_SCANCODE_F2); key(SDL_SCANCODE_LEFT); break;      /* from the first tile, Left: the last one, Quit */
    case 1: CHECK(ui->menu == RRHK_MENU_HUB); key(SDL_SCANCODE_RETURN); break;
    case 2:
        CHECK(ui->menu == RRHK_MENU_QUIT && ui->parent_menu == RRHK_MENU_HUB);
        frames_mark = frames;
        key(SDL_SCANCODE_RETURN);                       /* No is selected */
        break;
    case 3:
        CHECK(ui->menu == RRHK_MENU_HUB && frames == frames_mark);   /* back on the tiles; the game did not run */
        key(SDL_SCANCODE_RETURN);                       /* the Quit tile is still selected */
        break;
    case 4: CHECK(ui->menu == RRHK_MENU_QUIT); key(SDL_SCANCODE_ESCAPE); break;
    case 5: CHECK(ui->menu == RRHK_MENU_HUB); key(SDL_SCANCODE_ESCAPE); break;
    case 6: CHECK(ui->menu == 0); key(SDL_SCANCODE_F2); key(SDL_SCANCODE_LEFT); key(SDL_SCANCODE_RETURN); break;
    case 7:     /* Quit, Yes: the loop ends */
        CHECK(ui->menu == RRHK_MENU_QUIT);
        key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_RETURN);
        break;
    case 8: break;
    default: break;
    }
}

/* 1.8.1: the F2 tile before Quit restarts the game (Arthur, 19 Nov 2026): back to the game, and the machine's reset runs once, through
 * the loop's restart path (the one of the pad's Restart combination; in a session, the host's restart for every seat). */
static int resets_mark;
static void restart_tile_script(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0: resets_mark = resets; key(SDL_SCANCODE_F2); key(SDL_SCANCODE_LEFT); key(SDL_SCANCODE_LEFT); break;
    case 1: CHECK(ui->menu == RRHK_MENU_HUB && resets == resets_mark); key(SDL_SCANCODE_RETURN); break;
    case 2: break;
    case 3: CHECK(ui->menu == 0 && resets == resets_mark + 1); break;
    case 4: CHECK(resets == resets_mark + 1); stop = true; break;      /* once, not at every frame */
    default: break;
    }
}

/* 1.8.1 (session ABI 9): the host's « Change this option? » before a key that relaunches the match. Asked here directly (the
 * loop asks it in a session only): Esc and No drop the key, Yes gives it back once to the machine; the question sits where the
 * kit's « Quit? » does and leaves the menu it was asked from as it was. */
static void relaunch_confirm_script(void) {
    RrhkUi *ui = rrhk_ui();
    const SDL_Scancode row = (SDL_Scancode)EXTRA_KEY;
    switch (step++) {
    case 0:
        machine_key = 0;
        CHECK(rrhk_relaunch_ask(row) && ui->menu == RRHK_MENU_QUIT && rrhk_relaunch_asking());
        key(SDL_SCANCODE_ESCAPE);
        break;
    case 1:
        CHECK(ui->menu == 0 && !rrhk_relaunch_asking() && machine_key == 0);       /* Esc: dropped */
        CHECK(rrhk_relaunch_ask(row));
        key(SDL_SCANCODE_RETURN);                                                   /* No is selected */
        break;
    case 2:
        CHECK(ui->menu == 0 && !rrhk_relaunch_asking() && machine_key == 0);       /* No: dropped */
        CHECK(rrhk_relaunch_ask(row));
        key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_RETURN);                          /* Yes */
        break;
    case 3: break;
    case 4:
        CHECK(ui->menu == 0 && !rrhk_relaunch_asking() && machine_key == (int)row);  /* Yes: the key went on, once */
        machine_key = 0;
        stop = true;
        break;
    default: break;
    }
}

/* 1.7.6: on a machine with a graphics page, the F2 tile before Restart and Quit (1.8.1) opens it (and comes back to the tiles), and the options page's
 * F3 row, "F3 Graphics", opens it too (and comes back to the options). */
static void graphics_entry_script(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0: key(SDL_SCANCODE_F2); key(SDL_SCANCODE_LEFT); key(SDL_SCANCODE_LEFT); key(SDL_SCANCODE_LEFT); key(SDL_SCANCODE_RETURN); break;   /* Quit is last, Restart before it (1.8.1) */
    case 1: CHECK(ui->menu == RRHK_MENU_GRAPHICS); key(SDL_SCANCODE_ESCAPE); break;
    case 2: CHECK(ui->menu == RRHK_MENU_HUB); key(SDL_SCANCODE_LEFT); key(SDL_SCANCODE_RETURN); break;   /* Options: before it */
    case 3: CHECK(ui->menu == RRHK_MENU_OPTIONS && rrhk_option_selected() == 0); key(SDL_SCANCODE_RETURN); break;
    case 4: CHECK(ui->menu == RRHK_MENU_GRAPHICS); key(SDL_SCANCODE_ESCAPE); break;
    case 5: CHECK(ui->menu == RRHK_MENU_OPTIONS); key(SDL_SCANCODE_ESCAPE); key(SDL_SCANCODE_ESCAPE); break;
    case 6: CHECK(ui->menu == 0); stop = true; break;
    default: break;
    }
}

/* 1.7.6: a stick direction bound to a game row on a console profile: captured by F2 (a host-side row refuses it), kept, held in
 * play with the hysteresis of the triggers; the machine's own reading of the sticks is untouched. */
static void stick_script(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0: key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_RETURN); break;
    case 1: ui->row = A_ANALOG; key(SDL_SCANCODE_RETURN); break;              /* a host-side row */
    case 2: CHECK(ui->capturing); axis(SDL_CONTROLLER_AXIS_RIGHTX, 30000); break;
    case 3:
        CHECK(ui->capturing && !strcmp(ui->status, "Reserved button or config unavailable"));
        axis(SDL_CONTROLLER_AXIS_RIGHTX, 0); key(SDL_SCANCODE_ESCAPE);
        break;
    case 4: ui->row = A_CROSS; key(SDL_SCANCODE_RETURN); break;
    case 5: CHECK(ui->capturing); axis(SDL_CONTROLLER_AXIS_RIGHTX, 12000); break;    /* under the threshold: still waiting */
    case 6: CHECK(ui->capturing); axis(SDL_CONTROLLER_AXIS_RIGHTX, 30000); break;
    case 7:
        CHECK(!ui->capturing && ui->buttons[0][A_CROSS] == RRHK_PAD_RSTICK_RIGHT);
        CHECK(ini(L"Test3D.Gamepad.Player1", L"Cross") == (int)RRHK_PAD_RSTICK_RIGHT);
        CHECK(!strcmp(rrhk_pad_binding_name(RRHK_PAD_RSTICK_RIGHT), "R stick right"));
        axis(SDL_CONTROLLER_AXIS_RIGHTX, 0);
        key(SDL_SCANCODE_F2);
        break;
    case 8: CHECK(ui->menu == 0); axis(SDL_CONTROLLER_AXIS_RIGHTX, 20000); break;
    case 11: CHECK(last_pad[0] & CROSS_BIT); axis(SDL_CONTROLLER_AXIS_RIGHTX, 10000); break;   /* under the threshold, above half */
    case 14: CHECK(last_pad[0] & CROSS_BIT); axis(SDL_CONTROLLER_AXIS_RIGHTX, 5000); break;     /* under half: released */
    case 17: CHECK(!(last_pad[0] & CROSS_BIT)); axis(SDL_CONTROLLER_AXIS_RIGHTX, -30000); break; /* the other way: nothing */
    case 20: CHECK(!(last_pad[0] & CROSS_BIT)); axis(SDL_CONTROLLER_AXIS_RIGHTX, 0); break;
    case 21: stop = true; break;
    default: break;
    }
}

/* 1.7.6: any binding row of any machine (this one sets no bindings_clearable) is cleared without a capture: Delete and Backspace on
 * a keyboard page, the pad's X on a gamepad page, a combination too; each is written as cleared and the next start keeps it so
 * (clear_again). There, Restore defaults (the last row) gives the page's defaults back, swapping a default another action holds;
 * the other player's keys are untouched. */
static SDL_Scancode player2_key;
static void clear_script(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0: key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RETURN); break;                /* player 1's keyboard page */
    case 1:
        CHECK(ui->menu == RRHK_MENU_CONTROLS && ui->gamepad_page == 0 && ui->player == 0);
        ui->row = A_CROSS; key(SDL_SCANCODE_DELETE);
        break;
    case 2:
        CHECK(!ui->capturing && ui->keys[0][A_CROSS] == SDL_SCANCODE_UNKNOWN);
        CHECK(ini(L"Test3D.Keyboard.Player1", L"Cross") == 0);
        ui->row = A_CIRCLE; key(SDL_SCANCODE_BACKSPACE);
        break;
    case 3:
        CHECK(!ui->capturing && ui->keys[0][A_CIRCLE] == SDL_SCANCODE_UNKNOWN && ini(L"Test3D.Keyboard.Player1", L"Circle") == 0);
        rrhk_assign(0, A_CIRCLE, false, SDL_SCANCODE_W);       /* as F2 would: Circle on Cross's default key */
        CHECK(ui->keys[0][A_CROSS] == SDL_SCANCODE_UNKNOWN);   /* assigning takes nothing from a row without a key */
        key(SDL_SCANCODE_RIGHT);                               /* player 1's gamepad page */
        break;
    case 4:
        CHECK(ui->gamepad_page == 1 && ui->player == 0);
        ui->row = A_SQUARE; button(SDL_CONTROLLER_BUTTON_X, true);
        break;
    case 5:
        button(SDL_CONTROLLER_BUTTON_X, false);
        CHECK(!ui->capturing && (int)ui->buttons[0][A_SQUARE] == -1 && ini(L"Test3D.Gamepad.Player1", L"Square") == -1);
        ui->row = ACTIONS + RRHK_COMBO_FAST; key(SDL_SCANCODE_DELETE);     /* Fast forward, R2 by default */
        break;
    case 6:
        CHECK(!rrhk_combo_set(RRHK_COMBO_FAST, true));
        player2_key = ui->keys[1][A_CROSS];
        key(SDL_SCANCODE_ESCAPE); key(SDL_SCANCODE_ESCAPE);
        break;
    case 7: stop = true; break;
    default: break;
    }
}
static void clear_again(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0:     /* read back as cleared, not as the defaults */
        CHECK(ui->keys[0][A_CROSS] == SDL_SCANCODE_UNKNOWN && ui->keys[0][A_CIRCLE] == SDL_SCANCODE_W);
        CHECK((int)ui->buttons[0][A_SQUARE] == -1 && !rrhk_combo_set(RRHK_COMBO_FAST, true));
        key(SDL_SCANCODE_F2); key(SDL_SCANCODE_RETURN); key(SDL_SCANCODE_UP);
        break;
    case 1:
        CHECK(ui->menu == RRHK_MENU_CONTROLS && ui->gamepad_page == 0 && rrhk_restore_row());
        key(SDL_SCANCODE_RETURN);
        break;
    case 2:
        CHECK(ui->keys[0][A_CROSS] == SDL_SCANCODE_W && ui->keys[0][A_CIRCLE] == SDL_SCANCODE_X);
        CHECK(ini(L"Test3D.Keyboard.Player1", L"Cross") == SDL_SCANCODE_W && ini(L"Test3D.Keyboard.Player1", L"Circle") == SDL_SCANCODE_X);
        CHECK(ui->keys[1][A_CROSS] == player2_key && !strcmp(ui->status, "Default bindings restored"));
        CHECK((int)ui->buttons[0][A_SQUARE] == -1);             /* the keyboard page restores keys only */
        key(SDL_SCANCODE_RIGHT);
        break;
    case 3: ui->row = 0; key(SDL_SCANCODE_UP); break;          /* the gamepad page's last row */
    case 4:
        CHECK(ui->gamepad_page == 1 && rrhk_restore_row());
        button(SDL_CONTROLLER_BUTTON_A, true);                  /* A: Enter */
        break;
    case 5:
        button(SDL_CONTROLLER_BUTTON_A, false);
        CHECK(ui->buttons[0][A_SQUARE] == SDL_CONTROLLER_BUTTON_X && ui->buttons[0][A_CROSS] == SDL_CONTROLLER_BUTTON_A);
        CHECK(ini(L"Test3D.Gamepad.Player1", L"Square") == SDL_CONTROLLER_BUTTON_X && rrhk_combo_set(RRHK_COMBO_FAST, true));
        key(SDL_SCANCODE_ESCAPE); key(SDL_SCANCODE_ESCAPE);
        break;
    case 6: stop = true; break;
    default: break;
    }
}

/* 1.7.6: a machine whose games may draw a widescreen picture: the options page's "Screen format" row, kept for this game, and
 * the picture shown 16 wide for 9 high; the next start reads it back. */
static void widescreen_script(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0: {
        CHECK(ui->widescreen == 0);
        int w = 0, h = 0;
        SDL_GetRendererOutputSize(SDL_GetRenderer(rrhk_window()), &w, &h);
        const SDL_Rect dst = rrhk_game_rect(SDL_GetRenderer(rrhk_window()));
        CHECK(dst.w * 3 == dst.h * 4 || dst.w * 3 == dst.h * 4 + 1 || dst.w * 3 + 1 == dst.h * 4);   /* the machine's 4:3 */
        key(SDL_SCANCODE_F2); key(SDL_SCANCODE_LEFT); key(SDL_SCANCODE_LEFT); key(SDL_SCANCODE_LEFT); key(SDL_SCANCODE_RETURN);   /* the options tile: before Restart and Quit */
        break;
    }
    case 1: CHECK(ui->menu == RRHK_MENU_OPTIONS); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_RETURN); break;
    case 2: {
        CHECK(ui->widescreen == 1 && !strcmp(ui->status, "16:9"));
        CHECK(ini(L"Test3D.Widescreen", L"Capabilities") == 1);
        const SDL_Rect dst = rrhk_game_rect(SDL_GetRenderer(rrhk_window()));
        CHECK(dst.h > 0 && dst.w * 9 >= dst.h * 16 - 16 && dst.w * 9 <= dst.h * 16 + 16);    /* 16:9 */
        key(SDL_SCANCODE_ESCAPE); key(SDL_SCANCODE_ESCAPE);
        break;
    }
    case 3: stop = true; break;
    default: break;
    }
}
static void widescreen_again(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0: CHECK(ui->widescreen == 1); break;         /* read back at the next start */
    case 1: stop = true; break;
    default: break;
    }
}

/* The machine's own option rows (slots 0 and 1, three each, while extra_rows is set) and the key hook that receives them. */
static void option_rows_hook(int slot, RrhkOptionRows *rows) {
    if (!extra_rows) return;
    for (int i = 0; i < 3; ++i) {
        /* 1.7.5: the first row of each slot names its own icon; the others get the generic one from the kit */
        if (i == 0) rrhk_option_row_icon(rows, EXTRA_KEY + slot * 3, RR_ICON_ROW_SPEED, "Machine row: %s", slot ? "B" : "A");
        else rrhk_option_row(rows, EXTRA_KEY + slot * 3 + i, "Machine row: %s", slot ? "B" : "A");
    }
}
static bool key_event(RrhkUi *ui, SDL_Scancode key, bool *running) {
    (void)ui; (void)running;
    if ((int)key < EXTRA_KEY || (int)key >= EXTRA_KEY + 6) return false;
    machine_key = (int)key;
    return true;
}

/* 1.7.7: a machine with no picture (pixels() NULL), then a 0 x 0 one, under each of the four filters: no crash (xBR and Scale2x
 * read the picture), a black game area, then the picture again once the machine has one. `graphics_page`: the filter changed on the F3 page (a
 * machine with graphics options and a growing picture), otherwise F3 cycles it. */
static bool graphics_page;
static int null_filter, null_checks;
static void next_filter(void) {
    if (graphics_page) { key(SDL_SCANCODE_F3); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_DOWN); key(SDL_SCANCODE_RIGHT); key(SDL_SCANCODE_ESCAPE); }
    else key(SDL_SCANCODE_F3);
}
static void null_picture_script(void) {
    RrhkUi *ui = rrhk_ui();
    const int s = step++;
    if (s == 0) {
        memset(black_seen, 0, sizeof black_seen); black_wrong = 0;
        null_filter = ui->filter; no_picture = true;
        return;
    }
    /* four filters, three presents or more each: NULL (steps 1-16), then 0 x 0 (steps 18-33) */
    if ((s >= 1 && s <= 16) || (s >= 18 && s <= 33)) { if (s % 4 == 0) next_filter(); return; }
    if (s == 17 || s == 34) {
        CHECK(ui->filter == null_filter);                       /* back to the first one */
        for (int f = 0; f < 4; ++f) CHECK(black_seen[f] > 0);
        CHECK(black_wrong == 0);
        memset(black_seen, 0, sizeof black_seen); black_wrong = 0;
        no_picture = false; zero_size = s == 17;
        if (s == 34) { null_checks = picture_checks; want_picture = true; }
        return;
    }
    if (s == 37) { CHECK(picture_checks == null_checks + 1 && picture_ok); stop = true; }   /* the picture again */
}

/* 1.7.7 (HOST_KIT D30): Sync to display, without a display. The decision Auto and Locked make for given rates; the sound's
 * factor held within its bounds; a locked game's sound buffer neither grows nor runs dry over ten simulated minutes, also when
 * the refresh was measured 0.1 % off; then through the real loop with a stand-in refresh (RETRORECOMP_TEST_REFRESH_HZ): the
 * row cycles Auto, Locked, Free, Variable refresh and is kept, the game is paced by the present in play only (free in the menus,
 * under Tab and at max speed), its sound factor is machine / refresh while locked and exactly 1 otherwise. */
static void sync_pure_checks(void) {
    CHECK(rrhk_sync_decide(RRHK_SYNC_AUTO, 60.0, 59.9228));          /* Mega Drive, Master System on a 60 Hz screen */
    CHECK(rrhk_sync_decide(RRHK_SYNC_AUTO, 60.0, 60.0988));          /* NES, Super Nintendo */
    CHECK(rrhk_sync_decide(RRHK_SYNC_AUTO, 59.94, 59.7275));         /* Game Boy on a 59.94 Hz screen */
    CHECK(!rrhk_sync_decide(RRHK_SYNC_AUTO, 60.0, 59.1856));         /* Neo Geo: 1.4 %, beyond Auto */
    CHECK(rrhk_sync_decide(RRHK_SYNC_LOCKED, 60.0, 59.1856));        /* ... but within Locked's 3 % */
    CHECK(!rrhk_sync_decide(RRHK_SYNC_AUTO, 60.0, 50.0) && !rrhk_sync_decide(RRHK_SYNC_LOCKED, 60.0, 50.0));   /* PAL on 60 Hz */
    CHECK(!rrhk_sync_decide(RRHK_SYNC_AUTO, 144.0, 59.9228) && !rrhk_sync_decide(RRHK_SYNC_LOCKED, 144.0, 59.9228));
    CHECK(rrhk_sync_decide(RRHK_SYNC_AUTO, 50.0, 49.92));            /* an Amiga PAL game on a 50 Hz screen */
    CHECK(!rrhk_sync_decide(RRHK_SYNC_FREE, 60.0, 60.0) && !rrhk_sync_decide(RRHK_SYNC_VARIABLE, 60.0, 60.0));
    CHECK(!rrhk_sync_decide(RRHK_SYNC_AUTO, 0.0, 60.0) && !rrhk_sync_decide(RRHK_SYNC_AUTO, 60.0, 0.0));
    /* the factor: base clamped to 3 %, the fill's correction to 0.5 % */
    const double base = 59.9228 / 60.0;
    CHECK(SDL_fabs(rr_drc_ratio(base, 1000.0, 1000.0) - base) < 1e-12);
    CHECK(SDL_fabs(rr_drc_ratio(base, 0.0, 1000.0) - base * 1.005) < 1e-12);
    CHECK(SDL_fabs(rr_drc_ratio(base, 1e9, 1000.0) - base * 0.995) < 1e-12);
    CHECK(SDL_fabs(rr_drc_ratio(0.5, 1000.0, 1000.0) - 0.97) < 1e-12 && SDL_fabs(rr_drc_ratio(2.0, 1000.0, 1000.0) - 1.03) < 1e-12);
    for (int i = 0; i <= 100; ++i) {
        const double r = rr_drc_ratio(0.9 + i * 0.002, i * 50.0, 2500.0);
        CHECK(r >= 0.97 * 0.995 - 1e-12 && r <= 1.03 * 1.005 + 1e-12);
    }
    /* the resampler: continuous, its length follows the ratio */
    static int16_t in[48000 * 2], out[50000 * 2];
    for (int i = 0; i < 48000; ++i) in[2 * i] = in[2 * i + 1] = (int16_t)(10000.0 * SDL_sin(i * 0.01));
    RrDrcResampler r; memset(&r, 0, sizeof r);
    size_t total = 0;
    for (int block = 0; block < 60; ++block) total += rr_drc_resample(&r, in + block * 800 * 2, 800, 2, base, out, 50000 - total);
    CHECK(total >= 47937 && total <= 47939);                  /* 48000 x 0.99871 */
    memset(&r, 0, sizeof r);
    CHECK(rr_drc_resample(&r, in, 800, 2, 1.0, out, 50000) == 800 && out[2] == in[0] && out[4] == in[2]);   /* 1.0: a sample late, no change */
    /* closed loop: a locked game (one frame per refresh) makes 48000 / machine_hz frames of sound a frame, the device plays
     * 48000 / true_refresh; the factor is computed from the measured refresh. The buffer before each push stays near its target. */
    for (int trial = 0; trial < 2; ++trial) {
        const double machine = 59.9228, measured = 60.0, real = trial ? 59.94 : 60.0;   /* 2nd: the refresh measured 0.1 % off */
        const double target = 2000.0;
        double fill = target, made = 0.0, lowest = 1e9, highest = 0.0;
        RrDrcResampler loop; memset(&loop, 0, sizeof loop);
        for (int frame = 0; frame < 60 * 600; ++frame) {
            made += 48000.0 / machine;
            const size_t frames = (size_t)made; made -= (double)frames;
            static int16_t block[1000 * 2], stretched[1100 * 2];
            for (size_t i = 0; i < frames; ++i) block[2 * i] = block[2 * i + 1] = (int16_t)(frame + (int)i);
            fill += (double)rr_drc_resample(&loop, block, frames, 2, rr_drc_ratio(machine / measured, fill, target), stretched, 1100);
            fill -= 48000.0 / real;
            if (frame > 600) { if (fill < lowest) lowest = fill; if (fill > highest) highest = fill; }
        }
        CHECK(lowest > target * 0.5 && highest < target * 1.5);
        if (failures) fprintf(stderr, "  sync loop %d: fill %.1f .. %.1f\n", trial, lowest, highest);
    }
}

static void set_env(const char *name, const char *value);
static void refresh(const char *hz) { set_env("RETRORECOMP_TEST_REFRESH_HZ", hz); rrhk_sync.remeasure = true; }
static void sync_script(void) {
    RrhkUi *ui = rrhk_ui();
    switch (step++) {
    case 0:     /* Auto, the stand-in screen at 60.06 Hz, a 60 Hz machine: locked, its sound by 60 / 60.06 in play */
        CHECK(rrhk_sync.active && rrhk_sync.mode == RRHK_SYNC_AUTO);
        break;
    case 3:
        CHECK(rrhk_sync.lock && SDL_fabs(rrhk_sync.refresh_hz - 60.06) < 1e-9 && SDL_fabs(rrhk_audio_base() - 60.0 / 60.06) < 1e-12);
        ui->menu = RRHK_MENU_OPTIONS;          /* a menu: free, the factor 1, vsync kept */
        break;
    case 5:
        CHECK(rrhk_sync.lock && rrhk_audio_base() == 1.0);
        ui->menu = 0;
        break;
    case 7:
        CHECK(rrhk_audio_base() != 1.0);
        ui->max_speed = 1;                     /* max speed: free */
        break;
    case 9:
        CHECK(rrhk_audio_base() == 1.0);
        ui->max_speed = 0;
        break;
    case 11:
        CHECK(rrhk_audio_base() != 1.0 && rrhk_sync.quick_presents > 0);   /* the dummy driver never waits: held to 105 % */
        refresh("144");                        /* another display, 144 Hz: Auto is free, and says why */
        break;
    case 13: {
        CHECK(!rrhk_sync.lock && rrhk_audio_base() == 1.0 && rrhk_sync.why && !strcmp(rrhk_sync.why, "far"));
        char value[48]; rrhk_sync_value(value, sizeof value);
        CHECK(!strcmp(value, "Auto (free)"));
        refresh("61.5");                       /* 2.5 %: Auto free, Locked locks */
        break;
    }
    case 15:
        CHECK(!rrhk_sync.lock);
        ui->menu = RRHK_MENU_OPTIONS;
        for (int k = rrhk_option_selected(); k > 2; --k) key(SDL_SCANCODE_UP);     /* F3 page, F4, then Sync to display */
        for (int k = rrhk_option_selected(); k < 2; ++k) key(SDL_SCANCODE_DOWN);
        key(SDL_SCANCODE_RETURN);
        break;
    case 18: {  /* Locked, kept; named once measured */
        CHECK(rrhk_sync.mode == RRHK_SYNC_LOCKED && ini(L"Test3D.Video", L"sync") == RRHK_SYNC_LOCKED && rrhk_sync.lock);
        CHECK(strstr(ui->status, "61.50 Hz") && strstr(ui->status, "60.00 Hz") && strstr(ui->status, "+2.50 %"));
        char value[48]; rrhk_sync_value(value, sizeof value);
        CHECK(!strcmp(value, "Locked"));
        key(SDL_SCANCODE_RETURN);
        break;
    }
    case 21:    /* Free: the game's own clock, vsync off */
        CHECK(rrhk_sync.mode == RRHK_SYNC_FREE && !rrhk_sync.lock && !rrhk_sync.vsync && rrhk_audio_base() == 1.0);
        CHECK(strstr(ui->status, "60.00 Hz") != NULL);
        key(SDL_SCANCODE_RETURN);
        break;
    case 24:    /* Variable refresh: free, vsync off; on Windows the next start opens Direct3D 12 */
        CHECK(rrhk_sync.mode == RRHK_SYNC_VARIABLE && !rrhk_sync.lock && !rrhk_sync.vsync && ini(L"Test3D.Video", L"sync") == 3);
        ui->menu = 0; stop = true;          /* the machine runs again and ends the run */
        break;
    default: break;
    }
}
static void sync_again(void) {
    switch (step++) {
    case 0:
        CHECK(rrhk_sync.mode == RRHK_SYNC_VARIABLE && !rrhk_sync.lock);
#ifdef _WIN32
        CHECK(SDL_GetHint(SDL_HINT_RENDER_DRIVER) && !strcmp(SDL_GetHint(SDL_HINT_RENDER_DRIVER), "direct3d12"));
#endif
        rrhk_sync_next();                      /* back to Auto for the runs after this one */
        CHECK(rrhk_sync.mode == RRHK_SYNC_AUTO && ini(L"Test3D.Video", L"sync") == 0);
        break;
    case 2: stop = true; break;
    default: break;
    }
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
    .pixel_pitch = width, .rumble = true, .native_caption = RRHK_CORE_CAPTION,
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

/* 1.7.6 (HOST_KIT D29): a Linux game's launcher healed after its folder moved. The expected lines are retrorecomp/linux_desktop.py's
 * own `_argument` / `_value` for this path (a space, $, ", `, % and a backslash). */
#define LAUNCHER_ID "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
static const char moved_exe[] = "/home/arthur/Mes Jeux/Sonic $2 \"x\" `y` 100%\\b.elf";
static const char want_exec[] = "Exec=\"/home/arthur/Mes Jeux/Sonic \\\\$2 \\\\\"x\\\\\" \\\\`y\\\\` 100%%\\\\\\\\b.elf\"";
static const char want_path[] = "Path=/home/arthur/Mes Jeux";
static const char want_icon[] = "Icon=/home/arthur/Mes Jeux/datas/launchers/" LAUNCHER_ID ".png";
#define OLD_LAUNCHER(exec, path, icon, marker) "[Desktop Entry]\nType=Application\nVersion=1.0\nName=Sonic.elf\n" exec "\n" path "\n" \
    icon "\nTerminal=false\nCategories=Game;\nStartupNotify=false\nX-Custom=kept\n" marker "\n\n[Desktop Action Other]\nExec=other\n"
static void launcher_checks(void) {
    static const char stale[] = OLD_LAUNCHER("Exec=\"/media/old/Sonic.elf\"", "Path=/media/old", "Icon=/media/old/datas/launchers/"
                                             LAUNCHER_ID ".png", "X-RetroRecomp-Identity=" LAUNCHER_ID);
    char *healed = NULL, expected[2048];
    size_t len = 0;
    snprintf(expected, sizeof expected, OLD_LAUNCHER("%s", "%s", "%s", "X-RetroRecomp-Identity=" LAUNCHER_ID), want_exec, want_path, want_icon);
    CHECK(rrhk_launcher_text(stale, strlen(stale), moved_exe, &healed, &len) == 1);
    CHECK(healed && len == strlen(expected) && !memcmp(healed, expected, len));   /* the three lines, every other byte kept */
    {   /* healed once: current, untouched */
        char *again = NULL; size_t again_len = 0;
        CHECK(healed && rrhk_launcher_text(healed, len, moved_exe, &again, &again_len) == 0 && !again);
    }
    free(healed);
    /* not ours: no marker, or a marker that is not 64 lower-case hex digits */
    static const char foreign[] = OLD_LAUNCHER("Exec=/media/old/Sonic.elf", "Path=/media/old", "Icon=x", "X-Other=1");
    static const char upper[] = OLD_LAUNCHER("Exec=/media/old/Sonic.elf", "Path=/media/old", "Icon=x",
                                             "X-RetroRecomp-Identity=0123456789ABCDEF0123456789abcdef0123456789abcdef0123456789abcdef");
    healed = NULL;
    CHECK(rrhk_launcher_text(foreign, strlen(foreign), moved_exe, &healed, &len) == -1 && !healed);
    CHECK(rrhk_launcher_text(upper, strlen(upper), moved_exe, &healed, &len) == -1 && !healed);
    /* only Exec moved (the game renamed with its launcher): healed too; a path too long is left alone */
    char only_exec[2048];
    snprintf(only_exec, sizeof only_exec, OLD_LAUNCHER("Exec=\"/old.elf\"", "%s", "%s", "X-RetroRecomp-Identity=" LAUNCHER_ID), want_path, want_icon);
    CHECK(rrhk_launcher_text(only_exec, strlen(only_exec), moved_exe, &healed, &len) == 1 && healed);
    free(healed); healed = NULL;
    static char long_exe[9500];   /* past the 8 KiB of an Exec line: never a truncated path */
    memset(long_exe, 'a', sizeof long_exe - 1); long_exe[0] = '/'; long_exe[100] = '/';
    CHECK(rrhk_launcher_text(stale, strlen(stale), long_exe, &healed, &len) <= 0 && !healed);
#ifndef _WIN32
    {   /* the files: a moved folder's launcher rewritten (0755), our .hidden line gone, the player's kept byte for byte */
        char folder[] = "/tmp/rrhk-launcher-XXXXXX", exe[512], path[600], data[2048];
        CHECK(mkdtemp(folder) != NULL);
        snprintf(exe, sizeof exe, "%s/Sonic.elf", folder);
        snprintf(path, sizeof path, "%s.desktop", exe);
        FILE *f = fopen(path, "wb"); CHECK(f != NULL); if (f) { fputs(stale, f); fclose(f); }
        snprintf(path, sizeof path, "%s/.hidden", folder);
        f = fopen(path, "wb"); CHECK(f != NULL); if (f) { fputs("mine\xe9\r\nSonic.elf\nother\n", f); fclose(f); }
        CHECK(rrhk_heal_launcher(exe) == 1);
        snprintf(path, sizeof path, "%s.desktop", exe);
        struct stat st;
        CHECK(stat(path, &st) == 0 && (st.st_mode & 0777) == 0755);
        f = fopen(path, "rb"); size_t n = f ? fread(data, 1, sizeof data - 1, f) : 0; if (f) fclose(f); data[n] = 0;
        CHECK(strstr(data, "Path=") && !strncmp(strstr(data, "Path=") + 5, folder, strlen(folder)) && !strstr(data, "/media/old"));
        CHECK(strstr(data, "X-Custom=kept\n") && strstr(data, "\nExec=other\n"));
        snprintf(path, sizeof path, "%s/.hidden", folder);
        f = fopen(path, "rb"); n = f ? fread(data, 1, sizeof data - 1, f) : 0; if (f) fclose(f); data[n] = 0;
        CHECK(!strcmp(data, "mine\xe9\r\nother\n"));
        CHECK(rrhk_heal_launcher(exe) == 0);    /* current now */
        f = fopen(path, "wb"); if (f) { fputs("Sonic.elf\n", f); fclose(f); }
        CHECK(rrhk_heal_launcher(exe) == 0 && stat(path, &st) != 0);   /* a .hidden left empty is removed */
        snprintf(path, sizeof path, "%s.desktop", exe);
        f = fopen(path, "wb"); if (f) { fputs(foreign, f); fclose(f); }
        CHECK(rrhk_heal_launcher(exe) == -1);   /* not ours: untouched */
        f = fopen(path, "rb"); n = f ? fread(data, 1, sizeof data - 1, f) : 0; if (f) fclose(f); data[n] = 0;
        CHECK(!strcmp(data, foreign));
        unlink(path);
        CHECK(rrhk_heal_launcher(exe) == -1);   /* no launcher */
        rmdir(folder);
    }
#endif
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    launcher_checks();
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
    CHECK(step >= 76);
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
    /* a console's pad: its L2 and R2 rows on shoulder buttons, not on the triggers */
    static RrhkAction plain_actions[ACTIONS];
    memcpy(plain_actions, actions, sizeof actions);
    plain_actions[A_L2].pad[0] = SDL_CONTROLLER_BUTTON_PADDLE2; plain_actions[A_R2].pad[0] = SDL_CONTROLLER_BUTTON_PADDLE3;
    plain.actions = plain_actions;
    plain.analog_sticks = 0; plain.script_axes = NULL; plain.trigger_buttons = false;
    plain.gfx_options = NULL; plain.gfx_option_count = 0; plain.gfx_apply = NULL;
    plain.pixel_pitch = NULL; plain.rumble = false;
    plain.host_media = 0; plain.media_count = NULL; plain.media_current = NULL; plain.media_select = NULL;
    plain.native_caption = NULL;
    current = &plain;
    scale = 1; draw_picture(); disc_calls = 0; rumble_calls = 0;
    begin(plain_script);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 24);       /* the last step answered Yes to "Quit?" */
    /* 5. 1.7.4: the stretched mode is read back at the next start, even by a machine that reads its former preferences and knows
     * three modes (Master System, Game Gear, Game Boy clamp what they read); F4 then goes back to the window. */
    plain.settings_loaded = three_modes;
    begin(stretched_script);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 3);
    /* 6. 1.7.5: Quick save and Quick load bound on player 1's pad, then held in play. */
    plain.settings_loaded = NULL;
    plain.state_path = quick_path; plain.state_ready = quick_ready; plain.state_file = quick_file;
    begin(quick_script);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 20);
    /* 7. 1.7.5: a game row on R2 on a console profile. */
    begin(r2_script);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 13);
    /* 8. 1.7.5: a machine row on player 2's gamepad page. */
    plain.pad_rows = &port_row; plain.pad_row_count = 1;
    begin(pad_row_script);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 10);
    /* 9. 1.8.1: the F2 menu's Quit tile (1.7.6: the options page's Quit row). */
    plain.pad_rows = NULL; plain.pad_row_count = 0;
    begin(quit_row_script);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 8);
    /* 9c. 1.8.1: the host's « Change this option? » (session ABI 9). */
    begin(relaunch_confirm_script);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 5);
    /* 9b. 1.8.1: the F2 menu's Restart tile, before Quit. */
    begin(restart_tile_script);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 5);

    /* 11. 1.7.6: a stick direction bound to a game row. */
    begin(stick_script);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 22);
    /* 12. 1.7.6: the screen format of a machine whose games may draw a widescreen picture. */
    plain.widescreen = true;
    begin(widescreen_script);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 4);
    begin(widescreen_again);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 2);
    plain.widescreen = false;
    /* 13. 1.7.6: clearing any binding, Restore defaults. */
    begin(clear_script);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 8);
    begin(clear_again);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 7);
    /* 14. 1.7.7: no picture under each filter, on a console (F3 cycles) and on the machine whose picture grows (the F3 page). */
    begin(null_picture_script);
    CHECK(rrhk_main(&plain, "Capabilities", 2) == 0);
    CHECK(step >= 38);
    current = &full;
    graphics_page = true;
    begin(null_picture_script);
    CHECK(rrhk_main(&full, "Capabilities", 2) == 0);
    CHECK(step >= 38);
    graphics_page = false;
    /* 15. 1.7.7 (HOST_KIT D30): Sync to display (the checks set SDL_RENDER_VSYNC=0, which keeps the kit's vsync as the
     * conversion's runs have it; this run lifts it and stands in for the measured refresh). */
    sync_pure_checks();
    set_env("SDL_RENDER_VSYNC", "");
    set_env("RETRORECOMP_TEST_REFRESH_HZ", "60.06");
    begin(sync_script);
    CHECK(rrhk_main(&full, "Capabilities", 2) == 0);
    CHECK(step >= 25);
    begin(sync_again);
    CHECK(rrhk_main(&full, "Capabilities", 2) == 0);
    CHECK(step >= 3);
    set_env("RETRORECOMP_TEST_REFRESH_HZ", "");
    set_env("SDL_RENDER_VSYNC", "0");
    /* 10. 1.7.6: the graphics page from F2 and from the options page, on the machine that has one. */
    begin(graphics_entry_script);
    CHECK(rrhk_main(&full, "Capabilities", 2) == 0);
    CHECK(step >= 7);

    if (stick) SDL_JoystickClose(stick);
    SDL_Quit();
    free(picture);
    printf("%s: %d checks, %llu frames, %d failure(s)\n", failures ? "FAIL" : "PASS", checks, (unsigned long long)frames, failures);
    return failures ? 1 : 0;
}
