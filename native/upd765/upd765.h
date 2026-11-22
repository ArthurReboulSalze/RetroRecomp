/* The NEC uPD765A floppy disk controller, machine-neutral, reading the sector IDs of a DSK / EXTENDED DSK image (dsk_image.h):
 * the Amstrad CPC's controller first, meant for the Spectrum +3 too. MIT, Retro-Recomp.
 *
 * Written from NEC's uPD765A data sheet (command table, status registers, the end-of-transfer ID table) and the CPC's
 * documented wiring; floooh/chips upd765.h (zlib) and Clock Signal (MIT) read as documentation, nothing of them copied. The
 * MSX2+ has its own TC8566AF (native/msx_machine/msx_fdc.c) on raw images; moving it onto this core is a separate step with
 * its identity proof (STANDARDS rule 7), not made here.
 *
 * What it models. The main status register and the data register; the commands READ DATA, READ DELETED DATA, READ TRACK,
 * WRITE DATA, WRITE DELETED DATA, READ ID, FORMAT A TRACK, RECALIBRATE, SEEK, SENSE INTERRUPT STATUS, SENSE DRIVE STATUS and
 * SPECIFY; the SCAN commands and any other code answer "invalid" and are counted (`unmodelled`). Sectors are found by their
 * ID (C, H, R, N) on the track under the head, from the drive's rotational position (the next ID to pass the head, which
 * READ ID and every sector read move on), so a track's order, its odd IDs, its missing sectors, its deleted marks and the
 * error status an extended image recorded are what a program reads. A weak sector stored as several copies gives the next
 * copy at each read, in turn: the choice is part of the state, so two runs of one input read the same bytes. A sector asked
 * for longer than its stored bytes (an 8 KiB sector on a track that holds about 6 KiB) gives its stored bytes again, as the
 * track comes round; the bytes written past the stored ones are dropped.
 *
 * Every operation completes at once: no rotation time, no step time, no overrun, no drive busy bits. The terminal count line
 * is a capability of the machine (`tc_wired`): the CPC leaves it unconnected, so a transfer ends after the sector EOT with
 * "abnormal termination, end of cylinder" (ST1 bit 7), which AMSDOS takes as the normal end; with the line wired the
 * transfer waits at EOT for the machine to raise it (upd765_terminal_count). */
#ifndef RR_UPD765_H
#define RR_UPD765_H
#include <stdint.h>

#include "dsk_image.h"

enum { UPD765_DRIVES = 4 };

enum {
    UPD765_COMMAND = 0,     /* idle or taking command bytes */
    UPD765_EXEC_READ,       /* bytes to the CPU */
    UPD765_EXEC_WRITE,      /* bytes from the CPU */
    UPD765_EXEC_FORMAT,     /* four ID bytes per sector from the CPU */
    UPD765_RESULT,          /* result bytes to the CPU */
};

typedef struct {
    DskImage *image;        /* NULL: no disk; owned by the machine (its bytes are the disk written back) */
    uint8_t write_protected;
    uint8_t written;        /* set by every byte the program writes on this disk */
    uint8_t pcn;            /* the cylinder under the head */
    uint8_t position;       /* the next sector (index in the track's list) to pass under the head */
} Upd765Drive;

typedef struct {
    Upd765Drive drive[UPD765_DRIVES];
    /* Wiring, set by the machine before use (not part of a quick state): */
    uint8_t tc_wired;       /* the terminal count line is connected (upd765_terminal_count) */
    uint8_t unit_mask;      /* the unit-select bits decoded: 3 for four drives, 1 for two (the CPC decodes US0 only) */
    uint8_t phase;
    uint8_t cmd[9], cmd_len, cmd_need;
    uint8_t result[7], result_len, result_pos;
    uint8_t int_pending[UPD765_DRIVES], int_st0[UPD765_DRIVES];
    /* the transfer in progress */
    uint8_t command;        /* low five bits of the command byte */
    uint8_t unit, head, mt, sk;
    uint8_t c, h, r, n, eot, dtl;
    uint8_t st0, st1, st2;
    uint8_t at_end;         /* tc_wired: the sector EOT is done, waiting for the terminal count */
    uint8_t format_left, format_fill, format_id[4];
    uint16_t sector;        /* index in DskImage.sector of the sector in progress */
    uint8_t copy;           /* copy of a weak sector being read */
    uint8_t track_left;     /* READ TRACK: sectors still to read */
    uint32_t pos, length;   /* byte of the sector in progress, bytes to transfer */
    uint32_t weak_reads;    /* weak-sector reads so far: picks the next copy */
    /* Counted for the reports and the disk requests (media_request.h); not part of a quick state. */
    uint32_t commands;      /* READ and WRITE commands given */
    uint32_t boot_reads;    /* READ DATA of cylinder 0, head 0, the lowest sector R of the track: the disk's identity */
    uint32_t unmodelled;    /* commands answered "invalid" because they are not modelled (SCAN, unknown codes) */
} Upd765;

/* Reset the controller (the drives keep their disk and head). */
void upd765_reset(Upd765 *f);
/* Put a parsed image in a drive (NULL empties it); the drive's head stays where it is. */
void upd765_insert(Upd765 *f, int drive, DskImage *image, int write_protected);
/* The main status register: bit 7 request for master, bit 6 direction (1: to the CPU), bit 5 execution, bit 4 busy. */
uint8_t upd765_status(const Upd765 *f);
uint8_t upd765_read_data(Upd765 *f);
void upd765_write_data(Upd765 *f, uint8_t value);
/* The terminal count line (machines with tc_wired): ends a transfer normally after the sector in progress. */
void upd765_terminal_count(Upd765 *f);
/* SENSE DRIVE STATUS's ST3 for a drive, the head bit 0 (the CPC's drive ready and write-protect lines). */
uint8_t upd765_st3(const Upd765 *f, int drive);
#endif
