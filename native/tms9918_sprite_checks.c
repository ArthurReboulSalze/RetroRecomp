/* Checks of the TMS9918A's « sprite flicker reduction » (native/tms9918, `tms9918_set_all_sprites`): off, the picture is the chip's (four
 * sprites a line); on, the sprites past the fourth are drawn behind the others; in both, the status byte (the fifth-sprite flag and its
 * number, the collision flag) and the state the program reads are the same. tools/tms9918_sprite_selftest.py builds and runs it.
 * MIT, Retro-Recomp. Never part of a game. */
#include "tms9918.h"

#include <stdio.h>
#include <string.h>

static int failures, checks;
#define REQUIRE(cond, text) do { ++checks; if (!(cond)) { printf("FAIL: %s\n", text); ++failures; } } while (0)

/* Mode 1 (graphic 1), display on, sprites 8 x 8, attribute table at 1B00h, patterns at 3800h, backdrop colour 4. `magnify` doubles them. */
static void setup(Tms9918 *v, int magnify)
{
    memset(v, 0, sizeof *v);
    v->reg[1] = (uint8_t)(0x40 | (magnify ? 1 : 0));
    v->reg[5] = 0x36;                  /* 36h << 7 = 1B00h */
    v->reg[6] = 0x07;                  /* 7 << 11 = 3800h */
    v->reg[7] = 0x04;
    memset(v->vram + 0x3800, 0xFF, 8);          /* pattern 0: a solid block */
    v->vram[0x1B00] = 208;                      /* an empty list until sprites are put */
}

static void put(Tms9918 *v, int n, int y, int x, int colour)
{
    uint8_t *a = v->vram + 0x1B00 + 4 * n;
    a[0] = (uint8_t)y; a[1] = (uint8_t)x; a[2] = 0; a[3] = (uint8_t)colour;
    a[4] = 208;
}

/* The line's pixels and status, drawn with the option `on`, from the same state. */
static void draw(const Tms9918 *from, int on, int line, uint8_t *pixels, uint8_t *status)
{
    static Tms9918 v;
    v = *from;
    tms9918_set_all_sprites(on);
    tms9918_draw_line(&v, line);
    memcpy(pixels, v.frame[line], TMS_WIDTH);
    *status = v.status;
    REQUIRE(!memcmp(v.vram, from->vram, sizeof v.vram), "the video RAM is untouched");
    REQUIRE(v.address == from->address && !memcmp(v.reg, from->reg, sizeof v.reg), "the address and the registers are untouched");
}

int main(void)
{
    static Tms9918 v;
    uint8_t off[TMS_WIDTH], on[TMS_WIDTH], status_off, status_on;

    /* Eight sprites of eight colours side by side on lines 11-18: the chip shows four, the option all eight, the flags the same. */
    setup(&v, 0);
    for (int n = 0; n < 8; ++n) put(&v, n, 10, 20 + 16 * n, 2 + n);
    draw(&v, 0, 12, off, &status_off);
    draw(&v, 1, 12, on, &status_on);
    for (int n = 0; n < 4; ++n) REQUIRE(off[20 + 16 * n] == 2 + n && on[20 + 16 * n] == 2 + n, "the first four are drawn either way");
    for (int n = 4; n < 8; ++n) REQUIRE(off[20 + 16 * n] == 4, "past the fourth: the backdrop without the option");
    for (int n = 4; n < 8; ++n) REQUIRE(on[20 + 16 * n] == 2 + n, "past the fourth: drawn with the option");
    REQUIRE(status_off == status_on, "the status byte is the same with and without the option");
    REQUIRE((status_off & 0x40) && (status_off & 0x1F) == 4, "the fifth-sprite flag with number 4, as the chip");
    REQUIRE(!(status_off & 0x20), "no collision: they do not overlap");

    /* A later sprite overlaps an earlier one: behind it, and it sets no collision of its own (the chip never saw it). */
    setup(&v, 0);
    for (int n = 0; n < 4; ++n) put(&v, n, 10, 20 + 16 * n, 2 + n);
    put(&v, 4, 10, 24, 9);                        /* overlaps sprite 0 on x 24-27 */
    put(&v, 5, 10, 100, 10);
    put(&v, 6, 10, 104, 11);                      /* overlaps sprite 5, both dropped by the chip */
    draw(&v, 0, 12, off, &status_off);
    draw(&v, 1, 12, on, &status_on);
    REQUIRE(on[24] == 2 && on[27] == 2 && on[28] == 9 && on[31] == 9, "a later sprite is behind the earlier one");
    REQUIRE(on[100] == 10 && on[103] == 10 && on[104] == 10 && on[108] == 11, "among the dropped ones the lower number is in front");
    REQUIRE(status_off == status_on && !(status_on & 0x20), "no collision from sprites the chip does not process");
    REQUIRE(off[28] == 4 && off[100] == 4, "without the option the dropped ones are absent");

    /* A visible collision among the first four is reported either way. */
    setup(&v, 0);
    put(&v, 0, 10, 50, 2); put(&v, 1, 10, 52, 3); put(&v, 2, 10, 90, 4); put(&v, 3, 10, 120, 5); put(&v, 4, 10, 160, 6);
    draw(&v, 0, 12, off, &status_off);
    draw(&v, 1, 12, on, &status_on);
    REQUIRE((status_off & 0x20) && status_off == status_on, "the collision of the first four is the same");

    /* Magnified (16 pixels wide, 16 lines tall) and a transparent (colour 0) sprite past the fourth, and Y = 208 ends the list. */
    setup(&v, 1);
    for (int n = 0; n < 4; ++n) put(&v, n, 10, 20 + 24 * n, 2 + n);
    put(&v, 4, 10, 200, 0);                       /* transparent: never drawn */
    put(&v, 5, 10, 220, 12);
    v.vram[0x1B00 + 4 * 6] = 208;
    v.vram[0x1B00 + 4 * 7] = 10; v.vram[0x1B00 + 4 * 7 + 1] = 150; v.vram[0x1B00 + 4 * 7 + 3] = 13;
    draw(&v, 0, 20, off, &status_off);
    draw(&v, 1, 20, on, &status_on);
    REQUIRE(on[220] == 12 && on[235] == 12 && on[200] == 4, "magnified, past the fourth; a colour-0 sprite stays invisible");
    REQUIRE(on[150] == 4, "Y = 208 ends the list for the drawn ones too");
    REQUIRE(status_off == status_on && off[220] == 4, "same flags, absent without the option");

    /* Four sprites or fewer: the picture is identical with the option on. */
    setup(&v, 0);
    for (int n = 0; n < 4; ++n) put(&v, n, 10, 20 + 16 * n, 2 + n);
    draw(&v, 0, 12, off, &status_off);
    draw(&v, 1, 12, on, &status_on);
    REQUIRE(!memcmp(off, on, sizeof off) && status_off == status_on, "four or fewer: identical");

    /* The flag-only pass of the last visible line draws nothing whatever the option says. */
    tms9918_set_all_sprites(1);
    v.status = 0;
    tms9918_check_line(&v, 12);
    tms9918_set_all_sprites(0);

    printf(failures ? "tms9918 sprites: %d of %d failed\n" : "tms9918 sprites: ok (%d checks)\n", failures ? failures : checks, checks);
    return failures ? 1 : 0;
}
