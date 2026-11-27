/* The CRT and LCD looks (HOST_KIT D35), checked without a window: the overlays' values, the curve, the LCD grid, the F3 cycle,
 * then whole looks drawn by SDL's software renderer onto a surface, both the light way (no graphics card) and the full way
 * (render targets: the way a graphics card draws them). Prints one JSON line {"passed": n, "failed": m}. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "scanline_sdl.h"
#include "retro_menu.h"
#include "display_settings.h"

static int passed, failed;
#define CHECK(c) do { if (c) ++passed; else { ++failed; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static void overlay_checks(void) {
    /* beams: dark gaps at 2x and more, none below 2x, none above 300 lines; light at the line's centre, dark between lines */
    CHECK(rr_crt_beam_alpha(0, 191, 192) == 0 && rr_crt_beam_alpha(0, 448, 448) == 0);
    CHECK(rr_crt_beam_alpha(2, 1080, 480) == 0);                      /* 480 lines: fine lines, no gaps */
    int lo = 255, hi = 0;
    for (int y = 0; y < 1080; ++y) { const int a = rr_crt_beam_alpha(y, 1080, 192); if (a < lo) lo = a; if (a > hi) hi = a; }
    CHECK(lo < 40 && hi > 120 && hi <= 204);
    const int centre = rr_crt_beam_alpha((int)(1080.0 / 192 * 10.5), 1080, 192), edge = rr_crt_beam_alpha((int)(1080.0 / 192 * 11) - 1, 1080, 192);
    CHECK(centre < edge);
    CHECK(rr_crt_beam_alpha(-1, 1080, 192) == 0 && rr_crt_beam_alpha(1080, 1080, 192) == 0 && rr_crt_beam_alpha(5, 1080, 0) == 0);
    /* mask: one stripe lit in three, opaque, periodic; the slot mask staggered */
    for (int x = 0; x < 9; ++x) {
        const uint32_t t = rr_crt_mask_texel(x, 0, 0);
        const int lit = ((t >> 16 & 255) == 255) + ((t >> 8 & 255) == 255) + ((t & 255) == 255);
        CHECK((t >> 24) == 255 && lit == 1 && t == rr_crt_mask_texel(x + 3, 7, 0));
    }
    CHECK(rr_crt_mask_texel(0, 0, 1) != rr_crt_mask_texel(0, 3, 1));
    /* frame: white in the middle, black past the rounded corner, a darker edge with the vignette */
    CHECK((rr_crt_frame_texel(320, 240, 640, 480, 0.06, 0.45) & 255) == 255);
    CHECK((rr_crt_frame_texel(0, 0, 640, 480, 0.06, 0.45) & 255) == 0);
    CHECK((rr_crt_frame_texel(0, 240, 640, 480, 0.06, 0.45) & 255) < 255);
    CHECK((rr_crt_frame_texel(0, 0, 640, 480, 0.0, 0.0) & 255) == 255);
    /* the curve: the solved screen point warps back onto the picture point; inside the screen; the centre stays */
    double worst = 0;
    for (int j = 0; j <= 10; ++j)
        for (int i = 0; i <= 10; ++i) {
            const double sx = i / 5.0 - 1, sy = j / 5.0 - 1;
            double px, py;
            rr_crt_warp_solve(sx, sy, 0.031, 0.041, &px, &py);
            const double wx = px * (1 + 0.031 * py * py), wy = py * (1 + 0.041 * px * px);
            worst = fmax(worst, fmax(fabs(wx - sx), fabs(wy - sy)));
            CHECK(fabs(px) <= fabs(sx) + 1e-12 && fabs(py) <= fabs(sy) + 1e-12);
        }
    CHECK(worst < 1e-6);
    /* LCD: at 6x each cell has its gap on the right and bottom, and the cells repeat */
    CHECK((rr_lcd_texel(5, 0, 960, 864, 160, 144) & 255) < 200 && (rr_lcd_texel(0, 5, 960, 864, 160, 144) >> 8 & 255) < 200);
    CHECK((rr_lcd_texel(1, 1, 960, 864, 160, 144) >> 16 & 255) == 255);
    CHECK(rr_lcd_texel(2, 2, 960, 864, 160, 144) == rr_lcd_texel(8, 14, 960, 864, 160, 144));
    SDL_Rect small = {0, 0, 319, 288}, big = {0, 0, 480, 432};
    CHECK(!rr_look_lcd_fits(&small, 160, 144) && rr_look_lcd_fits(&big, 160, 144));
}

static void cycle_checks(void) {
    for (int lcd = 0; lcd < 2; ++lcd) {
        int f = 0, seen = 0, length = 0;
        do { seen |= 1 << f; CHECK(rr_menu_previous_filter(rr_menu_next_filter(f, lcd), lcd) == f); f = rr_menu_next_filter(f, lcd); ++length; }
        while (f != 0 && length < 20);
        CHECK(length == (lcd ? RR_FILTERS : RR_FILTERS - 1));
        CHECK(seen == (lcd ? 0x7f : 0x3f));
    }
    CHECK(rr_menu_next_filter(0, 0) == 2 && rr_menu_next_filter(2, 0) == 3 && rr_menu_next_filter(3, 0) == 1);   /* the old order kept */
    CHECK(rr_menu_next_filter(1, 0) == RR_FILTER_CRT_FLAT && rr_menu_next_filter(RR_FILTER_CRT_CURVED, 0) == 0);
    CHECK(rr_menu_next_filter(RR_FILTER_CRT_CURVED, 1) == RR_FILTER_LCD && rr_menu_next_filter(99, 1) == 0);
}

/* A test picture: 256 x 192, bars, a white line every 8 rows, alpha 0 like some machines' pictures (the looks must not care). */
static SDL_Texture *picture(SDL_Renderer *ren) {
    static uint32_t px[256 * 192];
    for (int y = 0; y < 192; ++y)
        for (int x = 0; x < 256; ++x)
            px[y * 256 + x] = y % 8 == 0 ? 0x00ffffffu : (x / 32 % 2 ? 0x00ff4020u : 0x002040ffu);
    SDL_Texture *t = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, 256, 192);
    SDL_UpdateTexture(t, NULL, px, 256 * 4);
    SDL_SetTextureBlendMode(t, SDL_BLENDMODE_NONE);
    SDL_SetTextureScaleMode(t, SDL_ScaleModeNearest);
    return t;
}

static uint64_t draw(SDL_Surface *canvas, SDL_Renderer *ren, RrLook *look, SDL_Texture *t, int kind, bool software, long *lit, uint32_t *corner) {
    SDL_SetRenderDrawColor(ren, 0, 0, 0, 255); SDL_RenderClear(ren);
    const SDL_Rect source = {0, 0, 256, 192}, dst = {64, 0, 512, 384};
    const bool drawn = rr_look_draw(ren, look, t, &source, &dst, 192, kind, software);
    CHECK(drawn);
    SDL_RenderPresent(ren);
    uint64_t hash = 1469598103934665603ull;
    *lit = 0;
    long outside = 0;
    const uint32_t *p = (const uint32_t *)canvas->pixels;
    for (int y = 0; y < canvas->h; ++y)
        for (int x = 0; x < canvas->w; ++x) {
            const uint32_t v = p[y * (canvas->pitch / 4) + x] & 0xffffff;
            hash = (hash ^ v) * 1099511628211ull;
            if (v) ++*lit;
            if ((x < 64 || x >= 576) && v) ++outside;
        }
    CHECK(outside == 0);                                     /* nothing outside the picture's rectangle */
    *corner = p[0 * (canvas->pitch / 4) + 64] & 0xffffff;
    return hash;
}

static void draw_checks(void) {
    SDL_Surface *canvas = SDL_CreateRGBSurfaceWithFormat(0, 640, 384, 32, SDL_PIXELFORMAT_ARGB8888);
    SDL_Renderer *ren = canvas ? SDL_CreateSoftwareRenderer(canvas) : NULL;
    CHECK(ren != NULL);
    if (!ren) return;
    SDL_Texture *t = picture(ren);
    RrLook look = {0};
    long lit; uint32_t corner;
    for (int pass = 0; pass < 2; ++pass) {       /* light (no graphics card), then full (render targets) */
        const bool software = pass == 0;
        const uint64_t flat = draw(canvas, ren, &look, t, RR_LOOK_CRT_FLAT, software, &lit, &corner);
        CHECK(lit > 640 * 384 / 2);
        CHECK(flat == draw(canvas, ren, &look, t, RR_LOOK_CRT_FLAT, software, &lit, &corner));     /* the same picture again */
        const uint64_t curved = draw(canvas, ren, &look, t, RR_LOOK_CRT_CURVED, software, &lit, &corner);
        if (software) CHECK(lit > 640 * 384 / 2);  /* drawn flat, with the slot mask */
        else CHECK(corner == 0 && lit > 640 * 384 / 3);   /* the rounded, curved corner is black */
        CHECK(curved != flat);
    }
    /* LCD: 2x does not fit (false: the caller draws the picture plain); 3x does */
    SDL_SetRenderDrawColor(ren, 0, 0, 0, 255); SDL_RenderClear(ren);
    const SDL_Rect source = {0, 0, 160, 144}, two = {0, 0, 320, 288}, three = {0, 0, 480, 384};
    CHECK(!rr_look_draw(ren, &look, t, &source, &two, 144, RR_LOOK_LCD, true));
    CHECK(rr_look_draw(ren, &look, t, &source, &three, 144, RR_LOOK_LCD, true) == false);     /* 384 < 3 x 144 */
    const SDL_Rect fits = {0, 0, 480, 432};
    SDL_Surface *tall = SDL_CreateRGBSurfaceWithFormat(0, 480, 432, 32, SDL_PIXELFORMAT_ARGB8888);
    SDL_Renderer *lcd = SDL_CreateSoftwareRenderer(tall);
    SDL_Texture *t2 = picture(lcd);
    RrLook look2 = {0};
    CHECK(rr_look_draw(lcd, &look2, t2, &source, &fits, 144, RR_LOOK_LCD, true));
    SDL_RenderPresent(lcd);
    const uint32_t *p = (const uint32_t *)tall->pixels;
    const uint32_t cell = p[1 * (tall->pitch / 4) + 1] & 0xffffff, gap = p[1 * (tall->pitch / 4) + 2] & 0xffffff;   /* 3 px cells: gap at x 2 */
    CHECK(cell != gap);
    /* a picture with no size draws nothing */
    const SDL_Rect none = {0, 0, 0, 0};
    CHECK(!rr_look_draw(ren, &look, t, &none, &fits, 144, RR_LOOK_CRT_FLAT, false));
    rr_look_destroy(&look); rr_look_destroy(&look2);
    CHECK(look.mask == NULL && look.picture == NULL);
    SDL_DestroyTexture(t); SDL_DestroyTexture(t2);
    SDL_DestroyRenderer(ren); SDL_DestroyRenderer(lcd);
    SDL_FreeSurface(canvas); SDL_FreeSurface(tall);
}

int main(void) {
    overlay_checks();
    cycle_checks();
    draw_checks();
    printf("{\"passed\": %d, \"failed\": %d}\n", passed, failed);
    return failed != 0;
}
