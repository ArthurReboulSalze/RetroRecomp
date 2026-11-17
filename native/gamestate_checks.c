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
    int step = game_banked_step((uint8_t)g_bank[0], (uint8_t)g_bank[1], (uint8_t)g_bank[2]);
    if(step != 2) fprintf(stderr, "State fixture RAM NOP returned %d at PC=%04X\n", step, g_z80.pc);
    assert(step == 2);
    assert(g_z80.pc == 0xC201); assert(!banked_fallback_steps);
    RetroStateIO restore = {original, original_size, 0, RR_STATE_CHECK, true};
    smsrecomp_machine_state(&restore); assert(restore.ok && restore.pos == original_size);
    restore.pos = 0; restore.mode = RR_STATE_APPLY; smsrecomp_machine_state(&restore); assert(restore.ok);
    unchanged(original, original_size); free(special); free(original);
}
/* ---- Mode 3: the rollback snapshot (native/gamestate.h). Save at a frame edge, run, load, run the same frames again: every digest
 * identical, from inside the callback the kit uses, with the frames ending in the middle of an IN/OUT as well as between
 * instructions. No file is written. ---- */
enum { SNAP_AT = 10, SNAP_RUN = 20, SNAP_LIMIT = 40 };
static int snap_phase;
static unsigned edges_in_io, edges_halted, edges_irq_pending;
static uint64_t snap_digest[SNAP_RUN + 1];
static uint8_t *snap_slot;
static size_t snap_size;
static int snap_frame(const uint32_t *pixels, int w, int h) {
    (void)pixels; (void)w; (void)h;
    if (smsrecomp_in_io) edges_in_io++;
    assert(smsrecomp_defer_frame());
    assert(!smsrecomp_defer_frame());       /* one edge at a time: a second frame end is run by the host in place */
    return 0;
}
static void snap_scramble(void) {
    /* What a frame edge can leave half-way: a pending control byte, EI's delay, the P/Q flag latches, HALT, odd PSG and phaser latches. */
    g_z80.pc = 0xC200; g_z80.sp = 0xC3FF; g_z80.q = 0xD7; g_z80.p = 1; g_z80.ei_block = 1; g_z80.halted = 1;
    g_z80.iff1 = false; g_z80.iff2 = true; g_z80.im = 2; g_z80.i = 0x9C; g_z80.r = 0xA5; g_z80.wz = 0xCEFA;
    g_z80.ix = 0x98EF; g_z80.iy = 0xABDF; g_ram[0x200] = 0x5A;
    g_vdp.frame_irq = g_vdp.line_irq = true; g_vdp.status |= 0x80;    /* interrupts pending */
    vdp_control_write(0x34);
    psg_write(0xE7); psg_write(0xF2); psg_advance(123);
    lightphaser_control(0x55, g_z80.cyc, 0x8A);
}
static void snap_trash(void) {
    memset(g_ram, 0xAB, sizeof g_ram); memset(&g_z80, 0, sizeof g_z80); vdp_reset(g_is_gg); psg_init(); smsrecomp_video_reset();
    lightphaser_reset(false, sms_light_phaser_hcounter_offset); g_frame = 3; g_bank[0] = g_bank[1] = g_bank[2] = 0;
}
static bool snap_edge(void) {
    const uint64_t frame = g_frame;
    if (g_z80.halted) edges_halted++;
    if (vdp_irq_asserted()) edges_irq_pending++;
    if (snap_phase == 0) {
        if (frame != SNAP_AT) return true;
        snap_size = smsrecomp_snap_bound(); assert(snap_size > 0 && snap_size < 1024u * 1024u);
        snap_slot = (uint8_t *)malloc(snap_size); assert(snap_slot);
        assert(smsrecomp_snap_save(snap_slot, snap_size) == snap_size);
        /* A save over a buffer of other bytes writes the same bytes; a buffer too small writes nothing. */
        uint8_t *other = (uint8_t *)malloc(snap_size); assert(other); memset(other, 0xA5, snap_size);
        assert(smsrecomp_snap_save(other, snap_size) == snap_size && !memcmp(other, snap_slot, snap_size));
        assert(smsrecomp_snap_save(other, snap_size - 1) == 0 && !smsrecomp_snap_save(NULL, snap_size));
        free(other);
        snap_digest[0] = smsrecomp_digest(); assert(snap_digest[0]);
        /* A wrong size or a foreign buffer is refused and the machine is untouched. */
        assert(!smsrecomp_snap_load(snap_slot, snap_size - 1) && !smsrecomp_snap_load(snap_slot, snap_size + 1) && !smsrecomp_snap_load(NULL, snap_size));
        uint8_t *foreign = (uint8_t *)calloc(snap_size, 1); assert(foreign);
        assert(!smsrecomp_snap_load(foreign, snap_size)); free(foreign);
        assert(smsrecomp_digest() == snap_digest[0]);
        snap_phase = 1; return true;
    }
    if (snap_phase == 1) {
        snap_digest[frame - SNAP_AT] = smsrecomp_digest();
        if (frame < SNAP_AT + SNAP_RUN) return true;
        /* Back to the saved frame, then the same frames again. */
        assert(smsrecomp_snap_load(snap_slot, snap_size));
        assert(g_frame == SNAP_AT && smsrecomp_digest() == snap_digest[0]);
        snap_phase = 2; return true;
    }
    if (snap_phase == 2) {
        assert(smsrecomp_digest() == snap_digest[frame - SNAP_AT]);
        if (frame < SNAP_AT + SNAP_RUN) return true;
        /* The same again, from a state with every odd latch set, restored after the machine was wiped. */
        snap_scramble();
        const uint64_t before = smsrecomp_digest(); assert(before);
        assert(smsrecomp_snap_save(snap_slot, snap_size) == snap_size);
        snap_trash(); assert(smsrecomp_digest() != before);
        assert(smsrecomp_snap_load(snap_slot, snap_size));
        assert(smsrecomp_digest() == before);
        snap_phase = 3; return false;       /* the scrambled machine is not run on */
    }
    return false;
}
static int snapshot_probe(void) {
    glue_init(false, SNAP_LIMIT); glue_set_frame_callback(snap_frame); glue_set_audio_sink(audio);
    smsrecomp_set_frame_edge_callback(snap_edge); glue_run();
    assert(snap_phase == 3 && banked_fallback_steps == 0 && g_hybrid_cyc == 0);
    /* The proof must have met the cases it claims: frames that end inside an IN/OUT, and not only between instructions. */
    printf("Snapshot: %zu bytes; save at frame %d, replay of %d frames identical; frame ends inside IN/OUT: %u, in HALT: %u, with /INT asserted: %u; wrong size, foreign buffer and short buffer refused; native fallback=0.\n",
           snap_size, SNAP_AT, SNAP_RUN, edges_in_io, edges_halted, edges_irq_pending);
    assert(edges_in_io + edges_halted > 0);    /* the main loop meets the first, the EI + HALT loop the second */
    free(snap_slot);
    return 0;
}
int main(int argc, char **argv) {
    assert(argc == 2 && glue_load_rom("authored")); mode = atoi(argv[1]);
    if (mode == 3) return snapshot_probe();
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
