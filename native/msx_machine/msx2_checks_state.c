/* Quick-state fixtures for the MSX machine (msx_state.c): an MSX1 and an MSX2 machine written and applied to a fresh one,
 * a third save equal byte for byte to the first, damaged payloads refused without touching the live machine, and a
 * state of one machine refused by the other. MIT, Retro-Recomp. A development check, never built into a game.
 * Prints one line per check and exits 1 if any fails. */
#include "msx_machine.h"
#include "state_io.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int msx_machine_state(MsxMachine *m, uint8_t *ram64, RetroStateIO *io);
int msx_machine_state_check(const MsxMachine *m, const uint8_t *ram64, const uint8_t *data, size_t size);
void msx_refresh_layout(MsxMachine *m);


enum { LINE = MSX_CYCLES_PER_LINE, CAP = 2 << 20, SEGMENTS = 16 };

static int failures;

static void check(const char *name, long got, long want)
{
    printf("%s %s: %ld (expected %ld)\n", got == want ? "ok  " : "FAIL", name, got, want);
    failures += got != want;
}

static MsxMachine ma, mb, snap;
static MsxV9938 va, vb, vsnap;
static uint8_t ram_a[65536], ram_b[65536], ram_snap[65536];
static uint8_t map_a[SEGMENTS * 0x4000], map_b[SEGMENTS * 0x4000], map_snap[SEGMENTS * 0x4000];
static uint8_t rom_plain[0x4000], rom_scc[0x8000], bios[0x10000];
static uint8_t buf1[CAP], buf2[CAP], buf3[CAP];

static size_t save(MsxMachine *m, uint8_t *ram64, uint8_t *buf)
{
    RetroStateIO io = { buf, CAP, 0, RR_STATE_WRITE, true };
    return msx_machine_state(m, ram64, &io) ? io.pos : 0;
}

static int apply(MsxMachine *m, uint8_t *ram64, const uint8_t *buf, size_t size)
{
    RetroStateIO io = { (uint8_t *)buf, size, 0, RR_STATE_APPLY, true };
    int ok = msx_machine_state(m, ram64, &io) && io.pos == size;
    msx_refresh_layout(m);
    return ok;
}

/* ---- machines ---- */
static void msx1_setup(MsxMachine *m, uint8_t *ram)
{
    memset(rom_plain, 0xFF, sizeof rom_plain);
    memset(rom_scc, 0xFF, sizeof rom_scc);
    memset(ram, 0, 65536);
    msx_init(m, MSX_LINES_NTSC);
    m->trace_frames = 1;
    MsxDevice d;
    memset(&d, 0, sizeof d);
    d.kind = MSX_DEV_ROM; d.rom = rom_plain; d.size = sizeof rom_plain; d.base = 0x4000; d.source = MSX_SOURCE_NONE;
    msx_set_device(m, 1, 0, d);
    MsxDevice s;
    memset(&s, 0, sizeof s);
    s.kind = MSX_DEV_ROM; s.rom = rom_scc; s.size = sizeof rom_scc; s.mapper = MSX_MAPPER_KONAMI_SCC; s.source = MSX_SOURCE_NONE;
    msx_set_device(m, 2, 0, s);
    MsxDevice r;
    memset(&r, 0, sizeof r);
    r.kind = MSX_DEV_RAM; r.ram = ram; r.size = 65536; r.source = MSX_SOURCE_NONE;
    msx_set_device(m, 3, 0, r);
}

static void vdp_reg(MsxMachine *m, int r, uint8_t v) { msx_out(m, 0x99, v); msx_out(m, 0x99, (uint8_t)(0x80 | r)); }
static void psg_reg(MsxMachine *m, int r, uint8_t v) { msx_out(m, 0xA0, (uint8_t)r); msx_out(m, 0xA1, v); }

static void msx1_drive(MsxMachine *m)
{
    msx_out(m, 0xA8, 0xEF);                       /* page 2: slot 2 (SCC cartridge), the rest slot 3 RAM */
    for (int i = 0; i < 64; ++i) msx_write(m, (uint16_t)(0xC000 + i), (uint8_t)(i * 3 + 1));
    msx_write(m, 0x9000, 0x3F);                   /* SCC on */
    msx_write(m, 0x7000, 0x02);                   /* a bank */
    for (int i = 0; i < 32; ++i) msx_write(m, (uint16_t)(0x9800 + i), (uint8_t)(i * 7));
    msx_write(m, 0x9880, 0x40); msx_write(m, 0x9881, 0x01); msx_write(m, 0x988A, 0x0C); msx_write(m, 0x988F, 0x1F);
    psg_reg(m, 0, 0x55); psg_reg(m, 1, 0x02); psg_reg(m, 7, 0x38); psg_reg(m, 8, 0x0A); psg_reg(m, 13, 0x0E);
    vdp_reg(m, 0, 0x00); vdp_reg(m, 1, 0xE0); vdp_reg(m, 7, 0x1D);
    msx_out(m, 0x99, 0x00); msx_out(m, 0x99, 0x40);
    for (int i = 0; i < 300; ++i) msx_out(m, 0x98, (uint8_t)(i * 5));
    msx_out(m, 0xAA, 0x55);
    msx_advance(m, 300 * LINE + 77);              /* more than a frame: lines drawn, frame trace folded, audio queued */
}

static void msx2_setup(MsxMachine *m, MsxV9938 *v, uint8_t *map)
{
    memset(bios, 0xFF, sizeof bios);
    memset(map, 0, SEGMENTS * 0x4000);
    msx_init(m, MSX_LINES_NTSC);
    msx_setup_msx2(m, bios, map, SEGMENTS, v);
    memset(rom_plain, 0xFF, sizeof rom_plain);
    MsxDevice d;
    memset(&d, 0, sizeof d);
    d.kind = MSX_DEV_ROM; d.rom = rom_plain; d.size = sizeof rom_plain; d.base = 0x4000; d.source = MSX_SOURCE_NONE;
    msx_set_device(m, 1, 0, d);
}

static void rtc_w(MsxMachine *m, int reg, int value) { msx_out(m, 0xB4, (uint8_t)reg); msx_out(m, 0xB5, (uint8_t)value); }

static void msx2_drive(MsxMachine *m)
{
    msx_out(m, 0xFC, 5); msx_out(m, 0xFD, 9); msx_out(m, 0xFE, 12); msx_out(m, 0xFF, 15);
    msx_out(m, 0xA8, 0xFF);                       /* every page in slot 3 (mapper RAM through 3-2 once expanded) */
    msx_write(m, 0xFFFF, 0xAA);                   /* secondary slots of slot 3: 3-2 on every page */
    for (int i = 0; i < 100; ++i) msx_write(m, (uint16_t)(0x8000 + i), (uint8_t)(i + 9));
    rtc_w(m, 13, 8); rtc_w(m, 0, 7);
    psg_reg(m, 0, 0x33); psg_reg(m, 7, 0x3E); psg_reg(m, 8, 0x0C);
    vdp_reg(m, 0, 0x06); vdp_reg(m, 1, 0x00);     /* Graphic 4, display off */
    msx_advance(m, LINE);
    vdp_reg(m, 16, 3); msx_out(m, 0x9A, 0x73); msx_out(m, 0x9A, 0x04);
    vdp_reg(m, 16, 9); msx_out(m, 0x9A, 0x25); msx_out(m, 0x9A, 0x06);
    vdp_reg(m, 14, 0); msx_out(m, 0x99, 0x00); msx_out(m, 0x99, 0x40);
    for (int i = 0; i < 400; ++i) msx_out(m, 0x98, (uint8_t)(i ^ 0x5A));
    vdp_reg(m, 1, 0x40);                          /* display on */
    /* HMMV 200 x 100 of 0xAA at (3, 4): the engine is left running */
    vdp_reg(m, 36, 3); vdp_reg(m, 37, 0); vdp_reg(m, 38, 4); vdp_reg(m, 39, 0);
    vdp_reg(m, 40, 200); vdp_reg(m, 41, 0); vdp_reg(m, 42, 100); vdp_reg(m, 43, 0);
    vdp_reg(m, 44, 0xAA); vdp_reg(m, 45, 0); vdp_reg(m, 46, 0xC0);
    msx_advance(m, 3 * LINE + 50);
}

/* ---- comparison, field by field (pointers and derived data are compared through what they show) ---- */
static int bad, quiet;
#define EQ(name, a, b) do { if ((a) != (b)) { if (!quiet) printf("  differs: %s\n", name); ++bad; } } while (0)
#define EQM(name, a, b) do { if (memcmp(&(a), &(b), sizeof(a))) { if (!quiet) printf("  differs: %s\n", name); ++bad; } } while (0)

static void eq_scc(const MsxScc *x, const MsxScc *y)
{
    EQM("scc.wave", x->wave, y->wave); EQM("scc.period", x->period, y->period); EQM("scc.volume", x->volume, y->volume);
    EQM("scc.volume_now", x->volume_now, y->volume_now); EQ("scc.enable", x->enable, y->enable);
    EQM("scc.count", x->count, y->count); EQM("scc.pos", x->pos, y->pos); EQM("scc.out", x->out, y->out);
}

static int eq_machine(const MsxMachine *x, const MsxMachine *y, const uint8_t *rx, const uint8_t *ry)
{
    bad = 0;
    EQ("primary", x->primary, y->primary); EQM("secondary", x->secondary, y->secondary);
    EQ("port_c", x->port_c, y->port_c); EQ("psg_latch", x->psg_latch, y->psg_latch); EQM("psg", x->psg, y->psg);
    EQ("line", x->line, y->line); EQ("cycles", x->cycles, y->cycles); EQ("next_line", x->next_line, y->next_line);
    EQ("next_draw", x->next_draw, y->next_draw); EQ("frames", x->frames, y->frames);
    EQ("vblank_line", x->vblank_line, y->vblank_line); EQ("frame_trace", x->frame_trace, y->frame_trace);
    for (int p = 0; p < 4; ++p)
        for (int s = 0; s < 4; ++s) {
            const MsxDevice *a = &x->slot[p][s], *b = &y->slot[p][s];
            EQ("dev.kind", a->kind, b->kind); EQ("dev.mapper", a->mapper, b->mapper); EQ("dev.size", a->size, b->size);
            EQM("dev.block", a->block, b->block); EQ("dev.scc_on", a->scc_on, b->scc_on);
            eq_scc(&a->scc, &b->scc);
        }
    for (unsigned a = 0; a < 0x10000; ++a)
        if (msx_peek(x, (uint16_t)a) != msx_peek(y, (uint16_t)a)) { if (!quiet) printf("  differs: peek %04X\n", a); ++bad; break; }
    if (x->mapper.segments) {
        EQ("segments", x->mapper.segments, y->mapper.segments); EQM("mapper.reg", x->mapper.reg, y->mapper.reg);
        EQ("mapper ram", memcmp(x->mapper.ram, y->mapper.ram, (size_t)x->mapper.segments * 0x4000), 0);
    } else {
        EQ("ram", memcmp(rx, ry, 65536), 0);
    }
    const MsxVdp *t = &x->vdp, *u = &y->vdp;
    EQM("tms.vram", t->vram, u->vram); EQM("tms.reg", t->reg, u->reg); EQ("tms.status", t->status, u->status);
    EQ("tms.address", t->address, u->address); EQ("tms.latch", t->latch, u->latch); EQ("tms.first", t->first, u->first);
    EQ("tms.readahead", t->readahead, u->readahead); EQM("tms.frame", t->frame, u->frame);
    EQM("tms.border", t->border, u->border);
    if (x->video == MSX_VIDEO_V9938) {
        const MsxV9938 *a = x->v9938, *b = y->v9938;
        EQM("v.vram", a->vram, b->vram); EQM("v.reg", a->reg, b->reg);
        EQ("v.status0", a->status0, b->status0); EQ("v.status1", a->status1, b->status1); EQ("v.status2", a->status2, b->status2);
        EQ("v.pointer", a->pointer, b->pointer); EQ("v.latch", a->latch, b->latch); EQ("v.first", a->first, b->first);
        EQ("v.readahead", a->readahead, b->readahead); EQ("v.pal_latch", a->pal_latch, b->pal_latch);
        EQ("v.pal_first", a->pal_first, b->pal_first); EQM("v.palette", a->palette, b->palette);
        EQ("v.collision_x", a->collision_x, b->collision_x); EQ("v.collision_y", a->collision_y, b->collision_y);
        EQ("v.blink_on", a->blink_on, b->blink_on); EQ("v.blink_count", a->blink_count, b->blink_count);
        EQ("v.lines_latched", a->lines_latched, b->lines_latched);
        EQ("v.adjust_h", a->adjust_h, b->adjust_h); EQ("v.adjust_v", a->adjust_v, b->adjust_v);
        EQM("v.frame", a->frame, b->frame); EQM("v.border", a->border, b->border); EQM("v.line_mode", a->line_mode, b->line_mode);
        const MsxV9938Cmd *c = &a->cmd, *d = &b->cmd;
        EQ("cmd.sx", c->sx, d->sx); EQ("cmd.sy", c->sy, d->sy); EQ("cmd.dx", c->dx, d->dx); EQ("cmd.dy", c->dy, d->dy);
        EQ("cmd.nx", c->nx, d->nx); EQ("cmd.ny", c->ny, d->ny); EQ("cmd.col", c->col, d->col); EQ("cmd.arg", c->arg, d->arg);
        EQ("cmd.cmd", c->cmd, d->cmd); EQ("cmd.status", c->status, d->status); EQ("cmd.transfer", c->transfer, d->transfer);
        EQ("cmd.mode", c->mode, d->mode); EQ("cmd.asx", c->asx, d->asx); EQ("cmd.adx", c->adx, d->adx);
        EQ("cmd.anx", c->anx, d->anx); EQ("cmd.next", c->next, d->next); EQ("cmd.writes", c->writes, d->writes);
        EQM("cmd.started", c->started, d->started);
    }
    if (x->has_rtc) {
        EQ("rtc.latch", x->rtc.latch, y->rtc.latch); EQ("rtc.mode", x->rtc.mode, y->rtc.mode);
        EQ("rtc.test", x->rtc.test, y->rtc.test); EQM("rtc.nibble", x->rtc.nibble, y->rtc.nibble);
        EQ("rtc.counted", x->rtc.counted, y->rtc.counted);
    }
    const MsxPsgSynth *s = &x->synth, *r = &y->synth;
    EQ("synth.time", s->time, r->time); EQ("synth.tick_rest", s->tick_rest, r->tick_rest); EQ("synth.ticks", s->ticks, r->ticks);
    EQM("synth.tone_count", s->tone_count, r->tone_count); EQM("synth.tone_out", s->tone_out, r->tone_out);
    EQ("synth.noise_count", s->noise_count, r->noise_count); EQ("synth.lfsr", s->lfsr, r->lfsr);
    EQ("synth.env_count", s->env_count, r->env_count); EQ("synth.env_step", s->env_step, r->env_step);
    EQ("synth.env_up", s->env_up, r->env_up); EQ("synth.env_holding", s->env_holding, r->env_holding);
    EQ("synth.next_sample", s->next_sample, r->next_sample); EQ("synth.acc", s->acc, r->acc);
    EQ("synth.acc_ticks", s->acc_ticks, r->acc_ticks); EQ("synth.out_count", s->out_count, r->out_count);
    EQ("synth.out", memcmp(s->out, r->out, s->out_count * sizeof s->out[0]), 0);
    return bad;
}

/* The first byte at which two saves of a machine with one field changed differ. */
static size_t first_diff(const uint8_t *a, const uint8_t *b, size_t n)
{
    for (size_t i = 0; i < n; ++i) if (a[i] != b[i]) return i;
    return (size_t)-1;
}

/* A snapshot of the live machine, its V9938 and RAM, to prove a refused check left them as they were. */
static void snapshot(const MsxMachine *m, const MsxV9938 *v, const uint8_t *ram, const uint8_t *map)
{
    memcpy(&snap, m, sizeof snap);
    if (v) memcpy(&vsnap, v, sizeof vsnap);
    memcpy(ram_snap, ram, sizeof ram_snap);
    memcpy(map_snap, map, sizeof map_snap);
}

static int untouched(const MsxMachine *m, const MsxV9938 *v, const uint8_t *ram, const uint8_t *map)
{
    return !memcmp(&snap, m, sizeof snap) && (!v || !memcmp(&vsnap, v, sizeof vsnap)) &&
           !memcmp(ram_snap, ram, sizeof ram_snap) && !memcmp(map_snap, map, sizeof map_snap);
}

static void roundtrip(const char *tag, int msx2)
{
    MsxMachine *a = &ma, *b = &mb;
    char name[96];
    if (msx2) {
        msx2_setup(a, &va, map_a); msx2_drive(a);
        msx2_setup(b, &vb, map_b);
    } else {
        msx1_setup(a, ram_a); msx1_drive(a);
        msx1_setup(b, ram_b);
    }
    size_t n1 = save(a, ram_a, buf1);
    snprintf(name, sizeof name, "%s: state written (bytes)", tag);
    check(name, n1 > 0, 1);
    printf("     %s state size: %zu bytes\n", tag, n1);
    if (msx2) {
        check("msx2: the command is still running at the save", va.cmd.cmd, 0xC0);
        check("msx2: the engine has not finished", (va.cmd.status & 1) != 0, 1);
    }
    snprintf(name, sizeof name, "%s: check accepts the written state", tag);
    snapshot(a, msx2 ? &va : NULL, ram_a, map_a);
    check(name, msx_machine_state_check(a, ram_a, buf1, n1), 1);
    snprintf(name, sizeof name, "%s: check leaves the live machine untouched", tag);
    check(name, untouched(a, msx2 ? &va : NULL, ram_a, map_a), 1);
    snprintf(name, sizeof name, "%s: check accepts it on a fresh machine", tag);
    snapshot(b, msx2 ? &vb : NULL, ram_b, map_b);
    check(name, msx_machine_state_check(b, ram_b, buf1, n1), 1);
    snprintf(name, sizeof name, "%s: the fresh machine untouched by the check", tag);
    check(name, untouched(b, msx2 ? &vb : NULL, ram_b, map_b), 1);
    quiet = 1;
    int differs = eq_machine(a, b, ram_a, ram_b);
    quiet = 0;
    snprintf(name, sizeof name, "%s: the fresh machine differs before the apply", tag);
    check(name, differs > 0, 1);
    snprintf(name, sizeof name, "%s: apply", tag);
    check(name, apply(b, ram_b, buf1, n1), 1);
    snprintf(name, sizeof name, "%s: every field equal after the apply", tag);
    check(name, eq_machine(a, b, ram_a, ram_b), 0);
    size_t n3 = save(b, ram_b, buf3);
    snprintf(name, sizeof name, "%s: third save has the same size", tag);
    check(name, (long)n3, (long)n1);
    snprintf(name, sizeof name, "%s: third save is byte-equal", tag);
    check(name, n3 == n1 && !memcmp(buf1, buf3, n1), 1);
    /* the applied machine keeps running like the original */
    msx_advance(a, 5 * LINE + 11);
    msx_advance(b, 5 * LINE + 11);
    snprintf(name, sizeof name, "%s: both machines still equal after running on", tag);
    check(name, eq_machine(a, b, ram_a, ram_b), 0);
}

static void damaged(const char *tag, int msx2)
{
    MsxMachine *a = &ma;
    MsxV9938 *v = msx2 ? &va : NULL;
    uint8_t *map = map_a;
    char name[96];
    if (msx2) { msx2_setup(a, &va, map_a); msx2_drive(a); }
    else { msx1_setup(a, ram_a); msx1_drive(a); }
    size_t n = save(a, ram_a, buf1);
    snapshot(a, v, ram_a, map);

    snprintf(name, sizeof name, "%s: truncated by one byte refused", tag);
    check(name, msx_machine_state_check(a, ram_a, buf1, n - 1), 0);
    snprintf(name, sizeof name, "%s: one byte longer refused", tag);
    memcpy(buf2, buf1, n); buf2[n] = 0;
    check(name, msx_machine_state_check(a, ram_a, buf2, n + 1), 0);
    snprintf(name, sizeof name, "%s: empty refused", tag);
    check(name, msx_machine_state_check(a, ram_a, buf1, 0), 0);

    /* where each field sits: the first byte that differs between two saves of a machine with that field changed */
    size_t at_line, at_lpf, at_reg = (size_t)-1;
    MsxMachine saved = *a;
    a->line += 1;
    size_t n2 = save(a, ram_a, buf2); (void)n2;
    at_line = first_diff(buf1, buf2, n);
    *a = saved;
    a->lines_per_frame = MSX_LINES_PAL;
    save(a, ram_a, buf2);
    at_lpf = first_diff(buf1, buf2, n);
    *a = saved;
    if (msx2) {
        a->mapper.reg[0] ^= 1;
        save(a, ram_a, buf2);
        at_reg = first_diff(buf1, buf2, n);
        *a = saved;
    }
    snapshot(a, v, ram_a, map);                             /* the live machine is back as it was */
    check("offsets: line before lines_per_frame", at_line < at_lpf, 1);

    memcpy(buf2, buf1, n); buf2[at_lpf] ^= 1;
    snprintf(name, sizeof name, "%s: lines_per_frame changed refused", tag);
    check(name, msx_machine_state_check(a, ram_a, buf2, n), 0);
    memcpy(buf2, buf1, n); buf2[at_lpf + 4] ^= 1;           /* video follows lines_per_frame (4 bytes) */
    snprintf(name, sizeof name, "%s: video changed refused", tag);
    check(name, msx_machine_state_check(a, ram_a, buf2, n), 0);
    memcpy(buf2, buf1, n); buf2[at_line + 1] = 0xFF;        /* line: a value far past lines_per_frame (little-endian) */
    snprintf(name, sizeof name, "%s: line too large refused", tag);
    check(name, msx_machine_state_check(a, ram_a, buf2, n), 0);
    memcpy(buf2, buf1, n); buf2[at_line] ^= 0;              /* control: an untouched copy is accepted */
    snprintf(name, sizeof name, "%s: control copy accepted", tag);
    check(name, msx_machine_state_check(a, ram_a, buf2, n), 1);
    /* 313 lines (little-endian 39h 01h): on the V9938 the standard is R#9's, taken at each frame, so a state saved after a
     * game (or a European BIOS) set 50 Hz loads into a machine that started at 262; on the TMS9918A it is the build's. */
    memcpy(buf2, buf1, n); buf2[at_lpf] = 0x39; buf2[at_lpf + 1] = 0x01;
    snprintf(name, sizeof name, "%s: a state of 313 lines into a 262-line machine", tag);
    check(name, msx_machine_state_check(a, ram_a, buf2, n), msx2 ? 1 : 0);
    if (msx2) {
        memcpy(buf2, buf1, n); buf2[at_reg] = SEGMENTS;     /* a mapper register at the segment count */
        check("msx2: mapper register >= segments refused", msx_machine_state_check(a, ram_a, buf2, n), 0);
        memcpy(buf2, buf1, n); buf2[at_reg] = SEGMENTS - 1;
        check("msx2: mapper register at the last segment accepted", msx_machine_state_check(a, ram_a, buf2, n), 1);
    }
    snprintf(name, sizeof name, "%s: refusals left the live machine untouched", tag);
    check(name, untouched(a, v, ram_a, map), 1);
}

static void cross(void)
{
    msx1_setup(&ma, ram_a); msx1_drive(&ma);
    size_t n1 = save(&ma, ram_a, buf1);
    msx2_setup(&mb, &vb, map_b); msx2_drive(&mb);
    size_t n2 = save(&mb, ram_b, buf2);
    snapshot(&mb, &vb, ram_b, map_b);
    check("MSX1 state refused by the MSX2 machine", msx_machine_state_check(&mb, ram_b, buf1, n1), 0);
    check("MSX2 machine untouched by that refusal", untouched(&mb, &vb, ram_b, map_b), 1);
    snapshot(&ma, NULL, ram_a, map_a);
    check("MSX2 state refused by the MSX1 machine", msx_machine_state_check(&ma, ram_a, buf2, n2), 0);
    check("MSX1 machine untouched by that refusal", untouched(&ma, NULL, ram_a, map_a), 1);
}

int main(void)
{
    (void)rr_state_word; (void)rr_state_bytes;   /* state_io.h's helpers are used by msx_state.c */
    roundtrip("msx1", 0);
    roundtrip("msx2", 1);
    damaged("msx1", 0);
    damaged("msx2", 1);
    cross();
    printf("%s\n", failures ? "FAILED" : "all state checks passed");
    return failures ? 1 : 0;
}
