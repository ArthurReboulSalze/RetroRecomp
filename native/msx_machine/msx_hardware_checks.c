/* MSX hardware fixtures: the TMS9918A picture and flags, the AY-3-8910 sound, the key click. MIT, Retro-Recomp.
 * A development check (tools/msx_reference.py), never built into a game. Each fixture programs the chips through
 * their I/O ports on a fresh machine, runs whole lines, and compares with values worked out by hand from the
 * TMS9918A and AY-3-8910 data manuals (the expected number is written next to each check). Prints one line per check
 * and exits 1 if any fails. */
#include "msx_machine.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static MsxMachine m;
static int failures;

static void check(const char *name, long got, long want)
{
    printf("%s %s: %ld (expected %ld)\n", got == want ? "ok  " : "FAIL", name, got, want);
    failures += got != want;
}

static void check_range(const char *name, double got, double low, double high)
{
    int ok = got >= low && got <= high;
    printf("%s %s: %.3f (expected %.3f to %.3f)\n", ok ? "ok  " : "FAIL", name, got, low, high);
    failures += !ok;
}

static void reg(int r, uint8_t v) { msx_out(&m, 0x99, v); msx_out(&m, 0x99, (uint8_t)(0x80 | r)); }

static void poke(uint16_t address, const uint8_t *bytes, int n)
{
    msx_out(&m, 0x99, (uint8_t)(address & 0xFF));
    msx_out(&m, 0x99, (uint8_t)(0x40 | (address >> 8)));
    for (int i = 0; i < n; ++i) msx_out(&m, 0x98, bytes[i]);
}

static void poke1(uint16_t address, uint8_t value) { poke(address, &value, 1); }

static void frame(void) { msx_advance(&m, (uint64_t)MSX_CYCLES_PER_LINE * MSX_LINES_NTSC); }

static uint8_t px(int x, int y) { return m.vdp.frame[y][x]; }

/* Graphic 1, names 1800h, colours 2000h, patterns 0000h, sprite attributes 1B00h, sprite patterns 3800h, backdrop 4,
 * all names 0 (pattern 0 empty, colour byte 00h: the backdrop), the sprite list ended at entry 0. */
static void fresh(uint8_t r1)
{
    msx_init(&m, MSX_LINES_NTSC);
    reg(0, 0x00); reg(1, r1); reg(2, 0x06); reg(3, 0x80); reg(4, 0x00); reg(5, 0x36); reg(6, 0x07); reg(7, 0x04);
    poke1(0x1B00, 208);
}

static void sprite(int n, uint8_t y, uint8_t x, uint8_t pattern, uint8_t colour)
{
    uint8_t a[4] = { y, x, pattern, colour };
    poke((uint16_t)(0x1B00 + n * 4), a, 4);
}

static void video_checks(void)
{
    /* Graphic 1: name 1 at (0,0), its pattern row 0 = 80h, colours F0h for names 0-7. */
    fresh(0x40);
    poke1(0x1800, 1); poke1(0x0008, 0x80); poke1(0x2000, 0xF0);
    frame();
    check("graphic 1: foreground pixel (0,0)", px(0, 0), 15);
    check("graphic 1: background colour 0 shows the backdrop (1,0)", px(1, 0), 4);
    check("graphic 1: pattern row 1 empty (0,1)", px(0, 1), 4);
    check("graphic 1: border colour of line 0", m.vdp.border[0], 4);
    poke1(0x1800 + 32 + 1, 9); poke1(9 * 8, 0x80); poke1(0x2001, 0x70);   /* name 9: second colour byte, second row */
    frame();
    check("graphic 1: name 9 at column 1, row 1 takes colour byte 1 (8,8)", px(8, 8), 7);

    /* Graphic 2 with the table masks: R#3 = 9Fh and R#4 = 00h make the lower thirds reuse the first third's tables. */
    fresh(0x40);
    reg(0, 0x02); reg(3, 0x9F); reg(4, 0x00);
    poke1(0x1800 + 16 * 32, 5); poke1(5 * 8, 0xFF); poke1(0x2000 + 5 * 8, 0x20);
    frame();
    check("graphic 2 masked: third 2 draws from third 0's pattern and colour (0,128)", px(0, 128), 2);
    reg(3, 0xFF); reg(4, 0x03);
    poke1(0x1028, 0x80); poke1(0x3028, 0x30);   /* third 2, name 5: its own pattern 1028h and colour 3028h */
    frame();
    check("graphic 2 unmasked: third 2 reads its own pattern and colour (0,128)", px(0, 128), 3);
    /* TMS99xx: R#3's low five bits also mask pattern address bits 6-10. R#3 = 80h, R#4 = 03h, name 45h in third 2:
     * pattern 1228h masked to 1028h, colour 2000h | (1228h & 3Fh) = 2028h. */
    reg(3, 0x80);
    poke1(0x1800 + 16 * 32, 0x45); poke1(0x1028, 0xFF); poke1(0x1228, 0x00); poke1(0x2028, 0x50);
    frame();
    check("graphic 2: R#3's low bits mask the pattern address too (0,128)", px(0, 128), 5);

    /* Text 1: names 0000h, patterns 0800h, colours from R#7 = F4h; 40 columns of 6 pixels from x = 8. */
    fresh(0x50);
    reg(2, 0x00); reg(4, 0x01); reg(7, 0xF4);
    poke1(0x0000, 2); poke1(0x0027, 2); poke1(0x0800 + 2 * 8, 0x84);
    frame();
    check("text 1: left border (5,0)", px(5, 0), 4);
    check("text 1: first pixel of column 0 at x = 6 (6,0)", px(6, 0), 15);
    check("text 1: bit 2 of the pattern is the sixth pixel (11,0)", px(11, 0), 15);
    check("text 1: the next column starts at x = 12 (12,0)", px(12, 0), 4);
    check("text 1: column 39 starts at x = 240 (240,0)", px(240, 0), 15);
    check("text 1: column 39's sixth pixel (245,0)", px(245, 0), 15);
    reg(7, 0xF6);
    frame();
    check("text 1: right border from x = 246, backdrop 6 (246,0)", px(246, 0), 6);

    /* Multicolor: name 3 at (0,0); pattern byte 3*8 + 0 = 9Ah gives colours 9 and 10 for lines 0-3. */
    fresh(0x48);
    poke1(0x1800, 3); poke1(0x1800 + 32, 3); poke1(24, 0x9A); poke1(26, 0xC0);
    frame();
    check("multicolor: left block (0,0)", px(0, 0), 9);
    check("multicolor: right block (4,0)", px(4, 0), 10);
    check("multicolor: next block row reads byte 25, empty (0,4)", px(0, 4), 4);
    check("multicolor: name row 1 reads byte 3 x 8 + 2 (0,8)", px(0, 8), 12);

    /* Sprites, 8 x 8: pattern 0 row 0 = 80h (one pixel), pattern 1 row 0 = FFh. Y = 9 shows from line 10. */
    fresh(0x40);
    poke1(0x3800, 0x80); poke1(0x3808, 0xFF);
    sprite(0, 9, 20, 0, 6); poke1(0x1B04, 208);
    frame();
    check("sprite: drawn one line below its Y (20,10)", px(20, 10), 6);
    check("sprite: nothing on line Y (20,9)", px(20, 9), 4);
    check("sprite: one pixel wide (21,10)", px(21, 10), 4);
    sprite(0, 9, 40, 0, 0x86);
    frame();
    check("sprite: early clock moves it 32 pixels left (8,10)", px(8, 10), 6);
    sprite(0, 255, 20, 0, 6);
    frame();
    check("sprite: Y = 255 shows on line 0 (20,0)", px(20, 0), 6);

    fresh(0x41);                               /* magnified */
    poke1(0x3800, 0x80);
    sprite(0, 9, 20, 0, 6); poke1(0x1B04, 208);
    frame();
    check("magnified: pixel doubled across (21,10)", px(21, 10), 6);
    check("magnified: pixel doubled down (20,11)", px(20, 11), 6);
    check("magnified: pattern row 1 starts at line 12 (20,12)", px(20, 12), 4);

    fresh(0x42);                               /* 16 x 16: pattern 5 masked to 4, right half row 0 = 01h */
    poke1(0x3800 + 4 * 8 + 16, 0x01);
    sprite(0, 9, 20, 5, 6); poke1(0x1B04, 208);
    frame();
    check("16 x 16: right half's last pixel (35,10)", px(35, 10), 6);

    /* Five sprites on one line: four drawn, the fifth-sprite flag with number 4. */
    fresh(0x40);
    poke1(0x3800, 0x80);
    for (int i = 0; i < 5; ++i) sprite(i, 9, (uint8_t)(i * 10), 0, 6);
    poke1(0x1B00 + 5 * 4, 208);
    frame();
    check("four per line: the fourth is drawn (30,10)", px(30, 10), 6);
    check("four per line: the fifth is not (40,10)", px(40, 10), 4);
    check("fifth-sprite flag and number, frame flag set (status)", msx_in(&m, 0x99), 0xC4);
    check("status read clears F, 5S and C, keeps the number", msx_in(&m, 0x99), 0x04);

    fresh(0x40);                               /* three sprites, list ended at 3: the number of the last processed */
    poke1(0x3800, 0x80);
    for (int i = 0; i < 3; ++i) sprite(i, 9, (uint8_t)(i * 10), 0, 6);
    poke1(0x1B0C, 208);
    frame();
    check("no fifth sprite: low bits hold the entry that ended the list (status)", msx_in(&m, 0x99), 0x83);

    /* Collision: colour 0 sprites collide; a colour 0 sprite in front leaves the one behind visible. */
    fresh(0x40);
    poke1(0x3800, 0x80); poke1(0x3808, 0xFF);
    sprite(0, 9, 50, 0, 0); sprite(1, 9, 50, 0, 7); poke1(0x1B08, 208);
    frame();
    check("collision: colour 0 in front, the sprite behind shows (50,10)", px(50, 10), 7);
    check("collision: flag set by a colour 0 sprite (status & 20h)", msx_in(&m, 0x99) & 0x20, 0x20);
    sprite(0, 9, 0, 1, 0x86); sprite(1, 9, 4, 1, 0x87);   /* both at x = -32 and -28: they meet only off screen */
    frame();
    check("collision: none outside the 256 visible columns (status & 20h)", msx_in(&m, 0x99) & 0x20, 0);
    sprite(0, 100, 50, 0, 6); sprite(1, 9, 60, 0, 7);
    frame();
    check("Y = 208 control: sprite 1 drawn while sprite 0 is elsewhere (60,10)", px(60, 10), 7);
    sprite(0, 208, 50, 0, 6);                  /* Y = 208 ends the list: sprite 1 is not drawn either */
    frame();
    check("Y = 208 ends the list (60,10)", px(60, 10), 4);

    fresh(0x41);                               /* magnified pixels collide: x = 20-21 and 21-22 meet at 21 */
    poke1(0x3800, 0x80);
    sprite(0, 9, 20, 0, 6); sprite(1, 9, 21, 0, 7); poke1(0x1B08, 208);
    frame();
    check("magnified collision (status & 20h)", msx_in(&m, 0x99) & 0x20, 0x20);

    fresh(0x40);                               /* the fifth-sprite flag is refused while the frame flag is set */
    poke1(0x3800, 0x80);
    frame();                                   /* frame flag set at line 192, not read */
    for (int i = 0; i < 5; ++i) sprite(i, 9, (uint8_t)(i * 10), 0, 6);
    poke1(0x1B00 + 5 * 4, 208);
    frame();
    check("fifth sprite while F is set: no 5S, low bits = the entry that ended the list (status)", msx_in(&m, 0x99), 0x85);

    fresh(0x40);                               /* sprites on line 192 are evaluated for the flags, not drawn */
    poke1(0x3800, 0x80);
    for (int i = 0; i < 5; ++i) sprite(i, 191, (uint8_t)(i * 10), 0, 6);
    poke1(0x1B00 + 5 * 4, 208);
    frame();
    check("five sprites on line 192 raise 5S before F (status)", msx_in(&m, 0x99), 0xC4);

    fresh(0x00);                               /* display off: border colour, no sprite processing */
    poke1(0x3800, 0x80); poke1(0x1800, 1); poke1(0x0008, 0xFF); poke1(0x2000, 0xF0);
    sprite(0, 9, 50, 0, 6); sprite(1, 9, 50, 0, 7); poke1(0x1B08, 208);
    frame();
    check("display off: background not drawn (0,0)", px(0, 0), 4);
    check("display off: no collision (status & 20h)", msx_in(&m, 0x99) & 0x20, 0);
}

/* Sound: run `seconds` and collect the samples. */
static int16_t samples[MSX_AUDIO_RATE * 2];

static unsigned listen(double seconds)
{
    unsigned total = 0, want = (unsigned)(seconds * MSX_AUDIO_RATE);
    uint64_t step = MSX_CPU_CLOCK / 200;
    while (total < want && total < sizeof samples / sizeof *samples) {
        msx_advance(&m, step);
        total += msx_audio_take(&m, samples + total, (unsigned)(sizeof samples / sizeof *samples) - total);
    }
    return total < want ? total : want;
}

static void psg(int r, uint8_t v) { msx_out(&m, 0xA0, (uint8_t)r); msx_out(&m, 0xA1, v); }

static double rising_crossings(unsigned n, double *low, double *high)
{
    double mean = 0, lo = 1e9, hi = -1e9;
    for (unsigned i = 0; i < n; ++i) { mean += samples[i]; lo = fmin(lo, samples[i]); hi = fmax(hi, samples[i]); }
    mean /= n;
    unsigned crossings = 0;
    for (unsigned i = 1; i < n; ++i) crossings += samples[i - 1] < mean && samples[i] >= mean;
    if (low) *low = lo;
    if (high) *high = hi;
    return crossings;
}

static void sound_checks(void)
{
    double lo, hi;
    /* Tone A, period 254: 1,789,772.5 / (16 x 254) = 440.39 Hz. */
    msx_init(&m, MSX_LINES_NTSC);
    psg(0, 254); psg(1, 0); psg(7, 0xBE); psg(8, 15);
    {                                          /* exactly one second of CPU cycles, in chunks the buffer holds */
        unsigned total = 0;
        for (uint64_t done = 0; done < MSX_CPU_CLOCK;) {
            uint64_t step = MSX_CPU_CLOCK - done < 17897 ? MSX_CPU_CLOCK - done : 17897;
            msx_advance(&m, step);
            done += step;
            total += msx_audio_take(&m, samples, MSX_AUDIO_BUFFER);
        }
        /* the last 16-cycle tick ends at 3,579,536: 3,579,536 / (3,579,545 / 44,100) = 44,099.9 samples */
        check_range("audio: one second of cycles gives 44,099-44,100 samples", total, 44099, 44100);
        check("audio: no sample dropped", (long)m.synth.dropped, 0);
    }
    unsigned n = listen(1.0);
    check_range("tone A, period 254: rising crossings in one second (440.39 Hz)", rising_crossings(n, &lo, &hi), 439, 441);
    double loud = hi - lo;
    psg(8, 7);
    listen(0.1);
    n = listen(0.5);
    rising_crossings(n, &lo, &hi);
    check_range("volume 7 against 15: amplitude ratio (0.1074 from the level table)", (hi - lo) / loud, 0.102, 0.113);

    /* Envelope shape 8 (repeated fall), period 70: one ramp lasts 256 x 70 / 1,789,772.5 s, 99.88 per second. All
     * tones and noises off, so the channel follows the envelope alone. */
    msx_init(&m, MSX_LINES_NTSC);
    psg(7, 0xBF); psg(8, 0x10); psg(11, 70); psg(12, 0); psg(13, 0x08);
    n = listen(1.0);
    unsigned jumps = 0;                         /* a restart may fall across two samples: compare two apart */
    for (unsigned i = 2; i < n; ++i)
        if (samples[i] - samples[i - 2] > 3000) { ++jumps; i += 2; }
    check_range("envelope shape 8, period 70: ramps restarting in one second (99.88)", jumps, 98, 101);
    psg(13, 0x0D);                              /* shape 13: rise once, then hold at the top */
    listen(0.05);
    n = listen(0.2);
    rising_crossings(n, &lo, &hi);
    check("envelope shape 13: holds at level 15 (32,767 / 3 x 21,000 / 37,000 x 4/5)", (long)lo, 4958);
    check("envelope shape 13: no change after the ramp", (long)(hi - lo), 0);
    psg(13, 0x00);                              /* a write restarts: shape 0 falls once and holds at 0 */
    listen(0.05);
    n = listen(0.2);
    rising_crossings(n, &lo, &hi);
    check("R#13 write restarts the envelope: shape 0 ends at level 0", (long)hi, 0);
    psg(13, 0x0A);                              /* shape 10: fall, rise, fall... no jump, the whole range */
    listen(0.05);
    n = listen(0.5);
    rising_crossings(n, &lo, &hi);
    jumps = 0;
    for (unsigned i = 2; i < n; ++i) jumps += abs(samples[i] - samples[i - 2]) > 3000;
    check("envelope shape 10: a triangle, no jump", jumps, 0);
    check("envelope shape 10: spans levels 0 to 15", (long)(hi - lo), 4958);

    /* Noise on channel A, period 31: the register shifts 1,789,772.5 / (16 x 31) = 3,608 times a second; a new bit
     * differs from the last on half the shifts and rises on a quarter: about 902 rising edges a second. */
    msx_init(&m, MSX_LINES_NTSC);
    psg(6, 31); psg(7, 0xB7); psg(8, 15);
    n = listen(1.0);
    check_range("noise, period 31: rising edges in one second (about 902)", rising_crossings(n, NULL, NULL), 820, 985);

    /* Key click: PPI port C bit 7 raises the output by the click's share of the mix. */
    msx_init(&m, MSX_LINES_NTSC);
    listen(0.05);
    msx_out(&m, 0xAB, 0x0F);                    /* bit set/reset: set bit 7 */
    listen(0.01);                               /* the sample that holds the edge is a mix */
    n = listen(0.1);
    rising_crossings(n, &lo, &hi);
    check("key click: output level with bit 7 set (32,767 x 16,000 / 37,000 x 4/5)", (long)lo, 32767L * 16000 / 37000 * 4 / 5);
}

int main(void)
{
    video_checks();
    sound_checks();
    printf("%s: %d failure(s)\n", failures ? "FAIL" : "PASS", failures);
    return failures ? 1 : 0;
}
