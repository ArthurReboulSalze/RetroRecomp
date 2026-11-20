/* PC Engine: the in-process snapshot of the machine and its digest, for the multiplayer rollback tier and the host's F8 / F9 for everyone
 * (native/hostkit/hostkit.h, "Multiplayer"). Memory only: never a file, never sent. A save allocates nothing once the first has run; a load recreates the engine's small audio presentation state (a few KB).
 * What it holds, and why it is not the engine's own checkpoint, is in docs/PC_ENGINE.md ("Multiplayer").
 * Original RetroRecomp code: MIT. The engine keeps its own MIT terms (licenses/pcenginerecomp.md). */
#ifndef RR_PCE_SNAPSHOT_H
#define RR_PCE_SNAPSHOT_H
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* The most bytes pce_snapshot_save can write for this machine (0 before pce_machine_init). */
size_t pce_snapshot_bound(void);
/* The whole state that decides future frames, valid after any frame: the HuC6280, the card's RAM banks (work RAM, the Backup RAM bank), the VDC with its VRAM,
 * sprite table, raster, video latches and both frame buffers, the VCE, the PSG and the rest of the audio side, the timer and interrupts, the pads, the
 * SF2 bank latch, the step and generation counters and the bridge's own counters. Not the ROM, not a pointer, nothing of the host. Returns the bytes
 * written, 0 when `capacity` is too small or the machine holds something the snapshot does not (a CD or an Arcade Card). A picture buffer larger than
 * the bridge's picture limit never fails a save: its size is kept and its pixels up to the limit (output, not state). */
size_t pce_snapshot_save(void *buffer, size_t capacity);
/* 1 when the bytes are a snapshot of this machine (size, magic, version and checksum checked before anything changes); 0 otherwise, the machine untouched. */
int pce_snapshot_load(const void *buffer, size_t size);
/* A 64-bit hash of the state that decides future frames, as named fields in a fixed little-endian order, after the last frame. It leaves out what is
 * not guest state (the picture, the audio samples, the generation and native / interpreted step counters), so builds that differ only in the
 * native code agree. 0 before pce_machine_init. */
uint64_t pce_snapshot_digest(void);

#ifdef __cplusplus
}
#endif
#endif
