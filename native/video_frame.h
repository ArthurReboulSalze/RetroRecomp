#ifndef SMSRECOMP_VIDEO_FRAME_H
#define SMSRECOMP_VIDEO_FRAME_H
#include <stdint.h>

/* Presentation metadata from the last rendered VDP frame. The host must not
 * reinterpret live registers or guess borders from the colour of pixels. */
int smsrecomp_frame_left_border(void);
/* VDP-owned raster state. Called on reset, each line transition, and present. */
void smsrecomp_video_reset(void);
void smsrecomp_video_begin_line(int line);
void smsrecomp_video_end_line(int line);
void smsrecomp_video_present(uint32_t *fb);
uint64_t smsrecomp_video_hash(void);
/* Host presentation choice: extra sprites and confirmed reversing-list priority
 * stabilization. Guest collision/overflow still use the original eight slots. */
void smsrecomp_video_set_sprite_flicker_reduction(int enabled);

#endif
