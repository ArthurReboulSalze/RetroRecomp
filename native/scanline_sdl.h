/* Shared presentation mask. No guest pixels or timing are changed. */
#ifndef RETRO_SCANLINE_SDL_H
#define RETRO_SCANLINE_SDL_H
#include <SDL.h>
#include <stdlib.h>
#include "scanlines.h"
typedef struct RrScanlineMask {
    SDL_Texture *texture;
    int height, rows;
} RrScanlineMask;
static void rr_scanlines_destroy(RrScanlineMask *mask) {
    if (mask->texture) SDL_DestroyTexture(mask->texture);
    mask->texture = NULL; mask->height = mask->rows = 0;
}
static void rr_scanlines_draw(SDL_Renderer *renderer, RrScanlineMask *mask,
                              const SDL_Rect *dst, int rows) {
    if (rows <= 0 || dst->h < 2 * rows || dst->w <= 0) return;
    if (!mask->texture || mask->height != dst->h || mask->rows != rows) {
        uint32_t *pixels = (uint32_t *)malloc((size_t)dst->h * sizeof(uint32_t));
        if (!pixels) return;
        for (int y = 0; y < dst->h; ++y)
            pixels[y] = (uint32_t)rr_scanline_alpha(y, dst->h, rows) << 24;
        SDL_Texture *texture = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888,
            SDL_TEXTUREACCESS_STATIC, 1, dst->h);
        int ready = texture && SDL_UpdateTexture(texture, NULL, pixels, sizeof(uint32_t)) == 0 &&
            SDL_SetTextureBlendMode(texture, SDL_BLENDMODE_BLEND) == 0 &&
            SDL_SetTextureScaleMode(texture, SDL_ScaleModeNearest) == 0;
        free(pixels);
        if (!ready) { if (texture) SDL_DestroyTexture(texture); return; }
        rr_scanlines_destroy(mask);
        mask->texture = texture; mask->height = dst->h; mask->rows = rows;
    }
    SDL_RenderCopy(renderer, mask->texture, NULL, dst);
}
#endif
