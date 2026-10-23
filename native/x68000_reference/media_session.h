/* Private X68000 media-session frontend. Original Retro-Recomp code, MIT. */
#ifndef RR_X68000_MEDIA_SESSION_H
#define RR_X68000_MEDIA_SESSION_H
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <libretro.h>
#define RR_MEDIA_MAX 10
#define RR_MEDIA_PATH 2048
#define RR_MEDIA_IMAGE_MAX (2u * 1024u * 1024u)
#define RR_MEDIA_SNAPSHOT_MAX (RR_MEDIA_MAX * RR_MEDIA_IMAGE_MAX + 1024u)
/* A short physical removal interval. Some guest loaders wait ten 100-Hz
 * timer ticks before checking the empty drive; reinserting in that interval
 * makes them wait forever. 16 complete frames also cover the 55-Hz mode. */
#define RR_MEDIA_INSERT_WAIT 16u
/* A candidate the guest ejects again within this many frames was refused.
 * Observed refusals: 17 frames (Power Unit), 78 frames (Metal Sight). */
#define RR_MEDIA_REJECT_WINDOW 300u
/* One guest request per drive, answered by rr_media_auto_advance. */
typedef struct {
    unsigned char active;    /* 0 none, 1 answering, 2 every candidate refused. */
    unsigned char polled;    /* Frames (up to 2) the guest polled this empty drive. */
    unsigned char moved;     /* The candidate was taken from the other drive. */
    signed char base;        /* Disk the guest ejected, or the other drive's disk. */
    signed char inserted;    /* Candidate being tried, -1 between candidates. */
    unsigned short refused;  /* Disks excluded for this request. */
    unsigned short window;   /* Frames left in which an eject is a refusal. */
} RRMediaRequest;
typedef struct {
    char content[RR_MEDIA_PATH], directory[RR_MEDIA_PATH], session_file[RR_MEDIA_PATH];
    char names[RR_MEDIA_MAX][32];
    unsigned count;
    int selected[2]; /* Last chosen image, retained across a guest eject. */
    unsigned empty_frames[2];
    RRMediaRequest request[2];
    struct retro_disk_control_callback disk;
    void (*select_drive)(unsigned);
    unsigned (*ready_mask)(void);
    /* Optional, set with rr_media_set_interest after rr_media_open. */
    unsigned (*interest)(unsigned);
    unsigned interest_seen[2];
    uint64_t identity;
    char error[192];
} RRMediaSession;
/* Call once after each complete guest frame of a multi-disk set. Only the
 * guest starts a change: a drive it ejected and then keeps polling (in two
 * frames after the eject) or blinks, or an empty drive it blinks to request
 * media. A game that ejects disks it has finished loading, and polls the
 * drive at most once more, is left alone. After
 * the bounded removal interval, candidates follow the set
 * order after the ejected disk (excluded), or after the other drive's disk for
 * a blink request. After an eject, the other drive's disk may be moved (its
 * drive is emptied first). A candidate the guest ejects again within
 * RR_MEDIA_REJECT_WINDOW frames is refused: a moved disk returns to its drive
 * and the next candidate follows. When every candidate is refused the drive
 * stays empty for the player. A host eject alone never starts a request; any
 * host change of a drive ends its request. Returns insertions made, -1 on error. */
int rr_media_auto_advance(RRMediaSession *);
/* Guest drive-interest counter (rr_x68000_media_interest); NULL leaves only
 * blink requests. Takes the current counts as the starting point. */
void rr_media_set_interest(RRMediaSession *, unsigned (*interest)(unsigned));
/* Open after retro_load_game. Only bounded private staged DIM/XDF media accepted.
 * select_drive drives the px68k_disk_drive variable used by the real callbacks. */
int rr_media_open(RRMediaSession *, const char *content, const char *session_file,
                  const struct retro_disk_control_callback *,
                  void (*select_drive)(unsigned), unsigned (*ready_mask)(void));
int rr_media_swap(RRMediaSession *, unsigned drive, int image);
int rr_media_boot(RRMediaSession *);
int rr_media_cycle(RRMediaSession *, unsigned drive, int direction);
int rr_media_save_session(RRMediaSession *);
int rr_media_load_session(RRMediaSession *); /* Missing saved session is success. */
/* Allocated opaque portable aux payload; caller frees it. Captures private file
 * bytes plus drive choices. In-memory dirty sectors/cursors are core state. */
int rr_media_capture(RRMediaSession *, void **data, size_t *size);
int rr_media_validate(RRMediaSession *, const void *data, size_t size);
int rr_media_apply(RRMediaSession *, const void *data, size_t size);
const char *rr_media_error(const RRMediaSession *);
/* Bits 0/1: presence; bits 8/9: guest-requested drive blink. */
unsigned rr_x68000_media_ready(void);
unsigned rr_x68000_media_activity(void);
/* Monotonic count of guest polls/commands aimed at a drive. Not machine state:
 * only differences between consecutive frames are meaningful. */
unsigned rr_x68000_media_interest(unsigned drive);
#endif
