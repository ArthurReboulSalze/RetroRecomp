/* Saves of the CPS-1.5 (QSound) boards: the 93C46 EEPROM (settings, scores) between runs. Original work: MIT.
 * Separate from quick states; interactive play only (validation runs never read or write it). */
#ifndef RR_CPS1_PERSISTENCE_H
#define RR_CPS1_PERSISTENCE_H
#include <stdbool.h>
#include <stddef.h>
#include <wchar.h>

/* After the board started: loads the saved EEPROM of this exact set when there is a valid one. False when a file exists
 * and cannot be used (it is left alone and nothing is written over it). A board without an EEPROM does nothing. */
bool rr_cps1_save_begin(void);
/* After every frame: writes the EEPROM when the game changed it. */
void rr_cps1_save_frame(void);
bool rr_cps1_save_close(void);
bool rr_cps1_save_path(wchar_t *path, size_t capacity);
#endif
