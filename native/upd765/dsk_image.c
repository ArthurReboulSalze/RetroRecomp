/* DSK and EXTENDED DSK images: see dsk_image.h. MIT, Retro-Recomp. */
#include "dsk_image.h"

#include <string.h>

uint32_t dsk_sector_bytes(uint8_t n)
{
    return 128u << (n & 7);
}

const DskTrack *dsk_track(const DskImage *image, unsigned cylinder, unsigned side)
{
    if (!image->bytes || cylinder >= image->cylinders || side >= image->sides)
        return NULL;
    return &image->track[cylinder * image->sides + side];
}

static uint32_t le16(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8; }

static int refuse(DskImage *image, int why)
{
    memset(image, 0, sizeof *image);
    return why;
}

int dsk_parse(DskImage *image, uint8_t *bytes, uint32_t size)
{
    memset(image, 0, sizeof *image);
    if (!bytes || size < 256)
        return DSK_ERR_SIGNATURE;
    int extended;
    if (!memcmp(bytes, "EXTENDED", 8))
        extended = 1;
    else if (!memcmp(bytes, "MV - CPC", 8))
        extended = 0;
    else
        return DSK_ERR_SIGNATURE;
    unsigned cylinders = bytes[0x30], sides = bytes[0x31];
    if (!cylinders || cylinders > DSK_MAX_CYLINDERS || sides < 1 || sides > DSK_MAX_SIDES)
        return DSK_ERR_GEOMETRY;
    image->bytes = bytes;
    image->size = size;
    image->cylinders = (uint8_t)cylinders;
    image->sides = (uint8_t)sides;
    image->extended = (uint8_t)extended;
    uint32_t standard_size = le16(bytes + 0x32);
    uint32_t at = 256;
    for (unsigned t = 0; t < cylinders * sides; ++t) {
        uint32_t track_size = extended ? (uint32_t)bytes[0x34 + t] << 8 : standard_size;
        DskTrack *track = &image->track[t];
        track->first = image->sector_count;
        if (!track_size)
            continue;                                                /* an extended image's unformatted track */
        if (track_size < 256 || at + track_size > size || memcmp(bytes + at, "Track-Info", 10))
            return refuse(image, DSK_ERR_TRACK_BLOCK);
        const uint8_t *block = bytes + at;
        unsigned count = block[0x15];
        if (count > DSK_MAX_SECTORS_PER_TRACK)
            return refuse(image, DSK_ERR_SECTOR_COUNT);
        track->count = (uint8_t)count;
        track->n = block[0x14];
        track->gap3 = block[0x16];
        track->filler = block[0x17];
        uint32_t data = at + 256;
        /* An early extended image left every stored length out (0): its sectors then hold 128 << N bytes. A track with some
         * lengths given means what it says: a 0 is a sector with no data (a protection's test track). */
        int lengths_given = 0;
        for (unsigned s = 0; s < count; ++s)
            lengths_given |= block[0x18 + 8 * s + 6] | block[0x18 + 8 * s + 7];
        for (unsigned s = 0; s < count; ++s) {
            const uint8_t *info = block + 0x18 + 8 * s;
            DskSector *sector = &image->sector[image->sector_count++];
            sector->c = info[0];
            sector->h = info[1];
            sector->r = info[2];
            sector->n = info[3];
            sector->st1 = extended ? info[4] : 0;
            sector->st2 = extended ? info[5] : 0;
            sector->info = at + 0x18 + 8 * s;
            uint32_t nominal = dsk_sector_bytes(sector->n);
            uint32_t stored;
            if (extended) {
                stored = le16(info + 6);
                if (!lengths_given)
                    stored = nominal > 0x1800 ? 0x1800 : nominal;
            } else {
                stored = dsk_sector_bytes(track->n);
                if (stored > 0x1800)
                    stored = 0x1800;
            }
            uint8_t copies = 1;
            if (extended && stored > nominal && stored % nominal == 0 && stored / nominal <= 255)
                copies = (uint8_t)(stored / nominal);
            sector->copies = copies;
            sector->stored = stored / copies;
            sector->data = data;
            if (data + stored > at + track_size || data + stored > size)
                return refuse(image, DSK_ERR_SECTOR_DATA);
            data += stored;
        }
        at += track_size;
    }
    return DSK_OK;
}
