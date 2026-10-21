/* Retro-Recomp X68000 compat: the Win32-style types the 2014 machine code uses.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Written from the list of identifiers used by the kept sources
 * (docs/X68000_PHASE3_PORTING.md section 1). Fixed widths on every host:
 * DWORD is 32-bit on Windows and Linux alike.
 */
#ifndef RR_BASE74_WINDOWS_H
#define RR_BASE74_WINDOWS_H

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef signed char CHAR;
typedef int16_t SHORT;
typedef int32_t INT;
typedef int32_t LONG;
typedef uint8_t UCHAR;
typedef uint16_t USHORT;
typedef uint32_t UINT;
typedef uint32_t ULONG;
typedef uint8_t BYTE;
typedef uint16_t WORD;
typedef uint32_t DWORD;
typedef int BOOL;
typedef void VOID;
typedef void *PVOID;
typedef void *LPVOID;
typedef BYTE *LPBYTE;
typedef char *LPSTR;
typedef const char *LPCSTR;
typedef void *HANDLE;
typedef int HWND;
typedef struct { LONG x, y; } POINT;

#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif
#ifndef MAX_PATH
#define MAX_PATH 1024
#endif

#define WINAPI
#define CALLBACK
#define UNUSED(v) ((void)(v))
#define INLINE static inline

#define ZeroMemory(d, n) memset((d), 0, (n))
#define CopyMemory(d, s, n) memcpy((d), (s), (n))
#define FillMemory(d, n, v) memset((d), (v), (n))
#define bzero(d, n) memset((d), 0, (n))

#ifdef __cplusplus
extern "C" {
#endif
/* Deterministic stand-in for the millisecond wall clock: the kept code only
 * uses it to stamp host MIDI/ROMEO output queues, never guest state. */
DWORD timeGetTime(void);
#ifdef __cplusplus
}
#endif

#endif
