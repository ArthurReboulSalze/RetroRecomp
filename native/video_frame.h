#ifndef SMSRECOMP_VIDEO_FRAME_H
#define SMSRECOMP_VIDEO_FRAME_H

/* Presentation metadata from the last rendered VDP frame. The host must not
 * reinterpret live registers or guess borders from the colour of pixels. */
int smsrecomp_frame_left_border(void);

#endif
