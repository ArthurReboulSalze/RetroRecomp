/* The TC8566AF (uPD765 command set) of the MSX2+ disk interface: see msx_fdc.h. MIT, Retro-Recomp.
 *
 * Commands (low five bits; MT, MF and SK in bits 7-5): 03h SPECIFY, 04h SENSE DRIVE STATUS, 05h WRITE DATA, 06h READ DATA,
 * 07h RECALIBRATE, 08h SENSE INTERRUPT STATUS, 0Ah READ ID, 0Dh FORMAT A TRACK, 0Fh SEEK; any other is invalid (one result
 * byte, 80h). Status: ST0 bits 7-6 the termination (00 normal, 01 abnormal, 10 invalid, 11 ready changed), bit 5 seek end,
 * bit 3 not ready, bit 2 head, bits 1-0 drive; ST1 bit 7 end of cylinder, bit 2 no data, bit 1 not writable, bit 0 missing
 * address mark; ST3 bit 6 write protected, bit 5 ready, bit 4 track 0, bit 3 two sides. A read or a write without terminal
 * count runs to the sector EOT (then the other side with MT); a byte asked past EOT ends it "abnormal, end of cylinder", as
 * the data sheet gives. Terminal count (control register 1, bit 0) ends it normally after the sector in progress, also after
 * the sector EOT (the disk ROMs send it once the last byte is in, while the chip still reads the sector's CRC), with the
 * data sheet's next ID: R + 1, or C + 1 and R = 1 after EOT. The main status register: bit 7
 * request for master, bit 6 direction (1: to the CPU), bit 5 execution phase, bit 4 busy. */
#include "msx_fdc.h"

#include <stdio.h>
#include <string.h>

int msx_fdc_trace;   /* development: every command and result on stderr */

static const uint8_t NEED[32] = {
    [0x03] = 3, [0x04] = 2, [0x05] = 9, [0x06] = 9, [0x07] = 2, [0x08] = 1, [0x0A] = 2, [0x0D] = 6, [0x0F] = 3,
};

void msx_fdc_reset(MsxFdc *f)
{
    f->phase = MSX_FDC_COMMAND;
    f->cmd_len = f->cmd_need = f->result_len = f->result_pos = 0;
    memset(f->int_pending, 0, sizeof f->int_pending);
}

int msx_fdc_insert(MsxFdc *f, int drive, uint8_t *data, uint32_t size, int write_protected)
{
    if (drive < 0 || drive >= MSX_FDC_DRIVES)
        return 0;
    MsxDisk *d = &f->disk[drive];
    memset(d, 0, sizeof *d);
    if (!data)
        return 1;
    if (size != MSX_FDC_TRACKS * MSX_FDC_SPT * MSX_FDC_SECTOR && size != 2u * MSX_FDC_TRACKS * MSX_FDC_SPT * MSX_FDC_SECTOR)
        return 0;
    d->data = data;
    d->size = size;
    d->sides = size == 2u * MSX_FDC_TRACKS * MSX_FDC_SPT * MSX_FDC_SECTOR ? 2 : 1;
    d->write_protected = (uint8_t)(write_protected != 0);
    return 1;
}

static void result7(MsxFdc *f, uint8_t st0, uint8_t st1, uint8_t st2)
{
    if (msx_fdc_trace) fprintf(stderr, "FDC result %02X %02X %02X  C%u H%u R%u N%u\n", st0, st1, st2, f->c, f->h, f->r, f->n);
    uint8_t out[7] = { st0, st1, st2, f->c, f->h, f->r, f->n };
    memcpy(f->result, out, 7);
    f->result_len = 7;
    f->result_pos = 0;
    f->phase = MSX_FDC_RESULT;
}

static void result_bytes(MsxFdc *f, const uint8_t *bytes, uint8_t count)
{
    memcpy(f->result, bytes, count);
    f->result_len = count;
    f->result_pos = 0;
    f->phase = count ? MSX_FDC_RESULT : MSX_FDC_COMMAND;
}

static uint8_t unit(const MsxFdc *f) { return (uint8_t)((f->head << 2) | f->drive); }

/* The byte offset of sector (c, h, r) in the image of the drive, or -1 when the track under the head has no such sector. */
static long sector_at(const MsxFdc *f)
{
    const MsxDisk *d = &f->disk[f->drive];
    if (!d->data || f->n != 2 || f->r < 1 || f->r > MSX_FDC_SPT || f->c != f->pcn[f->drive] || f->h != f->head
        || f->head >= d->sides || f->pcn[f->drive] >= MSX_FDC_TRACKS)
        return -1;
    long track = (long)f->pcn[f->drive] * d->sides + f->head;
    return (track * MSX_FDC_SPT + (f->r - 1)) * MSX_FDC_SECTOR;
}

/* After the last byte of sector r: the next sector, or the end of the transfer at EOT ("abnormal, end of cylinder"). */
static void next_sector(MsxFdc *f)
{
    f->pos = 0;
    if (f->r != f->eot) {
        ++f->r;
        return;
    }
    if (f->mt && f->head == 0 && f->disk[f->drive].sides == 2) {
        f->head = 1;
        f->h = 1;
        f->r = 1;
        return;
    }
    f->at_end = 1;                                                   /* waits for terminal count */
}

/* A byte asked after the sector EOT: the transfer ends "abnormal, end of cylinder" with the next ID. */
static void past_end(MsxFdc *f)
{
    f->at_end = 0;
    ++f->c;
    f->r = 1;
    result7(f, (uint8_t)(0x40 | unit(f)), 0x80, 0x00);
}

static void start_transfer(MsxFdc *f, int write)
{
    f->mt = (uint8_t)(f->cmd[0] >> 7);
    f->drive = f->cmd[1] & 3;
    f->head = (f->cmd[1] >> 2) & 1;
    f->c = f->cmd[2]; f->h = f->cmd[3]; f->r = f->cmd[4]; f->n = f->cmd[5]; f->eot = f->cmd[6];
    f->pos = 0;
    f->at_end = 0;
    if (f->drive >= MSX_FDC_DRIVES || !f->disk[f->drive].data) {
        result7(f, (uint8_t)(0x48 | unit(f)), 0x00, 0x00);          /* abnormal, not ready */
        return;
    }
    if (write && f->disk[f->drive].write_protected) {
        result7(f, (uint8_t)(0x40 | unit(f)), 0x02, 0x00);          /* abnormal, not writable */
        return;
    }
    if (sector_at(f) < 0) {
        result7(f, (uint8_t)(0x40 | unit(f)), 0x04, 0x00);          /* abnormal, no data */
        return;
    }
    f->phase = write ? MSX_FDC_EXEC_WRITE : MSX_FDC_EXEC_READ;
}

static void execute(MsxFdc *f)
{
    uint8_t command = f->cmd[0] & 0x1F;
    if (msx_fdc_trace) {
        fprintf(stderr, "FDC cmd");
        for (int i = 0; i < f->cmd_need; ++i) fprintf(stderr, " %02X", f->cmd[i]);
        fprintf(stderr, " pcn %u\n", f->pcn[f->cmd[1] & 1]);
    }
    switch (command) {
    case 0x03:                                                       /* SPECIFY: timings, nothing to model */
        result_bytes(f, NULL, 0);
        break;
    case 0x04: {                                                     /* SENSE DRIVE STATUS */
        uint8_t d = f->cmd[1] & 3, hd = (f->cmd[1] >> 2) & 1;
        const MsxDisk *disk = d < MSX_FDC_DRIVES ? &f->disk[d] : NULL;
        uint8_t st3 = (uint8_t)((hd << 2) | d);
        if (disk && disk->data) {
            st3 |= 0x20;
            if (disk->write_protected) st3 |= 0x40;
            if (disk->sides == 2) st3 |= 0x08;
        }
        if (d < MSX_FDC_DRIVES && f->pcn[d] == 0) st3 |= 0x10;
        result_bytes(f, &st3, 1);
        break;
    }
    case 0x05: start_transfer(f, 1); break;
    case 0x06: start_transfer(f, 0); break;
    case 0x07: {                                                     /* RECALIBRATE: to track 0, an interrupt to sense */
        uint8_t d = f->cmd[1] & 3;
        if (d < MSX_FDC_DRIVES) f->pcn[d] = 0;
        f->int_pending[d] = 1;
        f->int_st0[d] = (uint8_t)(0x20 | d | (d < MSX_FDC_DRIVES && f->disk[d].data ? 0x00 : 0x48));
        result_bytes(f, NULL, 0);
        break;
    }
    case 0x08: {                                                     /* SENSE INTERRUPT STATUS */
        for (int d = 0; d < 4; ++d)
            if (f->int_pending[d]) {
                f->int_pending[d] = 0;
                uint8_t out[2] = { f->int_st0[d], d < MSX_FDC_DRIVES ? f->pcn[d] : 0 };
                result_bytes(f, out, 2);
                return;
            }
        uint8_t invalid = 0x80;
        result_bytes(f, &invalid, 1);
        break;
    }
    case 0x0A:                                                       /* READ ID: the first sector of the track under the head */
        f->drive = f->cmd[1] & 3;
        f->head = (f->cmd[1] >> 2) & 1;
        if (f->drive >= MSX_FDC_DRIVES || !f->disk[f->drive].data) {
            result7(f, (uint8_t)(0x48 | unit(f)), 0x00, 0x00);
        } else if (f->head >= f->disk[f->drive].sides) {
            result7(f, (uint8_t)(0x40 | unit(f)), 0x01, 0x00);       /* missing address mark */
        } else {
            f->c = f->pcn[f->drive]; f->h = f->head; f->r = 1; f->n = 2;
            result7(f, unit(f), 0x00, 0x00);
        }
        break;
    case 0x0D:                                                       /* FORMAT A TRACK: SC IDs from the CPU, filled with D */
        f->drive = f->cmd[1] & 3;
        f->head = (f->cmd[1] >> 2) & 1;
        f->n = f->cmd[2];
        f->format_left = f->cmd[3];
        f->format_fill = f->cmd[5];
        f->pos = 0;
        if (f->drive >= MSX_FDC_DRIVES || !f->disk[f->drive].data) {
            result7(f, (uint8_t)(0x48 | unit(f)), 0x00, 0x00);
        } else if (f->disk[f->drive].write_protected) {
            result7(f, (uint8_t)(0x40 | unit(f)), 0x02, 0x00);
        } else {
            f->phase = MSX_FDC_EXEC_FORMAT;
        }
        break;
    case 0x0F: {                                                     /* SEEK: to NCN, an interrupt to sense */
        uint8_t d = f->cmd[1] & 3;
        if (d < MSX_FDC_DRIVES) f->pcn[d] = f->cmd[2];
        f->int_pending[d] = 1;
        f->int_st0[d] = (uint8_t)(0x20 | (f->cmd[1] & 7));
        result_bytes(f, NULL, 0);
        break;
    }
    default: {
        uint8_t invalid = 0x80;
        result_bytes(f, &invalid, 1);
        break;
    }
    }
}

static uint8_t main_status(const MsxFdc *f)
{
    switch (f->phase) {
    case MSX_FDC_EXEC_READ: return 0xF0;
    case MSX_FDC_EXEC_WRITE: case MSX_FDC_EXEC_FORMAT: return 0xB0;
    case MSX_FDC_RESULT: return 0xD0;
    default: return f->cmd_len ? 0x90 : 0x80;
    }
}

uint8_t msx_fdc_read(MsxFdc *f, unsigned offset)
{
    switch (offset & 3) {
    case 2:
        return main_status(f);
    case 3:
        if (f->phase == MSX_FDC_RESULT) {
            uint8_t v = f->result[f->result_pos++];
            if (f->result_pos >= f->result_len)
                f->phase = MSX_FDC_COMMAND;
            return v;
        }
        if (f->phase == MSX_FDC_EXEC_READ) {
            if (f->at_end) {
                past_end(f);
                return 0xFF;
            }
            long at = sector_at(f);
            uint8_t v = at < 0 ? 0xFF : f->disk[f->drive].data[at + f->pos];
            if (++f->pos == MSX_FDC_SECTOR)
                next_sector(f);
            return v;
        }
        return 0xFF;
    default:
        return 0xFF;
    }
}

void msx_fdc_write(MsxFdc *f, unsigned offset, uint8_t value)
{
    switch (offset & 3) {
    case 0: {                                                        /* the digital output register */
        uint8_t was = f->dor;
        if (msx_fdc_trace) fprintf(stderr, "FDC DOR %02X\n", value);
        f->dor = value;
        if (!(value & 0x04)) {
            msx_fdc_reset(f);
        } else if (!(was & 0x04)) {                                  /* out of reset: each drive reports "ready changed" */
            for (int d = 0; d < 4; ++d) {
                f->int_pending[d] = 1;
                f->int_st0[d] = (uint8_t)(0xC0 | d);
            }
        }
        break;
    }
    case 1:                                                          /* control register 1: bit 0 terminal count */
        if (msx_fdc_trace) fprintf(stderr, "FDC CR1 %02X phase %u pos %u\n", value, f->phase, f->pos);
        if ((value & 1) && (f->phase == MSX_FDC_EXEC_READ || f->phase == MSX_FDC_EXEC_WRITE)) {
            if (f->at_end || f->pos != 0) {                          /* after EOT, or in the middle of a sector (done) */
                f->pos = 0;
                if (f->r == f->eot) { ++f->c; f->r = 1; } else { ++f->r; }
            }
            f->at_end = 0;
            result7(f, unit(f), 0x00, 0x00);
        }
        break;
    case 3:
        if (f->phase == MSX_FDC_COMMAND) {
            if (!f->cmd_len)
                f->cmd_need = NEED[value & 0x1F] ? NEED[value & 0x1F] : 1;
            f->cmd[f->cmd_len++] = value;
            if (f->cmd_len >= f->cmd_need) {
                f->cmd_len = 0;
                execute(f);
            }
        } else if (f->phase == MSX_FDC_EXEC_WRITE) {
            if (f->at_end) {
                past_end(f);
                break;
            }
            long at = sector_at(f);
            if (at >= 0) {
                f->disk[f->drive].data[at + f->pos] = value;
                f->disk[f->drive].written = 1;
            }
            if (++f->pos == MSX_FDC_SECTOR)
                next_sector(f);
        } else if (f->phase == MSX_FDC_EXEC_FORMAT) {
            f->format_id[f->pos++] = value;
            if (f->pos == 4) {
                f->pos = 0;
                f->c = f->format_id[0]; f->h = f->format_id[1]; f->r = f->format_id[2]; f->n = f->format_id[3];
                long at = sector_at(f);
                if (at >= 0) {
                    memset(f->disk[f->drive].data + at, f->format_fill, MSX_FDC_SECTOR);
                    f->disk[f->drive].written = 1;
                }
                if (--f->format_left == 0)
                    result7(f, unit(f), 0x00, 0x00);
            }
        }
        break;
    default:
        break;
    }
}
