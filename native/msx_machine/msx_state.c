/* The MSX machine's part of a quick state (MIT, Retro-Recomp): items 3 to 9 of the stage 8 design, as fixed-width
 * little-endian fields through state_io.h. No pointer, no host address and no C layout is ever written; what is derived
 * (the region table, the SCC list) is rebuilt by msx_refresh_layout after an apply.
 *
 * Order: machine registers and timing, the 16 slot devices, RAM (64 KB on an MSX1 or the mapper's segments on an MSX2),
 * the TMS9918A, the V9938 and its command engine (MSX2), the RTC (when present), the PSG synth.
 *
 * Fields that describe the configuration (expanded, key_layout, lines_per_frame, video, has_rtc, each device's kind,
 * mapper and size, the mapper's segment count) are written but never applied: a state of another configuration is
 * refused. A state is decoded twice, as state_io.h asks: msx_machine_state_check on a scratch copy first (the live
 * machine, its RAM and its V9938 are never touched), then msx_machine_state in RR_STATE_APPLY mode. Not saved: keys,
 * joystick (host input), the hooks and the counters of unmapped reads and dropped writes, `dropped` of the synth. */
#include "msx_machine.h"
#include "state_io.h"

#include <string.h>

void msx_rebuild_layout(MsxMachine *m);   /* msx_machine.c: rebuild_regions plus the scc[] list of msx_set_device */

#define FULL(width) ((width) == 8 ? UINT64_MAX : ((1ull << (8 * (width))) - 1))
/* An unsigned field of `width` bytes whose value must not exceed `maximum`. */
#define W(lvalue, width, maximum) ((lvalue) = rr_state_word(io, (uint64_t)(lvalue), (width), (maximum)))
#define B(lvalue) W(lvalue, 1, 0xFF)

static int64_t signed_word(RetroStateIO *io, int64_t value, unsigned width)
{
    uint64_t mask = FULL(width);
    uint64_t r = rr_state_word(io, (uint64_t)value & mask, width, mask);
    if (width < 8 && ((r >> (8 * width - 1)) & 1))
        r |= ~mask;
    return (int64_t)r;
}
#define S(lvalue, width) ((lvalue) = (int64_t)signed_word(io, (int64_t)(lvalue), (width)))

/* A field of the configuration: written from the live machine, never applied, refused when it differs. */
static void same(RetroStateIO *io, uint64_t live, unsigned width)
{
    uint64_t v = rr_state_word(io, live, width, FULL(width));
    if (io->mode != RR_STATE_WRITE && v != live)
        io->ok = false;
}

static void words16(RetroStateIO *io, uint16_t *p, size_t n, uint64_t maximum)
{
    for (size_t i = 0; i < n; ++i)
        p[i] = (uint16_t)rr_state_word(io, p[i], 2, maximum);
}

static void signed16(RetroStateIO *io, int16_t *p, size_t n)
{
    for (size_t i = 0; i < n; ++i)
        p[i] = (int16_t)signed_word(io, p[i], 2);
}

static void scc_state(RetroStateIO *io, MsxScc *s)
{
    rr_state_bytes(io, s->wave, sizeof s->wave);
    words16(io, s->period, 5, 0xFFFF);
    rr_state_bytes(io, s->volume, sizeof s->volume);
    rr_state_bytes(io, s->volume_now, sizeof s->volume_now);
    B(s->enable);
    words16(io, s->count, 5, 0xFFFF);
    for (int c = 0; c < 5; ++c)
        W(s->pos[c], 1, 31);
    signed16(io, s->out, 5);
}

static void slots_state(MsxMachine *m, RetroStateIO *io)
{
    for (int p = 0; p < 4; ++p)
        for (int s = 0; s < 4; ++s) {
            MsxDevice *d = &m->slot[p][s];
            same(io, (uint64_t)d->kind, 1);
            same(io, (uint64_t)d->mapper, 1);
            same(io, d->size, 4);
            for (int i = 0; i < 8; ++i)
                S(d->block[i], 2);
            W(d->scc_on, 1, 1);
            scc_state(io, &d->scc);
        }
}

static void v9938_state(MsxMachine *m, RetroStateIO *io)
{
    MsxV9938 *v = m->v9938;
    if (!v) { io->ok = false; return; }
    rr_state_bytes(io, v->vram, sizeof v->vram);
    rr_state_bytes(io, v->reg, sizeof v->reg);
    B(v->status0); B(v->status1); B(v->status2);
    W(v->pointer, 2, 0x3FFF);
    B(v->latch); B(v->first); B(v->readahead);
    B(v->pal_latch); B(v->pal_first);
    words16(io, v->palette, 16, 0x777);
    W(v->collision_x, 2, 0xFFFF); W(v->collision_y, 2, 0xFFFF);
    B(v->blink_on); B(v->blink_count);
    B(v->lines_latched);
    S(v->adjust_h, 1); S(v->adjust_v, 1);
    words16(io, &v->frame[0][0], (size_t)MSX2_LINES * MSX2_WIDTH, 0xFFFF);
    words16(io, &v->border[0][0], (size_t)MSX2_LINES * 2, 0xFFFF);
    rr_state_bytes(io, v->line_mode, sizeof v->line_mode);
    MsxV9938Cmd *c = &v->cmd;
    W(c->sx, 2, 0x3FF); W(c->sy, 2, 0x3FF); W(c->dx, 2, 0x3FF);
    W(c->dy, 2, 0x3FF); W(c->nx, 2, 0x3FF); W(c->ny, 2, 0x3FF);
    B(c->col); B(c->arg); B(c->cmd); B(c->status); B(c->transfer);
    W(c->mode, 1, 0xFF);
    W(c->asx, 2, 0xFFFF); W(c->adx, 2, 0xFFFF); W(c->anx, 2, 0xFFFF);
    W(c->next, 8, UINT64_MAX); W(c->writes, 8, UINT64_MAX);
    for (int i = 0; i < 16; ++i)
        W(c->started[i], 8, UINT64_MAX);
}

static void rtc_state(MsxMachine *m, RetroStateIO *io)
{
    MsxRtc *r = &m->rtc;
    W(r->latch, 1, 15); W(r->mode, 1, 15); W(r->test, 1, 15);
    for (int b = 0; b < 4; ++b)
        for (int i = 0; i < 13; ++i)
            W(r->nibble[b][i], 1, 15);
    W(r->counted, 8, UINT64_MAX);
}

static void synth_state(MsxMachine *m, RetroStateIO *io)
{
    MsxPsgSynth *s = &m->synth;
    W(s->time, 8, UINT64_MAX);
    W(s->tick_rest, 4, 0xFFFFFFFFu);
    W(s->ticks, 4, 0xFFFFFFFFu);
    words16(io, s->tone_count, 3, 0xFFFF);
    for (int c = 0; c < 3; ++c)
        W(s->tone_out[c], 1, 1);
    W(s->noise_count, 2, 0xFFFF);
    W(s->lfsr, 4, 0xFFFFFFFFu);
    W(s->env_count, 2, 0xFFFF);
    W(s->env_step, 1, 15); W(s->env_up, 1, 1); W(s->env_holding, 1, 1);
    W(s->next_sample, 8, UINT64_MAX);
    S(s->acc, 4);
    W(s->acc_ticks, 4, 0xFFFFFFFFu);
    W(s->out_count, 4, MSX_AUDIO_BUFFER);
    if (io->ok)
        signed16(io, s->out, s->out_count);
}

static uint64_t abs_diff(uint64_t a, uint64_t b) { return a > b ? a - b : b - a; }

/* What a decoded state must satisfy before it is applied. */
static int consistent(const MsxMachine *m, const uint8_t *ram64)
{
    (void)ram64;
    if (m->line >= m->lines_per_frame || m->vblank_line > m->lines_per_frame)
        return 0;
    if (abs_diff(m->next_line, m->cycles) > MSX_CYCLES_PER_LINE)
        return 0;
    if (m->video == MSX_VIDEO_V9938 && abs_diff(m->next_draw, m->next_line) > MSX_CYCLES_PER_LINE)
        return 0;
    for (int p = 0; p < 4; ++p)
        for (int s = 0; s < 4; ++s) {
            const MsxDevice *d = &m->slot[p][s];
            if (d->kind != MSX_DEV_ROM)
                continue;
            for (int i = 0; i < 8; ++i)
                if (d->block[i] < -1 || d->block[i] >= (int)(d->size / 0x2000u))
                    return 0;
        }
    for (int i = 0; i < 4; ++i)
        if (m->mapper.segments && m->mapper.reg[i] >= m->mapper.segments)
            return 0;
    for (int y = 0; y < MSX_HEIGHT; ++y) {
        if (m->vdp.border[y] > 15)
            return 0;
        for (int x = 0; x < MSX_WIDTH; ++x)
            if (m->vdp.frame[y][x] > 15)
                return 0;
    }
    if (m->video == MSX_VIDEO_V9938) {
        const MsxV9938Cmd *c = &m->v9938->cmd;
        if (c->mode > 3 && c->mode != 0xFF)
            return 0;
        for (int i = 0; i < 16; ++i)
            if (m->v9938->palette[i] > 0x777)
                return 0;
    }
    return m->synth.out_count <= MSX_AUDIO_BUFFER;
}

int msx_machine_state(MsxMachine *m, uint8_t *ram64, RetroStateIO *io)
{
    /* 3. Machine */
    B(m->primary);
    rr_state_bytes(io, m->secondary, sizeof m->secondary);
    B(m->port_c);
    B(m->psg_latch);
    rr_state_bytes(io, m->psg, sizeof m->psg);
    W(m->line, 4, 0xFFFFFFFFu);
    W(m->cycles, 8, UINT64_MAX);
    W(m->next_line, 8, UINT64_MAX);
    W(m->next_draw, 8, UINT64_MAX);
    W(m->frames, 8, UINT64_MAX);
    W(m->vblank_line, 4, 0xFFFFFFFFu);
    W(m->frame_trace, 4, 0xFFFFFFFFu);
    for (int i = 0; i < 4; ++i)
        same(io, m->expanded[i], 1);
    same(io, m->key_layout, 1);
    same(io, m->lines_per_frame, 4);
    same(io, m->video, 1);
    same(io, m->has_rtc, 1);
    /* 4. Slots */
    slots_state(m, io);
    /* 5. RAM */
    same(io, m->mapper.segments, 4);
    if (m->mapper.segments) {
        if (!m->mapper.ram) { io->ok = false; return 0; }
        rr_state_bytes(io, m->mapper.ram, (size_t)m->mapper.segments * 0x4000u);
        for (int i = 0; i < 4; ++i)
            W(m->mapper.reg[i], 1, m->mapper.segments - 1);
    } else {
        if (!ram64) { io->ok = false; return 0; }
        rr_state_bytes(io, ram64, 65536);
    }
    /* 6. TMS9918A */
    MsxVdp *t = &m->vdp;
    rr_state_bytes(io, t->vram, sizeof t->vram);
    rr_state_bytes(io, t->reg, sizeof t->reg);
    B(t->status);
    W(t->address, 2, 0x3FFF);
    B(t->latch); B(t->first); B(t->readahead);
    /* The picture and the borders are colour indexes: read byte by byte, so the check sees the decoded values. */
    for (int y = 0; y < MSX_HEIGHT; ++y)
        for (int x = 0; x < MSX_WIDTH; ++x)
            W(t->frame[y][x], 1, 15);
    for (int y = 0; y < MSX_HEIGHT; ++y)
        W(t->border[y], 1, 15);
    /* 7. V9938 */
    if (m->video == MSX_VIDEO_V9938)
        v9938_state(m, io);
    /* 8. RTC */
    if (m->has_rtc)
        rtc_state(m, io);
    /* 9. PSG synth */
    synth_state(m, io);
    if (io->ok && io->mode != RR_STATE_WRITE && !consistent(m, ram64))
        io->ok = false;
    return io->ok;
}

/* The check on a scratch copy, from the reader's position; `cycles` (if given) receives the decoded machine cycle. */
int msx_machine_state_check_io(const MsxMachine *m, const uint8_t *ram64, RetroStateIO *io, uint64_t *cycles)
{
    static MsxMachine scratch;
    static MsxV9938 scratch_v;
    scratch = *m;
    if (m->video == MSX_VIDEO_V9938) {
        if (!m->v9938)
            return 0;
        scratch_v = *m->v9938;
        scratch.v9938 = &scratch_v;
    } else {
        scratch.v9938 = NULL;
    }
    /* CHECK never writes through RAM pointers or the state's bytes: only the scratch copy takes the decoded values. */
    io->mode = RR_STATE_CHECK;
    int ok = msx_machine_state(&scratch, (uint8_t *)ram64, io);
    if (cycles)
        *cycles = scratch.cycles;
    return ok;
}

int msx_machine_state_check(const MsxMachine *m, const uint8_t *ram64, const uint8_t *data, size_t size)
{
    RetroStateIO io = { (uint8_t *)data, size, 0, RR_STATE_CHECK, true };
    return msx_machine_state_check_io(m, ram64, &io, NULL) && io.pos == size;
}

void msx_refresh_layout(MsxMachine *m)
{
    msx_rebuild_layout(m);
}
