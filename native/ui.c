/* Small cached glyph atlas. Menus pause the game; no text work in its CPU path. */
#include "ui.h"
#include "controls.h"
#include <windows.h>
#include <stdio.h>
#include <string.h>
#define TR(en, fr) controls_text(en, fr)

static SDL_Texture *font;
static int ox, oy, unit;
enum { GW = 6, GH = 12, ATLAS_W = 96, ATLAS_H = 72 };

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
    HDC dc = CreateCompatibleDC(NULL);
    BITMAPINFO bi; memset(&bi, 0, sizeof(bi));
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth = ATLAS_W; bi.bmiHeader.biHeight = -ATLAS_H;
    bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 32; bi.bmiHeader.biCompression = BI_RGB;
    uint32_t *pixels = NULL;
    HBITMAP bitmap = CreateDIBSection(dc, &bi, DIB_RGB_COLORS, (void **)&pixels, NULL, 0);
    HFONT face = CreateFontW(-10, 6, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, ANSI_CHARSET,
        OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, NONANTIALIASED_QUALITY, FIXED_PITCH, L"Consolas");
    if (!dc || !bitmap || !face) {
        if (face) DeleteObject(face); if (bitmap) DeleteObject(bitmap); if (dc) DeleteDC(dc);
        return false;
    }
    HGDIOBJ old_bitmap = SelectObject(dc, bitmap), old_font = SelectObject(dc, face);
    memset(pixels, 0, ATLAS_W * ATLAS_H * 4);
    SetTextColor(dc, RGB(255,255,255)); SetBkMode(dc, TRANSPARENT);
    for (int c = 32; c < 128; ++c) {
        char letter = (char)c;
        int x = ((c - 32) % 16) * GW, y = ((c - 32) / 16) * GH;
        RECT cell = {x, y, x + GW, y + GH};
        ExtTextOutA(dc, x, y, ETO_CLIPPED, &cell, &letter, 1, NULL);
    }
    GdiFlush();
    for (int i = 0; i < ATLAS_W * ATLAS_H; ++i) pixels[i] = (pixels[i] & 255) ? 0xFFFFFFFF : 0;
    font = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STATIC, ATLAS_W, ATLAS_H);
    if (font) { SDL_UpdateTexture(font, NULL, pixels, ATLAS_W * 4); SDL_SetTextureBlendMode(font, SDL_BLENDMODE_BLEND); }
    SelectObject(dc, old_font); SelectObject(dc, old_bitmap);
    DeleteObject(face); DeleteObject(bitmap); DeleteDC(dc);
    return font != NULL;
}

void ui_shutdown(void) { if (font) SDL_DestroyTexture(font); font = NULL; }

void ui_layout(SDL_Renderer *renderer, int *x, int *y, int *scale) {
    int w, h; SDL_GetRendererOutputSize(renderer, &w, &h);
    int k = SDL_min(w / 256, h / 192); if (k < 1) k = 1;
    *x = (w - 256 * k) / 2; *y = (h - 192 * k) / 2; *scale = k;
}

static void box(SDL_Renderer *r, int x, int y, int w, int h, int red, int green, int blue, int alpha) {
    SDL_Rect rect = {ox + x * unit, oy + y * unit, w * unit, h * unit};
    SDL_SetRenderDrawColor(r, red, green, blue, alpha); SDL_RenderFillRect(r, &rect);
}

static void text(SDL_Renderer *r, int x, int y, const char *s, int red, int green, int blue) {
    if (!font) return;
    SDL_SetTextureColorMod(font, red, green, blue);
    for (int i = 0; s[i] && i < 39; ++i) {
        unsigned c = (unsigned char)s[i]; if (c < 32 || c > 127) c = '?';
        SDL_Rect source = {((c - 32) % 16) * GW, ((c - 32) / 16) * GH, GW, GH};
        SDL_Rect dest = {ox + (x + i * GW) * unit, oy + y * unit, GW * unit, GH * unit};
        SDL_RenderCopy(r, font, &source, &dest);
    }
}

void ui_menu(SDL_Renderer *r, int kind, int player, int row, bool gamepad, bool capture, const char *name, const char *status) {
    ui_layout(r, &ox, &oy, &unit);
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(r, 0, 0, 0, 180); SDL_RenderFillRect(r, NULL);
    box(r, 6, 6, 244, 180, 7, 23, 50, 255);
    box(r, 6, 6, 122, 2, 170, 102, 255, 255);
    box(r, 128, 6, 122, 2, 38, 215, 255, 255);
    text(r, 14, 15, kind == 1 ? TR("Retro-Recomp - Help", "Retro-Recomp - Aide") : kind == 3 ? "Retro-Recomp - Pause" :
        TR("Retro-Recomp - Controls", "Retro-Recomp - Commandes"), 38, 215, 255);
    if (kind == 3) {
        text(r, 14, 62, TR("Game paused", "Jeu en pause"), 233, 239, 247);
        text(r, 14, 90, TR("P / Enter: resume", "P / Entree : reprendre"), 233, 239, 247);
        text(r, 14, 118, TR("F1: restart", "F1 : redemarrer"), 157, 173, 194);
        text(r, 14, 140, TR("Gamepad shortcuts: see F2", "Raccourcis manette : voir F2"), 157, 173, 194);
        text(r, 14, 164, TR("H: help | F2: controls", "H : aide | F2 : commandes"), 157, 173, 194);
    } else if (kind == 1) {
        const char *lines[] = {TR("F1  Restart game", "F1  Redemarrer le jeu"), TR("F2  Controls", "F2  Commandes"),
            TR("F3  Next filter", "F3  Changer le filtre"), TR("F4  Fullscreen / window", "F4  Plein ecran / fenetre"),
            "F6  English / Francais",
            TR("P / Enter  Pause", "P / Entree  Pause"),
            TR("Gamepad shortcuts: see F2", "Raccourcis manette : voir F2"), TR("Xbox: D-pad / left stick, A / B", "Xbox : croix / stick gauche, A / B"),
            TR("Esc  Quit (close menus first)", "Echap  Quitter (fermer les menus)")};
        for (int i = 0; i < (int)(sizeof(lines) / sizeof(lines[0])); ++i)
            text(r, 14, 31 + 12 * i, lines[i], 233, 239, 247);
        text(r, 14, 174, TR("H / Esc: close help", "H / Echap : fermer l'aide"), 157, 173, 194);
    } else {
        char heading[64]; snprintf(heading, sizeof(heading), TR("Player %d  [Left/Right: P1/P2]", "Joueur %d  [Gauche/Droite : J1/J2]"), player + 1);
        text(r, 14, 30, heading, 233, 239, 247);
        text(r, 14, 43, gamepad ? TR("Gamepad [Tab:keys | C:swap]", "Manette [Tab:clavier | C:inverser]") : TR("Keyboard [Tab:gamepad]", "Clavier  [Tab : manette]"), 157, 173, 194);
        for (int i = 0; i < controls_action_count(player); ++i) {
            if (i == row) box(r, 12, 58 + 12 * i, 232, 12, 40, 63, 81, 255);
            char line[100];
            const char *binding = gamepad ? button_name(controls.buttons[player][i]) : key_name(controls.keys[player][i]);
            snprintf(line, sizeof(line), "%c %-12s %s", i == row ? '>' : ' ', controls_label(i), capture && i == row ? TR("Press...", "Appuie...") : binding);
            text(r, 14, 59 + 12 * i, line, i == row ? 83 : 233, i == row ? 216 : 239, i == row ? 202 : 247);
        }
        const char *hint = gamepad && !name ? TR("No gamepad connected", "Aucune manette connectee") : TR("Enter/A: bind | D: defaults", "Entree/A : changer | D : defauts");
        text(r, 14, 157, status && *status ? status : hint, 233, 239, 247);
        text(r, 14, 171, capture ? TR("Esc: cancel binding", "Echap : annuler l'attribution") : TR("Up/Down: select | Esc: close", "Haut/Bas : choisir | Echap : fermer"), 157, 173, 194);
    }
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_NONE);
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
