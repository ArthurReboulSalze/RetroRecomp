/* Gamepads unplugged and plugged in while a game runs, through the host kit's real loop (tools/hostkit_players_selftest.py).
 *
 * The same stub CPS-1 machine as checks.c (four players). Four pads of different models (X, Y, Z, W: one GUID each) are SDL
 * virtual game controllers attached and detached from the frame function, so the kit sees SDL's own device events. Plugging
 * a pad back in attaches a new device of the same model: a new instance, as SDL sees the same pad on another USB port.
 * It checks, frame after frame, which pad each player holds and that the pad's buttons reach that player's word:
 *   - an unplugged pad frees its player; a pad plugged in goes to the first free player, so player 1 is filled first,
 *     another pad as well as the same one on another port (the report of 27 November 2026: the game stayed deaf);
 *   - a pad that comes back takes its former player again when that player is free, and leaves player 1 to the next pad;
 *     a new pad does not wait for one that is gone;
 *   - a player pinned to one pad (F2's Gamepad row) whose pad is unplugged is free for another pad (Arthur's Master System
 *     was pinned to his first pad: no other pad reached player 1); the pinned pad takes its player back when it returns,
 *     the stand-in moving to the first free player, also under another GUID of the same model (a new name on another
 *     port, another SDL driver);
 *   - a button binding changed in F2 stays the player's when its pad comes back;
 *   - in a multiplayer session, the local seat (player 1's slot) follows a pad plugged in, and an unplugged seat pad gives
 *     way to another pad still plugged in.
 * No ROM, no visible window, no sound device. Original RetroRecomp code: MIT. */
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
#define CHECK(condition) do { if (!(condition)) { fprintf(stderr, "FAIL %s:%d (step %d): %s\n", __FILE__, __LINE__, step, #condition); ++failures; } } while (0)
static int step;

enum { B1 = 1, B2 = 2, B3 = 4, B4 = 8 };   /* the bits of rrhk_cps1.c */
enum { A_ROW, B_ROW };

#include "cps1_stub.h"

/* ---- the pads: four models, each plugged in at most once at a time ---- */
enum { X, Y, Z, W, X_AGAIN, MODELS, NONE = -1 };
/* X_AGAIN is X under another name (another CRC in its GUID): the same vendor and product, as Windows may name one pad */
static const char *const model_name[MODELS] = {"Pad X", "Pad Y", "Pad Z", "Pad W", "Pad X on another port"};
static SDL_Joystick *handle[MODELS];

static void plug(int k) {
    SDL_VirtualJoystickDesc desc;
    SDL_zero(desc);
    desc.version = SDL_VIRTUAL_JOYSTICK_DESC_VERSION;
    desc.type = SDL_JOYSTICK_TYPE_GAMECONTROLLER;
    desc.naxes = SDL_CONTROLLER_AXIS_MAX; desc.nbuttons = SDL_CONTROLLER_BUTTON_MAX;
    const int model = k == X_AGAIN ? X : k;
    desc.vendor_id = (Uint16)(0x1111 * (model + 1)); desc.product_id = (Uint16)(model + 1);
    desc.name = model_name[k];
    CHECK(!handle[k]);
    const int index = SDL_JoystickAttachVirtualEx(&desc);
    CHECK(index >= 0);
    handle[k] = index >= 0 ? SDL_JoystickOpen(index) : NULL;
    CHECK(handle[k] != NULL);
    if (!handle[k]) return;
    /* a released trigger is -32768 on a virtual axis (checks.c) */
    SDL_JoystickSetVirtualAxis(handle[k], SDL_CONTROLLER_AXIS_TRIGGERLEFT, -32768);
    SDL_JoystickSetVirtualAxis(handle[k], SDL_CONTROLLER_AXIS_TRIGGERRIGHT, -32768);
}

static void unplug(int k) {
    CHECK(handle[k] != NULL);
    if (!handle[k]) return;
    const SDL_JoystickID id = SDL_JoystickInstanceID(handle[k]);
    SDL_JoystickClose(handle[k]);
    handle[k] = NULL;
    for (int i = 0; i < SDL_NumJoysticks(); ++i) if (SDL_JoystickGetDeviceInstanceID(i) == id) { SDL_JoystickDetachVirtual(i); return; }
    CHECK(!"the virtual pad was found");
}

static void press(int k, SDL_GameControllerButton button, bool down) {
    if (handle[k]) CHECK(SDL_JoystickSetVirtualButton(handle[k], button, down ? 1 : 0) == 0);
}

/* The model a player's pad is, NONE without a pad. */
static int held_by(int p) {
    SDL_GameController *pad = rrhk_ui()->pads[p];
    if (!pad) return NONE;
    CHECK(SDL_GameControllerGetAttached(pad));
    const SDL_JoystickID id = SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(pad));
    for (int k = 0; k < MODELS; ++k) if (handle[k] && SDL_JoystickInstanceID(handle[k]) == id) return k;
    CHECK(!"a player holds a pad that is not plugged in");
    return NONE;
}

static bool slots_are(int p1, int p2, int p3, int p4) {
    const int want[4] = {p1, p2, p3, p4};
    bool same = true;
    for (int p = 0; p < 4; ++p) if (held_by(p) != want[p]) same = false;
    if (!same) {
        fprintf(stderr, "  step %d: players hold", step);
        for (int p = 0; p < 4; ++p) fprintf(stderr, " %s", held_by(p) == NONE ? "-" : model_name[held_by(p)]);
        fprintf(stderr, ", expected");
        for (int p = 0; p < 4; ++p) fprintf(stderr, " %s", want[p] == NONE ? "-" : model_name[want[p]]);
        fprintf(stderr, "\n");
    }
    return same;
}

/* The script: each step acts on its first frame, then checks once the kit has seen SDL's events (a few polls later). */
enum {
    FIRST, X_PRESS, X_OUT, Y_IN, Y_PRESS, Y_OTHER_PORT, Y_PRESS_AGAIN, X_BACK, X_PRESS_P2, BOTH_OUT, X_RETURNS, Y_RETURNS,
    Y_OUT_Z_IN, Y_AFTER_Z, PIN_X, X_OUT_PINNED, W_IN_WHILE_PINNED, X_BACK_PINNED, X_RENAMED, X_RENAMED_BACK, UNPIN, REMAP,
    REMAP_X_OUT, REMAP_X_BACK,
    SESSION, DONE
};
static unsigned step_frame;
static void next(void) { ++step; step_frame = 0; }
#define SETTLE 3          /* polls for SDL's device events to reach the kit */

/* In a multiplayer session (rrhk_session_on) only player 1's slot plays: the local seat. Set around a direct deal only, never
 * across a frame of the loop, so the session code itself never runs here. */
static void session_checks(void) {
    /* Z and X are plugged in, Z holds the seat (player 1), X player 2. */
    CHECK(slots_are(Z, X, NONE, NONE));
    rrhk_session_on = true;
    unplug(Z);
    SDL_PumpEvents(); SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
    rrhk_open_pads();
    CHECK(slots_are(X, NONE, NONE, NONE));          /* the seat takes the pad still plugged in */
    plug(Y);
    SDL_PumpEvents(); SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
    rrhk_open_pads();
    CHECK(slots_are(X, Y, NONE, NONE));             /* the seat has a pad: the new one goes on (player 3 was W's) */
    unplug(X);
    SDL_PumpEvents(); SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
    rrhk_open_pads();
    CHECK(slots_are(Y, NONE, NONE, NONE));
    unplug(Y);
    SDL_PumpEvents(); SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
    rrhk_open_pads();
    CHECK(slots_are(NONE, NONE, NONE, NONE));
    plug(W);
    SDL_PumpEvents(); SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
    rrhk_open_pads();
    CHECK(slots_are(W, NONE, NONE, NONE));          /* the seat follows the new pad */
    rrhk_session_on = false;
}

bool rr16_frame(uint16_t p1, uint16_t p2) {
    RrhkUi *ui = rrhk_ui();
    char value[96];
    ++frames; ++step_frame;
    switch (step) {
    case FIRST:                 /* X was plugged in before the window opened */
        CHECK(slots_are(X, NONE, NONE, NONE));
        press(X, SDL_CONTROLLER_BUTTON_A, true);
        next(); break;
    case X_PRESS:
        if (step_frame < SETTLE) break;
        CHECK(p1 == B1);
        press(X, SDL_CONTROLLER_BUTTON_A, false);
        unplug(X);
        next(); break;
    case X_OUT:                 /* player 1 is free again */
        if (step_frame < SETTLE) break;
        CHECK(slots_are(NONE, NONE, NONE, NONE));
        CHECK(p1 == 0);
        plug(Y);
        next(); break;
    case Y_IN:                  /* another pad: player 1 */
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Y, NONE, NONE, NONE));
        press(Y, SDL_CONTROLLER_BUTTON_A, true);
        next(); break;
    case Y_PRESS:
        if (step_frame < SETTLE) break;
        CHECK(p1 == B1);
        press(Y, SDL_CONTROLLER_BUTTON_A, false);
        unplug(Y); plug(Y);     /* the same pad on another USB port: a new device of the same model */
        next(); break;
    case Y_OTHER_PORT:
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Y, NONE, NONE, NONE));
        press(Y, SDL_CONTROLLER_BUTTON_A, true);
        next(); break;
    case Y_PRESS_AGAIN:
        if (step_frame < SETTLE) break;
        CHECK(p1 == B1);
        press(Y, SDL_CONTROLLER_BUTTON_A, false);
        plug(X);                /* X comes back: its player 1 is Y's now, X takes the first free player */
        next(); break;
    case X_BACK:
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Y, X, NONE, NONE));
        press(X, SDL_CONTROLLER_BUTTON_B, true);
        next(); break;
    case X_PRESS_P2:
        if (step_frame < SETTLE) break;
        CHECK(p1 == 0 && p2 == B2);
        press(X, SDL_CONTROLLER_BUTTON_B, false);
        unplug(X); unplug(Y);
        next(); break;
    case BOTH_OUT:
        if (step_frame < SETTLE) break;
        CHECK(slots_are(NONE, NONE, NONE, NONE));
        plug(X);                /* X first: its player 2 is free, it takes it back and leaves player 1 to Y */
        next(); break;
    case X_RETURNS:
        if (step_frame < SETTLE) break;
        CHECK(slots_are(NONE, X, NONE, NONE));
        plug(Y);
        next(); break;
    case Y_RETURNS:
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Y, X, NONE, NONE));
        unplug(Y); plug(Z);     /* a new pad does not wait for Y: player 1 */
        next(); break;
    case Y_OUT_Z_IN:
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Z, X, NONE, NONE));
        plug(Y);                /* Y's player 1 is taken: the first free one */
        next(); break;
    case Y_AFTER_Z:
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Z, X, Y, NONE));
        unplug(Y);
        next(); break;
    case PIN_X:                 /* F2's Gamepad row: player 2 pinned to X (Enter goes through the plugged pads) */
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Z, X, NONE, NONE));
        for (int tries = 0; tries < 6; ++tries) {
            rrhk_pad_next(1);
            rrhk_pad_value(value, sizeof value, 1);
            if (!strcmp(value, "Pad X")) break;
        }
        CHECK(!strcmp(value, "Pad X"));
        CHECK(slots_are(Z, X, NONE, NONE));
        unplug(X);
        next(); break;
    case X_OUT_PINNED:
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Z, NONE, NONE, NONE));
        rrhk_pad_value(value, sizeof value, 1);
        CHECK(strstr(value, "Pad X") != NULL);          /* "Pad X (disconnected)" */
        plug(W);
        next(); break;
    case W_IN_WHILE_PINNED:     /* the pinned player is free: W takes it (player 1 first: player 2 is the first free one) */
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Z, W, NONE, NONE));
        rrhk_pad_value(value, sizeof value, 1);
        CHECK(strstr(value, "Pad W") == value && strstr(value, "Pad X") != NULL);   /* "Pad W (in place of Pad X)" */
        plug(X);
        next(); break;
    case X_BACK_PINNED:         /* X takes its pinned player back; W, the stand-in, goes to the first free player */
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Z, X, W, NONE));
        rrhk_pad_value(value, sizeof value, 1);
        CHECK(!strcmp(value, "Pad X"));
        unplug(W); unplug(X); plug(X_AGAIN);
        next(); break;
    case X_RENAMED:             /* the same model under another name still has its pin */
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Z, X_AGAIN, NONE, NONE));
        unplug(X_AGAIN);
        next(); break;
    case X_RENAMED_BACK:
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Z, NONE, NONE, NONE));
        rrhk_pad_automatic(1);
        plug(X);
        next(); break;
    case UNPIN:                 /* automatic again: X comes back to the player it left */
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Z, X, NONE, NONE));
        /* F2: player 2's button 1 moved to B (the swap puts A on button 2) */
        rrhk_assign(1, A_ROW, true, SDL_CONTROLLER_BUTTON_B);
        CHECK(ui->buttons[1][A_ROW] == SDL_CONTROLLER_BUTTON_B && ui->buttons[1][B_ROW] == SDL_CONTROLLER_BUTTON_A);
        next(); break;
    case REMAP:
        unplug(X);
        next(); break;
    case REMAP_X_OUT:
        if (step_frame < SETTLE) break;
        CHECK(slots_are(Z, NONE, NONE, NONE));
        plug(X);
        next(); break;
    case REMAP_X_BACK:          /* X is player 2 again, with player 2's binding */
        if (step_frame == SETTLE) {
            CHECK(slots_are(Z, X, NONE, NONE));
            CHECK(ui->buttons[1][A_ROW] == SDL_CONTROLLER_BUTTON_B);
            press(X, SDL_CONTROLLER_BUTTON_B, true);
        }
        if (step_frame < 2 * SETTLE) break;
        CHECK(p2 == B1);
        press(X, SDL_CONTROLLER_BUTTON_B, false);
        next(); break;
    case SESSION:
        if (step_frame < SETTLE) break;
        session_checks();
        next(); break;
    default:
        return false;    /* the machine asks to stop: rrhk_main returns */
    }
    return true;
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    SDL_SetMainReady();
    if (SDL_Init(SDL_INIT_GAMECONTROLLER) != 0) { fprintf(stderr, "SDL: %s\n", SDL_GetError()); return 2; }
    plug(X);
    const int status = rr16_sdl_main("Hot plug", 1);
    CHECK(status == 0);
    CHECK(step == DONE);
    for (int k = 0; k < MODELS; ++k) if (handle[k]) SDL_JoystickClose(handle[k]);
    SDL_Quit();
    printf("%s: hot plug, %llu frames, %d failure(s)\n", failures ? "FAIL" : "PASS", (unsigned long long)frames, failures);
    return failures ? 1 : 0;
}
