/* The Atari ST's in-process snapshot, for multiplayer rollback and the host's F8 / F9 for everyone (docs/HOST_KIT.md, multiplayer). Original Retro-Recomp code, MIT; it is
 * linked with Hatari (GPL-2.0, licenses/hatari.md), so a program built with it is distributed under the GPL.
 *
 * Header only, included by the host-kit adapter and by the checks, so that the proofs run the very code a match runs. It uses the session's public calls only (the disk in the
 * drive, the table of the sectors the game wrote) and Hatari's lean snapshot (rr_snap_*, retrorecomp/atarist_hatari_rollback.py): memory only, into the caller's buffer, never a file,
 * never sent, no allocation unless a game has written sectors, valid after any frame, restored at once in place.
 *
 * A snapshot is: u32 magic, u32 size of Hatari's block, u32 size of the table of writes (0: none), u32 index of the disk in drive A, Hatari's block, the table of writes in the
 * session's own serial form. A snapshot of another game's disk, of another size or with a damaged header is refused before anything changes. */
#ifndef RR_ATARIST_SNAPSHOT_H
#define RR_ATARIST_SNAPSHOT_H
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "atarist_session.h"

size_t rr_snap_size(void);
size_t rr_snap_save(void *buffer, size_t capacity);
int rr_snap_load(const void *buffer, size_t size);
uint64_t rr_snap_digest(void);
void rr_rtc_session_clock(int64_t seconds);

#define RR_ST_SNAPSHOT_MAGIC 0x31534e52u          /* "RNS1" */
#define RR_ST_SNAPSHOT_HEADER 16u
/* The most a snapshot carries of what a game wrote to its disks (the sectors, in the session's serial form): a game that writes more cannot be saved (0 bytes, a refusal). */
#define RR_ST_SNAPSHOT_WRITES 65536u

static inline void rr_st_put32(uint8_t *at, uint32_t value) { at[0] = (uint8_t)value; at[1] = (uint8_t)(value >> 8); at[2] = (uint8_t)(value >> 16); at[3] = (uint8_t)(value >> 24); }
static inline uint32_t rr_st_get32(const uint8_t *at) { return (uint32_t)at[0] | (uint32_t)at[1] << 8 | (uint32_t)at[2] << 16 | (uint32_t)at[3] << 24; }

/* The session's serial form of an empty table of writes (its magic, a count of 0, the hash of no bytes): what a load of a snapshot without writes restores when the game has
 * written some since, so that the table is emptied. */
static inline size_t rr_st_empty_writes(uint8_t *out) {
   static const char magic[] = "RRATARIST-DISKWRITES-1\n";
   size_t at = sizeof magic - 1, n;
   uint64_t h = 0xcbf29ce484222325ull;                 /* the hash of an empty body (its offset basis) */
   memcpy(out, magic, at);
   for (n = 0; n < 4; n++) out[at++] = 0;
   for (n = 0; n < 8; n++) out[at++] = (uint8_t)(h >> (8 * n));
   return at;
}

/* A match begins (the host kit's session_begin): every seat reads the same clock (seconds since 1970, UTC; 0 returns to this PC's time) and starts from the export's own disks,
 * the sectors this PC's game wrote earlier left out. Nothing has run yet. */
static inline void rr_st_session_begin(RrStSession *s, uint64_t clock) {
   uint8_t empty[64];
   rr_rtc_session_clock((int64_t)clock);
   if (rr_st_writes_count(s)) rr_st_writes_restore(s, empty, rr_st_empty_writes(empty));
}

/* The most bytes a snapshot takes: 0 when this machine cannot be saved this way (a game on STX, SCP or Kryoflux images). */
static inline size_t rr_st_snapshot_bound(void) {
   size_t hatari = rr_snap_size();
   return hatari ? RR_ST_SNAPSHOT_HEADER + hatari + RR_ST_SNAPSHOT_WRITES : 0;
}

/* The bytes written, 0 on failure. */
static inline size_t rr_st_snapshot_save(RrStSession *s, void *buffer, size_t capacity) {
   uint8_t *out = (uint8_t *)buffer, *writes = NULL;
   size_t hatari = rr_snap_size(), writes_size = 0, total;
   if (!out || !hatari || capacity < RR_ST_SNAPSHOT_HEADER + hatari) return 0;
   if (rr_st_writes_count(s)) {
      writes_size = rr_st_writes_serialize(s, &writes);
      if (!writes || writes_size > RR_ST_SNAPSHOT_WRITES || RR_ST_SNAPSHOT_HEADER + hatari + writes_size > capacity) { free(writes); return 0; }
   }
   if (rr_snap_save(out + RR_ST_SNAPSHOT_HEADER, hatari) != hatari) { free(writes); return 0; }
   rr_st_put32(out, RR_ST_SNAPSHOT_MAGIC);
   rr_st_put32(out + 4, (uint32_t)hatari);
   rr_st_put32(out + 8, (uint32_t)writes_size);
   rr_st_put32(out + 12, rr_st_disk_index(s));
   if (writes_size) memcpy(out + RR_ST_SNAPSHOT_HEADER + hatari, writes, writes_size);
   free(writes);
   total = RR_ST_SNAPSHOT_HEADER + hatari + writes_size;
   return total;
}

/* Back to the saved state, at once. 0: refused, nothing changed (the size, the header or the disk are not this machine's). */
static inline int rr_st_snapshot_load(RrStSession *s, const void *buffer, size_t size) {
   const uint8_t *in = (const uint8_t *)buffer;
   size_t hatari = rr_snap_size(), writes_size;
   uint8_t empty[64];
   if (!in || !hatari || size < RR_ST_SNAPSHOT_HEADER + hatari || rr_st_get32(in) != RR_ST_SNAPSHOT_MAGIC || rr_st_get32(in + 4) != hatari) return 0;
   writes_size = rr_st_get32(in + 8);
   if (writes_size > RR_ST_SNAPSHOT_WRITES || size != RR_ST_SNAPSHOT_HEADER + hatari + writes_size || rr_st_get32(in + 12) != rr_st_disk_index(s)) return 0;
   if (writes_size) {
      if (rr_st_writes_restore(s, in + RR_ST_SNAPSHOT_HEADER + hatari, writes_size)) return 0;
   } else if (rr_st_writes_count(s)) {
      if (rr_st_writes_restore(s, empty, rr_st_empty_writes(empty))) return 0;
   }
   return rr_snap_load(in + RR_ST_SNAPSHOT_HEADER, hatari);
}

/* A restart inside a match: the machine goes back to `boot` (a snapshot saved after its first frame), keeping the disks as they are now (a reset does not undo a floppy's writes).
 * `scratch` holds `capacity` bytes (at least the bound). 0: refused, nothing changed. */
static inline int rr_st_snapshot_restart(RrStSession *s, const void *boot, size_t boot_size, void *scratch, size_t capacity) {
   const uint8_t *from = (const uint8_t *)boot;
   uint8_t *now = (uint8_t *)scratch;
   size_t hatari = rr_snap_size(), size;
   if (!from || !hatari || boot_size < RR_ST_SNAPSHOT_HEADER + hatari || rr_st_get32(from) != RR_ST_SNAPSHOT_MAGIC || rr_st_get32(from + 4) != hatari) return 0;
   if (!(size = rr_st_snapshot_save(s, now, capacity))) return 0;
   memcpy(now + RR_ST_SNAPSHOT_HEADER, from + RR_ST_SNAPSHOT_HEADER, hatari);          /* the machine of the boot, the header and the table of writes of now */
   return rr_st_snapshot_load(s, now, size);
}

/* The state the next frames depend on, as named fields (Hatari's, then the table of writes: how many sectors and a hash of them). */
static inline uint64_t rr_st_snapshot_digest(RrStSession *s) {
   uint64_t h = rr_snap_digest();
   unsigned count = rr_st_writes_count(s);
   h = (h ^ count) * 0x100000001b3ull;
   if (count) {
      uint8_t *writes = NULL;
      size_t size = rr_st_writes_serialize(s, &writes), n;
      for (n = 0; writes && n < size; n++) h = (h ^ writes[n]) * 0x100000001b3ull;
      free(writes);
   }
   return h;
}

#endif
