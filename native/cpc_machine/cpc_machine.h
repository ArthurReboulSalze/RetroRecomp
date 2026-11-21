/* The Amstrad CPC 6128 board: its 128 KiB of RAM and the player's ROMs behind the Gate Array's map, the CRTC, the PPI and the
 * keyboard, the uPD765 with its two drives, and the time that drives them, as the Z80 sees them through its bus. MIT, Retro-Recomp.
 *
 * The bus is the Z80's (cpc_read / cpc_write, cpc_in / cpc_out with the full 16-bit port: the CPC decodes its devices from the
 * high byte, see cpc_bus.h). The machine advances in T-states (cpc_advance): every 4 T-states, one microsecond, the CRTC and the
 * Gate Array take one character; the interrupt is a level (cpc_irq) that the Z80's acknowledge drops (cpc_acknowledge). A frame
 * is complete when the VSYNC starts (`frame_ready`). The AY-3-8912 is the shared chip (native/ay38910): the board keeps its sixteen
 * registers and its address latch, which the PPI drives (port A the data, port C bits 7-6 BDIR/BC1); its I/O port A (R14) reads
 * the keyboard row the PPI selects. The registers keep the bits the chip has (R1, R3, R5 and R13 four, R6 and R8-R10 five); a
 * latch byte with any of its high four bits set selects nothing (the AY-3-8912's address lines A4-A7 are tied low). Its clock
 * is 1 MHz: one tick of 8 chip clocks every CPC_AY_TICK T-states.
 *
 * The region map the banked Z80 chain reads (cpc_glue.inc) follows `generation`, raised each time what the Z80 sees in a
 * window changes: the Gate Array's ROM enables or RAM configuration, or the upper ROM number. */
#ifndef RR_CPC_MACHINE_H
#define RR_CPC_MACHINE_H
#include <stdint.h>

#include "cpc_bus.h"
#include "cpc_crtc.h"
#include "cpc_gate_array.h"
#include "cpc_ppi.h"
#include "upd765.h"
#include "ay38910.h"

enum { CPC_RAM_BYTES = 0x20000, CPC_ROM_BYTES = 0x4000, CPC_DRIVES = 2, CPC_AMSDOS_SLOT = 7, CPC_AY_TICK = 32 };

typedef struct {
    /* the machine as it was built (not part of a quick state) */
    const uint8_t *os, *basic, *amsdos;      /* 16 KiB each: the player's system ROM halves and AMSDOS (NULL: no ROM, reads FFh) */
    uint32_t *picture;                       /* CPC_SCREEN_WIDTH x CPC_SCREEN_HEIGHT, or NULL */
    CpcPsgBus psg;                           /* the PPI's bus to the AY (set by cpc_reset) */
    DskImage disk[CPC_DRIVES];
    /* state */
    uint8_t ram[CPC_RAM_BYTES];
    CpcCrtc crtc;
    CpcGateArray ga;
    CpcPpi ppi;
    Upd765 fdc;
    Ay38910 ay;
    uint8_t ay_reg[16];
    uint8_t ay_latch;                        /* the register the AY's bus selects; 16: none */
    uint8_t upper_rom;                       /* the number written at DFxxh */
    uint8_t motor;                           /* the drives' motor (FA7Eh bit 0) */
    uint8_t phase;                           /* T-states into the current microsecond, 0-3 */
    uint8_t frame_ready;                     /* a VSYNC started since the flag was cleared */
    uint64_t cycles;                         /* T-states since the reset */
    uint64_t frames;
    uint32_t generation;                     /* raised when the memory map changes */
    CpcMap map;                              /* the current map (cpc_memory_map of the Gate Array and the upper ROM) */
} CpcMachine;

/* Reset the board (power on): RAM cleared, the Gate Array, the CRTC (its type), the PPI and the controller reset, the ROMs and
 * the disks kept. */
void cpc_reset(CpcMachine *m, uint8_t crtc_type);
/* Put a DSK or EXTENDED DSK image in a drive (NULL empties it); 0 or the reader's DSK_ERR_* reason. */
int cpc_insert_disk(CpcMachine *m, int drive, uint8_t *bytes, uint32_t size, int write_protected);
uint8_t cpc_read(const CpcMachine *m, uint16_t address);
void cpc_write(CpcMachine *m, uint16_t address, uint8_t value);
uint8_t cpc_in(CpcMachine *m, uint16_t port);
void cpc_out(CpcMachine *m, uint16_t port, uint8_t value);
/* Run the video and the interrupt for `tstates` T-states. */
void cpc_advance(CpcMachine *m, uint64_t tstates);
/* The cycle (T-states since the reset) of the next microsecond boundary, where the Gate Array may raise the interrupt or start a
 * frame: the loop may run to it without missing one. */
uint64_t cpc_next_event(const CpcMachine *m);
int cpc_irq(const CpcMachine *m);
void cpc_acknowledge(CpcMachine *m);
#endif
