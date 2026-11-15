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
    if (f == RR_PACK_CRM && size >= 14) return be32(d + 6);
    return 0;
}

uint32_t rr_pack_packed_size(const uint8_t *d, size_t size) {
    int f = rr_pack_format(d, size);
    if ((f == RR_PACK_RNC1 || f == RR_PACK_RNC2) && size >= 12) return 18 + be32(d + 8);
    if (f == RR_PACK_CRM && size >= 14) return 14 + be32(d + 10);
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

/* ---- Crunch-Mania ("CrM!", "Crm!", "CrM2", "Crm2") ----------------------------------------------------------------
 * Written for Retro-Recomp from the format as the "ancient" library describes it (Teemu Suutari, BSD-2-Clause, src/CRMDecompressor.cpp,
 * read, not copied). A 14-byte header (id, two bytes, unpacked size, packed size); the packed stream is read backward from its end, bits
 * least significant first, and the output is written backward from its end. Its last six bytes give the first bits: a long whose top
 * (16 + shift) bits are pending, and the shift. "CrM!" is the standard mode (fixed codes), "CrM2" the LZH mode (Huffman tables per
 * block); a lower-case "m" means the output is delta coded ("sampled"). */

typedef struct CrmBits { const uint8_t *start, *p; uint32_t buf; int count; int bad; } CrmBits;

static uint32_t crm_bits(CrmBits *b, int n) {
    uint32_t v = 0;
    int pos = 0;
    while (n) {
        if (!b->count) {
            if (b->p <= b->start) { b->bad = 1; return 0; }
            b->buf = *--b->p;
            b->count = 8;
        }
        int k = n < b->count ? n : b->count;
        v |= (b->buf & ((1u << k) - 1u)) << pos;
        b->buf >>= k;
        b->count -= k;
        n -= k;
        pos += k;
    }
    return v;
}

/* A table of the LZH mode: codes numbered in order of their depth, each depth's codes consecutive (read most significant bit first). */
typedef struct CrmHuff { int max, n; uint32_t first[16], count[16], offset[16]; uint16_t value[512]; } CrmHuff;

static int crm_table(CrmBits *b, CrmHuff *h, int code_length) {
    uint32_t lengths[15];
    h->max = (int)crm_bits(b, 4);
    h->n = 0;
    if (!h->max) return 0;
    for (int i = 0; i < h->max; i++) lengths[i] = crm_bits(b, i + 1 < code_length ? i + 1 : code_length);
    uint32_t code = 0;
    for (int depth = 1; depth <= h->max; depth++) {
        h->first[depth] = code >> (h->max - depth);
        h->count[depth] = lengths[depth - 1];
        h->offset[depth] = (uint32_t)h->n;
        for (uint32_t i = 0; i < lengths[depth - 1]; i++) {
            if (h->n >= 512) return 0;
            h->value[h->n++] = (uint16_t)crm_bits(b, code_length);
            code += 1u << (h->max - depth);
        }
    }
    return !b->bad && code <= 1u << h->max;
}

static int crm_decode(CrmBits *b, const CrmHuff *h, uint32_t *out) {
    uint32_t acc = 0;
    for (int len = 1; len <= h->max; len++) {
        acc = acc << 1 | crm_bits(b, 1);
        if (acc - h->first[len] < h->count[len]) { *out = h->value[h->offset[len] + acc - h->first[len]]; return 1; }
    }
    return 0;
}

static uint32_t crm(const uint8_t *data, size_t size, uint8_t *out, size_t cap, const char **why) {
    uint32_t unpacked = be32(data + 6), packed = be32(data + 10);
    int lzh = data[3] == '2', sampled = data[2] == 'm';
    if (!unpacked || packed < 6 || 14 + (size_t)packed > size) { *why = "Crunch-Mania data shorter than its header says"; return 0; }
    if (unpacked > cap) { *why = "Crunch-Mania output larger than the room given"; return 0; }
    const uint8_t *tail = data + 14 + packed - 6;
    uint32_t shift = be16(tail + 4);
    if (shift > 16) { *why = "Crunch-Mania stream with a bad start"; return 0; }
    CrmBits b = {data + 14, tail, be32(tail) >> (16 - shift), (int)shift + 16, 0};
    uint32_t o = unpacked;          /* the output is written backward: o bytes are left to write */
#define CRM_PUT(v) do { if (!o) { *why = "Crunch-Mania output overruns"; return 0; } out[--o] = (uint8_t)(v); } while (0)
#define CRM_COPY(distance, count) do { uint32_t d_ = (distance), c_ = (count); \
        if (!d_ || c_ > o || o + d_ > unpacked) { *why = "Crunch-Mania match out of range"; return 0; } \
        for (uint32_t k_ = 0; k_ < c_; k_++, o--) out[o - 1] = out[o + d_ - 1]; } while (0)
    if (lzh) {
        do {
            CrmHuff lengths, distances;
            if (!crm_table(&b, &lengths, 9) || !crm_table(&b, &distances, 4)) { *why = "Crunch-Mania bad table"; return 0; }
            uint32_t items = crm_bits(&b, 16) + 1;
            for (uint32_t i = 0; i < items; i++) {
                uint32_t count, bits;
                if (!crm_decode(&b, &lengths, &count)) { *why = "Crunch-Mania bad length code"; return 0; }
                if (count & 0x100) { CRM_PUT(count); continue; }
                if (!crm_decode(&b, &distances, &bits)) { *why = "Crunch-Mania bad distance code"; return 0; }
                uint32_t distance = bits ? (crm_bits(&b, (int)bits) | 1u << bits) + 1 : crm_bits(&b, 1) + 1;
                CRM_COPY(distance, count + 3);
            }
            if (b.bad) { *why = "Crunch-Mania stream ends early"; return 0; }
        } while (crm_bits(&b, 1));
    } else {
        static const uint32_t length_bits[4] = {1, 2, 4, 8}, length_base[4] = {0, 2, 6, 22};
        static const uint32_t distance_bits[3] = {5, 9, 14}, distance_base[3] = {0, 32, 544};
        while (o) {
            if (crm_bits(&b, 1)) { CRM_PUT(crm_bits(&b, 8)); continue; }
            int li = !crm_bits(&b, 1) ? 0 : !crm_bits(&b, 1) ? 1 : !crm_bits(&b, 1) ? 2 : 3;
            uint32_t count = length_base[li] + crm_bits(&b, (int)length_bits[li]) + 2;
            if (count == 23) {
                count = crm_bits(&b, 1) ? crm_bits(&b, 5) + 15 : crm_bits(&b, 14) + 15;
                for (uint32_t i = 0; i < count; i++) CRM_PUT(crm_bits(&b, 8));
            } else {
                if (count > 23) count--;
                int di = !crm_bits(&b, 1) ? 1 : !crm_bits(&b, 1) ? 0 : 2;
                CRM_COPY(distance_base[di] + crm_bits(&b, (int)distance_bits[di]), count);
            }
            if (b.bad) { *why = "Crunch-Mania stream ends early"; return 0; }
        }
    }
#undef CRM_PUT
#undef CRM_COPY
    if (o || b.bad) { *why = "Crunch-Mania stream ends early"; return 0; }
    if (sampled) {
        uint8_t sum = 0;
        for (uint32_t i = 0; i < unpacked; i++) { sum = (uint8_t)(sum + out[i]); out[i] = sum; }
    }
    return unpacked;
}

uint32_t rr_unpack(const uint8_t *data, size_t size, uint8_t *out, size_t cap, const char **why) {
    int f = rr_pack_format(data, size);
    *why = NULL;
    if (f == RR_PACK_RNC1 && size >= 18) return rnc1(data, size, out, cap, why);
    if (f == RR_PACK_CRM && size >= 20) return crm(data, size, out, cap, why);
    *why = f == RR_PACK_NONE ? "not a packed format" : "this packed format is not unpacked yet";
    return 0;
}
