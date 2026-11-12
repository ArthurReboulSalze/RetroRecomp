/* The V9938 command engine (MSX2). MIT, Retro-Recomp.
 *
 * Written from the V9938 Technical Data Book (the commands chapter: the twelve commands, the logical operations, the
 * coordinate registers R#32-R#46 and the status bits); what the book leaves open (how the registers read back, TR after a
 * CPU-paced command, the clipping, LINE's step, SRCH's EQ) was checked against openMSX 22.0 run as a separate program
 * (private comparisons; none of its code or tables is here). The
 * rules followed here are restated in docs/MSX.md.
 *
 * Timing is approximated: each command has a start delay and an average cost per byte or dot in three classes (display
 * off or outside the picture; picture with sprites off; with sprites on), plus a cost at each line end; the access
 * slots of the chip and the slots the CPU takes are not modelled. The numbers were measured on 12 November 2026 by
 * timing commands from the outside in openMSX 22.0 run as a separate program (a black box: none of its code, tables or
 * data files was used). An authored MSX2 cartridge started each command in Graphic 4 at picture line 1 and read S#2
 * once, m CPU cycles later, m found by bisection (one read per run, so the reading did not change the timing; Z80
 * T-states plus one wait per M1 cycle, checked on all 4,370 runs): 200 commands per class, each end known to 6 ticks.
 * Start = the measured duration of a one-unit command in class 0; cost = the slope over single-line commands; line end
 * = the extra cost per line of narrow commands (class 0); LINE's minor step from its diagonals; POINT and LMCM's first
 * dot ended before the earliest possible read (72 ticks): 66 is taken. Against those 600 durations, this model is within
 * 4 % with the display off, 1 to 7 % on average in the picture, and up to about 40 % on some shapes with sprites on:
 * real durations follow the access slots, not a straight line.
 *
 * Determinism (native code and the reference interpreter must agree state for state): the engine moves only inside
 * msx_v9938_cmd_sync(m, cycle), which runs every unit whose tick (6 per machine cycle) is at or before the cycle, with the
 * VRAM, registers, screen mode and cost class of that moment. Every event that can change what a unit sees or that can
 * observe the engine syncs first: CPU VRAM accesses, status reads, command-register writes, writes to R#0, R#1, R#8, R#9,
 * each draw point and each line boundary. Adding or removing a sync therefore never changes the result. */
#include "msx_machine.h"

#include <string.h>

enum { TR = 0x80, BD = 0x10, CE = 0x01 };
enum { ARG_MAJ = 1, ARG_EQ = 2, ARG_DIX = 4, ARG_DIY = 8, ARG_MXS = 16, ARG_MXD = 32 };
enum { MODE_NONE = 0xFF };
enum { TICKS = 6 };                            /* VDP ticks per machine cycle */

enum { C_STOP = 0, C_POINT = 4, C_PSET = 5, C_SRCH = 6, C_LINE = 7, C_LMMV = 8, C_LMMM = 9, C_LMCM = 10, C_LMMC = 11,
       C_HMMV = 12, C_HMMM = 13, C_YMMM = 14, C_HMMC = 15 };

/* Start delay, cost per unit in classes 0-2, cost at a line end (VDP ticks; measured averages, see above). */
static const uint16_t START[16] = { 0, 0, 0, 0, 66, 117, 99, 141, 117, 123, 66, 0, 117, 126, 126, 0 };
static const uint16_t COST[16][3] = {
    { 0, 0, 0 }, { 0, 0, 0 }, { 0, 0, 0 }, { 0, 0, 0 }, { 0, 0, 0 }, { 0, 0, 0 },
    { 91, 98, 124 },                           /* SRCH */
    { 114, 125, 137 },                         /* LINE */
    { 98, 125, 138 },                          /* LMMV */
    { 130, 133, 196 },                         /* LMMM */
    { 0, 0, 0 }, { 0, 0, 0 },                  /* LMCM, LMMC: paced by the CPU */
    { 49, 62, 65 },                            /* HMMV */
    { 91, 97, 137 },                           /* HMMM */
    { 65, 68, 125 },                           /* YMMM */
    { 0, 0, 0 },                               /* HMMC: paced by the CPU */
};
static const uint16_t LINE_END[16] = { 0, 0, 0, 0, 0, 0, 0, 0, 64, 59, 0, 0, 56, 65, 64, 0 };
enum { LINE_MINOR_STEP = 33 };

/* ---- geometry: 0 G4, 1 G5, 2 G6, 3 G7 ---- */
static const uint16_t WIDTH[4] = { 256, 512, 512, 256 };
static const uint8_t BYTE_SHIFT[4] = { 1, 2, 1, 0 };      /* dots per byte = 1 << shift */
static const uint8_t DOT_MASK[4] = { 0x0F, 0x03, 0x0F, 0xFF };

static uint8_t mode_of(const MsxV9938 *v)
{
    int mode = ((v->reg[0] & 0x0E) << 1) | ((v->reg[1] >> 2) & 2) | ((v->reg[1] >> 4) & 1);
    switch (mode) {
    case 0x0C: return 0;
    case 0x10: return 1;
    case 0x14: return 2;
    case 0x1C: return 3;
    default: return MODE_NONE;
    }
}

/* The physical cell of a dot or byte: the logical address of the mode, through the G6/G7 interleave. */
static uint32_t address(int mode, unsigned x, unsigned y)
{
    switch (mode) {
    case 0: return ((uint32_t)(y & 1023) << 7) | ((x & 255) >> 1);
    case 1: return ((uint32_t)(y & 1023) << 7) | ((x & 511) >> 2);
    case 2: return msx_v9938_physical(((uint32_t)(y & 511) << 8) | ((x & 511) >> 1), 1);
    default: return msx_v9938_physical(((uint32_t)(y & 511) << 8) | (x & 255), 1);
    }
}

static unsigned dot_shift(int mode, unsigned x)
{
    switch (mode) {
    case 0: case 2: return (~x & 1) * 4;
    case 1: return (~x & 3) * 2;
    default: return 0;
    }
}

static uint8_t dot_read(MsxV9938 *v, int mode, unsigned x, unsigned y, int absent)
{
    if (absent)
        return DOT_MASK[mode];                 /* expansion RAM: not fitted, reads FFh */
    return (uint8_t)((v->vram[address(mode, x, y)] >> dot_shift(mode, x)) & DOT_MASK[mode]);
}

static void dot_write(MsxV9938 *v, int mode, unsigned x, unsigned y, uint8_t value, int absent)
{
    if (absent)
        return;
    uint32_t at = address(mode, x, y);
    unsigned shift = dot_shift(mode, x);
    uint8_t mask = (uint8_t)(DOT_MASK[mode] << shift);
    v->vram[at] = (uint8_t)((v->vram[at] & ~mask) | ((value << shift) & mask));
}

/* The logical operation (low nibble of R#46) of source S on destination D, both masked to a dot. */
static uint8_t apply(int op, uint8_t s, uint8_t d, uint8_t mask)
{
    if ((op & 8) && !s)
        return d;                              /* the T operations leave the destination where the source is 0 */
    switch (op & 7) {
    case 0: return s;
    case 1: return (uint8_t)(s & d);
    case 2: return (uint8_t)(s | d);
    case 3: return (uint8_t)(s ^ d);
    case 4: return (uint8_t)(~s & mask);
    default: return d;                         /* 5-7: nothing written */
    }
}

/* ---- registers ---- */

static void mirror(MsxV9938 *v)
{
    MsxV9938Cmd *c = &v->cmd;
    const uint16_t words[6] = { c->sx, c->sy, c->dx, c->dy, c->nx, c->ny };
    for (int i = 0; i < 6; ++i) {
        v->reg[32 + 2 * i] = (uint8_t)(words[i] & 0xFF);
        v->reg[33 + 2 * i] = (uint8_t)(words[i] >> 8);
    }
    v->reg[44] = c->col;
    v->reg[45] = c->arg;
    v->reg[46] = c->cmd;
}

void msx_v9938_cmd_reset(MsxMachine *m)
{
    MsxV9938 *v = m->v9938;
    memset(&v->cmd, 0, sizeof v->cmd);
    v->cmd.mode = mode_of(v);
    mirror(v);
}

/* ---- clipping: units in the current line, recomputed from the live registers ---- */

static int command(const MsxV9938Cmd *c) { return c->cmd >> 4; }
static int byte_command(int n) { return n >= C_HMMV; }

static unsigned line_units(const MsxV9938Cmd *c)
{
    int n = command(c), mode = c->mode;
    unsigned w = WIDTH[mode], left = (c->arg & ARG_DIX) != 0;
    unsigned shift = byte_command(n) ? BYTE_SHIFT[mode] : 0;
    unsigned limit = w >> shift;               /* dots, or bytes, in a line */
    unsigned nx = n == C_YMMM ? 512u >> shift : (c->nx & 1023) >> shift;
    if (!nx)
        nx = limit;
    unsigned x1, x2;
    int two = n == C_LMMM || n == C_HMMM;
    if (n == C_LMCM) x1 = x2 = c->sx;
    else if (two) { x1 = c->sx; x2 = c->dx; }
    else x1 = x2 = c->dx;
    if (x1 >= w || x2 >= w)
        return 1;                              /* a start outside the line: one unit a line */
    unsigned room = left ? ((x1 < x2 ? x1 : x2) >> shift) + 1 : limit - ((x1 > x2 ? x1 : x2) >> shift);
    return nx < room ? nx : room;
}

/* The line ends: the coordinates step, NY counts down; returns 1 when the block is done. */
static int line_end(MsxV9938Cmd *c, int source, int destination)
{
    int up = (c->arg & ARG_DIY) != 0, n = command(c);
    unsigned top = 1024;
    if (source && destination) top = c->sy < c->dy ? c->sy : c->dy;
    else if (source) top = c->sy;
    else top = c->dy;
    if (n == C_YMMM) top = c->sy < c->dy ? c->sy : c->dy;
    if (source) c->sy = (uint16_t)((c->sy + (up ? 1023 : 1)) & 1023);
    if (destination) c->dy = (uint16_t)((c->dy + (up ? 1023 : 1)) & 1023);
    c->ny = (uint16_t)((c->ny + 1023) & 1023);
    c->asx = n == C_LMCM || n == C_LMMM || n == C_HMMM ? c->sx : c->asx;
    c->adx = c->dx;
    c->anx = (uint16_t)line_units(c);
    return c->ny == 0 || (up && top == 0);
}

/* ---- one unit of the running command; returns 1 when the unit ended a line (for the line-end cost) ---- */

static void finish(MsxV9938 *v)
{
    v->cmd.cmd = 0;
    v->cmd.status &= (uint8_t)~CE;
}

static int unit(MsxV9938 *v, int *minor_step)
{
    MsxV9938Cmd *c = &v->cmd;
    int n = command(c), mode = c->mode, op = c->cmd & 15;
    unsigned w = WIDTH[mode];
    int left = (c->arg & ARG_DIX) != 0, up = (c->arg & ARG_DIY) != 0;
    int mxs = (c->arg & ARG_MXS) != 0, mxd = (c->arg & ARG_MXD) != 0;
    uint8_t mask = DOT_MASK[mode];
    unsigned step = byte_command(n) ? 1u << BYTE_SHIFT[mode] : 1u;
    unsigned tx = left ? 1024 - step : step;
    *minor_step = 0;
    switch (n) {
    case C_POINT:                              /* absent expansion RAM reads FFh, not masked to a dot */
        c->col = mxs ? 0xFF : dot_read(v, mode, c->sx, c->sy, 0);
        finish(v);
        return 0;
    case C_PSET:
        dot_write(v, mode, c->dx, c->dy, apply(op, c->col & mask, dot_read(v, mode, c->dx, c->dy, 0), mask), mxd);
        finish(v);
        return 0;
    case C_SRCH: {
        uint8_t p = mxs ? 0xFF : dot_read(v, mode, c->asx, c->sy, 0);   /* FFh never equals a masked colour */
        int equal = p == (c->col & mask);
        if ((c->arg & ARG_EQ) ? !equal : equal) {
            c->status |= BD;
            finish(v);
            return 0;
        }
        c->asx = (uint16_t)((c->asx + tx) & 1023);
        if (c->asx & w)
            finish(v);                         /* ran off the line: done, BD untouched */
        return 0;
    }
    case C_LINE: {
        uint8_t d = dot_read(v, mode, c->adx, c->dy, 0);
        dot_write(v, mode, c->adx, c->dy, apply(op, c->col & mask, d, mask), mxd);
        unsigned ty = up ? 1023u : 1u;
        if (!(c->arg & ARG_MAJ)) {             /* X is the long side */
            c->adx = (uint16_t)((c->adx + tx) & 1023);
            if (c->anx++ == (c->nx & 1023) || (c->adx & w)) { finish(v); return 0; }
            if (c->asx < c->ny) {
                c->asx = (uint16_t)(c->asx + c->nx);
                if (up && c->dy == 0) { c->dy = 1023; finish(v); return 0; }
                c->dy = (uint16_t)((c->dy + ty) & 1023);
                *minor_step = 1;
            }
            c->asx = (uint16_t)((c->asx - c->ny) & 1023);
        } else {                               /* Y is the long side */
            if (up && c->dy == 0) { c->dy = 1023; finish(v); return 0; }
            c->dy = (uint16_t)((c->dy + ty) & 1023);
            if (c->asx < c->ny) {
                c->asx = (uint16_t)(c->asx + c->nx);
                c->adx = (uint16_t)((c->adx + tx) & 1023);
                *minor_step = 1;
            }
            c->asx = (uint16_t)((c->asx - c->ny) & 1023);
            if (c->anx++ == (c->nx & 1023) || (c->adx & w)) { finish(v); return 0; }
        }
        return 0;
    }
    default:
        break;
    }
    /* Block commands. */
    int source = n == C_LMMM || n == C_LMCM || n == C_HMMM || n == C_YMMM;
    int destination = n != C_LMCM;
    switch (n) {
    case C_LMMV: case C_LMMC: {
        uint8_t d = dot_read(v, mode, c->adx, c->dy, 0);
        dot_write(v, mode, c->adx, c->dy, apply(op, c->col & mask, d, mask), mxd);
        break;
    }
    case C_LMMM: {
        uint8_t s = dot_read(v, mode, c->asx, c->sy, mxs);
        uint8_t d = dot_read(v, mode, c->adx, c->dy, 0);
        dot_write(v, mode, c->adx, c->dy, apply(op, s, d, mask), mxd);
        break;
    }
    case C_LMCM:
        c->col = mxs ? 0xFF : dot_read(v, mode, c->asx, c->sy, 0);
        c->status |= TR;
        break;
    case C_HMMV: case C_HMMC:
        if (!mxd) v->vram[address(mode, c->adx, c->dy)] = c->col;
        break;
    case C_HMMM: {
        uint8_t s = mxs ? 0xFF : v->vram[address(mode, c->asx, c->sy)];
        if (!mxd) v->vram[address(mode, c->adx, c->dy)] = s;
        break;
    }
    case C_YMMM: {                             /* both sides at the destination's X; MXD names the memory of both */
        uint8_t s = mxd ? 0xFF : v->vram[address(mode, c->adx, c->sy)];
        if (!mxd) v->vram[address(mode, c->adx, c->dy)] = s;
        break;
    }
    default:
        break;
    }
    c->asx = (uint16_t)((c->asx + tx) & 1023);
    c->adx = (uint16_t)((c->adx + tx) & 1023);
    if (c->anx > 1) {
        --c->anx;
        return 0;
    }
    if (line_end(c, source, destination))
        finish(v);
    return 1;
}

/* ---- starting a command (a write to R#46) ---- */

static void start(MsxMachine *m)
{
    MsxV9938 *v = m->v9938;
    MsxV9938Cmd *c = &v->cmd;
    int n = command(c);
    if (c->mode == MODE_NONE || n < C_POINT) { /* STOP, or no bitmap screen: nothing runs */
        finish(v);
        return;
    }
    c->ny &= 1023;
    c->status |= CE;
    ++c->started[n];
    c->asx = n == C_LINE ? (uint16_t)(((c->nx - 1) >> 1) & 1023) : c->sx;
    c->adx = c->dx;
    c->anx = n == C_LINE ? 0 : (uint16_t)line_units(c);
    c->next = TICKS * m->cycles + START[n];
    if (n == C_LMCM) {
        c->status |= TR;
        c->transfer = 1;                       /* the first dot is still to fetch */
    } else if (n == C_HMMC || n == C_LMMC) {
        c->status |= TR;
        if (c->transfer) {                     /* the R#44 written with the registers is the first byte or dot */
            int minor;
            c->transfer = 0;
            unit(v, &minor);
        }
    }
}

/* ---- the cost class of the current moment ---- */

static int cost_class(const MsxMachine *m)
{
    const MsxV9938 *v = m->v9938;
    if (!(v->reg[1] & 0x40) || m->line >= m->vblank_line)
        return 0;
    return (v->reg[8] & 0x02) ? 1 : 2;
}

void msx_v9938_cmd_sync(MsxMachine *m, uint64_t cycle)
{
    MsxV9938 *v = m->v9938;
    MsxV9938Cmd *c = &v->cmd;
    if (!(c->status & CE))
        return;
    int n = command(c);
    uint64_t now = TICKS * cycle;
    if (n == C_LMCM) {                         /* the first dot comes after the start delay; later ones on S#7 reads */
        if (c->transfer && c->next <= now) {
            int minor;
            c->transfer = 0;
            unit(v, &minor);
            mirror(v);
        }
        return;
    }
    if (n == C_HMMC || n == C_LMMC)
        return;                                /* paced by the CPU's R#44 writes */
    int class = cost_class(m);
    while ((c->status & CE) && c->next <= now) {
        int minor;
        int ended = unit(v, &minor);
        c->next += COST[n][class] + (ended ? LINE_END[n] : 0) + (minor ? LINE_MINOR_STEP : 0);
    }
    mirror(v);
}

void msx_v9938_cmd_line(MsxMachine *m)
{
    MsxV9938 *v = m->v9938;
    v->cmd.mode = mode_of(v);
    if (v->cmd.mode == MODE_NONE && (v->cmd.status & CE)) {
        finish(v);                             /* the screen left the bitmap modes: the command is abandoned */
        mirror(v);
    }
}

void msx_v9938_cmd_write(MsxMachine *m, int index, uint8_t value)
{
    MsxV9938 *v = m->v9938;
    MsxV9938Cmd *c = &v->cmd;
    if (index < 0 || index > 14)
        return;
    msx_v9938_cmd_sync(m, m->cycles);
    switch (index) {
    case 0: c->sx = (uint16_t)((c->sx & 0x100) | value); break;
    case 1: c->sx = (uint16_t)((c->sx & 0xFF) | ((value & 1) << 8)); break;
    case 2: c->sy = (uint16_t)((c->sy & 0x300) | value); break;
    case 3: c->sy = (uint16_t)((c->sy & 0xFF) | ((value & 3) << 8)); break;
    case 4: c->dx = (uint16_t)((c->dx & 0x100) | value); break;
    case 5: c->dx = (uint16_t)((c->dx & 0xFF) | ((value & 1) << 8)); break;
    case 6: c->dy = (uint16_t)((c->dy & 0x300) | value); break;
    case 7: c->dy = (uint16_t)((c->dy & 0xFF) | ((value & 3) << 8)); break;
    case 8: c->nx = (uint16_t)((c->nx & 0x300) | value); break;
    case 9: c->nx = (uint16_t)((c->nx & 0xFF) | ((value & 3) << 8)); break;
    case 10: c->ny = (uint16_t)((c->ny & 0x300) | value); break;
    case 11: c->ny = (uint16_t)((c->ny & 0xFF) | ((value & 3) << 8)); break;
    case 12: {                                 /* the colour; for HMMC and LMMC, the next byte or dot */
        int n = command(c);
        if (!c->cmd)
            c->status &= (uint8_t)~TR;         /* tested before the unit: the last byte of an HMMC leaves TR set */
        c->col = value;
        c->transfer = 1;
        if ((c->status & CE) && (n == C_HMMC || n == C_LMMC)) {
            int minor;
            c->transfer = 0;
            unit(v, &minor);
        }
        break;
    }
    case 13: c->arg = value; break;
    default:
        ++c->writes;
        c->cmd = value;
        start(m);
        break;
    }
    mirror(v);
}

uint8_t msx_v9938_cmd_status(MsxMachine *m)
{
    msx_v9938_cmd_sync(m, m->cycles);
    return (uint8_t)(m->v9938->cmd.status & (TR | BD | CE));
}

uint8_t msx_v9938_cmd_read_colour(MsxMachine *m)
{
    MsxV9938 *v = m->v9938;
    MsxV9938Cmd *c = &v->cmd;
    msx_v9938_cmd_sync(m, m->cycles);
    uint8_t value = c->col;
    if (!c->cmd) {
        c->status &= (uint8_t)~TR;
        c->transfer = 1;
    } else if (command(c) == C_LMCM && !c->transfer) {
        int minor;
        unit(v, &minor);                       /* the dot just taken makes room for the next one */
    }
    mirror(v);
    return value;
}

uint16_t msx_v9938_cmd_border_x(MsxMachine *m, int clear)
{
    MsxV9938Cmd *c = &m->v9938->cmd;
    msx_v9938_cmd_sync(m, m->cycles);
    uint16_t value = c->asx;
    if (clear)
        c->status &= (uint8_t)~BD;             /* a read of S#9 clears BD */
    return value;
}

void msx_v9938_cmd_print(const MsxMachine *m, FILE *out)
{
    const MsxV9938Cmd *c = &m->v9938->cmd;
    fprintf(out, "[%u, %u, %u, %u, %u, %u, %llu, %llu", c->status, c->transfer, c->mode, c->asx, c->adx, c->anx,
            (unsigned long long)c->next, (unsigned long long)c->writes);
    for (int i = 0; i < 16; ++i) fprintf(out, ", %llu", (unsigned long long)c->started[i]);
    fprintf(out, "]");
}
