/* The Z80's registers in a quick state or a snapshot of a machine on the banked Z80 chain (native/z80_chain_glue.inc). MIT,
 * Retro-Recomp. Included by the machine's state code after the CPU's type (Z80State, sms_runtime.h) is known.
 *
 * rr_z80_cpu_state(io, s) writes, checks or applies the CPU of `s` (io->mode, state_io.h), field after field in the order and
 * widths the Master System's state (gamestate.inc) and the MSX's (msx_machine/msx_state_file.inc) use, so that a machine moving
 * onto it keeps its state bytes: the main and the alternate registers (1 byte each), PC SP IX IY WZ (2), I R (1), IFF1 IFF2 (0-1),
 * IM (0-2), HALT (0-1), Q (1), P and the EI block (0-1), then the loop's cycle (8 bytes, at most 2^60). 43 bytes.
 *
 * Every field is read within its bounds: a value outside them (an IM 3, a HALT of 2, a cycle above 2^60) refuses the whole state
 * (io->ok false), even when the file's CRC is right. In the check pass the decoded values land in `s`, so `s` is a candidate:
 * the caller passes a copy of the live CPU and applies it only once every check of its state has passed. */
#ifndef RETRO_RECOMP_Z80_CHAIN_STATE_INC
#define RETRO_RECOMP_Z80_CHAIN_STATE_INC
#include "state_io.h"

#define RR_Z80_CPU_STATE_BYTES 43u

static void rr_z80_cpu_state(RetroStateIO *io, Z80State *s)
{
    Z80State v = *s;
    RR_FIELD(v, a, 1, 255); RR_FIELD(v, f, 1, 255); RR_FIELD(v, b, 1, 255); RR_FIELD(v, c, 1, 255);
    RR_FIELD(v, d, 1, 255); RR_FIELD(v, e, 1, 255); RR_FIELD(v, h, 1, 255); RR_FIELD(v, l, 1, 255);
    RR_FIELD(v, a_, 1, 255); RR_FIELD(v, f_, 1, 255); RR_FIELD(v, b_, 1, 255); RR_FIELD(v, c_, 1, 255);
    RR_FIELD(v, d_, 1, 255); RR_FIELD(v, e_, 1, 255); RR_FIELD(v, h_, 1, 255); RR_FIELD(v, l_, 1, 255);
    RR_FIELD(v, pc, 2, 65535); RR_FIELD(v, sp, 2, 65535); RR_FIELD(v, ix, 2, 65535);
    RR_FIELD(v, iy, 2, 65535); RR_FIELD(v, wz, 2, 65535); RR_FIELD(v, i, 1, 255); RR_FIELD(v, r, 1, 255);
    RR_FIELD(v, iff1, 1, 1); RR_FIELD(v, iff2, 1, 1); RR_FIELD(v, im, 1, 2); RR_FIELD(v, halted, 1, 1);
    RR_FIELD(v, q, 1, 255); RR_FIELD(v, p, 1, 1); RR_FIELD(v, ei_block, 1, 1); RR_FIELD(v, cyc, 8, (1ULL << 60));
    *s = v;
}
#endif
