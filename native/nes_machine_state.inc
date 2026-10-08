/* Included in the staged hw_machine.c. Snapshots contain no cartridge ROM,
 * pointers, native dispatch addresses, or host input/audio/window handles.
 * Chip layouts are deliberately ABI-bound; incompatible generations fail
 * before touching the running machine. This is a local quick-state format. */
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
    return sizeof(RrStateHeader) + sizeof(RrMachineState) + hw_cart.chr_ram_len +
           rr_nes_apu_size() + rr_nes_mapper_audio_size();
}
bool rr_nes_state_save(void *buffer, size_t size) {
    if (!buffer || size != rr_nes_state_size()) { state_error = "Could not create quick state"; return false; }
    uint8_t *bytes = (uint8_t *)buffer;
    memset(bytes, 0, size);
    RrStateHeader header = {0};
    memcpy(header.magic, "RRNESST1", 8);
    memcpy(header.abi, RR_NES_STATE_ABI, 65);
    memcpy(header.rom, RR_NES_ROM_SHA, 65);
    header.bytes = (uint32_t)size; header.pal = RR_NES_PAL; header.gun = RR_NES_ZAPPER;
    RrMachineState *s = (RrMachineState *)calloc(1, sizeof(*s));
    if (!s) { state_error = "Not enough memory to save"; return false; }
    s->processor = cpu; s->machine = hw; s->cart = hw_cart; s->video = ppu;
    s->cart.prg = s->cart.chr = NULL;
    s->gun = zapper; s->frame_done = hw_frame_done; s->dma_stalls = hw_dma_stalls;
    rr_nes_ppu_aux_save(s->ppu_aux);
    memcpy(s->image, hw_frame_index, sizeof(s->image));
    size_t pos = sizeof(header);
    memcpy(bytes + pos, s, sizeof(*s)); pos += sizeof(*s); free(s);
    memcpy(bytes + pos, hw_cart.chr + hw_cart.chr_ram_base, hw_cart.chr_ram_len); pos += hw_cart.chr_ram_len;
    rr_nes_apu_save(bytes + pos); pos += rr_nes_apu_size();
    rr_nes_mapper_audio_save(bytes + pos);
    header.checksum = state_crc(bytes + sizeof(header), size - sizeof(header));
    memcpy(bytes, &header, sizeof(header));
    state_error = "Quick state saved";
    return true;
}
bool rr_nes_state_load(const void *buffer, size_t size) {
    state_error = "Invalid or incompatible quick state";
    if (!buffer || size != rr_nes_state_size()) return false;
    const uint8_t *bytes = (const uint8_t *)buffer;
    RrStateHeader h;
    memcpy(&h, bytes, sizeof(h));
    if (memcmp(h.magic, "RRNESST1", 8) || memcmp(h.abi, RR_NES_STATE_ABI, 65) ||
            memcmp(h.rom, RR_NES_ROM_SHA, 65) || h.pal != RR_NES_PAL || h.gun != RR_NES_ZAPPER ||
            h.bytes != size || h.checksum != state_crc(bytes + sizeof(h), size - sizeof(h))) return false;
    RrMachineState *s = (RrMachineState *)malloc(sizeof(*s));
    if (!s) return false;
    memcpy(s, bytes + sizeof(h), sizeof(*s));
    bool valid = !s->cart.prg && !s->cart.chr &&
        memcmp(&s->cart.info, &hw_cart.info, sizeof(hw_cart.info)) == 0 &&
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
    size_t pos = sizeof(h) + sizeof(*s) + hw_cart.chr_ram_len + rr_nes_apu_size();
    valid &= rr_nes_mapper_audio_check(bytes + pos);
    if (!valid) { free(s); return false; }
    /* All checks complete. No partial restore is visible on any failure. */
    s->cart.prg = hw_cart.prg; s->cart.chr = hw_cart.chr;
    cpu = s->processor; hw = s->machine; hw_cart = s->cart; ppu = s->video;
    zapper = s->gun; hw_frame_done = s->frame_done != 0; hw_dma_stalls = s->dma_stalls;
    rr_nes_ppu_aux_load(s->ppu_aux); memcpy(hw_frame_index, s->image, sizeof(s->image));
    pos = sizeof(h) + sizeof(*s); free(s);
    memcpy(hw_cart.chr + hw_cart.chr_ram_base, bytes + pos, hw_cart.chr_ram_len); pos += hw_cart.chr_ram_len;
    rr_nes_apu_load(bytes + pos); pos += rr_nes_apu_size();
    rr_nes_mapper_audio_load(bytes + pos);
    state_error = "Quick state loaded";
    return true;
}
