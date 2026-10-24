/* CPS-1 adapter for the shared 16-bit menu/presentation host, and its quick
 * states. Original RetroRecomp code: MIT. */
#include <SDL.h>
#include <stdlib.h>
#include <string.h>
#include "retro_console16.h"
#include "console16_state.h"
#include "cps1_machine.h"

extern uint64_t rr_cps1_native_instructions, rr_cps1_interpreted_68k;
extern uint64_t rr_cps1_native_z80, rr_cps1_interpreted_z80;

static SDL_AudioStream *resampler;
static uint32_t pixels[RR16_WIDTH * RR16_HEIGHT];
static const RrCps1Input inputs[] = {RR_CPS1_INPUT_TABLE};

static uint16_t extra_pads[2];
static const RrCps1Dip dips[] = {RR_CPS1_DIP_TABLE};
static uint16_t dip_values[3];
static bool dip_override;

int rr_cps1_rotated(void) { return RR_CPS1_ROTATION == 270; }

/* ------------------------------------------------------------ DIP switches */

int rr_cps1_dip_count(void) { return RR_CPS1_DIP_COUNT; }
const RrCps1Dip *rr_cps1_dip(int index) { return index >= 0 && index < RR_CPS1_DIP_COUNT ? &dips[index] : NULL; }
void rr_cps1_dip_values(uint16_t values[3])
{
    for (int i = 0; i < 3; i++) values[i] = dip_override ? dip_values[i] : cps1_port_default(CPS1_DSWA + i);
}
static void apply_dips(void)
{
    if (dip_override) for (int i = 0; i < 3; i++) cps1_set_port(CPS1_DSWA + i, dip_values[i]);
}
void rr_cps1_set_dip_values(const uint16_t values[3])
{
    memcpy(dip_values, values, sizeof dip_values);
    dip_override = true;
    apply_dips();
}
bool rr_cps1_dip_visible(int index)
{
    const RrCps1Dip *dip = rr_cps1_dip(index);
    if (!dip) return false;
    if (dip->condition_port < 0) return true;
    uint16_t values[3];
    rr_cps1_dip_values(values);
    return ((values[dip->condition_port] & dip->condition_mask) == dip->condition_value) == (dip->condition_equals != 0);
}
int rr_cps1_dip_setting(int index)
{
    const RrCps1Dip *dip = rr_cps1_dip(index);
    uint16_t values[3];
    rr_cps1_dip_values(values);
    for (int k = 0; dip && k < dip->count; k++)
        if ((values[dip->port] & dip->mask) == dip->values[k]) return k;
    return -1;
}
void rr_cps1_dip_cycle(int index, int step)
{
    const RrCps1Dip *dip = rr_cps1_dip(index);
    if (!dip) return;
    int current = rr_cps1_dip_setting(index);
    int next = current < 0 ? 0 : (current + step + dip->count) % dip->count;
    uint16_t values[3];
    rr_cps1_dip_values(values);
    values[dip->port] = (uint16_t)((values[dip->port] & ~dip->mask) | dip->values[next]);
    rr_cps1_set_dip_values(values);
}

void rr_cps1_set_extra_pads(uint16_t p3, uint16_t p4) { extra_pads[0] = p3; extra_pads[1] = p4; }

/* Ports are active low: a pressed control clears its bit. */
void rr_cps1_apply_pads(uint16_t p1, uint16_t p2)
{
    const uint16_t pads[4] = {p1, p2, extra_pads[0], extra_pads[1]};
    uint16_t ports[4];
    for (int i = 0; i < 4; i++) ports[i] = cps1_port_default(CPS1_IN0 + i);
    for (size_t i = 0; i < sizeof inputs / sizeof *inputs; i++) {
        uint16_t pad = inputs[i].player >= 1 && inputs[i].player <= 4 ? pads[inputs[i].player - 1] : 0;
        if (pad & (1u << inputs[i].action)) ports[inputs[i].port] &= (uint16_t)~inputs[i].mask;
    }
    for (int i = 0; i < 4; i++) cps1_set_port(CPS1_IN0 + i, ports[i]);
}

bool rr16_init(bool headless) { (void)headless; return true; }
void rr16_reset(void)
{
    rr_cps1_reset_machine();
    apply_dips();
    if (resampler) SDL_AudioStreamClear(resampler);
    rr16_host_discontinuity();
}
bool rr16_frame(uint16_t p1, uint16_t p2) { rr_cps1_host_frame(p1, p2); return true; }

/* ROT270 boards drive a monitor turned a quarter counter-clockwise. */
const uint32_t *rr16_pixels(void)
{
    const uint32_t *src = cps1_framebuffer();
    if (!rr_cps1_rotated()) {
        for (unsigned n = 0; n < CPS1_SCREEN_W * CPS1_SCREEN_H; n++) pixels[n] = src[n] | 0xff000000u;
        return pixels;
    }
    for (int y = 0; y < CPS1_SCREEN_H; y++)
        for (int x = 0; x < CPS1_SCREEN_W; x++)
            pixels[(CPS1_SCREEN_W - 1 - x) * RR16_WIDTH + y] = src[y * CPS1_SCREEN_W + x] | 0xff000000u;
    return pixels;
}
int rr16_visible_width(void) { return rr_cps1_rotated() ? CPS1_SCREEN_H : CPS1_SCREEN_W; }
int rr16_visible_height(void) { return rr_cps1_rotated() ? CPS1_SCREEN_W : CPS1_SCREEN_H; }
int rr16_raster_height(void) { return rr16_visible_height(); }
/* The board's 384x224 raster fills a 4:3 monitor; its pixels are not square. */
int rr_cps1_display_width(void) { return rr_cps1_rotated() ? CPS1_SCREEN_W * 3 / 4 : (CPS1_SCREEN_H * 4 + 1) / 3; }

uint64_t rr16_interpreted(void) { return rr_cps1_interpreted_68k; }
uint64_t rr16_native_entries(void) { return rr_cps1_native_instructions; }
uint64_t rr16_audio_interpreted(void) { return rr_cps1_interpreted_z80; }
const char *rr16_audio_cpu(void) { return "Z80"; }
uint64_t rr16_audio_fingerprint(void) { return cps1_cpu_hash(); }
uint64_t rr16_audio_frame_fingerprint(void) { return cps1_cpu_hash(); }

/* Mono board output at 3.579545 MHz / 64, duplicated to stereo for SDL. */
size_t rr16_audio(int16_t *out, size_t capacity)
{
    size_t count = 0;
    const int16_t *mono = rr_cps1_take_audio(&count);
    if (!resampler) resampler = SDL_NewAudioStream(AUDIO_S16SYS, 2, CPS1_AUDIO_RATE, AUDIO_S16SYS, 2, 48000);
    if (!resampler) return 0;
    int16_t stereo[1024];
    for (size_t done = 0; done < count;) {
        size_t n = count - done > 512 ? 512 : count - done;
        for (size_t i = 0; i < n; i++) stereo[2 * i] = stereo[2 * i + 1] = mono[done + i];
        if (SDL_AudioStreamPut(resampler, stereo, (int)(n * 4))) return 0;
        done += n;
    }
    int bytes = SDL_AudioStreamGet(resampler, out, (int)(capacity * 2));
    return bytes > 0 ? (size_t)bytes / 2 : 0;
}
void rr16_pause(bool paused) { if (paused && resampler) SDL_AudioStreamClear(resampler); }
void rr16_shutdown(void) { if (resampler) SDL_FreeAudioStream(resampler); resampler = NULL; }
void rr16_gun_input(Rr16GunInput input) { (void)input; }
uint64_t rr16_input_frame(void) { return rr_cps1_frame_index(); }
void rr16_report_details(FILE *file) { (void)file; }
void rr16_trace_details(FILE *file) { (void)file; }

/* ------------------------------------------------------------ quick states */

enum { STATE_HEADER = 16 };
static void put32(uint8_t *p, uint32_t v) { for (unsigned n = 0; n < 4; n++) p[n] = (uint8_t)(v >> (8 * n)); }
static uint32_t get32(const uint8_t *p) { uint32_t v = 0; for (unsigned n = 0; n < 4; n++) v |= (uint32_t)p[n] << (8 * n); return v; }

/* Frames end after a whole VBLANK, with both CPUs between instructions. */
bool rr16_state_ready(void) { return true; }
uint8_t *rr16_state_capture(size_t *size)
{
    size_t machine = cps1_state_save(NULL, 0);
    if (!size || !machine || machine > (16u << 20)) return NULL;
    uint8_t *data = malloc(STATE_HEADER + machine);
    if (!data) return NULL;
    memcpy(data, "RCPS1ST1", 8);
    put32(data + 8, rr_cps1_frame_index());
    put32(data + 12, (uint32_t)machine);
    if (cps1_state_save(data + STATE_HEADER, machine) != machine) { free(data); return NULL; }
    *size = STATE_HEADER + machine;
    return data;
}
bool rr16_state_restore(const uint8_t *data, size_t size)
{
    if (!data || size < STATE_HEADER || memcmp(data, "RCPS1ST1", 8) || get32(data + 12) != size - STATE_HEADER)
        return false;
    if (!cps1_state_load(data + STATE_HEADER, size - STATE_HEADER)) return false;
    apply_dips();                               /* the switches shown in F2 */
    rr_cps1_restore_frame(get32(data + 8));
    if (resampler) SDL_AudioStreamClear(resampler);
    rr16_host_discontinuity();
    return true;
}
