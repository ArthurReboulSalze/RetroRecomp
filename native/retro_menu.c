#include "retro_menu.h"
#ifdef _WIN32
#include <windows.h>
#else
#include "font6x10.h"
#endif
#include <stdint.h>
#include <string.h>
#include "runtime_i18n.h"
#include "runtime_catalog.inc"
#include "runtime_glyphs.inc"

enum { GW = 6, GH = 12, ATLAS_W = 96, ATLAS_H = 72 };
static SDL_Texture *font;
static SDL_Texture *unicode_font;
static int language_id;
enum { UNICODE_COLS = 16, UNICODE_W = 192,
       UNICODE_H = ((sizeof(rr_glyphs)/sizeof(rr_glyphs[0])+15)/16)*12 };

int rr_language_from_code(const char *code) {
    if (code) for (int i=0;i<RR_LANGUAGE_COUNT;++i)
        if (code[0]==rr_language_codes[i][0] && code[1]==rr_language_codes[i][1] &&
            (!code[2] || code[2]=='-' || code[2]=='_')) return i;
    return 0;
}
int rr_language_from_wide(const wchar_t *code) {
    char code_bytes[3] = {0,0,0};
    if (code && code[0] && code[1] && (!code[2] || code[2]=='-' || code[2]=='_')) {
        code_bytes[0]=(char)code[0]; code_bytes[1]=(char)code[1];
    }
    return rr_language_from_code(code_bytes);
}
const char *rr_language_code(int id) { return rr_language_codes[id>=0 && id<RR_LANGUAGE_COUNT?id:0]; }
const wchar_t *rr_language_wide(int id) {
    static const wchar_t *codes[]={L"en",L"fr",L"it",L"es",L"de",L"zh",L"ja",L"ru"};
    return codes[id>=0 && id<RR_LANGUAGE_COUNT?id:0];
}
const char *rr_language_name(int id) { return rr_language_names[id>=0 && id<RR_LANGUAGE_COUNT?id:0]; }
int rr_language_next(int id) { return id>=0 && id<RR_LANGUAGE_COUNT?(id+1)%RR_LANGUAGE_COUNT:0; }
void rr_language_set(int id) { language_id=id>=0 && id<RR_LANGUAGE_COUNT?id:0; }
int rr_language_get(void) { return language_id; }
const char *rr_translate(int id, const char *en, const char *fr) {
    if (!en) return "";
    if (id<=0 || id>=RR_LANGUAGE_COUNT) return en;
    size_t lo=0,hi=sizeof(rr_translations)/sizeof(rr_translations[0]);
    while(lo<hi) {
        size_t at=lo+(hi-lo)/2; int cmp=strcmp(en,rr_translations[at][0]);
        if (!cmp) return rr_translations[at][id];
        if (cmp>0) lo=at+1; else hi=at;
    }
    return id==1 && fr?fr:en;
}
const char *rr_tr(const char *en) { return rr_translate(language_id,en,NULL); }

/* Strict UTF-8 decoding also keeps damaged settings/key names from consuming
 * the following byte or indexing outside the atlas. */
static uint32_t next_code(const char **text) {
    const unsigned char *s=(const unsigned char*)*text;
    uint32_t c=*s; unsigned count=1;
    if(c>=0xc2 && c<=0xdf) { c&=31; count=2; }
    else if(c>=0xe0 && c<=0xef) { c&=15; count=3; }
    else if(c>=0xf0 && c<=0xf4) { c&=7; count=4; }
    else if(c>=128) { ++*text; return '?'; }
    for(unsigned i=1;i<count;++i) {
        if((s[i]&0xc0)!=0x80) { ++*text; return '?'; }
        c=(c<<6)|(s[i]&63);
    }
    if ((count==2 && c<128) || (count==3 && c<2048) ||
        (count==4 && c<65536) || c>0x10ffff || (c>=0xd800 && c<=0xdfff)) { ++*text; return '?'; }
    *text+=count; return c;
}
static int glyph_index(uint32_t code) {
    size_t lo=0,hi=sizeof(rr_glyphs)/sizeof(rr_glyphs[0]);
    while(lo<hi) { size_t at=lo+(hi-lo)/2; if(code==rr_glyphs[at].code)return (int)at;
        if(code>rr_glyphs[at].code)lo=at+1;else hi=at; }
    return -1;
}
int rr_menu_text_width(const char *text) {
    int width=0;
    if(!text)return 0;
    while(*text) { uint32_t code=next_code(&text); int at=glyph_index(code);
        width+=at>=0?(int)rr_glyphs[at].width:GW; }
    return width;
}

#ifndef RR_RECOMP_VERSION
#define RR_RECOMP_VERSION "dev"
#endif
const char *rr_menu_build_label(void) { return "Retro-Recomp v" RR_RECOMP_VERSION; }

void rr_menu_build_footer(SDL_Renderer *renderer, int ox, int oy, int unit) {
    const char *label = rr_menu_build_label();
    int width = (int)strlen(label) * GW;
    rr_menu_text(renderer, ox, oy, unit, 242 - width, 174, label, 157, 173, 194);
}

bool rr_menu_init(SDL_Renderer *renderer) {
#ifdef _WIN32
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
#else
    uint32_t storage[ATLAS_W*ATLAS_H]={0},*pixels=storage;
    for(int c=32;c<128;++c)for(int y=0;y<10;++y)for(int x=0;x<GW;++x) {
        /* Preserve the fine six-pixel cell directly; resampling a bold VGA
         * bitmap made strokes uneven and lost the right edge of letters. */
        if(rr_font6x10[c-32][y]&(1u<<x))
            pixels[(((c-32)/16)*GH+y+1)*ATLAS_W+((c-32)%16)*GW+x]=0xffffffffu;
    }
#endif
    font = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STATIC, ATLAS_W, ATLAS_H);
    if (font) { SDL_UpdateTexture(font, NULL, pixels, ATLAS_W * 4); SDL_SetTextureBlendMode(font, SDL_BLENDMODE_BLEND); }
#ifdef _WIN32
    SelectObject(dc, old_font); SelectObject(dc, old_bitmap);
    DeleteObject(face); DeleteObject(bitmap); DeleteDC(dc);
    #endif
    uint32_t *extra=SDL_calloc(UNICODE_W*UNICODE_H,sizeof(uint32_t));
    if(extra) {
        for(size_t at=0;at<sizeof(rr_glyphs)/sizeof(rr_glyphs[0]);++at)
            for(unsigned y=0;y<12;++y) for(unsigned x=0;x<rr_glyphs[at].width;++x) {
                unsigned alpha=rr_glyph_pixels[rr_glyphs[at].offset+y*rr_glyphs[at].width+x];
                extra[((at/16)*12+y)*UNICODE_W+(at%16)*12+x]=(alpha<<24)|0xffffffu;
            }
        unicode_font=SDL_CreateTexture(renderer,SDL_PIXELFORMAT_ARGB8888,SDL_TEXTUREACCESS_STATIC,UNICODE_W,UNICODE_H);
        if(unicode_font) { SDL_UpdateTexture(unicode_font,NULL,extra,UNICODE_W*4); SDL_SetTextureBlendMode(unicode_font,SDL_BLENDMODE_BLEND); }
        SDL_free(extra);
    }
    if(!font || !unicode_font) { rr_menu_shutdown(); return false; }
    return true;
}

void rr_menu_shutdown(void) {
    if (font) SDL_DestroyTexture(font); font = NULL;
    if (unicode_font) SDL_DestroyTexture(unicode_font); unicode_font=NULL;
}

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
    s=rr_tr(s);
    SDL_SetTextureColorMod(font, red, green, blue);
    SDL_SetTextureColorMod(unicode_font, red, green, blue);
    int width=rr_menu_text_width(s), available=242-x, offset=0;
    if(available<=0 || width<=0)return;
    double fit=width>available?(double)available/width:1.0;
    while(*s) {
        uint32_t c=next_code(&s); int at=glyph_index(c);
        int advance=at>=0?(int)rr_glyphs[at].width:GW;
        SDL_Rect source;
        SDL_Texture *atlas=font;
        if(at>=0) { source=(SDL_Rect){(at%16)*12,(at/16)*12,advance,GH}; atlas=unicode_font; }
        else { if(c<32 || c>127)c='?'; source=(SDL_Rect){((c-32)%16)*GW,((c-32)/16)*GH,GW,GH}; }
        int left=(int)(offset*unit*fit),right=(int)((offset+advance)*unit*fit);
        int height=SDL_max(1,(int)(GH*unit*fit));
        SDL_Rect dest={ox+x*unit+left,oy+y*unit+(GH*unit-height)/2,SDL_max(1,right-left),height};
        SDL_RenderCopy(r,atlas,&source,&dest); offset+=advance;
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
