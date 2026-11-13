/* MSX cartridge SRAM file: the battery memory of an ASCII 8 KB or 16 KB cartridge, one file per game beside it (cart_save.c).
 * Original RetroRecomp code: MIT. */
#ifndef RR_MSX_SRAM_H
#define RR_MSX_SRAM_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <wchar.h>

enum { MSX_SRAM_MAX = 0x2000 };

bool msx_sram_path(wchar_t *path, size_t capacity);
/* Loads the file into `sram` (`bytes` long), which is what is saved from then on; without a file the game keeps the blank
 * memory. NULL path: no file, nothing is ever written (the converter's routes). Never a reason for the game not to start. */
void msx_sram_open(const wchar_t *path, uint8_t *sram, size_t bytes);
/* Writes the memory when it has been quiet for two seconds, or at once with force. False: this write failed (retried later). */
bool msx_sram_flush(uint64_t now_ms, bool force);
/* 0 nothing to say; 1 an unusable file was set aside and the game started blank; 2 it could not be, saving is off. */
unsigned msx_sram_notice(void);
/* FNV-1a 64 of the memory, as the file's header stores it. */
uint64_t msx_sram_hash(const uint8_t *bytes, size_t count);
#endif
