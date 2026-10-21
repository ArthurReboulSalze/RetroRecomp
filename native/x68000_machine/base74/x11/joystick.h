/* Retro-Recomp X68000 compat: joystick ports (implemented in input.c).
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 */
#ifndef RR_BASE74_JOYSTICK_H
#define RR_BASE74_JOYSTICK_H

#include "common.h"

#define PAD_2BUTTON 0
#define PAD_CPSF_MD 1
#define PAD_CPSF_SFC 2
#define PAD_CYBERSTICK_D 3
#define PAD_CYBERSTICK_A 4

#define JOY_UP 0x01
#define JOY_DOWN 0x02
#define JOY_LEFT 0x04
#define JOY_RIGHT 0x08
#define JOY_TRG2 0x20
#define JOY_TRG1 0x40

void Joystick_Init(void);
void Joystick_Cleanup(void);
BYTE Joystick_Read(BYTE num);
void Joystick_Write(BYTE num, BYTE data);
void Joystick_Update(int is_menu, int key, int port);
BYTE get_joy_downstate(void);
void reset_joy_downstate(void);
extern BYTE JoyKeyState;

#endif
