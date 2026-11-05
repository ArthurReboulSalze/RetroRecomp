/* Retro-Recomp: resload_Decrunch formats (MIT). See rr_decrunch.h.
 *
 * RNC method 1, as the format works: an 18-byte header ("RNC", method, unpacked length, packed length, CRC-16 of the
 * unpacked data, CRC-16 of the packed data, leeway, chunk count), then a stream of 16-bit little-endian words read
 * least significant bit first, with runs of literal bytes in between. The reader keeps 16 bits of look-ahead: when a
 * literal run follows, the look-ahead word is in fact the first literal bytes, so the bits are taken again after the
 * run. Each chunk carries three Huffman tables (literal run lengths, match distances, match lengths: 5-bit count, 4-bit
 * code lengths, canonical codes stored bit-reversed), a 16-bit count of sub-chunks, then per sub-chunk a literal run
 * and, except for the last one, a match. A decoded value n >= 2 stands for 2^(n-1) plus n-1 more bits.
 */
#include "rr_decrunch.h"

#include <string.h>

static uint16_t crc16(const uint8_t *p, size_t n) {
    uint16_t crc = 0;
    for (size_t i = 0; i < n; i++) {
        crc ^= p[i];
        for (int k = 0; k < 8; k++) crc = (crc & 1) ? (uint16_t)((crc >> 1) ^ 0xA001u) : (uint16_t)(crc >> 1);
    }
    return crc;
}

static uint32_t be32(const uint8_t *p) { return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; }
static uint16_t be16(const uint8_t *p) { return (uint16_t)(p[0] << 8 | p[1]); }

int rr_pack_format(const uint8_t *h, size_t size) {
    if (size < 4) return RR_PACK_NONE;
    if (h[0] == 'R' && h[1] == 'N' && h[2] == 'C') return h[3] == 1 ? RR_PACK_RNC1 : h[3] == 2 ? RR_PACK_RNC2 : RR_PACK_NONE;
    if (!memcmp(h, "IMP!", 4) || !memcmp(h, "ATN!", 4)) return RR_PACK_IMP;
    if (!memcmp(h, "TPWM", 4)) return RR_PACK_TPWM;
    if (h[0] == 'C' && h[1] == 'r' && (h[2] == 'M' || h[2] == 'm') && (h[3] == '!' || h[3] == '2')) return RR_PACK_CRM;
    return RR_PACK_NONE;
}

const char *rr_pack_name(int f) {
    switch (f) {
    case RR_PACK_RNC1: return "RNC1";
    case RR_PACK_RNC2: return "RNC2";
    case RR_PACK_IMP: return "Imploder";
    case RR_PACK_TPWM: return "TPWM";
    case RR_PACK_CRM: return "Crunch-Mania";
    default: return "none";
    }
}

uint32_t rr_pack_unpacked_size(const uint8_t *d, size_t size) {
    int f = rr_pack_format(d, size);
    if ((f == RR_PACK_RNC1 || f == RR_PACK_RNC2) && size >= 18) return be32(d + 4);
    if ((f == RR_PACK_IMP || f == RR_PACK_TPWM) && size >= 8) return be32(d + 4);
    return 0;
}

/* ---- RNC method 1 ------------------------------------------------------------------------------------------- */

typedef struct Bits { const uint8_t *p, *end; uint32_t buf; int count; int bad; } Bits;
typedef struct Huff { int n; uint32_t code[32]; int len[32]; int value[32]; } Huff;

static uint32_t le_long(const Bits *b, const uint8_t *p) {
    uint8_t v[4] = {0, 0, 0, 0};
    for (int i = 0; i < 4; i++) if (p + i < b->end) v[i] = p[i];
    return (uint32_t)v[0] | (uint32_t)v[1] << 8 | (uint32_t)v[2] << 16 | (uint32_t)v[3] << 24;
}

static void bits_init(Bits *b) { b->buf = le_long(b, b->p); b->count = 16; }

static void bits_advance(Bits *b, int n) {
    b->buf >>= n;
    b->count -= n;
    if (b->count < 16) {
        b->p += 2;
        if (b->p > b->end + 2) b->bad = 1;
        b->buf |= le_long(b, b->p) << b->count;
        b->count += 16;
    }
}

static uint32_t bits_read(Bits *b, int n) {
    uint32_t v = b->buf & ((1u << n) - 1u);
    bits_advance(b, n);
    return v;
}

/* After a literal run: the top 16 look-ahead bits were literals; take the bits again from the current position. */
static void bits_refill(Bits *b) {
    b->count -= 16;
    b->buf &= (1u << b->count) - 1u;
    b->buf |= le_long(b, b->p) << b->count;
    b->count += 16;
}

static int huff_read_table(Bits *b, Huff *h) {
    int lengths[32];
    h->n = 0;
    int num = (int)bits_read(b, 5);
    if (!num) return 1;
    for (int i = 0; i < num; i++) lengths[i] = (int)bits_read(b, 4);
    uint32_t code = 0;
    for (int len = 1; len <= 16; len++) {
        for (int j = 0; j < num; j++) {
            if (lengths[j] != len) continue;
            uint32_t rev = 0;
            for (int k = 0; k < len; k++) rev |= ((code >> k) & 1u) << (len - 1 - k);
            h->code[h->n] = rev;
            h->len[h->n] = len;
            h->value[h->n] = j;
            h->n++;
            code++;
        }
        code <<= 1;
    }
    return 1;
}

static int huff_read(Bits *b, const Huff *h, uint32_t *out) {
    for (int i = 0; i < h->n; i++) {
        if ((b->buf & ((1u << h->len[i]) - 1u)) == h->code[i]) {
            bits_advance(b, h->len[i]);
            int v = h->value[i];
            *out = v < 2 ? (uint32_t)v : (1u << (v - 1)) | bits_read(b, v - 1);
            return 1;
        }
    }
    return 0;
}

static uint32_t rnc1(const uint8_t *data, size_t size, uint8_t *out, size_t cap, const char **why) {
    uint32_t unpacked = be32(data + 4), packed = be32(data + 8);
    if (18 + (size_t)packed > size) { *why = "RNC1 data shorter than its header says"; return 0; }
    if (unpacked > cap) { *why = "RNC1 output larger than the room given"; return 0; }
    if (crc16(data + 18, packed) != be16(data + 14)) { *why = "RNC1 packed CRC mismatch"; return 0; }
    Bits b = {data + 18, data + 18 + packed, 0, 0, 0};
    bits_init(&b);
    if (bits_read(&b, 1)) { *why = "RNC1 with a lock bit"; }       /* the lock flag: no effect on unpacking */
    if (bits_read(&b, 1)) { *why = "RNC1 encrypted with a key is not unpacked"; return 0; }
    *why = NULL;
    uint32_t o = 0;
    Huff raw, dist, len;
    while (o < unpacked) {
        huff_read_table(&b, &raw);
        huff_read_table(&b, &dist);
        huff_read_table(&b, &len);
        uint32_t chunks = bits_read(&b, 16);
        for (;;) {
            uint32_t n;
            if (!huff_read(&b, &raw, &n)) { *why = "RNC1 bad literal code"; return 0; }
            if (n) {
                if (o + n > unpacked || b.p + n > b.end) { *why = "RNC1 literal run out of range"; return 0; }
                memcpy(out + o, b.p, n);
                o += n;
                b.p += n;
                bits_refill(&b);
            }
            if (chunks <= 1) break;
            chunks--;
            uint32_t d, l;
            if (!huff_read(&b, &dist, &d) || !huff_read(&b, &len, &l)) { *why = "RNC1 bad match code"; return 0; }
            d += 1;
            l += 2;
            if (d > o || o + l > unpacked) { *why = "RNC1 match out of range"; return 0; }
            for (uint32_t k = 0; k < l; k++, o++) out[o] = out[o - d];
        }
        if (b.bad) { *why = "RNC1 stream ends early"; return 0; }
    }
    if (crc16(out, unpacked) != be16(data + 12)) { *why = "RNC1 unpacked CRC mismatch"; return 0; }
    return unpacked;
}

uint32_t rr_unpack(const uint8_t *data, size_t size, uint8_t *out, size_t cap, const char **why) {
    int f = rr_pack_format(data, size);
    *why = NULL;
    if (f == RR_PACK_RNC1 && size >= 18) return rnc1(data, size, out, cap, why);
    *why = f == RR_PACK_NONE ? "not a packed format" : "this packed format is not unpacked yet";
    return 0;
}
