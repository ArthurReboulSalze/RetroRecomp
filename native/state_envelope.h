#ifndef RETRO_RECOMP_STATE_ENVELOPE_H
#define RETRO_RECOMP_STATE_ENVELOPE_H
/* The quick-state envelope shared by the Z80 machines (the Master System and Game Gear, gamestate.inc; the MSX,
 * msx_machine/msx_state_file.inc): an 88-byte header then the machine's body. MIT, Retro-Recomp. Lifted from
 * gamestate.inc on 12 November 2026 with its bytes unchanged.
 *
 *   0   8  magic (the machine's, eight bytes)
 *   8   4  schema
 *  12   4  machine (a model of the profile: the Master System's NTSC, PAL or Game Gear; MSX1 or MSX2)
 *  16  64  identity: the game's SHA-256 as text
 *  80   4  body length
 *  84   4  CRC-32 of the body
 *  88      body: fixed-width little-endian fields (state_io.h), written by the machine's `body` callback
 *
 * A state is decoded twice: checked whole, then applied, so a refused state never touches the live machine. The file
 * itself (where it lives, its atomic replacement) is the caller's. */
#include "gamestate.h"
#include "state_io.h"

#define RR_STATE_ENVELOPE_HEADER 88u

typedef struct {
    const char *magic;                 /* eight bytes */
    uint32_t schema, machine;
    const char *identity;              /* 64 characters */
    void (*body)(RetroStateIO *io);    /* writes, checks or applies the machine (io->mode) */
} RetroStateEnvelope;

static uint32_t rr_state_crc(const uint8_t *bytes, size_t size) {
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < size; ++i) {
        crc ^= bytes[i];
        for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1)));
    }
    return ~crc;
}

/* The whole state into `data` (`capacity` bytes): RR_STATE_OK and its size in `*size`, or RR_STATE_INVALID when the
 * machine refused to write itself or the capacity is too small. */
static int rr_state_envelope_write(const RetroStateEnvelope *e, uint8_t *data, size_t capacity, size_t *size) {
    if (capacity < RR_STATE_ENVELOPE_HEADER) return RR_STATE_INVALID;
    RetroStateIO body = {data + RR_STATE_ENVELOPE_HEADER, capacity - RR_STATE_ENVELOPE_HEADER, 0, RR_STATE_WRITE, true};
    e->body(&body);
    if (!body.ok) return RR_STATE_INVALID;
    memcpy(data, e->magic, 8);
    RetroStateIO header = {data, RR_STATE_ENVELOPE_HEADER, 8, RR_STATE_WRITE, true};
    rr_state_word(&header, e->schema, 4, UINT32_MAX); rr_state_word(&header, e->machine, 4, UINT32_MAX);
    rr_state_bytes(&header, (void *)e->identity, 64);
    rr_state_word(&header, body.pos, 4, UINT32_MAX);
    rr_state_word(&header, rr_state_crc(body.data, body.pos), 4, UINT32_MAX);
    *size = RR_STATE_ENVELOPE_HEADER + body.pos;
    return RR_STATE_OK;
}

/* A state read whole (`size` bytes): checked, then applied only when every check passed. RR_STATE_OK,
 * RR_STATE_INCOMPATIBLE (another schema, machine or game) or RR_STATE_INVALID (not a state, damaged, cut). */
static int rr_state_envelope_read(const RetroStateEnvelope *e, uint8_t *data, size_t size) {
    if (size < RR_STATE_ENVELOPE_HEADER || memcmp(data, e->magic, 8)) return RR_STATE_INVALID;
    RetroStateIO header = {data, RR_STATE_ENVELOPE_HEADER, 8, RR_STATE_CHECK, true};
    uint32_t schema = (uint32_t)rr_state_word(&header, 0, 4, UINT32_MAX);
    uint32_t machine = (uint32_t)rr_state_word(&header, 0, 4, UINT32_MAX);
    bool identity = !memcmp(data + header.pos, e->identity, 64); header.pos += 64;
    size_t length = (size_t)rr_state_word(&header, 0, 4, UINT32_MAX);
    uint32_t crc = (uint32_t)rr_state_word(&header, 0, 4, UINT32_MAX);
    if (schema != e->schema || machine != e->machine || !identity) return RR_STATE_INCOMPATIBLE;
    if (!header.ok || length != size - RR_STATE_ENVELOPE_HEADER ||
        crc != rr_state_crc(data + RR_STATE_ENVELOPE_HEADER, length)) return RR_STATE_INVALID;
    RetroStateIO body = {data + RR_STATE_ENVELOPE_HEADER, length, 0, RR_STATE_CHECK, true};
    e->body(&body);
    if (!body.ok || body.pos != length) return RR_STATE_INVALID;
    body.pos = 0; body.mode = RR_STATE_APPLY; e->body(&body);
    return RR_STATE_OK;
}
#endif
