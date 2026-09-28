/* CPU/VDP/PSG continuation and persisted-file checks. No SDL/video/window. */
#undef NDEBUG
#include <assert.h>
#include "runtime_glue.c"
static int mode, callbacks;
static unsigned audio_samples;
static uint64_t audio_hash = 1469598103934665603ULL;
static void audio(const int16_t *samples, size_t count) {
    /* Compare PCM after the saved frame, excluding sound played before loading. */
    if (g_frame <= 5) return;
    audio_samples += (unsigned)(count * 2);
    for (size_t i = 0; i < count * 2; ++i) audio_hash = (audio_hash ^ (uint16_t)samples[i]) * 1099511628211ULL;
}
static void completed(int operation, int result) {
    assert(result == RR_STATE_OK); callbacks++;
    assert(operation == (mode == 1 ? RR_QUICKSAVE : RR_QUICKLOAD));
    assert(g_frame == 5);
}
static int frame(const uint32_t *pixels, int w, int h) {
    (void)pixels; (void)w; (void)h;
    if (mode == 1 && g_frame == 5) assert(smsrecomp_request_state(RR_QUICKSAVE));
    if (mode == 2 && g_frame == 1) assert(smsrecomp_request_state(RR_QUICKLOAD));
    return 0;
}
static uint8_t *snapshot(size_t *size) {
    uint8_t *bytes = (uint8_t *)calloc(RR_STATE_CAPACITY, 1); assert(bytes);
    RetroStateIO body = {bytes, RR_STATE_CAPACITY, 0, RR_STATE_WRITE, true};
    smsrecomp_machine_state(&body); assert(body.ok); *size = body.pos; return bytes;
}
static void unchanged(const uint8_t *before, size_t size) {
    size_t n; uint8_t *after = snapshot(&n); assert(n == size && !memcmp(before, after, n)); free(after);
}
static void write_slot(uint8_t *bytes, size_t size) {
    FILE *f = retro_game_file(L"-quicksave.state", L"wb"); assert(f);
    assert(fwrite(bytes, size, 1, f) == 1 && fclose(f) == 0);
}
static void rejects(void) {
    size_t n; uint8_t *before = snapshot(&n);
    uint64_t interpreted = g_hybrid_cyc, total = smsrecomp_total_cycles;
    assert(smsrecomp_state_save() == RR_STATE_OK);
    FILE *f = retro_game_file(L"-quicksave.state", L"rb"); assert(f);
    uint8_t *file = (uint8_t *)malloc(RR_STATE_CAPACITY); assert(file);
    size_t size = fread(file, 1, RR_STATE_CAPACITY, f); fclose(f); assert(size == n + RR_STATE_HEADER);
    file[16] ^= 1; write_slot(file, size); assert(smsrecomp_state_load() == RR_STATE_INCOMPATIBLE); unchanged(before, n); file[16] ^= 1;
    file[8] ^= 1; write_slot(file, size); assert(smsrecomp_state_load() == RR_STATE_INCOMPATIBLE); unchanged(before, n); file[8] ^= 1;
    file[size-1] ^= 1; write_slot(file, size); assert(smsrecomp_state_load() == RR_STATE_INVALID); unchanged(before, n); file[size-1] ^= 1;
    write_slot(file, size-1); assert(smsrecomp_state_load() == RR_STATE_INVALID); unchanged(before, n);
    /* Valid checksum with invalid CPU interrupt mode must still fail atomically. */
    uint8_t im = file[RR_STATE_HEADER + 30]; file[RR_STATE_HEADER + 30] = 3;
    uint32_t crc = smsrecomp_state_crc(file + RR_STATE_HEADER, size - RR_STATE_HEADER);
    for (int i = 0; i < 4; ++i) file[84+i] = (uint8_t)(crc >> (i*8));
    write_slot(file, size); assert(smsrecomp_state_load() == RR_STATE_INVALID); unchanged(before, n);
    file[RR_STATE_HEADER + 30] = im;
    /* Failed atomic replacement preserves the destination (directory as target). */
    assert(!retro_game_file_replace(L"-missing.tmp", L"-quicksave.state"));
    assert(g_hybrid_cyc == interpreted && smsrecomp_total_cycles == total);
    retro_game_file_reset(L"-quicksave.state");
    assert(smsrecomp_state_load() == RR_STATE_MISSING); unchanged(before, n);
    assert(smsrecomp_state_save() == RR_STATE_OK);
    /* Callback scratch and telemetry do not enter the serialized machine. */
    g_hybrid_cyc += 13; smsrecomp_total_cycles += 29;
    assert(smsrecomp_state_load() == RR_STATE_OK);
    assert(g_hybrid_cyc == interpreted + 13 && smsrecomp_total_cycles == total + 29);
    unchanged(before, n); free(file); free(before);
}
static void special_fields(void) {
    size_t original_size; uint8_t *original = snapshot(&original_size);
    g_z80.pc = 0xC200; g_z80.sp = 0xC3FF;
    g_z80.a_ = 0xEF; g_z80.f_ = 0xB7; g_z80.b_ = 0x67; g_z80.c_ = 0x9A;
    g_z80.d_ = 0xDE; g_z80.e_ = 0xBC; g_z80.h_ = 0xCD; g_z80.l_ = 0xAB;
    g_z80.ix = 0x98EF; g_z80.iy = 0xABDF; g_z80.wz = 0xCEFA;
    g_z80.q = 0xD7; g_z80.p = 1; g_z80.ei_block = 1;
    g_z80.iff1 = false; g_z80.iff2 = true; g_z80.im = 2;
    g_ram[0x200] = 0x00; /* Native byte-guarded RAM NOP after reload. */
    vdp_control_write(0x34); /* First byte of a still-incomplete control command. */
    psg_write(0xE7); psg_write(0xF2); psg_advance(123);
    lightphaser_control(0x55, g_z80.cyc, 0x8A);
    assert(smsrecomp_state_save() == RR_STATE_OK);
    size_t special_size; uint8_t *special = snapshot(&special_size);
    memset(g_ram, 0xAB, sizeof g_ram); memset(&g_z80, 0, sizeof g_z80); vdp_reset(false); psg_init();
    lightphaser_reset(false, sms_light_phaser_hcounter_offset);
    assert(smsrecomp_state_load() == RR_STATE_OK); unchanged(special, special_size);
    assert(game_banked_step((uint8_t)g_bank[0], (uint8_t)g_bank[1], (uint8_t)g_bank[2]) == 2);
    assert(g_z80.pc == 0xC201); assert(!banked_fallback_steps);
    RetroStateIO restore = {original, original_size, 0, RR_STATE_CHECK, true};
    smsrecomp_machine_state(&restore); assert(restore.ok && restore.pos == original_size);
    restore.pos = 0; restore.mode = RR_STATE_APPLY; smsrecomp_machine_state(&restore); assert(restore.ok);
    unchanged(original, original_size); free(special); free(original);
}
int main(int argc, char **argv) {
    assert(argc == 2 && glue_load_rom("authored")); mode = atoi(argv[1]);
    glue_init(false, 12); glue_set_frame_callback(frame); glue_set_audio_sink(audio);
    smsrecomp_set_state_callback(completed); glue_run();
    assert(g_frame == 12 && callbacks == 1 && banked_fallback_steps == 0 && g_hybrid_cyc == 0);
    size_t size; uint8_t *state = snapshot(&size);
    if (mode == 1) {
        FILE *f = fopen("expected.state-test", "wb"); assert(f);
        assert(fwrite(state, size, 1, f) == 1 && fclose(f) == 0);
        f = fopen("expected.pcm-test", "wb"); assert(f);
        assert(fwrite(&audio_hash, sizeof audio_hash, 1, f) == 1);
        assert(fwrite(&audio_samples, sizeof audio_samples, 1, f) == 1 && fclose(f) == 0);
        printf("Persistent save created; payload=%zu bytes, native fallback=0.\n", size);
    } else {
        FILE *f = fopen("expected.state-test", "rb"); assert(f);
        uint8_t *expected = (uint8_t *)malloc(size); assert(expected);
        assert(fread(expected, size, 1, f) == 1 && fgetc(f) == EOF); fclose(f);
        if (memcmp(expected, state, size)) {
            for (size_t i = 0; i < size; ++i) if (expected[i] != state[i]) {
                printf("Continuation mismatch at %zu: expected %u actual %u\n", i, expected[i], state[i]); break;
            }
            return 1;
        }
        uint64_t hash; unsigned samples;
        f = fopen("expected.pcm-test", "rb"); assert(f);
        assert(fread(&hash, sizeof hash, 1, f) == 1 && fread(&samples, sizeof samples, 1, f) == 1); fclose(f);
        assert(hash == audio_hash && samples == audio_samples);
        special_fields(); rejects(); free(expected);
        puts("Cross-process resume: identical CPU/RAM/banks/VDP/raster/PSG/latches and PCM; corrupt/wrong-ROM/schema/invalid-field/missing files rejected without mutation; telemetry preserved; native fallback=0.");
    }
    free(state); return 0;
}
