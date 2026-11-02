/* Checks of the QSound model (native/cps1_qsound.c) on a synthetic DSP ROM and sample ROM: the busy flag after a reset and after a
 * register write, a run that is deterministic, the quick-state round trip (a loaded copy makes the very same samples as the original)
 * and the refusal of a state whose indices are out of range. Built by tools/cps1_qsound_selftest.py; no ROM of the player is used. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cps1_qsound.h"

static unsigned passed, failed;
static void expect(const char *what, int ok)
{
    if (ok) ++passed; else { ++failed; fprintf(stderr, "FAIL: %s\n", what); }
}

static uint8_t dsp_rom[CPS1_QSOUND_DSP_BYTES], samples[0x20000];

static void write_register(cps1_qsound *chip, uint8_t address, uint16_t value)
{
    cps1_qsound_write(chip, 0, (uint8_t)(value >> 8));
    cps1_qsound_write(chip, 1, (uint8_t)value);
    cps1_qsound_write(chip, 2, address);
}

static void step(cps1_qsound *chip, unsigned count, int16_t *out)
{
    for (unsigned n = 0; n < count; n++) cps1_qsound_sample(chip, out + 2 * n);
}

int main(void)
{
    /* a ROM of values that are not constant, so the tables and the samples change the output */
    for (unsigned n = 0; n < sizeof dsp_rom; n++) dsp_rom[n] = (uint8_t)(n * 37u + (n >> 8) * 11u);
    for (unsigned n = 0; n < sizeof samples; n++) samples[n] = (uint8_t)((n * 5u) ^ (n >> 7) ^ (n >> 14));
    static cps1_qsound chip;
    cps1_qsound_init(&chip, dsp_rom, samples, sizeof samples);
    static int16_t out[2 * 4096], first[2 * 4096], again[2 * 4096];

    expect("not ready right after a reset", cps1_qsound_ready(&chip) == 0);
    step(&chip, 4, out);
    expect("still busy after four samples (boot, two init samples, the filter refresh)", cps1_qsound_ready(&chip) == 0);
    step(&chip, 1, out);
    expect("ready after the fifth", cps1_qsound_ready(&chip) == 0x80);
    write_register(&chip, 0x93, 0x1234);
    expect("a register write makes it busy", cps1_qsound_ready(&chip) == 0);
    step(&chip, 1, out);
    expect("and ready again at the next sample", cps1_qsound_ready(&chip) == 0x80);

    /* a playing voice: the last voice's address register is not the voice's: the bank register of voice n sits in the slot before it */
    write_register(&chip, 0x78, 0x0000);        /* bank of voice 0 (written by the slot of voice 15) */
    write_register(&chip, 0x01, 0x0100);        /* voice 0 address */
    write_register(&chip, 0x02, 0x1000);        /* rate 1.0 */
    write_register(&chip, 0x05, 0x4000);        /* end address */
    write_register(&chip, 0x04, 0x0040);        /* loop length */
    write_register(&chip, 0x06, 0x4000);        /* volume */
    write_register(&chip, 0x80, 0x0120);        /* pan of voice 0 */
    step(&chip, 600, out);
    int nonzero = 0;
    for (unsigned n = 0; n < 1200; n++) nonzero += out[n] != 0;
    expect("a voice makes sound", nonzero > 0);

    /* the exact replay: save the state, run on, load it into another chip, run the same number of samples */
    const size_t size = cps1_qsound_state_bytes();
    uint8_t *state = malloc(size);
    expect("the state has a size", size > 4096 && state != NULL);
    expect("saving writes exactly that size", cps1_qsound_state_put(&chip, state) == size);
    step(&chip, 2000, first);
    static cps1_qsound copy;
    cps1_qsound_init(&copy, dsp_rom, samples, sizeof samples);
    expect("the state loads", cps1_qsound_state_get(&copy, state) == 1);
    step(&copy, 2000, again);
    expect("a loaded copy makes the very same 2,000 samples", memcmp(first, again, 4000 * sizeof first[0]) == 0);
    uint8_t *bad = malloc(size);
    expect("a copy of the state is made", bad != NULL && memcpy(bad, state, size) == bad);
    /* the echo write position sits after the 19 voice words and the voice tables; setting it past the line is refused */
    int refused = 0, untouched = 1;
    for (size_t offset = 0; offset + 1 < size; offset += 2) {
        memcpy(bad, state, size);
        bad[offset] = 0xff; bad[offset + 1] = 0x7f;
        cps1_qsound probe = copy;
        if (!cps1_qsound_state_get(&probe, bad)) { refused++; untouched &= memcmp(&probe, &copy, sizeof probe) == 0; }
    }
    expect("states with an index out of range are refused", refused > 20);
    expect("a refused state leaves the chip alone", untouched);
    free(state);
    free(bad);
    /* the sample ROM is mirrored like MAME's: 128 KiB repeats over the 24-bit space, a 192 KiB one is unmapped (0) up to 256 KiB and repeats from there */
    expect("a power-of-two ROM repeats over the high address bits",
           cps1_qsound_read_sample(&chip, 0, 5) == cps1_qsound_read_sample(&chip, 2, 5) && cps1_qsound_read_sample(&chip, 0, 5) == cps1_qsound_read_sample(&chip, 0x100, 5)
           && cps1_qsound_read_sample(&chip, 1, 5) == cps1_qsound_read_sample(&chip, 3, 5) && cps1_qsound_read_sample(&chip, 0, 5) != cps1_qsound_read_sample(&chip, 1, 5));
    static cps1_qsound odd;
    static uint8_t big[0x30000];
    for (unsigned n = 0; n < sizeof big; n++) big[n] = (uint8_t)(n * 7u + 1u);
    cps1_qsound_init(&odd, dsp_rom, big, sizeof big);
    expect("a ROM that is not a power of two is read inside it", cps1_qsound_read_sample(&odd, 2, 9) == (int16_t)(big[0x20009] << 8));
    expect("and reads 0 between its end and the power of two", cps1_qsound_read_sample(&odd, 3, 9) == 0);
    expect("and repeats from there", cps1_qsound_read_sample(&odd, 4, 9) == cps1_qsound_read_sample(&odd, 0, 9)
           && cps1_qsound_read_sample(&odd, 0, 9) == (int16_t)(big[9] << 8));
    printf("{\"passed\":%u,\"failed\":%u}\n", passed, failed);
    return failed ? 1 : 0;
}
