/* No HDR in a PlayStation game: the answers "off" to what Beetle PSX's core and Vulkan renderer ask of its HDR display transform
 * (Retro-Recomp's own code, MIT).
 *
 * Upstream's rhi/hdr_transform.c and rhi/hdr_aces2.c build the tone curves, the ACES 2.0 output transform and its lookup tables
 * for an HDR display. They carry no licence notice, hold tables transcribed from the Academy's reference code and a table derived
 * from Blender's, and a game never asks its frontend for an HDR output: they are not copied into a game's sources
 * (retrorecomp/psx_beetle.py, EXCLUDED). The core still configures the transform at start and the renderer still binds its
 * constant block and looks for its tables each frame; this file answers those calls for a standard-range picture: nothing is
 * enabled, no table exists (the renderer then keeps its own 1x1 placeholder images), and the constant block is zeros. Only the
 * declarations of rhi/hdr_transform.h are used. */
#include <string.h>

#include "hdr_transform.h"

void hdr_dt_configure(const struct hdr_dt_settings *s) { (void)s; }
unsigned hdr_dt_serial(void) { return 0; }
bool hdr_dt_enabled(void) { return false; }
void hdr_dt_fill(struct hdr_dt_block *b, float paper_white_nits, float peak_nits, float panel_peak_nits, const uint16_t panel_xy[8]) {
    (void)paper_white_nits; (void)peak_nits; (void)panel_peak_nits; (void)panel_xy;
    if (b) memset(b, 0, sizeof(*b));
}
const uint16_t *hdr_dt_aces2_lut(void) { return NULL; }
const uint16_t *hdr_dt_film_lut(void) { return NULL; }
const uint16_t *hdr_dt_film_desat(void) { return NULL; }
unsigned hdr_dt_generation(void) { return 0; }
const uint16_t *hdr_dt_aces2_cube(void) { return NULL; }
void hdr_dt_aces2_cube_finish(float paper_white_nits) { (void)paper_white_nits; }
uint16_t hdr_dt_unorm16_to_half(uint16_t v) { (void)v; return 0; }   /* reached only with a table to convert: there is none */
void hdr_dt_free(void) {}

void hdr_post_configure(const struct hdr_post_settings *s) { (void)s; }
bool hdr_post_enabled(void) { return false; }
bool hdr_post_compact(void) { return false; }
void hdr_post_frame_params(struct hdr_post_frame *f, unsigned w, unsigned h) {
    (void)w; (void)h;
    if (f) memset(f, 0, sizeof(*f));
}
