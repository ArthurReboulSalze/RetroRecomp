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

#include "z80_chain_state.inc"
#include "state_file.h"

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
    /* The box filter (native/audio_box.h): the stream's time and boundary, the level x cycles being built, the samples not yet taken. Its
     * clock, rate, capacity and buffer are constants of the build. */
    SGW(s->box.time, 8, UINT64_MAX);
    SGW(s->box.next_sample, 8, UINT64_MAX);
    if (io->mode == RR_STATE_WRITE)
        sg_state_signed(io, (int32_t)s->box.acc[0], 4);
    else
        s->box.acc[0] = sg_state_signed(io, (int32_t)s->box.acc[0], 4);
    SGW(s->box.acc_cycles, 8, 1u << 20);
    SGW(s->box.count, 4, SN_AUDIO_BUFFER);
    for (unsigned i = 0; io->ok && i < s->box.count; ++i) {
        if (io->mode == RR_STATE_WRITE)
            sg_state_signed(io, s->samples[i], 2);
        else
            s->samples[i] = (int16_t)sg_state_signed(io, s->samples[i], 2);
    }
    SGW(s->box.dropped, 4, 0xFFFFFFFFu);
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
    if (s->box.time != s->time - s->tick_rest)
        return 0;
    if (s->box.next_sample <= (s->box.time << 16) || s->box.next_sample > (s->box.time << 16) + s->box.step)
        return 0;
    if (s->box.acc[0] < 0 || s->box.acc[0] > (int64_t)s->box.acc_cycles * 26212)
        return 0;
    return 1;
}

static void sg_machine_state(SgMachine *m, RetroStateIO *io)
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
}

/* What the file's consistency hook checks (state_file.h): the machine the body decoded in the check pass, and the CPU's cycle it decoded. */
static SgMachine sg_scratch;
static uint64_t sg_scratch_cpu_cycles;
static bool sg_consistent(void)
{
    return sg_state_consistent(&sg_scratch, sg_scratch_cpu_cycles);
}

/* The body after the build binding (which state_file.h compares): the CPU, then the machine. */
static void sg_state_body(RetroStateIO *io)
{
    /* (2) the CPU: into a candidate, applied last */
    Z80State cpu = g_z80;
    rr_z80_cpu_state(io, &cpu);
    if (io->mode == RR_STATE_CHECK) {
        sg_scratch = machine;                        /* the live machine is never touched by a check */
        sg_machine_state(&sg_scratch, io);
        sg_scratch_cpu_cycles = cpu.cyc;
        return;
    }
    sg_machine_state(&machine, io);
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

static RetroStateFile sg_state_file(void)
{
    RetroStateFile f = {{"RRSG1ST\0", SG_STATE_SCHEMA, (unsigned)(RR_SG_PAL ? 2 : 1), RR_SG_IDENTITY, sg_state_body},
                        sg_state_binding, sizeof sg_state_binding, sg_consistent, SG_STATE_CAPACITY};
    return f;
}

/* Save to `path`: written beside it, flushed, then put in its place (the old state stays whole if anything fails). */
static int sg_state_save(const wchar_t *path)
{
    RetroStateFile f = sg_state_file();
    return rr_state_file_save(&f, path);
}

/* Load `path`: RR_STATE_OK, or a refusal that leaves the machine and the file as they were: RR_STATE_MISSING (no file: nothing is
 * created), RR_STATE_INCOMPATIBLE (a whole state of another game, standard, layout or build), RR_STATE_INVALID (not a state, damaged,
 * cut, or a body whose values no machine could have made), RR_STATE_IO_ERROR. */
static int sg_state_load(const wchar_t *path)
{
    RetroStateFile f = sg_state_file();
    return rr_state_file_load(&f, path);
}
