/* Four players through the host kit's real loop, with no game (tools/hostkit_players_selftest.py).
 *
 * The kit's shell and the CPS-1 adapter are compiled as an export compiles them; the CPS-1 machine is a stub that plays
 * a script from its frame function and records what the kit hands it. Four identical virtual game controllers are
 * attached before the window opens (dummy video and audio drivers, a hidden window). Built twice: a four-player board
 * (RR_CPS1_PLAYERS 4) and a two-player one (2). It checks that
 *   - four identical pads go to four distinct players (two on the two-player board, pads 3 and 4 to nobody);
 *   - one distinct button on each pad reaches its own player's pad word: players 1-2 through run_frame, 3-4 through
 *     rr_cps1_set_extra_pads (from run_frame since the multiplayer work), and on the two-player board pads 3 and 4 change nothing;
 *   - Start+Back held over a second on pad 3, and its triggers, neither restart nor change the speed; on pad 1 they do;
 *   - players 3 and 4 have keyboard keys of their own, no key drives two actions, CPS-1's explicit pad layout is kept;
 *   - a binding made in F2 swaps with the action that had the key or button, and a swap that leaves an action with no key
 *     still reads so after a reload; a key saved before 1.6.9 on a new default of player 3 wins and the default goes;
 *     an adapter that lists two pad columns gets player 1's layout for players 3 and 4.
 * No ROM, no visible window, no sound device; about four seconds of wall clock per board (the hold of one second is
 * measured on SDL's clock, twice). Original RetroRecomp code: MIT. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include "retro_console16.h"
#include "console16_state.h"
#include "platform_io.h"
#include "retro_keyboard.h"
#include "hostkit/hostkit_internal.h"

static int failures;
#define CHECK(condition) do { if (!(condition)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

enum { B1 = 1, B2 = 2, B3 = 4, B4 = 8, START_BIT = 64, COIN_BIT = 128 };   /* the bits of rrhk_cps1.c */
enum { A_ROW, B_ROW, C_ROW, X_ROW, Y_ROW, Z_ROW, START_ROW, COIN_ROW, UP_ROW, DOWN_ROW, LEFT_ROW, RIGHT_ROW, ROWS };

#include "cps1_stub.h"

static SDL_Joystick *stick[4];

static void press(int pad, SDL_GameControllerButton button, bool down) {
    if (pad < 4 && stick[pad]) CHECK(SDL_JoystickSetVirtualButton(stick[pad], button, down ? 1 : 0) == 0);
}
/* A virtual trigger is a full-range axis: SDL maps -32768 to a released trigger (0) and 0 to half-way (16384, past the
 * threshold), so a released trigger is -32768, as a real pad's at rest. */
static void trigger(int pad, SDL_GameControllerAxis axis, bool down) {
    if (pad < 4 && stick[pad]) CHECK(SDL_JoystickSetVirtualAxis(stick[pad], axis, down ? 32767 : -32768) == 0);
}

/* The script, one step per guest frame; times on SDL's clock where the kit measures a hold in milliseconds. */
enum { DEAL, BUTTONS, SPEED_P3, SPEED_P3_CHECK, SPEED_P1, SPEED_P1_CHECK, SPEED_P1_OFF, HOLD_P3, HOLD_P1, DONE };
static int step;
static unsigned step_frame;
static Uint64 step_ticks;
static void next(void) { ++step; step_frame = 0; step_ticks = SDL_GetTicks64(); }

/* No key drives two actions of the four rows of players (the keyboard is shared). */
static void unique_keys(void) {
    const RrhkUi *ui = rrhk_ui();
    for (int p = 0; p < RRHK_MAX_PLAYERS; ++p) for (int a = 0; a < ROWS; ++a) {
        if (ui->keys[p][a] == SDL_SCANCODE_UNKNOWN) continue;
        for (int q = 0; q <= p; ++q) for (int b = 0; b < (q == p ? a : ROWS); ++b) CHECK(ui->keys[q][b] != ui->keys[p][a]);
    }
}

static void deal(void) {
    const RrhkUi *ui = rrhk_ui();
    for (int p = 0; p < RRHK_MAX_PLAYERS; ++p) {
        if (p < RR_CPS1_PLAYERS) CHECK(ui->pads[p] != NULL);
        else CHECK(ui->pads[p] == NULL);
        for (int q = 0; q < p; ++q) CHECK(!ui->pads[p] || ui->pads[p] != ui->pads[q]);
    }
    /* CPS-1 writes its pad columns itself (PADS): kept as they are, the same for every player. */
    for (int p = 0; p < RRHK_MAX_PLAYERS; ++p) {
        CHECK(ui->buttons[p][A_ROW] == SDL_CONTROLLER_BUTTON_A && ui->buttons[p][Z_ROW] == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER);
        CHECK(ui->buttons[p][START_ROW] == SDL_CONTROLLER_BUTTON_START && ui->buttons[p][COIN_ROW] == SDL_CONTROLLER_BUTTON_BACK);
    }
    /* Players 3 and 4: the kit's keys (directions, buttons 1-3, Start, Coin); no key drives two actions of the players in play,
     * and none is a key of the kit. */
    /* 1.7.6: player 1 on S D F / E R T; player 3 on I K J L + U O N, player 4 on G B V H + C X 9 */
    static const SDL_Scancode third[ROWS] = {SDL_SCANCODE_U, SDL_SCANCODE_O, SDL_SCANCODE_N, 0, 0, 0, SDL_SCANCODE_3, SDL_SCANCODE_7,
                                             SDL_SCANCODE_I, SDL_SCANCODE_K, SDL_SCANCODE_J, SDL_SCANCODE_L};
    static const SDL_Scancode fourth[ROWS] = {SDL_SCANCODE_C, SDL_SCANCODE_X, SDL_SCANCODE_9, 0, 0, 0, SDL_SCANCODE_4, SDL_SCANCODE_8,
                                              SDL_SCANCODE_G, SDL_SCANCODE_B, SDL_SCANCODE_V, SDL_SCANCODE_H};
    for (int a = 0; a < ROWS; ++a) CHECK(ui->keys[2][a] == third[a] && ui->keys[3][a] == fourth[a]);
    static const SDL_Scancode kit[] = {SDL_SCANCODE_ESCAPE, SDL_SCANCODE_TAB, SDL_SCANCODE_GRAVE, SDL_SCANCODE_M, SDL_SCANCODE_P,
                                       SDL_SCANCODE_DELETE, SDL_SCANCODE_BACKSPACE, SDL_SCANCODE_MINUS, SDL_SCANCODE_EQUALS};
    for (int p = 0; p < RRHK_MAX_PLAYERS; ++p) for (int a = 0; a < ROWS; ++a) {
        const SDL_Scancode key = ui->keys[p][a];
        if (key == SDL_SCANCODE_UNKNOWN) continue;
        CHECK(key < SDL_SCANCODE_F1 || key > SDL_SCANCODE_F12);
        for (size_t k = 0; k < sizeof kit / sizeof kit[0]; ++k) CHECK(key != kit[k]);
        for (int q = 0; q <= p; ++q) for (int b = 0; b < (q == p ? a : ROWS); ++b) CHECK(ui->keys[q][b] != key);
    }
}

bool rr16_frame(uint16_t p1, uint16_t p2) {
    const RrhkUi *ui = rrhk_ui();
    ++frames; ++step_frame;
    switch (step) {
    case DEAL:
        deal();
        /* One distinct button on each pad: A, B, X, Y are buttons 1-4 of CPS-1. */
        press(0, SDL_CONTROLLER_BUTTON_A, true); press(1, SDL_CONTROLLER_BUTTON_B, true);
        press(2, SDL_CONTROLLER_BUTTON_X, true); press(3, SDL_CONTROLLER_BUTTON_Y, true);
        next(); break;
    case BUTTONS:
        if (step_frame < 3) break;
        CHECK(p1 == B1); CHECK(p2 == B2);
        CHECK(extra_calls > 0);
        if (RR_CPS1_PLAYERS > 3) { CHECK(extra[0] == B3); CHECK(extra[1] == B4); }
        else { CHECK(extra[0] == 0); CHECK(extra[1] == 0); }
        for (int pad = 0; pad < 4; ++pad) {
            static const SDL_GameControllerButton pressed[4] = {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_B,
                                                                SDL_CONTROLLER_BUTTON_X, SDL_CONTROLLER_BUTTON_Y};
            press(pad, pressed[pad], false);
        }
        next(); break;
    case SPEED_P3:   /* both triggers of pad 3: neither the fast-forward nor the maximum speed */
        trigger(2, SDL_CONTROLLER_AXIS_TRIGGERRIGHT, true); trigger(2, SDL_CONTROLLER_AXIS_TRIGGERLEFT, true);
        next(); break;
    case SPEED_P3_CHECK:
        if (step_frame < 3) break;
        CHECK(!ui->fast_hold); CHECK(!ui->max_speed);
        CHECK(p1 == 0 && p2 == 0);
        trigger(2, SDL_CONTROLLER_AXIS_TRIGGERRIGHT, false); trigger(2, SDL_CONTROLLER_AXIS_TRIGGERLEFT, false);
        next(); break;
    case SPEED_P1:   /* the right trigger of pad 1 still holds the fast-forward */
        trigger(0, SDL_CONTROLLER_AXIS_TRIGGERRIGHT, true);
        next(); break;
    case SPEED_P1_CHECK:
        if (step_frame < 3) break;
        CHECK(ui->fast_hold != 0); CHECK(!ui->max_speed);
        trigger(0, SDL_CONTROLLER_AXIS_TRIGGERRIGHT, false);
        next(); break;
    case SPEED_P1_OFF:
        if (step_frame < 3) break;
        CHECK(!ui->fast_hold);
        press(2, SDL_CONTROLLER_BUTTON_START, true); press(2, SDL_CONTROLLER_BUTTON_BACK, true);
        next(); break;
    case HOLD_P3:    /* Start+Back of pad 3, the restart combination of every pad before 1.6.9, held 1.3 s: nothing */
        if (step_frame == 4) {
            if (RR_CPS1_PLAYERS > 2) CHECK(extra[0] == (START_BIT | COIN_BIT));   /* player 3 does press Start and Coin */
            else CHECK(extra[0] == 0);
            CHECK(p1 == 0 && p2 == 0);
        }
        if (SDL_GetTicks64() - step_ticks < 1300) break;
        CHECK(resets == 0);
        press(2, SDL_CONTROLLER_BUTTON_START, false); press(2, SDL_CONTROLLER_BUTTON_BACK, false);
        press(0, SDL_CONTROLLER_BUTTON_START, true); press(0, SDL_CONTROLLER_BUTTON_BACK, true);
        next(); break;
    case HOLD_P1:    /* the same on pad 1 restarts once the second has passed */
        if (!resets && SDL_GetTicks64() - step_ticks < 1600) break;
        CHECK(resets == 1);
        press(0, SDL_CONTROLLER_BUTTON_START, false); press(0, SDL_CONTROLLER_BUTTON_BACK, false);
        next(); break;
    default:
        return false;    /* the machine asks to stop: rrhk_main returns */
    }
    return true;
}

/* After the loop: the F2 binding swap and the kit's default pad columns, on the kit's state as the loop left it. */
static void bindings(void) {
    RrhkUi *ui = rrhk_ui();
    const SDL_Scancode w = ui->keys[0][A_ROW], x = ui->keys[0][B_ROW], p2a = ui->keys[1][A_ROW];
    rrhk_assign(0, A_ROW, false, x);                     /* player 1's button 1 takes the key of its button 2 */
    CHECK(ui->keys[0][A_ROW] == x && ui->keys[0][B_ROW] == w);
    rrhk_assign(1, A_ROW, false, w);                     /* player 2 takes a key of player 1: the keyboard is shared */
    CHECK(ui->keys[1][A_ROW] == w && ui->keys[0][B_ROW] == p2a);
    rrhk_assign(0, A_ROW, true, SDL_CONTROLLER_BUTTON_B); /* a pad button swaps within its own player only */
    CHECK(ui->buttons[0][A_ROW] == SDL_CONTROLLER_BUTTON_B && ui->buttons[0][B_ROW] == SDL_CONTROLLER_BUTTON_A);
    CHECK(ui->buttons[1][A_ROW] == SDL_CONTROLLER_BUTTON_A && ui->buttons[1][B_ROW] == SDL_CONTROLLER_BUTTON_B);
    rrhk_assign(0, C_ROW, false, ui->keys[0][C_ROW]);    /* the same key again: nothing moves */
    CHECK(ui->keys[0][A_ROW] == x && ui->keys[0][B_ROW] == p2a);
    /* A swap into nothing: player 3's button 4 has no key; taking U from button 1 leaves button 1 with none. */
    if (RR_CPS1_PLAYERS > 3) {
        rrhk_assign(2, X_ROW, false, SDL_SCANCODE_U);
        CHECK(ui->keys[2][X_ROW] == SDL_SCANCODE_U && ui->keys[2][A_ROW] == SDL_SCANCODE_UNKNOWN);
    }
    unique_keys();

    /* Reload, as the next start does: what F2 stored comes back, the "no key" of the swap included, and no key is on two actions. */
    const RrhkMachine *board = rrhk_adapter();
    rrhk_bind(board); rrhk_load_bindings();
    CHECK(ui->keys[0][A_ROW] == x && ui->keys[0][B_ROW] == p2a && ui->keys[1][A_ROW] == w);
    CHECK(ui->buttons[0][A_ROW] == SDL_CONTROLLER_BUTTON_B && ui->buttons[0][B_ROW] == SDL_CONTROLLER_BUTTON_A);
    if (RR_CPS1_PLAYERS > 3) CHECK(ui->keys[2][X_ROW] == SDL_SCANCODE_U && ui->keys[2][A_ROW] == SDL_SCANCODE_UNKNOWN);
    unique_keys();

    /* A file that put player 1's button 4 on I, the default Up of player 3 (1.7.6): the saved key wins, the default goes. */
    wchar_t value[16];
    swprintf(value, 16, L"%d", (int)SDL_SCANCODE_I);
    CHECK(rr_ini_set(L"CPS1.Keyboard.Player1", L"B4", value, ui->ini_file));
    rrhk_bind(board); rrhk_load_bindings();
    CHECK(ui->keys[0][X_ROW] == SDL_SCANCODE_I && ui->keys[2][UP_ROW] == SDL_SCANCODE_UNKNOWN);
    CHECK(ui->keys[2][DOWN_ROW] == SDL_SCANCODE_K);   /* the other defaults stay */
    unique_keys();

    /* 1.7.6: player 1's defaults moved from W X C / A S D to S D F / E R T (by position). A saved key still equal to the former
     * default on this layout (W) is no choice: the new default (S) comes back; a key the player chose (K) stays. */
    swprintf(value, 16, L"%d", (int)rr_keyboard_letter(SDLK_w, SDL_SCANCODE_W));
    CHECK(rr_ini_set(L"CPS1.Keyboard.Player1", L"B1", value, ui->ini_file));
    swprintf(value, 16, L"%d", (int)SDL_SCANCODE_K);
    CHECK(rr_ini_set(L"CPS1.Keyboard.Player1", L"B2", value, ui->ini_file));
    rrhk_bind(board); rrhk_load_bindings();
    /* player 2 saved S above (the swap): player 1's new default S is dropped, never shared; the chosen K stays */
    CHECK(ui->keys[1][A_ROW] == SDL_SCANCODE_S && ui->keys[0][A_ROW] == SDL_SCANCODE_UNKNOWN);
    CHECK(ui->keys[0][B_ROW] == SDL_SCANCODE_K && ui->keys[0][C_ROW] == SDL_SCANCODE_F);
    unique_keys();
    swprintf(value, 16, L"%d", (int)SDL_SCANCODE_KP_7);
    CHECK(rr_ini_set(L"CPS1.Keyboard.Player2", L"B1", value, ui->ini_file));
    rrhk_bind(board); rrhk_load_bindings();
    CHECK(ui->keys[0][A_ROW] == SDL_SCANCODE_S && ui->keys[0][B_ROW] == SDL_SCANCODE_K && ui->keys[1][A_ROW] == SDL_SCANCODE_KP_7);
    unique_keys();

    /* An adapter that writes two pad columns (every one but CPS-1): players 3 and 4 get player 1's layout, never all A. */
    static const RrhkAction two[] = {
        {"A", L"A", 1, RRHK_FACE, 0, {SDL_SCANCODE_W, SDL_SCANCODE_KP_8}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}},
        {"B", L"B", 2, RRHK_FACE, 0, {SDL_SCANCODE_X, SDL_SCANCODE_KP_9}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}},
        {"Select", L"Select", 4, RRHK_SYSTEM, 0, {SDL_SCANCODE_LSHIFT, SDL_SCANCODE_KP_4}, {SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_BACK}},
        {"Start", L"Start", 8, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_7}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
        {"Up", L"Up", 16, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_KP_5}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}},
        {"Down", L"Down", 32, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_2}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
        {"Left", L"Left", 64, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_1}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
        {"Right", L"Right", 128, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_3}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}}};
    RrhkMachine fixture = *board;
    fixture.actions = two; fixture.action_count = 8; fixture.table_players = 4;
    fixture.up = 4; fixture.down = 5; fixture.left = 6; fixture.right = 7; fixture.start = 3;
    rrhk_bind(&fixture);
    for (int p = 2; p < 4; ++p) for (int a = 0; a < 8; ++a) CHECK(ui->buttons[p][a] == two[a].pad[0]);
    /* Its players 3 and 4 get the kit's keys too: Select is the button player 1 has on Shift. */
    CHECK(ui->keys[2][0] == SDL_SCANCODE_U && ui->keys[2][1] == SDL_SCANCODE_O && ui->keys[2][2] == SDL_SCANCODE_7);
    CHECK(ui->keys[2][3] == SDL_SCANCODE_3 && ui->keys[3][4] == SDL_SCANCODE_G && ui->keys[3][7] == SDL_SCANCODE_H);
    rrhk_bind(board);
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    SDL_SetMainReady();
    if (SDL_Init(SDL_INIT_GAMECONTROLLER) != 0) { fprintf(stderr, "SDL: %s\n", SDL_GetError()); return 2; }
    /* Four identical pads (one GUID): the kit tells them apart by instance, not by identity. */
    for (int pad = 0; pad < 4; ++pad) {
        const int index = SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER, SDL_CONTROLLER_AXIS_MAX, SDL_CONTROLLER_BUTTON_MAX, 0);
        CHECK(index >= 0);
        stick[pad] = index >= 0 ? SDL_JoystickOpen(index) : NULL;
        CHECK(stick[pad] != NULL);
        trigger(pad, SDL_CONTROLLER_AXIS_TRIGGERLEFT, false); trigger(pad, SDL_CONTROLLER_AXIS_TRIGGERRIGHT, false);
    }
    for (int pad = 1; pad < 4; ++pad) {
        char first[40], other[40];
        SDL_JoystickGetGUIDString(SDL_JoystickGetGUID(stick[0]), first, sizeof first);
        SDL_JoystickGetGUIDString(SDL_JoystickGetGUID(stick[pad]), other, sizeof other);
        CHECK(!strcmp(first, other));
    }
    const int status = rr16_sdl_main("Four players", 1);
    CHECK(status == 0);
    CHECK(step == DONE);
    bindings();
    for (int pad = 0; pad < 4; ++pad) if (stick[pad]) SDL_JoystickClose(stick[pad]);
    SDL_Quit();
    printf("%s: %d players, %llu frames, %d failure(s)\n", failures ? "FAIL" : "PASS", RR_CPS1_PLAYERS,
           (unsigned long long)frames, failures);
    return failures ? 1 : 0;
}
