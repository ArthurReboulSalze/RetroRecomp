/* The V9938 command engine (MSX2). MIT, Retro-Recomp.
 *
 * Stage 6: the hooks only. R#32-R#46 are latched (and mirrored in MsxV9938.reg), a write to R#46 is counted (it starts
 * a command on the chip) and the engine reports itself idle: S#2's TR, BD and CE read 0, S#7 gives the last colour
 * register, S#8/S#9 the last border X. The machine already calls msx_v9938_cmd_sync before every VRAM access of the
 * CPU, before each line is drawn and before S#2 and S#7-S#9 are read, so stage 7 fills the engine here and nothing
 * else moves. */
#include "msx_machine.h"

#include <string.h>

void msx_v9938_cmd_reset(MsxMachine *m)
{
    memset(&m->v9938->cmd, 0, sizeof m->v9938->cmd);
}

void msx_v9938_cmd_write(MsxMachine *m, int index, uint8_t value)
{
    MsxV9938 *v = m->v9938;
    if (index < 0 || index > 14)
        return;
    v->cmd.reg[index] = value;
    v->reg[32 + index] = value;
    if (index == 14)
        ++v->cmd.writes;
}

uint8_t msx_v9938_cmd_status(MsxMachine *m)
{
    (void)m;
    return 0;                                  /* TR, BD, CE: the engine is idle */
}

uint8_t msx_v9938_cmd_read_colour(MsxMachine *m)
{
    return m->v9938->cmd.colour;
}

uint16_t msx_v9938_cmd_border_x(MsxMachine *m, int clear)
{
    (void)clear;
    return m->v9938->cmd.border_x;
}

void msx_v9938_cmd_sync(MsxMachine *m, uint64_t cycle)
{
    (void)m;
    (void)cycle;
}
