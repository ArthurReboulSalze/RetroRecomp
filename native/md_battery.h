#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <wchar.h>
#include "video/genesis_bus.h"
bool rr_md_battery_path(wchar_t *path, size_t capacity);
/* NULL path disables host persistence, including all conversion probes. */
bool rr_md_battery_open(GenesisBus *bus, const wchar_t *path);
bool rr_md_battery_flush(const GenesisBus *bus, uint64_t now_ms, bool force);
