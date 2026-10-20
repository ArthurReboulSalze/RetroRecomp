#include "scale2x.h"
/* Game Boy adapter for the same menu canvas used by Master System/Game Gear.
 * Included after the GB runtime's input, save and display helpers. */

enum { RR_GB_HELP = 1, RR_GB_CONTROLS = 2, RR_GB_PAUSE = 3 };
static const GBInputAction rr_gb_actions[] = {
    GB_INPUT_ACTION_UP, GB_INPUT_ACTION_DOWN, GB_INPUT_ACTION_LEFT,
    GB_INPUT_ACTION_RIGHT, GB_INPUT_ACTION_A, GB_INPUT_ACTION_B,
    GB_INPUT_ACTION_START, GB_INPUT_ACTION_SELECT
};
static const char* rr_gb_labels_en[] = {
    "Up", "Down", "Left", "Right", "Button A", "Button B", "Start", "Select"
};
static const char* rr_gb_labels_fr[] = {
    "Haut", "Bas", "Gauche", "Droite", "Bouton A", "Bouton B", "Start", "Select"
};
static char g_rr_status[80] = {};
static uint32_t g_rr_status_until = 0;

static const char* rr_gb_tr(const char* english, const char* french) {
    return rr_translate(g_rr_language, english, french);
}

static void rr_gb_notice(const char* message) {
    snprintf(g_rr_status, sizeof(g_rr_status), "%s", message);
    g_rr_status_until = SDL_GetTicks() + 2600;
}

static void rr_gb_toggle_menu(int kind) {
    if (g_show_menu && g_rr_menu_kind == kind) {
        g_show_menu = false;
        g_rr_menu_kind = 0;
    } else {
        g_show_menu = true;
        g_rr_menu_kind = kind;
    }
    cancel_binding_capture();
    clear_all_binding_pressed_state();
    update_effective_joypad_state();
    reset_audio_output_buffer(true);
}

static void rr_gb_cycle_filter(void) {
    g_render_filter_mode = (GBRenderFilterMode)rr_menu_next_filter((int)g_render_filter_mode);
    update_render_filter();
    update_game_viewport();
    save_runtime_preferences();
    const char* names_en[] = {"Sharp pixels", "xBR smooth", "Scale2x", "Scanlines"};
    const char* names_fr[] = {"Pixels nets", "xBR smooth", "Scale2x", "Scanlines"};
    rr_gb_notice(rr_gb_tr(names_en[(int)g_render_filter_mode], names_fr[(int)g_render_filter_mode]));
}

static void rr_gb_cycle_fullscreen(void) {
    if (!g_fullscreen) {
        g_render_scaling_mode = GB_RENDER_SCALING_PIXEL_PERFECT;
        set_fullscreen_enabled(true);
        rr_gb_notice(rr_gb_tr("Fullscreen: perfect pixels", "Plein ecran : pixels parfaits"));
    } else if (g_render_scaling_mode == GB_RENDER_SCALING_PIXEL_PERFECT) {
        g_render_scaling_mode = GB_RENDER_SCALING_ASPECT_FIT;
        update_game_viewport();
        rr_gb_notice(rr_gb_tr("Fullscreen: aspect fit", "Plein ecran : ajuste"));
    } else {
        g_render_scaling_mode = GB_RENDER_SCALING_PIXEL_PERFECT;
        set_fullscreen_enabled(false);
        rr_gb_notice(rr_gb_tr("Windowed", "Fenetre"));
    }
    save_runtime_preferences();
}

static void rr_gb_palette_change(void) {
    if (g_registered_ctx && g_registered_ctx->config.model == GB_MODEL_CGB) {
        rr_gb_notice(rr_gb_tr("Game Boy Color: game palette", "Game Boy Color : couleurs du jeu"));
        return;
    }
    g_palette_idx = g_palette_idx == 1 ? 0 : 1;
    save_runtime_preferences();
    rr_gb_notice(g_palette_idx == 1 ?
        rr_gb_tr("Display: monochrome", "Affichage : monochrome") :
        rr_gb_tr("Display: classic green", "Affichage : vert classique"));
}

static void rr_gb_draw_menu(void) {
    if (!g_show_menu) return;
    if (g_rr_menu_kind == RR_OPTIONS_MENU) {rr_options_draw(g_renderer); return;}
    int ox, oy, unit;
    rr_menu_layout(g_renderer, &ox, &oy, &unit);
    rr_menu_begin(g_renderer, ox, oy, unit);
#define RR_TEXT(x, y, label, r, g, b) rr_menu_text(g_renderer, ox, oy, unit, x, y, label, r, g, b)
#define RR_BOX(x, y, w, h, r, g, b, a) rr_menu_box(g_renderer, ox, oy, unit, x, y, w, h, r, g, b, a)
    const char* heading = g_rr_menu_kind == RR_GB_HELP ? rr_gb_tr("Retro-Recomp - Help", "Retro-Recomp - Aide") :
        g_rr_menu_kind == RR_GB_PAUSE ? "Retro-Recomp - Pause" :
        rr_gb_tr("Retro-Recomp - Controls", "Retro-Recomp - Commandes");
    RR_TEXT(14, 15, heading, 38, 215, 255);
    if (g_rr_menu_kind == RR_GB_HELP) {
        char autofire[48];
        snprintf(autofire, sizeof(autofire), rr_gb_tr("F6  Autofire: %s", "F6  Tir auto : %s"), rr_tr(g_rr_autofire ? "ON" : "OFF"));
        const char* lines[] = {
            rr_gb_tr("F1  Restart game", "F1  Redemarrer le jeu"),
            rr_gb_tr("F2  Controls", "F2  Commandes"),
            rr_gb_tr("F3  Next filter", "F3  Changer le filtre"),
            rr_gb_tr("F4  Window / Pixel / Fit", "F4  Fenetre / Pixels / Ajuste"),
            rr_gb_tr("F5  Monochrome / classic green", "F5  Monochrome / vert classique"),
            autofire, "F7  Next language",
            rr_gb_tr("F8  Save game state", "F8  Sauvegarder l'etat"),
            rr_gb_tr("F9  Load game state", "F9  Charger l'etat"),
            rr_feedback_label(),
            rr_gb_tr("P  Pause | Enter  Start", "P  Pause | Entree  Start"),
            rr_gb_tr("Gamepad menu: Guide button", "Menu manette : bouton Guide"),
        };
        for (int i = 0; i < (int)(sizeof(lines) / sizeof(lines[0])); ++i)
            RR_TEXT(14, 29 + 12 * i, lines[i], 233, 239, 247);
        RR_TEXT(14, 174, rr_gb_tr("O: options | H / Esc: close", "H / Echap: fermer"), 157, 173, 194);
        rr_menu_build_footer(g_renderer, ox, oy, unit);
    } else if (g_rr_menu_kind == RR_GB_PAUSE) {
        RR_TEXT(14, 62, rr_gb_tr("Game paused", "Jeu en pause"), 233, 239, 247);
        RR_TEXT(14, 90, rr_gb_tr("P: resume", "P : reprendre"), 233, 239, 247);
        RR_TEXT(14, 118, rr_gb_tr("F1: restart", "F1 : redemarrer"), 157, 173, 194);
        RR_TEXT(14, 140, rr_gb_tr("Gamepad shortcuts: see F2", "Raccourcis manette : voir F2"), 157, 173, 194);
        RR_TEXT(14, 152, has_interpreter_activity(g_registered_ctx) ?
            rr_gb_tr("Interpreter fallback used", "Secours interprete utilise") :
            rr_gb_tr("Native code", "Code natif"), 255, 209, 110);
        RR_TEXT(14, 164, rr_gb_tr("H: help | F2: controls", "H : aide | F2 : commandes"), 157, 173, 194);
    } else {
        RR_TEXT(14, 30, rr_gb_tr("Game Boy controls", "Commandes Game Boy"), 233, 239, 247);
        RR_TEXT(14, 43, g_rr_bind_gamepad ? rr_gb_tr("Gamepad [Tab:keys]", "Manette [Tab:clavier]") :
            rr_gb_tr("Keyboard [Tab:gamepad]", "Clavier [Tab:manette]"), 157, 173, 194);
        for (int row = 0; row < 8; ++row) {
            if (row == g_rr_menu_row) RR_BOX(12, 58 + 12 * row, 232, 12, 40, 63, 81, 255);
            const GBInputAction action = rr_gb_actions[row];
            const GBInputBinding& binding = g_rr_bind_gamepad ? g_controller_bindings[action][0] : g_keyboard_bindings[action][0];
            const std::string name = binding_display_label(binding);
            char line[96];
            snprintf(line, sizeof(line), "%c %s: %s", row == g_rr_menu_row ? '>' : ' ',
                rr_gb_tr(rr_gb_labels_en[row], rr_gb_labels_fr[row]),
                g_binding_capture_active && row == g_rr_menu_row ? rr_gb_tr("Press...", "Appuie...") : rr_tr(name.c_str()));
            RR_TEXT(14, 59 + 12 * row, line, row == g_rr_menu_row ? 83 : 233,
                row == g_rr_menu_row ? 216 : 239, row == g_rr_menu_row ? 202 : 247);
        }
        RR_TEXT(14, 157, g_rr_status_until > SDL_GetTicks() ? g_rr_status :
            g_rr_bind_gamepad && g_controller_name.empty() ? rr_gb_tr("No gamepad connected", "Aucune manette connectee") :
            rr_gb_tr("Enter/A: bind | D: defaults", "Entree/A : changer | D : defauts"), 233, 239, 247);
        RR_TEXT(14, 171, g_binding_capture_active ? rr_gb_tr("Esc: cancel binding", "Echap : annuler l'attribution") :
            rr_gb_tr("O / Guide: options | Esc: close", "Haut/Bas : choisir | Echap : fermer"), 157, 173, 194);
    }
#undef RR_TEXT
#undef RR_BOX
    rr_menu_end(g_renderer);
}

static void rr_gb_draw_status(void) {
    if (g_show_menu && g_rr_menu_kind == RR_GB_HELP) return;
    if (!g_rr_status[0] || (int32_t)(g_rr_status_until - SDL_GetTicks()) <= 0) return;
    int ox, oy, unit;
    rr_menu_layout(g_renderer, &ox, &oy, &unit);
    SDL_SetRenderDrawBlendMode(g_renderer, SDL_BLENDMODE_BLEND);
    rr_menu_box(g_renderer, ox, oy, unit, 8, 173, 240, 14, 19, 27, 42, 235);
    rr_menu_text(g_renderer, ox, oy, unit, 13, 175, g_rr_status, 233, 239, 247);
    rr_menu_end(g_renderer);
}

static void rr_gb_scale2x(const uint32_t* source, int source_stride, uint32_t* output) {
    rr_scale2x(source,GB_SCREEN_WIDTH,GB_SCREEN_HEIGHT,source_stride,output,GB_SCREEN_WIDTH*2);
}

static bool rr_gb_handle_menu_event(const SDL_Event* event, GBContext* ctx) {
    int previous = g_show_menu ? g_rr_menu_kind : 0;
    int options_menu = previous;
    if (rr_options_event(event, &options_menu, g_binding_capture_active, true)) {
        g_rr_menu_kind = options_menu;
        g_show_menu = options_menu != 0;
        if (previous != options_menu) {
            clear_all_binding_pressed_state(); update_effective_joypad_state();
            reset_audio_output_buffer(true);
        }
        return true;
    }
    if (event->type == SDL_KEYUP) {
        const SDL_Scancode key = event->key.keysym.scancode;
        if (g_show_menu || key == SDL_SCANCODE_H || key == SDL_SCANCODE_P ||
            (key >= SDL_SCANCODE_F1 && key <= SDL_SCANCODE_F9)) return true;
        return false;
    }
    if (event->type == SDL_KEYDOWN) {
        const SDL_Scancode key = event->key.keysym.scancode;
        if (event->key.repeat) return g_show_menu || key == SDL_SCANCODE_F5;
        if (key == SDL_SCANCODE_F1) {
            if (ctx) { gb_context_reset(ctx, true); reset_audio_output_buffer(true); }
            g_show_menu = false; g_rr_menu_kind = 0;
            rr_gb_notice(rr_gb_tr("Game restarted", "Jeu redemarre"));
            return true;
        }
        if (key == SDL_SCANCODE_F2) { rr_gb_toggle_menu(RR_GB_CONTROLS); return true; }
        if (key == SDL_SCANCODE_H) { rr_gb_toggle_menu(RR_GB_HELP); return true; }
        if (key == SDL_SCANCODE_F3) { rr_gb_cycle_filter(); return true; }
        if (key == SDL_SCANCODE_F4) { rr_gb_cycle_fullscreen(); return true; }
        if (key == SDL_SCANCODE_F12) {rr_feedback_toggle();rr_gb_notice(rr_feedback_label());return true;}
        if (key == SDL_SCANCODE_F5) { rr_gb_palette_change(); return true; }
        if (key == SDL_SCANCODE_F6) {
            g_rr_autofire = !g_rr_autofire;
            memset(g_rr_fire,0,sizeof g_rr_fire);
            save_runtime_preferences();
            rr_gb_notice(g_rr_autofire ? rr_gb_tr("Autofire ON", "Tir auto ON") :
                rr_gb_tr("Autofire OFF", "Tir auto OFF"));
            return true;
        }
        if (key == SDL_SCANCODE_F7) {
            g_rr_language = rr_language_next(g_rr_language); rr_language_set(g_rr_language); save_runtime_preferences(); rr_gb_shared_language(true);
            rr_gb_notice(rr_gb_tr("Language: English", "Langue : francais"));
            return true;
        }
        if (key == SDL_SCANCODE_F8 || key == SDL_SCANCODE_F9) {
            if (ctx) {
                if (key == SDL_SCANCODE_F8) save_savestate_slot(ctx, 0);
                else load_savestate_slot(ctx, 0);
                rr_gb_notice(g_savestate_status.c_str());
            }
            return true;
        }
        if (key == SDL_SCANCODE_ESCAPE || key == SDL_SCANCODE_AC_BACK) {
            if (g_show_menu) rr_gb_toggle_menu(g_rr_menu_kind);
            else { SDL_Event quit = {}; quit.type = SDL_QUIT; SDL_PushEvent(&quit); }
            return true;
        }
        if (key == SDL_SCANCODE_P) {
            rr_gb_toggle_menu(RR_GB_PAUSE); return true;
        }
        if (!g_show_menu) return false;
        if (g_rr_menu_kind == RR_GB_CONTROLS) {
            if (key == SDL_SCANCODE_TAB) g_rr_bind_gamepad = !g_rr_bind_gamepad;
            else if (key == SDL_SCANCODE_UP) g_rr_menu_row = (g_rr_menu_row + 7) % 8;
            else if (key == SDL_SCANCODE_DOWN) g_rr_menu_row = (g_rr_menu_row + 1) % 8;
            else if (key == SDL_SCANCODE_D) {
                reset_runtime_control_defaults();
                rr_gb_notice(rr_gb_tr("Default bindings restored", "Commandes par defaut restaurees"));
            } else if (key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER) {
                start_binding_capture(g_rr_bind_gamepad ? GB_CAPTURE_DEVICE_CONTROLLER : GB_CAPTURE_DEVICE_KEYBOARD,
                    rr_gb_actions[g_rr_menu_row], 0);
            }
        }
        return true;
    }
    if (event->type == SDL_CONTROLLERBUTTONDOWN) {
        const Uint8 button = event->cbutton.button;
        if (button == SDL_CONTROLLER_BUTTON_GUIDE) {
            rr_gb_toggle_menu(RR_GB_PAUSE); return true;
        }
        if (!g_show_menu) return false;
        if (button == SDL_CONTROLLER_BUTTON_B) { rr_gb_toggle_menu(g_rr_menu_kind); return true; }
        if (g_rr_menu_kind == RR_GB_CONTROLS) {
            if (button == SDL_CONTROLLER_BUTTON_DPAD_UP) g_rr_menu_row = (g_rr_menu_row + 7) % 8;
            else if (button == SDL_CONTROLLER_BUTTON_DPAD_DOWN) g_rr_menu_row = (g_rr_menu_row + 1) % 8;
            else if (button == SDL_CONTROLLER_BUTTON_A)
                start_binding_capture(g_rr_bind_gamepad ? GB_CAPTURE_DEVICE_CONTROLLER : GB_CAPTURE_DEVICE_KEYBOARD,
                    rr_gb_actions[g_rr_menu_row], 0);
        }
        return true;
    }
    if (event->type == SDL_CONTROLLERBUTTONUP)
        return g_show_menu ||
            event->cbutton.button == SDL_CONTROLLER_BUTTON_GUIDE;
    if (g_show_menu && event->type == SDL_CONTROLLERAXISMOTION) return true;
    if (g_show_menu && event->type == SDL_MOUSEBUTTONDOWN && event->button.button == SDL_BUTTON_LEFT) {
        int ox, oy, unit, window_w, window_h, output_w, output_h;
        rr_menu_layout(g_renderer, &ox, &oy, &unit);
        SDL_GetWindowSize(g_window, &window_w, &window_h);
        SDL_GetRendererOutputSize(g_renderer, &output_w, &output_h);
        const int x = (event->button.x * output_w / window_w - ox) / unit;
        const int y = (event->button.y * output_h / window_h - oy) / unit;
        if (g_rr_menu_kind == RR_GB_CONTROLS && x >= 12 && x < 244) {
            if (y >= 43 && y < 55) g_rr_bind_gamepad = !g_rr_bind_gamepad;
            else if (y >= 58 && y < 154) {
                g_rr_menu_row = (y - 58) / 12;
                start_binding_capture(g_rr_bind_gamepad ? GB_CAPTURE_DEVICE_CONTROLLER : GB_CAPTURE_DEVICE_KEYBOARD,
                    rr_gb_actions[g_rr_menu_row], 0);
            }
        }
        return true;
    }
    return g_show_menu && (event->type == SDL_MOUSEBUTTONUP || event->type == SDL_MOUSEWHEEL);
}
