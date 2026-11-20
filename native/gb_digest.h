/* The digest of the Game Boy machine's state (native/gb_machine_state.h and the sound unit's own part, audio.c): FNV-1a over named
 * fields in a fixed byte order, one value at a time and always little-endian, so the same state gives the same number on every
 * system and with every compiler. Never a raw struct (padding, pointers). Original RetroRecomp code: MIT. */
#ifndef RR_GB_DIGEST_H
#define RR_GB_DIGEST_H
#include <stddef.h>
#include <stdint.h>

typedef struct RrGbDigest { uint64_t hash; } RrGbDigest;

static inline void rr_gb_dg_init(RrGbDigest* d) { d->hash = 0xcbf29ce484222325ull; }
static inline void rr_gb_dg_u8(RrGbDigest* d, uint8_t v) { d->hash = (d->hash ^ v) * 0x100000001b3ull; }
static inline void rr_gb_dg_u16(RrGbDigest* d, uint16_t v) { rr_gb_dg_u8(d, (uint8_t)v); rr_gb_dg_u8(d, (uint8_t)(v >> 8)); }
static inline void rr_gb_dg_u32(RrGbDigest* d, uint32_t v) { rr_gb_dg_u16(d, (uint16_t)v); rr_gb_dg_u16(d, (uint16_t)(v >> 16)); }
static inline void rr_gb_dg_u64(RrGbDigest* d, uint64_t v) { rr_gb_dg_u32(d, (uint32_t)v); rr_gb_dg_u32(d, (uint32_t)(v >> 32)); }
static inline void rr_gb_dg_i32(RrGbDigest* d, int32_t v) { rr_gb_dg_u32(d, (uint32_t)v); }
static inline void rr_gb_dg_bool(RrGbDigest* d, int v) { rr_gb_dg_u8(d, v ? 1u : 0u); }
/* A block of bytes (memory), after a one-byte section mark so that two blocks never run into each other. */
static inline void rr_gb_dg_block(RrGbDigest* d, uint8_t mark, const uint8_t* data, size_t size) {
    rr_gb_dg_u8(d, mark);
    for (size_t i = 0; i < size; ++i) rr_gb_dg_u8(d, data[i]);
}
#endif
