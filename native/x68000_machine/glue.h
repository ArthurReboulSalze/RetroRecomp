/* Retro-Recomp X68000 MIT host glue: shared private declarations.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Independently written from docs/X68000_GLUE_SPEC.md (behavioural
 * specification). Sources consulted: that specification, the machine-side
 * headers it names, and our own native/x68000_reference host. No code from
 * libretro.c, libretro/joystick.c or libretro/timer.c is used.
 */
#ifndef RR_X68000_MACHINE_GLUE_H
#define RR_X68000_MACHINE_GLUE_H

#include <stdbool.h>
#include <stdint.h>
#include "common.h"
#include <libretro.h>

extern retro_log_printf_t log_cb;

/* Configuration constants of this machine profile. */
#define RR_GLUE_MAX_DISKS 10
#define RR_GLUE_SAMPLE_RATE 44100.0

extern int CHANGEAV, CHANGEAV_TIMING, VID_MODE;
extern retro_environment_t rr_glue_environ;
extern float rr_glue_framerate;
extern int rr_glue_firstcall;
extern int rr_glue_cur_drive;
extern char rr_glue_system_conf[];

/* machine.c */
void rr_glue_boot(int argc, char **argv);
void rr_glue_exec_frame(void);
void rr_glue_update_framerate(void);
bool rr_glue_load_roms(void);
extern uint8_t rr_glue_disp_frame;

/* Snapshot sections owned by the glue (state/snapshot.c orders them). */
struct RRState;
void rr_state_main(struct RRState *s);
void rr_state_input(struct RRState *s);

/* input.c */
void rr_glue_mouse_frame(void);
void rr_glue_keyboard_frame(void);
void rr_glue_input_reset(void);
extern uint8_t Core_Key_State[512];
extern uint8_t Core_old_Key_State[512];
extern bool mbL, mbR;

#endif
