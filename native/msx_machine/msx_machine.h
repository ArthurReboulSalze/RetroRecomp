/* The MSX machine, CPU-independent: slots and secondary slots, RAM, ROM images, the PPI 8255 (slot select,
 * keyboard matrix), the TMS9918A register and status core, the PSG register file with the joystick port.
 * MIT, Retro-Recomp. Written from the MSX standard as documented (MSX2 Technical Handbook, TMS9918A data
 * manual); openMSX was read to understand behaviour, nothing was copied from it.
 *
 * The picture (TMS9918A, line by line) is in msx_video.c, the sound (AY-3-8910 and key click) in msx_psg.c, the
 * cartridges (plain, Konami, Konami SCC with its sound chip, ASCII 8 KB and 16 KB) in msx_cart.c. No V9938 yet. A CPU (the reference interpreter, later the native bodies) calls msx_read /
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
    MsxDevice *scc[4];      /* the cartridges with a Konami SCC, mixed into the sound (pointers into slot[][]: a copy
                             * of the machine must rebuild them, see msx_set_device) */
    int scc_count;
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
void msx_cart_reset(MsxDevice *d);
int msx_cart_write(MsxDevice *d, uint16_t address, uint8_t value);   /* 1 when the layout changed */
uint8_t msx_cart_read(const MsxDevice *d, uint16_t address);
int msx_scc_step(MsxScc *s, unsigned cycles);                       /* advance; returns the summed output */

#ifdef __cplusplus
}
#endif
#endif
