#ifndef RETRO_RECOMP_GAMESTATE_H
#define RETRO_RECOMP_GAMESTATE_H
#include <stdbool.h>
#include <stddef.h>
enum { RR_QUICKSAVE = 1, RR_QUICKLOAD = 2, RR_FRAME_EDGE = 3 };
enum { RR_STATE_OK, RR_STATE_MISSING, RR_STATE_INCOMPATIBLE, RR_STATE_INVALID, RR_STATE_IO_ERROR };
/* Requests are serviced only after a completed banked CPU instruction. */
bool smsrecomp_request_state(int operation);
void smsrecomp_set_state_callback(void (*callback)(int operation, int result));
/* Multiplayer (native/hostkit/hostkit_session.h). The frame ends in the middle of an IN/OUT as often as between instructions, so a
 * snapshot taken or loaded there would cut an instruction in two. In a session the host hands the frame over later: the call
 * returns true when the banked loop will call the callback at the end of the instruction that follows the frame end (the callback
 * answers false to stop the game); false when it cannot (the functions engine, another request pending, a frame already waiting),
 * and the host then runs the frame itself. A snapshot is the whole deterministic state, as it stands in memory, never a file:
 * smsrecomp_snap_bound() is its fixed size (0: none, the functions engine and the reference interpreter), save returns the bytes
 * written (0 on failure), load refuses a wrong size or a buffer it did not write. Valid between two frames, from the callback. */
void smsrecomp_set_frame_edge_callback(bool (*callback)(void));
bool smsrecomp_defer_frame(void);
size_t smsrecomp_snap_bound(void);
size_t smsrecomp_snap_save(void *buffer, size_t capacity);
bool smsrecomp_snap_load(const void *buffer, size_t size);
#endif
