/* A save file a game cannot use, set aside under another name: the one rule of every machine (the PlayStation's memory card first;
 * cart_save.c, the Atari ST's disk writes and the X68000's disks keep their own copy until they move to this file, with identical
 * results). Original RetroRecomp code: MIT. */
#ifndef RR_SAVE_SET_ASIDE_H
#define RR_SAVE_SET_ASIDE_H
#include <stdbool.h>
#include <wchar.h>

/* Moves `file` to "<file>.unusable-N", the first N from 1 to 99 that is free. Never deletes it, and never replaces a file already
 * set aside: with all 99 names taken, or when the move fails, it returns false and the file stays where it is. */
bool rr_save_set_aside(const wchar_t *file);
#endif
