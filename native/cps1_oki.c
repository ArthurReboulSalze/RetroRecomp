/* OKI MSM6295; see cps1_oki.h for provenance. */
#include "cps1_oki.h"
#include <string.h>

/* floor(16 * 1.1^step) for steps 0..48, as computed by MAME's okiadpcm.cpp;
 * stored as constants so no libm rounding can differ between hosts. */
static const int16_t step_size[49] = {
    16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97,
    107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449,
    494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552};
static const int8_t index_shift[8] = {-1, -1, -1, -1, 2, 4, 6, 8};
/* Volume table numerators over 0x20 (0 dB down to -24 dB, then silence). */
static const int8_t volume_table[16] = {0x20, 0x16, 0x10, 0x0b, 0x08, 0x06, 0x04, 0x03, 0x02, 0, 0, 0, 0, 0, 0, 0};

static uint8_t rom_byte(const cps1_oki *chip, uint32_t address)
{
    return address < chip->rom_size ? chip->rom[address] : 0;
}

void cps1_oki_init(cps1_oki *chip, const uint8_t *rom, size_t rom_size, int pin7)
{
    memset(chip, 0, sizeof *chip);
    chip->rom = rom; chip->rom_size = rom_size;
    chip->pin7 = pin7 ? 1 : 0;
    chip->command = -1;
}

void cps1_oki_reset(cps1_oki *chip)
{
    for (int i = 0; i < 4; i++) chip->voice[i].playing = 0;
}

unsigned cps1_oki_divider(const cps1_oki *chip)
{
    return chip->pin7 ? 132u : 165u;
}

uint8_t cps1_oki_status(const cps1_oki *chip)
{
    uint8_t result = 0xf0;
    for (int i = 0; i < 4; i++)
        if (chip->voice[i].playing) result |= (uint8_t)(1 << i);
    return result;
}

void cps1_oki_write(cps1_oki *chip, uint8_t command)
{
    if (chip->command != -1) {
        int mask = command >> 4;
        for (int i = 0; i < 4; i++, mask >>= 1) {
            if (!(mask & 1) || chip->voice[i].playing) continue;
            uint32_t base = (uint32_t)chip->command * 8;
            uint32_t start = ((uint32_t)rom_byte(chip, base) << 16 | (uint32_t)rom_byte(chip, base + 1) << 8 |
                              rom_byte(chip, base + 2)) & 0x3ffff;
            uint32_t stop = ((uint32_t)rom_byte(chip, base + 3) << 16 | (uint32_t)rom_byte(chip, base + 4) << 8 |
                             rom_byte(chip, base + 5)) & 0x3ffff;
            if (start < stop) {
                cps1_oki_voice *voice = &chip->voice[i];
                voice->playing = 1;
                voice->base = start;
                voice->sample = 0;
                voice->count = 2 * (stop - start + 1);
                voice->signal = 0;
                voice->step = 0;
                voice->volume = volume_table[command & 0x0f];
            }
        }
        chip->command = -1;
    } else if (command & 0x80) {
        chip->command = command & 0x7f;
    } else {
        int mask = command >> 3;
        for (int i = 0; i < 4; i++, mask >>= 1)
            if (mask & 1) chip->voice[i].playing = 0;
    }
}

int32_t cps1_oki_sample(cps1_oki *chip)
{
    int32_t sum = 0;
    for (int i = 0; i < 4; i++) {
        cps1_oki_voice *voice = &chip->voice[i];
        if (!voice->playing) continue;
        int nibble = rom_byte(chip, voice->base + voice->sample / 2) >> (((voice->sample & 1) << 2) ^ 4);
        int step = step_size[voice->step];
        int diff = step / 8;
        if (nibble & 4) diff += step;
        if (nibble & 2) diff += step / 2;
        if (nibble & 1) diff += step / 4;
        voice->signal += (nibble & 8) ? -diff : diff;
        if (voice->signal > 2047) voice->signal = 2047;
        else if (voice->signal < -2048) voice->signal = -2048;
        voice->step += index_shift[nibble & 7];
        if (voice->step > 48) voice->step = 48;
        else if (voice->step < 0) voice->step = 0;
        sum += voice->signal * voice->volume;
        if (++voice->sample >= voice->count) voice->playing = 0;
    }
    return sum;
}
