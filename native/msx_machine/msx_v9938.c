/* The V9938 of the MSX2: ports, registers, status, palette, the VRAM pointer and the line events. MIT, Retro-Recomp.
 *
 * Written from the V9938 Technical Data Book and the MSX2 Technical Handbook; behaviour the books leave open was
 * checked against openMSX 22.0 run as a separate program (private comparisons; none of its code or tables is here). The picture is drawn in msx_v9938_draw.c, the
 * command engine runs in msx_v9938_cmd.c (synced before every event that can see it or change what it sees).
 *
 * Time: two events per line of 228 machine cycles. The line boundary (the start of the left border) moves the line
 * counter, raises F at the first line after the picture and wraps the frame; the draw point, MSX2_DRAW_AT cycles later
 * (the start of the right border), draws the line with the registers, palette and VRAM of that instant, evaluates its
 * sprites and raises FH when the line matches R#19. A register written in the horizontal blank takes effect on the next
 * line; inside the displayed part of a line it acts on the whole line (line granularity).
 *
 * Not modelled (docs/MSX.md): the access-slot timing of port 98h, the F and FH "lost" windows, the frame-length change
 * when R#9 LN switches between 192 and 212 lines, mid-line effects, interlace's half-line field offset, the
 * superimpose and digitise bits, the expansion RAM (R#45 bit 6: reads FFh, writes dropped). */
#include "msx_machine.h"

#include <string.h>

/* Bits each register keeps (R#0-R#23). */
static const uint8_t reg_masks[24] = {
    0x7E, 0x7F, 0x7F, 0xFF, 0x3F, 0xFF, 0x3F, 0xFF,
    0xFB, 0xBF, 0x07, 0x03, 0xFF, 0xFF, 0x07, 0x0F,
    0x0F, 0xBF, 0xFF, 0xFF, 0x3F, 0x3F, 0x3F, 0xFF,
};

/* The colours after a reset (V9938 Technical Data Book, appendix: the initial palette), 0GGG0RRR0BBB. */
static const uint16_t reset_palette[16] = {
    0x000, 0x000, 0x611, 0x733, 0x117, 0x327, 0x151, 0x627,
    0x171, 0x373, 0x661, 0x664, 0x411, 0x265, 0x555, 0x777,
};

void msx_v9938_reset(MsxMachine *m)
{
    MsxV9938 *v = m->v9938;
    memset(v->reg, 0, sizeof v->reg);
    v->status0 = v->status1 = 0;
    v->status2 = 0x0C;
    v->pointer = 0;
    v->latch = v->first = v->readahead = 0;
    v->pal_latch = v->pal_first = 0;
    memcpy(v->palette, reset_palette, sizeof v->palette);
    v->collision_x = v->collision_y = 0;
    v->blink_on = v->blink_count = 0;
    v->lines_latched = 192;
    v->adjust_h = v->adjust_v = 0;
    memset(v->line_adjust, 0, sizeof v->line_adjust);
    msx_v9938_cmd_reset(m);
    m->lines_per_frame = MSX_LINES_NTSC;              /* R#9 is 0 after a reset: 60 Hz until the BIOS sets PAL */
    m->vblank_line = 192;
}

/* The physical cell the CPU port reaches: the logical address (R#14, the pointer) through the layout of the screen latched
 * at the last line boundary (the engine's too): a switch between G4/G5 and G6/G7 takes effect at the next line. */
static uint32_t vram_address(const MsxV9938 *v)
{
    int interleaved = v->cmd.mode == 2 || v->cmd.mode == 3;
    return msx_v9938_physical(((uint32_t)(v->reg[14] & 7) << 14) | v->pointer, interleaved);
}

/* After an access: the pointer counts in 16 KB; in the modes of the V9938 (M4 or M5 set) its carry moves R#14. */
static void step_pointer(MsxV9938 *v)
{
    v->pointer = (uint16_t)((v->pointer + 1) & 0x3FFF);
    if (v->pointer == 0 && (v->reg[0] & 0x0C))
        v->reg[14] = (uint8_t)((v->reg[14] + 1) & 7);
}

static uint8_t read_data(MsxMachine *m)
{
    MsxV9938 *v = m->v9938;
    msx_v9938_cmd_sync(m, m->cycles);
    uint8_t value = v->readahead;
    v->readahead = (v->reg[45] & 0x40) ? 0xFF : v->vram[vram_address(v)];
    step_pointer(v);
    return value;
}

static void write_data(MsxMachine *m, uint8_t value)
{
    MsxV9938 *v = m->v9938;
    msx_v9938_cmd_sync(m, m->cycles);
    if (!(v->reg[45] & 0x40))
        v->vram[vram_address(v)] = value;
    v->readahead = value;
    step_pointer(v);
}

/* The cycle inside the current line, 0 at the line boundary. */
static unsigned line_cycle(const MsxMachine *m)
{
    uint64_t start = m->next_line - MSX_CYCLES_PER_LINE;
    return m->cycles >= start ? (unsigned)(m->cycles - start) : 0;
}

/* The line R#19 asks for, in display lines from line 0: (R#19 - R#23) mod 256. */
static unsigned line_irq_line(const MsxV9938 *v)
{
    return (unsigned)((v->reg[19] - v->reg[23]) & 0xFF);
}

/* The last line a line interrupt can match before the counter resets (the lines between the picture's start and the
 * next frame's: 17 at 60 Hz, 44 at 50 Hz, ten more with 192 lines; the data book's section on R#19). */
static int line_irq_possible(const MsxMachine *m, unsigned line)
{
    unsigned to_display = (m->lines_per_frame == MSX_LINES_PAL ? 44u : 17u) + (m->v9938->lines_latched == 192 ? 10u : 0u);
    return line < m->lines_per_frame - to_display;
}

static uint8_t read_status(MsxMachine *m)
{
    MsxV9938 *v = m->v9938;
    unsigned index = v->reg[15] & 0x0F;
    uint8_t value;
    switch (index) {
    case 0:
        value = v->status0;
        v->status0 &= 0x1F;                    /* F, the ninth-sprite flag and the collision flag clear on a read */
        break;
    case 1:
        if (v->reg[0] & 0x10) {                /* line interrupt enabled: FH is a latch, cleared by this read */
            value = v->status1 & 1;
            v->status1 &= (uint8_t)~1;
        } else {                               /* disabled: FH is live, from the match line's draw point to its end */
            value = (m->line == line_irq_line(v) && line_cycle(m) >= MSX2_DRAW_AT) ? 1 : 0;
        }
        break;                                 /* ID bits 1-5: 0 (V9938); light pen bits: 0 */
    case 2: {
        msx_v9938_cmd_sync(m, m->cycles);
        unsigned c = line_cycle(m);
        int hr = !(c >= 9 && c < MSX2_DRAW_AT);
        int vr = m->line >= m->vblank_line && m->line + 1 < m->lines_per_frame;
        value = (uint8_t)((v->status2 & 0x02) | 0x0C | (hr ? 0x20 : 0) | (vr ? 0x40 : 0) | msx_v9938_cmd_status(m));
        break;
    }
    case 3: value = (uint8_t)(v->collision_x & 0xFF); break;
    case 4: value = (uint8_t)(0xFE | ((v->collision_x >> 8) & 1)); break;
    case 5:
        value = (uint8_t)(v->collision_y & 0xFF);
        v->collision_x = v->collision_y = 0;   /* a read of S#5 clears the coordinates */
        break;
    case 6: value = (uint8_t)(0xFC | ((v->collision_y >> 8) & 3)); break;
    case 7: value = msx_v9938_cmd_read_colour(m); break;
    case 8: value = (uint8_t)(msx_v9938_cmd_border_x(m, 0) & 0xFF); break;
    case 9: value = (uint8_t)(0xFE | ((msx_v9938_cmd_border_x(m, 1) >> 8) & 1)); break;
    default: value = 0xFF; break;
    }
    return value;
}

static void write_register(MsxMachine *m, unsigned index, uint8_t value)
{
    MsxV9938 *v = m->v9938;
    if (index >= 32 && index <= 46) {
        msx_v9938_cmd_write(m, (int)index - 32, value);
        return;
    }
    if (index >= 24)
        return;                                /* R#24-R#31 and R#47-R#63 do not exist */
    value &= reg_masks[index];
    if (index == 0 || index == 1 || index == 8 || index == 9)
        msx_v9938_cmd_sync(m, m->cycles);      /* the engine's screen and cost class come from these */
    uint8_t old = v->reg[index];
    v->reg[index] = value;
    switch (index) {
    case 0:
        if ((old & 0x10) && !(value & 0x10))
            v->status1 &= (uint8_t)~1;         /* line interrupt disabled: its pending flag goes */
        break;
    case 13:                                   /* writing R#13 restarts blinking, even with the same value */
        v->blink_on = (value & 0xF0) != 0;
        v->blink_count = ((value & 0xF0) && (value & 0x0F)) ? (uint8_t)((value >> 4) * 10) : 0;
        break;
    case 16:
        v->pal_latch = 0;                      /* a half-written palette entry is abandoned */
        break;
    default:
        break;
    }
}

static void write_control(MsxMachine *m, uint8_t value)
{
    MsxV9938 *v = m->v9938;
    if (!v->latch) {
        v->first = value;
        v->latch = 1;
        return;
    }
    v->latch = 0;
    if (value & 0x80) {
        if (!(value & 0x40))
            write_register(m, value & 0x3F, v->first);
        return;                                /* bits 7 and 6 both set: ignored */
    }
    v->pointer = (uint16_t)(((value & 0x3F) << 8) | v->first);
    if (!(value & 0x40)) {                     /* read setup: the VDP prefetches the first byte */
        msx_v9938_cmd_sync(m, m->cycles);
        v->readahead = (v->reg[45] & 0x40) ? 0xFF : v->vram[vram_address(v)];
        step_pointer(v);
    }
}

static void write_palette(MsxV9938 *v, uint8_t value)
{
    if (!v->pal_latch) {
        v->pal_first = value;
        v->pal_latch = 1;
        return;
    }
    v->pal_latch = 0;
    v->palette[v->reg[16] & 0x0F] = (uint16_t)(((value << 8) | v->pal_first) & 0x777);
    v->reg[16] = (uint8_t)((v->reg[16] + 1) & 0x0F);
}

uint8_t msx_v9938_in(MsxMachine *m, uint8_t port)
{
    MsxV9938 *v = m->v9938;
    switch (port) {
    case 0x98: v->latch = 0; return read_data(m);   /* a read of 98h or 99h abandons a half-written 99h pair */
    case 0x99: v->latch = 0; return read_status(m);
    default: return 0xFF;                      /* 9Ah and 9Bh are write-only: a read does not reach the VDP */
    }
}

void msx_v9938_out(MsxMachine *m, uint8_t port, uint8_t value)
{
    MsxV9938 *v = m->v9938;
    switch (port) {
    case 0x98:
        v->latch = 0;
        write_data(m, value);
        break;
    case 0x99:
        write_control(m, value);
        break;
    case 0x9A:
        write_palette(v, value);
        break;
    default: {                                 /* 9Bh: the register R#17 points at, then R#17 moves on unless bit 7 */
        uint8_t pointer = v->reg[17], target = pointer & 0x3F;
        write_register(m, target, value);
        if (!(pointer & 0x80))
            v->reg[17] = (uint8_t)((target + 1) & 0x3F);
        break;
    }
    }
}

int msx_v9938_irq(const MsxMachine *m)
{
    const MsxV9938 *v = m->v9938;
    return ((v->status0 & 0x80) && (v->reg[1] & 0x20)) || ((v->status1 & 1) && (v->reg[0] & 0x10));
}

/* The frame starts: what the V9938 takes once per frame: the standard (R#9 bit 1), the
 * picture height (R#9 bit 7), the adjust (R#18), the even/odd field, the blink counter. */
static void frame_start(MsxMachine *m)
{
    MsxV9938 *v = m->v9938;
    v->status2 ^= 0x02;
    m->lines_per_frame = (v->reg[9] & 0x02) ? MSX_LINES_PAL : MSX_LINES_NTSC;
    v->lines_latched = (v->reg[9] & 0x80) ? 212 : 192;
    v->adjust_v = (int8_t)((((v->reg[18] >> 4) & 0x0F) ^ 7) - 7);
    if (v->blink_count) {
        if (--v->blink_count == 0) {
            v->blink_on = !v->blink_on;
            v->blink_count = (uint8_t)((v->blink_on ? v->reg[13] >> 4 : v->reg[13] & 0x0F) * 10);
        }
    }
}

static void fold_trace(MsxMachine *m)
{
    const MsxV9938 *v = m->v9938;
    uint32_t h = m->frame_trace ^ 2166136261u;
    const uint8_t *p = (const uint8_t *)v->frame;
    for (size_t i = 0; i < sizeof v->frame; ++i) h = (h ^ p[i]) * 16777619u;
    p = (const uint8_t *)v->border;
    for (size_t i = 0; i < sizeof v->border; ++i) h = (h ^ p[i]) * 16777619u;
    p = (const uint8_t *)v->line_adjust;
    for (size_t i = 0; i < sizeof v->line_adjust; ++i) h = (h ^ p[i]) * 16777619u;
    for (int i = 0; i < 24; ++i) h = (h ^ v->reg[i]) * 16777619u;
    for (int i = 32; i < 47; ++i) h = (h ^ v->reg[i]) * 16777619u;
    h = (h ^ v->cmd.status) * 16777619u;
    p = (const uint8_t *)v->palette;
    for (size_t i = 0; i < sizeof v->palette; ++i) h = (h ^ p[i]) * 16777619u;
    m->frame_trace = (h ^ v->status0) * 16777619u;
}

/* The draw point of line `line`: the picture line, its sprites, the line interrupt. */
static void draw_point(MsxMachine *m, unsigned line)
{
    MsxV9938 *v = m->v9938;
    if (line < v->lines_latched && line < MSX2_LINES)
        msx_v9938_draw_line(m, (int)line);
    if ((v->reg[0] & 0x10) && line == line_irq_line(v) && line_irq_possible(m, line))
        v->status1 |= 1;
}

/* The line boundary: the counter moves; F at the first line after the picture; the frame wraps. */
static void line_boundary(MsxMachine *m)
{
    MsxV9938 *v = m->v9938;
    ++m->line;
    m->vblank_line = (v->reg[9] & 0x80) ? 212 : 192;   /* R#9 LN as it is at this line */
    if (m->line == m->vblank_line)
        v->status0 |= 0x80;
    if (m->line >= m->lines_per_frame) {
        m->line = 0;
        ++m->frames;
        if (m->trace_frames)
            fold_trace(m);
        frame_start(m);
    }
    v->adjust_h = (int8_t)(((v->reg[18] & 0x0F) ^ 7) - 7);   /* R#18 written during the last line applies from this one */
    if (m->line_hook)
        m->line_hook();
}

void msx_v9938_advance(MsxMachine *m)
{
    for (;;) {
        if (m->next_draw <= m->next_line) {
            if (m->cycles < m->next_draw)
                break;
            uint64_t at = m->next_draw;
            m->next_draw += MSX_CYCLES_PER_LINE;
            msx_v9938_cmd_sync(m, at);
            draw_point(m, m->line);
        } else {
            if (m->cycles < m->next_line)
                break;
            uint64_t at = m->next_line;
            m->next_line += MSX_CYCLES_PER_LINE;
            msx_v9938_cmd_sync(m, at);         /* the engine reaches the boundary with the line's cost class */
            line_boundary(m);
            msx_v9938_cmd_line(m);
        }
    }
}

void msx_v9938_print(const MsxMachine *m, FILE *out)
{
    const MsxV9938 *v = m->v9938;
    fprintf(out, "{\"reg\": [");
    for (int i = 0; i < 24; ++i) fprintf(out, "%s%u", i ? ", " : "", v->reg[i]);
    fprintf(out, "], \"cmd\": [");
    for (int i = 0; i < 15; ++i) fprintf(out, "%s%u", i ? ", " : "", v->reg[32 + i]);
    fprintf(out, "], \"engine\": ");
    msx_v9938_cmd_print(m, out);
    fprintf(out, ", \"status\": [%u, %u, %u], \"pointer\": %u, \"palette\": [", v->status0, v->status1, v->status2,
            v->pointer);
    for (int i = 0; i < 16; ++i) fprintf(out, "%s%u", i ? ", " : "", v->palette[i]);
    fprintf(out, "], \"collision\": [%u, %u], \"blink\": [%u, %u], \"lines\": %u, \"lines_per_frame\": %u, "
            "\"cmd_writes\": %llu}", v->collision_x, v->collision_y, v->blink_on, v->blink_count, v->lines_latched,
            m->lines_per_frame, (unsigned long long)v->cmd.writes);
}
