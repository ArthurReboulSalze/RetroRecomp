/* Authored VDP fixtures: no ROM, SDL window, screenshot or human visual test. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "video/sms_vdp.h"
#include "sms_clocks.h"
#include "video_frame.h"

static uint32_t output[256 * 192];
static void pattern(int tile, int color) {
    for (int y = 0; y < 8; ++y) for (int plane = 0; plane < 4; ++plane)
        g_vdp.vram[tile * 32 + y * 4 + plane] = color & (1 << plane) ? 255 : 0;
}
static void fixture(void) {
    vdp_reset(false);
    g_vdp.reg[0] = 6; g_vdp.reg[1] = 0x40;
    g_vdp.reg[2] = 14; g_vdp.reg[5] = 0x7E;
    g_vdp.vram[0x3F00] = 0xD0;
    g_vdp.cram[0] = 0; g_vdp.cram[1] = 3; g_vdp.cram[2] = 12;
    g_vdp.cram[16] = 0x30; g_vdp.cram[17] = 3; g_vdp.cram[18] = 12;
    pattern(1, 1); pattern(2, 2); pattern(3, 0);
    for (int i = 0; i < 32 * 28; ++i) g_vdp.vram[0x3800 + i * 2] = 1;
    smsrecomp_video_begin_line(0);
}
static void to_line(int line) { while (g_vdp.line != line) vdp_step_line(); }
static void complete(void) { to_line(192); smsrecomp_video_present(output); }
static void raster_checks(void) {
    fixture();
    /* Use background palette #1, index zero, like Gangster Town's car tiles. */
    for (int i = 0; i < 32 * 28; ++i) {
        g_vdp.vram[0x3800 + i * 2] = 3;
        g_vdp.vram[0x3801 + i * 2] = 8;
    }
    to_line(113); g_vdp.cram[16] = 6; complete();
    assert(output[112 * 256 + 80] == 0xFF0000FFu);
    assert(output[113 * 256 + 80] == 0xFFAA5500u);
    g_vdp.cram[16] = 0; smsrecomp_video_present(output);
    assert(output[113 * 256 + 80] == 0xFFAA5500u);
    /* Work on the next frame does not overwrite the completed frame. */
    to_line(0); to_line(20); smsrecomp_video_present(output);
    assert(output[0] == 0xFF0000FFu);
    assert(output[113 * 256 + 80] == 0xFFAA5500u);
    to_line(192); smsrecomp_video_present(output); assert(output[0] == 0xFF000000u);
    puts("PASS: per-line palette split, no vblank recoloring, completed frame preserved.");

    fixture();
    for (int row = 0; row < 28; ++row) g_vdp.vram[0x3800 + (row * 32 + 1) * 2] = 2;
    to_line(56); g_vdp.reg[8] = 8; complete();
    assert(output[56 * 256 + 8] == 0xFF00FF00u);
    assert(output[57 * 256 + 8] == 0xFFFF0000u);
    assert(output[57 * 256 + 16] == 0xFF00FF00u);
    puts("PASS: horizontal scroll latched for the following line.");

    fixture();
    for (int col = 0; col < 32; ++col) g_vdp.vram[0x3800 + (32 + col) * 2] = 2;
    to_line(4); g_vdp.reg[9] = 8; complete();
    assert(output[4 * 256 + 80] == 0xFFFF0000u);
    to_line(0); complete(); assert(output[0 * 256 + 80] == 0xFF00FF00u);
    puts("PASS: vertical scroll waits for the next frame.");
}
static void sprite_checks(void) {
    fixture();
    g_vdp.vram[0x3F00] = g_vdp.vram[0x3F01] = 9; g_vdp.vram[0x3F02] = 0xD0;
    g_vdp.vram[0x3F80] = g_vdp.vram[0x3F82] = 20;
    g_vdp.vram[0x3F81] = 2; g_vdp.vram[0x3F83] = 1;
    complete(); assert(output[10 * 256 + 20] == 0xFF00FF00u);
    assert((vdp_status_read() & 0x20) != 0); assert((vdp_status_read() & 0x60) == 0);
    puts("PASS: first sprite priority, collision detection and status clearing.");

    fixture();
    for (int i = 0; i < 9; ++i) {
        g_vdp.vram[0x3F00 + i] = 9;
        g_vdp.vram[0x3F80 + i * 2] = 16 + i * 16;
        g_vdp.vram[0x3F81 + i * 2] = 2;
    }
    g_vdp.vram[0x3F09] = 0xD0; complete();
    assert(output[10 * 256 + 128] == 0xFF00FF00u);
    assert(output[10 * 256 + 144] == 0xFFFF0000u);
    assert((vdp_status_read() & 0x40) != 0);
    puts("PASS: eight sprites per line and ninth-sprite overflow.");

    fixture(); g_vdp.vram[0x3F00] = 253; g_vdp.vram[0x3F01] = 0xD0;
    g_vdp.vram[0x3F80] = 20; g_vdp.vram[0x3F81] = 2;
    complete(); assert(output[20] == 0xFF00FF00u);
    fixture(); g_vdp.reg[1] |= 1;
    g_vdp.vram[0x3F00] = 9; g_vdp.vram[0x3F01] = 0xD0;
    g_vdp.vram[0x3F80] = 20; g_vdp.vram[0x3F81] = 2;
    complete(); assert(output[24 * 256 + 35] == 0xFF00FF00u);
    assert(output[26 * 256 + 35] == 0xFFFF0000u);
    puts("PASS: sprites wrap at the top edge and zoom doubles both dimensions.");
}
static void border_checks(void) {
    fixture(); g_vdp.reg[0] |= 0x20; complete();
    assert(smsrecomp_frame_left_border() == 8);
    assert(output[20 * 256] == 0xFF0000FFu);
    fixture(); to_line(80); g_vdp.reg[0] |= 0x20; complete();
    assert(smsrecomp_frame_left_border() == 0);
    assert(output[0] == 0xFFFF0000u && output[80 * 256] == 0xFF0000FFu);
    vdp_reset(false); smsrecomp_video_present(output);
    assert(output[0] == 0xFF000000u && smsrecomp_frame_left_border() == 0);
    puts("PASS: whole-frame border metadata, partial-line masks and reset.");
}
static void interrupt_checks(void) {
    fixture();
    g_vdp.reg[0] |= 0x10;
    g_vdp.reg[10] = 157;
    g_vdp.line_counter = 157; /* Enters line 158 with the previous value zero. */
    to_line(157); assert(!g_vdp.line_irq);
    to_line(158); assert(g_vdp.line_irq && vdp_irq_asserted());
    assert(!(vdp_status_read() & 0x80));
    to_line(192); assert(!g_vdp.frame_irq);
    to_line(193); assert(g_vdp.frame_irq && (vdp_status_read() & 0x80));
#if SMS_LINES_PER_FRAME == 313
    to_line(242); assert(vdp_vcounter() == 0xF2);
    to_line(243); assert(vdp_vcounter() == 0xBA);
    to_line(312); assert(vdp_vcounter() == 0xFF);
#else
    to_line(218); assert(vdp_vcounter() == 0xDA);
    to_line(219); assert(vdp_vcounter() == 0xD5);
    to_line(261); assert(vdp_vcounter() == 0xFF);
#endif
    to_line(0); assert(vdp_vcounter() == 0);
    puts("PASS: H-INT on entering line 158, V-INT on line 193, regional V-counter wrap.");
}
int main(void) { raster_checks(); sprite_checks(); border_checks(); interrupt_checks(); return 0; }
