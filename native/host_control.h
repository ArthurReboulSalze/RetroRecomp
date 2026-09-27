#ifndef SMSRECOMP_HOST_CONTROL_H
#define SMSRECOMP_HOST_CONTROL_H
#include <stdint.h>
/* Reset unwinds the generated C call stack before restarting the runtime. */
int smsrecomp_take_reset_request(void);
/* Player 2 is sampled alongside player 1, before the next CPU frame. */
uint8_t host_get_pad2(void);
#endif
