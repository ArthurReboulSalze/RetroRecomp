/* Retro-Recomp X68000 machine snapshot format RRX68MS1.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * One symmetric API saves and loads: every field is visited by the same call
 * in both directions. Integers are little-endian with fixed widths; 68000 bus
 * memory is stored in 68000 (big-endian) word order. Sections carry a tag, a
 * version and a length, and must appear in the documented order. Nothing that
 * depends on the host (pointers, bool/enum/long sizes, struct padding) is
 * ever copied as raw bytes.
 */
#ifndef RR_X68000_STATE_H
#define RR_X68000_STATE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RR_STATE_MAGIC "RRX68MS1"
#define RR_STATE_FORMAT 1

typedef struct RRState {
   uint8_t *data;      /* Saving: growable buffer (NULL = measure only). */
   size_t size;        /* Saving: bytes written; loading: bytes available. */
   size_t pos;
   size_t capacity;
   int loading;
   int error;          /* Sticky: any failure makes the whole operation fail. */
   const char *reason; /* First failure, for diagnostics. */
} RRState;

void rr_state_fail(RRState *s, const char *reason);

/* Fixed-width scalars. */
void rr_state_u8(RRState *s, uint8_t *v);
void rr_state_i8(RRState *s, int8_t *v);
void rr_state_u16(RRState *s, uint16_t *v);
void rr_state_i16(RRState *s, int16_t *v);
void rr_state_u32(RRState *s, uint32_t *v);
void rr_state_i32(RRState *s, int32_t *v);
void rr_state_u64(RRState *s, uint64_t *v);
void rr_state_f32(RRState *s, float *v);
void rr_state_f64(RRState *s, double *v);

/* Host-sized types, always stored with an explicit width. */
void rr_state_int(RRState *s, int *v);          /* 32-bit, range checked */
void rr_state_uint(RRState *s, unsigned *v);    /* 32-bit, range checked */
void rr_state_bool(RRState *s, int *v);         /* one byte, 0 or 1 */
#ifdef __cplusplus
void rr_state_cbool(RRState *s, bool *v);       /* C/C++ bool, one byte */
#else
void rr_state_cbool(RRState *s, _Bool *v);
#endif

/* Arrays. */
void rr_state_bytes(RRState *s, void *v, size_t count);
void rr_state_u16s(RRState *s, uint16_t *v, size_t count);
void rr_state_i16s(RRState *s, int16_t *v, size_t count);
void rr_state_u32s(RRState *s, uint32_t *v, size_t count);
void rr_state_i32s(RRState *s, int32_t *v, size_t count);
void rr_state_ints(RRState *s, int *v, size_t count);
/* 68000 bus memory held in host word-swapped order (address XOR 1). */
void rr_state_bus_words(RRState *s, uint8_t *v, size_t bytes);

/* Sections: begin returns a mark for end. Loading verifies tag, version and
 * that exactly the declared length was consumed. */
size_t rr_state_begin(RRState *s, const char tag[4], uint16_t version);
void rr_state_end(RRState *s, size_t mark);

/* Index of a pointer inside [base, base + count) or a stored index, validated. */
void rr_state_offset(RRState *s, uint32_t *offset, uint32_t limit);

#ifdef __cplusplus
}
#endif

#endif
