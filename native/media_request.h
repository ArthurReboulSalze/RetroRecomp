/* The next medium when the program asks for one, whatever the machine. MIT, Retro-Recomp.
 *
 * A machine reports the commands its program gives a disk drive, frame by frame (rr_media_command: how many, and whether they
 * were all one identity read, the read of the sector that tells one disk of a set from another: the boot sector on the MSX),
 * and each frame's picture (rr_media_frame, with a hash of it). A request is an identity read that stands alone: no other
 * drive command for `quiet` frames before it and after it, and the picture still for at least `still` frames when it came.
 * The program looked at which disk is in, did not take it, and went back to waiting (a "set disk 3 and push space" screen):
 * the caller puts the next disk of the set in (rr_media_frame returns 1). An identity read among other reads (loading, a file
 * opened through the disk system) is not a request, nor is a read while the picture moves. Nothing here names a title, a
 * disk or a sector number: the machine says what an identity read is.
 *
 * Kept by the caller (a route of the conversion, the player): it is not part of a quick state. A machine of the converter
 * that answers its programs' disk requests this way: the MSX2+ (msx_route.inc, msx_player.c). */
#pragma once

#include <stdint.h>
#include <string.h>

typedef struct {
    uint32_t quiet, still;      /* the rule: frames with no other drive command around the read, frames of still picture */
    uint64_t last_command;      /* the frame of the last command, UINT64_MAX before any */
    uint64_t pending;           /* the frame of a lone identity read waiting for its quiet frames, plus one (0: none) */
    uint32_t still_frames;      /* how many frames the picture has stayed the same */
    uint32_t picture;
    int have_picture;
    uint32_t answered;          /* the requests answered */
} RrMediaRequest;

static inline void rr_media_request_init(RrMediaRequest *q, uint32_t quiet, uint32_t still)
{
    memset(q, 0, sizeof *q);
    q->quiet = quiet;
    q->still = still;
    q->last_command = UINT64_MAX;
}

/* The drive commands of frame `frame`: `count` of them, `identity_only` when they were exactly one identity read. */
static inline void rr_media_command(RrMediaRequest *q, uint64_t frame, uint32_t count, int identity_only)
{
    if (!count)
        return;
    int alone_before = q->last_command == UINT64_MAX || frame - q->last_command >= q->quiet;
    q->pending = (count == 1 && identity_only && alone_before && q->still_frames >= q->still) ? frame + 1 : 0;
    q->last_command = frame;
}

/* At frame `frame`'s boundary, with its picture's hash: 1 when the next medium is to go in now. */
static inline int rr_media_frame(RrMediaRequest *q, uint64_t frame, uint32_t picture)
{
    if (q->have_picture && picture == q->picture) {
        if (q->still_frames < UINT32_MAX) ++q->still_frames;
    } else {
        q->still_frames = 0;
        q->picture = picture;
        q->have_picture = 1;
    }
    if (q->pending && frame >= q->pending - 1 + q->quiet) {
        q->pending = 0;
        ++q->answered;
        return 1;
    }
    return 0;
}
