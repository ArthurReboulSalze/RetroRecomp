/* PC Engine machine: the C interface of the bridge to the pinned pcenginerecomp runtime (pce_machine.cpp).
 * Original RetroRecomp code: MIT. The engine keeps its own MIT terms (licenses/pcenginerecomp.md). */
#ifndef RR_PCE_MACHINE_H
#define RR_PCE_MACHINE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* The largest picture the bridge hands out; wider or taller frames are cropped and counted. */
#define PCE_MAX_WIDTH 640
#define PCE_MAX_HEIGHT 264
#define PCE_PADS 5
#define PCE_AUDIO_RATE 44100u   /* the engine's raw PSG profile (48 kHz needs its filtered one) */

enum { PCE_BOARD_BASE = 0, PCE_BOARD_SF2 = 1 };
enum { PCE_POLICY_HYBRID = 0, PCE_POLICY_REFERENCE = 1, PCE_POLICY_NATIVE_ONLY = 2 };

typedef struct {
    uint64_t native, interpreted, guard_misses, irq_entries, frames, cropped_frames;
} PceCounters;

/* The pad masks are the engine's: I, II, Select, Run, Up, Right, Down, Left, III, IV, V, VI (bits 0-11). */
int pce_machine_init(const uint8_t *file, size_t size, int copier_header, int bit_reversed, int board,
                     int pad_buttons, int multitap, char *error, size_t error_size);
int pce_machine_reset(char *error, size_t error_size);
void pce_machine_policy(int policy);
void pce_machine_set_pads(const uint16_t masks[PCE_PADS]);
/* One guest frame: runs until the next picture is published. 0 on an engine fault (the text in error). */
int pce_machine_run_frame(char *error, size_t error_size);
/* ARGB8888, stride PCE_MAX_WIDTH; the visible part is width x height at the top left. */
const uint32_t *pce_machine_pixels(unsigned *width, unsigned *height);
unsigned pce_machine_dot_clock(void);
/* Interleaved stereo int16 at PCE_AUDIO_RATE produced since the last call; returns values (frames x 2). */
size_t pce_machine_audio(int16_t *out, size_t capacity);
void pce_machine_counters(PceCounters *counters);
uint64_t pce_machine_cpu_hash(void);
uint64_t pce_machine_ram_hash(void);
/* Quick states: the engine's versioned in-memory checkpoint, bound by the caller to this exact executable. */
uint8_t *pce_machine_state_save(size_t *size);
int pce_machine_state_load(const uint8_t *data, size_t size);
void pce_machine_free(void *data);
/* Code observation for the converter (the engine's own capture JSON), off by default. */
int pce_machine_capture_begin(const char *path, unsigned capacity, char *error, size_t error_size);
int pce_machine_capture_finish(char *error, size_t error_size);
void pce_machine_shutdown(void);

#ifdef __cplusplus
}
#endif
#endif
