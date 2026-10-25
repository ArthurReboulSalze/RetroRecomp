#ifndef RETRO_RECOMP_KEYBOARD_H
#define RETRO_RECOMP_KEYBOARD_H

#include <SDL.h>
#include <stdbool.h>

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

/* Shift means either Shift key: a binding on one of them also answers to the
 * other, unless that other key has a binding of its own in the same table
 * (every player's keys). Nothing else is aliased. */
static inline SDL_Scancode rr_keyboard_shift_twin(SDL_Scancode scan) {
    return scan == SDL_SCANCODE_LSHIFT ? SDL_SCANCODE_RSHIFT : scan == SDL_SCANCODE_RSHIFT ? SDL_SCANCODE_LSHIFT : SDL_SCANCODE_UNKNOWN;
}

static inline bool rr_keyboard_held(const Uint8 *state, SDL_Scancode scan, const SDL_Scancode *bound, int count) {
    if (scan <= SDL_SCANCODE_UNKNOWN || scan >= SDL_NUM_SCANCODES) return false;
    if (state[scan]) return true;
    SDL_Scancode twin = rr_keyboard_shift_twin(scan);
    if (twin == SDL_SCANCODE_UNKNOWN || !state[twin]) return false;
    for (int i = 0; i < count; ++i) if (bound[i] == twin) return false;
    return true;
}

#endif
