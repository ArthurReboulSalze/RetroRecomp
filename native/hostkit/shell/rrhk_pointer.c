/* Mouse as a pointing device (light guns, Super Scope): mouse to picture
 * coordinates, the reticle, and the gun page of F2. The sensor and port
 * emulation stay in the machine. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdint.h>
#include "platform_io.h"
#include "retro_menu.h"
#include "hostkit/hostkit_internal.h"

void rrhk_pointer_sample(SDL_Window *window, SDL_Renderer *renderer, uint16_t pad) {
    const RrhkMachine *m = rrhk.machine;
    RrhkPointer in = {.x = -1, .y = -1, .offscreen = true};
    int x, y, w, h, rw, rh;
    Uint32 buttons = SDL_GetMouseState(&x, &y);
    SDL_GetWindowSize(window, &w, &h);
    SDL_GetRendererOutputSize(renderer, &rw, &rh);
    SDL_Rect dst = rrhk_game_rect(renderer);
    if (!rrhk.menu && w > 0 && h > 0 &&
        (SDL_GetWindowFlags(window) & SDL_WINDOW_INPUT_FOCUS) &&
        (SDL_GetWindowFlags(window) & SDL_WINDOW_MOUSE_FOCUS)) {
        x = (int)((int64_t)x * rw / w); y = (int)((int64_t)y * rh / h);
        in.offscreen = x < dst.x || y < dst.y || x >= dst.x + dst.w || y >= dst.y + dst.h;
        if (!in.offscreen && dst.w > 0 && dst.h > 0) {
            in.x = (int)((int64_t)(x - dst.x) * m->display_width() / dst.w);
            in.y = (int)((int64_t)(y - dst.y) * m->raster_height() / dst.h);
        }
        in.fire = (buttons & SDL_BUTTON_LMASK) != 0;
        in.aux = (buttons & SDL_BUTTON_RMASK) != 0;
        in.secondary = (buttons & SDL_BUTTON_MMASK) != 0;
        in.start = (pad & m->actions[m->start].bit) != 0;
        in.pause = in.secondary || in.start;
        in.turbo = rrhk.pointer_turbo != 0;
    }
    rrhk.mouse = in;
    m->pointer_input(in);
    SDL_ShowCursor(in.offscreen || rrhk.menu ? SDL_ENABLE : SDL_DISABLE);
}

void rrhk_pointer_draw(SDL_Renderer *renderer, const SDL_Rect *dst) {
    const RrhkMachine *m = rrhk.machine;
    if (!m->pointer || rrhk.menu || rrhk.mouse.offscreen) return;
    int x = dst->x + (int)((rrhk.mouse.x + 0.5) * dst->w / m->display_width());
    int y = dst->y + (int)((rrhk.mouse.y + 0.5) * dst->h / m->raster_height());
    int sx = (int)((double)rrhk.pointer_size * dst->w / m->display_width());
    int sy = (int)((double)rrhk.pointer_size * dst->h / m->raster_height());
    if (sx < 1) sx = 1; if (sy < 1) sy = 1;
    SDL_RenderSetClipRect(renderer, dst);
    SDL_SetRenderDrawColor(renderer, rrhk.pointer_color == 2 ? 0 : 255, rrhk.pointer_color ? 255 : 0, rrhk.pointer_color == 1 ? 255 : 0, 255);
    if (rrhk.pointer_shape == 1) {
        SDL_Rect dot = {x - sx / 2, y - sy / 2, sx, sy}; SDL_RenderFillRect(renderer, &dot);
    } else {
        SDL_Rect horizontal = {x - sx, y - 1, sx * 2 + 1, 2};
        SDL_Rect vertical = {x - 1, y - sy, 2, sy * 2 + 1};
        SDL_RenderFillRect(renderer, &horizontal);
        SDL_RenderFillRect(renderer, &vertical);
    }
    SDL_RenderSetClipRect(renderer, NULL);
}

static void pointer_option(RrhkUi *ui, int direction) {
    if (ui->row == 0) ui->pointer_shape = !ui->pointer_shape;
    const int largest = ui->machine->pointer_max ? ui->machine->pointer_max : 12;
    if (ui->row == 1) ui->pointer_size = (ui->pointer_size - 1 + direction + largest) % largest + 1;
    if (ui->row == 2) ui->pointer_color = (ui->pointer_color + direction + 3) % 3;
    if (ui->row == 3) ui->pointer_turbo = !ui->pointer_turbo;
    if (!ui->ini_file[0]) return;
    const wchar_t *labels[] = {L"shape", L"size", L"color", L"turbo"};
    int values[] = {ui->pointer_shape, ui->pointer_size, ui->pointer_color, ui->pointer_turbo};
    wchar_t value[16]; swprintf(value, 16, L"%d", values[ui->row]);
    rr_mkdir(ui->data_dir);
    rr_ini_set(ui->pointer_section, labels[ui->row], value, ui->ini_file);
}

static int pointer_rows(const RrhkUi *ui) { return ui->machine->pointer == RRHK_POINTER_SCOPE ? 4 : 3; }

/* Left/Right turn pages: Enter / + choose the next value, - the previous. */
static void pointer_key(RrhkUi *ui, SDL_Scancode key) {
    int rows = pointer_rows(ui);
    if (key == SDL_SCANCODE_UP) ui->row = (ui->row + rows - 1) % rows;
    else if (key == SDL_SCANCODE_DOWN) ui->row = (ui->row + 1) % rows;
    else if (key == SDL_SCANCODE_MINUS || key == SDL_SCANCODE_KP_MINUS) pointer_option(ui, -1);
    else if (key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER || key == SDL_SCANCODE_EQUALS ||
             key == SDL_SCANCODE_KP_PLUS) pointer_option(ui, 1);
}

static void pointer_draw(RrhkUi *ui, const RrhkMenuCtx *ctx) {
    SDL_Renderer *ren = ctx->renderer;
    const int ox = ctx->ox, oy = ctx->oy, unit = ctx->unit;
    char line[100];
    const char *colors[] = {rr_tr("Red"), rr_tr("White"), rr_tr("Green")};
    const int rows = pointer_rows(ui);
    rr_menu_text(ren, ox, oy, unit, 14, 26, ui->machine->pointer == RRHK_POINTER_SCOPE ? "Super Scope" :
        ui->machine->pointer == RRHK_POINTER_JUSTIFIER ? "Justifier" :
        ui->machine->pointer == RRHK_POINTER_ZAPPER ? "Zapper" : "Menacer", RR_MENU_ACCENT);
    for (int i = 0; i < rows; ++i) {
        if (ui->row == i) rr_menu_box(ren, ox, oy, unit, 12, 40 + 22 * i, 232, 20, RR_MENU_SELECT, 255);
        if (i == 0) snprintf(line, sizeof line, "%s: %s", rrhk_tr("Shape", "Forme"), ui->pointer_shape ? rrhk_tr("Dot", "Point") : rrhk_tr("Cross", "Croix"));
        if (i == 1) snprintf(line, sizeof line, "%s: %d", rrhk_tr("Size", "Taille"), ui->pointer_size);
        if (i == 2) snprintf(line, sizeof line, "%s: %s", rrhk_tr("Color", "Couleur"), colors[ui->pointer_color]);
        if (i == 3) snprintf(line, sizeof line, "Scope turbo: %s", ui->pointer_turbo ? "On" : "Off");
        rr_menu_text(ren, ox, oy, unit, 14, 45 + 22 * i, line, RR_MENU_GOLD);
    }
    rr_menu_text(ren, ox, oy, unit, 14, RR_MENU_HINT_LINE, rr_tr("Enter / A / +: next | -: previous"), RR_MENU_GOLD);
    if (!ui->status[0]) rr_menu_text(ren, ox, oy, unit, 14, RR_MENU_LAST_LINE, rr_tr("Left/Right: page | Esc: close"), RR_MENU_GOLD);
}

const RrhkPage rrhk_pointer_page = {"Retro-Recomp - Gun", NULL, pointer_draw, pointer_key};
