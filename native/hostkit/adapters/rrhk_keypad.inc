/* The on-screen keypad of a gamepad player (host kit, 21 Nov 2026): a machine whose controller has a keypad (the ColecoVision's
 * twelve keys 0-9 * #; later the Atari 5200's, the Intellivision's) lets a player with a gamepad open a small grid over the
 * picture, move on it with the D-pad and press a key with A, while the game keeps running. Original Retro-Recomp code, MIT.
 *
 * Nothing here is the shell's: an adapter includes this file and calls it from hooks the shell already calls, so no other
 * machine's host stamp moves (the lead's condition, 21 Nov 2026).
 *   - RrhkMachine.event        -> rrhk_keypad_event   (the open row's press, then the D-pad, A and B while it is open)
 *   - RrhkMachine.action_held  -> rrhk_keypad_held    (what the keypad holds goes into the player's pad word)
 *   - RrhkMachine.before_present -> rrhk_keypad_draw  (drawn on the menu canvas, never into the machine's picture)
 *   - RrhkMachine.reset and the quick-state load       -> rrhk_keypad_close
 *
 * What reaches the game is the pad word only, so rollback, the digest and a multiplayer session need nothing more:
 *   - each key is an ordinary action row of the machine (bindable on the keyboard pages of F2 like any other) whose `bit` is the
 *     key's code (a multi-bit mask: the shell ORs `bit` into the word, so two keys held merge, as on the real keypad's lines);
 *   - the open row is an action row too (gamepad Y by default, never Back: Start+Back is Restart and R3+Back the chat); its
 *     `bit` is a flag the keypad holds while it is open and, after it closes, until every button of that pad is released. The
 *     machine's own input mapping takes the flag as « this pad's stick and fire buttons are not the game's » (the D-pad moves
 *     on the grid, A presses the key): a pure function of the word, the same on every seat.
 * The keypad closes on any menu, the Pause, a pause asked by another seat, the multiplayer chat, a restart and a quick-state
 * load; in a session whose controls are taken in turns, a seat that does not hold them cannot open it. Autofire never pulses a
 * keypad key (the keys are SYSTEM rows; A's own bit is masked by the flag).
 * Its two texts (title, hint) are in the five game languages in this file, read with rrhk_text (rrhk_text.h): native/runtime_catalog.inc
 * is a host file of every machine, and adding them there would move every machine's host stamp. They join the catalogue the next time
 * it moves. */
#include "hostkit/hostkit.h"
#include "hostkit/hostkit_internal.h"      /* rrhk_chat_open, rrhk_session_paused: read only, never changed by this file */
#include "hostkit/hostkit_session.h"
#include "hostkit/adapters/rrhk_text.h"
#include "retro_menu.h"
#include "runtime_i18n.h"
#include <string.h>

#define RRHK_KEYPAD_MAX_CELLS 16

/* What the machine declares (one, static). */
typedef struct {
    int rows, columns;                      /* 4 x 3 for the ColecoVision; rows x columns <= RRHK_KEYPAD_MAX_CELLS */
    const char *const *labels;              /* one per cell, row by row, as printed on the controller ("1" .. "#") */
    const int *actions;                     /* one per cell: the machine's action row that key presses */
    int open_action;                        /* the row that opens and closes it; its bit is the flag */
} RrhkKeypad;

static struct {
    bool open;                              /* the grid is shown and the D-pad, A and B are its own */
    bool release;                           /* closed, but a button of that pad is still held from then: the flag stays */
    int row, column;
    int pressed;                            /* the cell A holds down, -1: none */
} rrhk_keypad_state[RRHK_MAX_PLAYERS];

/* The keypad's texts in the five game languages (rrhk_text.h: en, fr, it, es, de; ASCII, as the catalogue writes them). */
static const RrhkText rrhk_keypad_title = {"Keypad", "Pave numerique", "Tastierino", "Teclado numerico", "Tastenfeld"};
static const RrhkText rrhk_keypad_hint = {"A: press | B: close", "A : appuyer | B : fermer", "A: premi | B: chiudi",
                                          "A: pulsar | B: cerrar", "A: druecken | B: schliessen"};

/* The player whose gamepad sent the event, -1: none of the machine's players. */
static int rrhk_keypad_player(SDL_JoystickID which) {
    RrhkUi *ui = rrhk_ui();
    for (int p = 0; p < RRHK_MAX_PLAYERS; ++p)
        if (ui->pads[p] && SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(ui->pads[p])) == which) return p;
    return -1;
}

/* Every button and trigger of player p's pad is up. The same rule as the chat's chat_anything_held (rrhk_chat.inc), for one
 * player's pad instead of player 1's and the keyboard: the shell's copy is static, and sharing it would move every host stamp;
 * both become one the next time the shell moves. */
static bool rrhk_keypad_pad_released(int p) {
    SDL_GameController *pad = rrhk_ui()->pads[p];
    if (!pad) return true;
    for (int b = 0; b < SDL_CONTROLLER_BUTTON_MAX; ++b) if (SDL_GameControllerGetButton(pad, (SDL_GameControllerButton)b)) return false;
    return SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_TRIGGERLEFT) < 8000 &&
           SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_TRIGGERRIGHT) < 8000;
}

static void rrhk_keypad_close_player(int p) {
    if (rrhk_keypad_state[p].open) rrhk_keypad_state[p].release = true;
    rrhk_keypad_state[p].open = false;
    rrhk_keypad_state[p].pressed = -1;
}
/* Every player's keypad closes (a restart, a quick-state load; the menus, the Pause and the chat are seen by rrhk_keypad_draw). */
static void rrhk_keypad_close(void) {
    for (int p = 0; p < RRHK_MAX_PLAYERS; ++p) rrhk_keypad_close_player(p);
}
static bool rrhk_keypad_any_open(void) {
    for (int p = 0; p < RRHK_MAX_PLAYERS; ++p) if (rrhk_keypad_state[p].open) return true;
    return false;
}

/* The players who may hold a keypad on this PC: in a session only this PC's seat, as player 1's pad, and not while another
 * seat holds the controls taken in turns. */
static bool rrhk_keypad_may_open(int p) {
    if (p >= 2 || !rrhk_ui()->pads[p]) return false;   /* two grids at most; a keyboard player has the keys themselves */
    if (!rrhk_session_active()) return true;
    if (p != 0) return false;
    if (rrhk_session_sharing() == RRHK_SHARING_TURNS && rrhk_session_holder() != rrhk_session_seat()) {
        rrhk_notice(rr_tr("It is not your turn"), 1800);
        return false;
    }
    return true;
}

/* From the machine's `event` hook, before its own handling: true when the keypad took the event. */
static bool rrhk_keypad_event(const RrhkKeypad *keypad, const SDL_Event *event) {
    const unsigned players = rrhk_action_pressed(event, keypad->open_action);      /* 0 in a menu or a capture */
    if (players) {
        for (int p = 0; p < RRHK_MAX_PLAYERS; ++p) {
            if (!(players & (1u << p))) continue;
            if (rrhk_keypad_state[p].open) rrhk_keypad_close_player(p);
            else if (rrhk_keypad_may_open(p)) {
                rrhk_keypad_state[p].open = true;
                rrhk_keypad_state[p].pressed = -1;
            }
        }
        return true;
    }
    if (event->type != SDL_CONTROLLERBUTTONDOWN && event->type != SDL_CONTROLLERBUTTONUP) return false;
    const int p = rrhk_keypad_player(event->cbutton.which);
    if (p < 0 || !rrhk_keypad_state[p].open) return false;
    const bool down = event->type == SDL_CONTROLLERBUTTONDOWN;
    switch (event->cbutton.button) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: case SDL_CONTROLLER_BUTTON_DPAD_DOWN:
        if (down) {
            const int step = event->cbutton.button == SDL_CONTROLLER_BUTTON_DPAD_DOWN ? 1 : -1;
            rrhk_keypad_state[p].row = (rrhk_keypad_state[p].row + step + keypad->rows) % keypad->rows;
        }
        return true;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: case SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
        if (down) {
            const int step = event->cbutton.button == SDL_CONTROLLER_BUTTON_DPAD_RIGHT ? 1 : -1;
            rrhk_keypad_state[p].column = (rrhk_keypad_state[p].column + step + keypad->columns) % keypad->columns;
        }
        return true;
    case SDL_CONTROLLER_BUTTON_A:
        /* held while A is held, as a finger on the key; the selection may not move under it */
        rrhk_keypad_state[p].pressed = down ? rrhk_keypad_state[p].row * keypad->columns + rrhk_keypad_state[p].column : -1;
        return true;
    case SDL_CONTROLLER_BUTTON_B:
        if (down) rrhk_keypad_close_player(p);
        return true;
    default:
        return false;                       /* Start, Guide and the rest keep the kit's roles (and a menu closes the keypad) */
    }
}

/* From the machine's `action_held` hook: the keypad holds the open row's flag (open, or closed and not yet all released) and
 * the key A holds down. */
static bool rrhk_keypad_held(const RrhkKeypad *keypad, int player, int action) {
    if (player < 0 || player >= RRHK_MAX_PLAYERS) return false;
    if (!rrhk_keypad_state[player].open) {
        if (!rrhk_keypad_state[player].release) return false;
        if (rrhk_keypad_pad_released(player)) { rrhk_keypad_state[player].release = false; return false; }
    }
    if (action == keypad->open_action) return true;
    const int cell = rrhk_keypad_state[player].pressed;
    return rrhk_keypad_state[player].open && cell >= 0 && cell < keypad->rows * keypad->columns && keypad->actions[cell] == action;
}

/* The grid of one player: player 1's at the right of the picture (the chat's lines are at the left), player 2's at the left;
 * between the chat's top lines and the shell's notice line (172). Menu units, the 256 x 192 canvas. */
#define RRHK_KEYPAD_CELL_W 18
#define RRHK_KEYPAD_CELL_H 12
#define RRHK_KEYPAD_STEP_X 20
#define RRHK_KEYPAD_STEP_Y 14
#define RRHK_KEYPAD_PANEL_W 92
#define RRHK_KEYPAD_TOP 44
static void rrhk_keypad_draw_player(SDL_Renderer *ren, const RrhkKeypad *keypad, int p, int ox, int oy, int unit, bool numbered) {
    const int grid_w = keypad->columns * RRHK_KEYPAD_STEP_X - (RRHK_KEYPAD_STEP_X - RRHK_KEYPAD_CELL_W);
    const int panel_h = 32 + keypad->rows * RRHK_KEYPAD_STEP_Y;
    const int left = p == 0 ? 256 - 6 - RRHK_KEYPAD_PANEL_W : 6, top = RRHK_KEYPAD_TOP;
    rr_menu_box(ren, ox, oy, unit, left, top, RRHK_KEYPAD_PANEL_W, panel_h, RR_MENU_PANEL_RGB, 235);
    rr_menu_box(ren, ox, oy, unit, left, top, RRHK_KEYPAD_PANEL_W, 1, RR_MENU_GOLD, 255);
    char title[48];
    if (numbered) snprintf(title, sizeof title, "%s %d", rrhk_text(&rrhk_keypad_title), p + 1);
    else snprintf(title, sizeof title, "%s", rrhk_text(&rrhk_keypad_title));
    int width = rr_menu_text_width(title);
    if (width > RRHK_KEYPAD_PANEL_W - 8) width = RRHK_KEYPAD_PANEL_W - 8;
    rr_menu_text_plain(ren, ox, oy, unit, left + (RRHK_KEYPAD_PANEL_W - width) / 2, top + 3, width, title, RR_MENU_GOLD);
    const int grid_left = left + (RRHK_KEYPAD_PANEL_W - grid_w) / 2, grid_top = top + 16;
    for (int row = 0; row < keypad->rows; ++row) for (int column = 0; column < keypad->columns; ++column) {
        const int cell = row * keypad->columns + column;
        const int x = grid_left + column * RRHK_KEYPAD_STEP_X, y = grid_top + row * RRHK_KEYPAD_STEP_Y;
        const bool selected = row == rrhk_keypad_state[p].row && column == rrhk_keypad_state[p].column;
        const bool pressed = rrhk_keypad_state[p].pressed == cell;
        if (pressed) {
            rr_menu_box(ren, ox, oy, unit, x - 1, y - 1, RRHK_KEYPAD_CELL_W + 2, RRHK_KEYPAD_CELL_H + 2, RR_MENU_ACCENT, 255);
            rr_menu_box(ren, ox, oy, unit, x, y, RRHK_KEYPAD_CELL_W, RRHK_KEYPAD_CELL_H, RR_MENU_GOLD, 255);
        } else if (selected) {
            rr_menu_box(ren, ox, oy, unit, x - 1, y - 1, RRHK_KEYPAD_CELL_W + 2, RRHK_KEYPAD_CELL_H + 2, RR_MENU_GOLD, 255);
            rr_menu_box(ren, ox, oy, unit, x, y, RRHK_KEYPAD_CELL_W, RRHK_KEYPAD_CELL_H, RR_MENU_SELECT, 255);
        } else rr_menu_box(ren, ox, oy, unit, x, y, RRHK_KEYPAD_CELL_W, RRHK_KEYPAD_CELL_H, 34, 30, 22, 255);
        const char *label = keypad->labels[cell];
        int label_w = rr_menu_text_width(label);
        if (label_w > RRHK_KEYPAD_CELL_W - 2) label_w = RRHK_KEYPAD_CELL_W - 2;
        const int label_x = x + (RRHK_KEYPAD_CELL_W - label_w) / 2;
        if (pressed) rr_menu_text_plain(ren, ox, oy, unit, label_x, y + 1, label_w, label, 34, 30, 22);   /* dark on gold */
        else if (selected) rr_menu_text_plain(ren, ox, oy, unit, label_x, y + 1, label_w, label, RR_MENU_ACCENT);
        else rr_menu_text_plain(ren, ox, oy, unit, label_x, y + 1, label_w, label, RR_MENU_GOLD);
    }
    rr_menu_hints(ren, ox, oy, unit, left + 4, top + panel_h - 13, RRHK_KEYPAD_PANEL_W - 8, rrhk_text(&rrhk_keypad_hint),
                  RR_MENU_HINT);
}

/* From the machine's `before_present` hook, every presented frame (menus included): a menu, the Pause, a pause asked by
 * another seat or the chat closes every keypad; otherwise the open ones are drawn. */
static void rrhk_keypad_draw(const RrhkKeypad *keypad, SDL_Renderer *ren) {
    RrhkUi *ui = rrhk_ui();
    if (!rrhk_keypad_any_open()) return;
    if (ui->menu || ui->paused || ui->capturing || (rrhk_session_active() && (rrhk_session_paused() || rrhk_chat_open()))) {
        rrhk_keypad_close();
        return;
    }
    int ox, oy, unit;
    rr_menu_layout(ren, &ox, &oy, &unit);
    SDL_SetRenderDrawBlendMode(ren, SDL_BLENDMODE_BLEND);
    /* « Keypad 1 » / « Keypad 2 » when two pads play on this PC, so that each player knows theirs */
    const bool numbered = !rrhk_session_active() && ui->pads[0] && ui->pads[1];
    for (int p = 0; p < RRHK_MAX_PLAYERS && p < 2; ++p)
        if (rrhk_keypad_state[p].open) rrhk_keypad_draw_player(ren, keypad, p, ox, oy, unit, numbered);
    SDL_SetRenderDrawBlendMode(ren, SDL_BLENDMODE_NONE);
}
