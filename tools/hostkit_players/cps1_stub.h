/* The stub CPS-1 machine the host kit's player checks run around (checks.c, hotplug.c): what the CPS-1 adapter calls,
 * with no game. Included once by each check program. Original RetroRecomp code: MIT. */
#ifndef RRHK_PLAYERS_CPS1_STUB_H
#define RRHK_PLAYERS_CPS1_STUB_H

static uint32_t pixels[RR16_WIDTH * RR16_HEIGHT];
static uint64_t frames;
static int resets, extra_calls;
static uint16_t extra[2];

/* ---- the stub machine: what the CPS-1 adapter calls ---- */
void rr_cps1_set_extra_pads(uint16_t p3, uint16_t p4) { extra[0] = p3; extra[1] = p4; ++extra_calls; }
int rr_cps1_display_width(void) { return 384; }
int rr_cps1_dip_count(void) { return 0; }
const RrCps1Dip *rr_cps1_dip(int index) { (void)index; return NULL; }
bool rr_cps1_dip_visible(int index) { (void)index; return false; }
int rr_cps1_dip_setting(int index) { (void)index; return -1; }
void rr_cps1_dip_values(uint16_t values[3]) { values[0] = values[1] = values[2] = 0xffff; }
void rr_cps1_set_dip_values(const uint16_t values[3]) { (void)values; }
void rr_cps1_dip_cycle(int index, int step) { (void)index; (void)step; }
/* The CPS boards' multiplayer hooks (rollback, digest, side effects, the CPS-2 name): no session runs here. */
int cps1_is_cps2(void) { return 0; }
size_t rr_cps1_snap_bound(void) { return 0; }
size_t rr_cps1_snap_save(void *buffer, size_t capacity) { (void)buffer; (void)capacity; return 0; }
bool rr_cps1_snap_load(const void *buffer, size_t size) { (void)buffer; (void)size; return false; }
uint64_t rr_cps1_digest(void) { return 0; }
void rr_cps1_side_effects(bool allowed) { (void)allowed; }
size_t rr_cps1_session_save(void *out, size_t capacity) { (void)out; (void)capacity; return 0; }
bool rr_cps1_session_save_put(const void *in, size_t size) { (void)in; (void)size; return false; }
bool rr_cps1_session_save_commit(void) { return false; }
size_t cps1_eeprom_size(void) { return 0; }
void rr16_reset(void) { ++resets; }
void rr16_pause(bool paused) { (void)paused; }
const uint32_t *rr16_pixels(void) { return pixels; }
int rr16_visible_width(void) { return 384; }
int rr16_visible_height(void) { return 224; }
int rr16_raster_height(void) { return 224; }
size_t rr16_audio(int16_t *pcm, size_t capacity) { (void)pcm; (void)capacity; return 0; }
uint64_t rr16_interpreted(void) { return 0; }
uint64_t rr16_audio_interpreted(void) { return 0; }
bool rr16_state_path(wchar_t *path, size_t capacity) { (void)path; (void)capacity; return false; }
bool rr16_state_ready(void) { return true; }
bool rr16_state_file(const wchar_t *path, bool load) { (void)path; (void)load; return false; }
uint64_t rr16_input_frame(void) { return frames; }
/* The fallback recording of an export is not part of the kit. */
int rr_feedback_toggle(void) { return 0; }
const char *rr_feedback_label(void) { return "F12 Record fallback hints: OFF"; }
int rr_feedback_pending(void) { return 0; }
void rr_feedback_finish(void) {}
#ifndef _WIN32
const void *rr_resource(unsigned id, size_t *size) { (void)id; *size = 0; return NULL; }
#endif
#endif
