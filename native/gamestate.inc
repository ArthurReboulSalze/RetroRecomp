/* Included in glue after its CPU, bus and timing definitions. No ROM bytes,
 * pointers, OS handles, C stacks, host options or learning data are saved. */
#include "gamestate.h"
#include "state_io.h"
#include <io.h>
#include <errno.h>
#include <windows.h>
#define RR_STATE_SCHEMA 1u
#define RR_STATE_MACHINE (g_is_gg ? 3u : (SMS_LINES_PER_FRAME == 313 ? 2u : 1u))
#define RR_STATE_HEADER 88u
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

static uint32_t smsrecomp_state_crc(const uint8_t *bytes, size_t size) {
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < size; ++i) {
        crc ^= bytes[i];
        for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1)));
    }
    return ~crc;
}
static int smsrecomp_state_save(void) {
    uint8_t *data = (uint8_t *)malloc(RR_STATE_CAPACITY);
    if (!data) return RR_STATE_IO_ERROR;
    RetroStateIO body = {data + RR_STATE_HEADER, RR_STATE_CAPACITY - RR_STATE_HEADER, 0, RR_STATE_WRITE, true};
    smsrecomp_machine_state(&body);
    if (!body.ok) { free(data); return RR_STATE_INVALID; }
    memcpy(data, "RRSTATE\0", 8);
    RetroStateIO header = {data, RR_STATE_HEADER, 8, RR_STATE_WRITE, true};
    rr_state_word(&header, RR_STATE_SCHEMA, 4, UINT32_MAX); rr_state_word(&header, RR_STATE_MACHINE, 4, UINT32_MAX);
    rr_state_bytes(&header, (void *)sms_rom_sha256, 64);
    rr_state_word(&header, body.pos, 4, UINT32_MAX);
    rr_state_word(&header, smsrecomp_state_crc(body.data, body.pos), 4, UINT32_MAX);
    wchar_t temporary[80]; swprintf(temporary, 80, L"-quicksave-%lu.state.tmp", GetCurrentProcessId());
    FILE *f = retro_game_file(temporary, L"wb");
    bool ok = f && fwrite(data, RR_STATE_HEADER + body.pos, 1, f) == 1;
    if (ok) ok = fflush(f) == 0 && _commit(_fileno(f)) == 0;
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
    if (read_ok && size >= RR_STATE_HEADER && extra == EOF && !memcmp(data, "RRSTATE\0", 8)) {
        RetroStateIO header = {data, RR_STATE_HEADER, 8, RR_STATE_CHECK, true};
        uint32_t schema = (uint32_t)rr_state_word(&header, 0, 4, UINT32_MAX);
        uint32_t machine = (uint32_t)rr_state_word(&header, 0, 4, UINT32_MAX);
        bool identity = !memcmp(data + header.pos, sms_rom_sha256, 64); header.pos += 64;
        size_t length = (size_t)rr_state_word(&header, 0, 4, UINT32_MAX);
        uint32_t crc = (uint32_t)rr_state_word(&header, 0, 4, UINT32_MAX);
        if (schema != RR_STATE_SCHEMA || machine != RR_STATE_MACHINE || !identity) result = RR_STATE_INCOMPATIBLE;
        else if (header.ok && length == size - RR_STATE_HEADER && crc == smsrecomp_state_crc(data + RR_STATE_HEADER, length)) {
            RetroStateIO body = {data + RR_STATE_HEADER, length, 0, RR_STATE_CHECK, true};
            smsrecomp_machine_state(&body);
            if (body.ok && body.pos == length) {
                body.pos = 0; body.mode = RR_STATE_APPLY; smsrecomp_machine_state(&body);
                result = RR_STATE_OK;
            }
        }
    }
    free(data); return result;
}
static void smsrecomp_state_service(void) {
    int operation = smsrecomp_state_pending;
    if (!operation) return;
    smsrecomp_state_pending = 0;
    int result = operation == RR_QUICKSAVE ? smsrecomp_state_save() : smsrecomp_state_load();
    fprintf(stderr, "[gamestate] %s result=%d guest_frame=%llu guest_pc=%04X\n",
        operation == RR_QUICKSAVE ? "save" : "load", result, (unsigned long long)g_frame, g_z80.pc);
    if (smsrecomp_state_callback) smsrecomp_state_callback(operation, result);
}
