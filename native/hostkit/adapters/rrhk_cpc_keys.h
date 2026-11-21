/* The Amstrad CPC's keyboard on the host's: each host key (SDL scancode) to the CPC key at the same position on the keyboard
 * (the CPC 6128's UK layout over a PC keyboard, US or ISO), as the player types and as the boot key sequence types. MIT,
 * Retro-Recomp. Host role, owner the CPC (the adapter maps the frame's keys through it). retrorecomp/cpc_keys.py holds the same
 * table for the converter, which types a start command through its inverse; tests/test_cpc_keys.py checks they are equal.
 *
 * The rows the keys of the CPC's main block take: 1-0 and - ^ above Q-P @ [ (the PC's [ and ] keys), A-L : ; ] (the PC's ; ' and
 * # or \ keys), Z-M , . / \ (the ISO key left of Z for \). Backspace is DEL, Delete is CLR, Left Alt is COPY, the keypad is the
 * CPC's function keys f0-f9, its point and its small ENTER. */
#ifndef RRHK_CPC_KEYS_H
#define RRHK_CPC_KEYS_H
#include <stdint.h>

#include "cpc_ppi.h"

typedef struct { uint8_t scancode; uint8_t cpc_key; } RrhkCpcKey;

static const RrhkCpcKey RRHK_CPC_KEYS[] = {
    { 4, CPC_KEY_A }, { 5, CPC_KEY_B }, { 6, CPC_KEY_C }, { 7, CPC_KEY_D }, { 8, CPC_KEY_E }, { 9, CPC_KEY_F },
    { 10, CPC_KEY_G }, { 11, CPC_KEY_H }, { 12, CPC_KEY_I }, { 13, CPC_KEY_J }, { 14, CPC_KEY_K }, { 15, CPC_KEY_L },
    { 16, CPC_KEY_M }, { 17, CPC_KEY_N }, { 18, CPC_KEY_O }, { 19, CPC_KEY_P }, { 20, CPC_KEY_Q }, { 21, CPC_KEY_R },
    { 22, CPC_KEY_S }, { 23, CPC_KEY_T }, { 24, CPC_KEY_U }, { 25, CPC_KEY_V }, { 26, CPC_KEY_W }, { 27, CPC_KEY_X },
    { 28, CPC_KEY_Y }, { 29, CPC_KEY_Z },
    { 30, CPC_KEY_1 }, { 31, CPC_KEY_2 }, { 32, CPC_KEY_3 }, { 33, CPC_KEY_4 }, { 34, CPC_KEY_5 }, { 35, CPC_KEY_6 },
    { 36, CPC_KEY_7 }, { 37, CPC_KEY_8 }, { 38, CPC_KEY_9 }, { 39, CPC_KEY_0 },
    { 40, CPC_KEY_RETURN }, { 41, CPC_KEY_ESC }, { 42, CPC_KEY_DEL }, { 43, CPC_KEY_TAB }, { 44, CPC_KEY_SPACE },
    { 45, CPC_KEY_MINUS }, { 46, CPC_KEY_CARET }, { 47, CPC_KEY_AT }, { 48, CPC_KEY_LBRACKET }, { 49, CPC_KEY_RBRACKET },
    { 50, CPC_KEY_RBRACKET }, { 51, CPC_KEY_COLON }, { 52, CPC_KEY_SEMICOLON }, { 54, CPC_KEY_COMMA }, { 55, CPC_KEY_DOT },
    { 56, CPC_KEY_SLASH }, { 57, CPC_KEY_CAPSLOCK }, { 76, CPC_KEY_CLR },
    { 79, CPC_KEY_RIGHT }, { 80, CPC_KEY_LEFT }, { 81, CPC_KEY_DOWN }, { 82, CPC_KEY_UP },
    { 88, CPC_KEY_ENTER }, { 89, CPC_KEY_F1 }, { 90, CPC_KEY_F2 }, { 91, CPC_KEY_F3 }, { 92, CPC_KEY_F4 }, { 93, CPC_KEY_F5 },
    { 94, CPC_KEY_F6 }, { 95, CPC_KEY_F7 }, { 96, CPC_KEY_F8 }, { 97, CPC_KEY_F9 }, { 98, CPC_KEY_F0 }, { 99, CPC_KEY_FDOT },
    { 100, CPC_KEY_BACKSLASH },
    { 224, CPC_KEY_CONTROL }, { 225, CPC_KEY_SHIFT }, { 226, CPC_KEY_COPY }, { 228, CPC_KEY_CONTROL }, { 229, CPC_KEY_SHIFT },
};
#endif
