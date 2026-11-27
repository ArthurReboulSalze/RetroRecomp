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

/* ---- The CRT and LCD looks (HOST_KIT D35), drawn with SDL_Renderer only: no shader, every driver ----
 * CRT: the picture with sharp lines and a soft horizontal blend, a brightness boost (what the mask and the gaps take back),
 * one beam per console line, a glow (a blurred copy added), the vignette and rounded corners, then flat or through the curve
 * (a grid of triangles), then the phosphor mask in screen space. LCD: the picture in whole cells with a dim grid.
 * On SDL's software renderer (no graphics card) the CRT keeps the picture, the beams and the mask only, and is drawn flat:
 * its triangles are sampled nearest there, which steps the curved lines. The overlays are made once per size. */
enum { RR_LOOK_CRT_FLAT, RR_LOOK_CRT_CURVED, RR_LOOK_LCD };
typedef struct RrLook {
    SDL_Texture *rows, *picture, *glow, *beams, *frame, *mask, *grid;
    int rows_w, rows_h, picture_w, picture_h, glow_w, glow_h, beams_h, beams_lines, frame_w, frame_h, frame_kind;
    int mask_w, mask_h, mask_kind, grid_w, grid_h, grid_sw, grid_sh;
} RrLook;

static void rr_look_destroy(RrLook *look) {
    SDL_Texture *all[] = {look->rows, look->picture, look->glow, look->beams, look->frame, look->mask, look->grid};
    for (size_t i = 0; i < sizeof all / sizeof all[0]; ++i) if (all[i]) SDL_DestroyTexture(all[i]);
    SDL_memset(look, 0, sizeof *look);
}

/* A render target of w x h, made again when the size changes. */
static SDL_Texture *rr_look_target(SDL_Renderer *renderer, SDL_Texture **slot, int *sw, int *sh, int w, int h) {
    if (*slot && *sw == w && *sh == h) return *slot;
    if (*slot) SDL_DestroyTexture(*slot);
    *slot = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_TARGET, w, h);
    *sw = *slot ? w : 0; *sh = *slot ? h : 0;
    return *slot;
}

/* A static overlay filled by a texel function, made again when its key changes. */
typedef uint32_t (*RrLookTexel)(int x, int y, const int *args);
static SDL_Texture *rr_look_overlay(SDL_Renderer *renderer, SDL_Texture **slot, int w, int h, SDL_BlendMode blend,
                                    SDL_ScaleMode scale, RrLookTexel texel, const int *args) {
    uint32_t *pixels = (uint32_t *)SDL_malloc((size_t)w * h * sizeof(uint32_t));
    if (!pixels) return NULL;
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x) pixels[(size_t)y * w + x] = texel(x, y, args);
    SDL_Texture *texture = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STATIC, w, h);
    const int ready = texture && SDL_UpdateTexture(texture, NULL, pixels, w * (int)sizeof(uint32_t)) == 0 &&
                      SDL_SetTextureBlendMode(texture, blend) == 0 && SDL_SetTextureScaleMode(texture, scale) == 0;
    SDL_free(pixels);
    if (!ready) { if (texture) SDL_DestroyTexture(texture); return NULL; }
    if (*slot) SDL_DestroyTexture(*slot);
    *slot = texture;
    return texture;
}
static uint32_t rr_look_beam_texel(int x, int y, const int *a) { (void)x; return (uint32_t)rr_crt_beam_alpha(y, a[0], a[1]) << 24; }
static uint32_t rr_look_mask_texel(int x, int y, const int *a) { return rr_crt_mask_texel(x, y, a[0]); }
static uint32_t rr_look_frame_texel(int x, int y, const int *a) {
    return rr_crt_frame_texel(x, y, a[0], a[1], a[2] ? 0.06 : 0.0105, a[2] ? 0.45 : 0.25);
}
static uint32_t rr_look_grid_texel(int x, int y, const int *a) { return rr_lcd_texel(x, y, a[0], a[1], a[2], a[3]); }

/* Cells of at least three pixels: below that the LCD grid would hide the picture, and the look shows it plain. */
static bool rr_look_lcd_fits(const SDL_Rect *dst, int source_w, int source_h) {
    return source_w > 0 && source_h > 0 && dst->w >= 3 * source_w && dst->h >= 3 * source_h;
}

/* The picture (curved or flat) of B into dst, through a grid of triangles for the curve. */
static void rr_look_curve(SDL_Renderer *renderer, SDL_Texture *b, const SDL_Rect *dst) {
    enum { GX = 48, GY = 36 };
    static SDL_Vertex v[(GX + 1) * (GY + 1)];
    static int idx[GX * GY * 6];
    for (int j = 0; j <= GY; ++j)
        for (int i = 0; i <= GX; ++i) {
            double px, py;
            rr_crt_warp_solve((double)i / GX * 2 - 1, (double)j / GY * 2 - 1, 0.031, 0.041, &px, &py);
            SDL_Vertex *q = &v[j * (GX + 1) + i];
            q->position.x = (float)(dst->x + (px + 1) * 0.5 * dst->w);
            q->position.y = (float)(dst->y + (py + 1) * 0.5 * dst->h);
            q->tex_coord.x = (float)i / GX; q->tex_coord.y = (float)j / GY;
            q->color.r = q->color.g = q->color.b = q->color.a = 255;
        }
    int n = 0;
    for (int j = 0; j < GY; ++j)
        for (int i = 0; i < GX; ++i) {
            const int a = j * (GX + 1) + i, c = a + GX + 1;
            idx[n++] = a; idx[n++] = a + 1; idx[n++] = c; idx[n++] = a + 1; idx[n++] = c + 1; idx[n++] = c;
        }
    SDL_RenderGeometry(renderer, b, v, (GX + 1) * (GY + 1), idx, n);
}

/* Draw the picture (source of texture) into dst with a look. lines: the console's lines in the picture (beams);
 * software: SDL's software renderer. false: the look could not be drawn (no texture): the caller draws the picture plain. */
static bool rr_look_draw(SDL_Renderer *renderer, RrLook *look, SDL_Texture *texture, const SDL_Rect *source,
                         const SDL_Rect *dst, int lines, int kind, bool software) {
    if (dst->w <= 0 || dst->h <= 0 || source->w <= 0 || source->h <= 0) return false;
    if (kind == RR_LOOK_LCD) {
        if (!rr_look_lcd_fits(dst, source->w, source->h)) return false;
        if (!look->grid || look->grid_w != dst->w || look->grid_h != dst->h || look->grid_sw != source->w || look->grid_sh != source->h) {
            const int args[4] = {dst->w, dst->h, source->w, source->h};
            if (!rr_look_overlay(renderer, &look->grid, dst->w, dst->h, SDL_BLENDMODE_MOD, SDL_ScaleModeNearest, rr_look_grid_texel, args))
                return false;
            look->grid_w = dst->w; look->grid_h = dst->h; look->grid_sw = source->w; look->grid_sh = source->h;
        }
        SDL_RenderCopy(renderer, texture, source, dst);
        SDL_RenderCopy(renderer, look->grid, NULL, dst);
        return true;
    }
    int out_w = 0, out_h = 0;
    SDL_Texture *const previous = SDL_GetRenderTarget(renderer);
    if (previous) SDL_QueryTexture(previous, NULL, NULL, &out_w, &out_h);
    else SDL_GetRendererOutputSize(renderer, &out_w, &out_h);
    const int mask_kind = kind == RR_LOOK_CRT_CURVED ? 1 : 0;
    if (!look->beams || look->beams_h != dst->h || look->beams_lines != lines) {
        const int args[2] = {dst->h, lines};
        if (!rr_look_overlay(renderer, &look->beams, 1, dst->h, SDL_BLENDMODE_BLEND, SDL_ScaleModeNearest, rr_look_beam_texel, args))
            return false;
        look->beams_h = dst->h; look->beams_lines = lines;
    }
    if (!look->mask || look->mask_w != out_w || look->mask_h != out_h || look->mask_kind != mask_kind) {
        const int args[1] = {mask_kind};
        if (!rr_look_overlay(renderer, &look->mask, out_w, out_h, SDL_BLENDMODE_MOD, SDL_ScaleModeNearest, rr_look_mask_texel, args))
            return false;
        look->mask_w = out_w; look->mask_h = out_h; look->mask_kind = mask_kind;
    }
    SDL_RendererInfo info;
    const bool targets = SDL_GetRendererInfo(renderer, &info) == 0 && (info.flags & SDL_RENDERER_TARGETTEXTURE);
    if (software || !targets) {
        /* light: the picture, the same brightness boost (added once more, x1.45, clipped), the beams, the mask; flat */
        SDL_RenderCopy(renderer, texture, source, dst);
        SDL_BlendMode kept = SDL_BLENDMODE_NONE;
        Uint8 r = 255, g = 255, b = 255;
        SDL_GetTextureBlendMode(texture, &kept); SDL_GetTextureColorMod(texture, &r, &g, &b);
        if (SDL_SetTextureBlendMode(texture, SDL_BLENDMODE_ADD) == 0) {
            SDL_SetTextureColorMod(texture, 115, 115, 115);
            SDL_RenderCopy(renderer, texture, source, dst);
        }
        SDL_SetTextureBlendMode(texture, kept); SDL_SetTextureColorMod(texture, r, g, b);
        SDL_RenderCopy(renderer, look->beams, NULL, dst);
        SDL_RenderCopy(renderer, look->mask, dst, dst);
        return true;
    }
    if (!look->frame || look->frame_w != dst->w || look->frame_h != dst->h || look->frame_kind != kind) {
        const int args[3] = {dst->w, dst->h, kind == RR_LOOK_CRT_CURVED};
        if (!rr_look_overlay(renderer, &look->frame, dst->w, dst->h, SDL_BLENDMODE_MOD, SDL_ScaleModeLinear, rr_look_frame_texel, args))
            return false;
        look->frame_w = dst->w; look->frame_h = dst->h; look->frame_kind = kind;
    }
    SDL_Texture *rows = rr_look_target(renderer, &look->rows, &look->rows_w, &look->rows_h, source->w, dst->h);
    SDL_Texture *b = rr_look_target(renderer, &look->picture, &look->picture_w, &look->picture_h, dst->w, dst->h);
    SDL_Texture *glow = rr_look_target(renderer, &look->glow, &look->glow_w, &look->glow_h, SDL_max(dst->w / 8, 1), SDL_max(dst->h / 8, 1));
    if (!rows || !b || !glow) return false;
    /* sharp lines vertically (nearest to source->w x dst->h), soft across (that copy stretched linear). The copy keeps the
     * colours and makes every pixel opaque (whatever alpha the machine's picture carries), so the additions below count. */
    SDL_BlendMode kept = SDL_BLENDMODE_NONE;
    SDL_GetTextureBlendMode(texture, &kept);
    SDL_SetRenderTarget(renderer, rows);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255); SDL_RenderClear(renderer);
    const SDL_BlendMode colours_only = SDL_ComposeCustomBlendMode(SDL_BLENDFACTOR_ONE, SDL_BLENDFACTOR_ZERO, SDL_BLENDOPERATION_ADD,
                                                                  SDL_BLENDFACTOR_ZERO, SDL_BLENDFACTOR_ONE, SDL_BLENDOPERATION_ADD);
    if (SDL_SetTextureBlendMode(texture, colours_only) != 0) SDL_SetTextureBlendMode(texture, SDL_BLENDMODE_NONE);
    SDL_RenderCopy(renderer, texture, source, NULL);
    SDL_SetTextureBlendMode(texture, kept);
    SDL_SetTextureScaleMode(rows, SDL_ScaleModeLinear);
    SDL_SetRenderTarget(renderer, b);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255); SDL_RenderClear(renderer);
    SDL_SetTextureBlendMode(rows, SDL_BLENDMODE_NONE); SDL_SetTextureColorMod(rows, 255, 255, 255);
    SDL_RenderCopy(renderer, rows, NULL, NULL);
    SDL_SetTextureBlendMode(rows, SDL_BLENDMODE_ADD); SDL_SetTextureColorMod(rows, 115, 115, 115);   /* x1.45, clipped */
    SDL_RenderCopy(renderer, rows, NULL, NULL);
    SDL_RenderCopy(renderer, look->beams, NULL, NULL);
    /* glow: an eighth-size copy, stretched back linear and added */
    SDL_SetRenderTarget(renderer, glow);
    SDL_SetTextureBlendMode(rows, SDL_BLENDMODE_NONE); SDL_SetTextureColorMod(rows, 255, 255, 255);
    SDL_RenderCopy(renderer, rows, NULL, NULL);
    SDL_SetRenderTarget(renderer, b);
    SDL_SetTextureScaleMode(glow, SDL_ScaleModeLinear);
    SDL_SetTextureBlendMode(glow, SDL_BLENDMODE_ADD); SDL_SetTextureColorMod(glow, 56, 56, 56);
    SDL_RenderCopy(renderer, glow, NULL, NULL);
    SDL_RenderCopy(renderer, look->frame, NULL, NULL);
    /* back to the screen: flat or curved, then the mask over the picture's rectangle */
    SDL_SetRenderTarget(renderer, previous);
    SDL_SetTextureBlendMode(b, SDL_BLENDMODE_NONE);
    SDL_SetTextureScaleMode(b, SDL_ScaleModeLinear);
    if (kind == RR_LOOK_CRT_CURVED) rr_look_curve(renderer, b, dst);
    else SDL_RenderCopy(renderer, b, NULL, dst);
    SDL_RenderCopy(renderer, look->mask, dst, dst);
    return true;
}
#endif
