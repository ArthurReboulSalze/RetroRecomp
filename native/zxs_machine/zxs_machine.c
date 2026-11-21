/* The ZX Spectrum machine (zxs_machine.h). MIT, Retro-Recomp. */
#include "zxs_machine.h"

#include <string.h>

enum { AY_TICK = 16 };      /* the AY runs at the CPU clock / 2 and ticks every 8 of its clocks */

/* The image the converter writes (retrorecomp/zxs_build.py, zxs_image), little-endian:
 *   0 "ZXS1"; 4 model (0 48K, 1 128K); 5 a 16K; 6 joystick (0 cursor, 1 Kempston, 2/3 Sinclair, FFh none); 7 border;
 *   8 port 7FFDh; 9 the AY's latch; 10-25 its registers; 26 IM; 27 IFF1; 28 IFF2; 29 I; 30 R; 31 0;
 *   32-55 AF BC DE HL AF' BC' DE' HL' IX IY SP PC; 56-59 the T-state within the frame; 60-63 0;
 *   then RAM banks 0 to 7, 16 KiB each. */
static uint16_t le16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }

void zxs_reset(ZxsMachine *m, int model, int ram16k, const uint8_t *rom)
{
    m->model = model;
    m->ram16k = model == ZXS_48K && ram16k;
    m->rom = rom;
    m->port_7ffd = 0;
    m->border = 7; m->out_fe = 0;
    memset(m->keys, 0xFF, sizeof m->keys);
    m->kempston = 0;
    m->ay_latch = 0; memset(m->ay_regs, 0, sizeof m->ay_regs);
    ay38910_reset(&m->ay);
    m->ay_next = AY_TICK; m->ay_level = 0;
    if (model == ZXS_128K) {
        m->t_line = 228; m->lines = 311; m->int_len = 36; m->top_line = 63; m->clock_hz = 3546900;
    } else {
        m->t_line = 224; m->lines = 312; m->int_len = 32; m->top_line = 64; m->clock_hz = 3500000;
    }
    m->t_frame = m->t_line * m->lines;
    m->cycles = 0; m->frame_start = 0; m->frames = 0; m->line = 0;
    m->frame_hook = NULL; m->hook_user = NULL; m->trace_frames = 0;
    memset(m->picture, 0, sizeof m->picture);
    m->frame_trace = 2166136261u;
    m->audio_time = 0;
    m->next_sample = (uint64_t)m->clock_hz * 65536u / ZXS_AUDIO_RATE;
    m->acc = 0; m->acc_cycles = 0; m->out_count = 0; m->dropped = 0;
}

int zxs_load_image(ZxsMachine *m, const uint8_t *image, size_t size, const uint8_t *rom, ZxsCpuStart *cpu)
{
    if (size != ZXS_IMAGE_BYTES || memcmp(image, "ZXS1", 4) || image[4] > ZXS_128K)
        return -1;
    zxs_reset(m, image[4], image[5], rom);
    m->kempston_present = image[6] == 1;
    m->border = image[7] & 7;
    m->out_fe = m->border;
    if (m->model == ZXS_128K)
        m->port_7ffd = image[8];
    m->ay_latch = image[9] & 15;
    memcpy(m->ay_regs, image + 10, 16);
    memcpy(m->ram, image + ZXS_IMAGE_HEADER, sizeof m->ram);
    cpu->im = image[26]; cpu->iff1 = image[27]; cpu->iff2 = image[28]; cpu->i = image[29]; cpu->r = image[30];
    uint16_t *regs[12] = {&cpu->af, &cpu->bc, &cpu->de, &cpu->hl, &cpu->af_, &cpu->bc_, &cpu->de_, &cpu->hl_,
                          &cpu->ix, &cpu->iy, &cpu->sp, &cpu->pc};
    for (int i = 0; i < 12; ++i)
        *regs[i] = le16(image + 32 + 2 * i);
    /* The frame position the snapshot was taken at (0 when the file does not say: the converter then gives the end of
     * the /INT pulse, so that a snapshot taken in its handler is not interrupted again at once). */
    uint32_t t = le32(image + 56) % m->t_frame;
    m->cycles = t;
    m->frame_start = 0;
    m->line = t / m->t_line;
    m->audio_time = t;
    m->ay_next = t + AY_TICK;
    m->next_sample = ((uint64_t)t << 16) + (uint64_t)m->clock_hz * 65536u / ZXS_AUDIO_RATE;
    return 0;
}

int zxs_bank_c000(const ZxsMachine *m) { return m->model == ZXS_128K ? (m->port_7ffd & 7) : 0; }
int zxs_rom_bank(const ZxsMachine *m) { return m->model == ZXS_128K ? ((m->port_7ffd >> 4) & 1) : 0; }

static int screen_bank(const ZxsMachine *m) { return m->model == ZXS_128K && (m->port_7ffd & 8) ? 7 : 5; }

uint8_t zxs_read(const ZxsMachine *m, uint16_t address)
{
    switch (address >> 14) {
    case 0: return m->rom[(size_t)zxs_rom_bank(m) << 14 | address];
    case 1: return m->ram[5][address & 0x3FFF];
    case 2: return m->ram16k ? 0xFF : m->ram[2][address & 0x3FFF];
    default: return m->ram16k ? 0xFF : m->ram[zxs_bank_c000(m)][address & 0x3FFF];
    }
}

void zxs_write(ZxsMachine *m, uint16_t address, uint8_t value)
{
    switch (address >> 14) {
    case 0: return;                                     /* the ROM */
    case 1: m->ram[5][address & 0x3FFF] = value; return;
    case 2: if (!m->ram16k) m->ram[2][address & 0x3FFF] = value; return;
    default: if (!m->ram16k) m->ram[zxs_bank_c000(m)][address & 0x3FFF] = value; return;
    }
}

/* ---- the sound: the beeper and, on the 128K, the AY ---- */
/* The beeper at a fixed level; the AY's three channels at equal weight, together at most AY_WEIGHT (our choice: the two are
 * mixed as a 128K's sound output adds them; the balance is not measured on a machine). */
enum { BEEP_LEVEL = 12000, AY_WEIGHT = 18000 };

static int beeper_level(const ZxsMachine *m) { return (m->out_fe & 0x10) ? BEEP_LEVEL : 0; }

/* The sound up to `cycle`: each output sample is the mean level over its interval (a box filter); the AY moves one tick every
 * AY_TICK cycles, its level held between two ticks. */
static void sound_to(ZxsMachine *m, uint64_t cycle)
{
    if (cycle <= m->audio_time)
        return;
    int beep = beeper_level(m);
    uint64_t step = (uint64_t)m->clock_hz * 65536u / ZXS_AUDIO_RATE;
    while (m->audio_time < cycle) {
        if (m->model == ZXS_128K && m->audio_time >= m->ay_next) {
            int levels[3];
            ay38910_tick(&m->ay, m->ay_regs, levels);
            m->ay_level = (int)(((int64_t)levels[0] + levels[1] + levels[2]) * AY_WEIGHT / (3 * 32767));
            m->ay_next += AY_TICK;
        }
        int level = beep + m->ay_level;
        uint64_t sample_end = (m->next_sample + 65535) >> 16;             /* the first cycle at or after the sample's end */
        uint64_t until = sample_end < cycle ? sample_end : cycle;
        if (m->model == ZXS_128K && m->ay_next < until)
            until = m->ay_next;
        if (until <= m->audio_time)
            until = m->audio_time + 1;
        uint64_t span = until - m->audio_time;
        m->acc += (int64_t)level * (int64_t)span;
        m->acc_cycles += span;
        m->audio_time = until;
        if ((m->audio_time << 16) >= m->next_sample) {
            int64_t mean = m->acc_cycles ? m->acc / (int64_t)m->acc_cycles : level;
            int16_t sample = (int16_t)(mean > 32767 ? 32767 : mean);
            if (m->out_count < ZXS_AUDIO_BUFFER)
                m->out[m->out_count++] = sample;
            else
                ++m->dropped;
            m->acc = 0; m->acc_cycles = 0;
            m->next_sample += step;
        }
    }
}

unsigned zxs_audio_take(ZxsMachine *m, int16_t *out, unsigned max)
{
    unsigned n = m->out_count < max ? m->out_count : max;
    memcpy(out, m->out, n * sizeof *out);
    memmove(m->out, m->out + n, (m->out_count - n) * sizeof *out);
    m->out_count -= n;
    return n;
}

/* ---- ports ---- */
uint8_t zxs_in(ZxsMachine *m, uint16_t port)
{
    if (!(port & 1)) {                                  /* the ULA: the half-rows whose address line is low */
        uint8_t value = 0x1F;
        for (int row = 0; row < 8; ++row)
            if (!(port & (0x100 << row)))
                value &= m->keys[row];
        /* Bits 5 and 7 read 1; bit 6 is the EAR input, which an issue 3 board shows as the EAR bit last written (no tape). */
        return (uint8_t)(0xA0 | value | ((m->out_fe & 0x10) ? 0x40 : 0));
    }
    if (m->kempston_present && !(port & 0xE0))          /* the Kempston interface: A5-A7 low */
        return m->kempston;
    if (m->model == ZXS_128K && (port & 0xC002) == 0xC000)  /* FFFDh: the AY's selected register */
        return m->ay_regs[m->ay_latch];
    return 0xFF;                                        /* the floating bus is not modelled */
}

void zxs_out(ZxsMachine *m, uint16_t port, uint8_t value)
{
    if (!(port & 1)) {
        sound_to(m, m->cycles);                         /* the beeper changes from now on */
        m->out_fe = value;
        m->border = value & 7;
    }
    if (m->model == ZXS_128K) {
        if (!(port & 0x8002) && !(m->port_7ffd & 0x20))  /* 7FFDh: A15 and A1 low, until the lock bit is set */
            m->port_7ffd = value;
        else if ((port & 0xC002) == 0xC000)              /* FFFDh: select an AY register */
            m->ay_latch = value & 15;
        else if ((port & 0xC002) == 0x8000) {            /* BFFDh: write it, the sound caught up first */
            sound_to(m, m->cycles);
            m->ay_regs[m->ay_latch] = value;
            if (m->ay_latch == 13)
                ay38910_shape_written(&m->ay, value);
        }
    }
}

/* ---- the frame and the picture ---- */
int zxs_irq(const ZxsMachine *m) { return m->cycles - m->frame_start < m->int_len; }

uint64_t zxs_next_event(const ZxsMachine *m) { return m->frame_start + (uint64_t)(m->line + 1) * m->t_line; }

static uint32_t fnv_add(uint32_t h, const uint8_t *data, size_t size)
{
    for (size_t i = 0; i < size; ++i) h = (h ^ data[i]) * 16777619u;
    return h;
}

/* Draw frame line `line` (0 .. lines-1) into the picture if it is one of the 240 shown. */
static void draw_line(ZxsMachine *m, unsigned line)
{
    int y = (int)line - (int)m->top_line + ZXS_BORDER_Y;
    if (y < 0 || y >= ZXS_HEIGHT)
        return;
    uint8_t *row = m->picture[y];
    int paper = y - ZXS_BORDER_Y;
    if (paper < 0 || paper >= 192) {
        memset(row, m->border, ZXS_WIDTH);
        return;
    }
    memset(row, m->border, ZXS_BORDER_X);
    memset(row + ZXS_BORDER_X + 256, m->border, ZXS_WIDTH - ZXS_BORDER_X - 256);
    const uint8_t *screen = m->ram[screen_bank(m)];
    /* The bitmap's interleaved layout: y7 y6 | y2 y1 y0 | y5 y4 y3 | x4..x0; the attributes after it, 32 a row of 8 lines. */
    unsigned bitmap = (unsigned)((paper & 0xC0) << 5 | (paper & 0x07) << 8 | (paper & 0x38) << 2);
    unsigned attributes = 0x1800 + (unsigned)(paper >> 3) * 32;
    int flash = (m->frames >> 4) & 1;
    for (int column = 0; column < 32; ++column) {
        uint8_t bits = screen[bitmap + column], attribute = screen[attributes + column];
        uint8_t bright = (attribute & 0x40) ? 8 : 0;
        uint8_t ink = (uint8_t)((attribute & 7) | bright), back = (uint8_t)(((attribute >> 3) & 7) | bright);
        if ((attribute & 0x80) && flash) { uint8_t t = ink; ink = back; back = t; }
        uint8_t *out = row + ZXS_BORDER_X + column * 8;
        for (int bit = 0; bit < 8; ++bit)
            out[bit] = (bits & (0x80 >> bit)) ? ink : back;
    }
}

void zxs_advance(ZxsMachine *m, uint64_t cycles)
{
    uint64_t target = m->cycles + cycles;
    while (zxs_next_event(m) <= target) {
        uint64_t end = zxs_next_event(m);
        m->cycles = end;
        sound_to(m, end);
        draw_line(m, m->line);
        if (++m->line == m->lines) {
            m->line = 0;
            m->frame_start += m->t_frame;
            ++m->frames;
            if (m->trace_frames)
                m->frame_trace = fnv_add(m->frame_trace, &m->picture[0][0], sizeof m->picture);
            if (m->frame_hook)
                m->frame_hook(m->hook_user);
        }
    }
    m->cycles = target;
    sound_to(m, target);
}
