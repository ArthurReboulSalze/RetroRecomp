/* The event handler of the windowed loop: function keys, F2 pages, binding
 * capture, controller hot-plug. One handler for every machine. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdio.h>
#include <string.h>
#include "platform_io.h"
#include "retro_menu.h"
#include "display_settings.h"
#include "runtime_feedback.h"
#include "hostkit/hostkit_internal.h"

void rrhk_toggle_autofire(void) {
    rrhk.autofire = !rrhk.autofire;
    rrhk_autofire_reset();
    /* Divergence 11 (decided 28 October 2026): one short notice from the shared catalogue, on every console. */
    rrhk_notice(rr_tr(rrhk.autofire ? "Autofire ON" : "Autofire OFF"), 1800);
    if (rrhk_write_ready())
        rr_ini_set(rrhk_autofire_section(), L"autofire", rrhk.autofire ? L"1" : L"0", rrhk.ini_file);
}

/* The player whose gamepad this event came from, -1 for a gamepad no player holds. */
static int event_player(SDL_JoystickID which) {
    for (int p = 0; p < rrhk.machine->table_players; ++p)
        if (rrhk.pads[p] && which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(rrhk.pads[p]))) return p;
    return -1;
}

/* The Pause/Menu action of a machine that has one (Master System, Game Gear): the key or the button bound to it, of any player. */
static bool pause_pressed(const SDL_Event *event, SDL_Scancode key) {
    const RrhkMachine *m = rrhk.machine;
    if (!m->host_pause) return false;
    const int action = m->host_pause - 1;
    if (event->type == SDL_CONTROLLERBUTTONDOWN) {
        int p = event_player(event->cbutton.which);
        return p >= 0 && p < m->players() && rrhk.buttons[p][action] == (SDL_GameControllerButton)event->cbutton.button;
    }
    if (key == SDL_SCANCODE_UNKNOWN) return false;
    /* Enter binds rows on an F2 page: it does not pause there. */
    if (rrhk_pages_open(rrhk.menu) && (key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER)) return false;
    for (int p = 0; p < m->players(); ++p) if (rrhk.keys[p][action] == key) return true;
    return false;
}

/* Help (F1) and Pause: open it, or go back to the menu it was opened from. Opening one while the Pause menu is up remembers it. */
void rrhk_toggle_menu(int kind) {
    rrhk.capturing = 0;
    if (rrhk.menu == kind) rrhk_close_menu();
    else { if (rrhk.menu == RRHK_MENU_PAUSE) rrhk.parent_menu = RRHK_MENU_PAUSE; rrhk.menu = kind; }
}

void rrhk_close_menu(void) {
    rrhk.menu = rrhk.parent_menu;
    rrhk.parent_menu = 0;
}

void rrhk_poll_events(RrhkRun *run) {
    const RrhkMachine *m = run->machine;
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
        /* A computer's own shortcuts and the guest keyboard come first (X68000). */
        if (m->event && m->event(&event, &run->running)) continue;
        if (rrhk_options_event(&event, &rrhk.menu, rrhk.capturing != 0)) continue;
        if (event.type == SDL_QUIT) run->running = false;
        if (event.type == SDL_CONTROLLERDEVICEADDED || event.type == SDL_CONTROLLERDEVICEREMOVED) rrhk_open_pads();
        if (event.type == SDL_CONTROLLERBUTTONDOWN && rrhk.menu == RRHK_MENU_CONTROLS && rrhk.capturing && rrhk.gamepad_page == 1) {
            /* Which pad may bind (divergence 3, decided 28 October 2026): the selected player's pad only, on every console. */
            if (rrhk.pads[rrhk.player] &&
                event.cbutton.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(rrhk.pads[rrhk.player]))) {
                rrhk.buttons[rrhk.player][rrhk.row] = (SDL_GameControllerButton)event.cbutton.button;
                rrhk_store_binding(); rrhk.capturing = 0; rrhk.status[0] = 0;
            }
            continue;
        }
        SDL_Scancode key = event.type == SDL_KEYDOWN && !event.key.repeat ? event.key.keysym.scancode : SDL_SCANCODE_UNKNOWN;
        /* An option row behaves as its function key. */
        if (rrhk.menu == RRHK_MENU_OPTIONS) {
            int chosen = rrhk_option_page_event(&event);
            if (chosen < 0) continue;
            if (chosen > 0) key = (SDL_Scancode)chosen;
        }
        /* Left/Right, Tab, LB/RB or the D-pad turn the F2 pages and B
         * closes them; on a page the D-pad and A choose rows. */
        if (rrhk_pages_open(rrhk.menu) && !rrhk.capturing) {
            int step = rrhk_pages_step(&event);
            if (step) { rrhk_turn_page(step); continue; }
            if (event.type == SDL_CONTROLLERBUTTONDOWN && key == SDL_SCANCODE_UNKNOWN) {
                int b = event.cbutton.button;
                if (b == SDL_CONTROLLER_BUTTON_B) { rrhk_close_menu(); continue; }
                key = b == SDL_CONTROLLER_BUTTON_DPAD_UP ? SDL_SCANCODE_UP : b == SDL_CONTROLLER_BUTTON_DPAD_DOWN ? SDL_SCANCODE_DOWN :
                    b == SDL_CONTROLLER_BUTTON_A ? SDL_SCANCODE_RETURN : b == SDL_CONTROLLER_BUTTON_X ? SDL_SCANCODE_DELETE :
                    SDL_SCANCODE_UNKNOWN;
            }
        }
        /* A gamepad button bound to Pause/Menu opens or closes the Pause menu (a key does after the binding capture below). */
        if (event.type == SDL_CONTROLLERBUTTONDOWN && key == SDL_SCANCODE_UNKNOWN &&
            pause_pressed(&event, key) && !rrhk_options_component(0, event.cbutton.button)) {
            rrhk.menu = rrhk.menu == RRHK_MENU_PAUSE ? 0 : RRHK_MENU_PAUSE; rrhk.parent_menu = 0; rrhk.capturing = 0;
            continue;
        }
        if (key == SDL_SCANCODE_UNKNOWN) continue;
        if (rrhk.menu == RRHK_MENU_CONTROLS && rrhk.capturing) {
            if (key == SDL_SCANCODE_ESCAPE) rrhk.capturing = 0;
            else if (!rrhk.gamepad_page && key > SDL_SCANCODE_UNKNOWN && key < SDL_NUM_SCANCODES &&
                     !(key >= SDL_SCANCODE_F1 && key <= SDL_SCANCODE_F12)) {
                rrhk.keys[rrhk.player][rrhk.row] = key; rrhk_store_binding(); rrhk.capturing = 0;
            }
            continue;
        }
        if (key == SDL_SCANCODE_F1 && (event.key.keysym.mod & KMOD_SHIFT)) {
            /* Shift+F1 restarts at once, without a confirmation. */
            m->reset(); rrhk_audio_pause_output(run);
        } else if (pause_pressed(&event, key) && !rrhk_options_component(key, -1)) {
            rrhk.menu = rrhk.menu == RRHK_MENU_PAUSE ? 0 : RRHK_MENU_PAUSE; rrhk.parent_menu = 0; rrhk.capturing = 0;
        } else if (key == SDL_SCANCODE_ESCAPE) { if (rrhk.menu) rrhk_close_menu(); else run->running = false; }
        /* F1 opens help. */
        else if (key == SDL_SCANCODE_F1) rrhk_toggle_menu(RRHK_MENU_HELP);
        else if (key == SDL_SCANCODE_F2) rrhk_toggle_settings();
        else if (key == SDL_SCANCODE_F12) {
            rr_feedback_toggle(); rrhk_notice(rr_feedback_label(), 1800);
        }
        else if (key == SDL_SCANCODE_F3) {
            rrhk.filter = rr_menu_next_filter(rrhk.filter);
            SDL_DestroyTexture(run->tex);
            run->tex = rrhk_texture_create(run);
            if (!run->tex) { run->running = false; break; }
            SDL_SetTextureScaleMode(run->tex, SDL_ScaleModeNearest);
            const char *labels[] = {rrhk_tr("Sharp pixels", "Pixels nets"), "xBR smooth", "Scale2x", "Scanlines"};
            rrhk_notice(labels[rrhk.filter], 1800);
            if (!rrhk_write_ready() || !rr_display_save(rrhk.ini_file, rrhk.data_dir, rrhk.video_section, L"filter", rrhk.filter))
                snprintf(rrhk.status, sizeof(rrhk.status), "%s", rrhk_tr("Config unavailable", "Config inaccessible"));
        } else if (key == SDL_SCANCODE_F4) {
            rrhk_cycle_display();
        } else if (m->key_event && m->key_event(&rrhk, key, &run->running)) {
            /* a machine key (Neo Geo F5, F11) */
        } else if (key == SDL_SCANCODE_F6) {
            rrhk_toggle_autofire();
        }
        else if (key == SDL_SCANCODE_F7) {
            rrhk.language = rr_language_next(rrhk.language); rr_language_set(rrhk.language);
            rrhk_notice(rr_language_name(rrhk.language), 2200);
            if (rrhk_write_ready())
                rr_ini_set(L"Interface", L"language", rr_language_wide(rrhk.language), rrhk.ini_file);
        } else if (key == SDL_SCANCODE_F8 || key == SDL_SCANCODE_F9) {
            run->pending_state = key == SDL_SCANCODE_F9 ? 2 : 1;
        } else if (rrhk.menu == RRHK_MENU_PAGE) {
            if (m->page && m->page->key) m->page->key(&rrhk, key);
        } else if (rrhk.menu == RRHK_MENU_CONTROLS) {
            bool enter = key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER;
            if (key == SDL_SCANCODE_UP) rrhk.row = (rrhk.row + rrhk_page_rows() - 1) % rrhk_page_rows();
            else if (key == SDL_SCANCODE_DOWN) rrhk.row = (rrhk.row + 1) % rrhk_page_rows();
            else if (rrhk_device_row()) {
                /* Divergence 10 (decided 28 October 2026): which pad this player uses. */
                if (enter) rrhk_pad_next(rrhk.player);
                else if (key == SDL_SCANCODE_DELETE || key == SDL_SCANCODE_BACKSPACE) rrhk_pad_automatic(rrhk.player);
            } else if (rrhk.row >= m->action_count) {
                /* Quit and restart combinations: hold them one second in play. */
                if (enter) rrhk_combo_start(rrhk.row - m->action_count, rrhk.gamepad_page != 0);
                else if (key == SDL_SCANCODE_DELETE || key == SDL_SCANCODE_BACKSPACE) rrhk_combo_clear(rrhk.row - m->action_count, rrhk.gamepad_page != 0);
            } else if (m->bindings_clearable && key == SDL_SCANCODE_DELETE) rrhk_clear_binding();
            else if (enter) rrhk.capturing = 1;
        }
    }
}
