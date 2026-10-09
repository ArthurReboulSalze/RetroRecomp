#ifndef RETRO_CONSOLE16_STATE_H
#define RETRO_CONSOLE16_STATE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <wchar.h>
/* Engine-owned payloads never contain a live C stack or host pointers. */
uint8_t *rr16_state_capture(size_t *size);
bool rr16_state_restore(const uint8_t *data, size_t size);
bool rr16_state_path(wchar_t *path, size_t capacity);
bool rr16_state_file(const wchar_t *path, bool load);
#endif
