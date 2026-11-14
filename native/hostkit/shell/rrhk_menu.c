/* Help (F1), controls pages (F2) and the machine's own page, drawn on the
 * shared menu canvas. The lines that belong to one machine come from its
 * adapter through the hooks of RrhkMachine. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
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

/* The rows of a page: the actions, player 1's two combinations and, on a gamepad page, the Gamepad row (divergence 10), then on
 * a machine with analog sticks the Stick dead zone row. */
static int stick_row(void) { return rrhk.gamepad_page && rrhk.machine->analog_sticks > 0 ? 1 : 0; }
/* 1.7.5: the machine's own rows of this player's gamepad page come first (RrhkMachine.pad_rows), then the kit's as before. */
const RrhkPadRow *rrhk_pad_row_at(int row) {
    const RrhkMachine *m = rrhk.machine;
    if (!rrhk.gamepad_page || !m->pad_rows || row < 0) return NULL;
    for (int i = 0, here = 0; i < m->pad_row_count; ++i)
        if (m->pad_rows[i].player == rrhk.player + 1 && m->pad_rows[i].count > 0 && here++ == row) return &m->pad_rows[i];
    return NULL;
}
int rrhk_pad_rows_here(void) {
    int count = 0;
    while (rrhk_pad_row_at(count)) ++count;
    return count;
}
int rrhk_action_row(void) { return rrhk.row - rrhk_pad_rows_here(); }
int rrhk_page_rows(void) {
    return rrhk_pad_rows_here() + rrhk.machine->action_count + (rrhk.player ? 0 : RRHK_COMBO_ROWS) + (rrhk.gamepad_page ? 1 : 0) +
           stick_row();
}
bool rrhk_device_row(void) { return rrhk.gamepad_page && rrhk.row == rrhk_page_rows() - 1 - stick_row(); }
bool rrhk_deadzone_row(void) { return stick_row() && rrhk.row == rrhk_page_rows() - 1; }

/* A control page shows fifteen rows at once (every machine before 1.7.0 had at most fifteen: nothing scrolled). Past them the
 * window follows the selected row, moving only when that row would leave it. */
enum { PAGE_ROWS = 15 };
static int page_first;
int rrhk_page_scroll(void) {
    const int rows = rrhk_page_rows();
    if (rows <= PAGE_ROWS) return page_first = 0;
    if (rrhk.row < page_first) page_first = rrhk.row;
    if (rrhk.row >= page_first + PAGE_ROWS) page_first = rrhk.row - PAGE_ROWS + 1;
    if (page_first > rows - PAGE_ROWS) page_first = rows - PAGE_ROWS;
    if (page_first < 0) page_first = 0;
    return page_first;
}

/* The graphics page (D14): the machine's options, the kit's Filter row, Restore defaults. */
int rrhk_graphics_rows(void) {
    const int options = rrhk.machine->gfx_option_count;
    return (options < RRHK_MAX_GFX_OPTIONS ? options : RRHK_MAX_GFX_OPTIONS) + 2;
}

void rrhk_graphics_draw(SDL_Renderer *ren) {
    const RrhkMachine *m = rrhk.machine;
    RrhkMenuCtx ctx = {ren, 0, 0, 0};
    rr_menu_layout(ren, &ctx.ox, &ctx.oy, &ctx.unit);
    rr_menu_begin(ren, ctx.ox, ctx.oy, ctx.unit);
    rr_menu_header_compact(ren, ctx.ox, ctx.oy, ctx.unit, rr_tr("Retro-Recomp - Graphics"), RR_ICON_OPTIONS_SMALL);
    const int rows = rrhk_graphics_rows(), options = rows - 2;
    if (rrhk.gfx_row < 0 || rrhk.gfx_row >= rows) rrhk.gfx_row = 0;
    char line[120];
    for (int r = 0; r < rows; ++r) {
        const int y = RR_MENU_FIRST_LINE + r * RR_MENU_LINE;
        if (r == rrhk.gfx_row) rr_menu_box(ren, ctx.ox, ctx.oy, ctx.unit, 12, y, 232, RR_MENU_LINE, RR_MENU_SELECT, 255);
        /* 1.7.5: the mark, the row's icon, then its text */
        if (r == rrhk.gfx_row) rr_menu_text(ren, ctx.ox, ctx.oy, ctx.unit, 14, y, ">", RR_MENU_ACCENT);
        int icon = r == options ? RR_ICON_ROW_FILTER : r > options ? RR_ICON_ROW_RESTORE : RR_ICON_ROW_GENERIC;
        if (r < options) {
            const RrhkGfxOption *option = &m->gfx_options[r];
            const int value = rrhk.gfx[r] >= 0 && rrhk.gfx[r] < option->count ? rrhk.gfx[r] : option->def;
            snprintf(line, sizeof line, "%s: %s", rr_tr(option->name), option->count > 0 ? rr_tr(option->values[value]) : "-");
            icon = rrhk_gfx_icon(option->name);
        } else if (r == options) {
            /* xBR works up to 1024 x 1024 and scanlines need two window pixels a row: past that the filter does nothing, and
             * the row says so. */
            char value[80], name[80];
            const SDL_Rect dst = rrhk_game_rect(ren);
            const bool inert = (rrhk.filter == 1 && (m->visible_width() > 1024 || m->visible_height() > 1024)) ||
                               (rrhk.filter == 3 && dst.h < 2 * m->visible_height());
            if (inert) snprintf(name, sizeof name, rr_tr("%s (not at this size)"), rrhk_filter_name(rrhk.filter));
            else snprintf(name, sizeof name, "%s", rrhk_filter_name(rrhk.filter));
            snprintf(value, sizeof value, rr_tr("Filter: %s"), name);
            snprintf(line, sizeof line, "%s", value);
        } else snprintf(line, sizeof line, "%s", rr_tr("Restore defaults"));
        rrhk_draw_icon(ren, ctx.ox, ctx.oy, ctx.unit, 20, y, icon, NULL);
        rr_menu_text_fit(ren, ctx.ox, ctx.oy, ctx.unit, 32, y, 210, line, RR_MENU_GOLD);
    }
    rr_menu_hints(ren, ctx.ox, ctx.oy, ctx.unit, 14, RR_MENU_HINT_LINE, 228, rr_tr("Up/Down: row | Left/Right: change"), RR_MENU_HINT);
    if (rrhk.status[0]) rr_menu_text(ren, ctx.ox, ctx.oy, ctx.unit, 14, RR_MENU_LAST_LINE, rrhk.status, RR_MENU_GOLD);
    else rr_menu_hints(ren, ctx.ox, ctx.oy, ctx.unit, 14, RR_MENU_LAST_LINE, 228, rr_tr("Esc / B: close"), RR_MENU_HINT);
    rr_menu_end(ren);
}

/* Control pages share their rows, so the selected row survives between them. */
void rrhk_turn_page(int step) {
    int control, before = rrhk.menu;
    rrhk.menu = rrhk_pages_goto(rrhk_pages_index() + step, &control);
    rrhk.player = control / 2; rrhk.gamepad_page = control % 2;
    rrhk.row = before == RRHK_MENU_CONTROLS && rrhk.menu == RRHK_MENU_CONTROLS ? SDL_min(rrhk.row, rrhk_page_rows() - 1) : 0;
    rrhk.capturing = 0; rrhk.status[0] = 0;
}

/* ---- The F2 menu (1.7.4): one tile per page, instead of pages turned with Left and Right ----
 * A tile for each player's keyboard and gamepad, one for the machine's own page when it has one (guns, DIP switches), one for
 * the options: the same pages, in the same order, as rrhk_pages_goto numbers them. Enter opens a page, Esc comes back to the
 * tiles, and Esc on the tiles goes back to where F2 was pressed (the game, or the Pause menu). A page opened another way (the
 * Guide button opens the options) closes as before. */
enum { HUB_COLUMNS = 5, TILE_W = 44, TILE_H = 40, TILE_GAP = 2 };
static int hub_tile, hub_parent;
static bool from_hub;
static bool quit_yes;

static void hub_open(int tile) {
    int control;
    rrhk.menu = rrhk_pages_goto(tile, &control);
    rrhk.player = control / 2; rrhk.gamepad_page = control % 2;
    rrhk.row = 0; rrhk.capturing = 0; rrhk.status[0] = 0; rrhk.parent_menu = 0;
    from_hub = true;
}
void rrhk_hub_key(SDL_Scancode key) {
    const int tiles = rrhk_pages_count();
    if (hub_tile < 0 || hub_tile >= tiles) hub_tile = 0;
    if (key == SDL_SCANCODE_LEFT) hub_tile = (hub_tile + tiles - 1) % tiles;
    else if (key == SDL_SCANCODE_RIGHT) hub_tile = (hub_tile + 1) % tiles;
    else if (key == SDL_SCANCODE_UP && hub_tile >= HUB_COLUMNS) hub_tile -= HUB_COLUMNS;
    else if (key == SDL_SCANCODE_DOWN && hub_tile + HUB_COLUMNS < tiles) hub_tile += HUB_COLUMNS;
    else if (key == SDL_SCANCODE_DOWN && hub_tile < HUB_COLUMNS && tiles > HUB_COLUMNS) hub_tile = tiles - 1;
    else if (key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER) hub_open(hub_tile);
}
/* What a tile is: a control page (its number: player * 2 + gamepad), the machine's page (-1) or the options (-2). */
static int hub_kind(int tile) {
    const int controls = 2 * rrhk.machine->players();
    return tile < controls ? tile : tile == rrhk_pages_count() - 1 ? -2 : -1;
}
static void hub_draw(const RrhkMenuCtx *ctx) {
    const RrhkMachine *m = rrhk.machine;
    SDL_Renderer *ren = ctx->renderer;
    const int ox = ctx->ox, oy = ctx->oy, unit = ctx->unit;
    const int tiles = rrhk_pages_count(), lines = (tiles + HUB_COLUMNS - 1) / HUB_COLUMNS;
    if (hub_tile < 0 || hub_tile >= tiles) hub_tile = 0;
    rr_menu_header(ren, ox, oy, unit, rr_tr("Controls"), NULL);
    const int top = lines > 1 ? 38 : 44;
    char label[16], title[80], value[80];
    for (int i = 0; i < tiles; ++i) {
        const int line = i / HUB_COLUMNS, in_line = line == lines - 1 ? tiles - line * HUB_COLUMNS : HUB_COLUMNS;
        const int x = (256 - in_line * TILE_W - (in_line - 1) * TILE_GAP) / 2 + (i % HUB_COLUMNS) * (TILE_W + TILE_GAP);
        const int y = top + line * (TILE_H + TILE_GAP), kind = hub_kind(i);
        const bool selected = i == hub_tile;
        if (selected) {
            rr_menu_box(ren, ox, oy, unit, x - 1, y - 1, TILE_W + 2, TILE_H + 2, RR_MENU_GOLD, 255);
            rr_menu_box(ren, ox, oy, unit, x, y, TILE_W, TILE_H, RR_MENU_ACCENT, 255);
            rr_menu_box(ren, ox, oy, unit, x + 1, y + 1, TILE_W - 2, TILE_H - 2, RR_MENU_SELECT, 255);
        } else {
            rr_menu_box(ren, ox, oy, unit, x, y, TILE_W, TILE_H, RR_MENU_SHADE, 255);
            rr_menu_box(ren, ox, oy, unit, x + 1, y + 1, TILE_W - 2, TILE_H - 2, 26, 24, 20, 255);
        }
        const int icon = kind == -2 ? RR_ICON_OPTIONS : kind == -1 ? (m->pointer ? RR_ICON_POINTER : RR_ICON_SWITCHES) :
            kind % 2 ? RR_ICON_GAMEPAD : RR_ICON_KEYBOARD;
        rr_menu_icon(ren, ox, oy, unit, x + (TILE_W - rr_menu_icon_width(icon)) / 2, y + (kind >= 0 ? 4 : 11), icon, !selected);
        if (kind >= 0) {
            snprintf(label, sizeof label, rr_tr("P%d"), kind / 2 + 1);
            const int width = rr_menu_block_width(label, 1);
            if (selected) rr_menu_block(ren, ox, oy, unit, x + (TILE_W - width) / 2, y + 28, 1, label, RR_MENU_ACCENT);
            else rr_menu_block(ren, ox, oy, unit, x + (TILE_W - width) / 2, y + 28, 1, label, RR_MENU_HINT);
        }
    }
    /* Under the tiles: what the selected one is, and for a gamepad which controller that player has. */
    const int y = top + lines * (TILE_H + TILE_GAP) + 4;
    rr_menu_box(ren, ox, oy, unit, 14, y, 228, 1, RR_MENU_SHADE, 255);
    const int kind = hub_kind(hub_tile);
    if (kind >= 0) snprintf(title, sizeof title, rr_tr(kind % 2 ? "Player %d - Gamepad" : "Player %d - Keyboard"), kind / 2 + 1);
    else {
        /* A page's title names the converter ("Retro-Recomp - Gun"): under the tiles the page alone is named. */
        const char *name = rr_tr(kind == -2 ? "Options" : m->page->title);
        if (!strncmp(name, "Retro-Recomp - ", 15)) name += 15;
        snprintf(title, sizeof title, "%s", name);
    }
    int width = rr_menu_text_width(title); if (width > 228) width = 228;
    rr_menu_text_fit(ren, ox, oy, unit, 128 - width / 2, y + 6, 228, title, RR_MENU_ACCENT);
    if (kind >= 0 && kind % 2) {
        char pad[60];
        rrhk_pad_value(pad, sizeof pad, kind / 2);
        snprintf(value, sizeof value, "%s: %s", rr_tr("Gamepad"), pad);
        width = rr_menu_text_width(value); if (width > 228) width = 228;
        rr_menu_text_fit(ren, ox, oy, unit, 128 - width / 2, y + 18, 228, value, RR_MENU_HINT);
    }
    rr_menu_hints(ren, ox, oy, unit, 14, RR_MENU_LAST_LINE, 228, rr_tr("Arrows: choose | Enter: open | Esc: close"), RR_MENU_HINT);
}

/* F2 opens the menu of tiles from the game, the help or the Pause menu, and closes F2 from the tiles or from any page. */
void rrhk_toggle_settings(void) {
    rrhk.capturing = 0;
    if (rrhk.menu == RRHK_MENU_HUB || (from_hub && rrhk_pages_open(rrhk.menu))) {
        rrhk.menu = hub_parent; rrhk.parent_menu = 0; hub_parent = 0; from_hub = false;
    } else if (rrhk_pages_open(rrhk.menu)) rrhk_close_menu();      /* a page opened by itself (the Guide button) */
    else {
        hub_parent = rrhk.menu == RRHK_MENU_PAUSE ? RRHK_MENU_PAUSE : 0;
        rrhk.menu = RRHK_MENU_HUB; rrhk.parent_menu = 0; from_hub = false;
        rrhk.player = rrhk.gamepad_page = rrhk.row = hub_tile = 0;
    }
}

/* Esc, B: back to the menu this one was opened from (the tiles for one of their pages), or to the game. */
void rrhk_close_menu(void) {
    if (rrhk.menu == RRHK_MENU_HUB) { rrhk.menu = hub_parent; hub_parent = 0; rrhk.parent_menu = 0; from_hub = false; return; }
    if (from_hub && rrhk_pages_open(rrhk.menu)) { rrhk.menu = RRHK_MENU_HUB; rrhk.parent_menu = 0; return; }
    rrhk.menu = rrhk.parent_menu;
    rrhk.parent_menu = 0;
}

/* ---- Quit? (1.7.4): Esc in play and the Quit combination ask before the game closes ----
 * Drawn by the kit like every menu, never a window of the system. "No" is selected when it opens. */
void rrhk_quit_ask(void) {
    if (rrhk.menu == RRHK_MENU_QUIT) return;
    rrhk.parent_menu = rrhk.menu == RRHK_MENU_PAUSE ? RRHK_MENU_PAUSE : 0;
    rrhk.menu = RRHK_MENU_QUIT; rrhk.capturing = 0;
    quit_yes = false;
}
/* true: the player chose Yes. */
bool rrhk_quit_key(SDL_Scancode key) {
    if (key == SDL_SCANCODE_LEFT || key == SDL_SCANCODE_RIGHT || key == SDL_SCANCODE_UP || key == SDL_SCANCODE_DOWN) quit_yes = !quit_yes;
    else if (key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER) {
        if (quit_yes) return true;
        rrhk_close_menu();
    }
    return false;
}
static void quit_draw(SDL_Renderer *ren, int ox, int oy, int unit) {
    enum { X = 58, Y = 62, W = 140, H = 62 };
    char title[48];
    SDL_SetRenderDrawBlendMode(ren, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(ren, 0, 0, 0, 150); SDL_RenderFillRect(ren, NULL);
    rr_menu_box(ren, ox, oy, unit, X - 1, Y - 1, W + 2, H + 2, RR_MENU_SHADE, 255);
    rr_menu_box(ren, ox, oy, unit, X, Y, W, H, RR_MENU_PANEL_RGB, 255);
    rr_menu_box(ren, ox, oy, unit, X - 1, Y - 1, W + 2, 2, RR_MENU_GOLD, 255);
    rr_menu_icon(ren, ox, oy, unit, X + 8, Y + 9, RR_ICON_LOGO, false);
    snprintf(title, sizeof title, "%s ?", rr_tr("Quit"));
    if (rr_menu_block_width(title, 2) > W - 50) snprintf(title, sizeof title, "%s", rr_tr("Quit"));
    rr_menu_block(ren, ox, oy, unit, X + 42, Y + 14, rr_menu_block_width(title, 2) > W - 50 ? 1 : 2, title, RR_MENU_GOLD);
    for (int i = 0; i < 2; ++i) {
        const bool selected = (i == 1) == quit_yes;
        const int x = X + 16 + i * 58, y = Y + 38;
        const char *label = rr_tr(i ? "Yes" : "No");
        const int width = rr_menu_block_width(label, 1);
        if (selected) {
            rr_menu_box(ren, ox, oy, unit, x, y, 50, 15, RR_MENU_GOLD, 255);
            rr_menu_box(ren, ox, oy, unit, x + 1, y + 1, 48, 13, RR_MENU_SELECT, 255);
            rr_menu_block(ren, ox, oy, unit, x + (50 - width) / 2, y + 5, 1, label, RR_MENU_ACCENT);
        } else {
            rr_menu_box(ren, ox, oy, unit, x, y, 50, 15, RR_MENU_SHADE, 255);
            rr_menu_box(ren, ox, oy, unit, x + 1, y + 1, 48, 13, 26, 24, 20, 255);
            rr_menu_block(ren, ox, oy, unit, x + (50 - width) / 2, y + 5, 1, label, RR_MENU_HINT);
        }
    }
    rr_menu_end(ren);
}

/* One line of the help: "F5  Reduce sprite flicker", or several keys on a line ("P  Pause | Enter  Start"). A part that starts
 * with a key (a function key, a key followed by two spaces, a combination with '+') gets a key cap; any other line is plain. */
static bool help_key(const char *part, size_t length, size_t *key) {
    size_t n = 0;
    while (n < length && part[n] != ' ') ++n;
    if (!n || n >= length || n > 12) return false;
    const bool function = part[0] == 'F' && n >= 2 && part[1] >= '0' && part[1] <= '9';
    const bool spaced = n + 1 < length && part[n + 1] == ' ';
    if (!function && !spaced && !memchr(part, '+', n)) return false;
    *key = n;
    return true;
}
static void help_line(const RrhkMenuCtx *ctx, int y, const char *text) {
    enum { COLUMN = 38 };
    int x = 14;
    bool first = true;
    while (*text) {
        const char *end = strstr(text, " | ");
        size_t length = end ? (size_t)(end - text) : strlen(text), key = 0;
        char word[100], cap[16];
        if (help_key(text, length, &key)) {
            memcpy(cap, text, key); cap[key] = 0;
            x += rr_menu_keycap(ctx->renderer, ctx->ox, ctx->oy, ctx->unit, x, y, cap) + 3;
            if (first && x < COLUMN) x = COLUMN;
            while (key < length && text[key] == ' ') ++key;
        }
        size_t n = length - key < sizeof word ? length - key : sizeof word - 1;
        memcpy(word, text + key, n); word[n] = 0;
        const int room = 242 - x, width = (int)n * 5;
        rr_menu_text_plain(ctx->renderer, ctx->ox, ctx->oy, ctx->unit, x, y, room > 0 ? room : 1, word, RR_MENU_GOLD);
        x += (width < room ? width : room) + 8;
        first = false;
        text = end ? end + 3 : text + length;
    }
}

void rrhk_menu_draw(SDL_Renderer *ren) {
    const RrhkMachine *m = rrhk.machine;
    /* A menu left another way (a quick state loaded, a restart, the help opened over a page) forgets the tiles. */
    if (rrhk.menu != RRHK_MENU_HUB && rrhk.menu != RRHK_MENU_GRAPHICS && !rrhk_pages_open(rrhk.menu)) { from_hub = false; hub_parent = 0; }
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
    if (rrhk.menu == RRHK_MENU_GRAPHICS) {
        rrhk_graphics_draw(ren);
        return;
    }
    RrhkMenuCtx ctx = {ren, 0, 0, 0};
    rr_menu_layout(ren, &ctx.ox, &ctx.oy, &ctx.unit);
    const int ox = ctx.ox, oy = ctx.oy, unit = ctx.unit;
    if (rrhk.menu == RRHK_MENU_QUIT) {      /* over the game picture, or over the Pause menu it was asked from */
        quit_draw(ren, ox, oy, unit);
        return;
    }
    rr_menu_begin(ren, ox, oy, unit);
    char heading[64], missing[80] = "";
    int status_y = RR_MENU_LAST_LINE;
    snprintf(heading, sizeof(heading), rr_tr(rrhk.gamepad_page ? "Player %d - Gamepad" : "Player %d - Keyboard"), rrhk.player + 1);
    /* The head of each menu (1.7.4): the mark and large letters where the body starts lower (help, the F2 tiles, Pause), a small
     * icon and small letters on the title line for the pages whose rows start at RR_MENU_FIRST_LINE. */
    if (rrhk.menu == RRHK_MENU_CONTROLS)
        rr_menu_header_compact(ren, ox, oy, unit, heading, rrhk.gamepad_page ? RR_ICON_GAMEPAD_SMALL : RR_ICON_KEYBOARD_SMALL);
    else if (rrhk.menu == RRHK_MENU_PAGE) rr_menu_header_compact(ren, ox, oy, unit, rr_tr(m->page->title), -1);
    else if (rrhk.menu == RRHK_MENU_PAUSE) rr_menu_header(ren, ox, oy, unit, "Retro-Recomp", NULL);
    if (rrhk.menu == RRHK_MENU_HUB) hub_draw(&ctx);
    else if (rrhk.menu == RRHK_MENU_PAUSE) {
        if (m->pause_page) m->pause_page(&rrhk, &ctx);
    } else if (rrhk.menu == RRHK_MENU_HELP && m->help_page && m->help_page(&rrhk, &ctx)) {
        /* the machine drew a whole page of its own, from RR_MENU_FIRST_LINE (X68000: Tab) */
        rr_menu_header_compact(ren, ox, oy, unit, rrhk_tr("RetroRecomp - Help", "RetroRecomp - Aide"), -1);
    } else if (rrhk.menu == RRHK_MENU_HELP) {
        rr_menu_header(ren, ox, oy, unit, "Retro-Recomp", rr_tr("Help"));
        /* One line per function key, then the console's own controls. */
        const char *lines[16]; int count = 0;
        char fire[64];
        snprintf(fire, sizeof(fire), rr_tr("F6  Autofire: %s"), rr_tr(rrhk.autofire ? "ON" : "OFF"));
        lines[count++] = rr_tr("F1  Help | Shift+F1 Restart");
        lines[count++] = rr_tr("F2  Controls & options");
        lines[count++] = rr_tr(m->gfx_option_count > 0 ? "F3  Graphics options" : "F3  Next filter");
        lines[count++] = rr_tr("F4  Window / Pixel / Fit / Stretched");
        if (m->help_lines) m->help_lines(0, lines, &count);
        lines[count++] = fire;
        lines[count++] = rr_tr("F7  Next language");
        /* F8 and F9 share a line (1.7.4): the head of the page is taller, and the longest help (a console with four lines of
         * its own, then two of controls) still ends inside the panel. */
        char states[120];
        snprintf(states, sizeof states, "%s | %s", rr_tr("F8  Save game state"), rr_tr("F9  Load game state"));
        lines[count++] = states;
        if (m->help_lines) m->help_lines(1, lines, &count);
        lines[count++] = rr_tr("Tab  Fast-forward | `  Max speed | M  Mute");   /* decision D12: on every console */
        lines[count++] = rr_feedback_label();
        lines[count++] = rrhk_tr("Esc  Quit (close menus first)", "Echap  Quitter (fermer les menus)");
        int y = 36;
        for (int i = 0; i < count; ++i, y += RR_MENU_LINE) help_line(&ctx, y, rr_tr(lines[i]));
        rr_menu_box(ren, ox, oy, unit, 14, y + 1, 228, 1, RR_MENU_SHADE, 255);
        y += 4;
        m->help_controls(&rrhk, &ctx, y);
    } else if (rrhk.menu == RRHK_MENU_CONTROLS) {
        /* Every control fits on the page, up to fifteen rows; player 1's
         * pages end with the quit and restart combinations. Past fifteen rows (1.7.0: up to twenty actions) the page
         * scrolls: fifteen rows at a time around the selected one, ^ and v at the right edge when more lie above or below. */
        char value[80];
        const int rows = rrhk_page_rows(), shown = rows < PAGE_ROWS ? rows : PAGE_ROWS;
        enum { ICON_X = 20, NAME_X = 32, VALUE_X = 104 };     /* 1.7.5: each row has its icon before the name */
        const int first = rrhk_page_scroll();
        /* Fifteen rows (twelve actions, the combinations and the Gamepad row) push the hint and the status down. */
        const int hint_y = shown > 14 ? 173 : RR_MENU_HINT_LINE;
        if (shown > 14) status_y = 182;
        const int stick = stick_row();
        if (first > 0) rr_menu_text(ren, ox, oy, unit, 246, RR_MENU_FIRST_LINE, "^", RR_MENU_HINT);
        if (first + shown < rows) rr_menu_text(ren, ox, oy, unit, 246, RR_MENU_FIRST_LINE + (shown - 1) * RR_MENU_LINE, "v", RR_MENU_HINT);
        const int extra = rrhk_pad_rows_here();
        for (int r = first; r < first + shown; ++r) {
            const int a = r - extra;       /* the action or combination of the row; below 0, a machine row */
            int y = RR_MENU_FIRST_LINE + (r - first) * RR_MENU_LINE;
            if (r == rrhk.row) rr_menu_box(ren, ox, oy, unit, 12, y, 232, RR_MENU_LINE, RR_MENU_SELECT, 255);
            const RrhkPadRow *own = rrhk_pad_row_at(r);
            if (own) {      /* a machine row: its icon, its name, its value */
                const int v = own->get ? own->get() : 0;
                rrhk_draw_icon(ren, ox, oy, unit, ICON_X, y, own->icon ? own->icon() : RR_ICON_ROW_GENERIC, NULL);
                if (r == rrhk.row) rr_menu_text(ren, ox, oy, unit, 14, y, ">", RR_MENU_ACCENT);
                if (r == rrhk.row) rr_menu_text_plain(ren, ox, oy, unit, NAME_X, y, VALUE_X - NAME_X - 4, rr_tr(own->label), RR_MENU_ACCENT);
                else rr_menu_text_plain(ren, ox, oy, unit, NAME_X, y, VALUE_X - NAME_X - 4, rr_tr(own->label), RR_MENU_GOLD);
                rr_menu_text_plain(ren, ox, oy, unit, VALUE_X + 2, y, 240 - VALUE_X,
                                   rr_tr(own->values[v >= 0 && v < own->count ? v : 0]), RR_MENU_GOLD);
                continue;
            }
            const char *name;
            bool cap = false, waiting = false;      /* the value is a key or a button: drawn as a key cap */
            int icon = RR_ICON_ROW_GENERIC;
            char letters[4] = "";
            if (rrhk.gamepad_page && r == rows - 1 - stick) {
                rrhk_pad_value(value, sizeof value, rrhk.player);
                name = rr_tr("Gamepad");
                icon = RR_ICON_ROW_GAMEPAD;
            } else if (stick && r == rows - 1) {
                /* "Stick dead zone: %s": the name is what stands before the colon */
                static char dead[48];
                snprintf(dead, sizeof dead, rr_tr("Stick dead zone: %s"), "");
                for (int i = (int)strlen(dead) - 1; i >= 0 && (dead[i] == ' ' || dead[i] == ':'); --i) dead[i] = 0;
                snprintf(value, sizeof value, "%d%%", rrhk.deadzone[rrhk.player]);
                name = dead;
                icon = RR_ICON_ROW_STICK;
            } else if (a >= m->action_count) {
                rrhk_combo_value(value, sizeof value, a - m->action_count, rrhk.gamepad_page != 0);
                name = rrhk_combo_label(a - m->action_count);
                icon = rrhk_combo_icon(a - m->action_count);
                cap = rrhk_combo_set(a - m->action_count, rrhk.gamepad_page != 0) && !rrhk_combo_capturing(a - m->action_count, rrhk.gamepad_page != 0);
                waiting = rrhk_combo_capturing(a - m->action_count, rrhk.gamepad_page != 0);
            } else {
                const SDL_GameControllerButton pad = rrhk.buttons[rrhk.player][a];
                const char *button = !rrhk.gamepad_page ? NULL :
                    pad == RRHK_PAD_LEFT_TRIGGER ? "L2" : pad == RRHK_PAD_RIGHT_TRIGGER ? "R2" :
                    pad >= 0 && pad < SDL_CONTROLLER_BUTTON_MAX ? rr_menu_pad_name(pad) : NULL;
                const char *bound = rrhk.gamepad_page ? (button ? button : "-") :
                    rrhk.keys[rrhk.player][a] == SDL_SCANCODE_UNKNOWN ? "-" : rr_keyboard_name(rrhk.keys[rrhk.player][a]);
                waiting = rrhk.capturing && r == rrhk.row;
                cap = !waiting && strcmp(bound, "-") != 0;
                snprintf(value, sizeof value, "%s", waiting ? rrhk_tr("Press a control...", "Appuie sur une touche...") : rr_tr(bound));
                name = rr_tr(m->actions[a].name);
                icon = rrhk_action_icon(m->actions[a].name, letters);
            }
            rrhk_draw_icon(ren, ox, oy, unit, ICON_X, y, icon, letters);
            if (r == rrhk.row) rr_menu_text(ren, ox, oy, unit, 14, y, ">", RR_MENU_ACCENT);
            if (r == rrhk.row) rr_menu_text_plain(ren, ox, oy, unit, NAME_X, y, VALUE_X - NAME_X - 4, name, RR_MENU_ACCENT);
            else rr_menu_text_plain(ren, ox, oy, unit, NAME_X, y, VALUE_X - NAME_X - 4, name, RR_MENU_GOLD);
            if (cap && rr_menu_text_width(value) + 4 <= 242 - VALUE_X) rr_menu_keycap(ren, ox, oy, unit, VALUE_X, y, value);
            else if (waiting) rr_menu_text_plain(ren, ox, oy, unit, VALUE_X + 2, y, 240 - VALUE_X, value, RR_MENU_ACCENT);
            else rr_menu_text_plain(ren, ox, oy, unit, VALUE_X + 2, y, 240 - VALUE_X, value, RR_MENU_GOLD);
        }
        {
            const char *hint = rrhk_device_row() ? rr_tr("Enter: change gamepad | Delete: Automatic") :
                rrhk_deadzone_row() ? rr_tr("Enter / A: change") :
                rrhk_pad_row_at(rrhk.row) ? rr_tr("Enter / A: change") :
                rrhk_action_row() >= m->action_count ? rrhk_combo_hint(rrhk_action_row() - m->action_count, rrhk.gamepad_page != 0) :
                rrhk.capturing ? rr_tr("Esc: cancel binding") : rr_tr("Enter: remap | Left/Right: page");
            rr_menu_hints(ren, ox, oy, unit, 14, hint_y, 228, hint, RR_MENU_HINT);
        }
        /* A binding or a combination waits for the selected player's own pad (divergence 3): say so when that
         * player has none. */
        if ((rrhk.capturing || rrhk_combo_capturing_pad()) && rrhk.gamepad_page && !rrhk.pads[rrhk.player])
            snprintf(missing, sizeof missing, rr_tr("No gamepad for player %d"), rrhk.player + 1);
    } else if (rrhk.menu == RRHK_MENU_PAGE) {
        if (m->page && m->page->draw) m->page->draw(&rrhk, &ctx);
    }
    if (rrhk.menu == RRHK_MENU_HELP) rr_menu_build_footer(ren, ox, oy, unit);
    else if (missing[0]) rrhk_menu_line(&ctx, status_y, missing);
    else if (rrhk.status[0] && rrhk.menu != RRHK_MENU_HUB) rrhk_menu_line(&ctx, status_y, rrhk.status);
    rr_menu_end(ren);
}

/* ---- Row icons of the menus (1.7.5) ----
 * A 9 x 9 pictogram at the left of each row of the control pages, the options page and the graphics page, drawn by retro_menu.c
 * with the F2 tiles' icons (RR_ICON_ROW_*); a face button is the ring with its letters inside. Which icon a row gets is data: the
 * English name of a machine's control, the key of an option row (rrhk_options.c); a row the kit does not know gets the generic
 * one (a small gem), never nothing. */
/* The letter of a face button from its control's name: "Button A", "A", "Trigger B", "Button 3", "L1", "II", the four
 * PlayStation shapes. Up to two letters (or the narrow I of roman numerals) fit in the ring; anything longer is no button. */
static bool button_letters(const char *name, char out[4]) {
    static const struct { const char *name, *letters; } shapes[] = {
        {"Triangle", "^"}, {"Circle", "o"}, {"Square", "["}, {"Cross", "x"}};
    for (size_t i = 0; i < sizeof shapes / sizeof shapes[0]; ++i)
        if (!strcmp(name, shapes[i].name)) { strcpy(out, shapes[i].letters); return true; }
    if (!strncmp(name, "Button ", 7)) name += 7;
    else if (!strncmp(name, "Trigger ", 8)) name += 8;
    const size_t length = strlen(name);
    if (length == 0 || length > 3) return false;
    bool roman = true;
    for (size_t i = 0; i < length; ++i) if (name[i] != 'I' && name[i] != 'V') roman = false;
    if (length == 3 && !roman) return false;
    for (size_t i = 0; i < length; ++i) {
        const char c = roman && length > 1 && name[i] == 'I' ? 'i' : name[i];
        out[i] = c;
    }
    out[length] = 0;
    return rr_menu_button_letters(out);
}

int rrhk_action_icon(const char *name, char letters[4]) {
    static const struct { const char *prefix; int icon; } named[] = {
        {"Up", RR_ICON_ROW_UP}, {"Down", RR_ICON_ROW_DOWN}, {"Left", RR_ICON_ROW_LEFT}, {"Right", RR_ICON_ROW_RIGHT},
        {"Stick up", RR_ICON_ROW_UP}, {"Stick down", RR_ICON_ROW_DOWN}, {"Stick left", RR_ICON_ROW_LEFT}, {"Stick right", RR_ICON_ROW_RIGHT},
        {"C-Up", RR_ICON_ROW_UP}, {"C-Down", RR_ICON_ROW_DOWN}, {"C-Left", RR_ICON_ROW_LEFT}, {"C-Right", RR_ICON_ROW_RIGHT},
        {"Start", RR_ICON_ROW_START}, {"Game Start", RR_ICON_ROW_START}, {"Run", RR_ICON_ROW_START},
        {"Select", RR_ICON_ROW_SELECT}, {"Mode", RR_ICON_ROW_SELECT}, {"Coin", RR_ICON_ROW_COIN},
        {"Pause", RR_ICON_ROW_PAUSE}, {"Analog", RR_ICON_ROW_STICK}};
    letters[0] = 0;
    if (!name) return RR_ICON_ROW_GENERIC;
    for (size_t i = 0; i < sizeof named / sizeof named[0]; ++i) {
        const size_t n = strlen(named[i].prefix);
        /* "Start (SPACE)", "Pause/Menu", "Start/Menu": the word, then a space, a slash or the end */
        if (!strncmp(name, named[i].prefix, n) && (!name[n] || name[n] == ' ' || name[n] == '/')) return named[i].icon;
    }
    return button_letters(name, letters) ? RR_ICON_ROW_BUTTON : RR_ICON_ROW_GENERIC;
}

void rrhk_draw_icon(SDL_Renderer *r, int ox, int oy, int unit, int x, int y, int icon, const char *letters) {
    if (icon == RR_ICON_ROW_BUTTON) rr_menu_button(r, ox, oy, unit, x, y, letters);
    else rr_menu_icon(r, ox, oy, unit, x, y, icon, false);
}

void rrhk_menu_icon(const RrhkMenuCtx *ctx, int x, int y, int icon) {
    rr_menu_icon(ctx->renderer, ctx->ox, ctx->oy, ctx->unit, x, y, icon, false);
}

/* The combinations below player 1's controls: Quit, Restart (1.7.5: then Quick save and Quick load). */
int rrhk_combo_icon(int index) {
    static const int icons[] = {RR_ICON_ROW_QUIT, RR_ICON_ROW_RESTART, RR_ICON_ROW_SAVE, RR_ICON_ROW_LOAD};
    return index >= 0 && index < (int)(sizeof icons / sizeof icons[0]) ? icons[index] : RR_ICON_ROW_GENERIC;
}

/* A machine's graphics option (the F3 page of the 3D machines) by its English name: the ones about the picture's size and shape
 * get the screen, the others the generic gem. */
int rrhk_gfx_icon(const char *name) {
    static const char *const screen[] = {"Aspect ratio", "Internal resolution", "Overscan crop"};
    for (size_t i = 0; name && i < sizeof screen / sizeof screen[0]; ++i) if (!strcmp(name, screen[i])) return RR_ICON_ROW_DISPLAY;
    return RR_ICON_ROW_GENERIC;
}
