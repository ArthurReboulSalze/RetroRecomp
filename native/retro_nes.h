#ifndef RETRO_NES_H
#define RETRO_NES_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#ifndef RR_NES_PAL
#define RR_NES_PAL 0
#endif
#ifndef RR_NES_ZAPPER
#define RR_NES_ZAPPER 0
#endif
#define RR_CPU_DIV (RR_NES_PAL ? 16 : 12)
#define RR_PPU_DIV (RR_NES_PAL ? 5 : 4)
#define RR_PRERENDER (RR_NES_PAL ? 311 : 261)
#define RR_MASTER_HZ (RR_NES_PAL ? 26601712.0 : 21477272.0)
#define RR_CPU_HZ (RR_MASTER_HZ / RR_CPU_DIV)
#define RR_FRAME_SECONDS ((RR_NES_PAL ? 106392.0 : 89341.5) * RR_PPU_DIV / RR_MASTER_HZ)
#define RR_READ_TICKS (RR_NES_PAL ? 9 : 7)

void rr_nes_zapper_aim(int x, int y, bool trigger, bool offscreen);
uint8_t rr_nes_zapper_read(int port);
void rr_nes_zapper_pixel(int x, int y, uint16_t color);
void rr_nes_zapper_reset(void);

/* In-memory snapshots are identified by cartridge + region + runtime ABI.
 * File helpers are atomic and create a directory only when actually saving. */
size_t rr_nes_state_size(void);
bool rr_nes_state_save(void *buffer, size_t size);
bool rr_nes_state_load(const void *buffer, size_t size);
bool rr_nes_state_file(const wchar_t *path, bool load);
const char *rr_nes_state_error(void);
void rr_nes_state_path(wchar_t *path, size_t capacity);

/* Private chip snapshots, accessible only to the machine adapter. */
size_t rr_nes_apu_size(void);
void rr_nes_apu_save(uint8_t *buffer);
void rr_nes_apu_load(const uint8_t *buffer);
void rr_nes_ppu_aux_save(uint8_t *buffer);
void rr_nes_ppu_aux_load(const uint8_t *buffer);
size_t rr_nes_mapper_audio_size(void);
void rr_nes_mapper_audio_save(uint8_t *buffer);
bool rr_nes_mapper_audio_check(const uint8_t *buffer);
void rr_nes_mapper_audio_load(const uint8_t *buffer);
#endif
