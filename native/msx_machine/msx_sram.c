/* MSX cartridge SRAM file (docs/MSX.md, "Saves"): the format and the cartridge's memory; the rules are in cart_save.c. The file
 * is a versioned header, then the 8 KB (ASCII 8) or 2 KB (ASCII 16) the game wrote. It survives a rebuild of the game: only the
 * exact cartridge is checked, not the engine. Quick states are separate files and carry the SRAM of their moment.
 * A file the game cannot use is never deleted, overwritten or a reason not to start: it moves to "<file>.unusable-N" and the game
 * starts with a blank SRAM; if it cannot move, it stays untouched and nothing is saved this session. Original RetroRecomp code: MIT. */
#include "platform_io.h"

#include <string.h>

#include "cart_save.h"
#include "msx_sram.h"

static uint8_t saved[MSX_SRAM_MAX], observed[MSX_SRAM_MAX];
/* magic, a damaged file set aside, an unreadable one reported, capacity, no identity word, the hash at offset 16 */
static const RrCartSaveFormat format = {{'R', 'R', 'M', 'S', 'X', 'S', 'R', '1'}, RR_CART_SAVE_SET_ASIDE | RR_CART_SAVE_NOTICE_UNREADABLE,
                                        MSX_SRAM_MAX, 0, 16};
static RrCartSave save = {&format, saved, observed};
static uint8_t *memory;
static size_t size;

unsigned msx_sram_notice(void) { return save.notice; }

bool msx_sram_path(wchar_t *path, size_t capacity) { return rr_cart_save_path(path, capacity); }

static const uint8_t *install(void *context, const uint8_t *payload)
{
    (void)context;
    if (payload) memcpy(memory, payload, size);
    return memory;
}

void msx_sram_open(const wchar_t *path, uint8_t *sram, size_t bytes)
{
    memory = sram;
    size = bytes;
    rr_cart_save_open(&save, path, bytes, NULL, install, NULL);
}

bool msx_sram_flush(uint64_t now_ms, bool force)
{
    if (!memory || !rr_cart_save_active(&save)) return true;
    return rr_cart_save_flush(&save, memory, size, NULL, now_ms, force);
}

uint64_t msx_sram_hash(const uint8_t *bytes, size_t count)
{
    uint64_t value = 14695981039346656037ull;
    for (size_t i = 0; i < count; ++i) value = (value ^ bytes[i]) * 1099511628211ull;
    return value;
}
