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
    if (version != 1 || !board->set[0] || (board->cpu_clock != 10000000u && board->cpu_clock != 12000000u) ||
        !board->range_count || board->kludge) {
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
static void sound_catch_up(void)
{
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

static uint8_t z80_read(void *context, uint16_t address)
{
    (void)context;
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

static int decode_gfx(void)
{
    free_gfx();
    const size_t groups = M.rom.gfx_size / 4, sprites = M.rom.gfx_size / 128;
    if (!groups) return 1;
    gfx_pens = malloc(groups * 8);
    sprite_blank = malloc(sprites ? sprites : 1);
    if (!gfx_pens || !sprite_blank) { free_gfx(); return 0; }
    for (size_t g = 0; g < groups; g++) {
        const uint8_t *p = M.rom.gfx + g * 4;
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
    for (int y = 0; y < CPS1_SCREEN_H; y++) {
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
                    if (pen != 15) pens[x + k] = (uint16_t)(colour + pen);
                }
            }
            x += run;
        }
    }
}

static void draw_sprite(int code, int color, int flipx, int flipy, int sx, int sy)
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
        if (raster_y < VISIBLE_Y || raster_y >= VISIBLE_Y + CPS1_SCREEN_H) continue;
        const uint8_t *src = tile_row(16, 0, code, flipy ? 15 - y : y);
        const int line = (raster_y - VISIBLE_Y) * CPS1_SCREEN_W + sx - VISIBLE_X;
        for (int x = x0; x < x1; x++) {
            const int pen = src[flipx ? 15 - x : x];
            if (pen == 15) continue;
            const int at = line + x;
            /* MAME prio_transpen with pmask 0x02 plus its implicit bit 31: a
             * high tile (1) or an earlier sprite (31) keeps the pixel, so the
             * first sprite of the list stays on top. */
            if (!((1u << (M.priority[at] & 0x1f)) & 0x80000002u)) M.pens[at] = (uint16_t)(colour + pen);
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
                    draw_sprite((code & ~0xf) + column + row, col, flipx, flipy, sx, sy);
                }
            }
        } else {
            draw_sprite(code, col, flipx, flipy, x & 0x1ff, y & 0x1ff);
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

/* ---------------------------------------------------------------- 68000 bus */

static uint16_t cps_b_read(int offset)
{
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

static uint16_t read_word(uint32_t address)
{
    address &= 0xfffffe;
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

static void write_word(uint32_t address, uint16_t data, uint16_t mask)
{
    address &= 0xfffffe;
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
    M.irq2 = 0;
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
    render_frame();
    memcpy(M.buffered_obj, video_base(A_OBJ, 0x800), sizeof M.buffered_obj);
    M.frame_number++;
    if (M.m68k_cycles - M.m68k_target < IRQ_SAMPLE_CYCLES) {
        m68k_running = 1;
        M.m68k_cycles += (uint64_t)m68k_execute(1);
        m68k_running = 0;
    }
    M.irq2 = 1;
    m68k_set_irq(2);
}

static void run_line(void)
{
    M.lines_run++;
    M.m68k_target = M.lines_run * (uint64_t)M.board.cpu_clock * LINE_PIXELS / PIXEL_CLOCK;
    while (M.m68k_cycles < M.m68k_target) {
        m68k_running = 1;
        M.m68k_cycles += (uint64_t)m68k_execute((int)(M.m68k_target - M.m68k_cycles));
        m68k_running = 0;
    }
    const uint64_t z80_target = M.lines_run * (uint64_t)CPS1_YM_CLOCK * LINE_PIXELS / PIXEL_CLOCK;
    while (M.z80_clock < z80_target) {
        latch_apply(M.z80_clock);
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
    M.cps_a[A_OBJ] = 0x9200; M.cps_a[A_SCROLL1] = 0x9000; M.cps_a[A_SCROLL2] = 0x9040;
    M.cps_a[A_SCROLL3] = 0x9080; M.cps_a[A_OTHER] = 0x9100;
    for (int i = 0; i < CPS1_PORTS; i++) M.ports[i] = M.board.port_default[i];
    /* The 68000 reset sequence (stack and PC fetches) takes 34 cycles before
     * the first instruction, as MAME's trace of the same boards shows. */
    M.line = 0; M.frame_number = 0; M.lines_run = 0; M.m68k_cycles = M68K_RESET_CYCLES; M.z80_clock = 0;
    M.latch[0] = M.latch[1] = 0; M.latch_count = 0; M.sound_bank = 0; M.irq2 = 0;
    cps1_opm_reset(M.opm);
    M.opm_samples = 0;
    cps1_oki_init(&M.oki, M.rom.oki, M.rom.oki_size, 1);
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

#define STATE_MAGIC "CPS1S001"
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

/* Fields in a fixed order; host pointers (ROM, callbacks, audio buffer) are
 * never written and are kept from the running machine on load. */
#define STATE_FIELDS(X) \
    X(M.ram) X(M.gfxram) X(M.cps_a) X(M.cps_b) X(M.buffered_obj) X(M.palette) X(M.ports) \
    X(M.frame) X(M.line) X(M.frame_number) X(M.lines_run) X(M.m68k_cycles) X(M.m68k_target) \
    X(M.z80_ram) X(M.latch) X(M.sound_bank) X(M.latch_queue) X(M.latch_count) X(M.z80_clock) \
    X(M.opm_samples) X(M.oki.command) X(M.oki.pin7) X(M.oki.voice) X(M.oki_base_clock) \
    X(M.oki_base_samples) X(M.oki_samples) X(M.oki_level) X(M.oki_previous) X(M.irq2)

size_t cps1_state_save(uint8_t *buffer, size_t capacity)
{
    writer_t w = {buffer, capacity, 0, 0};
    put(&w, STATE_MAGIC, 8);
#define SAVE(field) put(&w, &field, sizeof field);
    STATE_FIELDS(SAVE)
#undef SAVE
    z80 cpu = M.cpu;
    cpu.read_byte = NULL; cpu.write_byte = NULL; cpu.port_in = NULL; cpu.port_out = NULL; cpu.userdata = NULL;
    put(&w, &cpu, sizeof cpu);
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
    if (!buffer) return w.used;
    return w.overflow ? 0 : w.used;
}

int cps1_state_load(const uint8_t *buffer, size_t size)
{
    reader_t r = {buffer, size, 0, 0};
    char magic[8];
    get(&r, magic, 8);
    if (r.bad || memcmp(magic, STATE_MAGIC, 8)) return 0;
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
    get(&r, queue, sizeof queue); get(&r, &latch_count, sizeof latch_count); get(&r, &z80_clock, sizeof z80_clock);
    get(&r, &opm_samples, sizeof opm_samples); get(&r, &oki.command, sizeof oki.command);
    get(&r, &oki.pin7, sizeof oki.pin7); get(&r, oki.voice, sizeof oki.voice);
    get(&r, &oki_base_clock, sizeof oki_base_clock); get(&r, &oki_base_samples, sizeof oki_base_samples);
    get(&r, &oki_samples, sizeof oki_samples); get(&r, &oki_level, sizeof oki_level);
    get(&r, &oki_previous, sizeof oki_previous); get(&r, &irq2, sizeof irq2);
    z80 cpu;
    get(&r, &cpu, sizeof cpu);
    uint32_t context_size = 0, opm_size = 0;
    get(&r, &context_size, sizeof context_size);
    if (r.bad || context_size != cps1_m68k_state_bytes() || r.used + context_size > size) return 0;
    const uint8_t *context = buffer + r.used;
    r.used += context_size;
    get(&r, &opm_size, sizeof opm_size);
    if (r.bad || r.used + opm_size != size || line < 0 || line >= LINES || latch_count < 0 ||
        latch_count > LATCH_QUEUE || sound_bank > 1 || oki.pin7 > 1) return 0;
    for (int i = 0; i < 4; i++)
        if (oki.voice[i].step < 0 || oki.voice[i].step > 48) return 0;
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
    cpu.read_byte = M.cpu.read_byte; cpu.write_byte = M.cpu.write_byte;
    cpu.port_in = M.cpu.port_in; cpu.port_out = M.cpu.port_out; cpu.userdata = M.cpu.userdata;
    M.cpu = cpu;
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
        if (address + 2 > M.rom.maincpu_size) return NULL;
        *region = 1; *offset = address; *available = (unsigned)(M.rom.maincpu_size - address);
        return M.rom.maincpu + address;
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
            rr_feedback_note(region == 3 ? RR_FB_CPS1_RAM : RR_FB_CPS1_ROM, offset, 0, bytes,
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
        rr_feedback_note(RR_FB_CPS1_Z80, pc, 0, bytes, 4);
    }
#endif
    if (!rr_cps1_observe) return;
    uint8_t first = 0;
    rr_cps1_z80_code_byte(pc, &first);
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
    return fnv(hash, M.z80_ram, sizeof M.z80_ram);
}
