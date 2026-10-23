#include "retro_menu.h"
#include "font6x10.h"
#include "font10x20.h"
#include <stdint.h>
#include <string.h>
#include "runtime_i18n.h"
#include "runtime_catalog.inc"

/* Layout stays on the 256x192 grid; text uses five by ten cells, so every
 * function key gets its own help line and controls fit on one page. */
enum { GW = 5, GH = 10, FONT_COLUMNS = 16, FONT_ROWS = 6, FONT_MAX_UNIT = 16 };
/* Atlas cell width in pixels: at 1x the 6x10 bitmap keeps its spacing column
 * and is narrowed to five pixels when drawn. */
static int cell_width(int unit) { return unit < 2 ? 6 : GW * unit; }
static SDL_Renderer *font_renderer;
static SDL_Texture *font;
static int font_unit;
static int language_id;

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

/* Strict UTF-8 decoding keeps damaged settings/key names from consuming the
 * following byte. Games draw ASCII only: Latin-1 letters lose their accents
 * and any other character becomes '?', one cell each. */
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
static char ascii_code(uint32_t c) {
    static const char latin1[] = "AAAAAAACEEEEIIIIDNOOOOOxOUUUUYTsaaaaaaaceeeeiiiidnooooo/ouuuuyty";
    if(c>=32 && c<127) return (char)c;
    if(c>=0xc0 && c<=0xff) return latin1[c-0xc0];
    return '?';
}
int rr_menu_text_width(const char *text) {
    int width=0;
    if(!text)return 0;
    while(*text) { next_code(&text); width+=GW; }
    return width;
}

#ifndef RR_RECOMP_VERSION
#define RR_RECOMP_VERSION "dev"
#endif
const char *rr_menu_build_label(void) { return "Retro-Recomp v" RR_RECOMP_VERSION; }

/* The version sits at the right of the title row, clear of the bottom hints. */
void rr_menu_build_footer(SDL_Renderer *renderer, int ox, int oy, int unit) {
    const char *label = "v" RR_RECOMP_VERSION;
    int width = (int)strlen(label) * GW;
    rr_menu_text(renderer, ox, oy, unit, 242 - width, 12, label, RR_MENU_HINT);
}

/* Each 10x20 bitmap is drawn into a 5u x 10u cell by area coverage: solid
 * strokes stay solid and only their edges blend. Scale 1 keeps the original
 * 6x10 font. */
static SDL_Texture *build_font(SDL_Renderer *renderer, int unit) {
    int cw=cell_width(unit), ch=GH*unit, w=FONT_COLUMNS*cw, h=FONT_ROWS*ch;
    uint32_t *pixels=SDL_calloc((size_t)w*h,sizeof(uint32_t));
    if(!pixels) return NULL;
    for(int c=32;c<128;++c) {
        int ox=((c-32)%FONT_COLUMNS)*cw, oy=((c-32)/FONT_COLUMNS)*ch;
        if(unit<2) {
            for(int y=0;y<10;++y) for(int x=0;x<cw;++x)
                if(rr_font6x10[c-32][y]&(1u<<x)) pixels[(oy+y)*w+ox+x]=0xffffffffu;
            continue;
        }
        /* Source pixel sx spans [sx*cw,(sx+1)*cw) and target pixel tx spans
         * [tx*10,(tx+1)*10) on a common grid; likewise rows with 20 and ch. */
        for(int ty=0;ty<ch;++ty) for(int tx=0;tx<cw;++tx) {
            unsigned area=0;
            for(int sy=ty*20/ch;sy<20 && sy*ch<(ty+1)*20;++sy) {
                unsigned short row=rr_font10x20[c-32][sy];
                if(!row) continue;
                int top=SDL_max(sy*ch,ty*20), bottom=SDL_min((sy+1)*ch,(ty+1)*20);
                for(int sx=tx*10/cw;sx<10 && sx*cw<(tx+1)*10;++sx) if(row&(1u<<sx)) {
                    int left=SDL_max(sx*cw,tx*10), right=SDL_min((sx+1)*cw,(tx+1)*10);
                    area+=(unsigned)((right-left)*(bottom-top));
                }
            }
            if(area) pixels[(oy+ty)*w+ox+tx]=((area*255u+100u)/200u<<24)|0xffffffu;
        }
    }
    SDL_Texture *texture=SDL_CreateTexture(renderer,SDL_PIXELFORMAT_ARGB8888,SDL_TEXTUREACCESS_STATIC,w,h);
    if(texture) {
        SDL_UpdateTexture(texture,NULL,pixels,w*4);
        SDL_SetTextureBlendMode(texture,SDL_BLENDMODE_BLEND);
        SDL_SetTextureScaleMode(texture,SDL_ScaleModeLinear); /* only lines shrunk to fit */
    }
    SDL_free(pixels);
    return texture;
}

static bool use_font_unit(int unit) {
    unit=SDL_clamp(unit,1,FONT_MAX_UNIT);
    if(font && font_unit==unit) return true;
    SDL_Texture *texture=font_renderer?build_font(font_renderer,unit):NULL;
    if(!texture) return font!=NULL;
    if(font) SDL_DestroyTexture(font);
    font=texture; font_unit=unit;
    return true;
}

bool rr_menu_init(SDL_Renderer *renderer) {
    rr_menu_shutdown();
    font_renderer=renderer;
    int x, y, unit=1;
    if(renderer) rr_menu_layout(renderer,&x,&y,&unit);
    if(!use_font_unit(unit)) { font_renderer=NULL; return false; }
    return true;
}

void rr_menu_shutdown(void) {
    if (font) SDL_DestroyTexture(font);
    font = NULL; font_unit = 0; font_renderer = NULL;
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
    rr_menu_text_fit(r, ox, oy, unit, x, y, 242 - x, s, red, green, blue);
}
/* Text wider than `available` cells is narrowed to fit, never clipped. */
void rr_menu_text_fit(SDL_Renderer *r, int ox, int oy, int unit, int x, int y,
                      int available, const char *s, int red, int green, int blue) {
    if (!s || r != font_renderer || !use_font_unit(unit)) return;
    s=rr_tr(s);
    SDL_SetTextureColorMod(font, red, green, blue);
    int width=rr_menu_text_width(s), offset=0;
    if(available<=0 || width<=0)return;
    double fit=width>available?(double)available/width:1.0;
    int cw=cell_width(font_unit), ch=GH*font_unit;
    while(*s) {
        char c=ascii_code(next_code(&s));
        SDL_Rect source={((c-32)%FONT_COLUMNS)*cw,((c-32)/FONT_COLUMNS)*ch,cw,ch};
        int left=(int)(offset*unit*fit),right=(int)((offset+GW)*unit*fit);
        int height=SDL_max(1,(int)(GH*unit*fit));
        SDL_Rect dest={ox+x*unit+left,oy+y*unit+(GH*unit-height)/2,SDL_max(1,right-left),height};
        SDL_RenderCopy(r,font,&source,&dest); offset+=GW;
    }
}

void rr_menu_begin(SDL_Renderer *r, int ox, int oy, int unit) {
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(r, 0, 0, 0, 180); SDL_RenderFillRect(r, NULL);
    rr_menu_box(r, ox, oy, unit, 6, 6, 244, 180, RR_MENU_PANEL_RGB, 255);
    rr_menu_box(r, ox, oy, unit, 6, 6, 244, 2, RR_MENU_GOLD, 255);
}

void rr_menu_end(SDL_Renderer *r) { SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_NONE); }
/* F2 pages: title at the left, one small square per page at the right.
 * Pages up to the current one are filled, the current one brightest. */
void rr_menu_page_header(SDL_Renderer *r, int ox, int oy, int unit, const char *title, int page, int count) {
    int left = 243 - count * 9;
    rr_menu_text_fit(r, ox, oy, unit, 14, 12, count > 0 ? left - 20 : 228, title, RR_MENU_GOLD);
    for (int i = 0; i < count; ++i) {
        int x = left + i * 9;
        if (i < page) rr_menu_box(r, ox, oy, unit, x, 14, 6, 6, RR_MENU_HINT, 255);
        else if (i == page) rr_menu_box(r, ox, oy, unit, x, 14, 6, 6, RR_MENU_ACCENT, 255);
        else {
            rr_menu_box(r, ox, oy, unit, x, 14, 6, 1, RR_MENU_HINT, 255);
            rr_menu_box(r, ox, oy, unit, x, 19, 6, 1, RR_MENU_HINT, 255);
            rr_menu_box(r, ox, oy, unit, x, 15, 1, 4, RR_MENU_HINT, 255);
            rr_menu_box(r, ox, oy, unit, x + 5, 15, 1, 4, RR_MENU_HINT, 255);
        }
    }
}
