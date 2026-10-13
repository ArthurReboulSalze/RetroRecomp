#ifndef RR_SNES_BATTERY_H
#define RR_SNES_BATTERY_H
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <wchar.h>
#include "snes/cart.h"
bool rr_snes_battery_path(wchar_t *path, size_t capacity);
bool rr_snes_battery_open(Cart *cart, bool battery, const wchar_t *path);
bool rr_snes_battery_flush(const Cart *cart, uint64_t now_ms, bool force);
#endif
