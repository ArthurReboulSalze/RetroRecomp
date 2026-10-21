/* Retro-Recomp X68000 machine snapshot format RRX68MS1 (see rr_state.h).
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 */
#include <stdlib.h>
#include <string.h>

#include "rr_state.h"

void rr_state_fail(RRState *s, const char *reason)
{
   if (!s->error) {
      s->error = 1;
      s->reason = reason;
   }
}

static uint8_t *room(RRState *s, size_t count)
{
   if (s->error)
      return NULL;
   if (s->loading) {
      if (count > s->size - s->pos) {
         rr_state_fail(s, "snapshot truncated");
         return NULL;
      }
   } else if (s->data && s->pos + count > s->capacity) {
      size_t capacity = s->capacity ? s->capacity : 65536;
      uint8_t *grown;
      while (capacity < s->pos + count)
         capacity *= 2;
      grown = (uint8_t *)realloc(s->data, capacity);
      if (!grown) {
         rr_state_fail(s, "out of memory");
         return NULL;
      }
      memset(grown + s->capacity, 0, capacity - s->capacity);
      s->data = grown;
      s->capacity = capacity;
   }
   return s->data ? s->data + s->pos : NULL;
}

static void advance(RRState *s, size_t count)
{
   if (s->error)
      return;
   s->pos += count;
   if (!s->loading && s->pos > s->size)
      s->size = s->pos;
}

static void raw_le(RRState *s, uint64_t *value, unsigned width)
{
   uint8_t *p = room(s, width);
   unsigned i;
   if (s->error)
      return;
   if (s->loading) {
      uint64_t v = 0;
      for (i = 0; i < width; i++)
         v |= (uint64_t)p[i] << (8 * i);
      *value = v;
   } else if (p) {
      for (i = 0; i < width; i++)
         p[i] = (uint8_t)(*value >> (8 * i));
   }
   advance(s, width);
}

#define SCALAR(name, type, width, cast)                  \
   void rr_state_##name(RRState *s, type *v)             \
   {                                                     \
      uint64_t value = (uint64_t)(cast)*v;               \
      raw_le(s, &value, width);                          \
      if (s->loading && !s->error)                       \
         *v = (type)(cast)value;                         \
   }

SCALAR(u8, uint8_t, 1, uint8_t)
SCALAR(i8, int8_t, 1, uint8_t)
SCALAR(u16, uint16_t, 2, uint16_t)
SCALAR(i16, int16_t, 2, uint16_t)
SCALAR(u32, uint32_t, 4, uint32_t)
SCALAR(i32, int32_t, 4, uint32_t)
SCALAR(u64, uint64_t, 8, uint64_t)

void rr_state_f32(RRState *s, float *v)
{
   uint32_t bits;
   memcpy(&bits, v, 4);
   rr_state_u32(s, &bits);
   if (s->loading && !s->error)
      memcpy(v, &bits, 4);
}

void rr_state_f64(RRState *s, double *v)
{
   uint64_t bits;
   memcpy(&bits, v, 8);
   rr_state_u64(s, &bits);
   if (s->loading && !s->error)
      memcpy(v, &bits, 8);
}

void rr_state_int(RRState *s, int *v)
{
   int32_t value = (int32_t)*v;
   if (!s->loading && (long long)*v != (long long)value)
      rr_state_fail(s, "int outside 32-bit range");
   rr_state_i32(s, &value);
   if (s->loading && !s->error)
      *v = (int)value;
}

void rr_state_uint(RRState *s, unsigned *v)
{
   uint32_t value = (uint32_t)*v;
   if (!s->loading && (unsigned long long)*v != (unsigned long long)value)
      rr_state_fail(s, "unsigned outside 32-bit range");
   rr_state_u32(s, &value);
   if (s->loading && !s->error)
      *v = (unsigned)value;
}

void rr_state_bool(RRState *s, int *v)
{
   uint8_t value = *v ? 1 : 0;
   rr_state_u8(s, &value);
   if (s->loading && !s->error) {
      if (value > 1)
         rr_state_fail(s, "invalid boolean");
      else
         *v = value;
   }
}

void rr_state_cbool(RRState *s, _Bool *v)
{
   /* Read the stored byte: a compiler may pass an uninitialised bool through
    * `*v ? 1 : 0` unchanged, which would write a value no load accepts. */
   unsigned char raw;
   int value;
   memcpy(&raw, v, 1);
   value = raw != 0;
   rr_state_bool(s, &value);
   if (s->loading && !s->error)
      *v = value != 0;
}

void rr_state_bytes(RRState *s, void *v, size_t count)
{
   uint8_t *p = room(s, count);
   if (s->error)
      return;
   if (s->loading)
      memcpy(v, p, count);
   else if (p)
      memcpy(p, v, count);
   advance(s, count);
}

#define ARRAY(name, type, single)                               \
   void rr_state_##name(RRState *s, type *v, size_t count)      \
   {                                                            \
      size_t i;                                                 \
      for (i = 0; i < count && !s->error; i++)                  \
         single(s, &v[i]);                                      \
   }

ARRAY(u16s, uint16_t, rr_state_u16)
ARRAY(i16s, int16_t, rr_state_i16)
ARRAY(u32s, uint32_t, rr_state_u32)
ARRAY(i32s, int32_t, rr_state_i32)
ARRAY(ints, int, rr_state_int)

void rr_state_bus_words(RRState *s, uint8_t *v, size_t bytes)
{
   uint8_t *p;
   size_t i;
   if (bytes & 1) {
      rr_state_fail(s, "odd bus memory size");
      return;
   }
   p = room(s, bytes);
   if (s->error)
      return;
   if (s->loading) {
      for (i = 0; i < bytes; i += 2) {
         v[i] = p[i + 1];
         v[i + 1] = p[i];
      }
   } else if (p) {
      for (i = 0; i < bytes; i += 2) {
         p[i] = v[i + 1];
         p[i + 1] = v[i];
      }
   }
   advance(s, bytes);
}

size_t rr_state_begin(RRState *s, const char tag[4], uint16_t version)
{
   uint8_t name[4];
   uint16_t stored = version;
   uint32_t length = 0;
   size_t mark;

   memcpy(name, tag, 4);
   rr_state_bytes(s, name, 4);
   if (s->loading && !s->error && memcmp(name, tag, 4))
      rr_state_fail(s, "unexpected snapshot section");
   rr_state_u16(s, &stored);
   if (s->loading && !s->error && stored != version)
      rr_state_fail(s, "unsupported snapshot section version");
   mark = s->pos;
   rr_state_u32(s, &length);
   if (s->loading && !s->error && length > s->size - s->pos)
      rr_state_fail(s, "snapshot section exceeds data");
   return mark;
}

void rr_state_end(RRState *s, size_t mark)
{
   size_t body = mark + 4;
   if (s->error)
      return;
   if (s->loading) {
      uint32_t length = (uint32_t)s->data[mark] | ((uint32_t)s->data[mark + 1] << 8) |
                        ((uint32_t)s->data[mark + 2] << 16) | ((uint32_t)s->data[mark + 3] << 24);
      if (s->pos - body != length)
         rr_state_fail(s, "snapshot section length mismatch");
   } else if (s->data) {
      uint32_t length = (uint32_t)(s->pos - body);
      s->data[mark] = (uint8_t)length;
      s->data[mark + 1] = (uint8_t)(length >> 8);
      s->data[mark + 2] = (uint8_t)(length >> 16);
      s->data[mark + 3] = (uint8_t)(length >> 24);
   }
}

void rr_state_offset(RRState *s, uint32_t *offset, uint32_t limit)
{
   rr_state_u32(s, offset);
   if (!s->error && *offset > limit)
      rr_state_fail(s, "snapshot offset outside its buffer");
}
