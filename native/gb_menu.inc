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

/* F2 pages: keyboard, gamepad, then the options. Both control pages end
 * with the quit and restart combinations of their input type. */
enum { RR_GB_ROWS = 8 + RR_COMBO_ROWS };
static RrPages rr_gb_pages(void) { RrPages pages = {2, 0}; return pages; }
static int rr_gb_page(void) {
    return rr_pages_index(rr_gb_pages(), g_show_menu ? g_rr_menu_kind : 0, g_rr_bind_gamepad ? 1 : 0);
}
/* Both control pages share their rows, so the selected row survives between them. */
static void rr_gb_turn_page(int step) {
    int control, before = g_rr_menu_kind;
    g_rr_menu_kind = rr_pages_goto(rr_gb_pages(), rr_gb_page() + step, &control);
    g_rr_bind_gamepad = control != 0;
    if (before != RR_GB_CONTROLS || g_rr_menu_kind != RR_GB_CONTROLS) g_rr_menu_row = 0;
    cancel_binding_capture();
}
/* F2 opens on the first page from the game, help or pause, and closes F2 from any page. */
static void rr_gb_toggle_settings(void) {
    if (g_show_menu && rr_pages_open(g_rr_menu_kind)) { rr_gb_toggle_menu(g_rr_menu_kind); return; }
    g_rr_bind_gamepad = false; g_rr_menu_row = 0;
    rr_gb_toggle_menu(RR_GB_CONTROLS);
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

/* Option rows run their function keys exactly as the shortcuts do. */
static RrOptionRows rr_gb_option_rows(void) {
    RrOptionRows d; d.count = 0;
    rr_option_row(&d, SDL_SCANCODE_F3, "F3 Filter: %s", rr_option_filter_name((int)g_render_filter_mode));
    rr_option_row(&d, SDL_SCANCODE_F4, "F4 Display: %s", rr_option_mode_name(g_fullscreen ?
        (g_render_scaling_mode == GB_RENDER_SCALING_PIXEL_PERFECT ? 1 : 2) : 0));
    if (!g_registered_ctx || g_registered_ctx->config.model != GB_MODEL_CGB)
        rr_option_row(&d, SDL_SCANCODE_F5, "F5 Palette: %s", rr_tr(g_palette_idx == 1 ? "Monochrome" : "Classic green"));
    rr_option_row(&d, SDL_SCANCODE_F6, "F6 Autofire: %s", rr_tr(g_rr_autofire ? "ON" : "OFF"));
    rr_option_row(&d, SDL_SCANCODE_F7, "F7 Language: %s", rr_language_name(g_rr_language));
    rr_option_row(&d, SDL_SCANCODE_F12, "%s", rr_tr(rr_feedback_label()));
    rr_option_shared_rows(&d);
    return d;
}

static void rr_gb_draw_menu(void) {
    if (!g_show_menu) return;
    const int page = rr_gb_page(), pages = rr_pages_count(rr_gb_pages());
    if (g_rr_menu_kind == RR_OPTIONS_MENU) {
        RrOptionRows d = rr_gb_option_rows();
        rr_option_page_draw(g_renderer, &d, page, pages);
        return;
    }
    int ox, oy, unit;
    rr_menu_layout(g_renderer, &ox, &oy, &unit);
    rr_menu_begin(g_renderer, ox, oy, unit);
/* Variadic: colors are RR_MENU_* triplets, expanded after argument counting. */
#define RR_TEXT(x, y, label, ...) rr_menu_text(g_renderer, ox, oy, unit, x, y, label, __VA_ARGS__)
#define RR_BOX(x, y, w, h, ...) rr_menu_box(g_renderer, ox, oy, unit, x, y, w, h, __VA_ARGS__)
    if (g_rr_menu_kind == RR_GB_CONTROLS)
        rr_menu_page_header(g_renderer, ox, oy, unit, g_rr_bind_gamepad ? rr_gb_tr("Gamepad", "Manette") :
            rr_gb_tr("Keyboard", "Clavier"), page, pages);
    else RR_TEXT(14, RR_MENU_TITLE_LINE, g_rr_menu_kind == RR_GB_HELP ? rr_gb_tr("Retro-Recomp - Help", "Retro-Recomp - Aide") :
        "Retro-Recomp - Pause", RR_MENU_GOLD);
    if (g_rr_menu_kind == RR_GB_HELP) {
        char autofire[48];
        snprintf(autofire, sizeof(autofire), rr_gb_tr("F6  Autofire: %s", "F6  Tir auto : %s"), rr_tr(g_rr_autofire ? "ON" : "OFF"));
        const char* lines[] = {
            rr_gb_tr("F1  Help | Shift+F1 Restart", "F1  Aide | Maj+F1 Redemarrer"),
            rr_gb_tr("F2  Controls & options", "F2  Commandes et options"),
            rr_gb_tr("F3  Next filter", "F3  Changer le filtre"),
            rr_gb_tr("F4  Window / Pixel / Fit", "F4  Fenetre / Pixels / Ajuste"),
            rr_gb_tr("F5  Monochrome / classic green", "F5  Monochrome / vert classique"),
            autofire, "F7  Next language",
            rr_gb_tr("F8  Save game state", "F8  Sauvegarder l'etat"), rr_gb_tr("F9  Load game state", "F9  Charger l'etat"),
            rr_feedback_label(),
            rr_gb_tr("P  Pause | Enter  Start", "P  Pause | Entree  Start"),
            rr_gb_tr("Gamepad menu: Guide button", "Menu manette : bouton Guide"),
        };
        /* One line per function key, then the console's own controls. */
        for (int i = 0; i < (int)(sizeof(lines) / sizeof(lines[0])); ++i)
            RR_TEXT(14, RR_MENU_FIRST_LINE + RR_MENU_LINE * i, lines[i], RR_MENU_GOLD);
        RR_TEXT(14, RR_MENU_LAST_LINE, rr_gb_tr("F1 / Esc: close", "F1 / Echap : fermer"), RR_MENU_HINT);
        rr_menu_build_footer(g_renderer, ox, oy, unit);
    } else if (g_rr_menu_kind == RR_GB_PAUSE) {
        RR_TEXT(14, 62, rr_gb_tr("Game paused", "Jeu en pause"), RR_MENU_GOLD);
        RR_TEXT(14, 90, rr_gb_tr("P: resume", "P : reprendre"), RR_MENU_GOLD);
        RR_TEXT(14, 118, rr_gb_tr("Shift+F1: restart", "Maj+F1 : redemarrer"), RR_MENU_HINT);
        RR_TEXT(14, 140, rr_gb_tr("Gamepad shortcuts: see F2", "Raccourcis manette : voir F2"), RR_MENU_HINT);
        RR_TEXT(14, 152, has_interpreter_activity(g_registered_ctx) ?
            rr_gb_tr("Interpreter fallback used", "Secours interprete utilise") :
            rr_gb_tr("Native code", "Code natif"), RR_MENU_ACCENT);
        RR_TEXT(14, 164, rr_gb_tr("F1: help | F2: controls & options", "F1 : aide | F2 : commandes et options"), RR_MENU_HINT);
    } else {
        for (int row = 0; row < RR_GB_ROWS; ++row) {
            if (row == g_rr_menu_row) RR_BOX(12, RR_MENU_FIRST_LINE + RR_MENU_LINE * row, 232, RR_MENU_LINE, RR_MENU_SELECT, 255);
            char line[120];
            if (row >= 8) {
                char value[80];
                rr_combo_value(value, sizeof value, row - 8, g_rr_bind_gamepad);
                snprintf(line, sizeof(line), "%c %s: %s", row == g_rr_menu_row ? '>' : ' ', rr_combo_label(row - 8), value);
            } else {
                const GBInputAction action = rr_gb_actions[row];
                const GBInputBinding& binding = g_rr_bind_gamepad ? g_controller_bindings[action][0] : g_keyboard_bindings[action][0];
                const std::string name = binding_display_label(binding);
                snprintf(line, sizeof(line), "%c %s: %s", row == g_rr_menu_row ? '>' : ' ',
                    rr_gb_tr(rr_gb_labels_en[row], rr_gb_labels_fr[row]),
                    g_binding_capture_active && row == g_rr_menu_row ? rr_gb_tr("Press...", "Appuie...") : rr_tr(name.c_str()));
            }
            RR_TEXT(14, RR_MENU_FIRST_LINE + RR_MENU_LINE * row, line, row == g_rr_menu_row ? 83 : 233,
                row == g_rr_menu_row ? 216 : 239, row == g_rr_menu_row ? 202 : 247);
        }
        RR_TEXT(14, RR_MENU_HINT_LINE, g_rr_status_until > SDL_GetTicks() ? g_rr_status :
            g_rr_menu_row >= 8 ? rr_combo_hint(g_rr_menu_row - 8) :
            g_rr_bind_gamepad && g_controller_name.empty() ? rr_gb_tr("No gamepad connected", "Aucune manette connectee") :
            rr_gb_tr("Enter/A: bind | D: defaults", "Entree/A : changer | D : defauts"), RR_MENU_GOLD);
        RR_TEXT(14, RR_MENU_LAST_LINE, g_binding_capture_active ? rr_gb_tr("Esc: cancel binding", "Echap : annuler l'attribution") :
            rr_gb_tr("Left/Right: page | Esc: close", "Gauche/Droite : page | Echap : fermer"), RR_MENU_HINT);
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
    rr_menu_box(g_renderer, ox, oy, unit, 8, 173, 240, 14, RR_MENU_PANEL_RGB, 235);
    rr_menu_text(g_renderer, ox, oy, unit, 13, 175, g_rr_status, RR_MENU_GOLD);
    rr_menu_end(g_renderer);
}

static void rr_gb_scale2x(const uint32_t* source, int source_stride, uint32_t* output) {
    rr_scale2x(source,GB_SCREEN_WIDTH,GB_SCREEN_HEIGHT,source_stride,output,GB_SCREEN_WIDTH*2);
}

/* Enter / A / a click: bind the selected control, or capture the quit or
 * restart combination of the rows after them. */
static void rr_gb_activate_row(void) {
    if (g_rr_menu_row >= 8) rr_combo_start(g_rr_menu_row - 8, g_rr_bind_gamepad);
    else start_binding_capture(g_rr_bind_gamepad ? GB_CAPTURE_DEVICE_CONTROLLER : GB_CAPTURE_DEVICE_KEYBOARD,
        rr_gb_actions[g_rr_menu_row], 0);
}

static bool rr_gb_handle_menu_event(const SDL_Event* event, GBContext* ctx) {
    int previous = g_show_menu ? g_rr_menu_kind : 0;
    int options_menu = previous;
    if (rr_options_event(event, &options_menu, g_binding_capture_active)) {
        g_rr_menu_kind = options_menu;
        g_show_menu = options_menu != 0;
        if (previous != options_menu) {
            clear_all_binding_pressed_state(); update_effective_joypad_state();
            reset_audio_output_buffer(true);
        }
        return true;
    }
    /* An option row behaves as its function key. */
    SDL_Scancode shortcut = SDL_SCANCODE_UNKNOWN;
    if (g_show_menu && g_rr_menu_kind == RR_OPTIONS_MENU) {
        RrOptionRows d = rr_gb_option_rows();
        const int chosen = rr_option_page_event(event, &d);
        if (chosen < 0) return true;
        shortcut = (SDL_Scancode)chosen;
    }
    /* Left/Right, Tab, LB/RB or the D-pad turn the F2 pages. */
    if (g_show_menu && rr_pages_open(g_rr_menu_kind) && !g_binding_capture_active && !shortcut) {
        const int step = rr_pages_step(event);
        if (step) { rr_gb_turn_page(step); return true; }
    }
    if (event->type == SDL_KEYUP) {
        const SDL_Scancode key = event->key.keysym.scancode;
        if (g_show_menu || key == SDL_SCANCODE_P ||
            (key >= SDL_SCANCODE_F1 && key <= SDL_SCANCODE_F9)) return true;
        return false;
    }
    if (event->type == SDL_KEYDOWN || shortcut) {
        const SDL_Scancode key = shortcut ? shortcut : event->key.keysym.scancode;
        if (!shortcut && event->key.repeat) return g_show_menu || key == SDL_SCANCODE_F5;
        /* F1 opens help; Shift+F1 restarts at once, without a confirmation. */
        if (key == SDL_SCANCODE_F1 && !(event->key.keysym.mod & KMOD_SHIFT)) { rr_gb_toggle_menu(RR_GB_HELP); return true; }
        if (key == SDL_SCANCODE_F1) {
            if (ctx) { gb_context_reset(ctx, true); reset_audio_output_buffer(true); }
            g_show_menu = false; g_rr_menu_kind = 0;
            rr_gb_notice(rr_gb_tr("Game restarted", "Jeu redemarre"));
            return true;
        }
        if (key == SDL_SCANCODE_F2) { rr_gb_toggle_settings(); return true; }
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
            if (key == SDL_SCANCODE_UP) g_rr_menu_row = (g_rr_menu_row + RR_GB_ROWS - 1) % RR_GB_ROWS;
            else if (key == SDL_SCANCODE_DOWN) g_rr_menu_row = (g_rr_menu_row + 1) % RR_GB_ROWS;
            else if (key == SDL_SCANCODE_D) {
                reset_runtime_control_defaults();
                rr_gb_notice(rr_gb_tr("Default bindings restored", "Commandes par defaut restaurees"));
            } else if (key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER) rr_gb_activate_row();
            else if ((key == SDL_SCANCODE_DELETE || key == SDL_SCANCODE_BACKSPACE) && g_rr_menu_row >= 8)
                rr_combo_clear(g_rr_menu_row - 8, g_rr_bind_gamepad);
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
            if (button == SDL_CONTROLLER_BUTTON_DPAD_UP) g_rr_menu_row = (g_rr_menu_row + RR_GB_ROWS - 1) % RR_GB_ROWS;
            else if (button == SDL_CONTROLLER_BUTTON_DPAD_DOWN) g_rr_menu_row = (g_rr_menu_row + 1) % RR_GB_ROWS;
            else if (button == SDL_CONTROLLER_BUTTON_A) rr_gb_activate_row();
            else if (button == SDL_CONTROLLER_BUTTON_X && g_rr_menu_row >= 8) rr_combo_clear(g_rr_menu_row - 8, g_rr_bind_gamepad);
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
            if (y >= RR_MENU_FIRST_LINE && y < RR_MENU_FIRST_LINE + RR_MENU_LINE * RR_GB_ROWS) {
                g_rr_menu_row = (y - RR_MENU_FIRST_LINE) / RR_MENU_LINE;
                rr_gb_activate_row();
            }
        }
        return true;
    }
    return g_show_menu && (event->type == SDL_MOUSEBUTTONUP || event->type == SDL_MOUSEWHEEL);
}
