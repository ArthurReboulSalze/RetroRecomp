#ifndef RETRO_SNES_TIMING_H
#define RETRO_SNES_TIMING_H
/* Progressive SNES timing. PAL has 312 lines, unlike the Mega Drive's 313.
 * The audio oscillator is independent of the region's video oscillator. */
#if RR_SN_PAL
#define RR_SN_LINES 312u
#define RR_SN_MASTER_HZ 21281370ull
#define RR_SN_FRAME_SECONDS (425568.0 / 21281370.0)
#else
#define RR_SN_LINES 262u
/* Preserve the qualified NTSC runtime's existing presentation cadence. */
#define RR_SN_FRAME_SECONDS (1.0 / 60.0988139)
#endif
#define RR_SN_FRAME_MASTER (1364ull * RR_SN_LINES)
#define RR_SN_APU_HZ 1025280ull
#endif
