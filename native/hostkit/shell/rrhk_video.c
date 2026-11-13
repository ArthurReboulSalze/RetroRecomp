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
    Rr16Rect r = rr16_video_rect(w, h, m->display_width(), m->raster_height(),
                                density, rrhk.fullscreen != 2);
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
    int width = m->visible_width(), height = m->visible_height(), pitch = m->max_width;
    if (m->pixel_pitch) {
        /* The rows of the picture are pixel_pitch apart; only the visible part is uploaded (the buffer may be smaller than the store). */
        pitch = m->pixel_pitch();
        grow_store(run);
        width = SDL_min(width, run->store_w); height = SDL_min(height, run->store_h);
        if (doubled(run)) {
            /* the buffer is the store's size: rrhk_texture_create made it before the doubled texture */
            scale2x_store(m->pixels(), pitch, run->store_w, run->store_h, width, height, run->upscaled);
            SDL_Rect area = {0, 0, width * 2 + (width < run->store_w), height * 2 + (height < run->store_h)};
            SDL_UpdateTexture(run->tex, &area, run->upscaled, run->store_w * 2 * 4);
        } else {
            SDL_Rect area = {0, 0, width, height};
            SDL_UpdateTexture(run->tex, &area, m->pixels(), pitch * 4);
        }
    } else if (rrhk.filter == 2) { rrhk_scale2x(m->pixels(), run->upscaled); SDL_UpdateTexture(run->tex, NULL, run->upscaled, m->max_width * 2 * 4); }
    else SDL_UpdateTexture(run->tex, NULL, m->pixels(), m->max_width * 4);
    SDL_Rect dst = rrhk_game_rect(ren);
    SDL_SetRenderDrawColor(ren, 0, 0, 0, 255); SDL_RenderClear(ren);
    int texture_scale = doubled(run) ? 2 : 1;
    SDL_Rect source = {0, 0, width * texture_scale, height * texture_scale};
    SDL_Texture *smooth = rrhk.filter == 1 ? rr_xbr_update(ren, &run->xbr, m->pixels(), width, height, pitch) : NULL;
    if (smooth) SDL_RenderCopy(ren, smooth, NULL, &dst);
    else SDL_RenderCopy(ren, run->tex, &source, &dst);
    if (rrhk.filter == 3) rr_scanlines_draw(ren, &run->scanlines, &dst, m->visible_height());
    rrhk_pointer_draw(ren, &dst);
}
