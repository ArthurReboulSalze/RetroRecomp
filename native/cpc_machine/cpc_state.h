/* The Amstrad CPC board's state, field by field (state_io.h: fixed-width little-endian fields, never a C layout or a host
 * address), for the quick states, the rollback snapshots of a multiplayer session and their digest. MIT, Retro-Recomp.
 *
 * What is written: the 128 KiB of RAM, the CRTC, the Gate Array, the PPI with the keyboard and joystick lines, the uPD765 and its
 * drives' heads and positions, the AY's registers, latch and counters, the sound's stream (its time and the sample being built:
 * the samples already made belong to the host and are not part of it), the upper ROM, the motor, the time in T-states and the
 * emulated frame count (`frames`: the boot key sequence's clock, so a snapshot or a quick state carries where the sequence is).
 * What is not: the ROMs, the disk images' bytes (the player's snapshot adds the bytes of a disk the game wrote), the picture,
 * the region map (rebuilt: its generation moves on a load).
 *
 * A state is decoded twice, as state_io.h asks: checked whole on the live machine first (RR_STATE_CHECK changes nothing), then
 * applied. A state of another version, of another size, with a field out of its range, or made with another disk in a drive
 * (inserted or not) is refused and the machine is left as it was. The digest is the FNV-64 of the state's bytes: two seats whose
 * boards differ in any field, the frame count included, give two digests. */
#ifndef RR_CPC_STATE_H
#define RR_CPC_STATE_H
#include <stddef.h>
#include <stdint.h>

#include "cpc_machine.h"
#include "state_io.h"

enum { CPC_STATE_VERSION = 1 };

/* Read or write the board through `io` (RR_STATE_WRITE, RR_STATE_CHECK or RR_STATE_APPLY); 0 when io->ok stayed true. */
int cpc_machine_state(CpcMachine *m, RetroStateIO *io);
/* The bytes a state takes. */
size_t cpc_state_size(const CpcMachine *m);
/* Write the state into `out` (capacity bytes); its size, 0 when it does not fit. */
size_t cpc_state_save(const CpcMachine *m, uint8_t *out, size_t capacity);
/* Load a state written by cpc_state_save: 1, or 0 with the machine unchanged. */
int cpc_state_load(CpcMachine *m, const uint8_t *in, size_t size);
/* FNV-64 of the state's bytes (0 when it cannot be written). */
uint64_t cpc_state_digest(const CpcMachine *m);
#endif
