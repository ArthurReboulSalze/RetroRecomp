/* Retro-Recomp Nintendo 64: the cartridge and pak save memory the core exposes to the frontend as one blob.
 * Written from its uses in main.c and libretro.c. SPDX-License-Identifier: MIT */
#pragma once
#include <stdint.h>
#include "device/controllers/paks/mempak.h"
#include "device/cart/sram.h"
#include "device/cart/flashram.h"
#define EEPROM_MAX_SIZE 0x800   /* 16 Kbit EEPROM */
typedef struct {
    uint8_t eeprom[EEPROM_MAX_SIZE];
    uint8_t mempack[4 * MEMPAK_SIZE];   /* four Controller Paks, one after another */
    uint8_t sram[SRAM_SIZE];
    uint8_t flashram[FLASHRAM_SIZE];
} save_memory_data;
extern save_memory_data saved_memory;
