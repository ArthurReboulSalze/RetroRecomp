/* Quick states of the ColecoVision game (MIT, Retro-Recomp), included by coleco_player.c after coleco_glue.inc and coleco_game.h.
 *
 * The file is the envelope the Z80 machines share (state_envelope.h: magic RRCV1ST, schema 1, machine 1 NTSC or 2 PAL, the
 * cartridge's SHA-256), then the body, layout `coleco-state-1`, in this fixed order (state_io.h: fixed-width little-endian
 * fields, never a pointer, a host address or a C layout):
 *   (1) the build binding, RR_CV_STATE_ABI, 32 bytes the converter writes in coleco_game.h (the layout name, the standard, the size of
 *       the cartridge as the machine sees it, the BIOS's SHA-256), compared and never applied;
 *   (2) the CPU: A F B C D E H L, the shadow set, PC SP IX IY WZ I R, IFF1 IFF2 IM, halted, Q P, the EI delay, the cycle counter;
 *   (3) the machine: line, cycles, next line, frames, the frame trace, the VDP interrupt line as the CPU last saw it (the /NMI edge's memory), the controllers' mode, and (never applied, refused when they differ)
 *       the lines per frame and the cartridge's size;
 *   (4) the 1 KiB of RAM;
 *   (5) the TMS9918A: the 16 KiB of VRAM, the eight registers, the status, the address, the control latch, the first control byte, the
 *       read-ahead, the picture of 256 x 192 colour indices and the border colour of each line;
 *   (6) the SN76489A: the three tone periods, the noise register, the four attenuations, the latch, the four counters and outputs,
 *       the noise shift register, the clock (time, tick rest, ticks, next sample, the accumulator), the samples not yet taken and the
 *       count of samples lost.
 * Not saved: the pads (host input, the host gives them again at the next frame), the hooks, the trace switch, the cartridge and the BIOS. A state is
 * decoded twice, as state_io.h asks: checked whole on a scratch copy of the machine (the live machine and the CPU are never touched),
 * and applied only when every check passed, so a refused or damaged state leaves the game as it was. Saved and loaded at the service
 * point (an instruction and the interrupt it may accept complete), the only point where the loop's own locals hold nothing a state
 * would need. A state loaded by a fresh process continues the frames the saving process would have run. */
#include <wchar.h>

#include "z80_chain_state.inc"
#include "state_file.h"

#define CV_STATE_SCHEMA 1u
static int cv_state_picture = 1;               /* 0: the snapshots leave the picture and the borders out (they are drawn again) */
/* The largest body: the VRAM, the picture, the sound samples not yet taken, the CPU and the rest, with room to spare. */
#define CV_STATE_CAPACITY ((size_t)(160u << 10))

static const uint8_t cv_state_binding[32] = RR_CV_STATE_ABI;

#define CVW(lvalue, width, maximum) \
    (io->mode == RR_STATE_WRITE ? (void)rr_state_word(io, (uint64_t)(lvalue), (width), (maximum)) \
                                : (void)((lvalue) = rr_state_word(io, (uint64_t)(lvalue), (width), (maximum))))
#define CVB(lvalue) CVW(lvalue, 1, 0xFF)

/* A field of the configuration: written from the live machine, never applied, refused when it differs. */
static void cv_state_same(RetroStateIO *io, uint64_t live, unsigned width)
{
    uint64_t v = rr_state_word(io, live, width, width == 8 ? UINT64_MAX : (1ull << (8 * width)) - 1);
    if (io->mode != RR_STATE_WRITE && v != live)
        io->ok = false;
}

static int32_t cv_state_signed(RetroStateIO *io, int64_t value, unsigned width)
{
    const uint64_t mask = (1ull << (8 * width)) - 1;
    uint64_t r = rr_state_word(io, (uint64_t)value & mask, width, mask);
    if ((r >> (8 * width - 1)) & 1)
        r |= ~mask;
    return (int32_t)(int64_t)r;
}

/* (6) The SN76489A. */
static void cv_psg_state(RetroStateIO *io, Sn76489 *s)
{
    for (int c = 0; c < 3; ++c)
        CVW(s->tone[c], 2, 0x3FF);
    CVW(s->noise, 1, 7);
    for (int c = 0; c < 4; ++c)
        CVW(s->volume[c], 1, 15);
    CVW(s->latch, 1, 7);
    for (int c = 0; c < 4; ++c)
        CVW(s->count[c], 2, 0xFFFF);
    for (int c = 0; c < 4; ++c)
        CVW(s->out[c], 1, 1);
    CVW(s->lfsr, 2, 0x7FFF);
    CVW(s->time, 8, UINT64_MAX);
    CVW(s->tick_rest, 4, 15);
    /* The box filter (native/audio_box.h): the stream's time and boundary, the level x cycles being built, the samples not yet taken. Its
     * clock, rate, capacity and buffer are constants of the build. */
    CVW(s->box.time, 8, UINT64_MAX);
    CVW(s->box.next_sample, 8, UINT64_MAX);
    if (io->mode == RR_STATE_WRITE)
        cv_state_signed(io, (int32_t)s->box.acc[0], 4);
    else
        s->box.acc[0] = cv_state_signed(io, (int32_t)s->box.acc[0], 4);
    CVW(s->box.acc_cycles, 8, 1u << 20);
    CVW(s->box.count, 4, SN_AUDIO_BUFFER);
    for (unsigned i = 0; io->ok && i < s->box.count; ++i) {
        if (io->mode == RR_STATE_WRITE)
            cv_state_signed(io, s->samples[i], 2);
        else
            s->samples[i] = (int16_t)cv_state_signed(io, s->samples[i], 2);
    }
    CVW(s->box.dropped, 4, 0xFFFFFFFFu);
}

/* What a decoded state must satisfy before it is applied. `cpu_cycles` is the decoded CPU's cycle counter. */
static int cv_state_consistent(const CvMachine *m, uint64_t cpu_cycles)
{
    if (m->lines_per_frame != CV_LINES_NTSC && m->lines_per_frame != CV_LINES_PAL)
        return 0;
    if (m->line >= m->lines_per_frame || m->frames >= (1ull << 40) || m->cycles >= (1ull << 47) || m->nmi_level > 1 || m->keypad_mode > 1)
        return 0;
    /* The line clock is a function of the frame and the line: a state whose clock says otherwise is not one this machine made, and
     * a crafted one would only make the next catch-up loop for ever. */
    if (m->next_line != ((m->frames * m->lines_per_frame) + m->line + 1) * CV_CYCLES_PER_LINE)
        return 0;
    if (m->cycles >= m->next_line || m->next_line - m->cycles > CV_CYCLES_PER_LINE)
        return 0;
    /* At the service point the CPU is within a line of the machine (the hardware catches up at the end of a line, or at a port). */
    if (cpu_cycles < m->cycles || cpu_cycles - m->cycles > CV_CYCLES_PER_LINE)
        return 0;
    const Sn76489 *s = &m->psg;
    if (s->time > m->cycles || m->cycles - s->time > CV_CYCLES_PER_LINE || s->tick_rest > s->time)
        return 0;
    if (s->box.time != s->time - s->tick_rest)
        return 0;
    if (s->box.next_sample <= (s->box.time << 16) || s->box.next_sample > (s->box.time << 16) + s->box.step)
        return 0;
    if (s->box.acc[0] < 0 || s->box.acc[0] > (int64_t)s->box.acc_cycles * 26212)
        return 0;
    return 1;
}

static void cv_machine_state(CvMachine *m, RetroStateIO *io)
{
    /* (3) The machine. */
    CVW(m->line, 4, 0xFFFFFFFFu);
    CVW(m->cycles, 8, UINT64_MAX);
    CVW(m->next_line, 8, UINT64_MAX);
    CVW(m->frames, 8, UINT64_MAX);
    CVW(m->frame_trace, 4, 0xFFFFFFFFu);
    CVW(m->nmi_level, 1, 1);
    CVW(m->keypad_mode, 1, 1);
    cv_state_same(io, m->lines_per_frame, 4);
    cv_state_same(io, m->rom_size, 4);
    /* (4) RAM. */
    rr_state_bytes(io, m->ram, sizeof m->ram);
    /* (5) The TMS9918A. The picture and the borders are colour indices: read byte by byte, so the check sees the decoded values. */
    Tms9918 *t = &m->vdp;
    rr_state_bytes(io, t->vram, sizeof t->vram);
    rr_state_bytes(io, t->reg, sizeof t->reg);
    CVB(t->status);
    CVW(t->address, 2, 0x3FFF);
    CVW(t->latch, 1, 1);
    CVB(t->first);
    CVB(t->readahead);
    if (cv_state_picture) {
        for (int y = 0; y < TMS_HEIGHT; ++y)
            for (int x = 0; x < TMS_WIDTH; ++x)
                CVW(t->frame[y][x], 1, 15);
        for (int y = 0; y < TMS_HEIGHT; ++y)
            CVW(t->border[y], 1, 15);
    }
    /* (6) The SN76489A. */
    cv_psg_state(io, &m->psg);
}

/* What the file's consistency hook checks (state_file.h): the machine the body decoded in the check pass, and the CPU's cycle it decoded. */
static CvMachine cv_scratch;
static uint64_t cv_scratch_cpu_cycles;
static bool cv_consistent(void)
{
    return cv_state_consistent(&cv_scratch, cv_scratch_cpu_cycles);
}

/* The body after the build binding (which state_file.h compares): the CPU, then the machine. */
static void cv_state_body(RetroStateIO *io)
{
    /* (2) the CPU: into a candidate, applied last */
    Z80State cpu = g_z80;
    rr_z80_cpu_state(io, &cpu);
    if (io->mode == RR_STATE_CHECK) {
        cv_scratch = machine;                        /* the live machine is never touched by a check */
        cv_machine_state(&cv_scratch, io);
        cv_scratch_cpu_cycles = cpu.cyc;
        return;
    }
    cv_machine_state(&machine, io);
    if (io->mode == RR_STATE_APPLY && io->ok) {
        g_z80 = cpu;
        map_built = UINT32_MAX;                      /* the loop's region map is rebuilt before the next step */
        g_next_line_cyc = cv_next_event(&machine);
        smsrecomp_measured_guest_cycles = g_z80.cyc;
        step_start = g_z80.cyc;
        smsrecomp_interp_depth = 0;                  /* the fallback CPU is refilled from g_z80 at each use */
        /* Execution, fallback and learning counters stay cumulative across a load, as on the Master System and the MSX. */
    }
}

static RetroStateFile cv_state_file(void)
{
    RetroStateFile f = {{"RRCV1ST\0", CV_STATE_SCHEMA, (unsigned)(RR_CV_PAL ? 2 : 1), RR_CV_IDENTITY, cv_state_body},
                        cv_state_binding, sizeof cv_state_binding, cv_consistent, CV_STATE_CAPACITY};
    return f;
}

/* Save to `path`: written beside it, flushed, then put in its place (the old state stays whole if anything fails). */
static int cv_state_save(const wchar_t *path)
{
    RetroStateFile f = cv_state_file();
    return rr_state_file_save(&f, path);
}

/* Load `path`: RR_STATE_OK, or a refusal that leaves the machine and the file as they were: RR_STATE_MISSING (no file: nothing is
 * created), RR_STATE_INCOMPATIBLE (a whole state of another game, standard, layout or build), RR_STATE_INVALID (not a state, damaged,
 * cut, or a body whose values no machine could have made), RR_STATE_IO_ERROR. */
static int cv_state_load(const wchar_t *path)
{
    RetroStateFile f = cv_state_file();
    return rr_state_file_load(&f, path);
}

/* ---- In-process snapshots for multiplayer (hostkit.h, "Multiplayer"; MIT, Retro-Recomp) ----
 * The rollback tier saves one a frame and loads one a correction, the host's F8 / F9 for everyone are the same snapshots, and the digest the
 * session compares is a hash of one. A snapshot is a head (the magic and the two pad words the adapter set) then the quick state's body
 * (the CPU and the whole machine, without the picture: the next frame draws it again, as the MSX's snapshots). Fixed-width little-endian
 * fields, never a C layout or an address: the same bytes on Windows and Linux. Memory only, never a file, no envelope, no allocation per
 * call; taken and loaded at the service point (the frame's end), where the quick states already are. A load is checked whole (the head,
 * then the body on the machine's scratch copy, then its consistency rules) before anything is applied; a buffer of another size is refused. */
#define CV_SNAP_MAGIC 0x31504E5356435252ull
static uint8_t cv_snap_scratch[CV_STATE_CAPACITY];

static void cv_snap_head(RetroStateIO *io, uint16_t pads[2])
{
    if (rr_state_word(io, CV_SNAP_MAGIC, 8, UINT64_MAX) != CV_SNAP_MAGIC)
        io->ok = false;
    for (int i = 0; i < 2; ++i)
        pads[i] = (uint16_t)rr_state_word(io, machine.pad[i], 2, CV_PAD_MASK);
}

static size_t cv_snap_save(void *buffer, size_t capacity)
{
    uint16_t pads[2];
    RetroStateIO io = {(uint8_t *)buffer, capacity, 0, RR_STATE_WRITE, true};
    cv_snap_head(&io, pads);
    cv_state_picture = 0;                       /* the next frame draws the picture again: not stored */
    cv_state_body(&io);
    cv_state_picture = 1;
    return io.ok ? io.pos : 0;
}

static bool cv_snap_load(const void *buffer, size_t size)
{
    uint16_t pads[2];
    RetroStateIO check = {(uint8_t *)buffer, size, 0, RR_STATE_CHECK, true};
    cv_snap_head(&check, pads);
    if (!check.ok)
        return false;
    cv_state_picture = 0;
    cv_state_body(&check);
    cv_state_picture = 1;
    if (!check.ok || check.pos != size || !cv_consistent())
        return false;
    RetroStateIO apply = {(uint8_t *)buffer, size, 0, RR_STATE_APPLY, true};
    cv_snap_head(&apply, pads);
    cv_state_picture = 0;
    cv_state_body(&apply);
    cv_state_picture = 1;
    if (!apply.ok)
        return false;                                /* not reached: the same bytes passed the check */
    machine.pad[0] = pads[0];
    machine.pad[1] = pads[1];
    handed_this_frame = machine.line >= TMS_VBLANK_LINE;
    return true;
}

static size_t cv_snap_bound(void)
{
    static size_t bound;
    if (!bound)
        bound = cv_snap_save(cv_snap_scratch, sizeof cv_snap_scratch);
    return bound;
}

/* FNV-1a 64 over a snapshot's bytes: the deterministic state after the last frame, in the order the snapshot names its fields. */
static uint64_t cv_snap_digest(void)
{
    const size_t n = cv_snap_save(cv_snap_scratch, sizeof cv_snap_scratch);
    uint64_t h = 1469598103934665603ull;
    for (size_t i = 0; i < n; ++i) { h ^= cv_snap_scratch[i]; h *= 1099511628211ull; }
    return n ? h : 0;
}
