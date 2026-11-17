/* Retro-Recomp PlayStation session: one disc running on the Beetle PSX machine, driven frame by frame.
 * Original Retro-Recomp code, MIT. The machine it drives (Beetle PSX, derived from Mednafen) is GPL-2.0, so a program linking
 * this file with it is GPL-2.0 as a whole (licenses/beetle-psx.md).
 *
 * A small C interface over the libretro core, shared by the reference tool of the conversion and the game the player runs: the
 * session answers the core's environment calls itself, serves the disc from a pack (the files of the player's disc, appended to
 * the game or named by a pack file) through the core's virtual file system, hands it the player's BIOS from memory, and keeps
 * the picture, the sound and the inputs of each frame. Beetle keeps its state in globals, so there is one session per process. */
#ifndef RR_PSX_SESSION_H
#define RR_PSX_SESSION_H
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RR_PSX_BIOS_BYTES (512u * 1024u)
#define RR_PSX_RAM_BYTES (2u * 1024u * 1024u)
#define RR_PSX_AUDIO_RATE 44100u
#define RR_PSX_MAX_WIDTH 1024     /* the picture at the console's resolution fits in this */
#define RR_PSX_MAX_HEIGHT 576
#define RR_PSX_PICTURE_LIMIT 8192 /* a larger internal resolution: the picture grows up to this on each side (8x on the card) */

/* Pad bits of one player (the order of the PlayStation pad, libretro's joypad ids). */
enum {
    RR_PSX_PAD_B = 1 << 0, RR_PSX_PAD_Y = 1 << 1, RR_PSX_PAD_SELECT = 1 << 2, RR_PSX_PAD_START = 1 << 3,
    RR_PSX_PAD_UP = 1 << 4, RR_PSX_PAD_DOWN = 1 << 5, RR_PSX_PAD_LEFT = 1 << 6, RR_PSX_PAD_RIGHT = 1 << 7,
    RR_PSX_PAD_A = 1 << 8, RR_PSX_PAD_X = 1 << 9, RR_PSX_PAD_L = 1 << 10, RR_PSX_PAD_R = 1 << 11,
    RR_PSX_PAD_L2 = 1 << 12, RR_PSX_PAD_R2 = 1 << 13, RR_PSX_PAD_L3 = 1 << 14, RR_PSX_PAD_R3 = 1 << 15
};
/* B = Cross, A = Circle, Y = Square, X = Triangle (libretro's names for the PlayStation buttons). */

typedef struct RrPsxGame {
    const char *pack;           /* UTF-8 path of the pack: the game's own executable, or a pack file of the conversion */
    const uint8_t *bios;        /* the player's BIOS (RR_PSX_BIOS_BYTES), NULL: OpenBIOS, built into the core */
    const char *save_dir;       /* UTF-8 folder of the memory card, NULL: no card is written */
    int disc;                   /* the disc to start with (0-based) */
    int vulkan;                 /* 1.7.7: 1 the graphics card draws (Beetle's Vulkan renderer), 0 the CPU (its software renderer) */
    const char (*options)[2][64];   /* 1.7.7: core options (full key, value) set before the game loads (a session opened again), or NULL */
    int option_count;
} RrPsxGame;

typedef struct RrPsxSession RrPsxSession;

/* Opens the machine with the pack's first disc (or `disc`). NULL with a reason in `error`. With `vulkan`, a graphics card that cannot
 * be used (no Vulkan loader, no device, a device the renderer cannot run on) is never an error: the machine opens with the CPU
 * renderer and rr_psx_renderer_note says why. */
RrPsxSession *rr_psx_open(const RrPsxGame *game, char *error, size_t error_size);
void rr_psx_close(RrPsxSession *s);

/* The renderer drawing: 1 the graphics card (Vulkan), 0 the CPU. Why the card was asked for and not used, or NULL. The card's
 * name, or "" without the card. */
int rr_psx_renderer(const RrPsxSession *s);
/* The picture `pixels` (w x h, `pitch` pixels a row) copied into the session as its last picture, shown until its next frame
 * (a renderer switch: the session opened again has drawn nothing yet). */
void rr_psx_keep_picture(RrPsxSession *s, const uint32_t *pixels, int w, int h, int pitch);
const char *rr_psx_renderer_note(const RrPsxSession *s);
const char *rr_psx_gpu_name(const RrPsxSession *s);

/* Inputs of the next frame: the pad bits and the two sticks (-32768..32767) of a player (0 or 1). */
void rr_psx_pad(RrPsxSession *s, int player, unsigned bits, const int16_t sticks[4]);

/* The DualShock's Analog button of a player, held or not (it switches the pad between digital and analog mode). */
void rr_psx_analog_button(RrPsxSession *s, int player, int held);
/* The input check: the PlayStation button bits (Select 0 ... Square 15, the Analog button 16) the console reads for these pad
 * bits, without running a frame (the pad's own inputs are put back). */
uint32_t rr_psx_pad_probe(RrPsxSession *s, int player, unsigned bits, int analog);
/* The mode of a player's DualShock: 1 analog, 0 digital, -1 another device. */
int rr_psx_pad_analog_mode(const RrPsxSession *s, int player);

/* Runs one frame. 0: done; -1: the machine stopped (reason in rr_psx_error). */
int rr_psx_frame(RrPsxSession *s);
const char *rr_psx_error(const RrPsxSession *s);

/* The picture of the last frame, 0x00RRGGBB, `width` x `height` pixels, rows rr_psx_picture_pitch apart; the display aspect
 * the core reports. Valid until the next frame. */
const uint32_t *rr_psx_picture(const RrPsxSession *s, int *width, int *height, double *aspect);
/* The pixels between two rows of the picture (it is the core's own frame surface, not a copy). */
int rr_psx_picture_pitch(const RrPsxSession *s);
/* The sound of the last frame: interleaved stereo int16 at RR_PSX_AUDIO_RATE; returns stereo frames copied. */
size_t rr_psx_audio(RrPsxSession *s, int16_t *pcm, size_t capacity_frames);
double rr_psx_fps(const RrPsxSession *s);
int rr_psx_rumble(const RrPsxSession *s, int player, uint16_t *low, uint16_t *high);

/* Disc change of a multi-disc game: number of discs, the one in the drive, and a request to change it (the lid is opened, the
 * disc swapped and the lid closed by the session over the following frames). */
int rr_psx_disc_count(const RrPsxSession *s);
int rr_psx_disc_current(const RrPsxSession *s);
int rr_psx_disc_select(RrPsxSession *s, int index);

/* A core option (Beetle's key without its prefix, its value as the core names it), applied before the next frame. */
int rr_psx_option(RrPsxSession *s, const char *key, const char *value);
/* The session's core options (full key and value), for a session opened again with them: the count, and each pair. */
/* 1.7.7: 1 the card's frames are reduced by two (each pixel the mean of a 2x2 block) as they are read back: Supersampling, the card
 * drawing at twice the internal resolution chosen. The machine is untouched; the CPU renderer's frames never are. */
void rr_psx_set_halve(RrPsxSession *s, int halve);
int rr_psx_option_count(const RrPsxSession *s);
void rr_psx_option_at(const RrPsxSession *s, int index, char key[64], char value[64]);

/* Evidence of the last frame for the trace (deterministic: no clock, no host state). */
typedef struct RrPsxFrameInfo {
    uint64_t frame, video, pcm, ram;   /* FNV-1a 64 of the picture, of this frame's samples, of the 2 MiB of RAM */
    uint64_t cpu;                      /* FNV-1a 64 of the CPU state a game sees: the R3000A's registers, HI, LO, PC, the
                                        * pending load, SR, CAUSE, EPC, and the GTE's 64 registers */
    uint32_t samples;                  /* stereo frames of sound this frame */
    int width, height, nonblack, audible;
    uint64_t vram;                     /* FNV-1a 64 of the core's VRAM (1024 x 512 halfwords at 1x, the software renderer's own
                                        * copy; larger at a raised resolution of the software renderer): what the console drew,
                                        * whichever renderer shows it (1.7.7) */
} RrPsxFrameInfo;
void rr_psx_frame_info(const RrPsxSession *s, RrPsxFrameInfo *info);
/* Multiplayer: the deterministic state after the last frame (CPU and GTE, RAM, scratchpad, sound RAM, memory card), in a fixed
 * byte order, the same on every seat and system. */
uint64_t rr_psx_digest(const RrPsxSession *s);

/* The memory card of slot 1 (128 KiB), as the core keeps it; NULL when the core has none. */
uint8_t *rr_psx_card(RrPsxSession *s, size_t *size);

/* R3000A instructions run since the program started: by the core's interpreter (the counted fallback), and by the game's
 * native steps (none in a game built without them). */
uint64_t rr_psx_interpreted(const RrPsxSession *s);
uint64_t rr_psx_native(const RrPsxSession *s);
/* Instruction fetches that ran no instruction (an interrupt taken, or the CPU held by a DMA): neither of the two above. */
uint64_t rr_psx_unrun(const RrPsxSession *s);

/* The whole machine as bytes (quick states of the host kit): malloc'ed, NULL on failure; restore returns 0 on success. */
uint8_t *rr_psx_state_capture(RrPsxSession *s, size_t *size);
int rr_psx_state_restore(RrPsxSession *s, const uint8_t *data, size_t size);

/* Quick states (F8/F9): the whole machine; refused between builds (`abi`). 0: done; 1: no state; 2: another build or game;
 * 3: invalid; 4: input/output error. */
int rr_psx_state_save(RrPsxSession *s, const char *path, const char *abi);
int rr_psx_state_load(RrPsxSession *s, const char *path, const char *abi);

#ifdef __cplusplus
}
#endif
#endif
