/* Small cached glyph atlas. Menus pause the game; no text work in its CPU path. */
#include "ui.h"
#include "controls.h"
#include "retro_menu.h"
#include "embedded_rom.h"
#include <stdio.h>
#include <string.h>
#define TR(en, fr) controls_text(en, fr)

static int ox, oy, unit;

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
    default: return SDL_GetScancodeName(key);
    }
}

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
    text(r, 14, 15, kind == 4 ? "Retro-Recomp - Light Phaser" : kind == 1 ? TR("Retro-Recomp - Help", "Retro-Recomp - Aide") : kind == 3 ? "Retro-Recomp - Pause" :
        TR("Retro-Recomp - Controls", "Retro-Recomp - Commandes"), 38, 215, 255);
    if (kind == 4) {
        char lines[3][48];
        const char *shape = controls.phaser_shape == PHASER_DOT ? TR("Dot", "Point") : TR("Cross", "Croix");
        const char *color = controls.phaser_color == PHASER_WHITE ? TR("White", "Blanc") :
            controls.phaser_color == PHASER_GREEN ? TR("Pure green", "Vert pur") : TR("Red", "Rouge");
        snprintf(lines[0], sizeof(lines[0]), TR("Shape: %s", "Forme : %s"), shape);
        snprintf(lines[1], sizeof(lines[1]), TR("Size: %d / 5", "Taille : %d / 5"), controls.phaser_dot_size);
        snprintf(lines[2], sizeof(lines[2]), TR("Color: %s", "Couleur : %s"), color);
        for (int i = 0; i < 3; ++i) {
            int y = 34 + i*24;
            box(r, 14, y, 226, 22, i == row ? 40 : 14, i == row ? 63 : 35, i == row ? 81 : 58, 255);
            text(r, 22, y+5, "<", 38, 215, 255); text(r, 48, y+5, lines[i], 233, 239, 247);
            text(r, 224, y+5, ">", 38, 215, 255);
        }
        ui_phaser_reticle(r, ox + 128*unit, oy + 119*unit, unit);
        text(r, 14, 135, TR("Mouse: aim | Left click: trigger", "Souris : viser | Clic gauche : tirer"), 233, 239, 247);
        text(r, 14, 147, TR("Right click: off-screen shot", "Clic droit : tir hors ecran"), 233, 239, 247);
        text(r, 14, 159, TR("Up/Down: row | Left/Right: change", "Haut/Bas : ligne | Gauche/Droite"), 157, 173, 194);
        text(r, 14, 173, TR("F5 / Esc: close | Shared settings", "F5 / Echap : fermer | Reglages communs"), 157, 173, 194);
    } else if (kind == 3) {
        text(r, 14, 62, TR("Game paused", "Jeu en pause"), 233, 239, 247);
        text(r, 14, 90, TR("P / Enter: resume", "P / Entree : reprendre"), 233, 239, 247);
        text(r, 14, 118, TR("F1: restart", "F1 : redemarrer"), 157, 173, 194);
        text(r, 14, 140, TR("Gamepad shortcuts: see F2", "Raccourcis manette : voir F2"), 157, 173, 194);
        text(r, 14, 164, TR("H: help | F2: controls", "H : aide | F2 : commandes"), 157, 173, 194);
    } else if (kind == 1) {
        char autofire[64];
        snprintf(autofire, sizeof(autofire), TR("F6  Gamepad autofire: %s", "F6  Autofire manette : %s"), controls.autofire ? "ON" : "OFF");
        const char *lines[] = {TR("F1  Restart game", "F1  Redemarrer le jeu"), TR("F2  Controls", "F2  Commandes"),
            TR("F3  Next filter", "F3  Changer le filtre"), TR("F4  Window / Pixel / Fit", "F4  Fenetre / Pixels / Ajuste"),
            autofire, "F7  English / Francais",
            TR("F8  Save game state", "F8  Sauvegarder l'etat"), TR("F9  Load game state", "F9  Charger l'etat"),
            TR("P / Enter  Pause", "P / Entree  Pause"),
            TR("Gamepad shortcuts: see F2", "Raccourcis manette : voir F2"),
            TR("Esc  Quit (close menus first)", "Echap  Quitter (fermer les menus)")};
        for (int i = 0; i < (int)(sizeof(lines) / sizeof(lines[0])); ++i)
            text(r, 14, 31 + 12 * i, lines[i], 233, 239, 247);
        if (sms_light_phaser) text(r, 14, 163, TR("Gun: mouse/left click | F5: options", "Gun : souris/clic gauche | F5 : options"), 38, 215, 255);
#ifdef RETRO_GAME_GEAR
        text(r, 14, 163, TR("S / pad Start: cartridge Start", "S / Start manette : Start jeu"), 38, 215, 255);
#endif
        text(r, 14, 174, TR("H / Esc: close help", "H / Echap : fermer l'aide"), 157, 173, 194);
    } else {
#ifdef RETRO_GAME_GEAR
        char heading[64]; snprintf(heading, sizeof(heading), "%s", TR("Game Gear controls", "Commandes Game Gear"));
#else
        char heading[64]; snprintf(heading, sizeof(heading), TR("Player %d  [Left/Right: P1/P2]", "Joueur %d  [Gauche/Droite : J1/J2]"), player + 1);
#endif
        text(r, 14, 30, heading, 233, 239, 247);
#ifdef RETRO_GAME_GEAR
        text(r, 14, 43, gamepad ? TR("Gamepad [Tab:keys]", "Manette [Tab:clavier]") : TR("Keyboard [Tab:gamepad]", "Clavier  [Tab : manette]"), 157, 173, 194);
#else
        text(r, 14, 43, gamepad ? TR("Gamepad [Tab:keys | C:swap]", "Manette [Tab:clavier | C:inverser]") : TR("Keyboard [Tab:gamepad]", "Clavier  [Tab : manette]"), 157, 173, 194);
#endif
        for (int i = 0; i < controls_action_count(player); ++i) {
            if (i == row) box(r, 12, 58 + 12 * i, 232, 12, 40, 63, 81, 255);
            char line[100];
            const char *binding = gamepad ? button_name(controls.buttons[player][i]) : key_name(controls.keys[player][i]);
            snprintf(line, sizeof(line), "%c %-12s %s", i == row ? '>' : ' ', controls_label(i), capture && i == row ? TR("Press...", "Appuie...") : binding);
            text(r, 14, 59 + 12 * i, line, i == row ? 83 : 233, i == row ? 216 : 239, i == row ? 202 : 247);
        }
        const char *hint = gamepad && !name ? TR("No gamepad connected", "Aucune manette connectee") : TR("Enter/A: bind | D: defaults", "Entree/A : changer | D : defauts");
        text(r, 14, 157, status && *status ? status : hint, 233, 239, 247);
        text(r, 14, 171, capture ? TR("Esc: cancel binding", "Echap : annuler l'attribution") :
            sms_light_phaser ? TR("G/F5: gun | Up/Down: select", "G/F5 : gun | Haut/Bas : choisir") :
            TR("Up/Down: select | Esc: close", "Haut/Bas : choisir | Echap : fermer"), 157, 173, 194);
    }
    rr_menu_end(r);
}

void ui_toast(SDL_Renderer *r, const char *message) {
    ui_layout(r, &ox, &oy, &unit);
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND);
    box(r, 8, 173, 240, 14, 19, 27, 42, 235);
    text(r, 13, 175, message, 233, 239, 247);
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_NONE);
}

void ui_status(SDL_Renderer *r, const char *message) {
    ui_layout(r, &ox, &oy, &unit);
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND);
    box(r, 8, 5, 240, 14, 19, 27, 42, 235);
    text(r, 13, 7, message, 255, 209, 110);
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_NONE);
}
