/* Small cached glyph atlas. Menus pause the game; no text work in its CPU path. */
#include "ui.h"
#include "controls.h"
#include "retro_menu.h"
#include "runtime_feedback.h"
#include "retro_keyboard.h"
#include "embedded_rom.h"
#include <stdio.h>
#include <string.h>
#define TR(en, fr) controls_text(en, fr)

static int ox, oy, unit, page_index, page_count;
static int combo_count;
static const char *const *combo_labels, *const *combo_values;
static const char *combo_hint;

static const char *button_name(SDL_GameControllerButton button) {
    switch (button) {
    case SDL_CONTROLLER_BUTTON_INVALID: return TR("Unassigned", "Non attribue");
    case SDL_CONTROLLER_BUTTON_START: return "Start / Menu";
    case SDL_CONTROLLER_BUTTON_BACK: return "Select / Back";
    case SDL_CONTROLLER_BUTTON_A: return "A";
    case SDL_CONTROLLER_BUTTON_B: return "B";
    case SDL_CONTROLLER_BUTTON_X: return "X";
    case SDL_CONTROLLER_BUTTON_Y: return "Y";
    case SDL_CONTROLLER_BUTTON_DPAD_UP: return TR("D-pad up", "Croix haut");
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: return TR("D-pad down", "Croix bas");
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: return TR("D-pad left", "Croix gauche");
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: return TR("D-pad right", "Croix droite");
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: return "LB";
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: return "RB";
    case SDL_CONTROLLER_BUTTON_LEFTSTICK: return TR("Left stick click", "Clic stick gauche");
    case SDL_CONTROLLER_BUTTON_RIGHTSTICK: return TR("Right stick click", "Clic stick droit");
    default: return SDL_GameControllerGetStringForButton(button);
    }
}

static const char *key_name(SDL_Scancode key) {
    switch (key) {
    case SDL_SCANCODE_UNKNOWN: return TR("Unassigned", "Non attribue");
    case SDL_SCANCODE_RETURN: return TR("Enter", "Entree");
    case SDL_SCANCODE_KP_ENTER: return TR("Num Enter", "Num Entree");
    case SDL_SCANCODE_UP: return TR("Up arrow", "Fleche haut");
    case SDL_SCANCODE_DOWN: return TR("Down arrow", "Fleche bas");
    case SDL_SCANCODE_LEFT: return TR("Left arrow", "Fleche gauche");
    case SDL_SCANCODE_RIGHT: return TR("Right arrow", "Fleche droite");
    case SDL_SCANCODE_KP_1: return "Num 1";
    case SDL_SCANCODE_KP_2: return "Num 2";
    case SDL_SCANCODE_KP_3: return "Num 3";
    case SDL_SCANCODE_KP_4: return "Num 4";
    case SDL_SCANCODE_KP_5: return "Num 5";
    case SDL_SCANCODE_KP_7: return "Num 7";
    case SDL_SCANCODE_KP_8: return "Num 8";
    case SDL_SCANCODE_KP_9: return "Num 9";
    default: return rr_keyboard_name(key);
    }
}

void ui_pages(int page, int count) { page_index = page; page_count = count; }
void ui_combos(int count, const char *const *labels, const char *const *values, const char *hint) {
    combo_count = count; combo_labels = labels; combo_values = values; combo_hint = hint;
}
int ui_rows_top(bool gamepad) { (void)gamepad; return RR_MENU_FIRST_LINE; }

bool ui_init(SDL_Renderer *renderer) {
    return rr_menu_init(renderer);
}

void ui_shutdown(void) { rr_menu_shutdown(); }

void ui_layout(SDL_Renderer *renderer, int *x, int *y, int *scale) {
    rr_menu_layout(renderer, x, y, scale);
}

static void box(SDL_Renderer *r, int x, int y, int w, int h, int red, int green, int blue, int alpha) {
    rr_menu_box(r, ox, oy, unit, x, y, w, h, red, green, blue, alpha);
}

static void text(SDL_Renderer *r, int x, int y, const char *s, int red, int green, int blue) {
    rr_menu_text(r, ox, oy, unit, x, y, s, red, green, blue);
}

/* Both the preview and in-game reticle use the same console pixel grid.
 * A cross has one-pixel strokes, with each arm `size` pixels long. */
void ui_phaser_reticle(SDL_Renderer *r, int x, int y, int scale) {
    int size = controls.phaser_dot_size;
    int color = controls.phaser_color;
    SDL_SetRenderDrawColor(r, color == PHASER_GREEN ? 0 : 255,
        color == PHASER_RED ? 0 : 255, color == PHASER_WHITE ? 255 : 0, 255);
    if (controls.phaser_shape == PHASER_CROSS) {
        SDL_Rect horizontal = {x - size*scale, y, (size*2+1)*scale, scale};
        SDL_Rect vertical = {x, y - size*scale, scale, (size*2+1)*scale};
        SDL_RenderFillRect(r, &horizontal); SDL_RenderFillRect(r, &vertical);
    } else {
        SDL_Rect dot = {x - (size/2)*scale, y - (size/2)*scale, size*scale, size*scale};
        SDL_RenderFillRect(r, &dot);
    }
}

void ui_menu(SDL_Renderer *r, int kind, int player, int row, bool gamepad, bool capture, const char *name, const char *status) {
    ui_layout(r, &ox, &oy, &unit);
    rr_menu_begin(r, ox, oy, unit);
    if (kind == 4) rr_menu_page_header(r, ox, oy, unit, TR("Retro-Recomp - Gun", "Retro-Recomp - Pistolet"), page_index, page_count);
    else if (kind != 2) text(r, 14, RR_MENU_TITLE_LINE, kind == 1 ? TR("Retro-Recomp - Help", "Retro-Recomp - Aide") : "Retro-Recomp - Pause", RR_MENU_ACCENT);
    if (kind == 4) {
        char lines[3][48];
        const char *shape = controls.phaser_shape == PHASER_DOT ? TR("Dot", "Point") : TR("Cross", "Croix");
        const char *color = controls.phaser_color == PHASER_WHITE ? TR("White", "Blanc") :
            controls.phaser_color == PHASER_GREEN ? TR("Pure green", "Vert pur") : TR("Red", "Rouge");
        snprintf(lines[0], sizeof(lines[0]), TR("Shape: %s", "Forme : %s"), shape);
        snprintf(lines[1], sizeof(lines[1]), TR("Size: %d / 5", "Taille : %d / 5"), controls.phaser_dot_size);
        snprintf(lines[2], sizeof(lines[2]), TR("Color: %s", "Couleur : %s"), color);
        text(r, 14, 26, "Light Phaser", RR_MENU_ACCENT);
        /* Clicking the left part steps back; elsewhere steps forward. */
        for (int i = 0; i < 3; ++i) {
            int y = 40 + i*22;
            box(r, 14, y, 226, 20, i == row ? 40 : 14, i == row ? 63 : 35, i == row ? 81 : 58, 255);
            text(r, 22, y+5, "-", RR_MENU_ACCENT); text(r, 48, y+5, lines[i], RR_MENU_GOLD);
            text(r, 224, y+5, "+", RR_MENU_ACCENT);
        }
        ui_phaser_reticle(r, ox + 128*unit, oy + 119*unit, unit);
        text(r, 14, 134, TR("Mouse: aim | Left click: trigger", "Souris : viser | Clic gauche : tirer"), RR_MENU_GOLD);
        text(r, 14, 144, TR("Right click: off-screen shot", "Clic droit : tir hors ecran"), RR_MENU_GOLD);
        text(r, 14, RR_MENU_HINT_LINE, TR("Enter / A / +: next | -: previous", "Entree / A / + : suivant | - : precedent"), RR_MENU_HINT);
        text(r, 14, RR_MENU_LAST_LINE, TR("Left/Right: page | Esc: close", "Gauche/Droite : page | Echap : fermer"), RR_MENU_HINT);
    } else if (kind == 3) {
        text(r, 14, 62, TR("Game paused", "Jeu en pause"), RR_MENU_GOLD);
#ifdef RETRO_GAME_GEAR
        text(r, 14, 90, TR("P / Enter: resume", "P / Entree : reprendre"), RR_MENU_GOLD);
#else
        text(r, 14, 90, TR("Enter: resume", "Entree : reprendre"), RR_MENU_GOLD);
#endif
        text(r, 14, 118, TR("Shift+F1: restart", "Maj+F1 : redemarrer"), RR_MENU_HINT);
        char sprites[64];
        snprintf(sprites, sizeof(sprites), TR("F5 Sprite flicker reduction: %s", "F5 Reduction scintillement : %s"),
            controls.reduce_sprite_flicker ? "ON" : "OFF");
        text(r, 14, 140, sprites, RR_MENU_HINT);
#ifdef RETRO_GAME_GEAR
        text(r, 14, 152, TR("Gamepad shortcuts: see F2", "Raccourcis manette : voir F2"), RR_MENU_HINT);
#endif
        text(r, 14, 164, TR("F1: help | F2: controls & options", "F1 : aide | F2 : commandes et options"), RR_MENU_HINT);
    } else if (kind == 1) {
        char autofire[64];
        snprintf(autofire, sizeof(autofire), TR("F6  Autofire: %s", "F6  Tir auto : %s"), TR(controls.autofire ? "ON" : "OFF", controls.autofire ? "OUI" : "NON"));
        const char *lines[] = {TR("F1  Help | Shift+F1 Restart", "F1  Aide | Maj+F1 Redemarrer"),
            TR("F2  Controls & options", "F2  Commandes et options"),
            TR("F3  Next filter", "F3  Changer le filtre"), TR("F4  Window / Pixel / Fit", "F4  Fenetre / Pixels / Ajuste"),
            TR("F5  Reduce sprite flicker", "F5  Reduire le scintillement"),
            autofire, "F7  Next language",
            TR("F8  Save game state", "F8  Sauvegarder l'etat"), TR("F9  Load game state", "F9  Charger l'etat"),
            rr_feedback_label(),
#ifdef RETRO_GAME_GEAR
            TR("P / Enter  Pause", "P / Entree  Pause"),
#else
            TR("Enter  Pause", "Entree  Pause"),
#endif
            TR("Esc  Quit (close menus first)", "Echap  Quitter (fermer les menus)")};
        /* One line per function key, then the console's own controls. */
        for (int i = 0; i < (int)(sizeof(lines) / sizeof(lines[0])); ++i)
            text(r, 14, RR_MENU_FIRST_LINE + RR_MENU_LINE * i, lines[i], RR_MENU_GOLD);
        if (sms_light_phaser) text(r, 14, RR_MENU_HINT_LINE, TR("Gun: mouse/left click", "Gun : souris/clic gauche"), RR_MENU_ACCENT);
#ifdef RETRO_GAME_GEAR
        text(r, 14, RR_MENU_HINT_LINE, TR("S / pad Start: cartridge Start", "S / Start manette : Start jeu"), RR_MENU_ACCENT);
#endif
        text(r, 14, RR_MENU_LAST_LINE, TR("F1 / Esc: close", "F1 / Echap : fermer"), RR_MENU_HINT);
        rr_menu_build_footer(r, ox, oy, unit);
    } else {
        char heading[64];
#ifdef RETRO_GAME_GEAR
        (void)player;
        snprintf(heading, sizeof(heading), "%s", gamepad ? TR("Gamepad", "Manette") : TR("Keyboard", "Clavier"));
#else
        snprintf(heading, sizeof(heading), gamepad ? TR("Player %d - Gamepad", "Joueur %d - Manette") :
            TR("Player %d - Keyboard", "Joueur %d - Clavier"), player + 1);
#endif
        rr_menu_page_header(r, ox, oy, unit, heading, page_index, page_count);
#ifndef RETRO_GAME_GEAR
        if (gamepad) text(r, 14, 144, TR("C: swap P1/P2 controllers", "C : inverser les manettes J1/J2"), RR_MENU_HINT);
#endif
        /* Every control fits on the page; player 1's pages end with the quit
         * and restart combinations. */
        int actions = controls_action_count(player), top = ui_rows_top(gamepad);
        for (int i = 0; i < actions + combo_count; ++i) {
            if (i == row) box(r, 12, top + RR_MENU_LINE * i, 232, RR_MENU_LINE, RR_MENU_SELECT, 255);
            char line[120];
            if (i < actions) {
                const char *binding = gamepad ? button_name(controls.buttons[player][i]) : key_name(controls.keys[player][i]);
                snprintf(line, sizeof(line), "%c %-12s %s", i == row ? '>' : ' ', controls_label(i), capture && i == row ? TR("Press...", "Appuie...") : rr_tr(binding));
            } else snprintf(line, sizeof(line), "%c %-12s %s", i == row ? '>' : ' ', combo_labels[i - actions], combo_values[i - actions]);
            text(r, 14, top + RR_MENU_LINE * i, line, i == row ? 83 : 233, i == row ? 216 : 239, i == row ? 202 : 247);
        }
        const char *hint = row >= actions && combo_hint ? combo_hint : gamepad && !name ? TR("No gamepad connected", "Aucune manette connectee") : TR("Enter/A: bind | D: defaults", "Entree/A : changer | D : defauts");
        text(r, 14, RR_MENU_HINT_LINE, status && *status ? status : hint, RR_MENU_GOLD);
        text(r, 14, RR_MENU_LAST_LINE, capture ? TR("Esc: cancel binding", "Echap : annuler l'attribution") :
            TR("Left/Right: page | Esc: close", "Gauche/Droite : page | Echap : fermer"), RR_MENU_HINT);
    }
    combo_count = 0; combo_hint = NULL; /* set again before each ui_menu */
    rr_menu_end(r);
}

void ui_toast(SDL_Renderer *r, const char *message) {
    ui_layout(r, &ox, &oy, &unit);
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND);
    box(r, 8, 173, 240, 14, RR_MENU_PANEL_RGB, 235);
    text(r, 13, 175, message, RR_MENU_GOLD);
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_NONE);
}

void ui_status(SDL_Renderer *r, const char *message) {
    ui_layout(r, &ox, &oy, &unit);
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND);
    box(r, 8, 5, 240, 14, RR_MENU_PANEL_RGB, 235);
    text(r, 13, 7, message, RR_MENU_ACCENT);
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_NONE);
}
