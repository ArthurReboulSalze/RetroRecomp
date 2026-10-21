/* Retro-Recomp X68000 compat: common declarations for the 2014 machine code.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 */
#ifndef RR_BASE74_COMMON_H
#define RR_BASE74_COMMON_H

#include "windows.h"
#include <stdio.h>
#include <string.h>

#define SUCCESS 0
#define FAILURE 1
#define FASTCALL
#define STDCALL
#define LABEL
#ifndef __stdcall
#define __stdcall
#endif
/* MSVC: the only use (bg.c sprite table) is naturally 8-byte aligned. */
#if defined(_MSC_VER) && !defined(__attribute__)
#define __attribute__(x)
#endif

typedef uint8_t UINT8;
typedef uint16_t UINT16;
typedef uint32_t UINT32;
typedef int8_t INT8;
typedef int16_t INT16;
typedef int32_t INT32;

typedef union {
   struct {
      BYTE l;
      BYTE h;
   } b;
   WORD w;
} PAIR;

#ifdef __cplusplus
extern "C" {
#endif
/* Diagnostic only: must never stop emulation (MFP reaches it in games). */
void Error(const char *message);
void p6logd(const char *format, ...);
#ifdef __cplusplus
}
#endif

#endif
