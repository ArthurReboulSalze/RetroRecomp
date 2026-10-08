#ifndef RETRO_RECOMP_KEYBOARD_H
#define RETRO_RECOMP_KEYBOARD_H

#include <SDL.h>

/* Scancodes remain physical bindings in memory and on disk. Only their menu
 * labels and unsaved letter defaults follow SDL's active keyboard layout. */
static inline const char *rr_keyboard_name(SDL_Scancode scan) {
    SDL_Keycode key = SDL_GetKeyFromScancode(scan);
    const char *name = key != SDLK_UNKNOWN ? SDL_GetKeyName(key) : NULL;
    return name && name[0] ? name : SDL_GetScancodeName(scan);
}

static inline SDL_Scancode rr_keyboard_letter(SDL_Keycode key, SDL_Scancode fallback) {
    SDL_Scancode scan = SDL_GetScancodeFromKey(key);
    return scan != SDL_SCANCODE_UNKNOWN ? scan : fallback;
}

#endif
