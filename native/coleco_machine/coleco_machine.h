/* The ColecoVision: a Z80, a TMS9928A, an SN76489A, 1 KiB of RAM, the console's 8 KiB BIOS, a cartridge of up to 32 KiB and two
 * controllers. MIT, Retro-Recomp.
 *
 * The machine is the bus around the Z80 and the clock of its chips; the picture is native/tms9918, the sound native/sn76489. A CPU (the
 * reference interpreter, or the native bodies of the banked chain through coleco_glue.inc) calls cv_read / cv_write / cv_in / cv_out
 * and advances time with cv_advance. Written from the ColecoVision's documentation; MAME is the reference it is checked against in
 * development, run as a separate program (nothing of it is here). No real console was measured, so nothing about the hardware is claimed.
 *
 * Memory: the BIOS at 0000h-1FFFh (the player's own file, passed to cv_init); the expansion port at 2000h-5FFFh (nothing there: FFh); the 1 KiB of
 * RAM at 6000h, mirrored through 7FFFh; the cartridge at 8000h-FFFFh, mirrored every `rom_size` bytes (a multiple of 8 KiB, the image padded
 * with FFh as the chain's region map pads it). Ports (A7 A6 A5): 80h-9Fh write selects the controllers' keypad mode, C0h-DFh their joystick
 * mode; A0h-BFh the TMS9928A (A0 low: data, high: control and status); E0h-FFh write the SN76489A, read the controllers (A1 low: the first,
 * high: the second). The VDP's interrupt is the Z80's /NMI: an edge, taken when the frame flag rises with the interrupt enabled, or when it is
 * enabled with the flag already up (cv_nmi_edge). /INT is not wired.
 *
 * The controllers: in joystick mode a port reads the stick (bits 0-3: up, right, down, left) and the left fire button (bit 6); in keypad
 * mode the key's code in bits 0-3 and the right fire button (bit 6); the other bits read 1; every line is active low. The pad word of a
 * player (CV_PAD_*) is the buttons HELD: the stick, the two fire buttons, and the keypad's four lines (a key is the code of the lines
 * it pulls: two keys held merge, as on the real keypad). */
#ifndef COLECO_MACHINE_H
#define COLECO_MACHINE_H

#include <stdint.h>
#include <stdio.h>

#include "sn76489.h"
#include "tms9918.h"

enum { CV_CYCLES_PER_LINE = 228, CV_LINES_NTSC = 262, CV_LINES_PAL = 313, CV_RAM_SIZE = 1024, CV_BIOS_SIZE = 8192, CV_REGION_BITS = 13,
       CV_REGIONS = 8, CV_AUDIO_BUFFER = SN_AUDIO_BUFFER, CV_AUDIO_RATE = SN_AUDIO_RATE, CV_CPU_CLOCK = SN_CPU_CLOCK };

/* Pad bits, in `pad[port]` as the buttons HELD (a set bit is a held button or a pulled keypad line); the ports read them active low.
 * Bits 0-5: the stick and the two fire buttons; bits 6-9: the keypad's lines; bit 10 is reserved (the console has no Pause button: its
 * reset is the host's); bit 11 is the host's own flag, « the on-screen keypad is open » (the machine masks the stick and the fire
 * buttons while it is set: the host-kit pop-up uses the D-pad and A). */
enum { CV_PAD_UP = 1, CV_PAD_DOWN = 2, CV_PAD_LEFT = 4, CV_PAD_RIGHT = 8, CV_PAD_B1 = 16, CV_PAD_B2 = 32,
       CV_PAD_KEY_SHIFT = 6, CV_PAD_KEY_MASK = 0x0F << 6, CV_PAD_KEYPAD_OPEN = 1 << 11, CV_PAD_MASK = 0x0FFF & ~(1 << 10) };

/* The keypad's keys as the lines they pull (the 4 bits of CV_PAD_KEY_MASK, shifted down): the code the real keypad gives, active high here. */
enum { CV_KEY_0 = 0x05, CV_KEY_1 = 0x02, CV_KEY_2 = 0x08, CV_KEY_3 = 0x03, CV_KEY_4 = 0x0D, CV_KEY_5 = 0x0C, CV_KEY_6 = 0x01,
       CV_KEY_7 = 0x0A, CV_KEY_8 = 0x0E, CV_KEY_9 = 0x04, CV_KEY_HASH = 0x06, CV_KEY_STAR = 0x09 };

typedef struct {
    const uint8_t *bios;         /* the 8 KiB BIOS */
    const uint8_t *rom;          /* the cartridge, padded to `rom_size` */
    uint32_t rom_size;           /* a multiple of 8 KiB, 8 KiB to 32 KiB (0: no cartridge) */
    uint8_t ram[CV_RAM_SIZE];
    Tms9918 vdp;
    Sn76489 psg;
    uint16_t pad[2];             /* the buttons held (CV_PAD_*) */
    uint8_t keypad_mode;         /* 1: the controllers read the keypad and the right fire button; 0: the stick and the left fire button */
    uint8_t nmi_level;           /* the VDP's interrupt line as the CPU last saw it (an edge is a rise from 0) */
    uint64_t cycles;             /* the CPU cycle the chips are brought to */
    uint64_t next_line;
    unsigned lines_per_frame, line;
    uint64_t frames;
    void (*line_hook)(void);     /* optional: called after each line the machine runs */
    uint8_t trace_frames;        /* comparisons: fold every frame's picture and VDP state into frame_trace */
    uint32_t frame_trace;
    uint32_t generation;         /* the region layout never changes; kept for the chain's region map */
} CvMachine;

void cv_init(CvMachine *m, const uint8_t *bios, const uint8_t *rom, uint32_t rom_size, unsigned lines_per_frame);
uint8_t cv_read(CvMachine *m, uint16_t address);
uint8_t cv_peek(const CvMachine *m, uint16_t address);
void cv_write(CvMachine *m, uint16_t address, uint8_t value);
uint8_t cv_in(CvMachine *m, uint8_t port);
void cv_out(CvMachine *m, uint8_t port, uint8_t value);
int cv_irq(const CvMachine *m);
void cv_advance(CvMachine *m, uint64_t cycles);
static inline uint64_t cv_next_event(const CvMachine *m) { return m->next_line; }

/* /NMI: the VDP's interrupt line (the frame flag with the interrupt enabled). cv_nmi_edge returns 1 once per rise since the last call (the
 * chain asks after every instruction, once the machine has caught up with it). */
int cv_nmi_edge(CvMachine *m);

/* Sound: mono 16-bit samples at CV_AUDIO_RATE. Takes up to `max` samples. */
unsigned cv_audio_take(CvMachine *m, int16_t *out, unsigned max);

/* Hashes and dumps for the checks. */
uint32_t cv_vram_hash(const CvMachine *m);
uint32_t cv_ram_hash(const CvMachine *m);
uint32_t cv_frame_hash(const CvMachine *m);
int cv_dump_frame(const CvMachine *m, FILE *out);
void cv_print_state(const CvMachine *m, FILE *out);

#endif
