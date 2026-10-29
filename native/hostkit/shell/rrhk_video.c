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

void rrhk_scale2x(const uint32_t *source, uint32_t *target) {
    const RrhkMachine *m = rrhk.machine;
    int width = m->visible_width(), height = m->visible_height();
    rr_scale2x(source, width, height, m->max_width, target, m->max_width * 2);
    /* Linear sampling at a partial viewport's edge must see the edge color,
     * never the unused part of the maximum-size texture (e.g. 256-wide MD). */
    int pitch = m->max_width * 2;
    if (width < m->max_width)
        for (int y = 0; y < height * 2; ++y)
            target[y * pitch + width * 2] = target[y * pitch + width * 2 - 1];
    if (height < m->max_height)
        memcpy(target + height * 2 * pitch, target + (height * 2 - 1) * pitch,
            (size_t)(width * 2 + (width < m->max_width)) * sizeof(*target));
}

SDL_Rect rrhk_game_rect(SDL_Renderer *renderer) {
    const RrhkMachine *m = rrhk.machine;
    int w, h; SDL_GetRendererOutputSize(renderer, &w, &h);
    SDL_Rect own;
    if (m->game_rect && m->game_rect(w, h, rrhk.fullscreen, &own)) return own;
    int density = m->visible_height() / m->raster_height();
    int horizontal = m->visible_width() / m->display_width();
    if (horizontal > density) density = horizontal;
    /* Divergence 9 (decided, D2): whole pixels, centred, in the window and in the first fullscreen mode; only the second
     * fullscreen mode (Fit) stretches to the largest size that keeps the aspect. */
    Rr16Rect r = rr16_video_rect(w, h, m->display_width(), m->raster_height(),
                                density, rrhk.fullscreen != 2);
    SDL_Rect rect = {r.x, r.y, r.w, r.h};
    return rect;
}

/* The streaming texture of the current filter: twice the size for Scale2x. */
SDL_Texture *rrhk_texture_create(RrhkRun *run) {
    const RrhkMachine *m = run->machine;
    return SDL_CreateTexture(run->ren, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING,
        rrhk.filter == 2 ? m->max_width * 2 : m->max_width, rrhk.filter == 2 ? m->max_height * 2 : m->max_height);
}

/* Draw the last picture, with the filter and the reticle, into the back buffer. */
void rrhk_present_picture(RrhkRun *run) {
    const RrhkMachine *m = run->machine;
    SDL_Renderer *ren = run->ren;
    if (rrhk.filter == 2) { rrhk_scale2x(m->pixels(), run->upscaled); SDL_UpdateTexture(run->tex, NULL, run->upscaled, m->max_width * 2 * 4); }
    else SDL_UpdateTexture(run->tex, NULL, m->pixels(), m->max_width * 4);
    SDL_Rect dst = rrhk_game_rect(ren);
    SDL_SetRenderDrawColor(ren, 0, 0, 0, 255); SDL_RenderClear(ren);
    int texture_scale = rrhk.filter == 2 ? 2 : 1;
    SDL_Rect source = {0, 0, m->visible_width() * texture_scale, m->visible_height() * texture_scale};
    SDL_Texture *smooth = rrhk.filter == 1 ? rr_xbr_update(ren, &run->xbr, m->pixels(), m->visible_width(), m->visible_height(), m->max_width) : NULL;
    if (smooth) SDL_RenderCopy(ren, smooth, NULL, &dst);
    else SDL_RenderCopy(ren, run->tex, &source, &dst);
    if (rrhk.filter == 3) rr_scanlines_draw(ren, &run->scanlines, &dst, m->visible_height());
    rrhk_pointer_draw(ren, &dst);
}
