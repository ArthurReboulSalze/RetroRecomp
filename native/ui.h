#ifndef SMSRECOMP_UI_H
#define SMSRECOMP_UI_H
#include <SDL.h>
#include <stdbool.h>
bool ui_init(SDL_Renderer *renderer);
void ui_shutdown(void);
void ui_menu(SDL_Renderer *renderer, int kind, int player, int row, bool gamepad,
             bool capture, const char *controller_name, const char *status);
void ui_toast(SDL_Renderer *renderer, const char *text);
void ui_status(SDL_Renderer *renderer, const char *text);
void ui_layout(SDL_Renderer *renderer, int *x, int *y, int *scale);
#endif
