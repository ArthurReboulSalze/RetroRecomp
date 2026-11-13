/* The MSX2+ disk interface of the Panasonic machines: a TC8566AF floppy controller (the NEC uPD765 command set) behind four
 * registers in the disk ROM's slot, 7FF8h-7FFBh (and BFF8h-BFFBh): 7FF8h the digital output register, 7FF9h control
 * register 1 (bit 0: terminal count), 7FFAh the main status register, 7FFBh the data register. Written from NEC's uPD765
 * data sheet and the interface's documented addresses (MAME's msx/slot/disk.cpp, BSD-3-Clause, read as documentation;
 * nothing of it copied). MIT, Retro-Recomp.
 *
 * The disks are raw images (.dsk): 512-byte sectors, 9 a track, 80 tracks, one or two sides, sector IDs C = track, H = side,
 * R = 1-9, N = 2. Every operation completes at once: no rotation, no step time, no overrun. */
#ifndef RR_MSX_FDC_H
#define RR_MSX_FDC_H
#include <stdint.h>

enum { MSX_FDC_DRIVES = 2, MSX_FDC_SECTOR = 512, MSX_FDC_SPT = 9, MSX_FDC_TRACKS = 80 };

typedef struct {
    uint8_t *data;          /* the image, NULL: no disk in the drive */
    uint32_t size;          /* 368640 (one side) or 737280 (two sides) */
    uint8_t sides;
    uint8_t write_protected;
    uint8_t written;        /* set by every sector the game writes (the player saves the copy) */
} MsxDisk;

typedef struct {
    MsxDisk disk[MSX_FDC_DRIVES];
    uint8_t dor;            /* bits 0-1 drive, bit 2 not reset, bit 3 DMA, bits 4-7 motors */
    uint8_t phase;          /* MSX_FDC_COMMAND, _EXEC_READ, _EXEC_WRITE, _EXEC_FORMAT, _RESULT */
    uint8_t cmd[9], cmd_len, cmd_need;
    uint8_t result[7], result_len, result_pos;
    uint8_t pcn[MSX_FDC_DRIVES];
    uint8_t int_pending[MSX_FDC_DRIVES + 2], int_st0[MSX_FDC_DRIVES + 2];
    /* the transfer in progress */
    uint8_t drive, head, c, h, r, n, eot, mt;
    uint16_t pos;           /* byte of the current sector (format: byte of the 4-byte ID) */
    uint8_t format_left, format_fill, format_id[4];
    uint8_t at_end;         /* the sector EOT is done: terminal count ends normally, more data ends "end of cylinder" */
} MsxFdc;

enum { MSX_FDC_COMMAND = 0, MSX_FDC_EXEC_READ, MSX_FDC_EXEC_WRITE, MSX_FDC_EXEC_FORMAT, MSX_FDC_RESULT };

void msx_fdc_reset(MsxFdc *f);
/* 0 to 3: the register at 7FF8h + offset. */
uint8_t msx_fdc_read(MsxFdc *f, unsigned offset);
void msx_fdc_write(MsxFdc *f, unsigned offset, uint8_t value);
/* Put an image in a drive (NULL: empty it). False when the size is not a disk this controller reads. */
int msx_fdc_insert(MsxFdc *f, int drive, uint8_t *data, uint32_t size, int write_protected);
#endif
