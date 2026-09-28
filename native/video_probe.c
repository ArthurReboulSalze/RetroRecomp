/* Private-ROM headless diagnostics: no SDL, screenshots or visual review. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "glue.h"
#include "video/sms_vdp.h"
#include "embedded_rom.h"
#include "include/sms_runtime.h"
#include "video_frame.h"
#include "lightphaser.h"

int smsrecomp_take_reset_request(void) { return 0; }
static FILE *events;
static unsigned active_palette, active_scroll, active_vram, frame_vram;
static int play;
static void observe(int kind, uint16_t addr, uint8_t value) {
    unsigned long long frame = (unsigned long long)glue_frame_count();
    if (kind == VDPW_VRAM) {
        if (g_vdp.line < 192 && (g_vdp.reg[1] & 0x40)) { ++active_vram; ++frame_vram; }
        return;
    }
    fprintf(events, "%llu,%d,%d,%u,%u,%llu,%u\n", frame, g_vdp.line, kind, addr, value,
        (unsigned long long)g_z80.cyc, (unsigned)(g_z80.cyc % 228));
    if (frame >= 120 && g_vdp.line < 192 && (g_vdp.reg[1] & 0x40)) {
        if (kind == VDPW_CRAM) ++active_palette;
        if (kind == VDPW_REG && (addr == 8 || addr == 9)) ++active_scroll;
    }
}
static uint8_t script(uint64_t frame) {
    bool pressed = play ? frame >= 120 && frame % 120 < 5 : frame >= 120 && frame < 125;
    if (play && sms_light_phaser) {
        lightphaser_pointer(128, 96, pressed);
        if (sms_light_phaser_trigger_p2) glue_set_pad2(pressed ? SMS_PAD_B1 : 0);
    }
    return pressed ? SMS_PAD_B2 : 0;
}
static int record_frame(const uint32_t *fb, int w, int h) {
    const unsigned char *bytes = (const unsigned char *)fb;
    uint64_t hash = 1469598103934665603ULL;
    for (int i = 0; i < w * h * 4; ++i) hash = (hash ^ bytes[i]) * 1099511628211ULL;
    fprintf(events, "%llu,-1,3,0,%llu,%llu,%u\n", (unsigned long long)glue_frame_count(),
        (unsigned long long)hash, (unsigned long long)g_z80.cyc, (unsigned)(g_z80.cyc % 228));
    fprintf(events, "%llu,-1,4,0,%d,%llu,%u\n", (unsigned long long)glue_frame_count(),
        smsrecomp_frame_left_border(), (unsigned long long)g_z80.cyc, (unsigned)(g_z80.cyc % 228));
    fprintf(events, "%llu,-1,5,0,%u,%llu,%u\n", (unsigned long long)glue_frame_count(),
        frame_vram, (unsigned long long)g_z80.cyc, (unsigned)(g_z80.cyc % 228));
    frame_vram = 0;
    return 0;
}
int main(int argc, char **argv) {
    assert(argc >= 3);
    unsigned frames = (unsigned)strtoul(argv[1], NULL, 10);
    events = fopen(argv[2], "w"); assert(events);
    fputs("frame,line,kind,address,value,cycles,subcycle\n", events);
    play = getenv("RETRO_RECOMP_PROBE_PLAY") != NULL;
    assert(glue_load_rom("embedded")); glue_init(false, frames);
    glue_set_input_cb(script); vdp_set_write_observer(observe);
    glue_set_frame_callback(record_frame);
    if (argc > 3) glue_run_interp(); else glue_run();
    fclose(events); vdp_set_write_observer(NULL);
    printf("VDP probe: %s; frames=%llu active_palette=%u active_scroll=%u active_vram=%u fallback_cycles=%llu\n",
        sms_game_title, (unsigned long long)glue_frame_count(), active_palette, active_scroll, active_vram,
        (unsigned long long)smsrecomp_interpreter_cycles());
    assert(glue_frame_count() == frames);
    return 0;
}
