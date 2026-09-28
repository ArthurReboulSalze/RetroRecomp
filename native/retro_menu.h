#ifndef RETRO_RECOMP_MENU_H
#define RETRO_RECOMP_MENU_H

#include <SDL.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Shared 256 x 192 pixel menu canvas for every generated console runtime. */
bool rr_menu_init(SDL_Renderer *renderer);
void rr_menu_shutdown(void);
void rr_menu_layout(SDL_Renderer *renderer, int *x, int *y, int *scale);
void rr_menu_box(SDL_Renderer *renderer, int ox, int oy, int unit,
                 int x, int y, int w, int h, int red, int green, int blue, int alpha);
void rr_menu_text(SDL_Renderer *renderer, int ox, int oy, int unit,
                  int x, int y, const char *label, int red, int green, int blue);
void rr_menu_begin(SDL_Renderer *renderer, int ox, int oy, int unit);
void rr_menu_end(SDL_Renderer *renderer);

#ifdef __cplusplus
}
#endif

#endif
