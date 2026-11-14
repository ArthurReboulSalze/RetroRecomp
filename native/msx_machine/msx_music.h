/* MSX-MUSIC: the YM2413 (OPLL) of every MSX2+, at I/O ports 7Ch (register) and 7Dh (data). MIT, Retro-Recomp.
 *
 * Built only into an MSX2+ program (msx_build stages it with emu2413 for that machine): the machine reaches it through the
 * hooks of MsxFm (msx_machine.h), so the MSX and MSX2 programs link nothing of it. */
#ifndef RR_MSX_MUSIC_H
#define RR_MSX_MUSIC_H
#include "msx_machine.h"

/* The one chip of the program, its hooks set; it is reset at cycle 0. NULL when the chip cannot be made. */
MsxFm *msx_music_create(void);
#endif
