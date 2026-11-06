/* Retro-Recomp Atari ST session: one game (its floppy images) running on Hatari, driven frame by frame. Original Retro-Recomp
 * code, MIT; it is linked with Hatari (GPL-2.0, licenses/hatari.md), so a program built with it is distributed under the GPL.
 *
 * A C interface over Hatari's libretro core, so that the player (with the host kit) and the conversion's tools share one session:
 * the reference run, the native run and the windowed game all go through these functions. The session is the libretro frontend:
 * it answers Hatari's environment calls itself and serves the TOS image and the floppy images from memory through a libretro
 * virtual file system, so no game or firmware byte is written to a file and nothing of the host (configuration, clock) leaks into
 * the machine. Hatari keeps its state in globals: there is one session per process. */
#ifndef RR_ATARIST_SESSION_H
#define RR_ATARIST_SESSION_H
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RR_ST_MAX_DISKS 8
#define RR_ST_PICTURE_MAX_WIDTH 832
#define RR_ST_PICTURE_MAX_HEIGHT 620

/* Joystick bits of a port. */
enum { RR_ST_JOY_UP = 1, RR_ST_JOY_DOWN = 2, RR_ST_JOY_LEFT = 4, RR_ST_JOY_RIGHT = 8, RR_ST_JOY_FIRE = 16 };

typedef struct RrStDisk { const char *name; const uint8_t *data; uint32_t size; } RrStDisk;   /* name: its extension tells the format */

typedef struct RrStGame {
    const RrStDisk *disks; unsigned disk_count;   /* in order; disk 0 is in drive A at start */
    const uint8_t *tos; uint32_t tos_size;         /* the TOS image the machine boots (the player's own, or EmuTOS) */
    const char *machine;                           /* "st", "megast" or "ste" */
    unsigned memory_kb;                            /* ST RAM: 512, 1024, 2048 or 4096 */
    void (*log)(const char *line);                 /* Hatari's messages, for diagnostics; NULL: quiet */
} RrStGame;

typedef struct RrStSession RrStSession;

/* Opens the machine with its first disk in drive A. NULL with a reason in `error` when it cannot run. */
RrStSession *rr_st_open(const RrStGame *game, char *error, size_t error_size);

/* Inputs of the next frame: a joystick (port 0 is the mouse port, port 1 the joystick port), the mouse (relative motion), a key
 * (a libretro key code, pressed or released). */
void rr_st_joystick(RrStSession *s, unsigned port, unsigned bits);
void rr_st_mouse(RrStSession *s, int dx, int dy, int left, int right);
void rr_st_key(RrStSession *s, unsigned retrok, int down);

/* Changes the disk in drive A (index into the game's disks). 0: done. */
int rr_st_insert_disk(RrStSession *s, unsigned index);
unsigned rr_st_disk_index(const RrStSession *s);
unsigned rr_st_disk_count(const RrStSession *s);

/* The 68000 instructions the machine ran on Hatari's interpreter (every instruction of a build without native steps) and the
 * observation of the instructions run from RAM, the TOS ROM or the cartridge area: lines "pc words" (the instruction's own bytes). */
uint64_t rr_st_interpreted_count(const RrStSession *s);
uint64_t rr_st_native_count(const RrStSession *s);
void rr_st_set_observe(RrStSession *s, int enabled);
/* Native steps (only in a build with RR_ST_NATIVE): 1 when the request is honoured (a build without steps honours only "off"). */
int rr_st_set_native(RrStSession *s, int enabled);
/* The opcode -> handler table of Hatari's cycle-exact 68000 (the conversion's step generator reads it); 1: written. */
int rr_st_write_opcode_map(const RrStSession *s, FILE *out);
int rr_st_write_observations(const RrStSession *s, FILE *out);   /* 1: written */
size_t rr_st_observation_count(const RrStSession *s);

/* Runs one frame (one VBL of the machine). 0: the frame ran; -1: the machine stopped (rr_st_error). */
int rr_st_frame(RrStSession *s);
const char *rr_st_error(const RrStSession *s);

/* The picture of the last frame, 0x00RRGGBB, `stride` pixels per row. */
const uint32_t *rr_st_picture(const RrStSession *s, int *width, int *height, int *stride);
/* The video rate of the machine now (50, 60 or 71 Hz, from the GLUE's sync mode). */
int rr_st_refresh_rate(const RrStSession *s);
/* The sound of the last frame: interleaved stereo int16 at rr_st_audio_rate; returns frames copied. */
size_t rr_st_audio(RrStSession *s, int16_t *pcm, size_t capacity_frames);
unsigned rr_st_audio_rate(const RrStSession *s);

/* Evidence of the last frame for the trace (deterministic: no clock, no host state). */
typedef struct RrStFrameInfo {
    uint64_t frame, video, pcm, ram;   /* FNV-1a 64 of the picture, of this frame's samples, of the ST RAM */
    uint32_t pc, sr, d[8], a[8];
    uint32_t samples;                  /* stereo frames of sound this frame */
    int nonblack, audible;
} RrStFrameInfo;
void rr_st_frame_info(const RrStSession *s, RrStFrameInfo *info);
/* The ST RAM (for development dumps). */
const uint8_t *rr_st_ram(const RrStSession *s, size_t *size);

/* Quick states (F8/F9): the whole machine, with the session's frame and disk, in memory (the caller writes the file); refused
 * between builds (`abi`). capture: 0 done (*out malloc'd), 4 failed. restore: 0 done; 2 another build or game; 3 invalid. */
int rr_st_state_capture(RrStSession *s, const char *abi, uint8_t **out, size_t *size);
int rr_st_state_restore(RrStSession *s, const char *abi, const uint8_t *data, size_t size);

/* The machine's log (Hatari's messages), for the conversion's diagnostics: NULL to keep it quiet. */
void rr_st_set_log(RrStSession *s, void (*log)(const char *line));

#ifdef __cplusplus
}
#endif
#endif
