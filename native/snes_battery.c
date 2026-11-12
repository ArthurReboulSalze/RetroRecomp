/* The Super Nintendo's battery RAM file: the format and the machine's memory; the rules (load, save, atomic write, a file the game
 * cannot use set aside) are in cart_save.c. Lazy battery files survive rebuilds; quick states separately pin runtime ABI. */
#include "platform_io.h"
#include <string.h>

#include "cart_save.h"
#include "snes_battery.h"

static uint8_t saved[0x20000], observed[0x20000];
/* magic, a damaged file set aside, capacity, three identity words (the mapping, 0, 0), the hash at offset 32 */
static const RrCartSaveFormat format = {{'R','R','S','N','R','A','1',0}, RR_CART_SAVE_SET_ASIDE, sizeof saved, 3, 32};
static RrCartSave save = {&format, saved, observed};
static bool battery_enabled;
static unsigned mapping;

static void identity(const Cart *bus, uint32_t words[3]) {
    words[0]=(uint32_t)bus->type; words[1]=0; words[2]=0;
}
static const uint8_t *install(void *context, const uint8_t *payload) {
    Cart *bus=context;
    if (payload) memcpy(bus->ram,payload,bus->ramSize);
    return bus->ram;
}
unsigned rr_snes_battery_notice(void) { return save.notice; }
bool rr_snes_battery_path(wchar_t *path, size_t capacity) {
    return rr_cart_save_path(path,capacity);
}
bool rr_snes_battery_open(Cart *bus, bool battery, const wchar_t *path) {
    battery_enabled=battery; mapping=bus ? bus->type : 0;
    rr_cart_save_reset(&save);
    if (!bus) return false;
    if (!path || !(bus->ram && bus->ramSize) || !battery_enabled) return true;
    uint32_t words[3]; identity(bus,words);
    return rr_cart_save_open(&save,path,bus->ramSize,words,install,bus);
}
bool rr_snes_battery_flush(const Cart *bus, uint64_t now_ms, bool force) {
    if (!rr_cart_save_active(&save)) return true;
    if (bus->type!=mapping || !(bus->ram && bus->ramSize) || !battery_enabled || !bus->ramSize || bus->ramSize>sizeof saved) return false;
    uint32_t words[3]; identity(bus,words);
    return rr_cart_save_flush(&save,bus->ram,bus->ramSize,words,now_ms,force);
}
