/* Numeric checks only: no video driver, window, rendering or capture. The action table and the defaults of the Master
 * System / Game Gear adapter of the host kit, the machine fields the shell relies on, and the picture crop and placement
 * arithmetic. NDEBUG must not disable checks in this Release target. */
#undef NDEBUG
#include <assert.h>
#include "hostkit/adapters/rrhk_sms.c"
#include "hostkit/hostkit_internal.h"

static void tables(void) {
    const RrhkMachine *m = rrhk_adapter();
    assert(m->action_count == ACTIONS && m->table_players == PLAYERS && m->players() == PLAYERS && m->driven && m->own_audio);
    /* The pad byte of the runner: four directions, two face buttons that autofire, the Game Gear's cartridge Start. */
    unsigned seen = 0;
    for (int a = 0; a < ACTIONS; ++a) {
        const RrhkAction *action = &m->actions[a];
        assert(!(seen & action->bit)); seen |= action->bit;
        assert((action->group == RRHK_FACE) == (a == BUTTON1 || a == BUTTON2));
        assert(action->bit <= SMS_PAD_START);
    }
    assert(m->actions[PAUSE].bit == 0 && m->host_pause == PAUSE + 1);       /* the host's own: the guest never sees it */
#ifdef RETRO_GAME_GEAR
    assert(seen == (SMS_PAD_UP | SMS_PAD_DOWN | SMS_PAD_LEFT | SMS_PAD_RIGHT | SMS_PAD_B1 | SMS_PAD_B2 | SMS_PAD_START));
    assert(m->actions[PAUSE].key[0] == SDL_SCANCODE_P && m->actions[START].key[0] == SDL_SCANCODE_RETURN && m->start == START);
    assert(m->actions[PAUSE].pad[0] == SDL_CONTROLLER_BUTTON_BACK && m->actions[START].pad[0] == SDL_CONTROLLER_BUTTON_START);
    assert(!wcscmp(m->ini_section, L"GameGear"));
#else
    assert(seen == (SMS_PAD_UP | SMS_PAD_DOWN | SMS_PAD_LEFT | SMS_PAD_RIGHT | SMS_PAD_B1 | SMS_PAD_B2));
    assert(m->actions[PAUSE].key[0] == SDL_SCANCODE_RETURN && m->actions[PAUSE].key[1] == SDL_SCANCODE_KP_7);
    assert(m->actions[PAUSE].pad[0] == SDL_CONTROLLER_BUTTON_START && m->actions[UP].key[1] == SDL_SCANCODE_KP_5);
    assert(!wcscmp(m->ini_section, L"MasterSystem"));
#endif
    assert(!wcscmp(m->actions[BUTTON1].ini_key, L"Button1") && m->actions[BUTTON1].letter == SDLK_w);
}

static void placement(void) {
    SDL_Rect r;
    /* Whole pixels, centred, in the window and in the first fullscreen mode; the Game Gear window is 160 x 144. */
    full_crop = crop = (SDL_Rect){0, 0, SMS_SCREEN_W, SMS_SCREEN_H};
    assert(game_rect(1920, 1080, 0, &r) && r.w == 1280 && r.h == 960 && r.x == 320 && r.y == 60);
    assert(game_rect(1920, 1080, 1, &r) && r.w == 1280 && r.h == 960);
    assert(game_rect(1920, 1080, 2, &r) && r.w == 1440 && r.h == 1080 && r.x == 240 && r.y == 0);
    full_crop = crop = (SDL_Rect){48, 24, GG_SCREEN_W, GG_SCREEN_H};
    assert(game_rect(1920, 1080, 0, &r) && r.w == 1120 && r.h == 1008 && r.x == 400 && r.y == 36);
    /* A game that blanks the left column keeps the scale of the full picture. */
    full_crop = (SDL_Rect){0, 0, SMS_SCREEN_W, SMS_SCREEN_H}; crop = (SDL_Rect){8, 0, SMS_SCREEN_W - 8, SMS_SCREEN_H};
    SDL_Rect full; game_rect(1280, 960, 0, &full); assert(full.h == 960 && full.w == 248 * 5);
    /* Smaller than the picture: it keeps one pixel per pixel, centred (the window cannot be made smaller). */
    full_crop = crop = (SDL_Rect){0, 0, SMS_SCREEN_W, SMS_SCREEN_H};
    assert(game_rect(200, 130, 0, &r) && r.w == 256 && r.h == 192);
}

int main(void) {
    tables();
    placement();
    puts("PASS: action table and defaults of the Master System / Game Gear adapter; whole-pixel, fit and blanked-column placement.");
    return 0;
}
