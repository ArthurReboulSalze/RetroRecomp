/* Private-cartridge diagnostics. No window, images, learning outputs or ROM
 * patches. Compare actual game state with/without the host-only enhancement. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "runtime_glue.c"
#define vdp_step_line original_step_line
#define smsrecomp_video_state original_video_state
#include "runtime_video.c"
#undef vdp_step_line
#undef smsrecomp_video_state

static FILE *events;
static unsigned frame_max, frame_lines, frame_lost, frame_sat_writes;
static unsigned max_sprites;
static uint64_t affected_frames, lost_pixels, overflow_lines, active_sat_writes;
static uint64_t stabilized_frames, priority_adjusted_pixels;
static unsigned frame_adjusted_pixels;
static uint64_t audio_hash = 1469598103934665603ULL, audio_samples;
static int omit_presentation, improved;

int smsrecomp_take_reset_request(void) { return 0; }
void smsrecomp_video_state(RetroStateIO *io) {
    size_t start = io->pos;
    original_video_state(io);
    if (omit_presentation) {
        /* Keep the seven raster latches; omit only the two ARGB buffers. A
         * changed serializer must update this diagnostic deliberately. */
        assert(io->mode == RR_STATE_WRITE && io->ok && io->pos - start == 7 + sizeof raster_buffers);
        io->pos = start + 7;
    }
}
static uint64_t hash_bytes(uint64_t hash, const void *data, size_t length) {
    const uint8_t *bytes = data;
    for (size_t i = 0; i < length; ++i) hash = (hash ^ bytes[i]) * 1099511628211ULL;
    return hash;
}
void vdp_step_line(void) {
    int line = g_vdp.line;
    int work = raster_work, check_pixels = 0;
    uint32_t expected[256];
    if (line < SMS_SCREEN_H && (g_vdp.reg[1] & 0x40)) {
        int sat = (g_vdp.reg[5] & 0x7e) << 7;
        int height = ((g_vdp.reg[1] & 2) ? 16 : 8) * ((g_vdp.reg[1] & 1) ? 2 : 1);
        int count = 0;
        for (int i = 0; i < 64; ++i) {
            int raw = g_vdp.vram[(sat + i) & 0x3fff];
            if (raw == 0xd0) break;
            if (((line - ((raw + 1) & 255)) & 255) < height) ++count;
        }
        if ((unsigned)count > frame_max) frame_max = count;
        if (count > 8 || (improved && sprite_stable_reverse)) {
            uint32_t limited[256], unlimited[256], stabilized[256];
            int choice = reduce_sprite_flicker;
            int stable = sprite_stable_reverse;
            /* Diagnostic draws must not toggle the real host setting and
             * clear the live presentation history. These calls are pure. */
            reduce_sprite_flicker = 0;
            mode4_line(limited, line, raster_hscroll, raster_vscroll, false);
            reduce_sprite_flicker = 1; sprite_stable_reverse = 0;
            mode4_line(unlimited, line, raster_hscroll, raster_vscroll, false);
            sprite_stable_reverse = stable;
            mode4_line(stabilized, line, raster_hscroll, raster_vscroll, false);
            reduce_sprite_flicker = choice;
            memcpy(expected, choice ? stabilized : limited, sizeof expected);
            check_pixels = 1;
            unsigned lost = 0;
            for (int x = 0; x < 256; ++x) {
                lost += limited[x] != unlimited[x];
                if (choice) frame_adjusted_pixels += unlimited[x] != stabilized[x];
            }
            if (count > 8) { ++frame_lines; frame_lost += lost; }
            if (lost) {
                fprintf(events, "%llu,%d,%d,%u,", (unsigned long long)g_frame, line, count, lost);
                for (int i = 0; i < 64; ++i) {
                    int raw = g_vdp.vram[(sat + i) & 0x3fff];
                    if (raw == 0xd0) break;
                    if (((line - ((raw + 1) & 255)) & 255) < height)
                        fprintf(events, "%d:%d:%d:%d;", i, raw,
                            g_vdp.vram[(sat + 128 + i * 2) & 0x3fff],
                            g_vdp.vram[(sat + 129 + i * 2) & 0x3fff]);
                }
                fputc('\n', events);
            }
        }
    }
    original_step_line();
    if (check_pixels)
        assert(!memcmp(expected, raster_buffers[work] + line * SMS_SCREEN_W, sizeof expected));
}
static void observe(int kind, uint16_t address, uint8_t value) {
    (void)value;
    if (kind != VDPW_VRAM || g_vdp.line >= 192 || !(g_vdp.reg[1] & 0x40)) return;
    unsigned sat = (g_vdp.reg[5] & 0x7e) << 7;
    if (address >= sat && address < sat + 256) ++frame_sat_writes;
}
static void audio(const int16_t *samples, size_t count) {
    audio_hash = hash_bytes(audio_hash, samples, count * 2 * sizeof(*samples));
    audio_samples += count * 2;
}
static int frame_callback(const uint32_t *fb, int w, int h) {
    (void)fb; (void)w; (void)h;
    if (frame_lines) ++affected_frames;
    if (frame_adjusted_pixels) ++stabilized_frames;
    priority_adjusted_pixels += frame_adjusted_pixels;
    lost_pixels += frame_lost; overflow_lines += frame_lines; active_sat_writes += frame_sat_writes;
    if (frame_max > max_sprites) max_sprites = frame_max;
    fprintf(events, "%llu,-1,%u,%u,%u:%u\n", (unsigned long long)g_frame,
        frame_max, frame_lost, frame_lines, frame_sat_writes);
    frame_max = frame_lost = frame_lines = frame_sat_writes = 0;
    frame_adjusted_pixels = 0;
    return 0;
}
static uint8_t input(uint64_t frame) {
    /* Same finite reproducible route on both CPUs/modes; it is not an
     * assertion of whole-game play coverage. */
    if (frame >= 120 && frame < 125) return SMS_PAD_B1 | SMS_PAD_B2;
    if (frame >= 240 && frame < 360) return SMS_PAD_RIGHT;
    return 0;
}
int main(int argc, char **argv) {
    assert(argc >= 4);
    unsigned frames = (unsigned)strtoul(argv[1], NULL, 10);
    improved = atoi(argv[3]) != 0;
    events = fopen(argv[2], "w"); assert(events);
    fputs("frame,line,eligible,pixels_recovered,sprites_or_frame_summary\n", events);
    assert(glue_load_rom("embedded")); glue_init(false, frames);
    smsrecomp_video_set_sprite_flicker_reduction(improved);
    glue_set_input_cb(input); glue_set_frame_callback(frame_callback);
    glue_set_audio_sink(audio); vdp_set_write_observer(observe);
    if (argc > 4) glue_run_interp(); else glue_run();
    fclose(events);
    uint8_t *data = malloc(RR_STATE_CAPACITY); assert(data);
    RetroStateIO io = {data, RR_STATE_CAPACITY, 0, RR_STATE_WRITE, true};
    omit_presentation = 1; smsrecomp_machine_state(&io); omit_presentation = 0;
    assert(io.ok);
    uint64_t guest = hash_bytes(1469598103934665603ULL, data, io.pos); free(data);
    printf("{\"frames\":%llu,\"affected_frames\":%llu,\"overflow_lines\":%llu,"
        "\"recoverable_pixels\":%llu,\"max_sprites\":%u,\"active_sat_writes\":%llu,"
        "\"fallback_cycles\":%llu,\"guest_state_hash\":\"%016llx\","
        "\"pcm_hash\":\"%016llx\",\"pcm_samples\":%llu,\"sprite_reduction\":%s,"
        "\"stabilized_frames\":%llu,\"priority_adjusted_pixels\":%llu}\n",
        (unsigned long long)g_frame, (unsigned long long)affected_frames,
        (unsigned long long)overflow_lines, (unsigned long long)lost_pixels, max_sprites,
        (unsigned long long)active_sat_writes, (unsigned long long)smsrecomp_interpreter_cycles(),
        (unsigned long long)guest, (unsigned long long)audio_hash,
        (unsigned long long)audio_samples, improved ? "true" : "false",
        (unsigned long long)stabilized_frames, (unsigned long long)priority_adjusted_pixels);
    assert(g_frame == frames);
    return 0;
}
