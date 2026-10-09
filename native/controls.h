#ifndef SMSRECOMP_CONTROLS_H
#define SMSRECOMP_CONTROLS_H
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>

enum { FILTER_NEAREST, FILTER_LINEAR, FILTER_SCALE2X, FILTER_SCANLINES, FILTER_COUNT };
enum { CONTROL_PLAYERS = 2, CONTROL_GAME_ACTIONS = 6, CONTROL_PAUSE = 6, CONTROL_RESET = 7, CONTROL_ACTIONS = 8 };
enum { PHASER_CROSS, PHASER_DOT, PHASER_SHAPE_COUNT };
enum { PHASER_RED, PHASER_WHITE, PHASER_GREEN, PHASER_COLOR_COUNT };
typedef struct {
    SDL_Scancode keys[CONTROL_PLAYERS][CONTROL_ACTIONS];
    SDL_GameControllerButton buttons[CONTROL_PLAYERS][CONTROL_ACTIONS];
    int filter;
    int display_mode; /* 0 window, 1 integer fullscreen, 2 aspect-fit fullscreen */
    int first_controller_player;
    int language; /* 0 English, 1 French */
    bool autofire; /* Both mapped gamepad fire buttons, while held. */
    int phaser_dot_size; /* 1..5 source pixels; shared presentation setting */
    int phaser_shape;
    int phaser_color;
} Controls;
extern Controls controls;
const char *controls_label(int row);
const char *controls_filter_label(int filter);
const char *controls_text(const char *english, const char *french);
void controls_load(void);
bool controls_bind(int player, int row, bool gamepad, int value);
bool controls_filter(int filter);
bool controls_display_mode(int mode);
bool controls_controller_order(int first_player);
bool controls_language(int language);
bool controls_autofire(bool enabled);
void controls_reset_autofire(void);
bool controls_phaser_dot_size(int size);
bool controls_phaser_shape(int shape);
bool controls_phaser_color(int color);
bool controls_system_key(SDL_Scancode key, int action);
bool controls_system_button(int player, int button, int action);
int controls_action_count(int player);
bool controls_defaults(int player, bool gamepad);
bool controls_reserved(SDL_Scancode key);
uint8_t controls_read(int player, SDL_GameController *controller, bool focused);
#endif
