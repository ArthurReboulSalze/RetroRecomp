/* PC Engine Backup RAM file: the 2 KiB a HuCard game can keep on a console with a backup unit, one file per game beside it.
 * Original RetroRecomp code: MIT. */
#ifndef RR_PCE_BACKUP_H
#define RR_PCE_BACKUP_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <wchar.h>

bool rr_pce_backup_path(wchar_t *path, size_t capacity);
/* Loads the file into the machine, once it is started; without a file the game keeps the formatted memory (pce_machine.cpp).
 * NULL: no file, nothing is ever written (the converter's routes). Never a reason for the game not to start. */
void rr_pce_backup_open(const wchar_t *path);
/* Writes the memory when it has been quiet for two seconds, or at once with force. False: this write failed (retried later). */
bool rr_pce_backup_flush(uint64_t now_ms, bool force);
/* 0 nothing to say; 1 an unusable file was set aside and the game started formatted; 2 it could not be, saving is off. */
unsigned rr_pce_backup_notice(void);
#endif
