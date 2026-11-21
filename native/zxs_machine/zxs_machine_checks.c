/* ROM-free checks of the ZX Spectrum machine (zxs_machine.c), on authored images (tools/zxs_machine_selftest.py writes them).
 * MIT, Retro-Recomp. Built for a check, never into a game.
 *
 * Usage: zxs_machine_checks image48 image128 image16. Each image's RAM is authored by the tool: bank 5 holds a screen with a
 * known bitmap byte and attribute, the other banks hold their own number. The ROM is 32 KiB of a pattern (no Spectrum ROM). */
#include "zxs_machine.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int checks, failed;
static void check(const char *what, long got, long expected)
{
    ++checks;
    if (got != expected) {
        ++failed;
        printf("  FAILED %s: %ld, expected %ld\n", what, got, expected);
    }
}

static uint8_t *load(const char *path, size_t *size)
{
    FILE *f = fopen(path, "rb");
    if (!f) { printf("cannot open %s\n", path); exit(2); }
    static uint8_t buffer[3][ZXS_IMAGE_BYTES];
    static int next;
    uint8_t *into = buffer[next++];
    *size = fread(into, 1, ZXS_IMAGE_BYTES + 1, f);
    fclose(f);
    return into;
}

static ZxsMachine m;
static uint8_t rom[0x8000];

static void frames_and_irq(int model, uint32_t frame, unsigned pulse)
{
    const char *name = model == ZXS_128K ? "128K" : "48K";
    char what[96];
    uint64_t start = m.frame_start + m.t_frame;                    /* the next frame's start */
    zxs_advance(&m, start - m.cycles);
    snprintf(what, sizeof what, "%s: the frame is %u T", name, frame);
    check(what, (long)m.t_frame, (long)frame);
    snprintf(what, sizeof what, "%s: /INT is high at the frame's start", name);
    check(what, zxs_irq(&m), 1);
    zxs_advance(&m, pulse - 1);
    snprintf(what, sizeof what, "%s: /INT still high at T %u", name, pulse - 1);
    check(what, zxs_irq(&m), 1);
    zxs_advance(&m, 1);
    snprintf(what, sizeof what, "%s: /INT low at T %u", name, pulse);
    check(what, zxs_irq(&m), 0);
}

int main(int argc, char **argv)
{
    if (argc != 4) { printf("usage: zxs_machine_checks image48 image128 image16\n"); return 2; }
    for (unsigned i = 0; i < sizeof rom; ++i) rom[i] = (uint8_t)(i >> 8);    /* bank 0: 00h-3Fh, bank 1: 40h-7Fh */
    ZxsCpuStart cpu;
    size_t size;

    /* ---- 48K ---- */
    uint8_t *image = load(argv[1], &size);
    check("48K: the image loads", zxs_load_image(&m, image, size, rom, &cpu), 0);
    check("48K: PC from the image", cpu.pc, 0x8000);
    check("48K: the ROM at 0000h", zxs_read(&m, 0x1234), 0x12);
    check("48K: bank 2 at 8000h", zxs_read(&m, 0x8000), 2);
    check("48K: bank 0 at C000h", zxs_read(&m, 0xC000), 0);
    zxs_write(&m, 0x0000, 0x99);
    check("48K: the ROM is not written", zxs_read(&m, 0x0000), 0x00);
    zxs_out(&m, 0x7FFD, 0x07);
    check("48K: port 7FFDh pages nothing", zxs_read(&m, 0xC000), 0);
    frames_and_irq(ZXS_48K, 69888, 32);
    /* The keyboard: SPACE is bit 0 of half-row 7FFEh; the read of FEFEh does not see it, the read of 7FFEh does. */
    m.keys[7] &= (uint8_t)~1;
    check("48K: SPACE read on 7FFEh", zxs_in(&m, 0x7FFE) & 0x1F, 0x1E);
    check("48K: SPACE not on FEFEh", zxs_in(&m, 0xFEFE) & 0x1F, 0x1F);
    check("48K: both rows at once (7EFEh)", zxs_in(&m, 0x7EFE) & 0x1F, 0x1E);
    m.keys[7] = 0xFF;
    check("48K: no Kempston unless the image says so", zxs_in(&m, 0x001F), 0xFF);
    m.kempston_present = 1; m.kempston = 0x11;
    check("48K: Kempston fire and right", zxs_in(&m, 0x001F), 0x11);
    /* The picture: a full frame drawn; the authored screen has bitmap byte 80h at (0, 0) with ink 2, paper 5. */
    zxs_out(&m, 0x00FE, 0x01);                                     /* border blue */
    zxs_advance(&m, m.frame_start + 2 * m.t_frame - m.cycles);
    check("48K: border pixel (0, 0)", m.picture[0][0], 1);
    check("48K: border right of the paper", m.picture[ZXS_BORDER_Y + 10][ZXS_WIDTH - 1], 1);
    check("48K: paper (0, 0) is ink", m.picture[ZXS_BORDER_Y][ZXS_BORDER_X], 2);
    check("48K: paper (1, 0) is paper", m.picture[ZXS_BORDER_Y][ZXS_BORDER_X + 1], 5);
    check("48K: line 1 of the paper (bitmap +100h) is ink", m.picture[ZXS_BORDER_Y + 1][ZXS_BORDER_X + 7], 2);
    check("48K: bright cell (column 1)", m.picture[ZXS_BORDER_Y][ZXS_BORDER_X + 8], 8 + 5);
    /* Flash: the cell at column 2 has its flash bit; after 16 frames ink and paper swap. */
    uint8_t before = m.picture[ZXS_BORDER_Y][ZXS_BORDER_X + 16];
    zxs_advance(&m, (uint64_t)16 * m.t_frame);
    check("48K: flash swaps ink and paper after 16 frames", m.picture[ZXS_BORDER_Y][ZXS_BORDER_X + 16] != before, 1);
    /* The beeper: one frame with EAR high gives samples at its level, then one low gives 0; the read of FEh shows it in bit 6. */
    int16_t samples[ZXS_AUDIO_BUFFER];
    zxs_audio_take(&m, samples, ZXS_AUDIO_BUFFER);
    zxs_out(&m, 0x00FE, 0x10);
    check("48K: EAR bit read back in bit 6 (issue 3)", (zxs_in(&m, 0xFFFE) >> 6) & 1, 1);
    zxs_advance(&m, m.t_frame);
    unsigned n = zxs_audio_take(&m, samples, ZXS_AUDIO_BUFFER);
    check("48K: 880 or 881 samples a frame (69,888 T at 3.5 MHz, 44,100 Hz)", n >= 880 && n <= 881, 1);
    check("48K: a sample with EAR high is at the level", samples[n / 2] > 0, 1);
    zxs_out(&m, 0x00FE, 0x00);
    zxs_advance(&m, m.t_frame);
    n = zxs_audio_take(&m, samples, ZXS_AUDIO_BUFFER);
    check("48K: a sample with EAR low is 0", samples[n / 2], 0);

    /* ---- 128K ---- */
    image = load(argv[2], &size);
    check("128K: the image loads", zxs_load_image(&m, image, size, rom, &cpu), 0);
    check("128K: bank 3 at C000h from 7FFDh", zxs_read(&m, 0xC000), 3);
    check("128K: ROM 1 (7FFDh bit 4)", zxs_read(&m, 0x0000), 0x40);
    zxs_out(&m, 0x7FFD, 0x06);
    check("128K: bank 6 paged", zxs_read(&m, 0xC000), 6);
    check("128K: ROM 0 paged", zxs_read(&m, 0x0000), 0x00);
    zxs_write(&m, 0xC000, 0x66);
    check("128K: a write lands in bank 6", m.ram[6][0], 0x66);
    zxs_out(&m, 0x7FFD, 0x21);                                     /* bank 1, locked */
    zxs_out(&m, 0x7FFD, 0x04);
    check("128K: the lock keeps bank 1", zxs_read(&m, 0xC000), 1);
    check("128K: screen bank 5 shown", m.port_7ffd & 8, 0);
    zxs_out(&m, 0xFFFD, 0x07);
    zxs_out(&m, 0xBFFD, 0x3E);
    check("128K: AY register 7 written and read back", zxs_in(&m, 0xFFFD), 0x3E);
    frames_and_irq(ZXS_128K, 70908, 36);

    /* ---- 16K ---- */
    image = load(argv[3], &size);
    check("16K: the image loads", zxs_load_image(&m, image, size, rom, &cpu), 0);
    check("16K: nothing at 8000h", zxs_read(&m, 0x8000), 0xFF);
    zxs_write(&m, 0xC000, 0x12);
    check("16K: nothing written at C000h", zxs_read(&m, 0xC000), 0xFF);
    check("16K: bank 5 at 4000h", zxs_read(&m, 0x7FFF), 5);

    printf("CHECKS=%d FAILED=%d\n", checks, failed);
    return failed ? 1 : 0;
}
