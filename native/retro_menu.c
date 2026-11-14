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
    if (s) rr_menu_text_plain(r, ox, oy, unit, x, y, available, rr_tr(s), red, green, blue);
}
/* The same without a look-up in the catalogue: for text that is already translated (a part of a translated line, a key's
 * name), which must not be translated a second time ("Enter" is itself an entry). */
void rr_menu_text_plain(SDL_Renderer *r, int ox, int oy, int unit, int x, int y,
                        int available, const char *s, int red, int green, int blue) {
    if (!s || r != font_renderer || !use_font_unit(unit)) return;
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

/* ---- Pixel art of the menus (1.7.4): icons, block letters, key caps, notice plates ----
 * Drawn by hand on the menu grid and kept as packed rows, about 1.3 KB in all: no image file, no texture.
 * An icon row is 2 bits a cell, cell x in bits 2x and 2x+1: 0 nothing, 1 line, 2 fill, 3 highlight. The Retro-Recomp mark
 * uses the same bits for its plate, border, white and gold, with its four corner cells left out. */
static const uint64_t icon_keyboard[18] = {
    0x0ull, 0x0ull, 0x155555555555554ull, 0x6aaaaaaaaaaaaa9ull, 0x6aaaaaaaaaaaaa9ull, 0x6a5965965965969ull, 0x6a5965965965969ull,
    0x6aaaaaaaaaaaaa9ull, 0x6965965965965a9ull, 0x6965965965965a9ull, 0x6aaaaaaaaaaaaa9ull, 0x6965bfffffe5969ull,
    0x6965bfffffe5969ull, 0x6aaaaaaaaaaaaa9ull, 0x6aaaaaaaaaaaaa9ull, 0x155555555555554ull, 0x0ull, 0x0ull};
static const uint64_t icon_gamepad[18] = {
    0x0ull, 0x0ull, 0x155555555555554ull, 0x6aaaaaaaaaaaaa9ull, 0x6aafaaaaaaaaaa9ull, 0x6aafaaaaaaa5aa9ull, 0x6aaaaaaaaaa5aa9ull,
    0x6afafa5a5a555a9ull, 0x6afafaaaaa555a9ull, 0x6aaaaaaaaaa5aa9ull, 0x6aafaaaaaaa5aa9ull, 0x6aafaaaaaaaaaa9ull,
    0x1aaa9555556aaa4ull, 0x1aaa9000006aaa4ull, 0x1aaa9000006aaa4ull, 0x1aaa9000006aaa4ull, 0x55540000015550ull, 0x0ull};
static const uint64_t icon_options[18] = {
    0x0ull, 0x0ull, 0x154000ull, 0x1f4000ull, 0x2aaaaaaaa9f5554ull, 0x1f4000ull, 0x154000ull, 0x154000000000ull,
    0x1f4000000000ull, 0x2aa9f5555555554ull, 0x1f4000000000ull, 0x154000000000ull, 0x55000000ull, 0x7d000000ull,
    0x2aaaaaa7d555554ull, 0x7d000000ull, 0x55000000ull, 0x0ull};
static const uint64_t icon_pointer[18] = {
    0xf0000000ull, 0xf0000000ull, 0x15f5400000ull, 0x140f0140000ull, 0x400f0010000ull, 0x1000f0004000ull, 0x100000004000ull,
    0x100000004000ull, 0xfffc0503fff00ull, 0xfffc0503fff00ull, 0x100000004000ull, 0x100000004000ull, 0x1000f0004000ull,
    0x400f0010000ull, 0x140f0140000ull, 0x15f5400000ull, 0xf0000000ull, 0xf0000000ull};
static const uint64_t icon_switches[18] = {
    0x0ull, 0x0ull, 0x155555555555554ull, 0x6aaaaaaaaaaaaa9ull, 0x6a5656565656569ull, 0x6a4676764646769ull, 0x6a4676764646769ull,
    0x6a4676764646769ull, 0x6a4676764646769ull, 0x6a7646467676469ull, 0x6a7646467676469ull, 0x6a7646467676469ull,
    0x6a7646467676469ull, 0x6a5656565656569ull, 0x6aaaaaaaaaaaaa9ull, 0x155555555555554ull, 0x0ull, 0x0ull};
static const uint64_t icon_logo[20] = {
    0x1555555555554ull, 0x4f00000000001ull, 0x4fc0000000001ull, 0x4c00000000001ull, 0x40ffff02aaa81ull, 0x40ffff02aaa81ull,
    0x43f03f0a80a81ull, 0x43f03f0a80a81ull, 0x43ffff0aaaa81ull, 0x40ffff02aaa81ull, 0x40fc3f02a0a81ull, 0x43f03f0a80a81ull,
    0x43f03f0a80a81ull, 0x4000000000001ull, 0x42aaaaaaaaa81ull, 0x4000000000001ull, 0x42aaabfeaaa81ull, 0x400000f000001ull,
    0x4000000000001ull, 0x1555555555554ull};
static const uint64_t icon_keyboard_small[9] = {
    0x55555554ull, 0x1aaaaaaa9ull, 0x199999999ull, 0x1aaaaaaa9ull, 0x199999999ull, 0x1aaaaaaa9ull, 0x1abffffa9ull, 0x1aaaaaaa9ull,
    0x55555554ull};
static const uint64_t icon_gamepad_small[9] = {
    0x55555554ull, 0x1aaaaaaa9ull, 0x1abaaaa69ull, 0x1aaaaa959ull, 0x1aeaaaa69ull, 0xaaaaaaa8ull, 0x1a95555a9ull, 0x1a90001a9ull,
    0x54000054ull};
static const uint64_t icon_options_small[9] = {
    0x3f00ull, 0x2aaaabf55ull, 0x3f00ull, 0x3f00000ull, 0x2abf55555ull, 0x3f00000ull, 0x3f000ull, 0x2aaabf555ull, 0x3f000ull};
/* <row icons> */
/* Row icons (1.7.5): 9 x 9, at the left of the rows of the control, options and graphics pages. Drawn by hand (the drawing
 * and its packing script are kept with the interface notes); a face button is the ring with its letters drawn inside. */
static const uint64_t icon_row_up[9] = {0x300ull, 0xfc0ull, 0x3ff0ull, 0x540ull, 0x15655ull, 0x1aaa9ull, 0x15655ull, 0x640ull, 0x540ull};
static const uint64_t icon_row_down[9] = {0x540ull, 0x640ull, 0x15655ull, 0x1aaa9ull, 0x15655ull, 0x540ull, 0x3ff0ull, 0xfc0ull, 0x300ull};
static const uint64_t icon_row_left[9] = {0x1500ull, 0x1900ull, 0x1930ull, 0x1597cull, 0x1aa7full, 0x1597cull, 0x1930ull, 0x1900ull, 0x1500ull};
static const uint64_t icon_row_right[9] = {0x150ull, 0x190ull, 0x3190ull, 0xf595ull, 0x3f6a9ull, 0xf595ull, 0x3190ull, 0x190ull, 0x150ull};
static const uint64_t icon_row_button[9] = {0x1550ull, 0x6aa4ull, 0x1aaa9ull, 0x1aaa9ull, 0x1aaa9ull, 0x1aaa9ull, 0x1aaa9ull, 0x6aa4ull, 0x1550ull};
static const uint64_t icon_row_start[9] = {0x0ull, 0x5554ull, 0x1aaa9ull, 0x1aae9ull, 0x1abe9ull, 0x1aae9ull, 0x1aaa9ull, 0x5554ull, 0x0ull};
static const uint64_t icon_row_select[9] = {0x0ull, 0x0ull, 0x5554ull, 0x1aaa9ull, 0x1bff9ull, 0x1aaa9ull, 0x5554ull, 0x0ull, 0x0ull};
static const uint64_t icon_row_coin[9] = {0x1550ull, 0x7ff4ull, 0x1f67dull, 0x1da9dull, 0x1db9dull, 0x1da9dull, 0x1f67dull, 0x7ff4ull, 0x1550ull};
static const uint64_t icon_row_pause[9] = {0x0ull, 0x5454ull, 0x7474ull, 0x7474ull, 0x7474ull, 0x7474ull, 0x7474ull, 0x5454ull, 0x0ull};
static const uint64_t icon_row_quit[9] = {0x100ull, 0x4304ull, 0x1c30dull, 0x1c30dull, 0x1c00dull, 0x1c00dull, 0x7034ull, 0x1fd0ull, 0x540ull};
static const uint64_t icon_row_restart[9] = {0x5540ull, 0x7a90ull, 0x7f24ull, 0x4009ull, 0x9ull, 0x4009ull, 0x6024ull, 0x1a90ull, 0x540ull};
static const uint64_t icon_row_save[9] = {0x1555ull, 0x7ff9ull, 0x1bff9ull, 0x1aaa9ull, 0x1aba9ull, 0x1aba9ull, 0x1bff9ull, 0x1afe9ull, 0x15755ull};
static const uint64_t icon_row_load[9] = {0x54ull, 0x155a9ull, 0x1aaa9ull, 0x1aba9ull, 0x1afe9ull, 0x1bff9ull, 0x1aba9ull, 0x1aba9ull, 0x15555ull};
static const uint64_t icon_row_gamepad[9] = {0x0ull, 0x5554ull, 0x1aaa9ull, 0x19ab9ull, 0x166fdull, 0x19ab9ull, 0x1a569ull, 0x5014ull, 0x0ull};
static const uint64_t icon_row_stick[9] = {0x1550ull, 0x6aa4ull, 0x1a029ull, 0x18009ull, 0x18309ull, 0x18009ull, 0x1a029ull, 0x6aa4ull, 0x1550ull};
static const uint64_t icon_row_keyboard[9] = {0x0ull, 0x0ull, 0x15555ull, 0x19999ull, 0x15555ull, 0x19999ull, 0x1bff9ull, 0x15555ull, 0x0ull};
static const uint64_t icon_row_filter[9] = {0x15555ull, 0x1bebdull, 0x1bebdull, 0x1ebe9ull, 0x1ebe9ull, 0x1bebdull, 0x1bebdull, 0x15555ull, 0x0ull};
static const uint64_t icon_row_display[9] = {0x15555ull, 0x1aaa9ull, 0x16ab9ull, 0x1aaa9ull, 0x1aaa9ull, 0x15555ull, 0x540ull, 0x5554ull, 0x0ull};
static const uint64_t icon_row_autofire[9] = {0x0ull, 0xc0cull, 0x3f3full, 0x33f3full, 0x33f3full, 0x11515ull, 0x11919ull, 0x11515ull, 0x0ull};
static const uint64_t icon_row_language[9] = {0x5554ull, 0x1aaa9ull, 0x1bbb9ull, 0x1aaa9ull, 0x15654ull, 0x640ull, 0x140ull, 0x40ull, 0x0ull};
static const uint64_t icon_row_record[9] = {0x1550ull, 0x6aa4ull, 0x1afe9ull, 0x1bff9ull, 0x1bff9ull, 0x1bff9ull, 0x1afe9ull, 0x6aa4ull, 0x1550ull};
static const uint64_t icon_row_wave[9] = {0x0ull, 0x14ull, 0x69ull, 0x10041ull, 0x4100ull, 0x1400ull, 0x0ull, 0x15555ull, 0xccccull};
static const uint64_t icon_row_volume[9] = {0x0ull, 0x40ull, 0x3050ull, 0xd015ull, 0xd319ull, 0xd015ull, 0x3050ull, 0x40ull, 0x0ull};
static const uint64_t icon_row_sound[9] = {0x15540ull, 0x1ff40ull, 0x10040ull, 0x10040ull, 0x10040ull, 0x15054ull, 0x1f47dull, 0x1f47dull, 0x5014ull};
static const uint64_t icon_row_headphones[9] = {0x1550ull, 0x4004ull, 0x10001ull, 0x10001ull, 0x15015ull, 0x1d01dull, 0x1d01dull, 0x15015ull, 0x0ull};
static const uint64_t icon_row_fkey[9] = {0x15555ull, 0x1aaa9ull, 0x1bff9ull, 0x16ab9ull, 0x16ff9ull, 0x16ab9ull, 0x16ab9ull, 0x15555ull, 0x5554ull};
static const uint64_t icon_row_reminder[9] = {0x300ull, 0x540ull, 0x1a90ull, 0x1a90ull, 0x6aa4ull, 0x6aa4ull, 0x15555ull, 0x300ull, 0x0ull};
static const uint64_t icon_row_speed[9] = {0x0ull, 0x101ull, 0x505ull, 0x1d1dull, 0x7d7dull, 0x1d1dull, 0x505ull, 0x101ull, 0x0ull};
static const uint64_t icon_row_rumble[9] = {0x0ull, 0x1550ull, 0x36aa7ull, 0x6ee4ull, 0x36aa7ull, 0x6ee4ull, 0x36aa7ull, 0x1550ull, 0x0ull};
static const uint64_t icon_row_restore[9] = {0x5540ull, 0x7a90ull, 0x7f24ull, 0x4309ull, 0xfc9ull, 0x4309ull, 0x6024ull, 0x1a90ull, 0x540ull};
static const uint64_t icon_row_generic[9] = {0x0ull, 0x540ull, 0x1fd0ull, 0x7ef4ull, 0x1fabdull, 0x7ef4ull, 0x1fd0ull, 0x540ull, 0x0ull};
/* 3 x 5 letters of the face buttons, bit (row * 3 + x): i the narrow I of II to IV, ^ o [ x the PlayStation shapes. */
static const char row_letter_chars[] = "ABCXYZLRI123456DKPSFGHMEVi^o[x";
static const uint16_t row_letters[] = {0x5bea, 0x3aeb, 0x624e, 0x5aad, 0x24ad, 0x72a7, 0x7249, 0x5aeb, 0x7497, 0x749a, 0x72a3, 0x38a3, 0x49ed, 0x38cf, 0x7bce,
    0x3b6b, 0x5aed, 0x12eb, 0x388e, 0x12cf, 0x6b4e, 0x5bed, 0x5bfd, 0x72cf, 0x2b6d, 0x1249, 0xf50, 0x550, 0xf78, 0xaa8};
/* </row icons> */
static const struct { const uint64_t *rows; unsigned char w, h; } icons[RR_ICON_COUNT] = {
    {icon_keyboard, 30, 18}, {icon_gamepad, 30, 18}, {icon_options, 30, 18}, {icon_pointer, 30, 18}, {icon_switches, 30, 18},
    {icon_logo, 26, 20}, {icon_keyboard_small, 17, 9}, {icon_gamepad_small, 17, 9}, {icon_options_small, 17, 9},
    /* <row table> */
    {icon_row_up, 9, 9}, {icon_row_down, 9, 9}, {icon_row_left, 9, 9}, {icon_row_right, 9, 9}, {icon_row_button, 9, 9},
    {icon_row_start, 9, 9}, {icon_row_select, 9, 9}, {icon_row_coin, 9, 9}, {icon_row_pause, 9, 9}, {icon_row_quit, 9, 9},
    {icon_row_restart, 9, 9}, {icon_row_save, 9, 9}, {icon_row_load, 9, 9}, {icon_row_gamepad, 9, 9}, {icon_row_stick, 9, 9},
    {icon_row_keyboard, 9, 9}, {icon_row_filter, 9, 9}, {icon_row_display, 9, 9}, {icon_row_autofire, 9, 9},
    {icon_row_language, 9, 9}, {icon_row_record, 9, 9}, {icon_row_wave, 9, 9}, {icon_row_volume, 9, 9},
    {icon_row_sound, 9, 9}, {icon_row_headphones, 9, 9}, {icon_row_fkey, 9, 9}, {icon_row_reminder, 9, 9},
    {icon_row_speed, 9, 9}, {icon_row_rumble, 9, 9}, {icon_row_restore, 9, 9}, {icon_row_generic, 9, 9}
    /* </row table> */};
int rr_menu_icon_width(int icon) { return icon >= 0 && icon < RR_ICON_COUNT ? icons[icon].w : 0; }

/* The value of one cell, -1 for a cell that is not drawn (the mark's plate is rounded: its four corner cells). */
static int icon_cell(int icon, int row, int cx) {
    const int value = (int)((icons[icon].rows[row] >> (2 * cx)) & 3);
    if (icon == RR_ICON_LOGO) return (row == 0 || row == icons[icon].h - 1) && (cx == 0 || cx == icons[icon].w - 1) ? -1 : value;
    return value ? value : -1;
}

void rr_menu_icon(SDL_Renderer *r, int ox, int oy, int unit, int x, int y, int icon, bool dim) {
    static const unsigned char bright[4][3] = {{0, 0, 0}, {RR_MENU_GOLD}, {RR_MENU_SHADE}, {RR_MENU_ACCENT}};
    static const unsigned char faded[4][3] = {{0, 0, 0}, {RR_MENU_HINT}, {32, 27, 16}, {RR_MENU_HINT}};
    static const unsigned char mark[4][3] = {{8, 8, 8}, {RR_MENU_HINT}, {240, 240, 240}, {245, 170, 30}};
    if (icon < 0 || icon >= RR_ICON_COUNT) return;
    const unsigned char (*colors)[3] = icon == RR_ICON_LOGO ? mark : dim ? faded : bright;
    const int w = icons[icon].w, h = icons[icon].h;
    for (int row = 0; row < h; ++row)
        for (int cx = 0; cx < w;) {      /* one rectangle per run of equal cells */
            const int value = icon_cell(icon, row, cx);
            int end = cx + 1;
            while (end < w && icon_cell(icon, row, end) == value) ++end;
            if (value >= 0)
                rr_menu_box(r, ox, oy, unit, x + cx, y + row, end - cx, 1, colors[value][0], colors[value][1], colors[value][2], 255);
            cx = end;
        }
}

bool rr_menu_button_letters(const char *letters) {
    if (!letters || !letters[0] || strlen(letters) > 3) return false;
    for (const char *c = letters; *c; ++c) if (!strchr(row_letter_chars, *c)) return false;
    return true;
}
void rr_menu_button(SDL_Renderer *r, int ox, int oy, int unit, int x, int y, const char *letters) {
    rr_menu_icon(r, ox, oy, unit, x, y, RR_ICON_ROW_BUTTON, false);
    if (!rr_menu_button_letters(letters)) return;
    /* centred in the ring's seven inner cells, rows 2 to 6: three cells a letter (one for the narrow i), a cell apart */
    int width = -1;
    for (const char *c = letters; *c; ++c) width += (*c == 'i' ? 1 : 3) + 1;
    int lx = x + 1 + (7 - width) / 2;
    for (const char *c = letters; *c; ++c) {
        const unsigned bits = row_letters[strchr(row_letter_chars, *c) - row_letter_chars];
        for (int row = 0; row < 5; ++row)
            for (int cx = 0; cx < 3; ++cx)
                if (bits & (1u << (row * 3 + cx))) rr_menu_box(r, ox, oy, unit, lx + cx, y + 2 + row, 1, 1, RR_MENU_ACCENT, 255);
        lx += (*c == 'i' ? 1 : 3) + 1;
    }
}

/* Block letters, 5 rows of up to 5 cells: bit (row * 5 + x), the width in bits 28-30. Upper case, digits and a few signs. */
static const char block_chars[] = " +-./0123456789:?ABCDEFGHIJKLMNOPQRSTUVWXYZ";
static const uint32_t block_glyphs[] = {
    0x20000000, 0x30011c40, 0x30001c00, 0x10100000, 0x50111110, 0x50e9d72e, 0x30710862, 0x51f0ba0f, 0x50f83a0f, 0x50847d29,
    0x50f83c3f, 0x50e8bc2e, 0x5042221f, 0x50e8ba2e, 0x50e87a2e, 0x10008020, 0x40201907, 0x5118fe2e, 0x50f8be2f, 0x51e0843e,
    0x50f8c62f, 0x51f0bc3f, 0x5010bc3f, 0x51e8f43e, 0x5118fe31, 0x30710847, 0x5064a11c, 0x51149d31, 0x51f08421, 0x5118d771,
    0x511cd671, 0x50e8c62e, 0x5010be2f, 0x5164d62e, 0x5114be2f, 0x50f8383e, 0x5042109f, 0x50e8c631, 0x50454631, 0x511dd631,
    0x51151151, 0x50421151, 0x51f1111f};
static uint32_t block_glyph(char c) {
    if (c >= 'a' && c <= 'z') c = (char)(c - 'a' + 'A');
    const char *at = c ? strchr(block_chars, c) : NULL;
    return block_glyphs[at ? at - block_chars : strchr(block_chars, '?') - block_chars];
}
int rr_menu_block_width(const char *text, int k) {
    int width = 0;
    text = rr_tr(text);
    while (*text) width += ((int)(block_glyph(ascii_code(next_code(&text))) >> 28) + 1) * k;
    return width > 0 ? width - k : 0;
}
int rr_menu_block(SDL_Renderer *r, int ox, int oy, int unit, int x, int y, int k, const char *text, int red, int green, int blue) {
    const int start = x;
    text = rr_tr(text);
    while (*text) {
        const uint32_t glyph = block_glyph(ascii_code(next_code(&text)));
        const int w = (int)(glyph >> 28);
        for (int row = 0; row < 5; ++row) for (int cx = 0; cx < w; ++cx)
            if (glyph & (1u << (row * 5 + cx))) rr_menu_box(r, ox, oy, unit, x + cx * k, y + row * k, k, k, red, green, blue, 255);
        x += (w + 1) * k;
    }
    return x - start;
}

/* A key cap: the key's name on a lighter plate, one text line tall. Returns its width. */
static int keycap_width(const char *label, size_t length) { (void)label; return (int)length * GW + 4; }
static int keycap(SDL_Renderer *r, int ox, int oy, int unit, int x, int y, const char *label, size_t length) {
    char text[40];
    if (length >= sizeof text) length = sizeof text - 1;
    memcpy(text, label, length); text[length] = 0;
    const int w = keycap_width(text, length);
    rr_menu_box(r, ox, oy, unit, x, y, w, 9, RR_MENU_SELECT, 255);
    rr_menu_box(r, ox, oy, unit, x, y + 9, w, 1, RR_MENU_SHADE, 255);
    rr_menu_text_plain(r, ox, oy, unit, x + 2, y, w, text, RR_MENU_ACCENT);
    return w;
}
int rr_menu_keycap(SDL_Renderer *r, int ox, int oy, int unit, int x, int y, const char *label) {
    return keycap(r, ox, oy, unit, x, y, label, strlen(label));
}

/* "Enter: remap | Left/Right: page": each part is a key and what it does. A part counts as a key when it is short and its
 * only spaces sit beside a '/' or a '+' ("Enter / A", "Ctrl+Alt+K"); anything else stays ordinary text. */
typedef struct { const char *key; size_t key_length; const char *word; size_t word_length; } HintPart;
static bool key_like(const char *s, size_t n) {
    if (!n || n > 14) return false;
    for (size_t i = 0; i < n; ++i)
        if (s[i] == ' ' && !((i && (s[i - 1] == '/' || s[i - 1] == '+')) || (i + 1 < n && (s[i + 1] == '/' || s[i + 1] == '+')))) return false;
    return true;
}
static int hint_parts(const char *text, HintPart *parts, int capacity) {
    int count = 0;
    while (*text && count < capacity) {
        const char *end = strstr(text, " | ");
        size_t length = end ? (size_t)(end - text) : strlen(text);
        HintPart part = {NULL, 0, text, length};
        const char *colon = memchr(text, ':', length);
        if (colon) {
            size_t key = (size_t)(colon - text);
            while (key && text[key - 1] == ' ') --key;
            if (key_like(text, key)) {
                const char *word = colon + 1;
                while (word < text + length && *word == ' ') ++word;
                part.key = text; part.key_length = key; part.word = word; part.word_length = (size_t)(text + length - word);
            }
        }
        while (part.word_length && part.word[part.word_length - 1] == ' ') --part.word_length;
        parts[count++] = part;
        text = end ? end + 3 : text + length;
    }
    return count;
}
static int hint_width(const HintPart *parts, int count) {
    int width = 0;
    for (int i = 0; i < count; ++i)
        width += (parts[i].key ? keycap_width(parts[i].key, parts[i].key_length) + (parts[i].word_length ? 3 : 0) : 0) +
                 (int)parts[i].word_length * GW + (i + 1 < count ? 8 : 0);
    return width;
}
int rr_menu_hints_width(const char *text) {
    HintPart parts[6];
    text = rr_tr(text);
    return hint_width(parts, hint_parts(text, parts, 6));
}
/* Draws the line from x; wider than `available`, it is drawn as plain narrowed text instead (never clipped). */
void rr_menu_hints(SDL_Renderer *r, int ox, int oy, int unit, int x, int y, int available, const char *text, int red, int green, int blue) {
    HintPart parts[6];
    text = rr_tr(text);
    const int count = hint_parts(text, parts, 6);
    if (hint_width(parts, count) > available) { rr_menu_text_plain(r, ox, oy, unit, x, y, available, text, red, green, blue); return; }
    for (int i = 0; i < count; ++i) {
        char word[100];
        if (parts[i].key) x += keycap(r, ox, oy, unit, x, y, parts[i].key, parts[i].key_length) + (parts[i].word_length ? 3 : 0);
        size_t n = parts[i].word_length < sizeof word ? parts[i].word_length : sizeof word - 1;
        memcpy(word, parts[i].word, n); word[n] = 0;
        rr_menu_text_plain(r, ox, oy, unit, x, y, (int)n * GW, word, red, green, blue);
        x += (int)n * GW + 8;
    }
}

/* A notice over the game: a dark plate with a gold line, centred, as wide as its text (at most the menu's width). An icon may
 * lead it (-1: none). The text is a hint line: its keys are drawn as key caps. */
void rr_menu_plate(SDL_Renderer *r, int ox, int oy, int unit, int y, const char *text, int icon) {
    text = rr_tr(text);
    const int lead = icon >= 0 ? rr_menu_icon_width(icon) + 4 : 0;
    int content = rr_menu_hints_width(text) + lead;
    if (content > 232) content = 232;
    const int width = content + 12, x = (256 - width) / 2;
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND);
    rr_menu_box(r, ox, oy, unit, x, y - 3, width, 16, 0, 0, 0, 215);
    rr_menu_box(r, ox, oy, unit, x, y - 3, width, 1, RR_MENU_GOLD, 255);
    rr_menu_box(r, ox, oy, unit, x, y + 12, width, 1, RR_MENU_SHADE, 255);
    if (icon >= 0) rr_menu_icon(r, ox, oy, unit, x + 6, y, icon, false);
    rr_menu_hints(r, ox, oy, unit, x + 6 + lead, y, content - lead, text, RR_MENU_GOLD);
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_NONE);
}

/* The head of a menu. Tall: the mark, the title in large block letters, a line under it, the version at the right (help,
 * the F2 menu). Compact: a small icon (-1: none) and the title in small block letters on the title line, for the pages whose
 * rows start at RR_MENU_FIRST_LINE. */
void rr_menu_header(SDL_Renderer *r, int ox, int oy, int unit, const char *title, const char *subtitle) {
    rr_menu_icon(r, ox, oy, unit, 12, 10, RR_ICON_LOGO, false);
    const int width = rr_menu_block_width(title, 2);
    if (width <= 150) rr_menu_block(r, ox, oy, unit, 43, 12, 2, title, RR_MENU_GOLD);
    else rr_menu_block(r, ox, oy, unit, 43, 14, 1, title, RR_MENU_GOLD);
    if (subtitle) rr_menu_text_fit(r, ox, oy, unit, 43, 23, 150, subtitle, RR_MENU_HINT);
    rr_menu_build_footer(r, ox, oy, unit);
}
void rr_menu_header_compact(SDL_Renderer *r, int ox, int oy, int unit, const char *title, int icon) {
    int x = 14;
    if (icon >= 0) { rr_menu_icon(r, ox, oy, unit, x, 11, icon, false); x += rr_menu_icon_width(icon) + 5; }
    if (x + rr_menu_block_width(title, 1) <= 242) rr_menu_block(r, ox, oy, unit, x, 13, 1, title, RR_MENU_GOLD);
    else rr_menu_text_fit(r, ox, oy, unit, x, RR_MENU_TITLE_LINE, 242 - x, title, RR_MENU_GOLD);
}

/* A gamepad button as a player reads it on the pad, not SDL's identifier ("leftstick"): L3. The four directions are
 * translated. */
const char *rr_menu_pad_name(int button) {
    switch (button) {
    case SDL_CONTROLLER_BUTTON_A: return "A";
    case SDL_CONTROLLER_BUTTON_B: return "B";
    case SDL_CONTROLLER_BUTTON_X: return "X";
    case SDL_CONTROLLER_BUTTON_Y: return "Y";
    case SDL_CONTROLLER_BUTTON_BACK: return "Select";
    case SDL_CONTROLLER_BUTTON_GUIDE: return "Guide";
    case SDL_CONTROLLER_BUTTON_START: return "Start";
    case SDL_CONTROLLER_BUTTON_LEFTSTICK: return "L3";
    case SDL_CONTROLLER_BUTTON_RIGHTSTICK: return "R3";
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: return "L1";
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: return "R1";
    case SDL_CONTROLLER_BUTTON_DPAD_UP: return rr_tr("D-pad up");
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: return rr_tr("D-pad down");
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: return rr_tr("D-pad left");
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: return rr_tr("D-pad right");
    default: {
        const char *name = button >= 0 && button < SDL_CONTROLLER_BUTTON_MAX ?
            SDL_GameControllerGetStringForButton((SDL_GameControllerButton)button) : NULL;
        return name ? name : "-";
    }
    }
}
