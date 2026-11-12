/* The MSX machine, CPU-independent: slots and secondary slots, RAM, ROM images, the PPI 8255 (slot select,
 * keyboard matrix), the TMS9918A register and status core, the PSG register file with the joystick port.
 * MIT, Retro-Recomp. Written from the MSX standard as documented (MSX2 Technical Handbook, TMS9918A data
 * manual); openMSX was read to understand behaviour, nothing was copied from it.
 *
 * The picture (TMS9918A, line by line) is in msx_video.c, the sound (AY-3-8910 and key click) in msx_psg.c. No
 * cartridge mapper and no V9938 yet. A CPU (the reference interpreter, later the native bodies) calls msx_read /
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

typedef enum { MSX_DEV_NONE = 0, MSX_DEV_ROM, MSX_DEV_RAM } MsxDeviceKind;

/* What one (primary, secondary) slot holds: a ROM image seen from `base` for `size` bytes (unmapped bytes read
 * FFh), or RAM over the whole 64 KB. */
typedef struct {
    MsxDeviceKind kind;
    const uint8_t *rom;
    uint32_t size;
    uint16_t base;
    uint8_t *ram;          /* 64 KB, for MSX_DEV_RAM */
} MsxDevice;

/* One 8 KB region of the Z80 address space as currently selected: what reads see, where writes go. */
typedef struct {
    const uint8_t *read;   /* NULL: reads give FFh */
    uint8_t *write;        /* NULL: writes are dropped (a mapper hook later) */
    uint8_t primary, secondary;
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
    MsxVdp vdp;
    MsxPsgSynth synth;
    unsigned lines_per_frame;
    unsigned line;
    uint64_t cycles;       /* machine cycles, M1 wait states included */
    uint64_t next_line;
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

/* The slot (as the BIOS writes it: bit 7 expanded, bits 0-1 primary, 2-3 secondary) behind an address. */
uint8_t msx_slot_of(const MsxMachine *m, uint16_t address);

/* Input: one key of the 11 x 8 matrix (row 0-10, bit 0-7), and a joystick port (0 or 1) as active-low bits
 * (0 up, 1 down, 2 left, 3 right, 4 trigger A, 5 trigger B). */
void msx_key(MsxMachine *m, int row, int bit, int down);
void msx_joystick(MsxMachine *m, int port, uint8_t active_low);

/* Sound: mono 16-bit samples at MSX_AUDIO_RATE, PSG and key click mixed. Takes up to `max` samples. */
unsigned msx_audio_take(MsxMachine *m, int16_t *out, unsigned max);

/* Internal pieces shared by the machine's files. */
void msx_vdp_draw_line(MsxMachine *m, int line);
void msx_vdp_check_line(MsxMachine *m, int line);
void msx_psg_reset(MsxMachine *m);
void msx_psg_catch_up(MsxMachine *m);
void msx_psg_write(MsxMachine *m, uint8_t reg, uint8_t value);

#ifdef __cplusplus
}
#endif
#endif
