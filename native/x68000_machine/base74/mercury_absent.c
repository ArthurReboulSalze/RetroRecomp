/* Retro-Recomp X68000: YMF288 side of a Mercury Unit that is not fitted.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * The machine profile has no Mercury Unit (NO_MERCURY): x68k/mercury.c keeps
 * its register decode, the OPN pair behind it is absent and reads as 0.
 */
#include "common.h"
#include "fmg_wrap.h"

int M288_Init(int clock, int rate, const char *path) { (void)clock; (void)rate; (void)path; return 0; }
void M288_Cleanup(void) {}
void M288_Reset(void) {}
void M288_Update(short *buffer, int length) { (void)buffer; (void)length; }
void FASTCALL M288_Write(DWORD r, BYTE v) { (void)r; (void)v; }
BYTE FASTCALL M288_Read(WORD a) { (void)a; return 0; }
void FASTCALL M288_Timer(DWORD step) { (void)step; }
void M288_SetVolume(BYTE vol) { (void)vol; }
void M288_SetRate(int clock, int rate) { (void)clock; (void)rate; }
