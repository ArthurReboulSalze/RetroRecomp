/* Capcom CPS-1 board; see cps1_machine.h for provenance and limits.
 *
 * Reference CPUs: Musashi (68000) and superzazu's Z80, both from the pinned
 * Geolith copy. The 68000 and the sound side run in scanline slices; the
 * Z80 steps instruction by instruction so YM2151 and OKI output, timers and
 * the busy flag are caught up to the exact Z80 cycle of every access.
 */
#include "cps1_machine.h"
#include "cps1_oki.h"
#include "cps1_opm.h"
#include "cps1_eeprom.h"
#include "cps1_qsound.h"
#include "m68k.h"
#include "z80.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LINES 262
#define VBLANK_LINE 240
#define VISIBLE_X 64
#define VISIBLE_Y 16
#define PIXEL_CLOCK 8000000u
#define LINE_PIXELS 512u
#define GFXRAM_BYTES 0x30000
#define GFXRAM_SPAN 0x40000   /* register bases mask to 0x3ffff */
#define OBJ_WORDS 0x400
#define OKI_CLOCK 1000000u
#define LATCH_QUEUE 64
#define M68K_RESET_CYCLES 34
/* QSound board (CPS-1.5): the sound CPU runs at 8 MHz with a 250 Hz interrupt that is held until taken, and the QSound
 * chip makes a sample every 1248 DSP cycles of a 30 MHz clock (24,038.46 Hz: 5 samples per 1664 Z80 clocks). */
#define QSOUND_IRQ_CLOCKS 32000u
#define QSOUND_SHARED 0x1000
/* the EEPROM's clock ticks in a microsecond: the same figure everywhere the chip is created or restored */
#define eeprom_ticks() ((M.board.cpu_clock + 500000u) / 1000000u)

enum { A_OBJ, A_SCROLL1, A_SCROLL2, A_SCROLL3, A_OTHER, A_PALETTE, A_S1X, A_S1Y, A_S2X, A_S2Y,
       A_S3X, A_S3Y, A_STAR1X, A_STAR1Y, A_STAR2X, A_STAR2Y, A_ROWSCROLL, A_VIDEO };
typedef struct { uint64_t time; uint8_t which, value; } latch_event;

enum { GFX_SPRITES = 1, GFX_SCROLL1 = 2, GFX_SCROLL2 = 4, GFX_SCROLL3 = 8, GFX_STARS = 16 };

static struct {
    cps1_board board;
    cps1_regions rom;
    uint8_t ram[0x10000];
    uint16_t gfxram[GFXRAM_SPAN / 2];
    uint16_t cps_a[0x20], cps_b[0x20];
    uint16_t buffered_obj[OBJ_WORDS];
    uint32_t palette[CPS1_PALETTE_SIZE];
    uint16_t ports[CPS1_PORTS];
    uint32_t frame[CPS1_SCREEN_W * CPS1_SCREEN_H];
    uint16_t pens[CPS1_SCREEN_W * CPS1_SCREEN_H];
    uint8_t priority[CPS1_SCREEN_W * CPS1_SCREEN_H];
    int line;
    uint64_t frame_number, lines_run, m68k_cycles, m68k_target;
    /* sound */
    z80 cpu;
    uint8_t z80_ram[0x800];
    uint8_t latch[2], sound_bank;
    latch_event latch_queue[LATCH_QUEUE];
    int latch_count;
    uint64_t z80_clock;
    cps1_opm *opm;
    uint64_t opm_samples;
    cps1_oki oki;
    uint64_t oki_base_clock, oki_base_samples, oki_samples;
    int32_t oki_level, oki_previous;
    int16_t *audio; size_t audio_count, audio_capacity;
    int irq2;
    /* QSound board */
    uint8_t qram[2][QSOUND_SHARED];             /* shared RAM: Z80 c000-cfff and f000-ffff, 68000 f18000 and f1e000 (low bytes) */
    cps1_eeprom eeprom;
    uint64_t qsound_irq_clock;                  /* Z80 clock of the next 250 Hz interrupt */
    uint64_t qsound_done;                       /* QSound samples made so far */
    cps1_qsound qchip;
    /* CPS-2 board */
    uint16_t objram[2][0x1000];                 /* the two object RAM banks (0x2000 bytes each) */
    uint16_t obj2[0x1000];                      /* the copy latched at VBLANK that the sprites are drawn from */
    uint16_t output[6];                         /* 0x400000-0x40000b: base, unknown, priorities, unknown, x and y offsets */
    uint16_t pri_ctrl;                          /* the priorities word latched with the sprites */
    uint8_t objram_bank, z80_run, extra_ram[0x4002];
    /* the CPS-B-21 raster counters (MAME's cps_state::raster_scanline): two line counters with reloads, an interrupt position in the line */
    uint16_t raster_counter[3], raster_reload[3];
    uint8_t raster_pending, irq4;
    int rendered_rows;                          /* rows of the picture drawn so far in this frame (partial updates at raster interrupts) */
    uint64_t line_start;                        /* 68000 cycle at which the current line started */
} M;

/* ---------------------------------------------------------------- board */

static int read_ints(const char *text, int *values, int count)
{
    char *end;
    for (int i = 0; i < count; i++) {
        values[i] = (int)strtol(text, &end, 10);
        if (end == text) return 0;
        text = end;
    }
    return 1;
}

int cps1_board_parse(cps1_board *board, const char *text, char *error, size_t error_size)
{
    static const char *const ports[CPS1_PORTS] = {"IN0", "IN1", "IN2", "IN3", "DSWA", "DSWB", "DSWC"};
    memset(board, 0, sizeof *board);
    board->z80_clock = CPS1_YM_CLOCK;
    for (int i = 0; i < CPS1_PORTS; i++) board->port_default[i] = 0xffff;
    int version = 0;
    while (*text) {
        const char *end = strchr(text, '\n');
        size_t length = end ? (size_t)(end - text) : strlen(text);
        char line[256];
        if (length >= sizeof line) { snprintf(error, error_size, "board line too long"); return 0; }
        memcpy(line, text, length); line[length] = 0;
        text += length + (end ? 1 : 0);
        char key[32] = {0};
        int used = 0;
        if (sscanf(line, "%31s %n", key, &used) < 1) continue;
        const char *rest = line + used;
        int ok = 1, v[8];
        if (!strcmp(key, "cps1-board")) ok = read_ints(rest, &version, 1);
        else if (!strcmp(key, "set")) { strncpy(board->set, rest, sizeof board->set - 1); }
        else if (!strcmp(key, "cpu_clock")) { ok = read_ints(rest, v, 1); board->cpu_clock = (uint32_t)v[0]; }
        else if (!strcmp(key, "id")) { ok = read_ints(rest, v, 2); board->id_address = v[0]; board->id_value = v[1]; }
        else if (!strcmp(key, "mult")) ok = read_ints(rest, board->mult, 4);
        else if (!strcmp(key, "layer_control")) ok = read_ints(rest, &board->layer_control, 1);
        else if (!strcmp(key, "priority")) ok = read_ints(rest, board->priority, 4);
        else if (!strcmp(key, "palette_control")) ok = read_ints(rest, &board->palette_control, 1);
        else if (!strcmp(key, "layer_enable")) ok = read_ints(rest, board->layer_enable, 5);
        else if (!strcmp(key, "bank_sizes")) ok = read_ints(rest, board->bank_sizes, 4);
        else if (!strcmp(key, "ports")) ok = read_ints(rest, board->ports, 3);
        else if (!strcmp(key, "kludge")) ok = read_ints(rest, &board->kludge, 1);
        else if (!strcmp(key, "rotation")) ok = read_ints(rest, &board->rotation, 1);
        else if (!strcmp(key, "machine")) { board->cps2 = !strcmp(rest, "cps2"); board->qsound = board->cps2 || !strcmp(rest, "qsound"); ok = board->qsound; }
        else if (!strcmp(key, "z80_clock")) { ok = read_ints(rest, v, 1); board->z80_clock = (uint32_t)v[0]; }
        else if (!strcmp(key, "range")) {
            if (board->range_count >= CPS1_MAX_RANGES) { snprintf(error, error_size, "too many ranges"); return 0; }
            cps1_range *range = &board->ranges[board->range_count++];
            ok = read_ints(rest, v, 4);
            range->type = v[0]; range->start = v[1]; range->end = v[2]; range->bank = v[3];
            ok = ok && range->bank >= 0 && range->bank < 4;
        } else if (!strcmp(key, "input")) {
            char name[16]; int value, index = -1;
            ok = sscanf(rest, "%15s %d", name, &value) == 2;
            for (int i = 0; ok && i < CPS1_PORTS; i++) if (!strcmp(name, ports[i])) index = i;
            if (ok && index >= 0) { board->port_default[index] = (uint16_t)value; board->port_present[index] = 1; }
        } else { snprintf(error, error_size, "unknown board key %s", key); return 0; }
        if (!ok) { snprintf(error, error_size, "malformed board line: %s", line); return 0; }
    }
    /* the CPS-2's 16 MHz 68000 as MAME runs it: slowed by 0.7375 for the waitstates it does not emulate (docs/CPS2.md) */
    const int cps2_clock = board->cps2 && board->cpu_clock == 11800000u;
    if (version != 1 || !board->set[0] || (board->cpu_clock != 10000000u && board->cpu_clock != 12000000u && !cps2_clock) ||
        !board->range_count || board->kludge || (board->qsound ? board->z80_clock != 8000000u : board->z80_clock != CPS1_YM_CLOCK)) {
        snprintf(error, error_size, "unsupported CPS-1 board description");
        return 0;
    }
    return 1;
}

/* ---------------------------------------------------------------- audio */

static void audio_push(int16_t sample)
{
    if (M.audio_count == M.audio_capacity) {
        size_t capacity = M.audio_capacity ? M.audio_capacity * 2 : 4096;
        int16_t *grown = realloc(M.audio, capacity * sizeof *grown);
        if (!grown) return;
        M.audio = grown; M.audio_capacity = capacity;
    }
    M.audio[M.audio_count++] = sample;
}

/* Generate OKI samples due by Z80 clock `time`; return the output linearly
 * interpolated between the last two samples at that instant. */
static int32_t oki_catch_up_to(uint64_t time)
{
    const uint64_t master = time * OKI_CLOCK / CPS1_YM_CLOCK, divider = cps1_oki_divider(&M.oki);
    const uint64_t elapsed = master - M.oki_base_clock;
    const uint64_t due = M.oki_base_samples + elapsed / divider;
    while (M.oki_samples < due) {
        M.oki_previous = M.oki_level;
        M.oki_level = cps1_oki_sample(&M.oki);
        M.oki_samples++;
    }
    return M.oki_previous + (int32_t)((int64_t)(M.oki_level - M.oki_previous) * (int64_t)(elapsed % divider) / (int64_t)divider);
}

/* Mono mix with MAME's routes: YM2151 0.35 per channel, OKI 0.30. Each YM2151
 * sample (64 Z80 clocks) takes the OKI output at its own instant. */
static void qsound_catch_up(void);
static void sound_catch_up(void)
{
    if (M.board.qsound) { qsound_catch_up(); return; }
    while ((M.opm_samples + 1) * 64 <= M.z80_clock) {
        int32_t left, right;
        const int32_t oki = oki_catch_up_to((M.opm_samples + 1) * 64);
        cps1_opm_generate(M.opm, &left, &right);
        M.opm_samples++;
        int64_t mixed = ((int64_t)(left + right) * 35 + (int64_t)(oki / 2) * 30) / 100;
        audio_push((int16_t)(mixed > 32767 ? 32767 : mixed < -32768 ? -32768 : mixed));
    }
    oki_catch_up_to(M.z80_clock);
}

/* 68000 writes to the sound latches take effect on the Z80 at the same
 * instant: each write is stamped with the 68000 cycle and replayed when the
 * Z80 reaches it (MAME synchronizes the generic latch the same way). */
/* Musashi takes an interrupt raised between slices outside m68k_execute,
 * where m68k_cycles_run() still reports the finished slice. */
static int m68k_running;

static uint64_t m68k_now(void)
{
    return M.m68k_cycles + (m68k_running ? (uint64_t)m68k_cycles_run() : 0);
}

static void latch_write(int which, uint8_t value)
{
    if (M.latch_count == LATCH_QUEUE) {          /* never expected; keep order */
        M.latch[M.latch_queue[0].which] = M.latch_queue[0].value;
        memmove(M.latch_queue, M.latch_queue + 1, (LATCH_QUEUE - 1) * sizeof M.latch_queue[0]);
        M.latch_count--;
    }
    M.latch_queue[M.latch_count++] = (latch_event){m68k_now() * CPS1_YM_CLOCK / M.board.cpu_clock, (uint8_t)which, value};
}

static void latch_apply(uint64_t time)
{
    int applied = 0;
    while (applied < M.latch_count && M.latch_queue[applied].time <= time) {
        M.latch[M.latch_queue[applied].which] = M.latch_queue[applied].value;
        applied++;
    }
    if (applied) {
        memmove(M.latch_queue, M.latch_queue + applied, (size_t)(M.latch_count - applied) * sizeof M.latch_queue[0]);
        M.latch_count -= applied;
    }
}

static void opm_irq(void *context, int asserted)
{
    (void)context;
    if (asserted) z80_assert_irq(&M.cpu, 0xff); else z80_clr_irq(&M.cpu);
}

/* ---------------------------------------------------------------- QSound board */

/* Samples due by a Z80 clock: the QSound chip makes 24,038.46 samples a second, the Z80 runs at 8 MHz. */
static uint64_t qsound_due(uint64_t clock) { return clock * CPS1_QSOUND_RATE_NUM / CPS1_QSOUND_RATE_DEN; }

/* The chip catches up to the Z80 before the Z80 touches it, as MAME updates the stream on each access. */
static void qsound_catch_up(void)
{
    for (const uint64_t due = qsound_due(M.z80_clock); M.qsound_done < due; M.qsound_done++) {
        int16_t out[2];
        cps1_qsound_sample(&M.qchip, out);
        audio_push(out[0]);
        audio_push(out[1]);
    }
}

/* The sound CPU of the QSound board (MAME's qsound_sub_map): ROM, banked ROM, shared RAM, the QSound ports and RAM. */
static uint8_t qsound_z80_read(uint16_t address)
{
    if (address < 0x8000) return address < M.rom.audiocpu_size ? M.rom.audiocpu[address] : 0;
    if (address < 0xc000) {
        size_t offset = 0x10000 + (size_t)M.sound_bank * 0x4000 + (address - 0x8000);
        return offset < M.rom.audiocpu_size ? M.rom.audiocpu[offset] : 0;
    }
    if (address < 0xd000) return M.qram[0][address - 0xc000];
    if (address == 0xd007) { qsound_catch_up(); return cps1_qsound_ready(&M.qchip); }     /* 0x80 ready, 0x00 busy */
    if (address >= 0xf000) return M.qram[1][address - 0xf000];
    return 0;
}

static void qsound_z80_write(uint16_t address, uint8_t value)
{
    if (address >= 0xc000 && address < 0xd000) { M.qram[0][address - 0xc000] = value; return; }
    if (address >= 0xf000) { M.qram[1][address - 0xf000] = value; return; }
    if (address >= 0xd000 && address <= 0xd002) {
        if (address == 0xd002) qsound_catch_up();
        cps1_qsound_write(&M.qchip, address - 0xd000u, value);
    } else if (address == 0xd003) {
        int bank = value & 0x0f;
        if (0x10000 + (size_t)bank * 0x4000 >= M.rom.audiocpu_size) bank = 0;   /* MAME: a bank past the ROM selects bank 0 */
        M.sound_bank = (uint8_t)bank;
    }
}

static uint8_t z80_read(void *context, uint16_t address)
{
    (void)context;
    if (M.board.qsound) return qsound_z80_read(address);
    if (address < 0x8000) return address < M.rom.audiocpu_size ? M.rom.audiocpu[address] : 0;
    if (address < 0xc000) {
        size_t offset = 0x10000 + (size_t)M.sound_bank * 0x4000 + (address - 0x8000);
        return offset < M.rom.audiocpu_size ? M.rom.audiocpu[offset] : 0;
    }
    if (address >= 0xd000 && address < 0xd800) return M.z80_ram[address - 0xd000];
    switch (address) {
    case 0xf000: case 0xf001: sound_catch_up(); return cps1_opm_read(M.opm, address & 1, M.z80_clock);
    case 0xf002: sound_catch_up(); return cps1_oki_status(&M.oki);
    case 0xf008: return M.latch[0];
    case 0xf00a: return M.latch[1];
    }
    return 0;
}

static void z80_write(void *context, uint16_t address, uint8_t value)
{
    (void)context;
    if (M.board.qsound) { qsound_z80_write(address, value); return; }
    if (address >= 0xd000 && address < 0xd800) { M.z80_ram[address - 0xd000] = value; return; }
    switch (address) {
    case 0xf000: case 0xf001: sound_catch_up(); cps1_opm_write(M.opm, address & 1, value, M.z80_clock); break;
    case 0xf002: sound_catch_up(); cps1_oki_write(&M.oki, value); break;
    case 0xf004: M.sound_bank = value & 1; break;
    case 0xf006:
        if ((value & 1) != M.oki.pin7) {
            sound_catch_up();
            M.oki_base_clock = M.z80_clock * OKI_CLOCK / CPS1_YM_CLOCK;
            M.oki_base_samples = M.oki_samples;
            M.oki.pin7 = value & 1;
        }
        break;
    }
}

static uint8_t z80_in(z80 *cpu, uint16_t port) { (void)cpu; (void)port; return 0xff; }
static void z80_out(z80 *cpu, uint16_t port, uint8_t value) { (void)cpu; (void)port; (void)value; }

/* ---------------------------------------------------------------- video */

static void build_palette(void)
{
    int base = (M.cps_a[A_PALETTE] * 256) & ~(0x400 - 1);
    const uint16_t *ram = &M.gfxram[(base & 0x3ffff) / 2], *start = ram;
    const uint16_t control = M.cps_b[M.board.palette_control / 2];
    for (int page = 0; page < 6; page++) {
        if (control >> page & 1) {
            for (int offset = 0; offset < 0x200; offset++) {
                const uint16_t value = *ram++;
                const int bright = 0x0f + ((value >> 12) << 1);
                const int r = ((value >> 8) & 0x0f) * 0x11 * bright / 0x2d;
                const int g = ((value >> 4) & 0x0f) * 0x11 * bright / 0x2d;
                const int b = (value & 0x0f) * 0x11 * bright / 0x2d;
                M.palette[0x200 * page + offset] = (uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b;
            }
        } else if (ram != start) {
            ram += 0x200;
        }
    }
}

static const uint16_t *video_base(int reg, int boundary)
{
    int base = (M.cps_a[reg] * 256) & ~(boundary - 1);
    return &M.gfxram[(base & 0x3ffff) / 2];
}

static int bank_mapper(int type, int code)
{
    static const int shifts[17] = {[GFX_SPRITES] = 1, [GFX_SCROLL1] = 0, [GFX_SCROLL2] = 1, [GFX_SCROLL3] = 3};
    const int shift = shifts[type];
    code <<= shift;
    for (int i = 0; i < M.board.range_count; i++) {
        const cps1_range *range = &M.board.ranges[i];
        if (code >= range->start && code <= range->end && (range->type & type)) {
            int base = 0;
            for (int bank = 0; bank < range->bank; bank++) base += M.board.bank_sizes[bank];
            return (base + (code & (M.board.bank_sizes[range->bank] - 1))) >> shift;
        }
    }
    return -1;
}

/* The graphics ROM decoded once, one pen per byte. MAME's gfx_cps1 layout
 * keeps eight pixels in each group of four bytes (four bit planes, most
 * significant plane last), with 8 bytes per 16-pixel row for 8x8 and 16x16
 * tiles and 16 bytes per row for 32x32 tiles; decoded, a tile row of any size
 * is contiguous. sprite_blank flags 16x16 tiles whose pens are all 15: like
 * MAME's pen usage test, skipping them changes nothing. */
static uint8_t *gfx_pens, *sprite_blank;

static void free_gfx(void)
{
    free(gfx_pens); free(sprite_blank);
    gfx_pens = sprite_blank = NULL;
}

/* The CPS-2 graphics ROMs are stored shuffled: in each 2 MiB bank the 8-byte items are permuted by MAME's recursive `unshuffle`
 * (cps2_state::unshuffle), after which the bank has the CPS-1 layout. */
static void unshuffle(uint64_t *buffer, size_t length)
{
    if (length == 2) return;
    length /= 2;
    unshuffle(buffer, length);
    unshuffle(buffer + length, length);
    for (size_t i = 0; i < length / 2; i++) {
        const uint64_t item = buffer[length / 2 + i];
        buffer[length / 2 + i] = buffer[length + i];
        buffer[length + i] = item;
    }
}

static int decode_gfx(void)
{
    free_gfx();
    const size_t groups = M.rom.gfx_size / 4, sprites = M.rom.gfx_size / 128;
    if (!groups) return 1;
    uint8_t *shuffled = NULL;
    const uint8_t *source = M.rom.gfx;
    if (M.board.cps2) {
        const size_t bank = 0x200000;
        if (M.rom.gfx_size % bank) return 0;
        shuffled = malloc(M.rom.gfx_size);
        if (!shuffled) return 0;
        memcpy(shuffled, M.rom.gfx, M.rom.gfx_size);
        for (size_t at = 0; at < M.rom.gfx_size; at += bank) unshuffle((uint64_t *)(void *)(shuffled + at), bank / 8);
        source = shuffled;
    }
    gfx_pens = malloc(groups * 8);
    sprite_blank = malloc(sprites ? sprites : 1);
    if (!gfx_pens || !sprite_blank) { free_gfx(); free(shuffled); return 0; }
    for (size_t g = 0; g < groups; g++) {
        const uint8_t *p = source + g * 4;
        for (int x = 0; x < 8; x++) {
            const int bit = 7 - x;
            gfx_pens[g * 8 + (size_t)x] =
                (uint8_t)((p[3] >> bit & 1) << 3 | (p[2] >> bit & 1) << 2 | (p[1] >> bit & 1) << 1 | (p[0] >> bit & 1));
        }
    }
    for (size_t s = 0; s < sprites; s++) {
        const uint8_t *pens = gfx_pens + s * 256;
        size_t n = 0;
        while (n < 256 && pens[n] == 15) n++;
        sprite_blank[s] = n == 256;
    }
    free(shuffled);
    return 1;
}

/* Pens of row y of a tile, or NULL (all pens 15) when the ROM holds no tile of
 * this size. Codes wrap at the tile count like MAME's gfx element. */
static const uint8_t *tile_row(int size, int half, int code, int y)
{
    const size_t bytes = size == 32 ? 512 : size == 16 ? 128 : 64;
    const size_t count = M.rom.gfx_size / bytes;
    if (!count) return NULL;
    const size_t row = (size_t)((unsigned)code % count) * bytes + (size_t)y * (size == 32 ? 16 : 8);
    return gfx_pens + 2 * row + (size == 8 ? (size_t)half * 8 : 0);
}

/* One tilemap pass, a tile row at a time: each scanline is cut into runs that
 * stay in one tile, whose code, attributes and pens are looked up once. */
static int row_first, row_last = CPS1_SCREEN_H;     /* the picture rows a draw call may touch (the whole picture, or the part between two raster interrupts) */
static int tile_priority;           /* CPS-2: the value (1, 2 or 4) OR-ed into the priority plane under each opaque tile pixel */

static void draw_layer(int layer, int high)
{
    static const int sizes[3] = {8, 16, 32}, types[3] = {GFX_SCROLL1, GFX_SCROLL2, GFX_SCROLL3};
    static const int colors[3] = {0x20, 0x40, 0x60}, bases[3] = {A_SCROLL1, A_SCROLL2, A_SCROLL3};
    static const int scrolls[3][2] = {{A_S1X, A_S1Y}, {A_S2X, A_S2Y}, {A_S3X, A_S3Y}};
    const int size = sizes[layer], extent = size * 64 - 1;
    const uint16_t *map = video_base(bases[layer], 0x4000);
    const uint16_t *other = video_base(A_OTHER, 0x800);
    const int scroll_x = M.cps_a[scrolls[layer][0]], scroll_y = M.cps_a[scrolls[layer][1]];
    const int rowscroll = layer == 1 && (M.cps_a[A_VIDEO] & 1);
    uint16_t mask[4];
    for (int i = 0; i < 4; i++)
        mask[i] = M.board.priority[i] != -1 ? M.cps_b[M.board.priority[i] / 2] : 0;
    const int flip = M.cps_a[A_VIDEO] >> 15 & 1, step = flip ? -1 : 1;
    for (int y = row_first; y < row_last; y++) {
        const int raster_y = flip ? LINES - 1 - (y + VISIBLE_Y) : y + VISIBLE_Y;
        const int ty = (raster_y + scroll_y) & extent, row = ty / size;
        int line_x = scroll_x;
        if (rowscroll) line_x += other[(raster_y + M.cps_a[A_ROWSCROLL]) & 0x3ff];
        uint16_t *pens = M.pens + y * CPS1_SCREEN_W;
        uint8_t *priority = M.priority + y * CPS1_SCREEN_W;
        for (int x = 0; x < CPS1_SCREEN_W;) {
            const int raster_x = flip ? (int)LINE_PIXELS - 1 - (x + VISIBLE_X) : x + VISIBLE_X;
            const int tx = (raster_x + line_x) & extent, col = tx / size, first = tx % size;
            int run = flip ? first + 1 : size - first;
            if (run > CPS1_SCREEN_W - x) run = CPS1_SCREEN_W - x;
            int index;
            if (layer == 0) index = (row & 0x1f) + ((col & 0x3f) << 5) + ((row & 0x20) << 6);
            else if (layer == 1) index = (row & 0x0f) + ((col & 0x3f) << 4) + ((row & 0x30) << 6);
            else index = (row & 0x07) + ((col & 0x3f) << 3) + ((row & 0x38) << 6);
            int code = map[2 * index];
            const uint16_t attr = map[2 * index + 1];
            if (layer == 2) code &= 0x3fff;
            code = bank_mapper(types[layer], code);
            const int py = attr & 0x40 ? size - 1 - ty % size : ty % size;
            const uint8_t *src = code != -1 ? tile_row(size, index >> 5 & 1, code, py) : NULL;
            int px = first, advance = step;
            if (attr & 0x20) { px = size - 1 - first; advance = -step; }
            if (high) {
                const uint16_t pen_mask = mask[(attr >> 7) & 3];
                if (!src) {
                    if (pen_mask >> 15 & 1) for (int k = 0; k < run; k++) priority[x + k] |= 1;
                } else if (pen_mask) {
                    for (int k = 0; k < run; k++, px += advance)
                        if (pen_mask >> src[px] & 1) priority[x + k] |= 1;
                }
            } else if (src) {
                const uint16_t colour = (uint16_t)(((attr & 0x1f) + colors[layer]) * 16);
                for (int k = 0; k < run; k++, px += advance) {
                    const int pen = src[px];
                    if (pen != 15) { pens[x + k] = (uint16_t)(colour + pen); priority[x + k] |= (uint8_t)tile_priority; }
                }
            }
            x += run;
        }
    }
}

static void draw_sprite(int code, int color, int flipx, int flipy, int sx, int sy, uint32_t pmask)
{
    const size_t count = M.rom.gfx_size / 128;
    if (!count || sprite_blank[(unsigned)code % count]) return;
    if (M.cps_a[A_VIDEO] & 0x8000) {            /* MAME DRAWSPRITE, flipped screen */
        flipx = !flipx; flipy = !flipy;
        sx = 512 - 16 - sx; sy = 256 - 16 - sy;
    }
    const int x0 = sx < VISIBLE_X ? VISIBLE_X - sx : 0;
    const int x1 = sx + 16 > VISIBLE_X + CPS1_SCREEN_W ? VISIBLE_X + CPS1_SCREEN_W - sx : 16;
    if (x0 >= x1) return;
    const uint16_t colour = (uint16_t)(color * 16);
    for (int y = 0; y < 16; y++) {
        const int raster_y = sy + y;
        if (raster_y < VISIBLE_Y + row_first || raster_y >= VISIBLE_Y + row_last) continue;
        const uint8_t *src = tile_row(16, 0, code, flipy ? 15 - y : y);
        const int line = (raster_y - VISIBLE_Y) * CPS1_SCREEN_W + sx - VISIBLE_X;
        for (int x = x0; x < x1; x++) {
            const int pen = src[flipx ? 15 - x : x];
            if (pen == 15) continue;
            const int at = line + x;
            /* MAME prio_transpen with pmask 0x02 plus its implicit bit 31: a
             * high tile (1) or an earlier sprite (31) keeps the pixel, so the
             * first sprite of the list stays on top. */
            if (!((1u << (M.priority[at] & 0x1f)) & (pmask | 0x80000000u))) M.pens[at] = (uint16_t)(colour + pen);
            M.priority[at] = 31;
        }
    }
}

static void draw_sprites(void)
{
    int last = OBJ_WORDS - 4;
    for (int offset = 0; offset < OBJ_WORDS; offset += 4)
        if ((M.buffered_obj[offset + 3] & 0xff00) == 0xff00) { last = offset - 4; break; }
    const uint16_t *base = M.buffered_obj;
    for (int i = last; i >= 0; i -= 4, base += 4) {
        const int x = base[0], y = base[1], colour = base[3], col = colour & 0x1f;
        const int flipx = colour >> 5 & 1, flipy = colour >> 6 & 1;
        const int code = bank_mapper(GFX_SPRITES, base[2]);
        if (code == -1) continue;
        if (colour & 0xff00) {
            const int nx = ((colour & 0x0f00) >> 8) + 1, ny = ((colour & 0xf000) >> 12) + 1;
            for (int nys = 0; nys < ny; nys++) {
                const int sy = (y + nys * 16) & 0x1ff;
                for (int nxs = 0; nxs < nx; nxs++) {
                    const int sx = (x + nxs * 16) & 0x1ff;
                    const int column = flipx ? (code + (nx - 1) - nxs) & 0xf : (code + nxs) & 0xf;
                    const int row = 0x10 * (flipy ? ny - 1 - nys : nys);
                    draw_sprite((code & ~0xf) + column + row, col, flipx, flipy, sx, sy, 0x02);
                }
            }
        } else {
            draw_sprite(code, col, flipx, flipy, x & 0x1ff, y & 0x1ff, 0x02);
        }
    }
}

/* The CPS-2 object chip (MAME's cps2_render_sprites): 0x400 sprites of four words in the latched object RAM, drawn from the last
 * one down, each with its own 3-bit priority against the tile layers, 10-bit coordinates, block sprites, and the offsets of the
 * output registers. Sprites address the graphics ROM linearly (no bank mapper). */
#define CPS2_XOFFS 4
#define CPS2_YOFFS 5
#define CPS2_PRI 2
static void draw_sprites_cps2(const uint32_t primasks[8])
{
    int last = 0x1000 - 4;
    for (int offset = 0; offset < 0x1000; offset += 4)
        if (M.obj2[offset + 1] >= 0x8000 || M.obj2[offset + 3] >= 0xff00) { last = offset - 4; break; }
    const int xoffs = 64 - M.output[CPS2_XOFFS], yoffs = 16 - M.output[CPS2_YOFFS];
    for (int i = last; i >= 0; i -= 4) {
        const uint16_t *s = &M.obj2[i];
        int x = s[0], y = s[1];
        const int priority = x >> 13 & 7, code = s[2] + ((y & 0x6000) << 3), colour = s[3], col = colour & 0x1f;
        const int flipx = colour >> 5 & 1, flipy = colour >> 6 & 1;
        const uint32_t pmask = primasks[priority];
        if (colour & 0x80) { x += M.output[CPS2_XOFFS]; y += M.output[CPS2_YOFFS]; }
        if (colour & 0xff00) {
            const int nx = ((colour & 0x0f00) >> 8) + 1, ny = ((colour & 0xf000) >> 12) + 1;
            for (int nys = 0; nys < ny; nys++) {
                const int sy = (y + nys * 16 + yoffs) & 0x3ff;
                for (int nxs = 0; nxs < nx; nxs++) {
                    const int sx = (x + nxs * 16 + xoffs) & 0x3ff;
                    int block;
                    if (flipy) block = flipx ? code + (nx - 1) - nxs + 0x10 * (ny - 1 - nys) : code + nxs + 0x10 * (ny - 1 - nys);
                    else block = flipx ? code + (nx - 1) - nxs + 0x10 * nys : (code & ~0xf) + ((code + nxs) & 0xf) + 0x10 * nys;
                    draw_sprite(block, col, flipx, flipy, sx, sy, pmask);
                }
            }
        } else {
            draw_sprite(code, col, flipx, flipy, (x + xoffs) & 0x3ff, (y + yoffs) & 0x3ff, pmask);
        }
    }
}

static void draw_stars(void)
{
    const uint16_t layers = M.cps_b[M.board.layer_control / 2];
    if (!M.rom.stars) return;
    for (int field = 0; field < 2; field++) {
        if (!(layers & M.board.layer_enable[3 + field])) continue;
        const int scroll_x = M.cps_a[field ? A_STAR1X : A_STAR2X], scroll_y = M.cps_a[field ? A_STAR1Y : A_STAR2Y];
        for (int offs = 0; offs < 0x1000; offs++) {
            size_t at = 8 * (size_t)offs + (field ? 0 : 4);
            if (at >= M.rom.stars_size) break;
            int col = M.rom.stars[at];
            if ((col & 0x1f) == 0x0f) continue;
            int sx = ((offs / 256) * 32 - scroll_x + (col & 0x1f)) & 0x1ff;
            int sy = ((offs % 256) - scroll_y) & 0xff;
            if (M.cps_a[A_VIDEO] & 0x8000) { sx = 512 - sx; sy = 256 - sy; }
            const int count = (int)((M.frame_number / 16) % ((col & 0x80) ? 15 : 16));
            col = ((col & 0xe0) >> 1) + count;
            if (sx >= VISIBLE_X && sx < VISIBLE_X + CPS1_SCREEN_W && sy >= VISIBLE_Y && sy < VISIBLE_Y + CPS1_SCREEN_H)
                M.pens[(sy - VISIBLE_Y) * CPS1_SCREEN_W + sx - VISIBLE_X] = (uint16_t)((field ? 0x800 : 0xa00) + col);
        }
    }
}

static void render_layer(int layer, int high)
{
    if (layer == 0) { if (!high) draw_sprites(); return; }
    const uint16_t layers = M.cps_b[M.board.layer_control / 2], video = M.cps_a[A_VIDEO];
    int enabled = layers & M.board.layer_enable[layer - 1];
    if (layer == 2) enabled = enabled && (video & 4);
    if (layer == 3) enabled = enabled && (video & 8);
    if (enabled) draw_layer(layer - 1, high);
}

/* Pens are drawn at the start of VBLANK; colours are applied when VBLANK
 * ends, after the game's VBLANK handler has updated the palette. This is what
 * MAME presents (its indexed bitmap is coloured when shown): pixel-identical
 * fades on Final Fight and Street Fighter II for any colouring line from
 * VBLANK + 10 to the next VBLANK, not at VBLANK + 1 on SF2. */
#define COLOUR_LINE 0

static void apply_palette(void)
{
    for (size_t i = 0; i < CPS1_SCREEN_W * CPS1_SCREEN_H; i++) M.frame[i] = M.palette[M.pens[i]];
}

static void render_frame(void)
{
    for (size_t i = 0; i < CPS1_SCREEN_W * CPS1_SCREEN_H; i++) { M.pens[i] = 0xbff; M.priority[i] = 0; }
    draw_stars();
    const uint16_t control = M.cps_b[M.board.layer_control / 2];
    const int order[4] = {control >> 6 & 3, control >> 8 & 3, control >> 10 & 3, control >> 12 & 3};
    for (int i = 0; i < 4; i++) {
        render_layer(order[i], 0);
        if (i < 3 && order[i + 1] == 0) render_layer(order[i], 1);
    }
}

/* The CPS-2 frame (MAME's cps2_state::render_layers): the sprite layer of the layer-control word is taken out, the three tile
 * layers are drawn in the order it gives, each writing its value (1, 2, 4) into the priority plane, and the sprites last, each
 * tested against the plane with the mask its own priority and the latched priority word select. */
static void render_rows_cps2(int first, int last)
{
    row_first = first; row_last = last;
    for (size_t i = (size_t)first * CPS1_SCREEN_W; i < (size_t)last * CPS1_SCREEN_W; i++) { M.pens[i] = 0xbff; M.priority[i] = 0; }
    const uint16_t control = M.cps_b[M.board.layer_control / 2];
    int l0 = control >> 6 & 3, l1 = control >> 8 & 3, l2 = control >> 10 & 3, l3 = control >> 12 & 3;
    int p0 = M.pri_ctrl >> (4 * l0) & 15, p1 = M.pri_ctrl >> (4 * l1) & 15, p2 = M.pri_ctrl >> (4 * l2) & 15;
    const int p3 = M.pri_ctrl >> (4 * l3) & 15;
    if (l0 == 0) { l0 = l1; l1 = 0; p0 = p1; }
    if (l1 == 0) { l1 = l2; l2 = 0; p1 = p2; }
    if (l2 == 0) { l2 = l3; l3 = 0; p2 = p3; }
    uint32_t primasks[8], mask0 = 0xaa, mask1 = 0xcc;
    if (p0 > p1) mask0 &= ~0x88u;
    if (p0 > p2) mask0 &= ~0xa0u;
    if (p1 > p2) mask1 &= ~0xc0u;
    primasks[0] = 0xff;
    for (int i = 1; i < 8; i++) {
        if (i <= p0 && i <= p1 && i <= p2) { primasks[i] = 0xfe; continue; }
        primasks[i] = 0;
        if (i <= p0) primasks[i] |= mask0;
        if (i <= p1) primasks[i] |= mask1;
        if (i <= p2) primasks[i] |= 0xf0;
    }
    const int layers[3] = {l0, l1, l2};
    for (int i = 0; i < 3; i++) {
        if (!layers[i]) continue;
        tile_priority = 1 << i;
        render_layer(layers[i], 0);
    }
    tile_priority = 0;
    draw_sprites_cps2(primasks);
    row_first = 0; row_last = CPS1_SCREEN_H;
}

/* The rest of the picture at VBLANK, or the rows up to the line of a raster interrupt (MAME's update_partial): the registers the game
 * changes after the interrupt apply from the next row on. */
static void render_to_row(int last)
{
    if (last > CPS1_SCREEN_H) last = CPS1_SCREEN_H;
    if (last <= M.rendered_rows) return;
    render_rows_cps2(M.rendered_rows, last);
    M.rendered_rows = last;
}

/* ---------------------------------------------------------------- 68000 bus */

/* The 68000 here reads at the start of an instruction, MAME's clock reads it a few bus cycles later (a MOVE.W from an absolute address
 * reads in its last four cycles). The raster counters change every line, so a read near the end of a line must see the same line:
 * measured on mmatrix against MAME's taps (reads about 5 pixels, writes about 10 pixels later than ours), 8 cycles. */
#define CPS2_READ_DELAY 8

static uint16_t cps_b_read(int offset)
{
    if (M.board.cps2) {
        const uint64_t now = m68k_now() + CPS2_READ_DELAY;
        if (offset == 0x0e / 2) {                 /* the position in the line, relative to counter 3, and the unknown bit 0 */
            const int pixel = (int)((now - M.line_start) * PIXEL_CLOCK / M.board.cpu_clock) / 2;
            return (uint16_t)((((int)M.raster_counter[2] - pixel) << 1 & 0x1fe) | (M.cps_b[0x0e / 2] & 1));
        }
        if (offset == 0x10 / 2 || offset == 0x12 / 2) {
            /* MAME's counter changes at the start of the line, on the clock; the 68000 here runs a line in one slice, so a read made past the end
             * of the line by an instruction that crosses it sees the next line's value */
            uint16_t value = M.raster_counter[offset & 1];
            if (now >= M.m68k_target)
                value = (M.line + 1) % LINES == 0 ? M.raster_reload[offset & 1] : (uint16_t)(value - 1);
            return value & 0x1ff;
        }
    }
    /* As in MAME, an absent register (-1) compares as offset -1 / 2 == 0. */
    const cps1_board *b = &M.board;
    if (offset == b->id_address / 2) return (uint16_t)b->id_value;
    if (offset == b->mult[2] / 2)
        return (uint16_t)((uint32_t)M.cps_b[b->mult[0] / 2] * M.cps_b[b->mult[1] / 2]);
    if (offset == b->mult[3] / 2)
        return (uint16_t)(((uint32_t)M.cps_b[b->mult[0] / 2] * M.cps_b[b->mult[1] / 2]) >> 16);
    if (b->ports[0] && offset == b->ports[0] / 2) return M.ports[CPS1_IN2];
    if (b->ports[1] && offset == b->ports[1] / 2) return M.ports[CPS1_IN3];
    return 0xffff;
}

/* The QSound board's own 68000 space (MAME's qsound_main_map) above the work RAM: sound ROM read-back (Slam Masters' protection),
 * the RAM shared with the Z80 (low bytes only), players 3 and 4, the EEPROM. */
static int qsound_read(uint32_t address, uint16_t *word)
{
    if (address >= 0xf00000 && address < 0xf10000) {
        const size_t index = (address - 0xf00000) / 2;
        *word = M.rom.audiorom_raw && index < M.rom.audiorom_raw_size ? (uint16_t)(M.rom.audiorom_raw[index] | 0xff00) : 0;
        return 1;
    }
    if (address >= 0xf18000 && address < 0xf1a000) { *word = (uint16_t)(M.qram[0][(address - 0xf18000) / 2] | 0xff00); return 1; }
    if (address >= 0xf1e000 && address < 0xf20000) { *word = (uint16_t)(M.qram[1][(address - 0xf1e000) / 2] | 0xff00); return 1; }
    if (address == 0xf1c000) { *word = M.ports[CPS1_IN2]; return 1; }
    if (address == 0xf1c002) { *word = M.ports[CPS1_IN3]; return 1; }
    if (address == 0xf1c006) { *word = (uint16_t)cps1_eeprom_read_port(&M.eeprom, m68k_now()); return 1; }
    return 0;
}

/* The CPS-2 board's 68000 space (MAME's cps2_state::cps2_map): the program ROM, the object chip's output registers, the RAM shared
 * with the Z80 (low bytes), two object RAM banks, the CPS-A/B registers (mirrored), the inputs with the EEPROM's DO bit, the volume
 * register, the graphics RAM and the work RAM. */
#ifdef RR_CPS2_IOTRACE
/* Development only: the hardware accesses (0x400000-0x8fffff) of the first frames, to compare with MAME's taps on the same bus. */
static void io_trace(char kind, uint32_t address, uint16_t value)
{
    static FILE *file; static int opened;
    if (!opened) { opened = 1; const char *path = getenv("RR_IOTRACE"); file = path ? fopen(path, "w") : NULL; }
    if (file && address >= 0x400000 && address < 0x930000)
        fprintf(file, "%llu %c %06x %04x %d %d\n", (unsigned long long)M.frame_number, kind, address, value, M.line,
                (int)((m68k_now() - M.line_start) * PIXEL_CLOCK / M.board.cpu_clock));
}
#endif

#define CPS2_SERVICE_BIT 0x80u       /* bit 7 of the third switch bank: the service switch, clear = pressed */

static uint16_t cps2_read_bus(uint32_t address);
static uint16_t cps2_read(uint32_t address)
{
    const uint16_t value = cps2_read_bus(address);
#ifdef RR_CPS2_IOTRACE
    io_trace('R', address, value);
#endif
    return value;
}

static uint16_t cps2_read_bus(uint32_t address)
{
    if (address < 0x400000) return address + 1 < M.rom.maincpu_size ? (uint16_t)(M.rom.maincpu[address] << 8 | M.rom.maincpu[address + 1]) : 0;
    if (address >= 0xff0000) return (uint16_t)(M.ram[address & 0xffff] << 8 | M.ram[(address & 0xffff) + 1]);
    if (address >= 0x900000 && address < 0x900000 + GFXRAM_BYTES) return M.gfxram[(address - 0x900000) / 2];
    if (address >= 0x400000 && address < 0x40000c) return M.output[(address - 0x400000) / 2];
    if (address >= 0x618000 && address < 0x61a000) return (uint16_t)(M.qram[0][(address - 0x618000) / 2] | 0xff00);
    if (address >= 0x660000 && address < 0x664002) return (uint16_t)(M.extra_ram[address - 0x660000] << 8 | M.extra_ram[address - 0x660000 + 1]);
    if (address >= 0x708000 && address < 0x710000) return M.objram[M.objram_bank ^ 1][(address & 0x1fff) / 2];
    if ((address >= 0x800140 && address < 0x800180) || (address >= 0x804140 && address < 0x804180)) return cps_b_read((int)(address & 0x3f) / 2);
    if (address == 0x804000) return M.ports[CPS1_IN0];
    if (address == 0x804010) return M.ports[CPS1_IN1];
    /* The board's service switch (IN2 bit 1, active low, MAME's PORT_SERVICE_NO_TOGGLE) is the switch page's "test menu" setting: bit 7 of the
     * third bank, which the game never sees there (a production board has no switch banks, the game reads them as released). */
    if (address == 0x804020) return (uint16_t)(((M.ports[CPS1_IN2] & ~1u) | (cps1_eeprom_read_port(&M.eeprom, m68k_now()) & 1u)) &
                                              ((M.ports[CPS1_DSWC] & CPS2_SERVICE_BIT) ? 0xffffu : ~2u));
    if (address == 0x804030) return 0xe021;                 /* the digital volume at its maximum, no extra memory, no network adapter */
    /* The three switch banks of the development hardware (MAME's lr8 handlers at 0x8040b0 to 0x8040b2): a production board reads them
     * released, and some games do read them (mmatrix at boot). One byte each, on the high lane for the even addresses. */
    if (address == 0x8040b0) return (uint16_t)((M.ports[CPS1_DSWA] & 0xff) << 8 | (M.ports[CPS1_DSWB] & 0xff));
    if (address == 0x8040b2) return (uint16_t)(((M.ports[CPS1_DSWC] | CPS2_SERVICE_BIT) & 0xff) << 8);
    return 0;
}

static void cps2_write_bus(uint32_t address, uint16_t data, uint16_t mask);
static void cps2_write(uint32_t address, uint16_t data, uint16_t mask)
{
#ifdef RR_CPS2_IOTRACE
    io_trace('W', address, data);
#endif
    cps2_write_bus(address, data, mask);
}

static void cps2_write_bus(uint32_t address, uint16_t data, uint16_t mask)
{
    if (address >= 0xff0000) {
        if (mask & 0xff00) M.ram[address & 0xffff] = (uint8_t)(data >> 8);
        if (mask & 0x00ff) M.ram[(address & 0xffff) + 1] = (uint8_t)data;
        return;
    }
    if (address >= 0x900000 && address < 0x900000 + GFXRAM_BYTES) {
        uint16_t *word = &M.gfxram[(address - 0x900000) / 2];
        *word = (uint16_t)((*word & ~mask) | (data & mask));
        return;
    }
    if (address >= 0x400000 && address < 0x40000c) {
        uint16_t *word = &M.output[(address - 0x400000) / 2];
        *word = (uint16_t)((*word & ~mask) | (data & mask));
        return;
    }
    if (address >= 0x618000 && address < 0x61a000) { if (mask & 0x00ff) M.qram[0][(address - 0x618000) / 2] = (uint8_t)data; return; }
    if (address >= 0x660000 && address < 0x664002) {
        if (mask & 0xff00) M.extra_ram[address - 0x660000] = (uint8_t)(data >> 8);
        if (mask & 0x00ff) M.extra_ram[address - 0x660000 + 1] = (uint8_t)data;
        return;
    }
    if (address >= 0x700000 && address < 0x702000) {
        uint16_t *word = &M.objram[M.objram_bank][(address - 0x700000) / 2];
        *word = (uint16_t)((*word & ~mask) | (data & mask));
        return;
    }
    if (address >= 0x708000 && address < 0x710000) {
        uint16_t *word = &M.objram[M.objram_bank ^ 1][(address & 0x1fff) / 2];
        *word = (uint16_t)((*word & ~mask) | (data & mask));
        return;
    }
    if ((address >= 0x800100 && address < 0x800140) || (address >= 0x804100 && address < 0x804140)) {
        const int offset = (int)(address & 0x3f) / 2;
        M.cps_a[offset] = (uint16_t)((M.cps_a[offset] & ~mask) | (data & mask));
        if (offset == A_PALETTE) build_palette();
        return;
    }
    if ((address >= 0x800140 && address < 0x800180) || (address >= 0x804140 && address < 0x804180)) {
        const int offset = (int)(address & 0x3f) / 2;
        M.cps_b[offset] = (uint16_t)((M.cps_b[offset] & ~mask) | (data & mask));
        if (offset == 0x0e / 2) M.raster_reload[2] = M.cps_b[offset] >> 1 & 0xff;
        else if (offset == 0x10 / 2 || offset == 0x12 / 2) {
            M.raster_reload[offset & 1] = M.cps_b[offset] & 0x1ff;
            if (M.cps_b[offset] >> 15 & 1) M.raster_counter[offset & 1] = M.raster_reload[offset & 1];     /* manual reload */
        }
        return;
    }
    if (address == 0x8040e0) { if (mask & 0x00ff) M.objram_bank = data & 1; return; }
    if (address == 0x804040) {
        if (mask & 0xff00) cps1_eeprom_write_port16(&M.eeprom, data & 0x7000u, m68k_now());
        if (mask & 0x00ff) {                      /* bit 3 lets the Z80 run (held in reset while it is low); the coin lines have no visible state */
            const int run = data >> 3 & 1;
            if (!run && M.z80_run) z80_reset(&M.cpu);
            M.z80_run = (uint8_t)run;
        }
        return;
    }
    /* 0x8040a0 and the other unknown writes: no visible state */
}

static uint16_t read_word(uint32_t address)
{
    address &= 0xfffffe;
    if (M.board.cps2) return cps2_read(address);
    if (M.board.qsound && address >= 0xf00000 && address < 0xff0000) {
        uint16_t word;
        if (qsound_read(address, &word)) return word;
    }
    if (address < 0x400000) {
        return address + 1 < M.rom.maincpu_size ? (uint16_t)(M.rom.maincpu[address] << 8 | M.rom.maincpu[address + 1]) : 0;
    }
    if (address >= 0xff0000) return (uint16_t)(M.ram[address & 0xffff] << 8 | M.ram[(address & 0xffff) + 1]);
    if (address >= 0x900000 && address < 0x900000 + GFXRAM_BYTES) return M.gfxram[(address - 0x900000) / 2];
    if (address >= 0x800000 && address < 0x800008) return M.ports[CPS1_IN1];
    if (address >= 0x800018 && address < 0x800020) {
        static const int ports[4] = {CPS1_IN0, CPS1_DSWA, CPS1_DSWB, CPS1_DSWC};
        return (uint16_t)((M.ports[ports[(address - 0x800018) / 2]] & 0xff) << 8 | 0xff);
    }
    if (address >= 0x800140 && address < 0x800180) return cps_b_read((int)(address - 0x800140) / 2);
    return 0;
}

static int qsound_write(uint32_t address, uint16_t data, uint16_t mask)
{
    if (address >= 0xf18000 && address < 0xf1a000) { if (mask & 0x00ff) M.qram[0][(address - 0xf18000) / 2] = (uint8_t)data; return 1; }
    if (address >= 0xf1e000 && address < 0xf20000) { if (mask & 0x00ff) M.qram[1][(address - 0xf1e000) / 2] = (uint8_t)data; return 1; }
    if (address == 0xf1c006) { if (mask & 0x00ff) cps1_eeprom_write_port(&M.eeprom, data & 0xff, m68k_now()); return 1; }
    return address >= 0xf00000 && address < 0xff0000;     /* the coin control of players 3 and 4 and unmapped space: no visible state */
}

static void write_word(uint32_t address, uint16_t data, uint16_t mask)
{
    address &= 0xfffffe;
    if (M.board.cps2) { cps2_write(address, data, mask); return; }
    if (M.board.qsound && qsound_write(address, data, mask)) return;
    if (address >= 0xff0000) {
        if (mask & 0xff00) M.ram[address & 0xffff] = (uint8_t)(data >> 8);
        if (mask & 0x00ff) M.ram[(address & 0xffff) + 1] = (uint8_t)data;
        return;
    }
    if (address >= 0x900000 && address < 0x900000 + GFXRAM_BYTES) {
        uint16_t *word = &M.gfxram[(address - 0x900000) / 2];
        *word = (uint16_t)((*word & ~mask) | (data & mask));
        return;
    }
    if (address >= 0x800100 && address < 0x800140) {
        const int offset = (int)(address - 0x800100) / 2;
        M.cps_a[offset] = (uint16_t)((M.cps_a[offset] & ~mask) | (data & mask));
        if (offset == A_PALETTE) build_palette();
        return;
    }
    if (address >= 0x800140 && address < 0x800180) {
        const int offset = (int)(address - 0x800140) / 2;
        M.cps_b[offset] = (uint16_t)((M.cps_b[offset] & ~mask) | (data & mask));
        return;
    }
    if (M.board.qsound) return;                         /* no sound latch on this board */
    if (address >= 0x800180 && address < 0x800188) {
        latch_write(0, (uint8_t)((mask & 0x00ff) ? data : data >> 8));
        return;
    }
    if (address >= 0x800188 && address < 0x800190) {
        if (mask & 0x00ff) latch_write(1, (uint8_t)data);
        return;
    }
    /* 0x800030 coin counters/lockout and unmapped space: no visible state. */
}

uint16_t cps1_m68k_read16(uint32_t address) { return read_word(address); }
uint8_t cps1_m68k_read8(uint32_t address)
{
    const uint16_t word = read_word(address);
    return (uint8_t)((address & 1) ? word : word >> 8);
}
void cps1_m68k_write16(uint32_t address, uint16_t value) { write_word(address, value, 0xffff); }
void cps1_m68k_write8(uint32_t address, uint8_t value)
{
    if (address & 1) write_word(address, value, 0x00ff);
    else write_word(address, (uint16_t)(value << 8), 0xff00);
}

unsigned m68k_read_memory_8(unsigned address) { return cps1_m68k_read8(address); }
unsigned m68k_read_memory_16(unsigned address) { return cps1_m68k_read16(address); }
unsigned m68k_read_memory_32(unsigned address)
{
    return (unsigned)cps1_m68k_read16(address) << 16 | cps1_m68k_read16(address + 2);
}
void m68k_write_memory_8(unsigned address, unsigned value) { cps1_m68k_write8(address, (uint8_t)value); }
void m68k_write_memory_16(unsigned address, unsigned value) { cps1_m68k_write16(address, (uint16_t)value); }
void m68k_write_memory_32(unsigned address, unsigned value)
{
    cps1_m68k_write16(address, (uint16_t)(value >> 16));
    cps1_m68k_write16(address + 2, (uint16_t)value);
}
#ifdef RR_CPS2
/* The CPS-2 68000 fetches instruction words, extension words and PC-relative operands through its decryption (MAME's `opcodes`
 * space): the decrypted image over the program ROM, the ordinary bus elsewhere. Data reads keep the stored words. */
static unsigned op_word(unsigned address)
{
    address &= 0xfffffe;
    if (address < 0x400000 && M.rom.maincpu_op) return address + 1 < M.rom.maincpu_op_size ? (unsigned)(M.rom.maincpu_op[address] << 8 | M.rom.maincpu_op[address + 1]) : 0;
    return read_word(address);
}
unsigned m68k_read_immediate_16(unsigned address) { return op_word(address); }
unsigned m68k_read_immediate_32(unsigned address) { return op_word(address) << 16 | op_word(address + 2); }
unsigned m68k_read_pcrelative_8(unsigned address) { return op_word(address) >> (8 * (1 - (address & 1))) & 0xff; }
unsigned m68k_read_pcrelative_16(unsigned address) { return (address & 1) ? ((op_word(address - 1) << 8) | (op_word(address + 1) >> 8)) & 0xffff : op_word(address); }
unsigned m68k_read_pcrelative_32(unsigned address)
{
    return (address & 1) ? (op_word(address - 1) << 24) | (op_word(address + 1) << 8) | (op_word(address + 3) >> 8) : op_word(address) << 16 | op_word(address + 2);
}
#endif

unsigned m68k_read_disassembler_8(unsigned address) { return m68k_read_memory_8(address); }
unsigned m68k_read_disassembler_16(unsigned address) { return m68k_read_memory_16(address); }
unsigned m68k_read_disassembler_32(unsigned address) { return m68k_read_memory_32(address); }

/* Interrupt acknowledge clears IPL1/IPL2 and autovectors (MAME irqack_r).
 * The autovector cycle asserts VPA, so the 68000 waits for its E clock
 * (CPU clock / 10) as in MAME's m68000_device::vpa_sync: the access ends on
 * the next E boundary (or the one after when fewer than 3 cycles remain),
 * plus one cycle. iack_offset is where that bus cycle starts within the
 * interrupt sequence; iack_base the cycles a plain bus cycle would take. */
void cps1_m68k_use_cycles(int cycles);
int cps1_m68k_instruction_cycles(void);
int cps1_m68k_entry;   /* set by the patched m68k_execute around its entry check */
static int iack_model = 1, iack_offset = 0, iack_base = 0;

void cps1_set_iack_model(int enabled, int offset, int base)
{
    iack_model = enabled; iack_offset = offset; iack_base = base;
}

#ifdef CPS1_TRACE
static FILE *trace_file;
void cps1_trace_open(const char *path) { trace_file = fopen(path, "w"); }
void cps1_trace_instruction(unsigned pc)
{
    if (trace_file) fprintf(trace_file, "%llX %06X\n", (unsigned long long)m68k_now(), pc & 0xffffff);
}
#endif

int cps1_m68k_int_ack(int level)
{
    (void)level;
    M.irq2 = 0; M.irq4 = 0;
    m68k_set_irq(0);
    if (iack_model) {
        uint64_t now = m68k_now() + (uint64_t)iack_offset;
        if (m68k_running && !cps1_m68k_entry) now += (uint64_t)cps1_m68k_instruction_cycles();
        const uint64_t mod = now % 10;
        const uint64_t done = now - mod + (mod < 7 ? 10 : 20) + 1;
        const int wait = (int)(done - now) - iack_base;
        if (wait > 0) {
            if (m68k_running) cps1_m68k_use_cycles(wait);
            else M.m68k_cycles += (uint64_t)wait;
        }
    }
    return M68K_INT_ACK_AUTOVECTOR;
}

/* ---------------------------------------------------------------- frame */

/* MAME's 68000 samples its interrupt lines at the start of an
 * instruction's last bus cycle (4 cycles before its end): an interrupt
 * raised later than that is seen only after the following instruction
 * (measured on MAME 0.289 traces of these boards). */
#define IRQ_SAMPLE_CYCLES 4

static void vblank(void)
{
    if (M.board.cps2) {
        render_to_row(CPS1_SCREEN_H);
        M.rendered_rows = 0;
        /* the object RAM bank the output registers select and the priority word are latched after the frame is drawn */
        M.pri_ctrl = M.output[CPS2_PRI];
        memcpy(M.obj2, M.objram[M.objram_bank & 1], sizeof M.obj2);
    } else {
        render_frame();
        memcpy(M.buffered_obj, video_base(A_OBJ, 0x800), sizeof M.buffered_obj);
    }
    M.frame_number++;
    if (M.m68k_cycles - M.m68k_target < IRQ_SAMPLE_CYCLES) {
        m68k_running = 1;
        M.m68k_cycles += (uint64_t)m68k_execute(1);
        m68k_running = 0;
    }
    M.irq2 = 1;
    m68k_set_irq(2 | (M.irq4 ? 4 : 0));
}

/* MAME's cps_state::raster_scanline, at the start of line `scanline` of the 262: the two counters reload on line 0 and count down, and a
 * counter reaching zero schedules the interrupt (IPL2) at the position in the line the third register gives. */
static void raster_line(int scanline)
{
    int pending = 0;
    for (int i = 0; i < 2; i++) {
        if (scanline == 0) M.raster_counter[i] = M.raster_reload[i];
        else M.raster_counter[i] = (uint16_t)((M.raster_counter[i] - 1) & 0x1ff);
        if (M.raster_counter[i] == 0) pending = 1;
    }
    M.raster_counter[2] = M.raster_reload[2];
    M.raster_pending = (uint8_t)pending;
}

static void raster_fire(void)
{
    M.irq4 = 1;
    m68k_set_irq(4 | (M.irq2 ? 2 : 0));
    /* the picture is drawn up to this line: what the game's handler changes next applies below it */
    render_to_row(M.line - VISIBLE_Y + 1);
}

static void run_line(void)
{
    M.lines_run++;
    M.line_start = M.m68k_target;
    M.m68k_target = M.lines_run * (uint64_t)M.board.cpu_clock * LINE_PIXELS / PIXEL_CLOCK;
    if (M.board.cps2 && M.raster_pending) {
        uint64_t fire = M.line_start + (uint64_t)M.raster_reload[2] * 2 * M.board.cpu_clock / PIXEL_CLOCK;
        if (fire > M.m68k_target) fire = M.m68k_target;
        while (M.m68k_cycles < fire) {
            m68k_running = 1;
            M.m68k_cycles += (uint64_t)m68k_execute((int)(fire - M.m68k_cycles));
            m68k_running = 0;
        }
        if (M.m68k_cycles - fire < IRQ_SAMPLE_CYCLES) {         /* the 68000 samples its lines before the last cycles of an instruction */
            m68k_running = 1;
            M.m68k_cycles += (uint64_t)m68k_execute(1);
            m68k_running = 0;
        }
        M.raster_pending = 0;
        raster_fire();
    }
    while (M.m68k_cycles < M.m68k_target) {
        m68k_running = 1;
        M.m68k_cycles += (uint64_t)m68k_execute((int)(M.m68k_target - M.m68k_cycles));
        m68k_running = 0;
    }
    const uint64_t z80_target = M.lines_run * (uint64_t)M.board.z80_clock * LINE_PIXELS / PIXEL_CLOCK;
    if (M.board.cps2 && !M.z80_run) {                   /* held in reset: time passes, nothing runs */
        M.z80_clock = z80_target;
        while (M.qsound_irq_clock <= z80_target) M.qsound_irq_clock += QSOUND_IRQ_CLOCKS;
    }
    while (M.z80_clock < z80_target) {
        if (M.board.qsound) {
            if (M.z80_clock >= M.qsound_irq_clock) { z80_pulse_irq(&M.cpu, 0xff); M.qsound_irq_clock += QSOUND_IRQ_CLOCKS; }
        } else latch_apply(M.z80_clock);
        M.z80_clock += z80_step(&M.cpu);
    }
    sound_catch_up();
}

void cps1_run_frame(void)
{
    M.audio_count = 0;
    int drawn = 0;
    do {
        run_line();
        M.line = (M.line + 1) % LINES;
        if (M.board.cps2) raster_line(M.line);
        if (M.line == VBLANK_LINE) { vblank(); drawn = 1; }
    } while (!drawn || M.line != COLOUR_LINE);
    apply_palette();
}

/* ---------------------------------------------------------------- lifetime */

int cps1_init(const cps1_board *board, const cps1_regions *regions)
{
    free(M.audio);
    if (M.opm) cps1_opm_destroy(M.opm);
    memset(&M, 0, sizeof M);
    M.board = *board;
    M.rom = *regions;
    if (M.board.qsound && (!M.rom.dsp_rom || M.rom.dsp_rom_size < CPS1_QSOUND_DSP_BYTES || !M.rom.qsound)) return 0;   /* the player's own DSP ROM and the samples */
    cps1_eeprom_reset(&M.eeprom, eeprom_ticks());
    cps1_eeprom_set_wide(&M.eeprom, M.board.cps2);
    cps1_eeprom_set_clock_khz(&M.eeprom, M.board.cpu_clock / 1000u);
    if (!decode_gfx()) return 0;
    M.opm = cps1_opm_create(opm_irq, NULL);
    if (!M.opm) return 0;
    m68k_init();
    m68k_set_cpu_type(M68K_CPU_TYPE_68000);
    z80_init(&M.cpu);
    M.cpu.read_byte = z80_read;
    M.cpu.write_byte = z80_write;
    M.cpu.port_in = z80_in;
    M.cpu.port_out = z80_out;
    cps1_reset();
    return 1;
}

void cps1_reset(void)
{
    memset(M.ram, 0, sizeof M.ram);
    memset(M.gfxram, 0, sizeof M.gfxram);
    memset(M.cps_a, 0, sizeof M.cps_a);
    memset(M.cps_b, 0, sizeof M.cps_b);
    memset(M.buffered_obj, 0, sizeof M.buffered_obj);
    memset(M.palette, 0, sizeof M.palette);
    memset(M.z80_ram, 0, sizeof M.z80_ram);
    memset(M.qram, 0, sizeof M.qram);
    memset(M.objram, 0, sizeof M.objram);
    memset(M.obj2, 0, sizeof M.obj2);
    memset(M.output, 0, sizeof M.output);
    memset(M.extra_ram, 0, sizeof M.extra_ram);
    M.pri_ctrl = 0; M.objram_bank = 0; M.z80_run = 1;
    memset(M.raster_counter, 0, sizeof M.raster_counter); memset(M.raster_reload, 0, sizeof M.raster_reload);
    M.raster_reload[0] = M.raster_reload[1] = 0x1ff;
    M.raster_pending = 0; M.irq4 = 0; M.rendered_rows = 0; M.line_start = 0;
    {   /* the EEPROM keeps its contents through a reset; its lines start low */
        uint8_t kept[CPS1_EEPROM_BYTES];
        memcpy(kept, M.eeprom.data, sizeof kept);
        cps1_eeprom_reset(&M.eeprom, eeprom_ticks());
        cps1_eeprom_set_wide(&M.eeprom, M.board.cps2);
        cps1_eeprom_set_clock_khz(&M.eeprom, M.board.cpu_clock / 1000u);
        memcpy(M.eeprom.data, kept, sizeof kept);
    }
    M.qsound_irq_clock = QSOUND_IRQ_CLOCKS; M.qsound_done = 0;
    if (M.board.qsound) cps1_qsound_init(&M.qchip, M.rom.dsp_rom, M.rom.qsound, M.rom.qsound_size);
    M.cps_a[A_OBJ] = 0x9200; M.cps_a[A_SCROLL1] = 0x9000; M.cps_a[A_SCROLL2] = 0x9040;
    M.cps_a[A_SCROLL3] = 0x9080; M.cps_a[A_OTHER] = 0x9100;
    for (int i = 0; i < CPS1_PORTS; i++) M.ports[i] = M.board.port_default[i];
    /* The 68000 reset sequence (stack and PC fetches) takes 34 cycles before
     * the first instruction, as MAME's trace of the same boards shows. */
    M.line = 0; M.frame_number = 0; M.lines_run = 0; M.m68k_cycles = M68K_RESET_CYCLES; M.z80_clock = 0;
    M.latch[0] = M.latch[1] = 0; M.latch_count = 0; M.sound_bank = 0; M.irq2 = 0;
    cps1_opm_reset(M.opm);
    M.opm_samples = 0;
    if (!M.board.qsound) cps1_oki_init(&M.oki, M.rom.oki, M.rom.oki_size, 1);
    M.oki_base_clock = M.oki_base_samples = M.oki_samples = 0; M.oki_level = M.oki_previous = 0;
    m68k_set_irq(0);
    m68k_pulse_reset();
    z80_reset(&M.cpu);
    /* MAME's screen starts at the beginning of VBLANK: its first VBLANK
     * interrupt is raised at time 0 (masked by the reset SR) and every
     * later one a whole frame after, as its 68000 traces show. */
    M.line = VBLANK_LINE;
    memcpy(M.buffered_obj, video_base(A_OBJ, 0x800), sizeof M.buffered_obj);
    M.irq2 = 1;
    m68k_set_irq(2);
}

void cps1_shutdown(void)
{
    if (M.opm) cps1_opm_destroy(M.opm);
    free(M.audio);
    free_gfx();
    memset(&M, 0, sizeof M);
}

void cps1_set_port(int port, uint16_t value)
{
    if (port >= 0 && port < CPS1_PORTS) M.ports[port] = value;
}

uint16_t cps1_port_default(int port)
{
    return port >= 0 && port < CPS1_PORTS ? M.board.port_default[port] : 0xffff;
}

const uint32_t *cps1_framebuffer(void) { return M.frame; }
const int16_t *cps1_audio(size_t *samples) { *samples = M.audio_count; return M.audio; }
unsigned cps1_audio_rate(void) { return M.board.qsound ? 24038u : CPS1_AUDIO_RATE; }
unsigned cps1_audio_channels(void) { return M.board.qsound ? 2u : 1u; }
uint64_t cps1_frame_number(void) { return M.frame_number; }

void cps1_cpu_state_get(cps1_cpu_state *state)
{
    state->m68k_pc = m68k_get_reg(NULL, M68K_REG_PC);
    state->m68k_sr = m68k_get_reg(NULL, M68K_REG_SR);
    for (int i = 0; i < 8; i++) {
        state->m68k_d[i] = m68k_get_reg(NULL, (m68k_register_t)(M68K_REG_D0 + i));
        state->m68k_a[i] = m68k_get_reg(NULL, (m68k_register_t)(M68K_REG_A0 + i));
    }
    state->z80_pc = M.cpu.pc; state->z80_sp = M.cpu.sp;
    state->z80_af = M.cpu.af; state->z80_bc = M.cpu.bc; state->z80_de = M.cpu.de; state->z80_hl = M.cpu.hl;
}

static uint64_t fnv(uint64_t hash, const void *data, size_t size)
{
    const uint8_t *bytes = data;
    for (size_t i = 0; i < size; i++) { hash ^= bytes[i]; hash *= 0x100000001b3ull; }
    return hash;
}

const uint8_t *cps1_work_ram(void) { return M.ram; }

/* The EEPROM of the QSound board, for the host to keep between runs. */
size_t cps1_eeprom_size(void) { return M.board.qsound ? CPS1_EEPROM_BYTES : 0; }
const uint8_t *cps1_eeprom_data(void) { return M.board.qsound ? M.eeprom.data : NULL; }
int cps1_eeprom_load(const uint8_t *data, size_t size)
{
    if (!M.board.qsound || size != CPS1_EEPROM_BYTES) return 0;
    memcpy(M.eeprom.data, data, size);
    M.eeprom.changed = 0;
    return 1;
}
int cps1_eeprom_changed(void) { return M.board.qsound && cps1_eeprom_take_changed(&M.eeprom); }

/* Architectural registers and both CPU clocks; never host addresses. */
uint64_t cps1_cpu_hash(void)
{
    uint32_t m68k[22];
    for (int i = 0; i < 16; i++) m68k[i] = m68k_get_reg(NULL, (m68k_register_t)(M68K_REG_D0 + i));
    m68k[16] = m68k_get_reg(NULL, M68K_REG_PC); m68k[17] = m68k_get_reg(NULL, M68K_REG_SR);
    m68k[18] = m68k_get_reg(NULL, M68K_REG_USP); m68k[19] = m68k_get_reg(NULL, M68K_REG_ISP);
    m68k[20] = (uint32_t)M.m68k_cycles; m68k[21] = (uint32_t)M.z80_clock;
    const uint16_t z80_regs[] = {M.cpu.pc, M.cpu.sp, M.cpu.ix, M.cpu.iy, M.cpu.af, M.cpu.bc, M.cpu.de, M.cpu.hl,
                                 M.cpu.a_f_, M.cpu.b_c_, M.cpu.d_e_, M.cpu.h_l_, M.cpu.i, M.cpu.r};
    return fnv(fnv(0xcbf29ce484222325ull, m68k, sizeof m68k), z80_regs, sizeof z80_regs);
}

/* ------------------------------------------------------------- quick states */

#define STATE_MAGIC "CPS1S002"
#define STATE_MAGIC_QSOUND "CPS1Q002"   /* the QSound board saves more: another magic keeps the two apart */
#define STATE_MAGIC_CPS2 "CPS2Q001"     /* the CPS-2 board saves the QSound side and its own video, bank and raster state */
#define state_magic() (M.board.cps2 ? STATE_MAGIC_CPS2 : M.board.qsound ? STATE_MAGIC_QSOUND : STATE_MAGIC)
/* the CPS-2 board's own state, after the QSound side: the two object RAM banks and the latched copy, the output registers, the
 * priorities, the bank and Z80 reset lines, the extra RAM, the raster counters and the partial-picture bookkeeping */
#define CPS2_TAIL_BYTES (sizeof M.objram + sizeof M.obj2 + sizeof M.output + sizeof M.pri_ctrl + 2 + sizeof M.extra_ram + \
                         sizeof M.raster_counter + sizeof M.raster_reload + 2 + 4 + 8)
unsigned cps1_m68k_state_bytes(void);
void cps1_m68k_state_get(void *dst);
void cps1_m68k_state_set(const void *src);
typedef struct { uint8_t *data; size_t size, used; int overflow; } writer_t;
static void put(writer_t *w, const void *data, size_t size)
{
    if (w->data && w->used + size <= w->size) memcpy(w->data + w->used, data, size);
    else if (w->data) w->overflow = 1;
    w->used += size;
}
typedef struct { const uint8_t *data; size_t size, used; int bad; } reader_t;
static void get(reader_t *r, void *data, size_t size)
{
    if (r->used + size > r->size) { r->bad = 1; return; }
    memcpy(data, r->data + r->used, size);
    r->used += size;
}

/* Every byte of a state is defined by construction: arrays of plain integers
 * are written as they are, and every structure (the Z80, the sound-latch queue,
 * the OKI voices, the 68000 register block) is written field by field in
 * little-endian order or as a bounded range of fields, so neither compiler
 * padding, unused bit-field bits nor host pointers ever reach the file (the
 * rule of the X68000 state, native/x68000_machine/state/rr_state.h). */
static void put_le(writer_t *w, uint64_t value, unsigned bytes)
{
    uint8_t buffer[8];
    for (unsigned n = 0; n < bytes; n++) buffer[n] = (uint8_t)(value >> (8 * n));
    put(w, buffer, bytes);
}
static uint64_t get_le(reader_t *r, unsigned bytes)
{
    uint8_t buffer[8] = {0};
    uint64_t value = 0;
    get(r, buffer, bytes);
    for (unsigned n = 0; n < bytes; n++) value |= (uint64_t)buffer[n] << (8 * n);
    return value;
}

/* Z80 registers and flags, 34 bytes; callbacks stay those of the running machine. */
static void z80_state_put(writer_t *w, const z80 *z)
{
    const uint16_t words[] = {z->pc, z->sp, z->ix, z->iy, z->mem_ptr, z->af, z->bc, z->de, z->hl,
                              z->a_f_, z->b_c_, z->d_e_, z->h_l_};
    for (size_t n = 0; n < sizeof words / sizeof words[0]; n++) put_le(w, words[n], 2);
    const uint8_t bytes[] = {z->i, z->r, z->iff_delay, z->interrupt_mode, z->irq_data, z->irq_pending, z->nmi_pending,
                             (uint8_t)((z->iff1 ? 1 : 0) | (z->iff2 ? 2 : 0) | (z->halted ? 4 : 0))};
    put(w, bytes, sizeof bytes);
}
static void z80_state_get(reader_t *r, z80 *z)
{
    uint16_t words[13];
    uint8_t bytes[8];
    for (size_t n = 0; n < sizeof words / sizeof words[0]; n++) words[n] = (uint16_t)get_le(r, 2);
    get(r, bytes, sizeof bytes);
    if (r->bad || bytes[3] > 2 || (bytes[7] & ~7u)) { r->bad = 1; return; }
    z->pc = words[0]; z->sp = words[1]; z->ix = words[2]; z->iy = words[3]; z->mem_ptr = words[4];
    z->af = words[5]; z->bc = words[6]; z->de = words[7]; z->hl = words[8];
    z->a_f_ = words[9]; z->b_c_ = words[10]; z->d_e_ = words[11]; z->h_l_ = words[12];
    z->i = bytes[0]; z->r = bytes[1]; z->iff_delay = bytes[2]; z->interrupt_mode = bytes[3];
    z->irq_data = bytes[4]; z->irq_pending = bytes[5]; z->nmi_pending = bytes[6];
    z->iff1 = (bytes[7] & 1) != 0; z->iff2 = (bytes[7] & 2) != 0; z->halted = (bytes[7] & 4) != 0;
}
static void latch_queue_put(writer_t *w, const latch_event *queue)
{
    for (int n = 0; n < LATCH_QUEUE; n++) {
        put_le(w, queue[n].time, 8); put_le(w, queue[n].which, 1); put_le(w, queue[n].value, 1);
    }
}
static void latch_queue_get(reader_t *r, latch_event *queue)
{
    for (int n = 0; n < LATCH_QUEUE; n++) {
        queue[n].time = get_le(r, 8); queue[n].which = (uint8_t)get_le(r, 1); queue[n].value = (uint8_t)get_le(r, 1);
    }
}
static void oki_voices_put(writer_t *w, const cps1_oki_voice *voice)
{
    for (int n = 0; n < 4; n++) {
        put_le(w, voice[n].playing, 1); put_le(w, voice[n].base, 4); put_le(w, voice[n].sample, 4);
        put_le(w, voice[n].count, 4); put_le(w, (uint32_t)voice[n].signal, 4);
        put_le(w, (uint32_t)voice[n].step, 4); put_le(w, (uint32_t)voice[n].volume, 4);
    }
}
static void oki_voices_get(reader_t *r, cps1_oki_voice *voice)
{
    for (int n = 0; n < 4; n++) {
        voice[n].playing = (uint8_t)get_le(r, 1); voice[n].base = (uint32_t)get_le(r, 4);
        voice[n].sample = (uint32_t)get_le(r, 4); voice[n].count = (uint32_t)get_le(r, 4);
        voice[n].signal = (int32_t)(uint32_t)get_le(r, 4); voice[n].step = (int32_t)(uint32_t)get_le(r, 4);
        voice[n].volume = (int32_t)(uint32_t)get_le(r, 4);
    }
}

/* Plain integers and integer arrays in a fixed order (structures and pointers
 * go through the helpers above or stay out); host pointers (ROM, callbacks,
 * audio buffer) are never written and are kept from the running machine on load. */
#define STATE_FIELDS_BEFORE_QUEUE(X) \
    X(M.ram) X(M.gfxram) X(M.cps_a) X(M.cps_b) X(M.buffered_obj) X(M.palette) X(M.ports) \
    X(M.frame) X(M.line) X(M.frame_number) X(M.lines_run) X(M.m68k_cycles) X(M.m68k_target) \
    X(M.z80_ram) X(M.latch) X(M.sound_bank)
#define STATE_FIELDS_BEFORE_VOICES(X) \
    X(M.latch_count) X(M.z80_clock) X(M.opm_samples) X(M.oki.command) X(M.oki.pin7)
#define STATE_FIELDS_AFTER_VOICES(X) \
    X(M.oki_base_clock) X(M.oki_base_samples) X(M.oki_samples) X(M.oki_level) X(M.oki_previous) X(M.irq2)

size_t cps1_state_save(uint8_t *buffer, size_t capacity)
{
    writer_t w = {buffer, capacity, 0, 0};
    put(&w, state_magic(), 8);
#define SAVE(field) put(&w, &field, sizeof field);
    STATE_FIELDS_BEFORE_QUEUE(SAVE)
    latch_queue_put(&w, M.latch_queue);
    STATE_FIELDS_BEFORE_VOICES(SAVE)
    oki_voices_put(&w, M.oki.voice);
    STATE_FIELDS_AFTER_VOICES(SAVE)
#undef SAVE
    z80_state_put(&w, &M.cpu);
    uint32_t context_size = cps1_m68k_state_bytes();
    put(&w, &context_size, sizeof context_size);
    uint8_t *context = malloc(context_size);
    if (!context) return 0;
    cps1_m68k_state_get(context);
    put(&w, context, context_size);
    free(context);
    uint32_t opm_size = (uint32_t)cps1_opm_save(M.opm, NULL, 0);
    put(&w, &opm_size, sizeof opm_size);
    uint8_t *opm = malloc(opm_size ? opm_size : 1);
    if (!opm || cps1_opm_save(M.opm, opm, opm_size) != opm_size) { free(opm); return 0; }
    put(&w, opm, opm_size);
    free(opm);
    if (M.board.qsound) {
        uint8_t eeprom[CPS1_EEPROM_STATE_BYTES];
        put(&w, M.qram, sizeof M.qram);
        cps1_eeprom_state_put(&M.eeprom, eeprom);
        put(&w, eeprom, sizeof eeprom);
        put_le(&w, M.qsound_irq_clock, 8); put_le(&w, M.qsound_done, 8);
        uint8_t *chip = malloc(cps1_qsound_state_bytes());
        if (!chip) return 0;
        put(&w, chip, cps1_qsound_state_put(&M.qchip, chip));
        free(chip);
    }
    if (M.board.cps2) {
        put(&w, M.objram, sizeof M.objram); put(&w, M.obj2, sizeof M.obj2); put(&w, M.output, sizeof M.output);
        put(&w, &M.pri_ctrl, sizeof M.pri_ctrl); put(&w, &M.objram_bank, 1); put(&w, &M.z80_run, 1);
        put(&w, M.extra_ram, sizeof M.extra_ram); put(&w, M.raster_counter, sizeof M.raster_counter);
        put(&w, M.raster_reload, sizeof M.raster_reload); put(&w, &M.raster_pending, 1); put(&w, &M.irq4, 1);
        put_le(&w, (uint32_t)M.rendered_rows, 4); put_le(&w, M.line_start, 8);
    }
    if (!buffer) return w.used;
    return w.overflow ? 0 : w.used;
}

int cps1_state_load(const uint8_t *buffer, size_t size)
{
    reader_t r = {buffer, size, 0, 0};
    char magic[8];
    get(&r, magic, 8);
    if (r.bad || memcmp(magic, state_magic(), 8)) return 0;
    /* Read into a copy first so a truncated or foreign state leaves the
     * running machine untouched. */
    static uint8_t ram[sizeof M.ram], gfxram[sizeof M.gfxram];
    uint16_t cps_a[0x20], cps_b[0x20], obj[OBJ_WORDS], ports[CPS1_PORTS];
    static uint32_t palette[CPS1_PALETTE_SIZE], frame[CPS1_SCREEN_W * CPS1_SCREEN_H];
    int line, latch_count, irq2;
    uint64_t frame_number, lines_run, m68k_cycles, m68k_target, z80_clock, opm_samples;
    uint8_t z80_ram[sizeof M.z80_ram], latch[2], sound_bank;
    latch_event queue[LATCH_QUEUE];
    cps1_oki oki = M.oki;
    uint64_t oki_base_clock, oki_base_samples, oki_samples;
    int32_t oki_level, oki_previous;
    get(&r, ram, sizeof ram); get(&r, gfxram, sizeof gfxram); get(&r, cps_a, sizeof cps_a);
    get(&r, cps_b, sizeof cps_b); get(&r, obj, sizeof obj); get(&r, palette, sizeof palette);
    get(&r, ports, sizeof ports); get(&r, frame, sizeof frame); get(&r, &line, sizeof line);
    get(&r, &frame_number, sizeof frame_number); get(&r, &lines_run, sizeof lines_run);
    get(&r, &m68k_cycles, sizeof m68k_cycles); get(&r, &m68k_target, sizeof m68k_target);
    get(&r, z80_ram, sizeof z80_ram); get(&r, latch, sizeof latch); get(&r, &sound_bank, sizeof sound_bank);
    latch_queue_get(&r, queue);
    get(&r, &latch_count, sizeof latch_count); get(&r, &z80_clock, sizeof z80_clock);
    get(&r, &opm_samples, sizeof opm_samples); get(&r, &oki.command, sizeof oki.command);
    get(&r, &oki.pin7, sizeof oki.pin7);
    oki_voices_get(&r, oki.voice);
    get(&r, &oki_base_clock, sizeof oki_base_clock); get(&r, &oki_base_samples, sizeof oki_base_samples);
    get(&r, &oki_samples, sizeof oki_samples); get(&r, &oki_level, sizeof oki_level);
    get(&r, &oki_previous, sizeof oki_previous); get(&r, &irq2, sizeof irq2);
    z80 cpu = M.cpu;                            /* keeps the callbacks of the running machine */
    z80_state_get(&r, &cpu);
    uint32_t context_size = 0, opm_size = 0;
    get(&r, &context_size, sizeof context_size);
    if (r.bad || context_size != cps1_m68k_state_bytes() || r.used + context_size > size) return 0;
    const uint8_t *context = buffer + r.used;
    r.used += context_size;
    get(&r, &opm_size, sizeof opm_size);
    const size_t qsound_bytes = (M.board.qsound ? sizeof M.qram + CPS1_EEPROM_STATE_BYTES + 16 + cps1_qsound_state_bytes() : 0) +
                                (M.board.cps2 ? CPS2_TAIL_BYTES : 0);
    if (r.bad || r.used + opm_size + qsound_bytes != size || line < 0 || line >= LINES || latch_count < 0 ||
        latch_count > LATCH_QUEUE || sound_bank > (M.board.cps2 ? 15 : M.board.qsound ? 5 : 1) || oki.pin7 > 1) return 0;
    for (int i = 0; i < 4; i++)
        if (oki.voice[i].step < 0 || oki.voice[i].step > 48) return 0;
    uint8_t qram[2][QSOUND_SHARED] = {{0}};
    cps1_eeprom eeprom = {{0}};
    uint64_t qsound_irq_clock = 0, qsound_done = 0;
    cps1_qsound chip = M.qchip;
    static uint16_t objram[2][0x1000], obj2[0x1000];
    uint16_t output[6], pri_ctrl = 0, raster_counter[3], raster_reload[3];
    static uint8_t extra_ram[sizeof M.extra_ram];
    uint8_t objram_bank = 0, z80_run = 1, raster_pending = 0, irq4 = 0;
    int rendered_rows = 0;
    uint64_t line_start = 0;
    if (M.board.qsound) {
        const uint8_t *extra = buffer + r.used + opm_size;
        memcpy(qram, extra, sizeof qram);
        eeprom.wide = M.eeprom.wide; eeprom.khz = M.eeprom.khz;
        if (!cps1_eeprom_state_get(&eeprom, extra + sizeof qram, eeprom_ticks())) return 0;
        /* what the state holds and the EEPROM kept differ: the game's next save must write what is now the EEPROM's */
        if (memcmp(eeprom.data, M.eeprom.data, CPS1_EEPROM_BYTES)) eeprom.changed = 1;
        reader_t tail = {extra + sizeof qram + CPS1_EEPROM_STATE_BYTES, 16 + cps1_qsound_state_bytes(), 0, 0};
        qsound_irq_clock = get_le(&tail, 8); qsound_done = get_le(&tail, 8);
        if (!cps1_qsound_state_get(&chip, tail.data + tail.used)) return 0;
        if (M.board.cps2) {
            reader_t more = {tail.data + tail.used + cps1_qsound_state_bytes(), CPS2_TAIL_BYTES, 0, 0};
            get(&more, objram, sizeof objram); get(&more, obj2, sizeof obj2); get(&more, output, sizeof output);
            get(&more, &pri_ctrl, sizeof pri_ctrl); get(&more, &objram_bank, 1); get(&more, &z80_run, 1);
            get(&more, extra_ram, sizeof extra_ram); get(&more, raster_counter, sizeof raster_counter);
            get(&more, raster_reload, sizeof raster_reload); get(&more, &raster_pending, 1); get(&more, &irq4, 1);
            rendered_rows = (int)get_le(&more, 4); line_start = get_le(&more, 8);
            if (more.bad || objram_bank > 1 || z80_run > 1 || raster_pending > 1 || irq4 > 1 || rendered_rows < 0 ||
                rendered_rows > CPS1_SCREEN_H) return 0;
        }
    }
    if (!cps1_opm_load(M.opm, buffer + r.used, opm_size)) return 0;
    memcpy(M.ram, ram, sizeof ram); memcpy(M.gfxram, gfxram, sizeof gfxram);
    memcpy(M.cps_a, cps_a, sizeof cps_a); memcpy(M.cps_b, cps_b, sizeof cps_b);
    memcpy(M.buffered_obj, obj, sizeof obj); memcpy(M.palette, palette, sizeof palette);
    memcpy(M.ports, ports, sizeof ports); memcpy(M.frame, frame, sizeof frame);
    M.line = line; M.frame_number = frame_number; M.lines_run = lines_run;
    M.m68k_cycles = m68k_cycles; M.m68k_target = m68k_target;
    memcpy(M.z80_ram, z80_ram, sizeof z80_ram); memcpy(M.latch, latch, sizeof latch);
    M.sound_bank = sound_bank; memcpy(M.latch_queue, queue, sizeof queue); M.latch_count = latch_count;
    M.z80_clock = z80_clock; M.opm_samples = opm_samples;
    M.oki = oki; M.oki_base_clock = oki_base_clock; M.oki_base_samples = oki_base_samples;
    M.oki_samples = oki_samples; M.oki_level = oki_level; M.oki_previous = oki_previous; M.irq2 = irq2;
    M.cpu = cpu;
    if (M.board.qsound) {
        memcpy(M.qram, qram, sizeof qram); M.eeprom = eeprom;
        M.qsound_irq_clock = qsound_irq_clock; M.qsound_done = qsound_done; M.qchip = chip;
    }
    if (M.board.cps2) {
        memcpy(M.objram, objram, sizeof objram); memcpy(M.obj2, obj2, sizeof obj2); memcpy(M.output, output, sizeof output);
        M.pri_ctrl = pri_ctrl; M.objram_bank = objram_bank; M.z80_run = z80_run; memcpy(M.extra_ram, extra_ram, sizeof extra_ram);
        memcpy(M.raster_counter, raster_counter, sizeof raster_counter); memcpy(M.raster_reload, raster_reload, sizeof raster_reload);
        M.raster_pending = raster_pending; M.irq4 = irq4; M.rendered_rows = rendered_rows; M.line_start = line_start;
    }
    cps1_m68k_state_set(context);
#ifdef CPS1_NATIVE
    { extern void rr_cps1_native_discontinuity(void); rr_cps1_native_discontinuity(); }
#endif
    M.audio_count = 0;
    return 1;
}

/* ------------------------------------------------- native code view/fallback */

/* Side-effect-free code mapping for the native guards. Program ROM is
 * immutable; work RAM and GFX RAM code is guarded per variant (GFX RAM holds
 * host-order words, so its bytes are a big-endian copy of the next few
 * words); every other space stays interpreted (and counted). */
#define CODE_GFX 4
#define CODE_WINDOW_BYTES 16u
const uint8_t *rr_cps1_code_bytes(uint32_t address, uint32_t *region, uint32_t *offset, unsigned *available)
{
    address &= 0xffffffu;
    if (address & 1) return NULL;
    if (address < 0x400000u) {
        /* the CPS-2 translates, and checks, the decrypted image: that is what its instruction fetches see */
        const uint8_t *image = M.rom.maincpu_op ? M.rom.maincpu_op : M.rom.maincpu;
        const size_t size = M.rom.maincpu_op ? M.rom.maincpu_op_size : M.rom.maincpu_size;
        if (address + 2 > size) return NULL;
        *region = 1; *offset = address; *available = (unsigned)(size - address);
        return image + address;
    }
    if (address >= 0xff0000u) {
        *region = 3; *offset = address & 0xffffu; *available = 0x10000u - *offset;
        return M.ram + *offset;
    }
    if (address >= 0x900000u && address < 0x900000u + GFXRAM_BYTES) {
        /* One window for the caller's current instruction: code_word() never touches it. */
        static uint8_t window[CODE_WINDOW_BYTES];
        const uint32_t base = address - 0x900000u;
        unsigned count = GFXRAM_BYTES - base;
        if (count > CODE_WINDOW_BYTES) count = CODE_WINDOW_BYTES;
        for (unsigned n = 0; n < count / 2; n++) {
            const uint16_t value = M.gfxram[base / 2 + n];
            window[2 * n] = (uint8_t)(value >> 8); window[2 * n + 1] = (uint8_t)value;
        }
        *region = CODE_GFX; *offset = base; *available = count;
        return window;
    }
    return NULL;
}

int rr_cps1_code_word(uint32_t pc, uint16_t *word)
{
    pc &= 0xffffffu;
    if (pc >= 0x900000u && pc < 0x900000u + GFXRAM_BYTES && !(pc & 1)) {
        *word = M.gfxram[(pc - 0x900000u) / 2];
        return 1;
    }
    uint32_t region, offset; unsigned available;
    const uint8_t *bytes = rr_cps1_code_bytes(pc, &region, &offset, &available);
    if (!bytes || available < 2) return 0;
    *word = (uint16_t)(bytes[0] << 8 | bytes[1]);
    return 1;
}

int rr_cps1_z80_code_location(uint16_t pc, uint32_t *offset)
{
    if (pc < 0x8000) *offset = pc;
    else if (pc < 0xc000) *offset = 0x10000u + (uint32_t)M.sound_bank * 0x4000u + (pc - 0x8000u);
    else return 0;
    return *offset < M.rom.audiocpu_size;
}

int rr_cps1_z80_code_byte(uint16_t pc, uint8_t *byte)
{
    uint32_t offset;
    if (rr_cps1_z80_code_location(pc, &offset)) { *byte = M.rom.audiocpu[offset]; return 1; }
    if (pc >= 0xd000 && pc < 0xd800) { *byte = M.z80_ram[pc - 0xd000]; return 1; }
    return 0;
}

/* The sound ROM of a Kabuki board is read twice: instruction fetches (M1) see the opcode image, data reads the data image
 * (retrorecomp/cps1_kabuki.py). Without an opcode image both answer alike, so no other board changes. */
uint8_t rr_cps1_z80_read_op(uint16_t address)
{
    if (address < 0x8000 && M.rom.audiocpu_op) return address < M.rom.audiocpu_op_size ? M.rom.audiocpu_op[address] : 0;
    return z80_read(NULL, address);
}

int rr_cps1_z80_code_byte_m1(uint16_t pc, int m1, uint8_t *byte)
{
    if (m1 && pc < 0x8000 && M.rom.audiocpu_op && pc < M.rom.audiocpu_op_size) { *byte = M.rom.audiocpu_op[pc]; return 1; }
    return rr_cps1_z80_code_byte(pc, byte);
}

/* Interpreted instructions on a native build, with the RAM code they ran
 * (bounded); the converter turns RAM variants into guarded native code. */
#define MISS_SLOTS 8192
#define RAM_VARIANTS 4096
typedef struct { uint32_t pc; uint16_t word; uint64_t count; } miss_t;
/* offset: work RAM offset, or GFX RAM offset (up to 0x2ffff) in gfx_variants. */
typedef struct { uint32_t offset; uint16_t count; uint16_t words[8]; } ram_variant_t;
typedef struct { uint16_t pc; uint8_t bytes[4]; } z80_variant_t;
static miss_t m68k_misses[MISS_SLOTS], z80_misses[MISS_SLOTS];
static ram_variant_t ram_variants[RAM_VARIANTS], gfx_variants[RAM_VARIANTS];
static z80_variant_t z80_variants[RAM_VARIANTS];
static unsigned ram_variant_count, gfx_variant_count, z80_variant_count, misses_truncated;
uint64_t rr_cps1_interpreted_68k, rr_cps1_interpreted_z80, rr_cps1_native_z80;
int rr_cps1_force_z80_reference;
/* Qualification runs record every miss; ordinary play only counts them (and
 * hands them to the opt-in runtime feedback when a game links it). */
int rr_cps1_observe = 1;
#ifdef CPS1_FEEDBACK
#include "runtime_feedback.h"
/* The CPS-2 game has record kinds of its own (17 to 19), the three of the CPS-1 shifted by three. */
#ifdef RR_CPS2
#define FB_KIND(kind) ((kind) + 3)
#else
#define FB_KIND(kind) (kind)
#endif
#endif

static void note_miss(miss_t *table, uint32_t pc, uint16_t word)
{
    for (unsigned n = 0, slot = (pc * 2654435761u) % MISS_SLOTS; n < 64; n++, slot = (slot + 1) % MISS_SLOTS) {
        if (!table[slot].count) { table[slot] = (miss_t){pc, word, 1}; return; }
        if (table[slot].pc == pc && table[slot].word == word) { table[slot].count++; return; }
    }
    misses_truncated = 1;
}

void rr_cps1_note_instruction(uint32_t pc, int native)
{
    if (native) return;
    rr_cps1_interpreted_68k++;
#ifdef CPS1_FEEDBACK
    if (rr_feedback_enabled()) {
        uint32_t region, offset; unsigned available;
        const uint8_t *bytes = rr_cps1_code_bytes(pc, &region, &offset, &available);
        if (bytes && available >= 2 && region != CODE_GFX)
            rr_feedback_note(FB_KIND(region == 3 ? RR_FB_CPS1_RAM : RR_FB_CPS1_ROM), offset, 0, bytes,
                             region == 3 ? (available < 16 ? available & ~1u : 16) : 2);
    }
#endif
    if (!rr_cps1_observe) return;
    uint16_t word = 0;
    rr_cps1_code_word(pc, &word);
    note_miss(m68k_misses, pc & 0xffffffu, word);
    const uint32_t code = pc & 0xffffffu;
    const int gfx = code >= 0x900000u && code < 0x900000u + GFXRAM_BYTES;
    if ((code < 0xff0000u && !gfx) || (pc & 1)) return;
    ram_variant_t value = {0};
    value.offset = gfx ? code - 0x900000u : code & 0xffffu;
    for (unsigned n = 0; n < 8 && rr_cps1_code_word(pc + 2 * n, &value.words[n]); n++) value.count++;
    ram_variant_t *table = gfx ? gfx_variants : ram_variants;
    unsigned *count = gfx ? &gfx_variant_count : &ram_variant_count;
    for (unsigned n = 0; n < *count; n++)
        if (table[n].offset == value.offset && table[n].count == value.count &&
            !memcmp(table[n].words, value.words, value.count * 2)) return;
    if (*count < RAM_VARIANTS) table[(*count)++] = value;
    else misses_truncated = 1;
}

void rr_cps1_z80_note_fallback(uint16_t pc)
{
    rr_cps1_interpreted_z80++;
#ifdef CPS1_FEEDBACK
    if (rr_feedback_enabled()) {
        uint8_t bytes[4] = {0};
        for (unsigned n = 0; n < 4; n++) rr_cps1_z80_code_byte((uint16_t)(pc + n), &bytes[n]);
        rr_cps1_z80_code_byte_m1(pc, 1, &bytes[0]);
        rr_feedback_note(FB_KIND(RR_FB_CPS1_Z80), pc, 0, bytes, 4);
    }
#endif
    if (!rr_cps1_observe) return;
    uint8_t first = 0;
    rr_cps1_z80_code_byte_m1(pc, 1, &first);
    note_miss(z80_misses, pc, first);
    if (pc < 0xd000 || pc >= 0xd800) return;
    z80_variant_t value = {pc, {0}};
    for (unsigned n = 0; n < 4; n++) rr_cps1_z80_code_byte((uint16_t)(pc + n), &value.bytes[n]);
    for (unsigned n = 0; n < z80_variant_count; n++)
        if (z80_variants[n].pc == pc && !memcmp(z80_variants[n].bytes, value.bytes, 4)) return;
    if (z80_variant_count < RAM_VARIANTS) z80_variants[z80_variant_count++] = value;
    else misses_truncated = 1;
}

void cps1_fallback_report(FILE *file)
{
#ifdef CPS1_NATIVE
    extern uint64_t rr_cps1_native_instructions;
#else
    const uint64_t rr_cps1_native_instructions = 0;
#endif
    fprintf(file, "{\"m68k_native\":%llu,\"m68k_interpreted\":%llu,\"z80_native\":%llu,\"z80_interpreted\":%llu,"
                  "\"truncated\":%s,\"m68k_misses\":[", (unsigned long long)rr_cps1_native_instructions,
            (unsigned long long)rr_cps1_interpreted_68k, (unsigned long long)rr_cps1_native_z80,
            (unsigned long long)rr_cps1_interpreted_z80, misses_truncated ? "true" : "false");
    int comma = 0;
    for (unsigned n = 0; n < MISS_SLOTS; n++)
        if (m68k_misses[n].count) {
            fprintf(file, "%s{\"pc\":%u,\"word\":%u,\"count\":%llu}", comma ? "," : "", m68k_misses[n].pc,
                    m68k_misses[n].word, (unsigned long long)m68k_misses[n].count);
            comma = 1;
        }
    fprintf(file, "],\"z80_misses\":[");
    comma = 0;
    for (unsigned n = 0; n < MISS_SLOTS; n++)
        if (z80_misses[n].count) {
            fprintf(file, "%s{\"pc\":%u,\"byte\":%u,\"count\":%llu}", comma ? "," : "", z80_misses[n].pc,
                    z80_misses[n].word, (unsigned long long)z80_misses[n].count);
            comma = 1;
        }
    fprintf(file, "],\"m68k_ram\":[");
    for (unsigned n = 0; n < ram_variant_count; n++) {
        fprintf(file, "%s{\"offset\":%u,\"words\":\"", n ? "," : "", (unsigned)ram_variants[n].offset);
        for (unsigned w = 0; w < ram_variants[n].count; w++) fprintf(file, "%04x", ram_variants[n].words[w]);
        fputs("\"}", file);
    }
    fprintf(file, "],\"m68k_gfx\":[");
    for (unsigned n = 0; n < gfx_variant_count; n++) {
        fprintf(file, "%s{\"offset\":%u,\"words\":\"", n ? "," : "", (unsigned)gfx_variants[n].offset);
        for (unsigned w = 0; w < gfx_variants[n].count; w++) fprintf(file, "%04x", gfx_variants[n].words[w]);
        fputs("\"}", file);
    }
    fprintf(file, "],\"z80_ram\":[");
    for (unsigned n = 0; n < z80_variant_count; n++)
        fprintf(file, "%s{\"address\":%u,\"bytes\":\"%02x%02x%02x%02x\"}", n ? "," : "", z80_variants[n].pc,
                z80_variants[n].bytes[0], z80_variants[n].bytes[1], z80_variants[n].bytes[2], z80_variants[n].bytes[3]);
    fputs("]}\n", file);
}

uint64_t cps1_ram_hash(void)
{
    uint64_t hash = 0xcbf29ce484222325ull;
    hash = fnv(hash, M.ram, sizeof M.ram);
    hash = fnv(hash, M.gfxram, GFXRAM_BYTES);
    hash = fnv(hash, M.z80_ram, sizeof M.z80_ram);
    if (M.board.qsound) hash = fnv(hash, M.qram, sizeof M.qram);
    return hash;
}
