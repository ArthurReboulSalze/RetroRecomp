#ifndef RETRO_RECOMP_STATE_IO_H
#define RETRO_RECOMP_STATE_IO_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>

/* Fixed-width little-endian fields, never C layouts or host addresses.
 * Decode twice: validate the complete immutable payload before applying it. */
enum { RR_STATE_WRITE, RR_STATE_CHECK, RR_STATE_APPLY };
typedef struct { uint8_t *data; size_t size, pos; int mode; bool ok; } RetroStateIO;
static uint64_t rr_state_word(RetroStateIO *io, uint64_t value, unsigned width, uint64_t maximum) {
    if (!io->ok || width > 8 || io->pos > io->size || width > io->size - io->pos) {
        io->ok = false; return 0;
    }
    if (io->mode == RR_STATE_WRITE) {
        for (unsigned i = 0; i < width; ++i) io->data[io->pos + i] = (uint8_t)(value >> (i * 8));
    } else {
        value = 0;
        for (unsigned i = 0; i < width; ++i) value |= (uint64_t)io->data[io->pos + i] << (i * 8);
    }
    io->pos += width;
    if (value > maximum) io->ok = false;
    return value;
}
static void rr_state_bytes(RetroStateIO *io, void *data, size_t size) {
    if (!io->ok || io->pos > io->size || size > io->size - io->pos) { io->ok = false; return; }
    if (io->mode == RR_STATE_WRITE) memcpy(io->data + io->pos, data, size);
    else if (io->mode == RR_STATE_APPLY) memcpy(data, io->data + io->pos, size);
    io->pos += size;
}
#define RR_FIELD(object, field, width, maximum) \
    (object).field = rr_state_word(io, (uint64_t)(object).field, width, maximum)

void smsrecomp_video_state(RetroStateIO *io);
void smsrecomp_psg_state(RetroStateIO *io);
void lightphaser_state(RetroStateIO *io);
#endif
