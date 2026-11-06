/* gba_machine.h: what the Game Boy Advance player's host-kit adapter (hostkit/adapters/rrhk_gba.c) asks of the machine
 * (native/gba_machine.cpp, which holds the engine's driver). Original Retro-Recomp code: MIT. */
#ifndef RR_GBA_MACHINE_H
#define RR_GBA_MACHINE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <wchar.h>

#ifdef __cplusplus
extern "C" {
#endif

/* One frame, from VBlank to VBlank, with the buttons held (the hardware KEYINPUT bits, here high = pressed). The picture and
 * the sound of the frame are taken. false: the guest stopped, or a power cycle was asked. */
bool rrgba_frame(uint16_t pressed);
const uint32_t *rrgba_pixels(void);                  /* 240 x 160, 0xAARRGGBB */
size_t rrgba_audio(int16_t *pcm, size_t capacity);   /* the machine's mono sound at 32768 Hz; 0 when nothing is left */
void rrgba_reset(void);                              /* a power cycle: the loop ends and the machine is built again */
uint64_t rrgba_interpreted(void);                    /* guest instructions the engine's interpreter ran: never hidden */
uint64_t rrgba_frames(void);
bool rrgba_state_path(wchar_t *path, size_t capacity);
bool rrgba_state_file(const wchar_t *path, bool load);

#ifdef __cplusplus
}
#endif
#endif
