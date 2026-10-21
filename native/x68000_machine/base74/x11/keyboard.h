/* Retro-Recomp X68000 compat: keyboard queue towards the MFP.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 * The queue itself is NONAKA Kimihiro's code kept from 74ddbb3 (BSD).
 */
#ifndef RR_BASE74_KEYBOARD_H
#define RR_BASE74_KEYBOARD_H

#include "common.h"

#define KeyBufSize 128
#define RETROK_XFX 333

extern BYTE KeyBuf[KeyBufSize];
extern BYTE KeyBufWP;
extern BYTE KeyBufRP;
extern BYTE KeyEnable;
extern BYTE KeyIntFlag;

void Keyboard_Init(void);
void Keyboard_Int(void);
void send_keycode(BYTE code, int flag);
int Keyboard_IsSwKeyboard(void);

#endif
