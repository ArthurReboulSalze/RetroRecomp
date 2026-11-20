/* Picture presentation: texture, filters (sharp, xBR, Scale2x, scanlines),
 * the placement of the picture in the window and the reticle. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdlib.h>
#include <string.h>
#include "scale2x.h"
#include "console16_video.h"
#include "platform_io.h"
#include "runtime_i18n.h"
#include "hostkit/hostkit_internal.h"

/* Scale2x into a store of store_w x store_h source pixels (the target is twice that, store_w * 2 pixels a row). */
static void scale2x_store(const uint32_t *source, int pitch, int store_w, int store_h, int width, int height, uint32_t *target) {
    rr_scale2x(source, width, height, pitch, target, store_w * 2);
    /* Linear sampling at a partial viewport's edge must see the edge color,
     * never the unused part of the maximum-size texture (e.g. 256-wide MD). */
    int target_pitch = store_w * 2;
    if (width < store_w)
        for (int y = 0; y < height * 2; ++y)
            target[y * target_pitch + width * 2] = target[y * target_pitch + width * 2 - 1];
    if (height < store_h)
        memcpy(target + height * 2 * target_pitch, target + (height * 2 - 1) * target_pitch,
            (size_t)(width * 2 + (width < store_w)) * sizeof(*target));
}

void rrhk_scale2x(const uint32_t *source, uint32_t *target) {
    const RrhkMachine *m = rrhk.machine;
    scale2x_store(source, m->max_width, m->max_width, m->max_height, m->visible_width(), m->visible_height(), target);
}

SDL_Rect rrhk_game_rect(SDL_Renderer *renderer) {
    const RrhkMachine *m = rrhk.machine;
    int w, h; SDL_GetRendererOutputSize(renderer, &w, &h);
    SDL_Rect own;
    /* 1.7.4: the stretched mode fills the whole output, the aspect ignored, on every machine. It comes before the machine's own
     * placement (Master System and Game Gear crops, computers' aspect): what the machine shows of its picture is unchanged, the
     * rectangle it is drawn into is the screen. */
    if (rrhk.fullscreen == 3) return (SDL_Rect){0, 0, w, h};
    if (m->game_rect && m->game_rect(w, h, rrhk.fullscreen, &own)) return own;
    int density = m->visible_height() / m->raster_height();
    int horizontal = m->visible_width() / m->display_width();
    if (horizontal > density) density = horizontal;
    /* Scale2x doubles every pixel: from 2x up, whole pairs only. */
    if (m->even_scale2x && rrhk.filter == 2 && density < 2 && w >= 2 * m->display_width() && h >= 2 * m->raster_height()) density = 2;
    /* Divergence 9 (decided, D2): whole pixels, centred, in the window and in the first fullscreen mode; only the second
     * fullscreen mode (Fit) stretches to the largest size that keeps the aspect. */
    /* 1.7.6: a game shown at 16:9 (its own anamorphic widescreen option, RrhkMachine.widescreen) is 16 wide for 9 high */
    const int display_width = m->widescreen && rrhk.widescreen ? (m->raster_height() * 16 + 4) / 9 : m->display_width();
    Rr16Rect r = rr16_video_rect(w, h, display_width, m->raster_height(), density, rrhk.fullscreen != 2);
    SDL_Rect rect = {r.x, r.y, r.w, r.h};
    return rect;
}

/* Scale2x doubles the store. A picture that grows (pixel_pitch) past half the renderer's largest texture is shown without it,
 * and so is one whose Scale2x buffer could not be made. */
static bool doubled_size(const RrhkRun *run) {
    if (rrhk.filter != 2) return false;
    if (!run->machine->pixel_pitch) return true;
    return (!run->limit_w || run->store_w * 2 <= run->limit_w) && (!run->limit_h || run->store_h * 2 <= run->limit_h);
}
static bool doubled(const RrhkRun *run) { return doubled_size(run) && !(run->machine->pixel_pitch && run->double_refused); }

/* Scale2x's buffer for the store (a growing picture only: the others keep the buffer made at open). */
static bool upscaled_room(RrhkRun *run) {
    const size_t need = (size_t)run->store_w * 2 * run->store_h * 2;
    if (need <= run->upscaled_pixels) return true;
    uint32_t *grown = (uint32_t *)realloc(run->upscaled, need * sizeof(uint32_t));
    if (!grown) return false;
    run->upscaled = grown; run->upscaled_pixels = need;
    return true;
}

/* The streaming texture of the current filter: twice the size for Scale2x. A growing picture makes Scale2x's buffer first: if it
 * cannot, the texture is the plain one and the picture is shown without Scale2x (never a doubled texture with no content). */
SDL_Texture *rrhk_texture_create(RrhkRun *run) {
    if (run->machine->pixel_pitch) run->double_refused = doubled_size(run) && !upscaled_room(run);
    const int k = doubled(run) ? 2 : 1;
    return SDL_CreateTexture(run->ren, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, run->store_w * k, run->store_h * k);
}

/* A machine whose picture grows (pixel_pitch, 1.7.0): a larger texture once the picture passes the store, never larger than the
 * renderer takes. The store never shrinks during a run. A store that cannot grow (no texture, or with Scale2x no buffer for it)
 * stays as it was, its texture and buffer untouched: the part that fits is shown, and that size is not tried again until the
 * picture's size changes. */
static void grow_store(RrhkRun *run) {
    const RrhkMachine *m = run->machine;
    int w = m->visible_width(), h = m->visible_height();
    if (run->limit_w && w > run->limit_w) w = run->limit_w;
    if (run->limit_h && h > run->limit_h) h = run->limit_h;
    if (w <= run->store_w && h <= run->store_h) return;
    if (w == run->refused_w && h == run->refused_h) return;
    const int old_w = run->store_w, old_h = run->store_h;
    const bool old_refused = run->double_refused;
    run->store_w = SDL_max(w, run->store_w); run->store_h = SDL_max(h, run->store_h);
    SDL_Texture *texture = rrhk_texture_create(run);
    if (!texture || (doubled_size(run) && run->double_refused && !old_refused)) {
        if (texture) SDL_DestroyTexture(texture);
        run->store_w = old_w; run->store_h = old_h; run->double_refused = old_refused;
        run->refused_w = w; run->refused_h = h;
        return;
    }
    run->refused_w = run->refused_h = 0;
    SDL_SetTextureScaleMode(texture, SDL_ScaleModeNearest);
    SDL_DestroyTexture(run->tex);
    run->tex = texture;
}

/* Draw the last picture, with the filter and the reticle, into the back buffer. */
void rrhk_present_picture(RrhkRun *run) {
    const RrhkMachine *m = run->machine;
    SDL_Renderer *ren = run->ren;
    /* 1.7.7: a machine may have no picture yet (a session reopened by a graphics option, its first frame not run while a menu
     * holds it, or a Restart under a menu): a NULL or zero-size picture shows the game's area black and nothing is read. xBR
     * and Scale2x read the picture themselves and crashed on it (the PlayStation's renderer switch, F3). */
    const uint32_t *pixels = m->pixels();
    int width = m->visible_width(), height = m->visible_height(), pitch = m->max_width;
    if (!pixels || width <= 0 || height <= 0) {
        SDL_SetRenderDrawColor(ren, 0, 0, 0, 255); SDL_RenderClear(ren);
        return;
    }
    if (m->pixel_pitch) {
        /* The rows of the picture are pixel_pitch apart; only the visible part is uploaded (the buffer may be smaller than the store). */
        pitch = m->pixel_pitch();
        grow_store(run);
        width = SDL_min(width, run->store_w); height = SDL_min(height, run->store_h);
        if (doubled(run)) {
            /* the buffer is the store's size: rrhk_texture_create made it before the doubled texture */
            scale2x_store(pixels, pitch, run->store_w, run->store_h, width, height, run->upscaled);
            SDL_Rect area = {0, 0, width * 2 + (width < run->store_w), height * 2 + (height < run->store_h)};
            SDL_UpdateTexture(run->tex, &area, run->upscaled, run->store_w * 2 * 4);
        } else {
            SDL_Rect area = {0, 0, width, height};
            SDL_UpdateTexture(run->tex, &area, pixels, pitch * 4);
        }
    } else if (rrhk.filter == 2) { rrhk_scale2x(pixels, run->upscaled); SDL_UpdateTexture(run->tex, NULL, run->upscaled, m->max_width * 2 * 4); }
    else SDL_UpdateTexture(run->tex, NULL, pixels, m->max_width * 4);
    SDL_Rect dst = rrhk_game_rect(ren);
    SDL_SetRenderDrawColor(ren, 0, 0, 0, 255); SDL_RenderClear(ren);
    int texture_scale = doubled(run) ? 2 : 1;
    SDL_Rect source = {0, 0, width * texture_scale, height * texture_scale};
    SDL_Texture *smooth = rrhk.filter == 1 ? rr_xbr_update(ren, &run->xbr, pixels, width, height, pitch) : NULL;
    if (smooth) SDL_RenderCopy(ren, smooth, NULL, &dst);
    else SDL_RenderCopy(ren, run->tex, &source, &dst);
    /* 1.7.6: one scanline per line of the console (raster_height), not per row of a raised internal resolution (visible_height):
     * a 240-line game drawn at 2x or 4x keeps its 240 dark lines, which show on any screen of 480 rows or more */
    if (rrhk.filter == 3) rr_scanlines_draw(ren, &run->scanlines, &dst, m->raster_height());
    rrhk_pointer_draw(ren, &dst);
}

/* ---- 1.7.7 (HOST_KIT D30): Sync to display. The row, its preference, the decision and the notices; the measurement of the
 * refresh and the pacing are rrhk_main.c's (end_frame). ---- */
RrhkSync rrhk_sync;

bool rrhk_sync_decide(int mode, double refresh_hz, double machine_hz) {
    if (refresh_hz <= 0.0 || machine_hz <= 0.0) return false;
    const double gap = SDL_fabs(machine_hz / refresh_hz - 1.0);
    if (mode == RRHK_SYNC_AUTO) return gap <= RRHK_SYNC_AUTO_GAP;
    if (mode == RRHK_SYNC_LOCKED) return gap <= RR_DRC_BASE_LIMIT;
    return false;
}

void rrhk_sync_load(bool test_run) {
    const int saved = rrhk.read_file[0] ? rr_ini_int(rrhk.video_section, L"sync", RRHK_SYNC_AUTO, rrhk.read_file) : RRHK_SYNC_AUTO;
    memset(&rrhk_sync, 0, sizeof rrhk_sync);
    rrhk_sync.mode = saved >= 0 && saved < RRHK_SYNC_MODES ? saved : RRHK_SYNC_AUTO;
    const char *diagnostic = getenv("SDL_RENDER_VSYNC");
    rrhk_sync.active = !test_run && !(diagnostic && *diagnostic);
    rrhk_sync.remeasure = rrhk_sync.active;
#ifdef _WIN32
    /* Variable refresh: Direct3D 12, whose swap chain allows tearing (SDL 2.32: DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING, presents
     * with DXGI_PRESENT_ALLOW_TEARING when vsync is off); Direct3D 11 otherwise, as before. An SDL_RENDER_DRIVER set by the
     * player still wins (its priority is higher). */
    SDL_SetHint(SDL_HINT_RENDER_DRIVER, rrhk_sync.active && rrhk_sync.mode == RRHK_SYNC_VARIABLE ? "direct3d12" : "direct3d11");
#endif
}

void rrhk_sync_next(void) {
    rrhk_sync.mode = (rrhk_sync.mode + 1) % RRHK_SYNC_MODES;
    rrhk_sync.remeasure = rrhk_sync.active;
    rrhk_sync.announce = true;
    wchar_t value[8];
    swprintf(value, 8, L"%d", rrhk_sync.mode);
    if (!rrhk_write_ready() || !rr_ini_set(rrhk.video_section, L"sync", value, rrhk.ini_file))
        snprintf(rrhk.status, sizeof rrhk.status, "%s", rr_tr("Config unavailable"));
}

void rrhk_sync_value(char *out, size_t size) {
    const char *value;
    switch (rrhk_sync.mode) {
    case RRHK_SYNC_AUTO: value = !rrhk_sync.active ? "Auto" : rrhk_sync.lock ? "Auto (locked)" : "Auto (free)"; break;
    case RRHK_SYNC_LOCKED: value = rrhk_sync.active && !rrhk_sync.lock ? "Locked (free)" : "Locked"; break;
    case RRHK_SYNC_FREE: value = "Free"; break;
    default: value = "Variable refresh"; break;
    }
    snprintf(out, size, "%s", rr_tr(value));
}

/* The outcome of the row or of a measurement, once: what the game now does, with the speed difference when locked. */
void rrhk_sync_notice(void) {
    char text[160], game[16], screen[16], gap[16];
    rrhk_sync.announce = false;
    RrhkNumeric numeric;
    rrhk_numeric_begin(&numeric);       /* the same figures on every machine, whatever locale its engine set */
    snprintf(game, sizeof game, "%.2f", rrhk_sync.machine_hz);
    snprintf(screen, sizeof screen, "%.2f", rrhk_sync.refresh_hz);
    snprintf(gap, sizeof gap, "%+.2f %%", rrhk_sync.machine_hz > 0.0 ? 100.0 * (rrhk_sync.refresh_hz / rrhk_sync.machine_hz - 1.0) : 0.0);
    rrhk_numeric_end(&numeric);
    if (rrhk_sync.mode == RRHK_SYNC_VARIABLE) {
#ifdef _WIN32
        snprintf(text, sizeof text, "%s", rr_tr(rrhk_sync.vrr_renderer ? "Variable refresh: screen follows game" :
                                                "Variable refresh: from the next start"));
#else
        snprintf(text, sizeof text, "%s", rr_tr("Variable refresh: screen follows game"));
#endif
    } else if (rrhk_sync.mode == RRHK_SYNC_FREE) {
        snprintf(text, sizeof text, rr_tr("Free: the game's own %s Hz"), game);
    } else if (rrhk_sync.lock) {
        snprintf(text, sizeof text, rr_tr("Locked: %s Hz, game %s Hz (%s)"), screen, game, gap);
    } else if (rrhk_sync.why && !strcmp(rrhk_sync.why, "far")) {
        snprintf(text, sizeof text, rr_tr("Free: screen %s Hz, game %s Hz"), screen, game);
    } else if (rrhk_sync.why) {
        snprintf(text, sizeof text, "%s", rr_tr(rrhk_sync.why));
    } else return;
    rrhk_notice(text, 3200);
}
