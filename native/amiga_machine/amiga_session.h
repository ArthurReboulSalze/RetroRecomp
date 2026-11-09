/* Retro-Recomp Amiga session: one WHDLoad install running on vAmiga's Core, without WHDLoad and without a Kickstart.
 * Original Retro-Recomp code, MIT. The machine it drives (vAmiga Core) is MPL-2.0 (licenses/vamiga.md).
 *
 * A C interface over the C++ machine, so that the player (C, with the host kit) and the conversion's tools share one
 * session: the reference run, the native run and the windowed game all go through these functions. The host drives the
 * machine frame by frame (no emulator thread) and answers the slave's resload calls itself (native/amiga_whdload). */
#ifndef RR_AMIGA_SESSION_H
#define RR_AMIGA_SESSION_H
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* The picture handed to the player: hires pixels (two texels of vAmiga's super-hires texture each), 352 lores pixels of
 * overscan wide, one row per line (the host shows each line twice as tall: its scanline filter needs the real lines).
 * PAL shows 280 lines, NTSC 236. */
#define RR_AMIGA_PICTURE_WIDTH 704
#define RR_AMIGA_PICTURE_LINES_PAL 280
#define RR_AMIGA_PICTURE_LINES_NTSC 236
#define RR_AMIGA_PICTURE_MAX_HEIGHT RR_AMIGA_PICTURE_LINES_PAL
#define RR_AMIGA_AUDIO_RATE 48000u

/* Joystick bits of port 2 (the game port). */
enum { RR_AMIGA_JOY_UP = 1, RR_AMIGA_JOY_DOWN = 2, RR_AMIGA_JOY_LEFT = 4, RR_AMIGA_JOY_RIGHT = 8, RR_AMIGA_JOY_FIRE = 16,
       RR_AMIGA_JOY_FIRE2 = 32 };

typedef struct RrAmigaFile { const char *name; const uint8_t *data; uint32_t size; } RrAmigaFile;

typedef struct RrAmigaGame {
    const uint8_t *slave; uint32_t slave_size;
    const RrAmigaFile *files; unsigned file_count;     /* the install's data files, names relative to its data folder */
    const char *save_dir;     /* UTF-8 folder where resload_SaveFile writes (and whose files replace the install's), NULL: none */
    int ntsc;
    /* The player's own Kickstart image (normalised, 256 KiB), for the installs that ask for one; NULL: none. The session copies
     * it to ExpMem when the slave's request (size, CRC-16) matches it; it is never written anywhere else. */
    const uint8_t *kickstart; uint32_t kickstart_size;
    /* CUSTOM1..5 as the install's own icon sets them (its ToolTypes), what resload_Control's CUSTOMn_GET answer. */
    uint32_t custom[5];
} RrAmigaGame;

typedef struct RrAmigaSession RrAmigaSession;

/* Opens the machine and enters the slave's ws_GameLoader. NULL with a reason in `error` when the install cannot run. */
RrAmigaSession *rr_amiga_open(const RrAmigaGame *game, char *error, size_t error_size);

/* Inputs of the next frame: the joystick of port 2, the mouse of port 1 (relative motion), the Amiga raw keys held. */
void rr_amiga_joystick(RrAmigaSession *s, unsigned bits);
void rr_amiga_mouse(RrAmigaSession *s, int dx, int dy, int left, int right);
void rr_amiga_keys(RrAmigaSession *s, const uint8_t held[128]);

/* Runs one frame (resload calls answered on the way). 0: the frame ran; -1: the install stopped (resload refused, Abort, or
 * the CPU left the resload table at a breakpoint); the reason is rr_amiga_error. */
int rr_amiga_frame(RrAmigaSession *s);
/* 1 when the install stopped because it ended itself normally (resload_Abort with TDREASON_OK), 0 for any other stop. */
int rr_amiga_quit(const RrAmigaSession *s);
uint64_t rr_amiga_kickstart_native_count(const RrAmigaSession *s);
const char *rr_amiga_error(const RrAmigaSession *s);

/* The picture of the last frame, 0xAARRGGBB, RR_AMIGA_PICTURE_WIDTH per row. */
const uint32_t *rr_amiga_picture(const RrAmigaSession *s, int *width, int *height);
/* The union of the display windows the game opened so far (DIWSTRT/DIWSTOP, from vAmiga's viewport tracking), in picture
 * columns and rows: what the player shows instead of the whole overscan picture. 0 while no window was opened. */
int rr_amiga_viewport(const RrAmigaSession *s, int *x, int *y, int *w, int *h);
/* The Kickstart the install runs with: 1 and its size and CRC-16 once loaded (slave header or resload_LoadKick), else 0. Its
 * instructions run on the interpreter (counted apart: rr_amiga_kickstart_interpreted_count, included in the total). */
int rr_amiga_kickstart(const RrAmigaSession *s, uint32_t *size, uint16_t *crc16);
uint64_t rr_amiga_kickstart_interpreted_count(const RrAmigaSession *s);
/* The sound of the last frame: interleaved stereo int16 at RR_AMIGA_AUDIO_RATE; returns frames copied. */
size_t rr_amiga_audio(RrAmigaSession *s, int16_t *pcm, size_t capacity_frames);

/* Evidence of the last frame for the trace (deterministic: no clock, no host state). */
typedef struct RrAmigaFrameInfo {
    uint64_t frame, video, pcm, ram;   /* FNV-1a 64 of the whole texture, of this frame's samples, of chip + slow + fast RAM */
    uint32_t pc, sr, d[8], a[8];
    uint32_t samples;                  /* stereo frames of sound this frame */
    int nonblack, audible;
} RrAmigaFrameInfo;
void rr_amiga_frame_info(const RrAmigaSession *s, RrAmigaFrameInfo *info);

/* Native steps (only in a build with RR_AMIGA_NATIVE) and the observation of executed RAM instructions. */
int rr_amiga_set_native(RrAmigaSession *s, int enabled);   /* 0: this build has no native steps */
void rr_amiga_set_observe(RrAmigaSession *s, int enabled);
int rr_amiga_write_observations(const RrAmigaSession *s, const char *path);   /* lines "pc words" (12 bytes) */
uint64_t rr_amiga_native_count(const RrAmigaSession *s);
/* Of those, the instructions whose form is translated C; the others are Moira's code specialised. */
uint64_t rr_amiga_translated_count(const RrAmigaSession *s);
uint64_t rr_amiga_interpreted_count(const RrAmigaSession *s);
long rr_amiga_resload_calls(const RrAmigaSession *s);
int rr_amiga_write_resload_log(const RrAmigaSession *s, const char *path);

/* Quick states (F8/F9): the whole machine, the resload state and the inputs; refused between builds (`abi`). 0: done;
 * 1: no state; 2: another build or game; 3: invalid; 4: input/output error. */
int rr_amiga_state_save(RrAmigaSession *s, const char *path, const char *abi);
int rr_amiga_state_load(RrAmigaSession *s, const char *path, const char *abi);

#ifdef __cplusplus
}
#endif
#endif
