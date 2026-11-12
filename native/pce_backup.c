/* PC Engine Backup RAM file (docs/PC_ENGINE.md, "Saves"): the format and the machine's memory; the rules are in cart_save.c. The file
 * is a versioned header, then the 2,048 bytes the game wrote. It survives a rebuild of the game: only the exact HuCard is checked,
 * not the engine or the bridge. Quick states are separate files.
 * A file the game cannot use is never deleted, overwritten or a reason not to start: it moves to "<file>.unusable-N" and the game
 * starts formatted; if it cannot move, it stays untouched and nothing is saved this session. Original RetroRecomp code: MIT. */
#include "platform_io.h"

#include "cart_save.h"
#include "pce_backup.h"
#include "pce_machine.h"

static uint8_t saved[PCE_BACKUP_BYTES], observed[PCE_BACKUP_BYTES];
/* magic, a damaged file set aside, an unreadable one reported, capacity, no identity word, the hash at offset 16 */
static const RrCartSaveFormat format = {{'R', 'R', 'P', 'C', 'E', 'B', 'R', '1'}, RR_CART_SAVE_SET_ASIDE | RR_CART_SAVE_NOTICE_UNREADABLE,
                                        PCE_BACKUP_BYTES, 0, 16};
static RrCartSave save = {&format, saved, observed};

unsigned rr_pce_backup_notice(void) { return save.notice; }

bool rr_pce_backup_path(wchar_t *path, size_t capacity) { return rr_cart_save_path(path, capacity); }

static const uint8_t *install(void *context, const uint8_t *payload)
{
    (void)context;
    if (payload) pce_machine_set_backup(payload);
    return pce_machine_backup();
}

void rr_pce_backup_open(const wchar_t *path)
{
    rr_cart_save_open(&save, path, PCE_BACKUP_BYTES, NULL, install, NULL);
}

bool rr_pce_backup_flush(uint64_t now_ms, bool force)
{
    if (!rr_cart_save_active(&save)) return true;
    return rr_cart_save_flush(&save, pce_machine_backup(), PCE_BACKUP_BYTES, NULL, now_ms, force);
}
