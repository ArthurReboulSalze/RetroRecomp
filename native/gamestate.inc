/* Included in glue after its CPU, bus and timing definitions. No ROM bytes,
 * pointers, OS handles, C stacks, host options or learning data are saved. */
#include "gamestate.h"
#include "state_io.h"
#include "state_envelope.h"
#include <errno.h>
#include "platform_io.h"
#define RR_STATE_SCHEMA 1u
#define RR_STATE_MACHINE (g_is_gg ? 3u : (SMS_LINES_PER_FRAME == 313 ? 2u : 1u))
#define RR_STATE_HEADER RR_STATE_ENVELOPE_HEADER
#define RR_STATE_CAPACITY (1024u * 1024u)

void smsrecomp_set_state_callback(void (*callback)(int, int)) { smsrecomp_state_callback = callback; }
bool smsrecomp_request_state(int operation) {
#ifdef SMSRECOMP_BANKED_AOT
    if ((operation == RR_QUICKSAVE || operation == RR_QUICKLOAD) && !getenv("SMSRECOMP_REFERENCE")) {
        smsrecomp_state_pending = operation; return true;
    }
#endif
    return false;
}

static void smsrecomp_machine_state(RetroStateIO *io) {
    psg_catch_up(); /* the saved PSG matches the eager timeline */
    Z80State s = g_z80;
    RR_FIELD(s, a, 1, 255); RR_FIELD(s, f, 1, 255); RR_FIELD(s, b, 1, 255); RR_FIELD(s, c, 1, 255);
    RR_FIELD(s, d, 1, 255); RR_FIELD(s, e, 1, 255); RR_FIELD(s, h, 1, 255); RR_FIELD(s, l, 1, 255);
    RR_FIELD(s, a_, 1, 255); RR_FIELD(s, f_, 1, 255); RR_FIELD(s, b_, 1, 255); RR_FIELD(s, c_, 1, 255);
    RR_FIELD(s, d_, 1, 255); RR_FIELD(s, e_, 1, 255); RR_FIELD(s, h_, 1, 255); RR_FIELD(s, l_, 1, 255);
    RR_FIELD(s, pc, 2, 65535); RR_FIELD(s, sp, 2, 65535); RR_FIELD(s, ix, 2, 65535);
    RR_FIELD(s, iy, 2, 65535); RR_FIELD(s, wz, 2, 65535); RR_FIELD(s, i, 1, 255); RR_FIELD(s, r, 1, 255);
    RR_FIELD(s, iff1, 1, 1); RR_FIELD(s, iff2, 1, 1); RR_FIELD(s, im, 1, 2); RR_FIELD(s, halted, 1, 1);
    RR_FIELD(s, q, 1, 255); RR_FIELD(s, p, 1, 1); RR_FIELD(s, ei_block, 1, 1); RR_FIELD(s, cyc, 8, (1ULL << 60));
    int banks[3];
    for (int i = 0; i < 3; ++i) banks[i] = (int)rr_state_word(io, g_bank[i], 1, 255);
    rr_state_bytes(io, g_ram, sizeof g_ram);
    uint64_t next = rr_state_word(io, g_next_line_cyc, 8, (1ULL << 60));
    uint64_t frame = rr_state_word(io, g_frame, 8, (1ULL << 60) / SMS_CYC_PER_FRAME);
    uint64_t sound = rr_state_word(io, g_psg_cyc, 8, (1ULL << 60));
    unsigned model = (g_is_gg ? 1u : 0u) | (g_mapper_cm ? 2u : 0u) | (sms_light_phaser ? 4u : 0u);
    if (rr_state_word(io, model, 1, 7) != model ||
        rr_state_word(io, sms_light_phaser_hcounter_offset, 2, 65535) != sms_light_phaser_hcounter_offset ||
        rr_state_word(io, sms_light_phaser_trigger_p2, 1, 1) != sms_light_phaser_trigger_p2) io->ok = false;
    SmsVdp v = g_vdp;
    /* Small chip arrays are copied into the candidate, so validation never touches live state. */
    for (unsigned i = 0; i < sizeof v.vram; ++i) v.vram[i] = (uint8_t)rr_state_word(io, v.vram[i], 1, 255);
    for (unsigned i = 0; i < sizeof v.cram; ++i) v.cram[i] = (uint8_t)rr_state_word(io, v.cram[i], 1, 255);
    for (unsigned i = 0; i < sizeof v.reg; ++i) v.reg[i] = (uint8_t)rr_state_word(io, v.reg[i], 1, 255);
    RR_FIELD(v, addr, 2, 0x3FFF); RR_FIELD(v, code, 1, 3); RR_FIELD(v, latch, 1, 255);
    RR_FIELD(v, ctrl_second, 1, 1); RR_FIELD(v, readbuf, 1, 255); RR_FIELD(v, status, 1, 255);
    RR_FIELD(v, line, 2, SMS_LINES_PER_FRAME - 1); RR_FIELD(v, line_counter, 2, 255);
    RR_FIELD(v, frame_irq, 1, 1); RR_FIELD(v, line_irq, 1, 1); RR_FIELD(v, is_gg, 1, 1);
    RR_FIELD(v, cram_latch, 1, 255);
    if (v.is_gg != g_is_gg || next != frame * SMS_CYC_PER_FRAME + (uint64_t)(v.line + 1) * SMS_CYC_PER_LINE ||
        s.cyc >= next || s.cyc < next - SMS_CYC_PER_LINE || sound > s.cyc) io->ok = false;
    smsrecomp_video_state(io); smsrecomp_psg_state(io); lightphaser_state(io);
    if (io->mode == RR_STATE_APPLY && io->ok) {
        g_z80 = s; memcpy(g_bank, banks, sizeof banks); g_vdp = v;
        g_next_line_cyc = g_sync_deadline = next; g_frame = frame; g_psg_cyc = sound;
        smsrecomp_measured_guest_cycles = s.cyc;
        g_hz_init = false; smsrecomp_interp_depth = 0; reference_cycle_base = 0;
        smsrecomp_in_io = smsrecomp_stop_pending = false;
        /* Execution/fallback/learning counters remain cumulative across rewinds. */
    }
}

/* Multiplayer (native/hostkit/hostkit_session.h): the digest players compare, FNV-1a 64 over the machine as the quick state
 * writes it field by field (the same bytes on Windows and Linux), envelope left out. Taken between two frames only. */
uint64_t smsrecomp_digest(void) {
    static uint8_t *data;
    if (!data && !(data = (uint8_t *)malloc(RR_STATE_CAPACITY))) return 0;
    RetroStateIO io = {data, RR_STATE_CAPACITY, 0, RR_STATE_WRITE, true};
    smsrecomp_machine_state(&io);
    if (!io.ok) return 0;
    uint64_t hash = 14695981039346656037ull;
    for (size_t i = 0; i < io.pos; ++i) { hash ^= data[i]; hash *= 1099511628211ull; }
    return hash;
}

/* Multiplayer rollback (native/gamestate.h): the whole deterministic state as it stands in memory, copied as it is. The same
 * content as the quick state (CPU, banks, RAM, VDP, raster, PSG, Light Phaser latches, counters of the timeline); what is
 * cumulative telemetry stays out, as it does there. Valid at the end of a completed instruction, which is where the frame
 * edge below is delivered. The cartridge has no RAM in this runtime, so there is none to save. */
#define RR_SNAP_MAGIC 0x31504E53u    /* "SNP1" */
typedef struct {
    uint32_t magic, model;
    Z80State z80;
    int bank[3];
    uint64_t next_line, frame, psg_cyc;
    uint8_t phaser[16];
} RrSnapHead;
#define RR_SNAP_PHASER_BYTES 10      /* lightphaser_state: control, h_latch, previous_cycles */
static size_t smsrecomp_snap_size(void) {
    return sizeof(RrSnapHead) + sizeof g_ram + sizeof g_vdp + smsrecomp_video_snap_size() + smsrecomp_psg_snap_size();
}
size_t smsrecomp_snap_bound(void) {
#ifdef SMSRECOMP_BANKED_AOT
    return getenv("SMSRECOMP_REFERENCE") ? 0 : smsrecomp_snap_size();
#else
    return 0;
#endif
}
size_t smsrecomp_snap_save(void *buffer, size_t capacity) {
    const size_t size = smsrecomp_snap_bound();
    if (!size || !buffer || capacity < size) return 0;
    psg_catch_up();     /* the saved PSG matches the eager timeline, as in the digest */
    uint8_t *out = (uint8_t *)buffer;
    RrSnapHead head;
    memset(&head, 0, sizeof head);
    head.magic = RR_SNAP_MAGIC;
    head.model = (g_is_gg ? 1u : 0u) | (g_mapper_cm ? 2u : 0u) | (sms_light_phaser ? 4u : 0u) | (SMS_LINES_PER_FRAME == 313 ? 8u : 0u);
    head.z80 = g_z80;
    for (int i = 0; i < 3; ++i) head.bank[i] = g_bank[i];
    head.next_line = g_next_line_cyc; head.frame = g_frame; head.psg_cyc = g_psg_cyc;
    RetroStateIO io = {head.phaser, sizeof head.phaser, 0, RR_STATE_WRITE, true};
    lightphaser_state(&io);
    if (!io.ok || io.pos != RR_SNAP_PHASER_BYTES) return 0;
    memcpy(out, &head, sizeof head); out += sizeof head;
    memcpy(out, g_ram, sizeof g_ram); out += sizeof g_ram;
    memcpy(out, &g_vdp, sizeof g_vdp); out += sizeof g_vdp;
    smsrecomp_video_snap_save(out); out += smsrecomp_video_snap_size();
    smsrecomp_psg_snap_save(out);
    return size;
}
bool smsrecomp_snap_load(const void *buffer, size_t size) {
    if (!buffer || !size || size != smsrecomp_snap_bound()) return false;
    const uint8_t *in = (const uint8_t *)buffer;
    RrSnapHead head;
    memcpy(&head, in, sizeof head); in += sizeof head;
    const unsigned model = (g_is_gg ? 1u : 0u) | (g_mapper_cm ? 2u : 0u) | (sms_light_phaser ? 4u : 0u) | (SMS_LINES_PER_FRAME == 313 ? 8u : 0u);
    if (head.magic != RR_SNAP_MAGIC || head.model != model) return false;
    const uint8_t *ram = in; in += sizeof g_ram;
    SmsVdp vdp;
    memcpy(&vdp, in, sizeof vdp); in += sizeof vdp;
    if (vdp.is_gg != g_is_gg || vdp.line < 0 || vdp.line >= SMS_LINES_PER_FRAME ||
        head.next_line != head.frame * SMS_CYC_PER_FRAME + (uint64_t)(vdp.line + 1) * SMS_CYC_PER_LINE ||
        head.z80.cyc >= head.next_line || head.z80.cyc < head.next_line - SMS_CYC_PER_LINE || head.psg_cyc > head.z80.cyc ||
        head.z80.im > 2) return false;
    RetroStateIO io = {head.phaser, sizeof head.phaser, 0, RR_STATE_CHECK, true};
    lightphaser_state(&io);
    if (!io.ok || io.pos != RR_SNAP_PHASER_BYTES) return false;
    const uint8_t *video = in; in += smsrecomp_video_snap_size();
    /* The two chips check their own bytes before they apply them; a buffer that is the kit's own never fails here. */
    if (!smsrecomp_psg_snap_load(in)) return false;
    if (!smsrecomp_video_snap_load(video)) return false;
    io.pos = 0; io.mode = RR_STATE_APPLY;
    lightphaser_state(&io);
    g_z80 = head.z80;
    for (int i = 0; i < 3; ++i) g_bank[i] = head.bank[i];
    memcpy(g_ram, ram, sizeof g_ram);
    g_vdp = vdp;
    g_next_line_cyc = g_sync_deadline = head.next_line; g_frame = head.frame; g_psg_cyc = head.psg_cyc;
    smsrecomp_measured_guest_cycles = head.z80.cyc;
    g_hz_init = false; smsrecomp_interp_depth = 0; reference_cycle_base = 0;
    smsrecomp_in_io = smsrecomp_stop_pending = false;
    return true;
}

/* The frame edge of a session (native/gamestate.h): rides on the request word the banked loop already tests after every
 * completed instruction, so a game without a session pays nothing. */
static bool (*smsrecomp_frame_edge)(void);
void smsrecomp_set_frame_edge_callback(bool (*callback)(void)) { smsrecomp_frame_edge = callback; }
bool smsrecomp_defer_frame(void) {
#ifdef SMSRECOMP_BANKED_AOT
    /* One edge at a time: a second frame end before the first was delivered (an endless stream of redundant prefixes, which
     * completes no instruction) is run by the host in place. */
    if (!smsrecomp_frame_edge || smsrecomp_state_pending || getenv("SMSRECOMP_REFERENCE")) return false;
    smsrecomp_state_pending = RR_FRAME_EDGE;
    return true;
#else
    return false;
#endif
}

/* The envelope is shared (state_envelope.h): the Master System's magic, schema, model and cartridge identity. */
static uint32_t smsrecomp_state_crc(const uint8_t *bytes, size_t size) { return rr_state_crc(bytes, size); }
static RetroStateEnvelope smsrecomp_state_envelope(void) {
    RetroStateEnvelope e = {"RRSTATE\0", RR_STATE_SCHEMA, RR_STATE_MACHINE, sms_rom_sha256, smsrecomp_machine_state};
    return e;
}
static int smsrecomp_state_save(void) {
    uint8_t *data = (uint8_t *)malloc(RR_STATE_CAPACITY);
    if (!data) return RR_STATE_IO_ERROR;
    RetroStateEnvelope envelope = smsrecomp_state_envelope();
    size_t size = 0;
    if (rr_state_envelope_write(&envelope, data, RR_STATE_CAPACITY, &size) != RR_STATE_OK) { free(data); return RR_STATE_INVALID; }
    wchar_t temporary[80]; swprintf(temporary, 80, L"-quicksave-%lu.state.tmp", rr_process_id());
    FILE *f = retro_game_file(temporary, L"wb");
    bool ok = f && fwrite(data, size, 1, f) == 1;
    if (ok) ok = rr_flush_file(f);
    if (f && fclose(f) != 0) ok = false;
    free(data);
    if (ok) ok = retro_game_file_replace(temporary, L"-quicksave.state") != 0;
    if (!ok) retro_game_file_reset(temporary);
    return ok ? RR_STATE_OK : RR_STATE_IO_ERROR;
}
static int smsrecomp_state_load(void) {
    FILE *f = retro_game_file(L"-quicksave.state", L"rb");
    if (!f) return errno == ENOENT ? RR_STATE_MISSING : RR_STATE_IO_ERROR;
    uint8_t *data = (uint8_t *)malloc(RR_STATE_CAPACITY);
    if (!data) { fclose(f); return RR_STATE_IO_ERROR; }
    size_t size = fread(data, 1, RR_STATE_CAPACITY, f);
    int extra = fgetc(f); bool read_ok = !ferror(f); fclose(f);
    int result = RR_STATE_INVALID;
    if (read_ok && extra == EOF) {
        RetroStateEnvelope envelope = smsrecomp_state_envelope();
        result = rr_state_envelope_read(&envelope, data, size);
    }
    free(data); return result;
}
static void smsrecomp_state_service(void) {
    int operation = smsrecomp_state_pending;
    if (!operation) return;
    smsrecomp_state_pending = 0;
    if (operation == RR_FRAME_EDGE) {
        if (smsrecomp_frame_edge && !smsrecomp_frame_edge()) smsrecomp_stop_pending = true;
        return;
    }
    int result = operation == RR_QUICKSAVE ? smsrecomp_state_save() : smsrecomp_state_load();
    fprintf(stderr, "[gamestate] %s result=%d guest_frame=%llu guest_pc=%04X\n",
        operation == RR_QUICKSAVE ? "save" : "load", result, (unsigned long long)g_frame, g_z80.pc);
    if (smsrecomp_state_callback) smsrecomp_state_callback(operation, result);
}
