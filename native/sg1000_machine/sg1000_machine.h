/* The Sega SG-1000: a Z80, a TMS9918A, an SN76489A, 1 KiB of RAM, a cartridge of up to 48 KiB and two pads. MIT, Retro-Recomp.
 *
 * The machine is the bus around the Z80 and the clock of its chips; the picture is native/tms9918, the sound native/sn76489. A CPU (the
 * reference interpreter, or the native bodies of the banked chain through sg1000_glue.inc) calls sg_read / sg_write / sg_in / sg_out
 * and advances time with sg_advance. Written from the SG-1000's documentation; MAME is the reference it is checked against in
 * development, run as a separate program (nothing of it is here). No real console was measured, so nothing about the hardware is claimed.
 *
 * Memory: the cartridge at 0000h-BFFFh, mirrored every `rom_size` bytes (a multiple of 8 KiB, the image padded with FFh as the chain's
 * region map pads it); RAM 1 KiB at C000h, mirrored through FFFFh. Ports (A7 A6, A0): 40h-7Fh write the SN76489A; 80h-BFh the TMS9918A
 * (A0 low: data, high: control and status); C0h-FFh the pads (A0 low: DCh, high: DDh). The VDP's interrupt is on /INT; the Pause button
 * is /NMI: it is bit 6 of each pad's word (SG_PAD_PAUSE), and the edge (the press, from the word the machine last saw, kept in its state)
 * raises it once (sg_pad_word, sg_pause). */
#ifndef SG1000_MACHINE_H
#define SG1000_MACHINE_H

#include <stdint.h>
#include <stdio.h>

#include "sn76489.h"
#include "tms9918.h"

enum { SG_CYCLES_PER_LINE = 228, SG_LINES_NTSC = 262, SG_LINES_PAL = 313, SG_RAM_SIZE = 1024, SG_REGION_BITS = 13, SG_REGIONS = 8,
       SG_AUDIO_BUFFER = SN_AUDIO_BUFFER, SG_AUDIO_RATE = SN_AUDIO_RATE, SG_CPU_CLOCK = SN_CPU_CLOCK };

/* Pad bits, in `pad[port]` as the buttons HELD (a set bit is a held button); the ports read them active low. */
enum { SG_PAD_UP = 1, SG_PAD_DOWN = 2, SG_PAD_LEFT = 4, SG_PAD_RIGHT = 8, SG_PAD_B1 = 16, SG_PAD_B2 = 32, SG_PAD_PAUSE = 64, SG_PAD_MASK = 0x7F };

typedef struct {
    const uint8_t *rom;          /* the cartridge, padded to `rom_size` */
    uint32_t rom_size;           /* a multiple of 8 KiB, 8 KiB to 48 KiB */
    uint8_t ram[SG_RAM_SIZE];
    Tms9918 vdp;
    Sn76489 psg;
    uint8_t pad[2];              /* the buttons held (SG_PAD_*) */
    uint8_t nmi_edge;            /* the Pause button was pressed since the CPU last asked */
    uint8_t pause_held;          /* bit per seat: its word had Pause at the last sg_pad_word (the press edge comes from it) */
    uint64_t cycles;             /* the CPU cycle the chips are brought to */
    uint64_t next_line;
    unsigned lines_per_frame, line;
    uint64_t frames;
    void (*line_hook)(void);     /* optional: called after each line the machine runs */
    uint8_t trace_frames;        /* comparisons: fold every frame's picture and VDP state into frame_trace */
    uint32_t frame_trace;
    uint32_t generation;         /* the region layout never changes; kept for the chain's region map */
} SgMachine;

void sg_init(SgMachine *m, const uint8_t *rom, uint32_t rom_size, unsigned lines_per_frame);
uint8_t sg_read(SgMachine *m, uint16_t address);
uint8_t sg_peek(const SgMachine *m, uint16_t address);
void sg_write(SgMachine *m, uint16_t address, uint8_t value);
uint8_t sg_in(SgMachine *m, uint8_t port);
void sg_out(SgMachine *m, uint8_t port, uint8_t value);
int sg_irq(const SgMachine *m);
void sg_advance(SgMachine *m, uint64_t cycles);
static inline uint64_t sg_next_event(const SgMachine *m) { return m->next_line; }

/* The Pause button: raises /NMI once; sg_nmi_edge takes it (the chain asks after every instruction). */
void sg_pause(SgMachine *m);
/* One seat's word for the frame to come (SG_PAD_*): its pad, and a press of Pause (bit 6 set where it was not) is one /NMI. */
void sg_pad_word(SgMachine *m, int seat, uint16_t word);
int sg_nmi_edge(SgMachine *m);

/* Sound: mono 16-bit samples at SG_AUDIO_RATE. Takes up to `max` samples. */
unsigned sg_audio_take(SgMachine *m, int16_t *out, unsigned max);

/* Hashes and dumps for the checks. */
uint32_t sg_vram_hash(const SgMachine *m);
uint32_t sg_ram_hash(const SgMachine *m);
uint32_t sg_frame_hash(const SgMachine *m);
int sg_dump_frame(const SgMachine *m, FILE *out);
void sg_print_state(const SgMachine *m, FILE *out);

#endif
