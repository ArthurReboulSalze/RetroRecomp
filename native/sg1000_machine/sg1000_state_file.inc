/* Quick states of the SG-1000 game (MIT, Retro-Recomp), included by sg1000_player.c after sg1000_glue.inc and sg1000_game.h.
 *
 * The file is the envelope the Z80 machines share (state_envelope.h: magic RRSG1ST, schema 1, machine 1 NTSC or 2 PAL, the
 * cartridge's SHA-256), then the body, layout `sg1000-state-1`, in this fixed order (state_io.h: fixed-width little-endian
 * fields, never a pointer, a host address or a C layout):
 *   (1) the build binding, RR_SG_STATE_ABI, 32 bytes the converter writes in sg1000_game.h (the layout name, the standard, the size of
 *       the cartridge as the machine sees it), compared and never applied;
 *   (2) the CPU: A F B C D E H L, the shadow set, PC SP IX IY WZ I R, IFF1 IFF2 IM, halted, Q P, the EI delay, the cycle counter;
 *   (3) the machine: line, cycles, next line, frames, the frame trace, the /NMI edge, and (never applied, refused when they differ)
 *       the lines per frame and the cartridge's size;
 *   (4) the 1 KiB of RAM;
 *   (5) the TMS9918A: the 16 KiB of VRAM, the eight registers, the status, the address, the control latch, the first control byte, the
 *       read-ahead, the picture of 256 x 192 colour indices and the border colour of each line;
 *   (6) the SN76489A: the three tone periods, the noise register, the four attenuations, the latch, the four counters and outputs,
 *       the noise shift register, the clock (time, tick rest, ticks, next sample, the accumulator), the samples not yet taken and the
 *       count of samples lost.
 * Not saved: the pads (host input, the host gives them again at the next frame), the hooks, the trace switch, the cartridge. A state is
 * decoded twice, as state_io.h asks: checked whole on a scratch copy of the machine (the live machine and the CPU are never touched),
 * and applied only when every check passed, so a refused or damaged state leaves the game as it was. Saved and loaded at the service
 * point (an instruction and the interrupt it may accept complete), the only point where the loop's own locals hold nothing a state
 * would need. A state loaded by a fresh process continues the frames the saving process would have run. */
#include <wchar.h>

#include "state_envelope.h"

#define SG_STATE_SCHEMA 1u
/* The largest body: the VRAM, the picture, the sound samples not yet taken, the CPU and the rest, with room to spare. */
#define SG_STATE_CAPACITY ((size_t)(160u << 10))

static const uint8_t sg_state_binding[32] = RR_SG_STATE_ABI;

#define SGW(lvalue, width, maximum) \
    (io->mode == RR_STATE_WRITE ? (void)rr_state_word(io, (uint64_t)(lvalue), (width), (maximum)) \
                                : (void)((lvalue) = rr_state_word(io, (uint64_t)(lvalue), (width), (maximum))))
#define SGB(lvalue) SGW(lvalue, 1, 0xFF)

/* A field of the configuration: written from the live machine, never applied, refused when it differs. */
static void sg_state_same(RetroStateIO *io, uint64_t live, unsigned width)
{
    uint64_t v = rr_state_word(io, live, width, width == 8 ? UINT64_MAX : (1ull << (8 * width)) - 1);
    if (io->mode != RR_STATE_WRITE && v != live)
        io->ok = false;
}

/* (2) The CPU, field for field as the MSX's (msx_state_file.inc) and the Master System's (gamestate.inc), into `s`. */
static void sg_cpu_state(RetroStateIO *io, Z80State *s)
{
    Z80State v = *s;
    RR_FIELD(v, a, 1, 255); RR_FIELD(v, f, 1, 255); RR_FIELD(v, b, 1, 255); RR_FIELD(v, c, 1, 255);
    RR_FIELD(v, d, 1, 255); RR_FIELD(v, e, 1, 255); RR_FIELD(v, h, 1, 255); RR_FIELD(v, l, 1, 255);
    RR_FIELD(v, a_, 1, 255); RR_FIELD(v, f_, 1, 255); RR_FIELD(v, b_, 1, 255); RR_FIELD(v, c_, 1, 255);
    RR_FIELD(v, d_, 1, 255); RR_FIELD(v, e_, 1, 255); RR_FIELD(v, h_, 1, 255); RR_FIELD(v, l_, 1, 255);
    RR_FIELD(v, pc, 2, 65535); RR_FIELD(v, sp, 2, 65535); RR_FIELD(v, ix, 2, 65535);
    RR_FIELD(v, iy, 2, 65535); RR_FIELD(v, wz, 2, 65535); RR_FIELD(v, i, 1, 255); RR_FIELD(v, r, 1, 255);
    RR_FIELD(v, iff1, 1, 1); RR_FIELD(v, iff2, 1, 1); RR_FIELD(v, im, 1, 2); RR_FIELD(v, halted, 1, 1);
    RR_FIELD(v, q, 1, 255); RR_FIELD(v, p, 1, 1); RR_FIELD(v, ei_block, 1, 1); RR_FIELD(v, cyc, 8, (1ULL << 60));
    *s = v;
}

static int32_t sg_state_signed(RetroStateIO *io, int64_t value, unsigned width)
{
    const uint64_t mask = (1ull << (8 * width)) - 1;
    uint64_t r = rr_state_word(io, (uint64_t)value & mask, width, mask);
    if ((r >> (8 * width - 1)) & 1)
        r |= ~mask;
    return (int32_t)(int64_t)r;
}

/* (6) The SN76489A. */
static void sg_psg_state(RetroStateIO *io, Sn76489 *s)
{
    for (int c = 0; c < 3; ++c)
        SGW(s->tone[c], 2, 0x3FF);
    SGW(s->noise, 1, 7);
    for (int c = 0; c < 4; ++c)
        SGW(s->volume[c], 1, 15);
    SGW(s->latch, 1, 7);
    for (int c = 0; c < 4; ++c)
        SGW(s->count[c], 2, 0xFFFF);
    for (int c = 0; c < 4; ++c)
        SGW(s->out[c], 1, 1);
    SGW(s->lfsr, 2, 0x7FFF);
    SGW(s->time, 8, UINT64_MAX);
    SGW(s->tick_rest, 4, 15);
    SGW(s->ticks, 4, 0xFFFFFFFFu);
    SGW(s->next_sample, 8, UINT64_MAX);
    if (io->mode == RR_STATE_WRITE)
        sg_state_signed(io, s->acc, 4);
    else
        s->acc = sg_state_signed(io, s->acc, 4);
    SGW(s->acc_ticks, 4, 16);
    SGW(s->sample_count, 4, SN_AUDIO_BUFFER);
    for (unsigned i = 0; io->ok && i < s->sample_count; ++i) {
        if (io->mode == RR_STATE_WRITE)
            sg_state_signed(io, s->samples[i], 2);
        else
            s->samples[i] = (int16_t)sg_state_signed(io, s->samples[i], 2);
    }
    SGW(s->dropped, 8, UINT64_MAX);
}

/* What a decoded state must satisfy before it is applied. `cpu_cycles` is the decoded CPU's cycle counter. */
static int sg_state_consistent(const SgMachine *m, uint64_t cpu_cycles)
{
    if (m->lines_per_frame != SG_LINES_NTSC && m->lines_per_frame != SG_LINES_PAL)
        return 0;
    if (m->line >= m->lines_per_frame || m->frames >= (1ull << 40) || m->cycles >= (1ull << 47) || m->nmi_edge > 1)
        return 0;
    /* The line clock is a function of the frame and the line: a state whose clock says otherwise is not one this machine made, and
     * a crafted one would only make the next catch-up loop for ever. */
    if (m->next_line != ((m->frames * m->lines_per_frame) + m->line + 1) * SG_CYCLES_PER_LINE)
        return 0;
    if (m->cycles >= m->next_line || m->next_line - m->cycles > SG_CYCLES_PER_LINE)
        return 0;
    /* At the service point the CPU is within a line of the machine (the hardware catches up at the end of a line, or at a port). */
    if (cpu_cycles < m->cycles || cpu_cycles - m->cycles > SG_CYCLES_PER_LINE)
        return 0;
    const Sn76489 *s = &m->psg;
    if (s->time > m->cycles || m->cycles - s->time > SG_CYCLES_PER_LINE || s->tick_rest > s->time)
        return 0;
    if (s->next_sample <= ((s->time - s->tick_rest) << 16) || s->next_sample > (s->time << 16) + ((uint64_t)SN_CPU_CLOCK * 65536u / SN_AUDIO_RATE))
        return 0;
    if (s->acc < 0 || (int64_t)s->acc > (int64_t)s->acc_ticks * 26212)
        return 0;
    return 1;
}

static void sg_machine_state(SgMachine *m, RetroStateIO *io, uint64_t cpu_cycles)
{
    /* (3) The machine. */
    SGW(m->line, 4, 0xFFFFFFFFu);
    SGW(m->cycles, 8, UINT64_MAX);
    SGW(m->next_line, 8, UINT64_MAX);
    SGW(m->frames, 8, UINT64_MAX);
    SGW(m->frame_trace, 4, 0xFFFFFFFFu);
    SGW(m->nmi_edge, 1, 1);
    sg_state_same(io, m->lines_per_frame, 4);
    sg_state_same(io, m->rom_size, 4);
    /* (4) RAM. */
    rr_state_bytes(io, m->ram, sizeof m->ram);
    /* (5) The TMS9918A. The picture and the borders are colour indices: read byte by byte, so the check sees the decoded values. */
    Tms9918 *t = &m->vdp;
    rr_state_bytes(io, t->vram, sizeof t->vram);
    rr_state_bytes(io, t->reg, sizeof t->reg);
    SGB(t->status);
    SGW(t->address, 2, 0x3FFF);
    SGW(t->latch, 1, 1);
    SGB(t->first);
    SGB(t->readahead);
    for (int y = 0; y < TMS_HEIGHT; ++y)
        for (int x = 0; x < TMS_WIDTH; ++x)
            SGW(t->frame[y][x], 1, 15);
    for (int y = 0; y < TMS_HEIGHT; ++y)
        SGW(t->border[y], 1, 15);
    /* (6) The SN76489A. */
    sg_psg_state(io, &m->psg);
    if (io->ok && io->mode != RR_STATE_WRITE && !sg_state_consistent(m, cpu_cycles))
        io->ok = false;
}

static void sg_state_body(RetroStateIO *io)
{
    /* (1) the build binding */
    for (int i = 0; i < 32; ++i)
        if (rr_state_word(io, sg_state_binding[i], 1, 255) != sg_state_binding[i])
            io->ok = false;
    /* (2) the CPU: into a candidate, applied last */
    Z80State cpu = g_z80;
    sg_cpu_state(io, &cpu);
    if (io->mode == RR_STATE_CHECK) {
        static SgMachine scratch;                    /* the live machine is never touched by a check */
        scratch = machine;
        sg_machine_state(&scratch, io, cpu.cyc);
        return;
    }
    sg_machine_state(&machine, io, cpu.cyc);
    if (io->mode == RR_STATE_APPLY && io->ok) {
        g_z80 = cpu;
        map_built = UINT32_MAX;                      /* the loop's region map is rebuilt before the next step */
        g_next_line_cyc = sg_next_event(&machine);
        smsrecomp_measured_guest_cycles = g_z80.cyc;
        step_start = g_z80.cyc;
        smsrecomp_interp_depth = 0;                  /* the fallback CPU is refilled from g_z80 at each use */
        /* Execution, fallback and learning counters stay cumulative across a load, as on the Master System and the MSX. */
    }
}

static RetroStateEnvelope sg_state_envelope(void)
{
    RetroStateEnvelope e = {"RRSG1ST\0", SG_STATE_SCHEMA, (unsigned)(RR_SG_PAL ? 2 : 1), RR_SG_IDENTITY, sg_state_body};
    return e;
}

/* Save to `path`: written beside it, flushed, then put in its place (the old state stays whole if anything fails). */
static int sg_state_save(const wchar_t *path)
{
    uint8_t *data = (uint8_t *)malloc(SG_STATE_CAPACITY);
    if (!data) return RR_STATE_IO_ERROR;
    RetroStateEnvelope envelope = sg_state_envelope();
    size_t size = 0;
    if (rr_state_envelope_write(&envelope, data, SG_STATE_CAPACITY, &size) != RR_STATE_OK) { free(data); return RR_STATE_INVALID; }
    wchar_t temporary[32768];
    swprintf(temporary, 32768, L"%ls.%lu.tmp", path, rr_process_id());
    FILE *f = rr_fopen(temporary, L"wb");
    bool ok = f && fwrite(data, size, 1, f) == 1;
    if (ok) ok = rr_flush_file(f) != 0;
    if (f && fclose(f) != 0) ok = false;
    free(data);
    if (ok) ok = rr_replace(temporary, path) != 0;
    if (!ok) rr_remove(temporary);
    return ok ? RR_STATE_OK : RR_STATE_IO_ERROR;
}

/* Load `path`: RR_STATE_OK, or a refusal that leaves the machine and the file as they were: RR_STATE_MISSING (no file: nothing is
 * created), RR_STATE_INCOMPATIBLE (a whole state of another game, standard, layout or build), RR_STATE_INVALID (not a state, damaged,
 * cut, or a body whose values no machine could have made), RR_STATE_IO_ERROR. */
static int sg_state_load(const wchar_t *path)
{
    FILE *f = rr_fopen(path, L"rb");
    if (!f) return rr_exists(path) ? RR_STATE_IO_ERROR : RR_STATE_MISSING;
    uint8_t *data = (uint8_t *)malloc(SG_STATE_CAPACITY);
    if (!data) { fclose(f); return RR_STATE_IO_ERROR; }
    size_t size = fread(data, 1, SG_STATE_CAPACITY, f);
    int extra = fgetc(f); bool read_ok = !ferror(f); fclose(f);
    int result = RR_STATE_INVALID;
    if (read_ok && extra == EOF) {
        RetroStateEnvelope envelope = sg_state_envelope();
        result = rr_state_envelope_read(&envelope, data, size);
        /* A whole, undamaged state of another build (the layout, the standard, the cartridge's size): incompatible, not damaged. */
        if (result == RR_STATE_INVALID && size >= RR_STATE_ENVELOPE_HEADER + 32
            && (size_t)(data[80] | data[81] << 8 | (uint32_t)data[82] << 16 | (uint32_t)data[83] << 24) == size - RR_STATE_ENVELOPE_HEADER
            && rr_state_crc(data + RR_STATE_ENVELOPE_HEADER, size - RR_STATE_ENVELOPE_HEADER)
               == (uint32_t)(data[84] | data[85] << 8 | (uint32_t)data[86] << 16 | (uint32_t)data[87] << 24)
            && memcmp(data + RR_STATE_ENVELOPE_HEADER, sg_state_binding, 32))
            result = RR_STATE_INCOMPATIBLE;
    }
    free(data);
    return result;
}
