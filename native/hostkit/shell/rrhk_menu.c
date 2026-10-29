/* Help (F1), controls pages (F2) and the machine's own page, drawn on the
 * shared menu canvas. The lines that belong to one machine come from its
 * adapter through the hooks of RrhkMachine. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdio.h>
#include "platform_io.h"
#include "retro_menu.h"
#include "retro_keyboard.h"
#include "runtime_feedback.h"
#include "hostkit/hostkit_internal.h"

void rrhk_menu_line(const RrhkMenuCtx *ctx, int y, const char *text) {
    rr_menu_text(ctx->renderer, ctx->ox, ctx->oy, ctx->unit, 14, y, text, RR_MENU_GOLD);
}

void rrhk_help_sound_line(const RrhkMenuCtx *ctx, int y) {
    rrhk_menu_line(ctx, y, rrhk.machine->audio_interpreted() ? rrhk_tr("Sound CPU: interpreter fallback", "CPU audio : secours interprete") :
                                                              rrhk_tr("Sound CPU: native code", "CPU audio : code natif"));
}

/* The rows of a page: the actions, player 1's two combinations and, on a gamepad page, the Gamepad row (divergence 10). */
int rrhk_page_rows(void) { return rrhk.machine->action_count + (rrhk.player ? 0 : RRHK_COMBO_ROWS) + (rrhk.gamepad_page ? 1 : 0); }
bool rrhk_device_row(void) { return rrhk.gamepad_page && rrhk.row == rrhk_page_rows() - 1; }

/* Control pages share their rows, so the selected row survives between them. */
void rrhk_turn_page(int step) {
    int control, before = rrhk.menu;
    rrhk.menu = rrhk_pages_goto(rrhk_pages_index() + step, &control);
    rrhk.player = control / 2; rrhk.gamepad_page = control % 2;
    rrhk.row = before == RRHK_MENU_CONTROLS && rrhk.menu == RRHK_MENU_CONTROLS ? SDL_min(rrhk.row, rrhk_page_rows() - 1) : 0;
    rrhk.capturing = 0; rrhk.status[0] = 0;
}

/* F2 opens on the first page from the game, help or pause, and closes F2 from any page. */
void rrhk_toggle_settings(void) {
    if (rrhk_pages_open(rrhk.menu)) rrhk_close_menu();
    else {
        if (rrhk.menu == RRHK_MENU_PAUSE) rrhk.parent_menu = RRHK_MENU_PAUSE;
        rrhk.menu = RRHK_MENU_CONTROLS; rrhk.player = rrhk.gamepad_page = rrhk.row = 0;
    }
    rrhk.capturing = 0;
}

void rrhk_menu_draw(SDL_Renderer *ren) {
    const RrhkMachine *m = rrhk.machine;
    if (!rrhk.menu) {
        if (rrhk.paused) {      /* F11 (X68000): the picture stays under the word */
            int ox, oy, unit; rr_menu_layout(ren, &ox, &oy, &unit);
            rr_menu_begin(ren, ox, oy, unit);
            rr_menu_text(ren, ox, oy, unit, 100, 85, rr_tr("Paused"), RR_MENU_GOLD);
            rr_menu_end(ren);
        }
        return;
    }
    if (rrhk.menu == RRHK_MENU_OPTIONS) {
        rrhk_option_page_draw(ren);
        return;
    }
    RrhkMenuCtx ctx = {ren, 0, 0, 0};
    rr_menu_layout(ren, &ctx.ox, &ctx.oy, &ctx.unit);
    const int ox = ctx.ox, oy = ctx.oy, unit = ctx.unit;
    rr_menu_begin(ren, ox, oy, unit);
    char heading[64], missing[80] = "";
    int status_y = RR_MENU_LAST_LINE;
    snprintf(heading, sizeof(heading), rr_tr(rrhk.gamepad_page ? "Player %d - Gamepad" : "Player %d - Keyboard"), rrhk.player + 1);
    if (rrhk.menu == RRHK_MENU_CONTROLS || rrhk.menu == RRHK_MENU_PAGE)
        rrhk_menu_page_header(&ctx, rrhk.menu == RRHK_MENU_CONTROLS ? heading : rr_tr(m->page->title));
    else if (rrhk.menu == RRHK_MENU_PAUSE) rr_menu_text(ren, ox, oy, unit, 14, RR_MENU_TITLE_LINE, "Retro-Recomp - Pause", RR_MENU_ACCENT);
    else rrhk_menu_line(&ctx, RR_MENU_TITLE_LINE, rrhk_tr("RetroRecomp - Help", "RetroRecomp - Aide"));
    if (rrhk.menu == RRHK_MENU_PAUSE) {
        if (m->pause_page) m->pause_page(&rrhk, &ctx);
    } else if (rrhk.menu == RRHK_MENU_HELP && m->help_page && m->help_page(&rrhk, &ctx)) {
        /* the machine drew a whole page of its own (X68000: Tab) */
    } else if (rrhk.menu == RRHK_MENU_HELP) {
        /* One line per function key, then the console's own controls. */
        const char *lines[14]; int count = 0;
        char fire[64];
        snprintf(fire, sizeof(fire), rr_tr("F6  Autofire: %s"), rr_tr(rrhk.autofire ? "ON" : "OFF"));
        lines[count++] = rr_tr("F1  Help | Shift+F1 Restart");
        lines[count++] = rr_tr("F2  Controls & options");
        lines[count++] = rr_tr("F3  Next filter");
        lines[count++] = rr_tr("F4  Window / Pixel / Fit");
        if (m->help_lines) m->help_lines(0, lines, &count);
        lines[count++] = fire;
        lines[count++] = rr_tr("F7  Next language");
        lines[count++] = rr_tr("F8  Save game state");
        lines[count++] = rr_tr("F9  Load game state");
        if (m->help_lines) m->help_lines(1, lines, &count);
        lines[count++] = rr_feedback_label();
        lines[count++] = rrhk_tr("Esc  Quit (close menus first)", "Echap  Quitter (fermer les menus)");
        int y = RR_MENU_FIRST_LINE;
        for (int i = 0; i < count; ++i, y += RR_MENU_LINE) rrhk_menu_line(&ctx, y, lines[i]);
        y += 6;
        m->help_controls(&rrhk, &ctx, y);
    } else if (rrhk.menu == RRHK_MENU_CONTROLS) {
        /* Every control fits on the page, up to fourteen rows; player 1's
         * pages end with the quit and restart combinations. */
        char line[120], value[80];
        const int rows = rrhk_page_rows();
        /* Fifteen rows (twelve actions, the combinations and the Gamepad row) push the hint and the status down. */
        const int hint_y = rows > 14 ? 173 : RR_MENU_HINT_LINE;
        if (rows > 14) status_y = 182;
        for (int a = 0; a < rows; ++a) {
            int y = RR_MENU_FIRST_LINE + a * RR_MENU_LINE;
            if (a == rrhk.row) rr_menu_box(ren, ox, oy, unit, 12, y, 232, RR_MENU_LINE, RR_MENU_SELECT, 255);
            if (rrhk.gamepad_page && a == rows - 1) {
                rrhk_pad_value(value, sizeof value, rrhk.player);
                snprintf(line, sizeof(line), "%c %s: %s", a == rrhk.row ? '>' : ' ', rr_tr("Gamepad"), value);
            } else if (a >= m->action_count) {
                rrhk_combo_value(value, sizeof value, a - m->action_count, rrhk.gamepad_page != 0);
                snprintf(line, sizeof(line), "%c %s: %s", a == rrhk.row ? '>' : ' ', rrhk_combo_label(a - m->action_count), value);
            } else {
                const char *button = rrhk.gamepad_page ? SDL_GameControllerGetStringForButton(rrhk.buttons[rrhk.player][a]) : NULL;
                const char *bound = rrhk.gamepad_page ? (button ? button : "-") :
                    rrhk.keys[rrhk.player][a] == SDL_SCANCODE_UNKNOWN ? "-" : rr_keyboard_name(rrhk.keys[rrhk.player][a]);
                snprintf(line, sizeof(line), "%c %s: %s", a == rrhk.row ? '>' : ' ', rr_tr(m->actions[a].name),
                         rrhk.capturing && a == rrhk.row ? rrhk_tr("Press a control...", "Appuie sur une touche...") : rr_tr(bound));
            }
            rrhk_menu_line(&ctx, y, line);
        }
        rrhk_menu_line(&ctx, hint_y, rrhk_device_row() ? rr_tr("Enter: change gamepad | Delete: Automatic") :
            rrhk.row >= m->action_count ? rrhk_combo_hint(rrhk.row - m->action_count) :
            rrhk.capturing ? rr_tr("Esc: cancel binding") : rr_tr("Enter: remap | Left/Right: page"));
        /* A binding or a combination waits for the selected player's own pad (divergence 3): say so when that
         * player has none. */
        if ((rrhk.capturing || rrhk_combo_capturing_pad()) && rrhk.gamepad_page && !rrhk.pads[rrhk.player])
            snprintf(missing, sizeof missing, rr_tr("No gamepad for player %d"), rrhk.player + 1);
    } else if (rrhk.menu == RRHK_MENU_PAGE) {
        if (m->page && m->page->draw) m->page->draw(&rrhk, &ctx);
    }
    if (rrhk.menu == RRHK_MENU_HELP) rr_menu_build_footer(ren, ox, oy, unit);
    else if (missing[0]) rrhk_menu_line(&ctx, status_y, missing);
    else if (rrhk.status[0]) rrhk_menu_line(&ctx, status_y, rrhk.status);
    rr_menu_end(ren);
}
