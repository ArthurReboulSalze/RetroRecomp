/* DSK and EXTENDED DSK floppy images (the CPCEMU formats of the Amstrad CPC, also used by the Spectrum +3): parsed in place into
 * a table of tracks and sector IDs that the uPD765 (upd765.h) reads. MIT, Retro-Recomp.
 *
 * Written from the format's public description (the CPCEMU "MV - CPCEMU Disk-File" layout and the "EXTENDED CPC DSK File"
 * specification with its 2002-2007 extensions: per-track sizes, per-sector stored lengths, several copies of a weak sector).
 * floooh/chips fdd_cpc.h (zlib) and Clock Signal's CPCDSK.cpp (MIT) were read as documentation; nothing of them is copied.
 *
 * Layout. The image starts with a 256-byte disk block: 34 bytes of signature, 14 of creator, then the track count (30h), the
 * side count (31h) and, for a standard image, one size for every track (32h, little endian, the 256-byte track block
 * included); an extended image has instead one byte per track from 34h, its size in units of 256 bytes, 0 for a track that is
 * not formatted. Each track starts with a 256-byte block ("Track-Info\r\n", 10h track, 11h side, 14h sector size N, 15h sector
 * count, 16h GAP#3, 17h filler) and its sector list from 18h, 8 bytes each: C, H, R, N, ST1, ST2 and, in an extended image,
 * the stored length (little endian). The sector data follow the track block in list order. A standard image stores
 * 128 << N bytes per sector, N the track's (at most 1800h); an extended one stores the stated length, a multiple of the
 * sector's size when it holds several copies of a weak sector (the controller gives one copy per read).
 *
 * Nothing here allocates or keeps state of its own: the tables point into the image, which the caller owns. */
#ifndef RR_DSK_IMAGE_H
#define RR_DSK_IMAGE_H
#include <stdint.h>

enum {
    DSK_MAX_CYLINDERS = 84,          /* a 3" or 3.5" drive steps to about 82; images rarely hold more than 42 */
    DSK_MAX_SIDES = 2,
    DSK_MAX_SECTORS_PER_TRACK = 29,  /* what a 256-byte track block can list */
    DSK_MAX_SECTORS = DSK_MAX_CYLINDERS * DSK_MAX_SIDES * DSK_MAX_SECTORS_PER_TRACK,
};

/* Why an image was refused (dsk_parse's return); 0 is a good image. */
enum {
    DSK_OK = 0,
    DSK_ERR_SIGNATURE,      /* neither "MV - CPC" nor "EXTENDED" */
    DSK_ERR_GEOMETRY,       /* no track, more than DSK_MAX_CYLINDERS or not one or two sides */
    DSK_ERR_TRACK_BLOCK,    /* a track's block is missing, past the end, or not "Track-Info" */
    DSK_ERR_SECTOR_COUNT,   /* more sectors than a track block can list */
    DSK_ERR_SECTOR_DATA,    /* a sector's data run past its track or the image */
};

typedef struct {
    uint8_t c, h, r, n;     /* the ID field as the controller reads it */
    uint8_t st1, st2;       /* the controller's status recorded with the sector (extended images; 0 in a standard one) */
    uint8_t copies;         /* 1, or the number of copies of a weak sector */
    uint8_t unused;
    uint32_t stored;        /* bytes stored for one copy (0: an ID with no data field) */
    uint32_t data;          /* offset of the first copy in the image */
    uint32_t info;          /* offset of its 8-byte entry in the track block (to record a deleted mark written) */
} DskSector;

typedef struct {
    uint16_t first;         /* index of its first sector in DskImage.sector */
    uint8_t count;          /* 0: not formatted */
    uint8_t n, gap3, filler;
} DskTrack;

typedef struct {
    uint8_t *bytes;
    uint32_t size;
    uint8_t cylinders, sides, extended;
    DskTrack track[DSK_MAX_CYLINDERS * DSK_MAX_SIDES];   /* cylinder * sides + side */
    DskSector sector[DSK_MAX_SECTORS];
    uint16_t sector_count;
} DskImage;

/* Read an image in place; 0 (DSK_OK) or the reason it was refused, the image then left empty (no track). */
int dsk_parse(DskImage *image, uint8_t *bytes, uint32_t size);
/* The track under a head, NULL when the cylinder or the side is not on the image. */
const DskTrack *dsk_track(const DskImage *image, unsigned cylinder, unsigned side);
/* 128 << n, as the controller counts a sector of size code n (n is taken modulo 8, as the uPD765 does). */
uint32_t dsk_sector_bytes(uint8_t n);
#endif
