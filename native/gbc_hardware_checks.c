/* Authored checks of the colour hardware of the Game Boy engine (Game Boy Color profile, docs/GAME_BOY_COLOR.md). No cartridge bytes: a 32 KiB image with a
 * Color-enhanced header and two tiny programs written here, and a host that drives the registers the way a game's code does. The expectations are the ones of
 * Pan Docs (the register pages of the colour hardware): they are **documentation, not a console**: they prove that the engine does what the page says, never
 * that a real Game Boy Color does. Built and run by tools/gameboy_color_selftest.py on the runtime as the converter adapts it for the Color.
 * Checked: the seven work-RAM banks (SVBK), the second video bank (VBK), the palette ports with their auto-increment (BCPS/BCPD, OCPS/OCPD), the
 * general-purpose and the horizontal-blank HDMA, the speed switch (KEY1 and STOP) and the length of a frame in double speed, the registers that read as 1 in
 * colour mode. Printed: one JSON line with the number of checks of each group; any failed check stops the program. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbrt.h"
#include "ppu.h"
#include "audio.h"

static uint8_t rom_image[0x8000];
static unsigned checks_run;

void gb_dispatch(GBContext* ctx, uint16_t addr) {
    const uint8_t saved = ctx->single_step_mode;
    ctx->single_step_mode = 1;
    gb_interpret(ctx, addr);
    ctx->single_step_mode = saved;
}

static void on_audio(GBContext* ctx, int16_t left, int16_t right) { (void)ctx; (void)left; (void)right; }

#define CHECK(condition) do { ++checks_run; if (!(condition)) { fprintf(stderr, "check failed: %s (line %d)\n", #condition, __LINE__); exit(1); } } while (0)

static GBContext* fresh(const uint8_t* program, size_t length) {
    memset(rom_image, 0, sizeof rom_image);
    rom_image[0x100] = 0x00; rom_image[0x101] = 0xC3; rom_image[0x102] = 0x50; rom_image[0x103] = 0x01;
    memcpy(rom_image + 0x134, "COLOR CHECKS", 12);
    rom_image[0x143] = 0x80;                                    /* Color-enhanced */
    memcpy(rom_image + 0x150, program, length);
    GBConfig config;
    memset(&config, 0, sizeof config);
    config.model = GB_MODEL_CGB;
    config.enable_audio = true; config.enable_serial = true; config.speed_percent = 100;
    config.ignore_rtc_persistence = true;
    GBContext* ctx = gb_context_create(&config);
    CHECK(ctx && gb_context_load_rom(ctx, rom_image, sizeof rom_image));
    ctx->callbacks.on_audio_sample = on_audio;
    gb_context_reset(ctx, true);
    ctx->pc = 0x150; ctx->halted = 0; ctx->ime = 0; ctx->ime_pending = 0;
    CHECK(ctx->config.model == GB_MODEL_CGB && !ctx->config.cgb_compatibility_mode);     /* the colour hardware in colour mode */
    return ctx;
}

static void lcd_off(GBContext* ctx) { gb_write8(ctx, 0xFF40, 0x00); }

static void work_ram_banks(void) {
    static const uint8_t halt[] = { 0xF3, 0x18, 0xFE };           /* DI ; JR -2 */
    GBContext* ctx = fresh(halt, sizeof halt);
    for (unsigned bank = 1; bank <= 7; ++bank) {
        gb_write8(ctx, 0xFF70, (uint8_t)bank);
        gb_write8(ctx, 0xD000, (uint8_t)(0x10 + bank));
        gb_write8(ctx, 0xDFFF, (uint8_t)(0x20 + bank));
    }
    for (unsigned bank = 1; bank <= 7; ++bank) {
        gb_write8(ctx, 0xFF70, (uint8_t)bank);
        CHECK(gb_read8(ctx, 0xD000) == 0x10 + bank);
        CHECK(gb_read8(ctx, 0xDFFF) == 0x20 + bank);
        CHECK((gb_read8(ctx, 0xFF70) & 0x07) == bank);
    }
    gb_write8(ctx, 0xFF70, 0);                                   /* bank 0 selects bank 1 at $D000 */
    CHECK(gb_read8(ctx, 0xD000) == 0x11);
    gb_write8(ctx, 0xFF70, 3); gb_write8(ctx, 0xC000, 0x99); gb_write8(ctx, 0xC800, 0x77);
    gb_write8(ctx, 0xFF70, 5);                                   /* $C000-$CFFF is always bank 0 */
    CHECK(gb_read8(ctx, 0xC000) == 0x99 && gb_read8(ctx, 0xC800) == 0x77);
    gb_write8(ctx, 0xFF70, 6);                                   /* the echo of $C000 shows bank 0, of $D000 the selected bank */
    CHECK(gb_read8(ctx, 0xE000) == 0x99);
    CHECK(gb_read8(ctx, 0xF000) == 0x16);
    gb_context_destroy(ctx);
}

static void video_banks(void) {
    static const uint8_t halt[] = { 0xF3, 0x18, 0xFE };
    GBContext* ctx = fresh(halt, sizeof halt);
    lcd_off(ctx);
    gb_write8(ctx, 0xFF4F, 0); gb_write8(ctx, 0x8000, 0xA5); gb_write8(ctx, 0x9FFF, 0x5A);
    gb_write8(ctx, 0xFF4F, 1); gb_write8(ctx, 0x8000, 0x3C); gb_write8(ctx, 0x9FFF, 0xC3);
    CHECK(gb_read8(ctx, 0xFF4F) == 0xFF);                         /* bits 7 to 1 read as 1 */
    CHECK(gb_read8(ctx, 0x8000) == 0x3C && gb_read8(ctx, 0x9FFF) == 0xC3);
    gb_write8(ctx, 0xFF4F, 0);
    CHECK(gb_read8(ctx, 0xFF4F) == 0xFE);
    CHECK(gb_read8(ctx, 0x8000) == 0xA5 && gb_read8(ctx, 0x9FFF) == 0x5A);
    gb_write8(ctx, 0xFF4F, 0xFE);                                 /* only bit 0 counts */
    CHECK(gb_read8(ctx, 0x8000) == 0xA5);
    gb_context_destroy(ctx);
}

static void palette_ports(void) {
    static const uint8_t halt[] = { 0xF3, 0x18, 0xFE };
    GBContext* ctx = fresh(halt, sizeof halt);
    lcd_off(ctx);
    for (unsigned port = 0; port < 2; ++port) {                   /* 0: background (BCPS/BCPD), 1: objects (OCPS/OCPD) */
        const uint16_t index = port ? 0xFF6A : 0xFF68, data = port ? 0xFF6B : 0xFF69;
        gb_write8(ctx, index, 0x80);                              /* index 0, auto-increment on */
        for (unsigned i = 0; i < 64; ++i) gb_write8(ctx, data, (uint8_t)(i * 3 + port));
        CHECK((gb_read8(ctx, index) & 0x3F) == 0);                /* 64 writes wrapped the index */
        for (unsigned i = 0; i < 64; ++i) {
            gb_write8(ctx, index, (uint8_t)i);                    /* auto-increment off: the index stays */
            CHECK(gb_read8(ctx, data) == (uint8_t)(i * 3 + port));
            CHECK((gb_read8(ctx, index) & 0x3F) == i);
        }
        gb_write8(ctx, index, 0x80 | 10);
        gb_write8(ctx, data, 0xEE);
        CHECK((gb_read8(ctx, index) & 0x3F) == 11);               /* a write advances it */
        (void)gb_read8(ctx, data);
        CHECK((gb_read8(ctx, index) & 0x3F) == 11);               /* a read does not */
    }
    gb_context_destroy(ctx);
}

static void hdma(void) {
    static const uint8_t halt[] = { 0xF3, 0x18, 0xFE };
    GBContext* ctx = fresh(halt, sizeof halt);
    lcd_off(ctx);
    for (unsigned i = 0; i < 0x40; ++i) gb_write8(ctx, (uint16_t)(0xC000 + i), (uint8_t)(0x40 + i));
    gb_write8(ctx, 0xFF4F, 0);
    /* general purpose: four blocks of sixteen bytes, at once */
    gb_write8(ctx, 0xFF51, 0xC0); gb_write8(ctx, 0xFF52, 0x00); gb_write8(ctx, 0xFF53, 0x80); gb_write8(ctx, 0xFF54, 0x00);
    gb_write8(ctx, 0xFF55, 0x03);
    gb_run_cycles(ctx, 4000);
    for (unsigned i = 0; i < 0x40; ++i) CHECK(gb_read8(ctx, (uint16_t)(0x8000 + i)) == 0x40 + i);
    CHECK(gb_read8(ctx, 0xFF55) == 0xFF);                         /* finished */
    /* horizontal blank, to the second video bank: two blocks, one per line while the screen is on */
    for (unsigned i = 0; i < 0x20; ++i) gb_write8(ctx, (uint16_t)(0xC100 + i), (uint8_t)(0x90 + i));
    gb_write8(ctx, 0xFF4F, 1);
    gb_write8(ctx, 0xFF51, 0xC1); gb_write8(ctx, 0xFF52, 0x00); gb_write8(ctx, 0xFF53, 0x81); gb_write8(ctx, 0xFF54, 0x00);
    gb_write8(ctx, 0xFF40, 0x91);                                 /* screen on */
    gb_write8(ctx, 0xFF55, 0x81);
    CHECK((gb_read8(ctx, 0xFF55) & 0x80) == 0);                   /* active: bit 7 clear, the blocks left in the low bits */
    CHECK((gb_read8(ctx, 0xFF55) & 0x7F) == 1);
    gb_run_cycles(ctx, 70224);                                    /* a frame */
    CHECK(gb_read8(ctx, 0xFF55) == 0xFF);
    gb_write8(ctx, 0xFF40, 0x00);
    for (unsigned i = 0; i < 0x20; ++i) CHECK(gb_read8(ctx, (uint16_t)(0x8100 + i)) == 0x90 + i);
    gb_write8(ctx, 0xFF4F, 0);                                    /* the first bank was not touched */
    CHECK(gb_read8(ctx, 0x8100) != 0x90);
    gb_context_destroy(ctx);
}

/* The steps a timer counts in one frame (the clock of 1,024 CPU cycles a step, which cannot overflow in a frame): the divider and the timers run on
 * the CPU clock, so the same frame, which is the video unit's 70,224 dots, holds twice the steps in double speed. */
static unsigned timer_steps_in_a_frame(GBContext* ctx) {
    gb_reset_frame(ctx);
    while (!ctx->frame_done) gb_run_cycles(ctx, 4096);             /* to a frame boundary */
    gb_reset_frame(ctx);
    gb_write8(ctx, 0xFF05, 0);                                     /* TIMA */
    gb_write8(ctx, 0xFF06, 0);
    gb_write8(ctx, 0xFF07, 0x04);                                  /* on, 1,024 cycles a step */
    while (!ctx->frame_done) gb_run_cycles(ctx, 256);
    const unsigned steps = gb_read8(ctx, 0xFF05);
    gb_write8(ctx, 0xFF07, 0x00);
    gb_reset_frame(ctx);
    return steps;
}

static void speed_switch(void) {
    /* LD A,1 ; LDH ($4D),A ; STOP ; JR -2 : prepare the switch and execute STOP */
    static const uint8_t program[] = { 0x3E, 0x01, 0xE0, 0x4D, 0x10, 0x00, 0x18, 0xFE };
    static const uint8_t halt[] = { 0xF3, 0x18, 0xFE };
    GBContext* ctx = fresh(halt, sizeof halt);
    gb_write8(ctx, 0xFF40, 0x91);
    CHECK(gb_read8(ctx, 0xFF4D) == 0x7E);                         /* single speed, no switch armed */
    const unsigned normal = timer_steps_in_a_frame(ctx);
    CHECK(ctx->cgb_double_speed == 0);
    CHECK(normal >= 67 && normal <= 69);                          /* 70,224 cycles at 1,024 a step */
    gb_context_destroy(ctx);

    ctx = fresh(program, sizeof program);
    gb_write8(ctx, 0xFF40, 0x91);
    for (unsigned i = 0; i < 200 && !ctx->cgb_double_speed; ++i) gb_run_cycles(ctx, 4096);
    CHECK(ctx->cgb_double_speed == 1);                            /* the program's STOP switched the speed */
    CHECK((gb_read8(ctx, 0xFF4D) & 0x80) != 0);                   /* KEY1 bit 7: double speed */
    CHECK((gb_read8(ctx, 0xFF4D) & 0x01) == 0);                   /* the armed bit is spent */
    const unsigned doubled = timer_steps_in_a_frame(ctx);
    CHECK(doubled >= 136 && doubled <= 138);                      /* the same frame holds twice the CPU cycles */
    gb_context_destroy(ctx);
}

static void colour_mode_registers(void) {
    static const uint8_t halt[] = { 0xF3, 0x18, 0xFE };
    GBContext* ctx = fresh(halt, sizeof halt);
    CHECK((gb_read8(ctx, 0xFF4D) & 0x7E) == 0x7E);                /* KEY1: bits 6 to 1 read as 1 */
    CHECK((gb_read8(ctx, 0xFF70) & 0xF8) == 0xF8);                /* SVBK: bits 7 to 3 read as 1 */
    CHECK((gb_read8(ctx, 0xFF4F) & 0xFE) == 0xFE);                /* VBK */
    gb_context_destroy(ctx);
}

int main(void) {
    work_ram_banks();
    const unsigned banks = checks_run;
    video_banks();
    const unsigned video = checks_run - banks;
    palette_ports();
    const unsigned palettes = checks_run - banks - video;
    hdma();
    const unsigned dma = checks_run - banks - video - palettes;
    speed_switch();
    colour_mode_registers();
    const unsigned rest = checks_run - banks - video - palettes - dma;
    printf("{\"gbc_hardware_checks\":{\"work_ram_banks\":%u,\"video_banks\":%u,\"palette_ports\":%u,\"hdma\":%u,\"speed_and_registers\":%u,\"total\":%u}}\n",
           banks, video, palettes, dma, rest, checks_run);
    return 0;
}
