/* The MSX machine, CPU-independent: slots and secondary slots, RAM, ROM images, the PPI 8255 (slot select,
 * keyboard matrix), the TMS9918A register and status core, the PSG register file with the joystick port.
 * MIT, Retro-Recomp. Written from the MSX standard as documented (MSX2 Technical Handbook, TMS9918A data
 * manual); openMSX was read to understand behaviour, nothing was copied from it.
 *
 * The picture (TMS9918A, line by line) is in msx_video.c, the sound (AY-3-8910 and key click) in msx_psg.c, the
 * cartridges (plain, Konami, Konami SCC with its sound chip, ASCII 8 KB and 16 KB) in msx_cart.c. The MSX2's V9938 in
 * msx_v9938*.c, its memory mapper and clock in msx_msx2.c. A CPU (the reference interpreter, later the native bodies) calls msx_read /
 * msx_write / msx_in / msx_out and advances time with msx_advance. */
#ifndef RR_MSX_MACHINE_H
#define RR_MSX_MACHINE_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

enum { MSX_CYCLES_PER_LINE = 228, MSX_LINES_NTSC = 262, MSX_LINES_PAL = 313, MSX_VBLANK_LINE = 192 };
enum { MSX_KEY_ROWS = 11 };

typedef enum { MSX_DEV_NONE = 0, MSX_DEV_ROM, MSX_DEV_RAM, MSX_DEV_MAPPER_RAM } MsxDeviceKind;
enum { MSX_SOURCE_NONE = 0xFF };

/* The cartridge mappers of the first scope. A plain ROM has no register: it sits at `base`, and with `mirrored` its
 * 8 KB blocks repeat over the other regions of the slot. */
typedef enum {
    MSX_MAPPER_PLAIN = 0,
    MSX_MAPPER_KONAMI,         /* 8 KB banks; 4000h-5FFFh fixed to block 0; any write in 6000h-BFFFh selects its region */
    MSX_MAPPER_KONAMI_SCC,     /* 8 KB banks; writes at 5000h, 7000h, 9000h, B000h (+ 7FFh); the SCC at 9800h */
    MSX_MAPPER_ASCII8,         /* 8 KB banks; writes at 6000h, 6800h, 7000h, 7800h (+ 7FFh) for 4000h-BFFFh */
    MSX_MAPPER_ASCII16,        /* 16 KB banks; writes at 6000h-67FFh (page 1) and 7000h-77FFh (page 2) */
    MSX_MAPPER_COUNT
} MsxMapper;

/* The Konami SCC (K051649): five channels of 32 signed 8-bit samples, channels 4 and 5 sharing one waveform. */
typedef struct {
    int8_t wave[4][32];
    uint16_t period[5];
    uint8_t volume[5];         /* as written; the channel takes it at its next sample (volume_now) */
    uint8_t volume_now[5];
    uint8_t enable;            /* bits 0-4 */
    uint16_t count[5];
    uint8_t pos[5];
    int16_t out[5];            /* the channel's latched output: sample x volume >> 4, set when it steps or restarts */
} MsxScc;

/* What one (primary, secondary) slot holds: a ROM image (plain or with a mapper) or RAM over the whole 64 KB. */
typedef struct {
    MsxDeviceKind kind;
    const uint8_t *rom;
    uint32_t size;
    uint16_t base;         /* plain ROMs: where the image starts */
    /* `size` is rounded up to whole 8 KB blocks (16 KB for ASCII 16): the caller's buffer must hold that padding,
     * filled with FFh as an empty socket reads. */
    uint8_t *ram;          /* 64 KB, for MSX_DEV_RAM */
    MsxMapper mapper;
    uint8_t mirrored;      /* plain ROMs: repeat over the slot */
    int16_t block[8];      /* the 8 KB block of the image seen in each region, -1 for none (kept by the machine) */
    uint8_t scc_on;        /* Konami SCC: the SCC answers at 9800h-9FFFh */
    uint8_t source;        /* native code: which translated source the image is (0 cartridge, 1 BIOS), MSX_SOURCE_NONE if none */
    uint8_t bank_base;     /* native code: the 8 KB bank of the source where this image starts (the MSX2 sub-ROM: 6) */
    MsxScc scc;
} MsxDevice;

/* One 8 KB region of the Z80 address space as currently selected: what reads see, where writes go. */
typedef struct {
    const uint8_t *read;   /* NULL: reads give FFh, or go to the device when `device` is set */
    uint8_t *write;        /* NULL: writes are dropped, or go to the device's mapper when `device` is set */
    uint8_t primary, secondary;
    uint8_t device;        /* 1 when a mapper or a sound chip of the slot answers in this region */
} MsxRegion;

enum { MSX_WIDTH = 256, MSX_HEIGHT = 192 };

typedef struct {
    uint8_t vram[16384];
    uint8_t reg[8];
    uint8_t status;
    uint16_t address;
    uint8_t latch, first, readahead;
    /* The picture, one line at a time: colour indices 0-15 (colour 0 already replaced by the backdrop), and the
     * border colour of each line (R#7 low nibble when the line was drawn). Text mode draws 240 pixels from x = 6. */
    uint8_t frame[MSX_HEIGHT][MSX_WIDTH];
    uint8_t border[MSX_HEIGHT];
} MsxVdp;

/* The V9938 (MSX2; msx_v9938.c, msx_v9938_draw.c) and its command engine (msx_v9938_cmd.c). */
enum { MSX_VIDEO_TMS9918A = 0, MSX_VIDEO_V9938 = 1 };
enum { MSX2_WIDTH = 512, MSX2_LINES = 212, MSX2_VRAM = 0x20000, MSX2_DRAW_AT = 180 };

typedef struct {
    uint16_t sx, sy, dx, dy, nx, ny;   /* R#32-R#43, live (9, 10, 9, 10, 10, 10 bits) */
    uint8_t col, arg, cmd;             /* R#44 (also S#7), R#45, R#46 (0 when no command runs) */
    uint8_t status;                    /* S#2's TR 80h, BD 10h, CE 01h */
    uint8_t transfer;                  /* HMMC/LMMC: a byte given by R#44 not yet used; LMCM: the first dot still to fetch */
    uint8_t mode;                      /* the engine's screen (0 G4, 1 G5, 2 G6, 3 G7, FFh none), latched at line boundaries */
    uint16_t asx, adx, anx;            /* working source X (S#8/S#9), destination X, units left in the line */
    uint64_t next;                     /* the VDP tick (6 per machine cycle) of the next unit while CE is set */
    uint64_t writes;                   /* writes to R#46 */
    uint64_t started[16];              /* commands started, by R#46's high nibble */
} MsxV9938Cmd;

/* VRAM is kept as the chip holds it: two banks, so Graphic 6 and 7 see their logical addresses interleaved (even bytes
 * in the first 64 KB, odd bytes in the second), while every other mode sees them in order (data book, VRAM access in
 * G6/G7). A game that writes in one family of modes and shows or copies in the other sees what the chip shows. */
static inline uint32_t msx_v9938_physical(uint32_t logical, int interleaved)
{
    logical &= 0x1FFFF;
    return interleaved ? (logical >> 1) | ((logical & 1) << 16) : logical;
}
/* Graphic 6 (mode 14h) and Graphic 7 (1Ch) from R#0 and R#1. */
static inline int msx_v9938_interleaved(const uint8_t *reg)
{
    int mode = ((reg[0] & 0x0E) << 1) | ((reg[1] >> 2) & 2) | ((reg[1] >> 4) & 1);
    return mode == 0x14 || mode == 0x1C;
}

typedef struct {
    uint8_t vram[MSX2_VRAM];           /* physical: see msx_v9938_physical */
    uint8_t reg[48];                   /* R#0-R#23 masked; R#32-R#46 mirror cmd.reg */
    uint8_t status0, status1, status2; /* S#0; S#1 FH latch; S#2 EO in bit 1 */
    uint16_t pointer;                  /* 14 bits */
    uint8_t latch, first, readahead;   /* port 99h latch and its first byte; the data buffer of port 98h */
    uint8_t pal_latch, pal_first;      /* port 9Ah two-byte latch */
    uint16_t palette[16];              /* 0GGG0RRR0BBB */
    uint16_t collision_x, collision_y; /* S#3-S#6 */
    uint8_t blink_on, blink_count;     /* R#13 */
    uint8_t lines_latched;             /* 192 or 212, taken at frame start */
    int8_t adjust_h, adjust_v;         /* R#18 at frame start */
    /* The picture: 9-bit colours, palette applied when the line was drawn; 256-pixel modes doubled. The border colour of
     * each line (even and odd half-pixels: Graphic 5 pairs). */
    uint16_t frame[MSX2_LINES][MSX2_WIDTH];
    uint16_t border[MSX2_LINES][2];
    uint8_t line_mode[MSX2_LINES];
    MsxV9938Cmd cmd;
} MsxV9938;

/* The MSX2 memory mapper (ports FCh-FFh): RAM in 16 KB segments, one register per page. */
typedef struct {
    uint8_t *ram;
    uint32_t segments;                 /* a power of two, 4 to 256 */
    uint8_t reg[4];
} MsxMapperRam;

/* The RP5C01 clock (ports B4h/B5h): four blocks of 13 nibbles, the mode register; it runs on machine time only. */
typedef struct {
    uint8_t latch, mode, test, nibble[4][13];
    uint64_t counted;                  /* machine cycles already turned into seconds */
} MsxRtc;

enum { MSX_AUDIO_RATE = 44100, MSX_AUDIO_BUFFER = 8192, MSX_CPU_CLOCK = 3579545 };

/* The AY-3-8910 as a sound generator (msx_psg.c); its registers are MsxMachine.psg. */
typedef struct {
    uint64_t time;                 /* CPU cycle the generator has reached */
    unsigned tick_rest;            /* CPU cycles left over below one tick (16 CPU cycles) */
    uint32_t ticks;                /* ticks run so far (noise and envelope run on every second one) */
    uint16_t tone_count[3];
    uint8_t tone_out[3];
    uint16_t noise_count;
    uint32_t lfsr;
    uint16_t env_count;
    uint8_t env_step, env_up, env_holding;
    uint64_t next_sample;          /* in CPU cycles x 65536 */
    int32_t acc;
    uint32_t acc_ticks;
    int16_t out[MSX_AUDIO_BUFFER];
    unsigned out_count;            /* samples waiting; the caller takes them with msx_audio_take */
    uint64_t dropped;              /* samples lost because the caller did not take them */
} MsxPsgSynth;

typedef struct {
    MsxDevice slot[4][4];
    uint8_t expanded[4];   /* primary slot p is expanded into four secondary slots */
    uint8_t secondary[4];  /* the FFFFh register of each expanded primary slot */
    uint8_t primary;       /* PPI port A (A8h): two bits per page */
    uint8_t port_c;        /* PPI port C (AAh): keyboard row, cassette, CAPS LED, click */
    uint8_t keys[16];      /* keyboard matrix, active low; rows 0-10 used */
    uint8_t psg_latch, psg[16];
    uint8_t joystick[2];   /* active low: bits 0-3 up/down/left/right, 4-5 triggers A/B */
    uint8_t key_layout;    /* the value of PSG R14 bit 6 itself: 00h ("50on" layout, the default) or 40h (JIS) */
    MsxRegion region[8];
    uint32_t generation;   /* raised each time the region layout changes */
    void (*line_hook)(void);   /* optional: called after each line the machine runs */
    uint8_t trace_frames;      /* comparisons: fold every frame's picture and VDP state into frame_trace */
    uint32_t frame_trace;
    MsxVdp vdp;
    MsxPsgSynth synth;
    void (*cart_write_hook)(void *user, uint16_t address, uint8_t value);   /* optional trace of writes to a cartridge */
    void *hook_user;
    MsxDevice *scc[4];      /* the cartridges with a Konami SCC, mixed into the sound (pointers into slot[][]: a copy
                             * of the machine must rebuild them, see msx_set_device) */
    int scc_count;
    unsigned lines_per_frame;
    unsigned vblank_line;  /* the line whose start raises the frame flag: 192 (TMS9918A) or 192/212 (V9938, R#9) */
    unsigned line;
    uint64_t cycles;       /* machine cycles, M1 wait states included */
    uint64_t next_line;
    uint64_t next_draw;    /* V9938: the draw point of the current line (MSX2_DRAW_AT cycles after its start) */
    uint8_t video;         /* MSX_VIDEO_TMS9918A or MSX_VIDEO_V9938 */
    MsxV9938 *v9938;       /* the MSX2's VDP, storage owned by the caller (msx_set_v9938) */
    MsxMapperRam mapper;   /* MSX2: segments 0 when absent */
    MsxRtc rtc;
    uint8_t has_rtc;
    uint64_t frames;
    uint64_t unmapped_reads, dropped_writes;
} MsxMachine;

void msx_init(MsxMachine *m, unsigned lines_per_frame);
void msx_set_device(MsxMachine *m, int primary, int secondary, MsxDevice device);
void msx_set_expanded(MsxMachine *m, int primary, int expanded);
void msx_reset(MsxMachine *m);

uint8_t msx_read(MsxMachine *m, uint16_t address);
/* A read with no side effect and no counter, for tools and traces. */
uint8_t msx_peek(const MsxMachine *m, uint16_t address);
void msx_write(MsxMachine *m, uint16_t address, uint8_t value);
uint8_t msx_in(MsxMachine *m, uint8_t port);
void msx_out(MsxMachine *m, uint8_t port, uint8_t value);

/* The VDP's interrupt request: frame flag set and enabled in R#1. A level line, held until the status is read. */
int msx_irq(const MsxMachine *m);
/* Add machine cycles and run the line events they cross (the frame flag at the end of the active area). */
void msx_advance(MsxMachine *m, uint64_t cycles);

/* The machine cycle of the next line event: the line boundary, or on the V9938 the draw point when it comes first. A
 * caller that advances the machine lazily (the native step loop) must not let the CPU run past it. */
static inline uint64_t msx_next_event(const MsxMachine *m)
{
    return m->video == MSX_VIDEO_V9938 && m->next_draw < m->next_line ? m->next_draw : m->next_line;
}

/* The slot (as the BIOS writes it: bit 7 expanded, bits 0-1 primary, 2-3 secondary) behind an address. */
uint8_t msx_slot_of(const MsxMachine *m, uint16_t address);

/* Input: one key of the 11 x 8 matrix (row 0-10, bit 0-7), and a joystick port (0 or 1) as active-low bits
 * (0 up, 1 down, 2 left, 3 right, 4 trigger A, 5 trigger B). */
void msx_key(MsxMachine *m, int row, int bit, int down);
void msx_joystick(MsxMachine *m, int port, uint8_t active_low);

/* Sound: mono 16-bit samples at MSX_AUDIO_RATE, PSG and key click mixed. Takes up to `max` samples. */
unsigned msx_audio_take(MsxMachine *m, int16_t *out, unsigned max);

/* Comparisons: the machine-side state as JSON members (each followed by ", "): PSG registers, the cartridge banks of
 * every slot, the SCC registers, the per-frame trace. */
#include <stdio.h>
void msx_print_state(const MsxMachine *m, FILE *out);

/* MSX2: the V9938 (its storage given by the caller, zeroed and reset here), the memory mapper (RAM of `segments` x 16 KB
 * given by the caller, placed in slot primary-secondary) and the RP5C01 clock. Call after msx_init. */
void msx_set_v9938(MsxMachine *m, MsxV9938 *v9938);
void msx_set_mapper(MsxMachine *m, int primary, int secondary, uint8_t *ram, uint32_t segments);
void msx_set_rtc(MsxMachine *m);

/* The MSX2 board as C-BIOS lays it out (used for C-BIOS and for the player's own BIOS): slot 0 holds the main ROM and the
 * logo page (bytes 0000h-BFFFh of `bios`), slot 3 is expanded with the sub-ROM in 3-0 (bytes C000h-FFFFh of `bios`) and
 * the mapper RAM in 3-2; the RP5C01 and the V9938. `bios` is the 64 KB BIOS source (native code: source 1, the sub-ROM
 * from its bank 6). The cartridge goes in slot 1 as on the MSX1. Call after msx_init. */
void msx_setup_msx2(MsxMachine *m, const uint8_t *bios, uint8_t *mapper_ram, uint32_t segments, MsxV9938 *v9938);

/* The picture, VRAM and RAM hashes the runners report (FNV-1a), for either machine (`ram64` is the MSX1's RAM; the
 * MSX2's is the mapper's), and the raw picture and VRAM for tools. */
uint32_t msx_vram_hash(const MsxMachine *m);
uint32_t msx_frame_hash(const MsxMachine *m);
uint32_t msx_ram_hash(const MsxMachine *m, const uint8_t *ram64);
int msx_dump_frame(const MsxMachine *m, FILE *out);
int msx_dump_vram(const MsxMachine *m, FILE *out);

/* Internal pieces shared by the machine's files. */
void msx_v9938_reset(MsxMachine *m);
uint8_t msx_v9938_in(MsxMachine *m, uint8_t port);
void msx_v9938_out(MsxMachine *m, uint8_t port, uint8_t value);
int msx_v9938_irq(const MsxMachine *m);
void msx_v9938_advance(MsxMachine *m);
void msx_v9938_draw_line(MsxMachine *m, int line);
void msx_v9938_print(const MsxMachine *m, FILE *out);
uint8_t msx_mapper_in(const MsxMachine *m, uint8_t port);
void msx_mapper_out(MsxMachine *m, uint8_t port, uint8_t value);
uint8_t msx_rtc_in(MsxMachine *m, uint8_t port);
void msx_rtc_out(MsxMachine *m, uint8_t port, uint8_t value);
void msx_rtc_reset(MsxRtc *r);
/* Stage 7 hooks: the command engine (a latch-only stub in stage 6). */
void msx_v9938_cmd_write(MsxMachine *m, int index, uint8_t value);
uint8_t msx_v9938_cmd_status(MsxMachine *m);
uint8_t msx_v9938_cmd_read_colour(MsxMachine *m);
uint16_t msx_v9938_cmd_border_x(MsxMachine *m, int clear);
void msx_v9938_cmd_sync(MsxMachine *m, uint64_t cycle);
void msx_v9938_cmd_reset(MsxMachine *m);
void msx_v9938_cmd_line(MsxMachine *m);                             /* a line boundary: the engine's screen is latched */
void msx_v9938_cmd_print(const MsxMachine *m, FILE *out);
void msx_vdp_draw_line(MsxMachine *m, int line);
void msx_vdp_check_line(MsxMachine *m, int line);
void msx_psg_reset(MsxMachine *m);
void msx_psg_catch_up(MsxMachine *m);
void msx_psg_write(MsxMachine *m, uint8_t reg, uint8_t value);
void msx_cart_reset(MsxDevice *d);
int msx_cart_write(MsxDevice *d, uint16_t address, uint8_t value);   /* 1 when the layout changed */
uint8_t msx_cart_read(const MsxDevice *d, uint16_t address);
int msx_scc_step(MsxScc *s, unsigned cycles);                       /* advance; returns the summed output */

#ifdef __cplusplus
}
#endif
#endif
