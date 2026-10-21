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
typedef struct {
    char content[RR_MEDIA_PATH], directory[RR_MEDIA_PATH], session_file[RR_MEDIA_PATH];
    char names[RR_MEDIA_MAX][32];
    unsigned count;
    int selected[2]; /* Last chosen image, retained across a guest eject. */
    unsigned empty_frames[2];
    struct retro_disk_control_callback disk;
    void (*select_drive)(unsigned);
    unsigned (*ready_mask)(void);
    uint64_t identity;
    char error[192];
} RRMediaSession;
/* previous == RR_MEDIA_MAX: empty flashing drive, other drive holds next-1. */
typedef struct { unsigned drive,previous,next; } RRMediaRule;
/* Call once after each complete guest frame. Explicit, exact-game rules only.
 * Leave the bounded removal interval between eject and insertion so the
 * firmware can acknowledge removal. A host manual eject never triggers an
 * explicit previous-image rule. Moving media detaches the donor first. */
int rr_media_auto_advance(RRMediaSession *, const RRMediaRule *, unsigned count);
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
#endif
