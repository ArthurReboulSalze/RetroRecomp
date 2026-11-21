/* The ZX Spectrum machine (16K, 48K, 128K): memory and paging, the ULA's frame, picture and ports, the beeper, the
 * keyboard and the Kempston joystick. MIT, Retro-Recomp; our own code, written from the machine's documented timings
 * (floooh/chips, zlib, and Clock Signal, MIT, read as references only; no GPL code).
 *
 * What it models (docs/ZX_SPECTRUM.md): the frame of 69,888 T-states (48K: 312 lines of 224) or 70,908 (128K: 311 of 228), the
 * /INT pulse at its start (32 T, 36 T on the 128K), the picture drawn line by line at the end of each line (256 x 192 paper
 * from the screen bank, the border of that line, the attribute flash every 16 frames), port FEh (border, beeper, keyboard
 * half-rows by the high byte of the port, the EAR bit of an issue 3 board), the 128K's port 7FFDh (RAM bank at C000h, screen
 * bank, ROM, lock), the Kempston port 1Fh, the 128K's AY-3-8910 (native/ay38910, the chip shared with the MSX; its clock is the
 * CPU's / 2, a tick every 16 T-states) on ports FFFDh/BFFDh, mixed with the beeper.
 *
 * What it does not model (stated, never hidden): the ULA's memory contention (every instruction takes its plain Z80 time), the
 * floating bus (an unused port reads FFh), the border changes within a line, tapes, the +2A/+3. */
#ifndef RR_ZXS_MACHINE_H
#define RR_ZXS_MACHINE_H

#include <stddef.h>
#include <stdint.h>

#include "ay38910.h"

enum { ZXS_48K = 0, ZXS_128K = 1 };
enum { ZXS_AUDIO_RATE = 44100, ZXS_AUDIO_BUFFER = 8192 };
/* The picture the machine gives: the 256 x 192 paper with a border of 32 columns left and right and 24 lines above and below. */
enum { ZXS_WIDTH = 320, ZXS_HEIGHT = 240, ZXS_BORDER_X = 32, ZXS_BORDER_Y = 24 };
/* The machine image the converter writes (retrorecomp/zxs_build.py, zxs_image): a header, then the eight RAM banks of 16 KiB. */
enum { ZXS_IMAGE_HEADER = 64, ZXS_IMAGE_BYTES = ZXS_IMAGE_HEADER + 8 * 0x4000 };

typedef struct {
    uint16_t af, bc, de, hl, af_, bc_, de_, hl_, ix, iy, sp, pc;
    uint8_t i, r, im, iff1, iff2;
} ZxsCpuStart;

typedef struct {
    int model;                     /* ZXS_48K or ZXS_128K */
    int ram16k;                    /* a 16K: nothing answers at 8000h-FFFFh (reads FFh) */
    const uint8_t *rom;            /* 16 KiB (48K) or 32 KiB (128K: the editor ROM, then the 48K BASIC ROM) */
    uint8_t ram[8][0x4000];
    uint8_t port_7ffd;             /* the 128K's paging register (bit 5 locks it until reset) */
    uint8_t border, out_fe;        /* the border colour and the last value written to port FEh */
    uint8_t keys[8];               /* the half-rows, active low (bits 0-4): FEFE, FDFE, FBFE, F7FE, EFFE, DFFE, BFFE, 7FFE */
    uint8_t kempston;              /* active high: bits 0 right, 1 left, 2 down, 3 up, 4 fire */
    int kempston_present;          /* the Kempston interface answers at port 1Fh */
    uint8_t ay_latch, ay_regs[16]; /* the 128K's AY-3-8910 registers */
    Ay38910 ay;                    /* its counters (native/ay38910) */
    uint64_t ay_next;              /* the cycle of its next tick (every 16 T) */
    int ay_level;                  /* its mixed output since the last tick */

    unsigned t_line, lines, int_len, top_line;   /* T-states a line, lines a frame, the /INT pulse, the first paper line */
    uint32_t t_frame;
    uint64_t cycles;               /* T-states since reset */
    uint64_t frame_start;          /* the cycle the current frame began at */
    uint64_t frames;
    unsigned line;                 /* the next line of the frame to draw */
    uint8_t picture[ZXS_HEIGHT][ZXS_WIDTH];      /* colour indices 0-15 (8-15 bright) */
    uint32_t frame_trace;          /* a running hash of every finished picture */
    int trace_frames;
    void (*frame_hook)(void *user);    /* optional: called at the start of each frame (a line boundary, between instructions) */
    void *hook_user;

    /* The beeper, box-filtered to ZXS_AUDIO_RATE. */
    uint32_t clock_hz;
    uint64_t audio_time;           /* the cycle the sound has reached */
    uint64_t next_sample;          /* in cycles x 65536 */
    int64_t acc;                   /* level x cycles since the last sample */
    uint64_t acc_cycles;
    int16_t out[ZXS_AUDIO_BUFFER];
    unsigned out_count;
    uint64_t dropped;
} ZxsMachine;

/* Reset to the model's power-on map (RAM is left as it is). `rom` stays the caller's. */
void zxs_reset(ZxsMachine *m, int model, int ram16k, const uint8_t *rom);
/* The converter's image (ZXS_IMAGE_BYTES): the model, the RAM, the ports, the frame position; the CPU's registers in `cpu`.
 * Returns 0, or -1 for an image this machine cannot take. */
int zxs_load_image(ZxsMachine *m, const uint8_t *image, size_t size, const uint8_t *rom, ZxsCpuStart *cpu);

uint8_t zxs_read(const ZxsMachine *m, uint16_t address);
void zxs_write(ZxsMachine *m, uint16_t address, uint8_t value);
uint8_t zxs_in(ZxsMachine *m, uint16_t port);
void zxs_out(ZxsMachine *m, uint16_t port, uint8_t value);

/* Run the machine (lines, frames, sound) by `cycles` T-states. */
void zxs_advance(ZxsMachine *m, uint64_t cycles);
/* The cycle of the next line end (the machine's next event). */
uint64_t zxs_next_event(const ZxsMachine *m);
/* The level of /INT now (the pulse at the start of each frame). */
int zxs_irq(const ZxsMachine *m);
/* Which RAM bank shows at C000h, and which ROM at 0000h (0 on the 48K). */
int zxs_bank_c000(const ZxsMachine *m);
int zxs_rom_bank(const ZxsMachine *m);
/* Up to `max` mono 16-bit samples at ZXS_AUDIO_RATE. */
unsigned zxs_audio_take(ZxsMachine *m, int16_t *out, unsigned max);

#endif
