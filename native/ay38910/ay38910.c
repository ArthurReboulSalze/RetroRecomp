/* The AY-3-8910 sound generator (ay38910.h; the tick itself is inline there). MIT, Retro-Recomp. Moved unchanged from
 * native/msx_machine/msx_psg.c. */
#include "ay38910.h"

#include <string.h>

void ay38910_reset(Ay38910 *ay)
{
    memset(ay, 0, sizeof *ay);
    ay->lfsr = 1;
}

void ay38910_shape_written(Ay38910 *ay, uint8_t value)
{
    ay->env_step = 0;
    ay->env_count = 0;
    ay->env_holding = 0;
    ay->env_up = (value & 4) ? 1 : 0;
}
