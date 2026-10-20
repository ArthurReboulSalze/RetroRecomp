/* Converter-only SDL controller polling, called on Tk's owning thread.
 * No window, audio device, keyboard hook, game injection or input forwarding. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <stdint.h>
#include <stdlib.h>
#ifdef _WIN32
#define RR_PAD_API __declspec(dllexport)
#else
#define RR_PAD_API __attribute__((visibility("default")))
#endif
typedef struct { SDL_GameController *pad[4]; } RrPlayerPads;
static void refresh(RrPlayerPads *p) {
    for (int i = 0; i < 4; ++i) if (p->pad[i] && !SDL_GameControllerGetAttached(p->pad[i])) {
        SDL_GameControllerClose(p->pad[i]); p->pad[i] = NULL;
    }
    for (int i = 0; i < SDL_NumJoysticks(); ++i) if (SDL_IsGameController(i)) {
        SDL_JoystickID id = SDL_JoystickGetDeviceInstanceID(i);
        int known = 0;
        for (int j = 0; j < 4; ++j) if (p->pad[j] &&
            SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(p->pad[j])) == id) known = 1;
        if (!known) for (int j = 0; j < 4; ++j) if (!p->pad[j]) {p->pad[j] = SDL_GameControllerOpen(i); break;}
    }
}
RR_PAD_API RrPlayerPads *rr_player_pads_open(void) {
    SDL_SetMainReady();
    SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, "1");
    if (SDL_InitSubSystem(SDL_INIT_GAMECONTROLLER) != 0) return NULL;
    RrPlayerPads *p = (RrPlayerPads *)calloc(1, sizeof(*p));
    if (!p) {SDL_QuitSubSystem(SDL_INIT_GAMECONTROLLER); return NULL;}
    refresh(p); return p;
}
RR_PAD_API int rr_player_pads_poll(RrPlayerPads *p, int32_t *values) {
    if (!p || !values) return -1;
    SDL_PumpEvents();
    SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
    refresh(p);
    int count = 0;
    for (int i = 0; i < 4; ++i) {
        Uint32 mask = 0;
        if (p->pad[i]) {
            ++count;
            for (int b = 0; b < SDL_CONTROLLER_BUTTON_MAX; ++b)
                if (SDL_GameControllerGetButton(p->pad[i], (SDL_GameControllerButton)b)) mask |= 1u << b;
        }
        values[i * 3] = (int32_t)mask;
        values[i * 3 + 1] = p->pad[i] ? SDL_GameControllerGetAxis(p->pad[i], SDL_CONTROLLER_AXIS_LEFTX) : 0;
        values[i * 3 + 2] = p->pad[i] ? SDL_GameControllerGetAxis(p->pad[i], SDL_CONTROLLER_AXIS_LEFTY) : 0;
    }
    return count;
}
RR_PAD_API void rr_player_pads_close(RrPlayerPads *p) {
    if (!p) return;
    for (int i = 0; i < 4; ++i) if (p->pad[i]) SDL_GameControllerClose(p->pad[i]);
    free(p); SDL_QuitSubSystem(SDL_INIT_GAMECONTROLLER);
}
