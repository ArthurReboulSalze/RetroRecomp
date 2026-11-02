/* QSound high-level model, see cps1_qsound.h. Adapted from MAME's qsoundhle.cpp (BSD-3-Clause, superctr and Valley Bell). */
#include "cps1_qsound.h"
#include <string.h>

enum {
    DATA_PAN_TAB = 0x110, DATA_ADPCM_TAB = 0x9dc, DATA_FILTER_TAB = 0xd53,
    STATE_BOOT = 0x000, STATE_INIT1 = 0x288, STATE_INIT2 = 0x61a, STATE_REFRESH1 = 0x039, STATE_REFRESH2 = 0x04f,
    STATE_NORMAL1 = 0x314, STATE_NORMAL2 = 0x6b2,
    PAN_TABLE_DRY = 0, PAN_TABLE_WET = 98, PAN_TABLE_CH_OFFSET = 196, FILTER_ENTRY_SIZE = 95,
    DELAY_BASE_OFFSET = 0x554, DELAY_BASE_OFFSET2 = 0x53c
};

/* MAME shifts signed values left; here the shift is done on the unsigned value so the wrap-around is defined. */
static int32_t shl(int32_t value, unsigned bits) { return (int32_t)((uint32_t)value << bits); }
static int32_t clamp(int32_t value, int32_t low, int32_t high) { return value < low ? low : value > high ? high : value; }
static uint16_t dsp(const cps1_qsound *q, unsigned address) { return q->dsp_rom[address & 0xfff]; }

/* A sample byte of the sample ROM, as the signed 16-bit value the DSP reads (bits 0-7 are tied to ground). MAME gives the ROM a 24-bit
 * address space, mirrored over the bits above the power of two that holds it (device_rom_interface::set_rom); a ROM that is not a power of
 * two is unmapped between its end and that power of two, which reads 0. */
int16_t cps1_qsound_read_sample(const cps1_qsound *q, uint16_t bank, uint16_t address)
{
    const uint32_t at = ((uint32_t)(bank & 0x7fff) << 16 | address) & 0xffffffu;
    const size_t inside = (size_t)at & q->sample_mask;
    const uint8_t value = q->samples && inside < q->sample_bytes ? q->samples[inside] : 0;
    return (int16_t)(value << 8);
}
#define read_sample cps1_qsound_read_sample

/* A PCM voice: 16 of them, each updated every sample with full rate and volume control. */
static int16_t voice_update(const cps1_qsound *q, cps1_qs_voice *v, int32_t *echo_out)
{
    const int16_t output = (int16_t)((v->volume * read_sample(q, v->bank, (uint16_t)v->addr)) >> 14);
    *echo_out = (int32_t)((uint32_t)*echo_out + (uint32_t)shl((int32_t)output * v->echo, 2));
    int32_t phase = v->rate + (shl(v->addr, 12) | (v->phase >> 4));
    if ((phase >> 12) >= v->end_addr) phase -= shl(v->loop_len, 12);
    phase = clamp(phase, -0x8000000, 0x7ffffff);
    v->addr = (int16_t)(phase >> 12);
    v->phase = (uint16_t)(shl(phase, 4) & 0xffff);
    return output;
}

/* An ADPCM voice (Capcom never used them): one of the three is updated every sample, so the rate is a third of the master one. */
static int16_t adpcm_update(const cps1_qsound *q, cps1_qs_adpcm *a, int16_t current, int nibble)
{
    int8_t step;
    if (!nibble) {
        if (a->cur_addr == a->end_addr) a->cur_vol = 0;
        if (a->flag) {
            current = 0;
            a->flag = 0;
            a->step_size = 10;
            a->cur_vol = a->volume;
            a->cur_addr = a->start_addr;
        }
        step = (int8_t)(read_sample(q, a->bank, a->cur_addr) >> 8);
    } else {
        step = (int8_t)(read_sample(q, a->bank, a->cur_addr++) >> 4);
    }
    step = (int8_t)(step >> 4);
    int32_t delta = ((1 + (step * 2 < 0 ? -step * 2 : step * 2)) * a->step_size) >> 1;
    if (step <= 0) delta = -delta;
    delta = clamp(delta + current, -32768, 32767);
    const int16_t next = (int16_t)((dsp(q, (uint16_t)(DATA_ADPCM_TAB + 8 + step)) * a->step_size) >> 6);
    a->step_size = (int16_t)clamp(next, 1, 2000);
    return (int16_t)((delta * a->cur_vol) >> 16);
}

/* The echo: a moving average of the delay line's output, fed back. */
static int16_t echo_apply(cps1_qs_echo *e, int32_t input)
{
    int32_t old = e->delay_line[e->delay_pos];
    const int32_t last = e->last_sample;
    e->last_sample = (int16_t)old;
    old = (old + last) >> 1;
    const int32_t fresh = (int32_t)((uint32_t)input + (uint32_t)shl(old * e->feedback, 2));
    e->delay_line[e->delay_pos++] = (int16_t)(fresh >> 16);
    if (e->delay_pos >= e->length) e->delay_pos = 0;
    return (int16_t)old;
}

/* The FIR filter of the Q1 transfer function. */
static int32_t fir_apply(cps1_qs_fir *f, int16_t input)
{
    int32_t output = 0;
    int tap = 0;
    for (; tap < f->tap_count - 1; tap++) {
        output -= shl(f->taps[tap] * f->delay_line[f->delay_pos++], 2);
        if (f->delay_pos >= f->tap_count - 1) f->delay_pos = 0;
    }
    output -= shl(f->taps[tap] * input, 2);
    f->delay_line[f->delay_pos++] = input;
    if (f->delay_pos >= f->tap_count - 1) f->delay_pos = 0;
    return output;
}

static int32_t delay_apply(cps1_qs_delay *d, int32_t input)
{
    d->delay_line[d->write_pos++] = (int16_t)(input >> 16);
    if (d->write_pos >= 51) d->write_pos = 0;
    const int32_t output = d->delay_line[d->read_pos++] * d->volume;
    if (d->read_pos >= 51) d->read_pos = 0;
    return output;
}

static void delay_update(cps1_qs_delay *d)
{
    int16_t read = (int16_t)((d->write_pos - d->delay) % 51);
    if (read < 0) read = (int16_t)(read + 51);
    d->read_pos = read;
}

static void state_init(cps1_qsound *q)
{
    const int mode = q->state == STATE_INIT2;
    /* busy for 4 samples, the filter refresh included */
    if (q->state_counter >= 2) { q->state_counter = 0; q->state = q->next_state; return; }
    if (q->state_counter == 1) { q->state_counter++; return; }
    memset(q->voice, 0, sizeof q->voice);
    memset(q->adpcm, 0, sizeof q->adpcm);
    memset(q->filter, 0, sizeof q->filter);
    memset(q->alt_filter, 0, sizeof q->alt_filter);
    memset(q->wet, 0, sizeof q->wet);
    memset(q->dry, 0, sizeof q->dry);
    memset(&q->echo, 0, sizeof q->echo);
    for (int i = 0; i < 19; i++) { q->voice_pan[i] = DATA_PAN_TAB + 0x10; q->voice_output[i] = 0; }
    for (int i = 0; i < 16; i++) q->voice[i].bank = 0x8000;
    for (int i = 0; i < 3; i++) q->adpcm[i].bank = 0x8000;
    if (!mode) {
        q->wet[0].delay = 0; q->dry[0].delay = 46; q->wet[1].delay = 0; q->dry[1].delay = 48;
        q->filter[0].table_pos = DATA_FILTER_TAB + FILTER_ENTRY_SIZE * 1;
        q->filter[1].table_pos = DATA_FILTER_TAB + FILTER_ENTRY_SIZE * 2;
        q->echo.end_pos = DELAY_BASE_OFFSET + 6;
        q->next_state = STATE_REFRESH1;
    } else {
        q->wet[0].delay = 1; q->dry[0].delay = 0; q->wet[1].delay = 0; q->dry[1].delay = 0;
        q->filter[0].table_pos = 0xf73; q->filter[1].table_pos = 0xfa4;
        q->alt_filter[0].table_pos = 0xf73; q->alt_filter[1].table_pos = 0xfa4;
        q->echo.end_pos = DELAY_BASE_OFFSET2 + 6;
        q->next_state = STATE_REFRESH2;
    }
    for (int ch = 0; ch < 2; ch++) { q->wet[ch].volume = 0x3fff; q->dry[ch].volume = 0x3fff; }
    q->delay_update = 1;
    q->ready_flag = 0;
    q->state_counter = 1;
}

static void state_refresh_filter_1(cps1_qsound *q)
{
    for (int ch = 0; ch < 2; ch++) {
        q->filter[ch].delay_pos = 0;
        q->filter[ch].tap_count = 95;
        for (int i = 0; i < 95; i++) q->filter[ch].taps[i] = (int16_t)dsp(q, (unsigned)(q->filter[ch].table_pos + i));
    }
    q->state = q->next_state = STATE_NORMAL1;
}

static void state_refresh_filter_2(cps1_qsound *q)
{
    for (int ch = 0; ch < 2; ch++) {
        q->filter[ch].delay_pos = 0;
        q->filter[ch].tap_count = 45;
        for (int i = 0; i < 45; i++) q->filter[ch].taps[i] = (int16_t)dsp(q, (unsigned)(q->filter[ch].table_pos + i));
        q->alt_filter[ch].delay_pos = 0;
        q->alt_filter[ch].tap_count = 44;
        for (int i = 0; i < 44; i++) q->alt_filter[ch].taps[i] = (int16_t)dsp(q, (unsigned)(q->alt_filter[ch].table_pos + i));
    }
    q->state = q->next_state = STATE_NORMAL2;
}

static void state_normal_update(cps1_qsound *q)
{
    q->ready_flag = 0x80;
    q->echo.length = (int16_t)clamp((int16_t)(q->echo.end_pos - (q->state == STATE_NORMAL2 ? DELAY_BASE_OFFSET2 : DELAY_BASE_OFFSET)), 0, 1024);
    int32_t echo_input = 0;
    for (int i = 0; i < 16; i++) q->voice_output[i] = voice_update(q, &q->voice[i], &echo_input);
    const int adpcm_voice = q->state_counter % 3;
    q->voice_output[16 + adpcm_voice] = adpcm_update(q, &q->adpcm[adpcm_voice], q->voice_output[16 + adpcm_voice], q->state_counter / 3);
    const int16_t echo_output = echo_apply(&q->echo, echo_input);
    for (int ch = 0; ch < 2; ch++) {
        /* the echo comes out on the unfiltered part of the left channel and the filtered part of the right one */
        int32_t wet = ch == 1 ? shl(echo_output, 14) : 0;
        int32_t dry = ch == 0 ? shl(echo_output, 14) : 0;
        for (int i = 0; i < 19; i++) {
            const uint16_t pan = (uint16_t)(q->voice_pan[i] + ch * PAN_TABLE_CH_OFFSET);
            dry = (int32_t)((uint32_t)dry - (uint32_t)(q->voice_output[i] * (int16_t)dsp(q, (uint16_t)(pan + PAN_TABLE_DRY))));
            wet = (int32_t)((uint32_t)wet - (uint32_t)(q->voice_output[i] * (int16_t)dsp(q, (uint16_t)(pan + PAN_TABLE_WET))));
        }
        dry = shl(clamp(dry, -0x1fffffff, 0x1fffffff), 2);
        wet = shl(clamp(wet, -0x1fffffff, 0x1fffffff), 2);
        wet = fir_apply(&q->filter[ch], (int16_t)(wet >> 16));
        if (q->state == STATE_NORMAL2) dry = fir_apply(&q->alt_filter[ch], (int16_t)(dry >> 16));
        int32_t output = delay_apply(&q->wet[ch], wet) + delay_apply(&q->dry[ch], dry);
        output = (output + 0x2000) & ~0x3fff;
        q->out[ch] = (int16_t)clamp(output >> 14, -0x7fff, 0x7fff);
        if (q->delay_update) { delay_update(&q->wet[ch]); delay_update(&q->dry[ch]); }
    }
    q->delay_update = 0;
    /* after 6 samples the next state runs */
    if (++q->state_counter > 5) { q->state_counter = 0; q->state = q->next_state; }
}

void cps1_qsound_sample(cps1_qsound *q, int16_t out[2])
{
    switch (q->state) {
    case STATE_REFRESH1: state_refresh_filter_1(q); break;
    case STATE_REFRESH2: state_refresh_filter_2(q); break;
    case STATE_NORMAL1: case STATE_NORMAL2: state_normal_update(q); break;
    default: state_init(q); break;               /* the boot state and both init states */
    }
    out[0] = q->out[0];
    out[1] = q->out[1];
}

/* The registers the Z80 writes through the data latch (MAME's register map). */
static void write_register(cps1_qsound *q, uint8_t address, uint16_t data)
{
#define SET(field) do { memcpy(&(field), &data, sizeof(uint16_t)); } while (0)
    q->ready_flag = 0;
    if (address < 0x80) {
        cps1_qs_voice *v = &q->voice[address >> 3];
        switch (address & 7) {
        case 0: SET(q->voice[((address >> 3) + 1) % 16].bank); break;     /* the bank applies to the next voice */
        case 1: SET(v->addr); break;
        case 2: SET(v->rate); break;
        case 3: SET(v->phase); break;
        case 4: SET(v->loop_len); break;
        case 5: SET(v->end_addr); break;
        case 6: SET(v->volume); break;
        }
    } else if (address < 0x90) SET(q->voice_pan[address - 0x80]);
    else if (address < 0x93) SET(q->voice_pan[16 + address - 0x90]);
    else if (address == 0x93) SET(q->echo.feedback);
    else if (address >= 0xba && address < 0xca) SET(q->voice[address - 0xba].echo);
    else if (address >= 0xca && address < 0xd6) {
        cps1_qs_adpcm *a = &q->adpcm[(address - 0xca) >> 2];
        switch ((address - 0xca) & 3) {
        case 0: SET(a->start_addr); break;
        case 1: SET(a->end_addr); break;
        case 2: SET(a->bank); break;
        case 3: SET(a->volume); break;
        }
    } else if (address >= 0xd6 && address < 0xd9) SET(q->adpcm[address - 0xd6].flag);
    else if (address == 0xd9) SET(q->echo.end_pos);
    else if (address == 0xda || address == 0xdc) SET(q->filter[(address - 0xda) >> 1].table_pos);
    else if (address == 0xdb || address == 0xdd) SET(q->alt_filter[(address - 0xdb) >> 1].table_pos);
    else if (address == 0xde || address == 0xe0) SET(q->wet[(address - 0xde) >> 1].delay);
    else if (address == 0xdf || address == 0xe1) SET(q->dry[(address - 0xdf) >> 1].delay);
    else if (address == 0xe2) SET(q->delay_update);
    else if (address == 0xe3) SET(q->next_state);
    else if (address == 0xe4 || address == 0xe6) SET(q->wet[(address - 0xe4) >> 1].volume);
    else if (address == 0xe5 || address == 0xe7) SET(q->dry[(address - 0xe5) >> 1].volume);
#undef SET
}

void cps1_qsound_write(cps1_qsound *q, unsigned offset, uint8_t data)
{
    switch (offset) {
    case 0: q->data_latch = (uint16_t)((q->data_latch & 0x00ff) | (data << 8)); break;
    case 1: q->data_latch = (uint16_t)((q->data_latch & 0xff00) | data); break;
    case 2: write_register(q, data, q->data_latch); break;
    default: break;
    }
}

uint8_t cps1_qsound_ready(const cps1_qsound *q) { return (uint8_t)q->ready_flag; }

void cps1_qsound_init(cps1_qsound *q, const uint8_t *dsp_rom, const uint8_t *samples, size_t sample_bytes)
{
    memset(q, 0, sizeof *q);
    for (unsigned n = 0; n < 0x1000; n++) q->dsp_rom[n] = (uint16_t)(dsp_rom[2 * n] | dsp_rom[2 * n + 1] << 8);
    q->samples = samples;
    q->sample_bytes = samples ? sample_bytes : 0;
    size_t mask = q->sample_bytes ? q->sample_bytes - 1 : 0;      /* the smallest power of two minus one that covers the last byte */
    for (unsigned shift = 1; shift < 32; shift <<= 1) mask |= mask >> shift;
    q->sample_mask = mask;
    cps1_qsound_reset(q);
}

void cps1_qsound_reset(cps1_qsound *q)
{
    q->ready_flag = 0;
    q->out[0] = q->out[1] = 0;
    q->state = STATE_BOOT;
    q->state_counter = 0;
}

/* ------------------------------------------------------------------ quick state */

typedef struct { uint8_t *out; const uint8_t *in; size_t at; int bad; } stream;
static void w16(stream *s, uint16_t v) { if (s->out) { s->out[s->at] = (uint8_t)v; s->out[s->at + 1] = (uint8_t)(v >> 8); } s->at += 2; }
static void w32(stream *s, uint32_t v) { w16(s, (uint16_t)v); w16(s, (uint16_t)(v >> 16)); }
static uint16_t r16(stream *s) { const uint16_t v = (uint16_t)(s->in[s->at] | s->in[s->at + 1] << 8); s->at += 2; return v; }
static uint32_t r32(stream *s) { const uint32_t low = r16(s); return low | (uint32_t)r16(s) << 16; }

/* One walk over every field, reading (in set), writing (out set) or only counting (neither); the order is the format. */
static void walk(cps1_qsound *q, stream *s)
{
#define U16(field) do { if (s->in) (field) = r16(s); else w16(s, (uint16_t)(field)); } while (0)
#define I32(field) do { if (s->in) (field) = (int32_t)r32(s); else w32(s, (uint32_t)(field)); } while (0)
    U16(q->data_latch); U16(q->out[0]); U16(q->out[1]);
    for (int i = 0; i < 16; i++) {
        U16(q->voice[i].bank); U16(q->voice[i].addr); U16(q->voice[i].phase); U16(q->voice[i].rate);
        U16(q->voice[i].loop_len); U16(q->voice[i].end_addr); U16(q->voice[i].volume); U16(q->voice[i].echo);
    }
    for (int i = 0; i < 3; i++) {
        U16(q->adpcm[i].start_addr); U16(q->adpcm[i].end_addr); U16(q->adpcm[i].bank); U16(q->adpcm[i].volume);
        U16(q->adpcm[i].flag); U16(q->adpcm[i].cur_vol); U16(q->adpcm[i].step_size); U16(q->adpcm[i].cur_addr);
    }
    for (int i = 0; i < 19; i++) { U16(q->voice_pan[i]); U16(q->voice_output[i]); }
    U16(q->echo.end_pos); U16(q->echo.feedback); U16(q->echo.length); U16(q->echo.last_sample); U16(q->echo.delay_pos);
    for (int i = 0; i < 1024; i++) U16(q->echo.delay_line[i]);
    cps1_qs_fir *fir[4] = {&q->filter[0], &q->filter[1], &q->alt_filter[0], &q->alt_filter[1]};
    for (int f = 0; f < 4; f++) {
        I32(fir[f]->tap_count); I32(fir[f]->delay_pos); U16(fir[f]->table_pos);
        for (int i = 0; i < 95; i++) { U16(fir[f]->taps[i]); U16(fir[f]->delay_line[i]); }
    }
    cps1_qs_delay *delay[4] = {&q->wet[0], &q->wet[1], &q->dry[0], &q->dry[1]};
    for (int d = 0; d < 4; d++) {
        U16(delay[d]->delay); U16(delay[d]->volume); U16(delay[d]->write_pos); U16(delay[d]->read_pos);
        for (int i = 0; i < 51; i++) U16(delay[d]->delay_line[i]);
    }
    U16(q->state); U16(q->next_state); U16(q->delay_update); I32(q->state_counter); I32(q->ready_flag);
#undef U16
#undef I32
}

size_t cps1_qsound_state_bytes(void)
{
    cps1_qsound probe;
    memset(&probe, 0, sizeof probe);
    stream s = {NULL, NULL, 0, 0};
    walk(&probe, &s);
    return s.at;
}

size_t cps1_qsound_state_put(const cps1_qsound *q, uint8_t *out)
{
    stream s = {out, NULL, 0, 0};
    walk((cps1_qsound *)q, &s);
    return s.at;
}

/* A state is read into a copy first; every index the model uses to address its own arrays must be in range. */
int cps1_qsound_state_get(cps1_qsound *q, const uint8_t *in)
{
    cps1_qsound next = *q;
    stream s = {NULL, in, 0, 0};
    walk(&next, &s);
    cps1_qs_fir *fir[4] = {&next.filter[0], &next.filter[1], &next.alt_filter[0], &next.alt_filter[1]};
    for (int f = 0; f < 4; f++)
        if (fir[f]->tap_count < 0 || fir[f]->tap_count > 95 || fir[f]->delay_pos < 0 || fir[f]->delay_pos > 95) return 0;
    cps1_qs_delay *delay[4] = {&next.wet[0], &next.wet[1], &next.dry[0], &next.dry[1]};
    for (int d = 0; d < 4; d++)
        if (delay[d]->write_pos < 0 || delay[d]->write_pos >= 51 || delay[d]->read_pos < 0 || delay[d]->read_pos >= 51) return 0;
    if (next.echo.delay_pos < 0 || next.echo.delay_pos >= 1024 || next.echo.length < 0 || next.echo.length > 1024) return 0;
    if (next.state_counter < 0 || next.state_counter > 5 || (next.ready_flag != 0 && next.ready_flag != 0x80)) return 0;
    *q = next;
    return 1;
}
