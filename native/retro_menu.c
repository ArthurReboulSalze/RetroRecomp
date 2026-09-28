#include "retro_menu.h"
#include <windows.h>
#include <stdint.h>
#include <string.h>

enum { GW = 6, GH = 12, ATLAS_W = 96, ATLAS_H = 72 };
static SDL_Texture *font;

bool rr_menu_init(SDL_Renderer *renderer) {
    HDC dc = CreateCompatibleDC(NULL);
    BITMAPINFO bi; memset(&bi, 0, sizeof(bi));
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth = ATLAS_W; bi.bmiHeader.biHeight = -ATLAS_H;
    bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 32; bi.bmiHeader.biCompression = BI_RGB;
    uint32_t *pixels = NULL;
    HBITMAP bitmap = CreateDIBSection(dc, &bi, DIB_RGB_COLORS, (void **)&pixels, NULL, 0);
    HFONT face = CreateFontW(-10, 6, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, ANSI_CHARSET,
        OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, NONANTIALIASED_QUALITY, FIXED_PITCH, L"Consolas");
    if (!dc || !bitmap || !face) {
        if (face) DeleteObject(face); if (bitmap) DeleteObject(bitmap); if (dc) DeleteDC(dc);
        return false;
    }
    HGDIOBJ old_bitmap = SelectObject(dc, bitmap), old_font = SelectObject(dc, face);
    memset(pixels, 0, ATLAS_W * ATLAS_H * 4);
    SetTextColor(dc, RGB(255,255,255)); SetBkMode(dc, TRANSPARENT);
    for (int c = 32; c < 128; ++c) {
        char letter = (char)c;
        int x = ((c - 32) % 16) * GW, y = ((c - 32) / 16) * GH;
        RECT cell = {x, y, x + GW, y + GH};
        ExtTextOutA(dc, x, y, ETO_CLIPPED, &cell, &letter, 1, NULL);
    }
    GdiFlush();
    for (int i = 0; i < ATLAS_W * ATLAS_H; ++i) pixels[i] = (pixels[i] & 255) ? 0xFFFFFFFF : 0;
    font = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STATIC, ATLAS_W, ATLAS_H);
    if (font) { SDL_UpdateTexture(font, NULL, pixels, ATLAS_W * 4); SDL_SetTextureBlendMode(font, SDL_BLENDMODE_BLEND); }
    SelectObject(dc, old_font); SelectObject(dc, old_bitmap);
    DeleteObject(face); DeleteObject(bitmap); DeleteDC(dc);
    return font != NULL;
}

void rr_menu_shutdown(void) { if (font) SDL_DestroyTexture(font); font = NULL; }

void rr_menu_layout(SDL_Renderer *renderer, int *x, int *y, int *scale) {
    int w, h; SDL_GetRendererOutputSize(renderer, &w, &h);
    int k = SDL_min(w / 256, h / 192); if (k < 1) k = 1;
    *x = (w - 256 * k) / 2; *y = (h - 192 * k) / 2; *scale = k;
}

void rr_menu_box(SDL_Renderer *r, int ox, int oy, int unit,
                 int x, int y, int w, int h, int red, int green, int blue, int alpha) {
    SDL_Rect rect = {ox + x * unit, oy + y * unit, w * unit, h * unit};
    SDL_SetRenderDrawColor(r, red, green, blue, alpha); SDL_RenderFillRect(r, &rect);
}

void rr_menu_text(SDL_Renderer *r, int ox, int oy, int unit,
                  int x, int y, const char *s, int red, int green, int blue) {
    if (!font || !s) return;
    SDL_SetTextureColorMod(font, red, green, blue);
    for (int i = 0; s[i] && i < 39; ++i) {
        unsigned c = (unsigned char)s[i]; if (c < 32 || c > 127) c = '?';
        SDL_Rect source = {((c - 32) % 16) * GW, ((c - 32) / 16) * GH, GW, GH};
        SDL_Rect dest = {ox + (x + i * GW) * unit, oy + y * unit, GW * unit, GH * unit};
        SDL_RenderCopy(r, font, &source, &dest);
    }
}

void rr_menu_begin(SDL_Renderer *r, int ox, int oy, int unit) {
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(r, 0, 0, 0, 180); SDL_RenderFillRect(r, NULL);
    rr_menu_box(r, ox, oy, unit, 6, 6, 244, 180, 7, 23, 50, 255);
    rr_menu_box(r, ox, oy, unit, 6, 6, 122, 2, 170, 102, 255, 255);
    rr_menu_box(r, ox, oy, unit, 128, 6, 122, 2, 38, 215, 255, 255);
}

void rr_menu_end(SDL_Renderer *r) { SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_NONE); }
