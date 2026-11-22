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
    /* The level at a later time of the same line, the machine left behind (the native loop's case). */
    uint64_t next = m.frame_start + m.t_frame;
    zxs_advance(&m, next - m.cycles);
    snprintf(what, sizeof what, "%s: /INT at the CPU's time is low at T %u, the machine still at T 0", name, pulse);
    check(what, zxs_irq_at(&m, next + pulse), 0);
    snprintf(what, sizeof what, "%s: /INT at the CPU's time is high at T %u, the machine still at T 0", name, pulse - 1);
    check(what, zxs_irq_at(&m, next + pulse - 1), 1);
    snprintf(what, sizeof what, "%s: /INT at the CPU's time is low late in the first line, the machine still at T 0", name);
    check(what, zxs_irq_at(&m, next + m.t_line - 1), 0);
}

/* Contention, from the documented numbers (docs/ZX_SPECTRUM.md): the delay 6, 5, 4, 3, 2, 1, 0, 0 by the T-state within the first
 * 128 of each of the 192 paper lines, from T-state 14335 (48K, 224 a line) or 14361 (128K, 228 a line) of the frame; 4000h-7FFFh,
 * and the 128K's odd banks at C000h; the I/O cases N:1 C:3, N:4, C:1 C:3 and C:1 x4. */
static void contention_checks(void)
{
    zxs_reset(&m, ZXS_48K, 0, rom);
    check("48K: no delay before 14335", zxs_contend_memory(&m, 14334, 0x4000), 0);
    check("48K: 6 at 14335", zxs_contend_memory(&m, 14335, 0x4000), 6);
    check("48K: 5 at 14336", zxs_contend_memory(&m, 14336, 0x5800), 5);
    check("48K: 1 at 14340", zxs_contend_memory(&m, 14340, 0x7FFF), 1);
    check("48K: 0 at 14341", zxs_contend_memory(&m, 14341, 0x4000), 0);
    check("48K: 0 at 14342", zxs_contend_memory(&m, 14342, 0x4000), 0);
    check("48K: 6 again at 14343", zxs_contend_memory(&m, 14343, 0x4000), 6);
    check("48K: 6 at 14335 + 120", zxs_contend_memory(&m, 14335 + 120, 0x4000), 6);
    check("48K: none from the 128th T-state of a line", zxs_contend_memory(&m, 14335 + 128, 0x4000), 0);
    check("48K: none in the right border", zxs_contend_memory(&m, 14335 + 223, 0x4000), 0);
    check("48K: 6 at the next line", zxs_contend_memory(&m, 14335 + 224, 0x4000), 6);
    check("48K: 6 on the last paper line", zxs_contend_memory(&m, 14335 + 191 * 224, 0x4000), 6);
    check("48K: none below the paper", zxs_contend_memory(&m, 14335 + 192 * 224, 0x4000), 0);
    check("48K: the next frame, from the frame start", zxs_contend_memory(&m, 69888 + 14335, 0x4000), 6);
    check("48K: ROM is not contended", zxs_contend_memory(&m, 14335, 0x3FFF), 0);
    check("48K: 8000h is not contended", zxs_contend_memory(&m, 14335, 0x8000), 0);
    check("48K: I/O N:1 C:3 on the ULA (high byte free)", zxs_contend_io(&m, 14334, 0x00FE), 6);
    check("48K: I/O N:4 (neither)", zxs_contend_io(&m, 14335, 0x00FF), 0);
    check("48K: I/O C:1 C:3 (contended high byte, the ULA)", zxs_contend_io(&m, 14337, 0x40FE), 4);
    check("48K: I/O C:1 x4 (contended high byte only)", zxs_contend_io(&m, 14335, 0x40FF), 12);
    check("48K: I/O outside the paper", zxs_contend_io(&m, 100, 0x40FF), 0);

    zxs_reset(&m, ZXS_128K, 0, rom);
    check("128K: no delay at 14360", zxs_contend_memory(&m, 14360, 0x4000), 0);
    check("128K: 6 at 14361", zxs_contend_memory(&m, 14361, 0x4000), 6);
    check("128K: 6 at the next line (228)", zxs_contend_memory(&m, 14361 + 228, 0x4000), 6);
    check("128K: none from the 128th T-state", zxs_contend_memory(&m, 14361 + 128, 0x4000), 0);
    check("128K: the next frame (70908)", zxs_contend_memory(&m, 70908 + 14361, 0x4000), 6);
    check("128K: bank 2 at 8000h is not contended", zxs_contend_memory(&m, 14361, 0x8000), 0);
    zxs_out(&m, 0x7FFD, 0x01);
    check("128K: bank 1 at C000h is", zxs_contend_memory(&m, 14361, 0xC000), 6);
    check("128K: and a port with its high byte there", zxs_contend_io(&m, 14361, 0xC0FF), 12);
    zxs_out(&m, 0x7FFD, 0x07);
    check("128K: bank 7 at C000h is", zxs_contend_memory(&m, 14361, 0xFFFF), 6);
    zxs_out(&m, 0x7FFD, 0x02);
    check("128K: bank 2 at C000h is not", zxs_contend_memory(&m, 14361, 0xC000), 0);
    check("128K: nor a port with its high byte there", zxs_contend_io(&m, 14361, 0xC0FF), 0);
}

/* The floating bus (an unattached port reads what the ULA fetches), from Ramsoft's floating bus guide: in each 8 T-states of the
 * first 128 of a paper line the bitmap byte, the attribute, the next bitmap byte, the next attribute, then FFh; the first fetch
 * at T-state 14347 (48K) or 14368 (128K); the I/O cycle samples the bus 3 T-states after its start and its contention. */
static uint8_t read_at(uint64_t sample, unsigned wait, uint16_t port)
{
    m.io_t = sample - 3 - wait; m.io_wait = wait;
    return zxs_in(&m, port);
}

static void floating_bus_checks(void)
{
    zxs_reset(&m, ZXS_48K, 0, rom);
    uint8_t *screen = m.ram[5];
    screen[0x0000] = 0xA1; screen[0x1800] = 0xB2; screen[0x0001] = 0xC3; screen[0x1801] = 0xD4;   /* line 0, columns 0 and 1 */
    screen[0x0002] = 0xE5; screen[0x0100] = 0x96; screen[0x0020] = 0x87; screen[0x1820] = 0x78;   /* column 2; lines 1 and 8 */
    check("48K floating bus: FFh before the first fetch", read_at(14346, 0, 0x00FF), 0xFF);
    check("48K floating bus: the bitmap at 14347", read_at(14347, 0, 0x00FF), 0xA1);
    check("48K floating bus: its attribute at 14348", read_at(14348, 0, 0x00FF), 0xB2);
    check("48K floating bus: the next bitmap at 14349", read_at(14349, 0, 0x00FF), 0xC3);
    check("48K floating bus: the next attribute at 14350", read_at(14350, 0, 0x00FF), 0xD4);
    check("48K floating bus: FFh in the idle half", read_at(14351, 0, 0x00FF), 0xFF);
    check("48K floating bus: column 2 at 14355", read_at(14355, 0, 0x00FF), 0xE5);
    check("48K floating bus: line 1 at 14347 + 224", read_at(14347 + 224, 0, 0x00FF), 0x96);
    check("48K floating bus: line 8 at 14347 + 8 x 224", read_at(14347 + 8 * 224, 0, 0x00FF), 0x87);
    check("48K floating bus: line 8's attribute", read_at(14348 + 8 * 224, 0, 0x00FF), 0x78);
    check("48K floating bus: FFh in the right border", read_at(14347 + 128, 0, 0x00FF), 0xFF);
    check("48K floating bus: FFh below the paper", read_at(14347 + 192 * 224, 0, 0x00FF), 0xFF);
    check("48K floating bus: the contention delays the sample", read_at(14347, 4, 0x40FF), 0xA1);
    check("48K floating bus: the next frame", read_at(69888 + 14347, 0, 0x00FF), 0xA1);
    check("48K floating bus: port 1Fh floats without a Kempston", read_at(14347, 0, 0x001F), 0xA1);
    check("48K floating bus: the ULA's port reads the keyboard", read_at(14347, 0, 0x00FE) & 0x1F, 0x1F);
    check("48K floating bus: the Fuller port floats without a Fuller box", read_at(14347, 0, 0x017F), 0xA1);
    m.fuller_present = 1;
    check("48K: a Fuller box present and idle reads FFh in the paper", read_at(14347, 0, 0x017F), 0xFF);
    check("48K: and its port is 7Fh only", read_at(14347, 0, 0x01FF), 0xA1);
    m.fuller_present = 0;
    zxs_reset(&m, ZXS_128K, 0, rom);
    m.ram[5][0x0000] = 0x5A; m.ram[7][0x0000] = 0x7A;
    check("128K floating bus: FFh at 14367", read_at(14367, 0, 0x00FF), 0xFF);
    check("128K floating bus: the bitmap at 14368", read_at(14368, 0, 0x00FF), 0x5A);
    check("128K floating bus: line 1 at 14368 + 228", read_at(14368 + 228, 0, 0x00FF), m.ram[5][0x0100]);
    zxs_out(&m, 0x7FFD, 0x08);
    check("128K floating bus: the shadow screen (bank 7)", read_at(14368, 0, 0x00FF), 0x7A);
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
    /* The AY's tone A at full volume (period 100: 1,773,450 / 1,600 = 1,108 Hz) sounds; mute (mixer FFh) gives silence. */
    {
        static const uint8_t tone[][2] = {{0, 100}, {1, 0}, {7, 0x3E}, {8, 15}};
        for (unsigned i = 0; i < 4; ++i) { zxs_out(&m, 0xFFFD, tone[i][0]); zxs_out(&m, 0xBFFD, tone[i][1]); }
        int16_t buffer[ZXS_AUDIO_BUFFER];
        zxs_audio_take(&m, buffer, ZXS_AUDIO_BUFFER);
        zxs_advance(&m, m.t_frame);
        unsigned count = zxs_audio_take(&m, buffer, ZXS_AUDIO_BUFFER), low = 0, high = 0, flips = 0;
        for (unsigned i = 0; i < count; ++i) {
            low += buffer[i] < 1000; high += buffer[i] > 5000;
            if (i && (buffer[i] > 3000) != (buffer[i - 1] > 3000)) ++flips;
        }
        check("128K: the AY tone has low and high samples", low > 100 && high > 100, 1);
        check("128K: 1,108 Hz is about 44 edges in a frame (3,200 T a period)", flips >= 40 && flips <= 48, 1);
        /* A channel whose tone and noise are off outputs its volume as a steady level: volume 0 is silence. */
        zxs_out(&m, 0xFFFD, 7); zxs_out(&m, 0xBFFD, 0xFF);
        zxs_advance(&m, m.t_frame);
        count = zxs_audio_take(&m, buffer, ZXS_AUDIO_BUFFER);
        check("128K: tone and noise off: the volume as a steady level", buffer[count / 2], 6000);
        zxs_out(&m, 0xFFFD, 8); zxs_out(&m, 0xBFFD, 0x00);
        zxs_advance(&m, m.t_frame);
        zxs_audio_take(&m, buffer, ZXS_AUDIO_BUFFER);
        zxs_advance(&m, m.t_frame);
        count = zxs_audio_take(&m, buffer, ZXS_AUDIO_BUFFER);
        check("128K: volume 0 is silent", buffer[count / 2], 0);
    }
    frames_and_irq(ZXS_128K, 70908, 36);

    /* ---- 16K ---- */
    image = load(argv[3], &size);
    check("16K: the image loads", zxs_load_image(&m, image, size, rom, &cpu), 0);
    check("16K: nothing at 8000h", zxs_read(&m, 0x8000), 0xFF);
    zxs_write(&m, 0xC000, 0x12);
    check("16K: nothing written at C000h", zxs_read(&m, 0xC000), 0xFF);
    check("16K: bank 5 at 4000h", zxs_read(&m, 0x7FFF), 5);

    contention_checks();
    floating_bus_checks();
    printf("CHECKS=%d FAILED=%d\n", checks, failed);
    return failed ? 1 : 0;
}
