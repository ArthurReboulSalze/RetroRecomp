/* The Mega Drive's battery SRAM file: the format and the machine's memory; the rules (load, save, atomic write) are in
 * cart_save.c. A damaged or wrong-cartridge file is left where it is and the open fails: it is never replaced by blank progress.
 * Lazy battery files survive rebuilds; quick states separately pin runtime ABI. */
#include "platform_io.h"
#include <string.h>

#include "cart_save.h"
#include "md_battery.h"

static uint8_t saved[0x10000], observed[0x10000];
/* magic, no flags, capacity, three identity words (the SRAM's base, end and stride), the hash at offset 32 */
static const RrCartSaveFormat format = {{'R','R','M','D','R','A','1',0}, 0, sizeof saved, 3, 32};
static RrCartSave save = {&format, saved, observed};

static void identity(const GenesisBus *bus, uint32_t words[3]) {
    words[0]=bus->sram_base; words[1]=bus->sram_end; words[2]=bus->sram_stride;
}
static const uint8_t *install(void *context, const uint8_t *payload) {
    GenesisBus *bus=context;
    if (payload) memcpy(bus->sram,payload,bus->sram_size);
    return bus->sram;
}
bool rr_md_battery_path(wchar_t *path, size_t capacity) {
    return rr_cart_save_path(path,capacity);
}
bool rr_md_battery_open(GenesisBus *bus, const wchar_t *path) {
    rr_cart_save_reset(&save);
    if (!path || !bus->sram_present || !bus->sram_battery) return true;
    uint32_t words[3]; identity(bus,words);
    return rr_cart_save_open(&save,path,bus->sram_size,words,install,bus);
}
bool rr_md_battery_flush(const GenesisBus *bus, uint64_t now_ms, bool force) {
    if (!rr_cart_save_active(&save)) return true;
    if (!bus->sram_present || !bus->sram_battery || !bus->sram_size || bus->sram_size>sizeof saved) return false;
    uint32_t words[3]; identity(bus,words);
    return rr_cart_save_flush(&save,bus->sram,bus->sram_size,words,now_ms,force);
}
