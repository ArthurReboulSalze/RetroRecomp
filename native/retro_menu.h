#ifndef RETRO_RECOMP_MENU_H
#define RETRO_RECOMP_MENU_H

#include <SDL.h>
#include <stdbool.h>
#include "runtime_i18n.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Shared 256 x 192 pixel menu canvas for every generated console runtime.
 * Text cells are 5 x 10; menus use 10-unit lines from RR_MENU_FIRST_LINE,
 * with the title on RR_MENU_TITLE_LINE and hints from RR_MENU_HINT_LINE. */
#define RR_MENU_TITLE_LINE 12
#define RR_MENU_FIRST_LINE 24
#define RR_MENU_LINE 10
#define RR_MENU_HINT_LINE 164
#define RR_MENU_LAST_LINE 175
/* Converter identity (smsrecomp/branding.py): near-black panels and gold
 * lettering in every console menu. Colors only: no texture, font or asset. */
#define RR_MENU_PANEL_RGB 18, 18, 18
#define RR_MENU_GOLD 239, 198, 79    /* titles and ordinary lines */
#define RR_MENU_HINT 196, 160, 72    /* key hints and secondary lines */
#define RR_MENU_ACCENT 255, 222, 128 /* emphasis: guns, cartridge Start, notices */
#define RR_MENU_SELECT 81, 68, 42    /* selected row, as in the converter lists */
/* Stored IDs remain stable: sharp=0, xBR=1, Scale2x=2, scanlines=3.
 * F3 presents xBR last without changing an existing saved preference. */
static inline int rr_menu_next_filter(int filter) {
    static const int next[4] = {2, 0, 3, 1};
    return filter >= 0 && filter < 4 ? next[filter] : 0;
}
bool rr_menu_init(SDL_Renderer *renderer);
void rr_menu_shutdown(void);
void rr_menu_layout(SDL_Renderer *renderer, int *x, int *y, int *scale);
void rr_menu_box(SDL_Renderer *renderer, int ox, int oy, int unit,
                 int x, int y, int w, int h, int red, int green, int blue, int alpha);
void rr_menu_text(SDL_Renderer *renderer, int ox, int oy, int unit,
                  int x, int y, const char *label, int red, int green, int blue);
void rr_menu_text_fit(SDL_Renderer *renderer, int ox, int oy, int unit, int x, int y,
                      int available, const char *label, int red, int green, int blue);
int rr_menu_text_width(const char *text);
void rr_menu_begin(SDL_Renderer *renderer, int ox, int oy, int unit);
void rr_menu_end(SDL_Renderer *renderer);
void rr_menu_page_header(SDL_Renderer *renderer, int ox, int oy, int unit,
                         const char *title, int page, int count);
/* The converter injects this version at build time, never from user settings. */
const char *rr_menu_build_label(void);
void rr_menu_build_footer(SDL_Renderer *renderer, int ox, int oy, int unit);

#ifdef __cplusplus
}
#endif

#endif
