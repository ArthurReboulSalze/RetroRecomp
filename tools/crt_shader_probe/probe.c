/* tools/crt_shader_selftest.py: the host kit's real shell around a stand-in machine (a 256 x 224 test picture, 224 lines), run
 * as a hidden-window test run with a CRT look on (RETRORECOMP_HOST_TEST_FILTER, and its style), the window read back after a
 * few frames and summed up on one JSON line. CRT_PROBE_FLICKER=1: every other frame is black, and the window is read on a
 * black one (the LCD's slow response leaves the last picture in it). Never visible: test runs open their window hidden. Not
 * part of any game. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include "platform_io.h"
#include "retro_menu.h"
#include "hostkit/hostkit_internal.h"

int rr_feedback_toggle(void) { return 0; }
const char *rr_feedback_label(void) { return "F12"; }
int rr_feedback_pending(void) { return 0; }
void rr_feedback_finish(void) {}

enum { W = 256, H = 224 };
static uint32_t picture[W * H], black[W * H];
static bool flicker, done, black_now;
static int ran;
static const RrhkAction actions[1] = {{"Start", L"Start", 1, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_RETURN},
                                       {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}}};
static int width(void) { return W; }
static int height(void) { return H; }
static const uint32_t *pixels(void) { return black_now ? black : picture; }
static int players(void) { return 1; }
static void reset(void) {}
static void pause_machine(bool p) { (void)p; }
static size_t audio(int16_t *pcm, size_t cap) { (void)pcm; (void)cap; return 0; }
static uint64_t zero(void) { return 0; }
static int frames;
static bool run_frame(uint16_t p1, uint16_t p2) {
    (void)p1; (void)p2;
    black_now = flicker && ++ran % 2 == 0;
    return !done && frames < 40;
}

/* Across the picture's rectangle, the luma of rows y0..y1 (of the picture) summed per column into profile (dst.w values). */
static void profile_of(const uint32_t *px, int w, const SDL_Rect *dst, int y0, int y1, double *profile) {
    const int top = dst->y + dst->h * y0 / H, bottom = dst->y + dst->h * y1 / H;
    for (int x = 0; x < dst->w; ++x) {
        double sum = 0;
        for (int y = top; y < bottom; ++y) {
            const uint32_t v = px[(size_t)y * w + dst->x + x];
            sum += (double)((v >> 16 & 255) * 3 + (v >> 8 & 255) * 6 + (v & 255)) / 10.0;
        }
        profile[x] = sum / (bottom > top ? bottom - top : 1);
    }
}

static void before_present(SDL_Renderer *r) {
    if (done || ++frames < 8 || (flicker && !black_now)) return;
    done = true;
    int w, h; SDL_GetRendererOutputSize(r, &w, &h);
    uint32_t *px = (uint32_t *)malloc((size_t)w * h * 4);
    if (!px || SDL_RenderReadPixels(r, NULL, SDL_PIXELFORMAT_ARGB8888, px, w * 4) != 0) { printf("{\"read\": false}\n"); free(px); return; }
    const SDL_Rect dst = rrhk_game_rect(r);
    double sum = 0; long lit = 0, outside = 0;
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x) {
            const uint32_t v = px[(size_t)y * w + x];
            const int luma = (int)((v >> 16 & 255) * 3 + (v >> 8 & 255) * 6 + (v & 255)) / 10;
            const bool in = x >= dst.x && x < dst.x + dst.w && y >= dst.y && y < dst.y + dst.h;
            if (in) { sum += luma; if (luma > 8) ++lit; }
            else if (v & 0xffffff) ++outside;
        }
    const uint32_t corner = px[(size_t)dst.y * w + dst.x] & 0xffffff;
    const uint32_t centre = px[(size_t)(dst.y + dst.h / 2) * w + dst.x + dst.w / 2] & 0xffffff;
    /* a checksum of a 64 x 64 block at the centre, for two backends' comparison (by mean difference, done in Python) */
    unsigned long long block = 0;
    for (int y = 0; y < 64; ++y)
        for (int x = 0; x < 64; ++x) block += px[(size_t)(dst.y + dst.h / 2 - 32 + y) * w + dst.x + dst.w / 2 - 32 + x] & 0xff;
    /* D35's styles: detail, the contrast the one-pixel black and white stripes (rows 120..151) keep across, the mask's three
     * columns averaged out (a sharper style keeps more); mask, how much each row of the white bar (rows 16..96, the left
     * eighth) varies across, on average (a stronger mask varies more) */
    double *profile = (double *)malloc(sizeof(double) * (size_t)dst.w * 2), *smooth = profile + dst.w;
    double detail = 0, mask = 0;
    if (profile) {
        profile_of(px, w, &dst, 121, 151, profile);
        double lo = 1e9, hi = 0;
        for (int x = 1; x + 1 < dst.w; ++x) smooth[x] = (profile[x - 1] + profile[x] + profile[x + 1]) / 3.0;
        for (int x = dst.w / 4; x < dst.w * 3 / 4; ++x) { lo = SDL_min(lo, smooth[x]); hi = SDL_max(hi, smooth[x]); }
        detail = hi > 0 ? (hi - lo) / (hi + lo) : 0;
        int rows = 0;
        for (int y = dst.y + dst.h * 16 / H; y < dst.y + dst.h * 96 / H; ++y) {
            lo = 1e9; hi = 0;
            for (int x = dst.x + dst.w / 64; x < dst.x + dst.w / 10; ++x) {
                const uint32_t v = px[(size_t)y * w + x];
                const double luma = (double)((v >> 16 & 255) * 3 + (v >> 8 & 255) * 6 + (v & 255)) / 10.0;
                lo = SDL_min(lo, luma); hi = SDL_max(hi, luma);
            }
            if (hi > 16) { mask += (hi - lo) / hi; ++rows; }
        }
        mask = rows ? mask / rows : 0;
        free(profile);
    }
    SDL_RendererInfo info; SDL_GetRendererInfo(r, &info);
    printf("{\"read\": true, \"renderer\": \"%s\", \"filter\": %d, \"crt_style\": %d, \"lcd_style\": %d, \"w\": %d, \"h\": %d, "
           "\"dst\": [%d, %d, %d, %d], \"mean\": %.3f, \"lit\": %ld, \"outside\": %ld, \"corner\": %u, \"centre\": %u, "
           "\"block\": %llu, \"detail\": %.4f, \"mask\": %.4f}\n",
           info.name, rrhk_ui()->filter, rrhk_ui()->crt_style, rrhk_ui()->lcd_style, w, h, dst.x, dst.y, dst.w, dst.h,
           sum / ((double)dst.w * dst.h), lit, outside, (unsigned)corner, (unsigned)centre, block, detail, mask);
    fflush(stdout);
    free(px);
}
static RrhkMachine probe = {
    .ini_section = L"CrtProbe", .console_name = "CRT probe", .table_players = 1, .players = players,
    .actions = actions, .action_count = 1, .up = 0, .down = 0, .left = 0, .right = 0, .start = 0,
    .max_width = W, .max_height = H, .frame_seconds = 1.0 / 60.0,
    .reset = reset, .run_frame = run_frame, .pause = pause_machine, .pixels = pixels,
    .visible_width = width, .visible_height = height, .raster_height = height, .display_width = width,
    .audio = audio, .interpreted = zero, .audio_interpreted = zero, .before_present = before_present,
    .lcd_screen = true};             /* so the LCD look (6) can be asked too: its real screen is a colour TFT (no lcd_panel) */
const RrhkMachine *rrhk_adapter(void) { return &probe; }

int main(void) {
    SDL_SetMainReady();
    if (SDL_Init(SDL_INIT_VIDEO) != 0) return 2;
    /* bars, a grey ramp and white lines every 8 rows: bright and dark parts, horizontal detail; rows 120 to 151, black and
     * white stripes one pixel wide (D35's styles: how much of them a look keeps) */
    for (int y = 0; y < H; ++y)
        for (int x = 0; x < W; ++x) {
            uint32_t c = 0xff000000u | (uint32_t)((x * 255 / (W - 1)) * 0x010101u);
            if (y < 112) { static const uint32_t bars[8] = {0xffffff, 0xffff00, 0x00ffff, 0x00ff00, 0xff00ff, 0xff0000, 0x0000ff, 0x000000};
                           c = 0xff000000u | bars[x * 8 / W]; }
            if (y % 8 == 0 && y >= 112) c = 0xffffffffu;
            if (y >= 120 && y < 152) c = x % 2 ? 0xff000000u : 0xffffffffu;
            picture[y * W + x] = c;
            black[y * W + x] = 0xff000000u;
        }
    const char *f = getenv("CRT_PROBE_FLICKER");
    flicker = f && !strcmp(f, "1");
    const int rc = rrhk_main(&probe, "CRT probe", 4);
    SDL_Quit();
    return rc;
}
