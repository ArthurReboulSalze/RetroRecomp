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
/* After every frame: asks for the EEPROM to be written when the game changed it (a worker writes it once it has been stable for a
 * second). In a multiplayer session the host plays on its own file as alone and writes it (hostkit.h side_effects: not in a silent frame);
 * a guest's frames ask for no file at all, and the host's EEPROM image is put in its memory before the match's boot digest
 * (cps1_host.h rr_cps1_session_save_put). */
void rr_cps1_save_frame(void);
/* What a frame may do outside the machine (hostkit.h side_effects): off, the change flag is still taken but no file is asked for. */
void rr_cps1_save_side_effects(bool allowed);
bool rr_cps1_save_close(void);
bool rr_cps1_save_path(wchar_t *path, size_t capacity);
#endif
