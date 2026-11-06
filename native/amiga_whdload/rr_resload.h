/* Retro-Recomp: the resload services a WHDLoad slave calls, answered by the host (MIT).
 *
 * Written from the public WHDLoad autodoc and include file (offsets, register conventions, patch-list and tag
 * encodings); no WHDLoad code is used. The slave and the game run as 68000 code in the machine; when the slave jumps
 * into the resload table, the machine stops the CPU at that address and calls rr_resload_call() with the CPU
 * registers. Guest memory is reached only through the host callbacks, so the same code serves the reference machine
 * and the native build. Every call is counted per entry; an entry or a format this layer does not provide is
 * refused with its number (RR_RESLOAD_REFUSED), never answered with a pretended success.
 */
#ifndef RR_RESLOAD_H
#define RR_RESLOAD_H

#include <stdint.h>

#define RR_RESLOAD_FORMAT 1
#define RR_RESLOAD_ENTRIES 36          /* offsets $00 (private Install) to $8C (ReadJoyPort), 4 bytes each */
#define RR_RESLOAD_WHDLOAD_VERSION 18  /* what resload_Control answers for WHDLTAG_VERSION_GET */

enum { RR_RESLOAD_RETURN = 0, RR_RESLOAD_ABORT = 1, RR_RESLOAD_REFUSED = 2 };

/* DOS error codes the services return in D1 (dos/dos.h). */
enum {
    RR_DOS_OBJECT_NOT_FOUND = 205, RR_DOS_OBJECT_WRONG_TYPE = 212, RR_DOS_WRITE_PROTECTED = 214, RR_DOS_SEEK_ERROR = 219,
    RR_DOS_DISK_FULL = 221, RR_DOS_NO_MORE_ENTRIES = 232, RR_DOS_BUFFER_OVERFLOW = 303
};

#define RR_FIB_SIZE 260                /* sizeof(struct FileInfoBlock), dos/dosextens.h */
#define RR_SCAN_SLOTS 16               /* directories that can be walked with Examine/ExNext at the same time */

typedef struct RrResloadHost {
    void *user;
    uint8_t (*read8)(void *user, uint32_t address);
    void (*write8)(void *user, uint32_t address, uint8_t value);
    /* A data file by its name relative to the data folder (AmigaDOS: case-insensitive, '/' separated).
       Returns 1 and its bytes, or 0 when there is no such file. Disk images are the files "Disk.N". */
    int (*file)(void *user, const char *name, const uint8_t **data, uint32_t *size);
    /* Writes `size` bytes at `offset` of a save file (`whole`: the file becomes exactly these bytes).
       Returns 0 or a DOS error code. NULL: the install is read-only. */
    int (*save)(void *user, const char *name, uint32_t offset, const uint8_t *data, uint32_t size, int whole);
    int (*remove)(void *user, const char *name);
    /* Guest code may have changed (loads, patches, FlushCache): native code must check its guards again. */
    void (*flush)(void *user);
    /* The install's files, for Examine, ExNext and ListFiles: the `index`-th file (0, 1, 2 ...) with its name relative
       to the data folder ('/' separated, folders are implied by the names) and its size. Returns 0 past the last file.
       The order is the host's own (the layer sorts what it shows); the name stays valid until the next call. NULL: the
       install shows no files (only the root folder exists). */
    int (*list)(void *user, uint32_t index, const char **name, uint32_t *size);
    /* The player's Kickstart image, which the host owns (the layer never keeps it). Returns 1 when the image the player
       has is the one asked for - its size and CRC-16 are `size` and `crc16`; `name` (the base name the slave asks
       for, e.g. "34005.a500") is only a hint - and, in that case, has copied it to guest address `destination` (the
       start of ExpMem; any relocation of the image is the host's). Returns 0, touching no guest memory, when the
       player has no such image. NULL: the host has no Kickstart. */
    int (*kickstart)(void *user, uint32_t size, uint16_t crc16, const char *name, uint32_t destination);
} RrResloadHost;

typedef struct RrScan {
    uint16_t token;                    /* 0: free; else (generation << 4) | slot, kept in the high half of fib_DiskKey */
    char dir[256];
} RrScan;

typedef struct RrResload {
    RrResloadHost host;
    uint32_t slave_base;               /* address of the slave's first hunk in guest memory */
    uint16_t slave_version, slave_flags;
    uint32_t custom[5];                /* the Custom1-5 options */
    int32_t button_wait;               /* 0 or -1 */
    uint32_t attn_flags;               /* exec AttnFlags of the modelled CPU (0 for a 68000) */
    uint32_t eclock;                   /* E clock in Hz: 709379 PAL, 715909 NTSC */
    uint32_t monitor;                  /* monitor id: 0x00021000 PAL, 0x00011000 NTSC */
    uint32_t exp_mem_size;
    uint32_t exp_mem;                  /* guest address of ExpMem, where a Kickstart image is loaded; 0: none */
    uint32_t keytrans;                 /* guest address of the 128-byte raw-key table, 0: none */
    uint32_t cbswitch, cbaf;           /* functions the slave registered (kept, never called: no OS switch here) */
    uint32_t scratch;                  /* guest address of 256 bytes the host reserves for answers (TIME_GET), 0: none */
    uint32_t time_days, time_mins, time_ticks;   /* the fixed start time TIME_GET reports (days since 1978-01-01) */
    uint32_t io_error;                 /* last DOS error of a service */
    uint32_t unknown_tags;             /* Control items not processed (the call returned FALSE) */
    uint32_t calls[RR_RESLOAD_ENTRIES];
    uint32_t refused_offset;           /* entry or reason of the last refusal */
    uint32_t abort_reason[3];          /* resload_Abort arguments: success, primary, secondary */
    char message[320];                 /* why the last call refused or aborted */
    /* Kickstart: the image loaded by rr_resload_load_slave_kickstart or resload_LoadKick (kick_loaded 0: none), and,
       after a refusal, the first image asked for with how many were asked for in all. */
    uint8_t kick_loaded;
    uint32_t kick_size;
    uint16_t kick_crc;
    char kick_name[64];
    uint32_t kick_wanted_size;
    uint16_t kick_wanted_crc;
    char kick_wanted_name[64];
    uint32_t kick_wanted_count;
    RrScan scans[RR_SCAN_SLOTS];       /* the directories Examine has opened for ExNext */
    uint16_t scan_generation;
} RrResload;

void rr_resload_init(RrResload *r, const RrResloadHost *host, uint32_t slave_base, uint16_t version, uint16_t flags);

/* Performs the service at `offset` of the resload table. `regs` holds D0-D7 then A0-A7 and is updated with the
   results; registers the autodoc does not name as results are left as they were. */
int rr_resload_call(RrResload *r, uint32_t offset, uint32_t regs[16]);

/* The Kickstart a v16+ slave's header asks for (ws_kickname, ws_kicksize, ws_kickcrc), loaded before the slave runs:
   the image goes to the start of ExpMem (r->exp_mem) through host.kickstart. With ws_kickcrc == 0xFFFF the header
   holds a table of (CRC-16, name) pairs ended by CRC 0: they are tried in order and the CRC-16 of the one loaded is
   written into ws_kickcrc of the slave in guest memory. Returns RR_RESLOAD_RETURN when the image is loaded or the slave
   asks for none (version below 16, or ws_kicksize 0: r->kick_loaded tells), RR_RESLOAD_REFUSED when the player has no
   such image (r->message names what was asked for; r->kick_wanted_* hold the first image asked for). */
int rr_resload_load_slave_kickstart(RrResload *r);

/* The CRC-16 resload_CRC16 computes (ANSI CRC-16, polynomial 0x8005 reflected, the LHA/ARC variant). */
uint16_t rr_resload_crc16(const RrResload *r, uint32_t address, uint32_t length);

/* Applies a patch list (resload_Patch): `list` and `destination` are guest addresses. Returns RR_RESLOAD_RETURN or
   RR_RESLOAD_REFUSED (unknown command, BKPT/BELL, unbalanced IF). */
int rr_resload_patch(RrResload *r, uint32_t list, uint32_t destination);

#endif
