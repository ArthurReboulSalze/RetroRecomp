#ifndef SMSRECOMP_HOST_CONTROL_H
#define SMSRECOMP_HOST_CONTROL_H
#include <stdint.h>
/* Reset unwinds the generated C call stack before restarting the runtime. */
int smsrecomp_take_reset_request(void);
/* Player 2 is sampled alongside player 1, before the next CPU frame. */
uint8_t host_get_pad2(void);
/* Optional live input refresh at a machine's input-port read. The core owns
 * the callback, not SDL; headless/scripted execution leaves it unset. */
void smsrecomp_set_input_refresh(void (*refresh)(void));
void host_refresh_input(void);
/* Simulation time: autofire pauses with the guest and ignores display Hz. */
uint64_t smsrecomp_input_time_us(void);
#endif
