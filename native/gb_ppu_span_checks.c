/* The picture of the PPU for a line with sprites, run in batches of dots (native/gb_ppu_object_span.h), against the runtime without it: this program
 * is built twice (tools/gameboy_ppu_span_selftest.py: the runtime as the converter adapts it, and the same with the pinned ppu.c as it is) and prints the
 * same line from both; the two lines must be equal. No cartridge bytes: a program of two instructions (a halted loop) and a host that writes the
 * video memory, the sprite table and the registers of the video unit at random, in the middle of the lines (between slices of a few dozen to a few
 * thousand cycles, which is where the CPU of a game writes them), with sprites placed on the lines being drawn: every x from the left edge to the right
 * edge (partly or wholly off screen, several at one x, ten on a line), 8x8 and 8x16, flipped, behind the background, both palettes, the background and
 * the window on and off, the window at every WX, scrolled, the objects switched on and off, tile data and maps of both kinds.
 * Printed: a hash of the whole picture (grey levels and colours) after every frame, folded into one value, the number of frames, the number of lines
 * that had a sprite, and the number of times each register was written. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbrt.h"
#include "ppu.h"
#include "audio.h"

static uint8_t rom_image[0x8000];

void gb_dispatch(GBContext* ctx, uint16_t addr) {
    const uint8_t saved = ctx->single_step_mode;
    ctx->single_step_mode = 1;
    gb_interpret(ctx, addr);
    ctx->single_step_mode = saved;
}

static void on_audio(GBContext* ctx, int16_t left, int16_t right) { (void)ctx; (void)left; (void)right; }

static uint64_t rng_state;
static uint32_t rnd(void) {
    rng_state += 0x9e3779b97f4a7c15ull;
    uint64_t z = rng_state;
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ull;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebull;
    return (uint32_t)((z ^ (z >> 31)) >> 16);
}

static uint64_t fnv(uint64_t hash, const void* data, size_t size) {
    const unsigned char* bytes = (const unsigned char*)data;
    for (size_t i = 0; i < size; ++i) hash = (hash ^ bytes[i]) * 1099511628211ull;
    return hash;
}

static void place_sprites(GBContext* ctx, unsigned how_many, bool on_this_line, bool tall) {
    const GBPPU* ppu = (const GBPPU*)ctx->ppu;
    for (unsigned i = 0; i < how_many; ++i) {
        uint8_t* entry = ctx->oam + (rnd() % 40) * 4u;
        const int height = tall ? 16 : 8;
        const int y = on_this_line ? (int)ppu->ly + 16 - (int)(rnd() % height) : (int)(rnd() % 170);
        entry[0] = (uint8_t)y;
        const unsigned pick = rnd() % 10;
        entry[1] = pick == 0 ? (uint8_t)(rnd() % 12) : pick == 1 ? (uint8_t)(160 + rnd() % 12) : pick == 2 ? (uint8_t)(8 + (rnd() % 4) * 8) : (uint8_t)(rnd() % 176);
        entry[2] = (uint8_t)rnd();
        entry[3] = (uint8_t)(rnd() & 0xF0u);                 /* priority, flip y, flip x, palette */
    }
}

int main(int argc, char** argv) {
    const unsigned frames_wanted = argc > 1 ? (unsigned)atoi(argv[1]) : 600;
    rng_state = argc > 2 ? (uint64_t)atoll(argv[2]) : 1;
    memset(rom_image, 0, sizeof rom_image);
    rom_image[0x100] = 0x00; rom_image[0x101] = 0xC3; rom_image[0x102] = 0x50; rom_image[0x103] = 0x01;
    rom_image[0x150] = 0xF3; rom_image[0x151] = 0x18; rom_image[0x152] = 0xFE;      /* DI ; JR -2 */
    GBConfig config;
    memset(&config, 0, sizeof config);
    config.model = GB_MODEL_DMG;
    config.enable_audio = true; config.enable_serial = true; config.speed_percent = 100;
    config.ignore_rtc_persistence = true;
    GBContext* ctx = gb_context_create(&config);
    assert(ctx && gb_context_load_rom(ctx, rom_image, sizeof rom_image));
    ctx->callbacks.on_audio_sample = on_audio;
    gb_context_reset(ctx, true);
    ctx->pc = 0x150; ctx->halted = 0; ctx->ime = 0; ctx->ime_pending = 0;
    GBPPU* ppu = (GBPPU*)ctx->ppu;

    for (size_t i = 0; i < 0x2000; ++i) ctx->vram[i] = (uint8_t)rnd();                /* tiles and maps of both kinds */
    place_sprites(ctx, 40, false, false);

    uint64_t chain = 1469598103934665603ull;
    unsigned frames = 0, lines_with_sprites = 0, writes = 0;
    uint8_t last_ly = 255;
    while (frames < frames_wanted) {
        /* the host between two slices: what a game's code writes in the middle of a line */
        const unsigned actions = rnd() % 4;
        for (unsigned a = 0; a < actions; ++a) {
            switch (rnd() % 14) {
            case 0: { uint8_t v = (uint8_t)rnd(); v = (uint8_t)((v & 0x7F) | 0x80); if (rnd() % 8) v |= 0x01; if (rnd() % 3) v |= 0x02; gb_write8(ctx, 0xFF40, v); break; }   /* LCDC: screen on, mostly */
            case 1: gb_write8(ctx, 0xFF43, (uint8_t)rnd()); break;                   /* SCX */
            case 2: gb_write8(ctx, 0xFF42, (uint8_t)rnd()); break;                   /* SCY */
            case 3: gb_write8(ctx, 0xFF47, (uint8_t)rnd()); break;                   /* BGP */
            case 4: gb_write8(ctx, 0xFF48, (uint8_t)rnd()); break;                   /* OBP0 */
            case 5: gb_write8(ctx, 0xFF49, (uint8_t)rnd()); break;                   /* OBP1 */
            case 6: gb_write8(ctx, 0xFF4B, (uint8_t)(rnd() % 4 == 0 ? rnd() % 8 : rnd() % 180)); break;   /* WX */
            case 7: gb_write8(ctx, 0xFF4A, (uint8_t)(rnd() % 3 == 0 ? rnd() % 40 : rnd() % 150)); break;  /* WY */
            case 8: place_sprites(ctx, 1 + rnd() % 12, true, (ppu->lcdc & LCDC_OBJ_SIZE) != 0); break;
            case 9: place_sprites(ctx, 1 + rnd() % 3, false, false); break;
            case 10: for (unsigned k = 0; k < 4; ++k) ctx->vram[rnd() % 0x2000] = (uint8_t)rnd(); break;
            case 11: { const unsigned at = (unsigned)(rnd() % 160); for (unsigned k = 0; k < 4 && at + k < 160; ++k) ctx->oam[at + k] = (uint8_t)rnd(); break; }
            case 12: { const unsigned x = rnd() % 160; for (unsigned k = 0; k < 10; ++k) { uint8_t* e = ctx->oam + ((x + k) % 40) * 4u; e[0] = (uint8_t)((int)ppu->ly + 16 - (int)(rnd() % 8)); e[1] = (uint8_t)(rnd() % 3 == 0 ? 8 + x % 160 : 8 + x % 160 + k % 3); } break; }   /* ten on a line, some at the same x */
            default: gb_write8(ctx, 0xFF40, (uint8_t)(ppu->lcdc ^ (1u << (rnd() % 8)) | 0x80u)); break;
            }
            ++writes;
        }
        gb_run_cycles(ctx, 30u + rnd() % 2400u);
        if (ppu->ly != last_ly) {
            last_ly = ppu->ly;
            if (ppu->visible_sprite_count) ++lines_with_sprites;
        }
        if (ctx->frame_done) {
            const uint32_t* picture = gb_get_framebuffer(ctx);
            assert(picture);
            chain = fnv(chain, picture, (size_t)GB_SCREEN_WIDTH * GB_SCREEN_HEIGHT * sizeof(uint32_t));
            chain = fnv(chain, ppu->framebuffer, (size_t)GB_SCREEN_WIDTH * GB_SCREEN_HEIGHT);
            gb_reset_frame(ctx);
            ctx->stopped = 0;
            ++frames;
        }
    }
    printf("{\"ppu_span_checks\":\"%016llx\",\"frames\":%u,\"lines_with_sprites\":%u,\"writes\":%u}\n", (unsigned long long)chain, frames, lines_with_sprites, writes);
    gb_context_destroy(ctx);
    return 0;
}
