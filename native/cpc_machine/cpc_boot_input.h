/* The boot key sequence on the CPC's keyboard without a window: the keys of a frame (native/hostkit/adapters/rrhk_boot_keys.h)
 * through the positional table (rrhk_cpc_keys.h) onto the PPI's matrix, as the CPC adapter's input function does in the window
 * while the sequence owns the keyboard. MIT, Retro-Recomp. Used by the headless run (cpc_headless.inc) of the reference runner, the
 * native check and the game, so the three type the start command at the same frames.
 *
 * cpc_boot_inputs(m, seq) sets the inputs of the frame to come from the board's own frame count: the sequence's keys while it
 * owns the keyboard, nothing after it (no key, no joystick: a route's events will come on top). */
#ifndef CPC_BOOT_INPUT_H
#define CPC_BOOT_INPUT_H
#include <string.h>

#include "cpc_machine.h"
#include "rrhk_boot_keys.h"
#include "rrhk_cpc_keys.h"

static void cpc_boot_inputs(CpcMachine *m, const RrhkBootKeys *seq)
{
    static uint8_t state[SDL_NUM_SCANCODES];
    memset(m->ppi.keys, 0, sizeof m->ppi.keys);
    m->ppi.joystick[0] = m->ppi.joystick[1] = 0;
    if (!rrhk_boot_keys_frame(seq, (uint32_t)m->frames, state))
        return;
    for (unsigned i = 0; i < sizeof RRHK_CPC_KEYS / sizeof RRHK_CPC_KEYS[0]; ++i)
        if (state[RRHK_CPC_KEYS[i].scancode]) cpc_ppi_key(&m->ppi, RRHK_CPC_KEYS[i].cpc_key, 1);
}
#endif
