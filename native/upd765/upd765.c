/* The NEC uPD765A: see upd765.h. MIT, Retro-Recomp.
 *
 * Command byte: MT bit 7 (multi-track), MF bit 6 (MFM, not checked), SK bit 5 (skip deleted data), the code in bits 4-0.
 * ST0: bits 7-6 the termination (00 normal, 01 abnormal, 10 invalid), bit 5 seek end, bit 4 equipment check, bit 3 not
 * ready, bit 2 head, bits 1-0 unit. ST1: bit 7 end of cylinder, bit 5 data error (CRC), bit 4 overrun, bit 2 no data, bit 1
 * not writable, bit 0 missing address mark. ST2: bit 6 control mark (deleted data), bit 5 data error in the data field,
 * bit 4 wrong cylinder, bit 1 bad cylinder, bit 0 missing data address mark. ST3: bit 6 write protected, bit 5 ready,
 * bit 4 track 0, bit 3 two sides, bit 2 head, bits 1-0 unit. */
#include "upd765.h"

#include <string.h>

enum {
    CMD_READ_TRACK = 0x02, CMD_SPECIFY = 0x03, CMD_SENSE_DRIVE = 0x04, CMD_WRITE = 0x05, CMD_READ = 0x06,
    CMD_RECALIBRATE = 0x07, CMD_SENSE_INT = 0x08, CMD_WRITE_DELETED = 0x09, CMD_READ_ID = 0x0A,
    CMD_READ_DELETED = 0x0C, CMD_FORMAT = 0x0D, CMD_SEEK = 0x0F,
};

static const uint8_t NEED[32] = {
    [0x02] = 9, [0x03] = 3, [0x04] = 2, [0x05] = 9, [0x06] = 9, [0x07] = 2, [0x08] = 1, [0x09] = 9, [0x0A] = 2,
    [0x0C] = 9, [0x0D] = 6, [0x0F] = 3, [0x11] = 9, [0x19] = 9, [0x1D] = 9,
};

void upd765_reset(Upd765 *f)
{
    f->phase = UPD765_COMMAND;
    f->cmd_len = f->cmd_need = f->result_len = f->result_pos = 0;
    f->at_end = 0;
    memset(f->int_pending, 0, sizeof f->int_pending);
}

void upd765_insert(Upd765 *f, int drive, DskImage *image, int write_protected)
{
    if (drive < 0 || drive >= UPD765_DRIVES)
        return;
    Upd765Drive *d = &f->drive[drive];
    d->image = image && image->bytes ? image : NULL;
    d->write_protected = (uint8_t)(write_protected != 0);
    d->written = 0;
    d->position = 0;
}

static Upd765Drive *unit_drive(Upd765 *f, uint8_t unit) { return &f->drive[unit & f->unit_mask & 3]; }
static const Upd765Drive *unit_drive_c(const Upd765 *f, uint8_t unit) { return &f->drive[unit & f->unit_mask & 3]; }
static uint8_t us_hd(const Upd765 *f) { return (uint8_t)((f->head << 2) | f->unit); }

static void result7(Upd765 *f)
{
    uint8_t out[7] = { f->st0, f->st1, f->st2, f->c, f->h, f->r, f->n };
    memcpy(f->result, out, 7);
    f->result_len = 7;
    f->result_pos = 0;
    f->at_end = 0;
    f->phase = UPD765_RESULT;
}

static void result_bytes(Upd765 *f, const uint8_t *bytes, uint8_t count)
{
    if (count)
        memcpy(f->result, bytes, count);
    f->result_len = count;
    f->result_pos = 0;
    f->phase = count ? UPD765_RESULT : UPD765_COMMAND;
}

static void abnormal(Upd765 *f, uint8_t st0_bits, uint8_t st1, uint8_t st2)
{
    f->st0 = (uint8_t)(0x40 | st0_bits | us_hd(f));
    f->st1 |= st1;
    f->st2 |= st2;
    result7(f);
}

static const DskTrack *head_track(const Upd765 *f)
{
    const Upd765Drive *d = unit_drive_c(f, f->unit);
    return d->image ? dsk_track(d->image, d->pcn, f->head) : NULL;
}

static const DskSector *sector_of(const Upd765 *f, unsigned index)
{
    return &unit_drive_c(f, f->unit)->image->sector[index];
}

/* The sector with the ID (c, h, r, n) on the track under the head, searched from the drive's rotational position: its index
 * in the image's table, or -1 with ST1/ST2 set as the chip sets them (missing address mark on a blank track, else no data,
 * with wrong / bad cylinder when an ID on the track has another C). */
static int find_sector(Upd765 *f)
{
    Upd765Drive *d = unit_drive(f, f->unit);
    const DskTrack *t = head_track(f);
    if (!t || !t->count) {
        f->st1 |= 0x01;
        return -1;
    }
    for (unsigned k = 0; k < t->count; ++k) {
        unsigned i = (d->position + k) % t->count;
        const DskSector *s = sector_of(f, t->first + i);
        if (s->c == f->c && s->h == f->h && s->r == f->r && s->n == f->n) {
            d->position = (uint8_t)((i + 1) % t->count);
            return t->first + i;
        }
    }
    f->st1 |= 0x04;
    for (unsigned i = 0; i < t->count; ++i) {
        const DskSector *s = sector_of(f, t->first + i);
        if (s->c != f->c) {
            f->st2 |= 0x10;
            if (s->c == 0xFF)
                f->st2 |= 0x02;
        }
    }
    return -1;
}

static uint32_t transfer_length(const Upd765 *f)
{
    if (f->n == 0)
        return f->dtl ? f->dtl : 128;
    return dsk_sector_bytes(f->n);
}

static int is_read(uint8_t command) { return command == CMD_READ || command == CMD_READ_DELETED || command == CMD_READ_TRACK; }

/* Start on sector `index` (found for its ID). 1: bytes to move; 0: the command ended (result phase) or moved on (SK). */
static int begin_sector(Upd765 *f, int index);

/* "Abnormal termination, end of cylinder", with the data sheet's next ID. */
static void cylinder_ends(Upd765 *f)
{
    if (f->mt)
        f->h ^= 1;
    ++f->c;
    f->r = 1;
    abnormal(f, 0x00, 0x80, 0x00);
}

/* After the sector EOT: the end the wiring gives (see upd765.h). */
static void end_of_cylinder(Upd765 *f)
{
    if (f->tc_wired)
        f->at_end = 1;
    else
        cylinder_ends(f);
}

/* The sector is done (all its bytes moved, or skipped): the next one, or the end of the command. */
static void next_sector(Upd765 *f)
{
    f->pos = 0;
    if (f->command == CMD_READ_TRACK) {
        ++f->r;
        if (--f->track_left == 0) {
            end_of_cylinder(f);
            return;
        }
        const DskTrack *t = head_track(f);
        Upd765Drive *d = unit_drive(f, f->unit);
        unsigned i = d->position;
        d->position = (uint8_t)((i + 1) % t->count);
        begin_sector(f, t->first + i);
        return;
    }
    if (f->r == f->eot) {
        const Upd765Drive *d = unit_drive_c(f, f->unit);
        if (f->mt && f->head == 0 && d->image && d->image->sides == 2) {
            f->head = 1;
            f->h = 1;
            f->r = 1;
        } else {
            end_of_cylinder(f);
            return;
        }
    } else {
        ++f->r;
    }
    int index = find_sector(f);
    if (index < 0) {
        abnormal(f, 0x00, 0x00, 0x00);
        return;
    }
    while (!begin_sector(f, index)) {
        if (f->phase != UPD765_EXEC_READ && f->phase != UPD765_EXEC_WRITE)
            return;                                                  /* ended */
        /* skipped (SK): on to the next ID */
        if (f->r == f->eot) {
            end_of_cylinder(f);
            return;
        }
        ++f->r;
        index = find_sector(f);
        if (index < 0) {
            abnormal(f, 0x00, 0x00, 0x00);
            return;
        }
    }
}

static int begin_sector(Upd765 *f, int index)
{
    const DskSector *s = sector_of(f, (unsigned)index);
    f->sector = (uint16_t)index;
    f->pos = 0;
    f->length = transfer_length(f);
    if (f->command == CMD_READ_TRACK) {
        if (s->c != f->c || s->h != f->h || s->r != f->r || s->n != f->n)
            f->st1 |= 0x04;                                          /* READ TRACK goes on past an ID that does not match */
    } else {
        if (s->st2 & 0x01) {                                         /* an ID with no data field */
            abnormal(f, 0x00, 0x01, 0x01);
            return 0;
        }
        int deleted = (s->st2 & 0x40) != 0;
        int wanted_deleted = f->command == CMD_READ_DELETED;
        if (is_read(f->command) && deleted != wanted_deleted) {
            f->st2 |= 0x40;                                          /* control mark */
            if (f->sk)
                return 0;                                            /* skipped */
        }
    }
    f->copy = 0;
    if (is_read(f->command) && s->copies > 1)
        f->copy = (uint8_t)(f->weak_reads++ % s->copies);
    return 1;
}

/* A read or write sector ends: its own error, the control mark (one sector only), or the next one. */
static void sector_done(Upd765 *f)
{
    const DskSector *s = sector_of(f, f->sector);
    if (is_read(f->command) && f->command != CMD_READ_TRACK && ((s->st1 & 0x20) || (s->st2 & 0x20))) {
        abnormal(f, 0x00, 0x20, (uint8_t)(s->st2 & 0x20));          /* a CRC error: DE, and DD when it is in the data field */
        return;
    }
    if (is_read(f->command) && f->command != CMD_READ_TRACK && (f->st2 & 0x40) && !f->sk) {
        f->pos = 0;
        f->st0 = us_hd(f);                                           /* a control mark ends the read after this sector */
        if (f->r == f->eot) { ++f->c; f->r = 1; } else { ++f->r; }
        result7(f);
        return;
    }
    next_sector(f);
}

static int drive_ready(const Upd765 *f)
{
    return unit_drive_c(f, f->unit)->image != NULL;
}

static void start_transfer(Upd765 *f)
{
    f->mt = (uint8_t)(f->cmd[0] >> 7);
    f->sk = (uint8_t)((f->cmd[0] >> 5) & 1);
    f->unit = f->cmd[1] & 3;
    f->head = (f->cmd[1] >> 2) & 1;
    f->c = f->cmd[2]; f->h = f->cmd[3]; f->r = f->cmd[4]; f->n = f->cmd[5]; f->eot = f->cmd[6]; f->dtl = f->cmd[8];
    f->st0 = f->st1 = f->st2 = 0;
    f->pos = 0;
    f->at_end = 0;
    int write = f->command == CMD_WRITE || f->command == CMD_WRITE_DELETED;
    ++f->commands;
    if (!drive_ready(f)) {
        abnormal(f, 0x08, 0x00, 0x00);                               /* not ready */
        return;
    }
    Upd765Drive *d = unit_drive(f, f->unit);
    if (f->command == CMD_READ && f->c == 0 && f->h == 0 && f->head == 0 && d->pcn == 0) {
        const DskTrack *t = dsk_track(d->image, 0, 0);
        if (t && t->count) {
            uint8_t lowest = 0xFF;
            for (unsigned i = 0; i < t->count; ++i)
                if (sector_of(f, t->first + i)->r < lowest)
                    lowest = sector_of(f, t->first + i)->r;
            if (f->r == lowest)
                ++f->boot_reads;
        }
    }
    if (write && d->write_protected) {
        abnormal(f, 0x00, 0x02, 0x00);                               /* not writable */
        return;
    }
    f->phase = write ? UPD765_EXEC_WRITE : UPD765_EXEC_READ;
    if (f->command == CMD_READ_TRACK) {
        const DskTrack *t = head_track(f);
        if (!t || !t->count) {
            abnormal(f, 0x00, 0x01, 0x00);
            return;
        }
        f->track_left = f->eot ? f->eot : 1;
        d->position = (uint8_t)(1 % t->count);                       /* from the index hole */
        begin_sector(f, t->first);
        return;
    }
    int index = find_sector(f);
    if (index < 0) {
        abnormal(f, 0x00, 0x00, 0x00);
        return;
    }
    while (!begin_sector(f, index)) {
        if (f->phase == UPD765_RESULT)
            return;
        if (f->r == f->eot) {
            end_of_cylinder(f);
            return;
        }
        ++f->r;
        index = find_sector(f);
        if (index < 0) {
            abnormal(f, 0x00, 0x00, 0x00);
            return;
        }
    }
}

static void start_format(Upd765 *f)
{
    f->unit = f->cmd[1] & 3;
    f->head = (f->cmd[1] >> 2) & 1;
    f->n = f->cmd[2];
    f->format_left = f->cmd[3];
    f->format_fill = f->cmd[5];
    f->st0 = f->st1 = f->st2 = 0;
    f->pos = 0;
    if (!drive_ready(f)) {
        abnormal(f, 0x08, 0x00, 0x00);
        return;
    }
    Upd765Drive *d = unit_drive(f, f->unit);
    if (d->write_protected) {
        abnormal(f, 0x00, 0x02, 0x00);
        return;
    }
    /* The image keeps its layout: a track is formatted in place when it already holds as many sectors with room for the new
     * size; any other layout is refused as not writable, and counted. */
    const DskTrack *t = head_track(f);
    int fits = t && t->count == f->format_left && f->format_left;
    for (unsigned i = 0; fits && i < t->count; ++i) {
        const DskSector *s = sector_of(f, t->first + i);
        if (s->copies != 1 || s->stored < dsk_sector_bytes(f->n))
            fits = 0;
    }
    if (!fits) {
        ++f->unmodelled;
        abnormal(f, 0x00, 0x02, 0x00);
        return;
    }
    f->phase = UPD765_EXEC_FORMAT;
}

static void execute(Upd765 *f)
{
    f->command = f->cmd[0] & 0x1F;
    switch (f->command) {
    case CMD_SPECIFY:                                                /* step rate, head load and unload: no timing modelled */
        result_bytes(f, NULL, 0);
        break;
    case CMD_SENSE_DRIVE: {
        uint8_t st3 = upd765_st3(f, f->cmd[1] & 3);
        st3 = (uint8_t)((st3 & ~0x07) | (f->cmd[1] & 7));
        result_bytes(f, &st3, 1);
        break;
    }
    case CMD_READ: case CMD_READ_DELETED: case CMD_READ_TRACK: case CMD_WRITE: case CMD_WRITE_DELETED:
        start_transfer(f);
        break;
    case CMD_RECALIBRATE: {
        uint8_t u = f->cmd[1] & 3;
        Upd765Drive *d = unit_drive(f, u);
        d->pcn = 0;
        f->int_pending[u] = 1;
        f->int_st0[u] = (uint8_t)(0x20 | u | (d->image ? 0x00 : 0x48));
        result_bytes(f, NULL, 0);
        break;
    }
    case CMD_SEEK: {
        uint8_t u = f->cmd[1] & 3;
        Upd765Drive *d = unit_drive(f, u);
        d->pcn = f->cmd[2] < DSK_MAX_CYLINDERS ? f->cmd[2] : DSK_MAX_CYLINDERS - 1;
        f->int_pending[u] = 1;
        f->int_st0[u] = (uint8_t)(0x20 | (f->cmd[1] & 7) | (d->image ? 0x00 : 0x48));
        result_bytes(f, NULL, 0);
        break;
    }
    case CMD_SENSE_INT:
        for (int u = 0; u < UPD765_DRIVES; ++u)
            if (f->int_pending[u]) {
                f->int_pending[u] = 0;
                uint8_t out[2] = { f->int_st0[u], unit_drive(f, (uint8_t)u)->pcn };
                result_bytes(f, out, 2);
                return;
            }
        {
            uint8_t invalid = 0x80;                                  /* nothing to report: "invalid", as the chip answers */
            result_bytes(f, &invalid, 1);
        }
        break;
    case CMD_READ_ID: {
        f->unit = f->cmd[1] & 3;
        f->head = (f->cmd[1] >> 2) & 1;
        f->st0 = f->st1 = f->st2 = 0;
        if (!drive_ready(f)) {
            abnormal(f, 0x08, 0x00, 0x00);
            break;
        }
        const DskTrack *t = head_track(f);
        if (!t || !t->count) {
            abnormal(f, 0x00, 0x01, 0x00);                           /* missing address mark */
            break;
        }
        Upd765Drive *d = unit_drive(f, f->unit);
        const DskSector *s = sector_of(f, t->first + d->position % t->count);
        d->position = (uint8_t)((d->position + 1) % t->count);
        f->c = s->c; f->h = s->h; f->r = s->r; f->n = s->n;
        f->st0 = us_hd(f);
        result7(f);
        break;
    }
    case CMD_FORMAT:
        start_format(f);
        break;
    default: {
        uint8_t invalid = 0x80;
        ++f->unmodelled;
        result_bytes(f, &invalid, 1);
        break;
    }
    }
}

uint8_t upd765_st3(const Upd765 *f, int drive)
{
    const Upd765Drive *d = unit_drive_c(f, (uint8_t)drive);
    uint8_t st3 = (uint8_t)(drive & 3);
    if (d->image) {
        st3 |= 0x20;
        if (d->write_protected) st3 |= 0x40;
        if (d->image->sides == 2) st3 |= 0x08;
    }
    if (d->pcn == 0) st3 |= 0x10;
    return st3;
}

uint8_t upd765_status(const Upd765 *f)
{
    switch (f->phase) {
    case UPD765_EXEC_READ: return 0xF0;
    case UPD765_EXEC_WRITE: case UPD765_EXEC_FORMAT: return 0xB0;
    case UPD765_RESULT: return 0xD0;
    default: return f->cmd_len ? 0x90 : 0x80;
    }
}

static uint8_t sector_byte(const Upd765 *f)
{
    const DskSector *s = sector_of(f, f->sector);
    if (!s->stored)
        return 0x00;
    const uint8_t *bytes = unit_drive_c(f, f->unit)->image->bytes;
    return bytes[s->data + (uint32_t)f->copy * s->stored + f->pos % s->stored];
}

uint8_t upd765_read_data(Upd765 *f)
{
    if (f->phase == UPD765_RESULT) {
        uint8_t v = f->result[f->result_pos++];
        if (f->result_pos >= f->result_len)
            f->phase = UPD765_COMMAND;
        return v;
    }
    if (f->phase != UPD765_EXEC_READ)
        return 0xFF;
    if (f->at_end) {                                                 /* a byte asked after EOT: the terminal count came late */
        cylinder_ends(f);
        return 0xFF;
    }
    uint8_t v = sector_byte(f);
    if (++f->pos >= f->length)
        sector_done(f);
    return v;
}

static void write_byte(Upd765 *f, uint8_t value)
{
    Upd765Drive *d = unit_drive(f, f->unit);
    DskSector *s = &d->image->sector[f->sector];
    if (f->pos == 0) {                                               /* a fresh data field: its mark and a good CRC */
        uint8_t st2 = (uint8_t)(s->st2 & ~0x60);
        if (f->command == CMD_WRITE_DELETED)
            st2 |= 0x40;
        uint8_t st1 = (uint8_t)(s->st1 & ~0x20);
        if (st2 != s->st2 || st1 != s->st1) {
            s->st2 = st2;
            s->st1 = st1;
            if (d->image->extended) {
                d->image->bytes[s->info + 4] = st1;
                d->image->bytes[s->info + 5] = st2;
            }
        }
    }
    if (f->pos < s->stored) {
        for (unsigned k = 0; k < s->copies; ++k)
            d->image->bytes[s->data + k * s->stored + f->pos] = value;
        d->written = 1;
    }
}

void upd765_write_data(Upd765 *f, uint8_t value)
{
    switch (f->phase) {
    case UPD765_COMMAND:
        if (!f->cmd_len)
            f->cmd_need = NEED[value & 0x1F] ? NEED[value & 0x1F] : 1;
        f->cmd[f->cmd_len++] = value;
        if (f->cmd_len >= f->cmd_need) {
            f->cmd_len = 0;
            execute(f);
        }
        break;
    case UPD765_EXEC_WRITE:
        if (f->at_end) {                                             /* a byte given after EOT: not written, the transfer ends */
            cylinder_ends(f);
            break;
        }
        write_byte(f, value);
        if (++f->pos >= f->length)
            next_sector(f);
        break;
    case UPD765_EXEC_FORMAT: {
        f->format_id[f->pos++] = value;
        if (f->pos < 4)
            break;
        f->pos = 0;
        Upd765Drive *d = unit_drive(f, f->unit);
        const DskTrack *t = head_track(f);
        unsigned k = (unsigned)(t->count - f->format_left);
        DskSector *s = &d->image->sector[t->first + k];
        s->c = f->format_id[0]; s->h = f->format_id[1]; s->r = f->format_id[2]; s->n = f->format_id[3];
        s->st1 = s->st2 = 0;
        memcpy(d->image->bytes + s->info, f->format_id, 4);
        if (d->image->extended) {
            d->image->bytes[s->info + 4] = 0;
            d->image->bytes[s->info + 5] = 0;
        }
        memset(d->image->bytes + s->data, f->format_fill, s->stored);
        d->written = 1;
        f->c = s->c; f->h = s->h; f->r = s->r; f->n = s->n;
        if (--f->format_left == 0) {
            d->position = 0;
            f->st0 = us_hd(f);
            result7(f);
        }
        break;
    }
    default:
        break;                                                       /* a byte in the result phase is not data */
    }
}

void upd765_terminal_count(Upd765 *f)
{
    if (f->phase != UPD765_EXEC_READ && f->phase != UPD765_EXEC_WRITE)
        return;
    if (f->at_end || f->pos != 0) {                                  /* after EOT, or during a sector (it completes) */
        if (f->r == f->eot) { ++f->c; f->r = 1; } else { ++f->r; }
    }
    f->pos = 0;
    f->st0 = us_hd(f);
    result7(f);
}
