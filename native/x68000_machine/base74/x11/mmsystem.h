/* Retro-Recomp X68000 compat: host MIDI output API used by midi.c.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * This host has no MIDI device: opening always fails, so the machine keeps
 * `hOut` at 0 and emits nothing. Names are mapped to rr_* to avoid clashes
 * with the system's winmm on Windows.
 */
#ifndef RR_BASE74_MMSYSTEM_H
#define RR_BASE74_MMSYSTEM_H

#include "common.h"

typedef UINT MMRESULT;
typedef HANDLE HMIDIOUT;

typedef struct rr_midihdr {
   LPSTR lpData;
   DWORD dwBufferLength;
   DWORD dwBytesRecorded;
   DWORD dwUser;
   DWORD dwFlags;
   struct rr_midihdr *lpNext;
   DWORD reserved;
   DWORD dwOffset;
   DWORD dwReserved[8];
} MIDIHDR;

#define MMSYSERR_NOERROR 0
#define MIDIERR_STILLPLAYING 2
#define MIDI_MAPPER (-1)
#define CALLBACK_NULL 0

static inline MMRESULT rr_midi_unavailable(void) { return 1; }
#define midiOutOpen(h, id, cb, inst, flags) ((void)(h), rr_midi_unavailable())
#define midiOutReset(h) ((void)(h), MMSYSERR_NOERROR)
#define midiOutClose(h) ((void)(h), MMSYSERR_NOERROR)
#define midiOutShortMsg(h, m) ((void)(h), MMSYSERR_NOERROR)
#define midiOutLongMsg(h, p, n) ((void)(h), (void)(p), MMSYSERR_NOERROR)
#define midiOutPrepareHeader(h, p, n) ((void)(h), (void)(p), MMSYSERR_NOERROR)
#define midiOutUnprepareHeader(h, p, n) ((void)(h), (void)(p), MMSYSERR_NOERROR)

#endif
