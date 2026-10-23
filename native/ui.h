#ifndef SMSRECOMP_UI_H
#define SMSRECOMP_UI_H
#include <SDL.h>
#include <stdbool.h>
bool ui_init(SDL_Renderer *renderer);
void ui_shutdown(void);
void ui_menu(SDL_Renderer *renderer, int kind, int player, int row, bool gamepad,
             bool capture, const char *controller_name, const char *status);
/* Position of the next ui_menu among the F2 pages; a count of 0 hides the squares. */
void ui_pages(int page, int count);
/* Extra rows after player 1's controls (quit and restart combinations), with
 * the hint shown while one is selected; the strings live until ui_menu. */
void ui_combos(int count, const char *const *labels, const char *const *values, const char *hint);
/* First control row on the 256 x 192 menu grid; rows are RR_MENU_LINE apart. */
int ui_rows_top(bool gamepad);
void ui_toast(SDL_Renderer *renderer, const char *text);
void ui_status(SDL_Renderer *renderer, const char *text);
void ui_layout(SDL_Renderer *renderer, int *x, int *y, int *scale);
void ui_phaser_reticle(SDL_Renderer *renderer, int x, int y, int scale);
#endif
