#ifndef RETRO_RECOMP_GAMESTATE_H
#define RETRO_RECOMP_GAMESTATE_H
#include <stdbool.h>
enum { RR_QUICKSAVE = 1, RR_QUICKLOAD = 2 };
enum { RR_STATE_OK, RR_STATE_MISSING, RR_STATE_INCOMPATIBLE, RR_STATE_INVALID, RR_STATE_IO_ERROR };
/* Requests are serviced only after a completed banked CPU instruction. */
bool smsrecomp_request_state(int operation);
void smsrecomp_set_state_callback(void (*callback)(int operation, int result));
#endif
