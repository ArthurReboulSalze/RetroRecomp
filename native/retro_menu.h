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
/* Stored IDs remain stable: sharp=0, xBR=1, Scale2x=2, scanlines=3, CRT flat=4, CRT curved=5, LCD grid=6 (display_settings.h).
 * F3's order: sharp, Scale2x, scanlines, xBR, CRT flat, CRT curved, then the LCD grid on a machine with an LCD screen (lcd). */
static inline int rr_menu_next_filter(int filter, int lcd) {
    static const int next[7] = {2, 4, 3, 1, 5, 6, 0};
    const int n = filter >= 0 && filter < 7 ? next[filter] : 0;
    return n == 6 && !lcd ? 0 : n;
}
static inline int rr_menu_previous_filter(int filter, int lcd) {
    static const int previous[7] = {6, 3, 0, 2, 1, 4, 5};
    const int p = filter >= 0 && filter < 7 ? previous[filter] : 0;
    return p == 6 && !lcd ? 5 : p;
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
/* Text that is already translated: drawn as it is, with no look-up in the catalogue. */
void rr_menu_text_plain(SDL_Renderer *renderer, int ox, int oy, int unit, int x, int y,
                        int available, const char *text, int red, int green, int blue);
int rr_menu_text_width(const char *text);
/* UTF-8 in, the ASCII a game draws out (accents dropped, other characters '?'), at most cap - 1 characters; returns how many. */
size_t rr_menu_ascii_text(const char *text, char *out, size_t cap);
void rr_menu_begin(SDL_Renderer *renderer, int ox, int oy, int unit);
void rr_menu_end(SDL_Renderer *renderer);
void rr_menu_page_header(SDL_Renderer *renderer, int ox, int oy, int unit,
                         const char *title, int page, int count);
/* Pixel art of the menus (1.7.4): small icons, block letters, key caps and notice plates, all drawn from packed rows of
 * retro_menu.c (no image, no texture). Coordinates are menu units, as for the text. */
#define RR_MENU_SHADE 46, 38, 20     /* dark gold: icon fills, the lower edge of a key cap, separators */
/* 1.7.5: the 9 x 9 row icons (RR_ICON_ROW_*) follow the tiles', drawn by the same rr_menu_icon. */
enum { RR_ICON_KEYBOARD, RR_ICON_GAMEPAD, RR_ICON_OPTIONS, RR_ICON_POINTER, RR_ICON_SWITCHES, RR_ICON_LOGO,
       RR_ICON_KEYBOARD_SMALL, RR_ICON_GAMEPAD_SMALL, RR_ICON_OPTIONS_SMALL,
       RR_ICON_GRAPHICS,  /* 1.7.6: the F2 tile of the graphics page, a 3D shape on a screen */
       RR_ICON_CHAT,      /* the F2 tile of the multiplayer chat, a speech bubble */
       RR_ICON_EXIT,      /* 1.9.0: the F2 tile that quits the game, a door and an arrow */
       RR_ICON_RESTART,   /* 1.9.0: the F2 tile that restarts the game, two arcs of a ring with their arrows */
       RR_ICON_PASS,      /* 1.9.0: multiplayer, turns: pass the controller (a pad, an arrow on) */
       RR_ICON_GIVE,      /* 1.9.0: the host gives the controller (a pad, an arrow to a player) */
       RR_ICON_SHARING,   /* 1.9.0: the host switches everyone at once / turns (two players, arrows both ways) */
       RR_ICON_CONTROLS,  /* 1.9.0: the F2 tile of the players' controls (a keyboard and a pad) */
       RR_ICON_DISPLAY_WINDOW, RR_ICON_DISPLAY_PIXEL, RR_ICON_DISPLAY_FIT, RR_ICON_DISPLAY_STRETCH,   /* 1.9.0: the F2 display
                          * mode tile, one a mode in display_mode's order (RR_ICON_DISPLAY_WINDOW + mode) */
       /* <row enum> */
       RR_ICON_ROW_UP, RR_ICON_ROW_DOWN, RR_ICON_ROW_LEFT, RR_ICON_ROW_RIGHT, RR_ICON_ROW_BUTTON, RR_ICON_ROW_START,
       RR_ICON_ROW_SELECT, RR_ICON_ROW_COIN, RR_ICON_ROW_PAUSE, RR_ICON_ROW_QUIT, RR_ICON_ROW_RESTART, RR_ICON_ROW_SAVE,
       RR_ICON_ROW_LOAD, RR_ICON_ROW_GAMEPAD, RR_ICON_ROW_STICK, RR_ICON_ROW_KEYBOARD, RR_ICON_ROW_FILTER,
       RR_ICON_ROW_DISPLAY, RR_ICON_ROW_AUTOFIRE, RR_ICON_ROW_LANGUAGE, RR_ICON_ROW_RECORD, RR_ICON_ROW_WAVE,
       RR_ICON_ROW_VOLUME, RR_ICON_ROW_SOUND, RR_ICON_ROW_HEADPHONES, RR_ICON_ROW_FKEY, RR_ICON_ROW_REMINDER,
       RR_ICON_ROW_SPEED, RR_ICON_ROW_RUMBLE, RR_ICON_ROW_RESTORE, RR_ICON_ROW_PORT_MOUSE, RR_ICON_ROW_PORT_JOYSTICK,
       RR_ICON_ROW_EXIT, RR_ICON_ROW_PALETTE, RR_ICON_ROW_SPRITE, RR_ICON_ROW_DIP, RR_ICON_ROW_DISK, RR_ICON_ROW_MOUSE,
       RR_ICON_ROW_HELP, RR_ICON_ROW_SLIDERS, RR_ICON_ROW_MAXSPEED, RR_ICON_ROW_GRAPHICS, RR_ICON_ROW_WIDESCREEN,
       RR_ICON_ROW_SYNC, RR_ICON_ROW_GENERIC,
       /* </row enum> */ RR_ICON_COUNT };
int rr_menu_icon_width(int icon);
/* A face button's row icon (1.7.5): the ring with up to three letters inside ("A", "3", "L1", "ii" for II, "^" "o" "[" "x" for the
 * PlayStation shapes); false when a letter has no drawing (the caller then shows the generic icon). */
bool rr_menu_button_letters(const char *letters);
void rr_menu_button(SDL_Renderer *renderer, int ox, int oy, int unit, int x, int y, const char *letters);
void rr_menu_icon(SDL_Renderer *renderer, int ox, int oy, int unit, int x, int y, int icon, bool dim);
/* Block letters, five cells tall, `k` units a cell; both translate `text` and return its width in units. */
int rr_menu_block_width(const char *text, int k);
int rr_menu_block(SDL_Renderer *renderer, int ox, int oy, int unit, int x, int y, int k, const char *text,
                  int red, int green, int blue);
/* A key cap around `label` as it is (already translated); returns its width. */
int rr_menu_keycap(SDL_Renderer *renderer, int ox, int oy, int unit, int x, int y, const char *label);
/* A hint line such as "Enter: remap | Left/Right: page": the keys become key caps. Wider than `available`, it is drawn as
 * plain narrowed text. */
int rr_menu_hints_width(const char *text);
void rr_menu_hints(SDL_Renderer *renderer, int ox, int oy, int unit, int x, int y, int available, const char *text,
                   int red, int green, int blue);
/* A notice over the game picture: a dark plate, centred, with an optional icon (-1: none). */
void rr_menu_plate(SDL_Renderer *renderer, int ox, int oy, int unit, int y, const char *text, int icon);
void rr_menu_header(SDL_Renderer *renderer, int ox, int oy, int unit, const char *title, const char *subtitle);
void rr_menu_header_compact(SDL_Renderer *renderer, int ox, int oy, int unit, const char *title, int icon);
const char *rr_menu_pad_name(int button);   /* "L3", "Select", "D-pad up" (translated) */
/* The converter injects this version at build time, never from user settings. */
const char *rr_menu_build_label(void);
void rr_menu_build_footer(SDL_Renderer *renderer, int ox, int oy, int unit);

#ifdef __cplusplus
}
#endif

#endif
