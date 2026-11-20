/* Included in the staged hw_machine.c. Snapshots contain no cartridge ROM,
 * pointers, native dispatch addresses, or host input/audio/window handles.
 * Every structure is written field by field (nes_state_main.inc, generated from
 * the definitions below and the engine's), so no compiler padding reaches the
 * file and every byte of it is defined. Incompatible generations fail before
 * touching the running machine. This is a local quick-state format. */
#include "nes_state_abi.h"
#include "retro_nes_config.h"
#include "cpu6502.h"

typedef struct {
    int32_t x, y;
    uint8_t trigger, offscreen;
    uint64_t light_until;
} RrZapper;
static RrZapper zapper;
void rr_nes_zapper_reset(void) { memset(&zapper, 0, sizeof(zapper)); zapper.offscreen = 1; }
void rr_nes_zapper_aim(int x, int y, bool trigger, bool offscreen) {
    zapper.x = x; zapper.y = y; zapper.trigger = trigger;
    zapper.offscreen = offscreen || x < 0 || x >= 256 || y < 0 || y >= 240;
    if (zapper.offscreen) zapper.light_until = 0;
}
uint8_t rr_nes_zapper_read(int port) {
    if (!RR_NES_ZAPPER || port != 1) return 0;
    return (uint8_t)((zapper.trigger ? 16 : 0) |
        (zapper.offscreen || hw.cycles >= zapper.light_until ? 8 : 0));
}
void rr_nes_zapper_pixel(int x, int y, uint16_t color) {
    if (!RR_NES_ZAPPER || zapper.offscreen || abs(x - zapper.x) > 4 || abs(y - zapper.y) > 4) return;
    uint32_t rgb = hw_palette_argb[color & 511];
    unsigned light = (((rgb >> 16) & 255) * 77 + ((rgb >> 8) & 255) * 150 + (rgb & 255) * 29) >> 8;
    if (light >= 160) {
        /* CRT response approximation: 19..26 scanlines of sensor persistence.
         * It sees only pixels already emitted, never a future/stale frame. */
        unsigned lines = 19 + (light - 160) * 7 / 95;
        zapper.light_until = hw.cycles + (lines * 341 * RR_PPU_DIV + RR_CPU_DIV - 1) / RR_CPU_DIV;
    }
}

typedef struct {
    char magic[8], abi[65], rom[65];
    uint32_t bytes, checksum, pal, gun;
} RrStateHeader;
typedef struct {
    Cpu6502 processor;
    HwMachine machine;
    HwCart cart;
    HwPpu video;
    RrZapper gun;
    uint8_t ppu_aux[2], frame_done;
    int32_t dma_stalls;
    uint16_t image[256 * 240];
} RrMachineState;
#include "nes_state_main.inc"
static const char *state_error = "";
const char *rr_nes_state_error(void) { return state_error; }
static uint32_t state_crc(const uint8_t *data, size_t size) {
    uint32_t crc = ~0u;
    for (size_t i = 0; i < size; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1)));
    }
    return ~crc;
}
size_t rr_nes_state_size(void) {
    return rr_size_RrStateHeader() + rr_size_RrMachineState() + hw_cart.chr_ram_len +
           rr_nes_apu_size() + rr_nes_mapper_audio_size();
}
static bool cart_info_equal(const NesCartInfo *a, const NesCartInfo *b) {
    uint8_t x[128], y[128];
    if (rr_size_NesCartInfo() > sizeof x) return false;
    rr_ser_NesCartInfo(x, a); rr_ser_NesCartInfo(y, b);
    return memcmp(x, y, rr_size_NesCartInfo()) == 0;
}
bool rr_nes_state_save(void *buffer, size_t size) {
    rr_ppu_sync();
    if (!buffer || size != rr_nes_state_size()) { state_error = "Could not create quick state"; return false; }
    uint8_t *bytes = (uint8_t *)buffer;
    /* Every byte of the file is written by a field serialiser, one after the
     * other: the cursor must end exactly at `size`. Nothing is zero-filled first. */
    RrStateHeader header;
    memset(&header, 0, sizeof header);
    memcpy(header.magic, "RRNESST2", 8);
    memcpy(header.abi, RR_NES_STATE_ABI, 65);
    memcpy(header.rom, RR_NES_ROM_SHA, 65);
    header.bytes = (uint32_t)size; header.pal = RR_NES_PAL; header.gun = RR_NES_ZAPPER;
    RrMachineState *s = (RrMachineState *)calloc(1, sizeof(*s));
    if (!s) { state_error = "Not enough memory to save"; return false; }
    memcpy(&s->processor, &cpu, sizeof(cpu)); memcpy(&s->machine, &hw, sizeof(hw));
    memcpy(&s->cart, &hw_cart, sizeof(hw_cart)); memcpy(&s->video, &ppu, sizeof(ppu));
    s->cart.prg = s->cart.chr = NULL;
    memcpy(&s->gun, &zapper, sizeof(zapper)); s->frame_done = hw_frame_done; s->dma_stalls = hw_dma_stalls;
    rr_nes_ppu_aux_save(s->ppu_aux);
    memcpy(s->image, hw_frame_index, sizeof(s->image));
    const size_t head = rr_size_RrStateHeader();
    uint8_t *cursor = rr_ser_RrMachineState(bytes + head, s); free(s);
    memcpy(cursor, hw_cart.chr + hw_cart.chr_ram_base, hw_cart.chr_ram_len); cursor += hw_cart.chr_ram_len;
    rr_nes_apu_save(cursor); cursor += rr_nes_apu_size();
    rr_nes_mapper_audio_save(cursor); cursor += rr_nes_mapper_audio_size();
    if (cursor != bytes + size) { state_error = "Could not create quick state"; return false; }
    header.checksum = state_crc(bytes + head, size - head);
    rr_ser_RrStateHeader(bytes, &header);
    state_error = "Quick state saved";
    return true;
}
bool rr_nes_state_load(const void *buffer, size_t size) {
    state_error = "Invalid or incompatible quick state";
    if (!buffer || size != rr_nes_state_size()) return false;
    const uint8_t *bytes = (const uint8_t *)buffer;
    RrStateHeader h;
    const size_t head = rr_size_RrStateHeader();
    rr_de_RrStateHeader(bytes, &h);
    if (memcmp(h.magic, "RRNESST2", 8) || memcmp(h.abi, RR_NES_STATE_ABI, 65) ||
            memcmp(h.rom, RR_NES_ROM_SHA, 65) || h.pal != RR_NES_PAL || h.gun != RR_NES_ZAPPER ||
            h.bytes != size || h.checksum != state_crc(bytes + head, size - head)) return false;
    RrMachineState *s = (RrMachineState *)calloc(1, sizeof(*s));
    if (!s) return false;
    rr_de_RrMachineState(bytes + head, s);
    bool valid = cart_info_equal(&s->cart.info, &hw_cart.info) &&
        s->cart.prg_len == hw_cart.prg_len && s->cart.prg_slots == hw_cart.prg_slots &&
        s->cart.chr_len == hw_cart.chr_len && s->cart.chr_pages == hw_cart.chr_pages &&
        s->cart.chr_ram_base == hw_cart.chr_ram_base && s->cart.chr_ram_len == hw_cart.chr_ram_len &&
        s->cart.mapper == hw_cart.mapper && s->machine.tick <= RR_CPU_DIV && s->machine.align < 4 &&
        s->machine.pal_bus_pending <= 1 &&
        s->video.dot <= 340 && s->video.scanline <= RR_PRERENDER &&
        s->video.fine_x < 8 && s->video.emphasis < 8 && s->video.oam2_addr <= 32 &&
        s->video.oamc_index <= 32 && s->ppu_aux[1] <= 2;
    for (int i = 0; i < 8; i++) {
        uint32_t prg = s->cart.prg_off[i];
        valid &= !(prg & 4095) && ((prg & MMC5_PRG_OPEN) ||
            ((prg & MMC5_PRG_RAM) ? (prg & ~(MMC5_PRG_RAM | MMC5_PRG_OPEN)) < sizeof(hw_cart.wram) :
                                   prg < hw_cart.prg_slots * 4096));
        valid &= (s->cart.chr_ciram & (1u << i)) ? s->cart.chr_off[i] < 4096 :
            s->cart.chr_off[i] < hw_cart.chr_pages * 1024 + hw_cart.chr_ram_len;
    }
    for (size_t i = 0; i < 256 * 240; i++) valid &= s->image[i] < 512;
    size_t pos = head + rr_size_RrMachineState() + hw_cart.chr_ram_len + rr_nes_apu_size();
    valid &= rr_nes_mapper_audio_check(bytes + pos);
    if (!valid) { free(s); return false; }
    /* All checks complete. No partial restore is visible on any failure. */
    s->cart.prg = hw_cart.prg; s->cart.chr = hw_cart.chr;
    cpu = s->processor; hw = s->machine; hw_cart = s->cart; ppu = s->video;
    zapper = s->gun; hw_frame_done = s->frame_done != 0; hw_dma_stalls = s->dma_stalls;
    rr_nes_ppu_aux_load(s->ppu_aux); memcpy(hw_frame_index, s->image, sizeof(s->image));
    pos = head + rr_size_RrMachineState(); free(s);
    memcpy(hw_cart.chr + hw_cart.chr_ram_base, bytes + pos, hw_cart.chr_ram_len); pos += hw_cart.chr_ram_len;
    rr_nes_apu_load(bytes + pos); pos += rr_nes_apu_size();
    rr_nes_mapper_audio_load(bytes + pos);
    state_error = "Quick state loaded";
    return true;
}

/* Multiplayer rollback (native/hostkit/hostkit_session.h): the same machine as a quick state, raw, for this process only. It
 * loads only what this process saved a few frames earlier, so it has no header, no checksum, no allocation and no validation;
 * the quick-state files, their format and their key are untouched. The cartridge's PRG/CHR pointers never change in a run and
 * are copied as they are; the CHR RAM they point into is copied beside. */
#define RR_NES_SNAP_FIELDS(X) X(cpu) X(hw) X(hw_cart) X(ppu) X(zapper) X(hw_frame_done) X(hw_dma_stalls)
size_t rr_nes_snap_bound(void) {
#define RR_NES_SNAP_SIZE(name) sizeof(name) +
    return RR_NES_SNAP_FIELDS(RR_NES_SNAP_SIZE) 2 + sizeof(((RrMachineState *)0)->image) + hw_cart.chr_ram_len +
           rr_nes_apu_size() + rr_nes_mapper_audio_size();
#undef RR_NES_SNAP_SIZE
}
size_t rr_nes_snap_save(void *buffer, size_t capacity) {
    const size_t size = rr_nes_snap_bound();
    if (!buffer || capacity < size) return 0;
    rr_ppu_sync();
    uint8_t *cursor = (uint8_t *)buffer;
#define RR_NES_SNAP_PUT(name) memcpy(cursor, &name, sizeof(name)); cursor += sizeof(name);
    RR_NES_SNAP_FIELDS(RR_NES_SNAP_PUT)
#undef RR_NES_SNAP_PUT
    rr_nes_ppu_aux_save(cursor); cursor += 2;
    memcpy(cursor, hw_frame_index, sizeof(((RrMachineState *)0)->image)); cursor += sizeof(((RrMachineState *)0)->image);
    memcpy(cursor, hw_cart.chr + hw_cart.chr_ram_base, hw_cart.chr_ram_len); cursor += hw_cart.chr_ram_len;
    rr_nes_apu_save(cursor); cursor += rr_nes_apu_size();
    rr_nes_mapper_audio_save(cursor); cursor += rr_nes_mapper_audio_size();
    return (size_t)(cursor - (uint8_t *)buffer) == size ? size : 0;
}
bool rr_nes_snap_load(const void *buffer, size_t size) {
    if (!buffer || size != rr_nes_snap_bound()) return false;
    const uint8_t *cursor = (const uint8_t *)buffer;
#define RR_NES_SNAP_GET(name) memcpy(&name, cursor, sizeof(name)); cursor += sizeof(name);
    RR_NES_SNAP_FIELDS(RR_NES_SNAP_GET)
#undef RR_NES_SNAP_GET
    rr_nes_ppu_aux_load(cursor); cursor += 2;
    memcpy(hw_frame_index, cursor, sizeof(((RrMachineState *)0)->image)); cursor += sizeof(((RrMachineState *)0)->image);
    memcpy(hw_cart.chr + hw_cart.chr_ram_base, cursor, hw_cart.chr_ram_len); cursor += hw_cart.chr_ram_len;
    rr_nes_apu_load(cursor); cursor += rr_nes_apu_size();
    rr_nes_mapper_audio_load(cursor);
    return true;
}
/* The digest a session compares between players: FNV-1a 64 over the quick state's field-written payload (the same bytes on
 * Windows and Linux), header left out. NULL-safe: 0 when the payload cannot be made. */
uint64_t rr_nes_digest(void) {
    static uint8_t *payload;
    static size_t capacity;
    const size_t size = rr_nes_state_size(), head = rr_size_RrStateHeader();
    if (size > capacity) { free(payload); payload = (uint8_t *)malloc(size); capacity = payload ? size : 0; }
    if (!payload || !rr_nes_state_save(payload, size)) return 0;
    uint64_t hash = 14695981039346656037ull;
    for (size_t i = head; i < size; ++i) { hash ^= payload[i]; hash *= 1099511628211ull; }
    return hash;
}

/* Multiplayer, the host's save (hostkit_session.h, session ABI 8): the cartridge's nonvolatile memory (region 0) and the Datach's
 * EEPROM (region 1) as one image, magic "RNS1" then the two lengths (little endian) then the two regions, so the guest plays the
 * match on the host's bytes. A guest never writes its own save file: rr_nes_saves_blocked() stops the host program's write. */
static bool rr_saves_allowed = true;
void rr_nes_saves_allowed(bool allowed) { rr_saves_allowed = allowed; }
bool rr_nes_saves_blocked(void) { return !rr_saves_allowed; }
static void rr_put32(uint8_t *at, uint32_t value) { for (int i = 0; i < 4; i++) at[i] = (uint8_t)(value >> (8 * i)); }
static uint32_t rr_get32(const uint8_t *at) { return (uint32_t)at[0] | (uint32_t)at[1] << 8 | (uint32_t)at[2] << 16 | (uint32_t)at[3] << 24; }
size_t rr_nes_session_save(void *out, size_t capacity) {
    const size_t a = cyc_nvram_size(0), b = cyc_nvram_size(1), total = 12 + a + b;
    if (!a && !b) return 0;
    if (total > 2u * 1024u * 1024u) return 0;
    if (!out) return total;
    if (capacity < total) return 0;
    uint8_t *bytes = (uint8_t *)out;
    memcpy(bytes, "RNS1", 4); rr_put32(bytes + 4, (uint32_t)a); rr_put32(bytes + 8, (uint32_t)b);
    if ((a && !cyc_nvram_export(0, bytes + 12, a)) || (b && !cyc_nvram_export(1, bytes + 12 + a, b))) return 0;
    return total;
}
bool rr_nes_session_save_put(const void *in, size_t size) {
    const size_t a = cyc_nvram_size(0), b = cyc_nvram_size(1);
    const uint8_t *bytes = (const uint8_t *)in;
    if (!in || size != 12 + a + b || memcmp(bytes, "RNS1", 4) || rr_get32(bytes + 4) != a || rr_get32(bytes + 8) != b) return false;
    return (!a || cyc_nvram_import(0, bytes + 12, a)) && (!b || cyc_nvram_import(1, bytes + 12 + a, b));
}
