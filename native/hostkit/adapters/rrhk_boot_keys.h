/* The boot key sequence of a computer game: the command a game starts from (the Amstrad CPC's RUN"BOMB and RETURN), typed by
 * the player shell into the computer's keyboard, counted in emulated frames. MIT, Retro-Recomp. Host role; its only user today
 * is the Amstrad CPC's adapter (docs/HOST_KIT.md: reviewed by the interface specialist, 21 Nov 2026).
 *
 * The sequence is data the game carries (generated/boot_keys.h, written at conversion from the disk's catalogue, in the game's
 * stamp): host keys, the scancodes of the session's key set (hostkit_session.h), each with or without Left Shift, at the position
 * of the computer's key on the host keyboard (the computer's own positional table maps them, as it maps the player's typing).
 *
 * The rule, the same on every PC: from the machine's reset (emulated frame 0) to the end of the last key's gap, the sequence owns
 * the keyboard: the adapter takes this frame's keys from here and ignores every keyboard-derived input of the player (his keys,
 * the host's typing in a session, the pad's keyboard aliases); only the joystick lines stay live. Before `start_frame` no key is
 * down (the computer boots); then each key is down `hold_frames` frames and every key up `gap_frames` frames, so two equal letters
 * in a row read as two and a key the player holds cannot merge with the last one. The frame is the machine's emulated frame, in
 * its quick state, its rollback snapshot and its digest: a pause, a menu or a fast-forward changes nothing, a restart replays it. */
#ifndef RRHK_BOOT_KEYS_H
#define RRHK_BOOT_KEYS_H
#include <stdint.h>
#include <string.h>

#if defined(__has_include)
#if __has_include(<SDL_scancode.h>)
#include <SDL_scancode.h>
#define RRHK_BOOT_KEYS_SDL 1
#endif
#endif
#ifndef RRHK_BOOT_KEYS_SDL
enum { SDL_SCANCODE_LSHIFT = 225, SDL_NUM_SCANCODES = 512 };   /* SDL's own values, for a build without SDL's headers */
#endif

typedef struct {
    uint8_t scancode;       /* a host key of the session set (SDL scancodes 4 to 100) */
    uint8_t shift;          /* 1: Left Shift down with it */
} RrhkBootKey;

typedef struct {
    uint16_t start_frame;   /* emulated frames after reset before the first key */
    uint8_t hold_frames;    /* frames each key is down (at least 1) */
    uint8_t gap_frames;     /* frames every key is up after it (at least 1) */
    uint16_t count;         /* 0: no sequence */
    const RrhkBootKey *keys;
} RrhkBootKeys;

/* The frame after the sequence's last gap: from it on the player has the keyboard (0 when there is no sequence). */
static inline uint32_t rrhk_boot_keys_end(const RrhkBootKeys *seq)
{
    if (!seq || !seq->count || !seq->keys)
        return 0;
    return (uint32_t)seq->start_frame + (uint32_t)seq->count * ((uint32_t)seq->hold_frames + seq->gap_frames);
}

/* Emulated frame `frame`: 1 while the sequence owns the keyboard, `state` (SDL_NUM_SCANCODES bytes, as SDL's keyboard state)
 * then holds exactly its keys of that frame; 0 once it is over or when there is none, `state` untouched. Pure. */
static inline int rrhk_boot_keys_frame(const RrhkBootKeys *seq, uint32_t frame, uint8_t *state)
{
    if (frame >= rrhk_boot_keys_end(seq))
        return 0;
    memset(state, 0, SDL_NUM_SCANCODES);
    if (frame < seq->start_frame)
        return 1;
    uint32_t period = (uint32_t)seq->hold_frames + seq->gap_frames;
    uint32_t at = frame - seq->start_frame;
    const RrhkBootKey *key = &seq->keys[at / period];
    if (at % period < seq->hold_frames) {
        state[key->scancode] = 1;
        if (key->shift)
            state[SDL_SCANCODE_LSHIFT] = 1;
    }
    return 1;
}
#endif
