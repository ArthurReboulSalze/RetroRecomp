/* Retro-Recomp Nintendo 64 session: one cartridge running on Mupen64Plus-Next, driven frame by frame. Original Retro-Recomp code,
 * MIT; it is linked with Mupen64Plus (GPL-2.0-or-later) and GNU Lightning (LGPL-3.0-or-later), so a program built with it is
 * distributed under the GPL-3.0 (licenses/mupen64plus-next.md).
 *
 * A C interface over the libretro core, shared by the conversion's headless runs and the windowed game: the session is the
 * libretro frontend. It answers the core's environment calls itself (fixed options, no file of the host is read), creates its
 * own Vulkan device through the core's context negotiation (no window and no surface: each finished frame is copied from the
 * renderer's image into host memory, the picture the host kit presents as a 2D frame), and keeps the picture, the sound, the
 * pads and the rumble of each frame. The core keeps its state in globals: there is one session per process. */
#ifndef RR_N64_SESSION_H
#define RR_N64_SESSION_H
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RR_N64_MAX_WIDTH 640        /* the console's picture (one field or two) fits in this */
#define RR_N64_MAX_HEIGHT 576
#define RR_N64_PICTURE_LIMIT 4096   /* with an internal resolution: up to this on each side */
#define RR_N64_RDRAM_BYTES (8u * 1024u * 1024u)

/* Pad bits of one player: libretro's joypad ids, which the core maps to the N64 pad (its own table): B = A button, Y = B button,
 * L2 = Z, R2 = R, Select = L, Start, the d-pad, and X/A/L/R = C-Up/C-Down/C-Left/C-Right. */
enum {
    RR_N64_PAD_A = 1 << 0,        /* RETRO_DEVICE_ID_JOYPAD_B */
    RR_N64_PAD_B = 1 << 1,        /* _Y */
    RR_N64_PAD_L = 1 << 2,        /* _SELECT */
    RR_N64_PAD_START = 1 << 3,
    RR_N64_PAD_UP = 1 << 4, RR_N64_PAD_DOWN = 1 << 5, RR_N64_PAD_LEFT = 1 << 6, RR_N64_PAD_RIGHT = 1 << 7,
    RR_N64_PAD_C_DOWN = 1 << 8,   /* _A */
    RR_N64_PAD_C_UP = 1 << 9,     /* _X */
    RR_N64_PAD_C_LEFT = 1 << 10,  /* _L */
    RR_N64_PAD_C_RIGHT = 1 << 11, /* _R */
    RR_N64_PAD_Z = 1 << 12,       /* _L2 */
    RR_N64_PAD_R = 1 << 13        /* _R2 */
};

/* How the VR4300 runs: the core's cached interpreter (a game without native blocks), the pure interpreter observed (the
 * conversion's observation run), native blocks first (a game with blocks; the pure interpreter runs the rest). Every mode
 * counts the instructions its interpreter runs. */
enum { RR_N64_CPU_CACHED = 0, RR_N64_CPU_OBSERVE = 1, RR_N64_CPU_NATIVE = 2, RR_N64_CPU_PURE = 3 };

typedef struct RrN64Game {
    const uint8_t *rom; size_t rom_size;  /* the cartridge image, big-endian (the session copies nothing to a file) */
    int cpu;                              /* RR_N64_CPU_* */
    const char *gpu;                      /* a part of the Vulkan device's name to prefer; NULL: the first discrete GPU */
    int evidence;                         /* 1: each frame waits for the GPU before RDRAM is hashed (headless checks) */
    int threaded_rdp;                     /* 1: parallel-rdp records on its worker thread (faster, not deterministic) */
    const char *pak;                      /* controller pak of every pad: "memory" (default), "rumble", "none" */
    void (*log)(const char *line);        /* the core's warnings, for diagnostics; NULL: quiet */
} RrN64Game;

typedef struct RrN64Session RrN64Session;

/* Opens the machine. NULL with a reason in `error` when it cannot run (no Vulkan 1.1 device, an image the core refuses). */
RrN64Session *rr_n64_open(const RrN64Game *game, char *error, size_t error_size);

/* Inputs of the next frame: the pad bits and the sticks (-32768..32767: left X, left Y, right X, right Y; the right stick is the C
 * buttons) of a player (0..3). */
void rr_n64_pad(RrN64Session *s, int player, unsigned bits, const int16_t sticks[4]);

/* Runs one frame (one vertical interrupt of the console). 0: done; -1: the machine stopped (rr_n64_error). */
int rr_n64_frame(RrN64Session *s);
/* Frames run since the machine started (a loaded state brings its own). */
uint64_t rr_n64_frame_index(const RrN64Session *s);
const char *rr_n64_error(const RrN64Session *s);

/* The picture of the last frame, 0x00RRGGBB, `width` pixels per row (it grows with the internal resolution). */
const uint32_t *rr_n64_picture(const RrN64Session *s, int *width, int *height);
/* The display aspect the core reports (4:3 on a television). */
double rr_n64_aspect(const RrN64Session *s);
/* The sound of the last frame: interleaved stereo int16 at rr_n64_audio_rate; returns stereo frames copied. */
size_t rr_n64_audio(RrN64Session *s, int16_t *pcm, size_t capacity_frames);
unsigned rr_n64_audio_rate(const RrN64Session *s);
double rr_n64_fps(const RrN64Session *s);
/* The rumble of a player's pak now (0..65535 per motor); 1 when it runs. */
int rr_n64_rumble(const RrN64Session *s, int player, uint16_t *strong, uint16_t *weak);

/* A core option (Mupen64Plus-Next's key without its "mupen64plus-" prefix, its value as the core names it), applied before the
 * next frame; an option of the renderer that needs a new renderer (the internal resolution) gets one after that frame. 1: known. */
int rr_n64_option(RrN64Session *s, const char *key, const char *value);

/* Evidence of the last frame for the trace (deterministic with `evidence`: no clock, no host state). */
typedef struct RrN64FrameInfo {
    uint64_t frame, video, pcm, ram, cpu;   /* FNV-1a 64 of the picture, this frame's samples, RDRAM, the CPU registers */
    uint32_t pc, samples;                   /* the PC after the frame; stereo frames of sound this frame */
    int width, height, nonblack, audible;
} RrN64FrameInfo;
void rr_n64_frame_info(const RrN64Session *s, RrN64FrameInfo *info);
const uint8_t *rr_n64_rdram(const RrN64Session *s, size_t *size);

/* The cartridge's saves and the controller paks as one block (EEPROM, SRAM, Flash, four memory paks), as the core keeps them;
 * the caller loads it before the first frame and writes it when it changed. */
uint8_t *rr_n64_save_memory(RrN64Session *s, size_t *size);

/* VR4300 instructions run by the interpreters (the counted fallback) and by native blocks; block entries and guard misses. */
uint64_t rr_n64_interpreted_count(const RrN64Session *s);
uint64_t rr_n64_native_count(const RrN64Session *s);
uint64_t rr_n64_block_entry_count(const RrN64Session *s);
uint64_t rr_n64_guard_miss_count(const RrN64Session *s);
/* The observation (RR_N64_CPU_OBSERVE): lines "pc count len word..." per (address, code identity). 1: written. */
int rr_n64_observations_write(const RrN64Session *s, void *file);
size_t rr_n64_observed_count(const RrN64Session *s);
/* The Vulkan device the renderer runs on (its name), for the report. */
const char *rr_n64_gpu_name(const RrN64Session *s);

/* Quick states (F8/F9): the whole machine and the session's frame, in memory (the caller writes the file); refused between
 * builds (`abi`). capture: 0 done (*out malloc'd), 4 failed. restore: 0 done; 2 another build; 3 invalid. */
int rr_n64_state_capture(RrN64Session *s, const char *abi, uint8_t **out, size_t *size);
int rr_n64_state_restore(RrN64Session *s, const char *abi, const uint8_t *data, size_t size);

#ifdef __cplusplus
}
#endif
#endif
