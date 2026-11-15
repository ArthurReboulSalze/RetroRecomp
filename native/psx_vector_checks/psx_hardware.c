/* The hardware tests of JaCzekanski/ps1-tests run on the PlayStation machine (gate G11 evidence; tools/psx_hardware_selftest.py).
 * Original Retro-Recomp code, MIT; linked with Beetle PSX (GPL-2.0), the program is GPL-2.0 as a whole. Never part of a game.
 *
 *   psx_hardware --pack FILE --frames N --tty FILE --vram FILE [--bios FILE]
 *
 * Runs the pack's program (a PS-X EXE named as the pack's disc: Beetle loads it after the BIOS's start-up) for N frames with no
 * input, and writes what the program printed through the BIOS (std_out_putchar, B(3Dh): the character in a0 when the CPU
 * reaches 0xB0 with t1 = 0x3D; the observing build's step hook sees every fetch) and the 1024x512 VRAM at the end, as
 * little-endian 16-bit words. Exit 0, or 2 with a reason on stderr. */
#include "psx_session.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "mednafen/psx/gpu.h"

extern PS_GPU GPU;
void rr_psx_cpu_registers(uint32_t out[41]);

static FILE *tty;

/* The observing build's hook: every instruction the interpreter fetches. */
void rr_psx_observe(uint32_t pc, uint32_t word) {
    (void)word;
    if (!tty || (pc & 0x1FFFFFFFu) != 0xB0u) return;
    uint32_t r[41];
    rr_psx_cpu_registers(r);
    if (r[9] == 0x3Du) fputc((int)(r[4] & 0xFFu), tty);
}
int rr_psx_observe_write(FILE *f) { (void)f; return 1; }

int main(int argc, char **argv) {
    const char *pack = NULL, *tty_path = NULL, *vram_path = NULL, *bios_path = NULL;
    long frames = 0;
    for (int i = 1; i + 1 < argc; i += 2) {
        if (!strcmp(argv[i], "--pack")) pack = argv[i + 1];
        else if (!strcmp(argv[i], "--frames")) frames = atol(argv[i + 1]);
        else if (!strcmp(argv[i], "--tty")) tty_path = argv[i + 1];
        else if (!strcmp(argv[i], "--vram")) vram_path = argv[i + 1];
        else if (!strcmp(argv[i], "--bios")) bios_path = argv[i + 1];
    }
    if (!pack || !tty_path || !vram_path || frames <= 0) { fprintf(stderr, "usage: psx_hardware --pack F --frames N --tty F --vram F\n"); return 2; }
    if (!(tty = fopen(tty_path, "wb"))) { fprintf(stderr, "cannot write %s\n", tty_path); return 2; }
    char error[256] = {0};
    /* The player's BIOS (Beetle starts a PS-X EXE through the console's BIOS; the free OpenBIOS runs its own shell instead). */
    static uint8_t bios[RR_PSX_BIOS_BYTES];
    if (bios_path) {
        FILE *b = fopen(bios_path, "rb");
        if (!b || fread(bios, 1, sizeof bios, b) != sizeof bios) { fprintf(stderr, "cannot read the BIOS %s\n", bios_path); return 2; }
        fclose(b);
    }
    RrPsxGame game = {pack, bios_path ? bios : NULL, NULL, 0};
    RrPsxSession *s = rr_psx_open(&game, error, sizeof error);
    if (!s) { fprintf(stderr, "%s\n", error); return 2; }
    for (long n = 0; n < frames; n++)
        if (rr_psx_frame(s) != 0) { fprintf(stderr, "%s\n", rr_psx_error(s)); return 2; }
    const unsigned shift = GPU_get_upscale_shift();
    FILE *v = fopen(vram_path, "wb");
    if (!v || !GPU.vram) { fprintf(stderr, "cannot write %s\n", vram_path); return 2; }
    for (unsigned y = 0; y < 512; y++)
        for (unsigned x = 0; x < 1024; x++) {
            const uint16_t p = GPU.vram[((size_t)(y << shift) << (10 + shift)) + (x << shift)];
            const uint8_t b[2] = {(uint8_t)p, (uint8_t)(p >> 8)};
            fwrite(b, 1, 2, v);
        }
    int ok = fclose(v) == 0;
    ok = (fclose(tty) == 0) && ok;
    rr_psx_close(s);
    return ok ? 0 : 2;
}
