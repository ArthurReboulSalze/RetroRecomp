/* Capcom CPS-1 board (standard 10/12 MHz A/B/C boards, no QSound).
 *
 * Adapted from MAME's CPS-1 driver (src/mame/capcom/cps1.cpp, cps1_v.cpp,
 * BSD-3-Clause, copyright-holders: Paul Leaman) at revision
 * 61a222977fd29f22ce11fbea3f7c290fd7ced091; see licenses/cps1-machine.md.
 * The frame is rendered whole at the start of VBLANK, as MAME does for this
 * board; mid-frame register writes and 68000 bus waits are not modelled.
 */
#ifndef CPS1_MACHINE_H
#define CPS1_MACHINE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CPS1_SCREEN_W 384
#define CPS1_SCREEN_H 224
#define CPS1_PALETTE_SIZE 0xc00
#define CPS1_MAX_RANGES 32
#define CPS1_YM_CLOCK 3579545u
#define CPS1_AUDIO_RATE (CPS1_YM_CLOCK / 64u)

enum { CPS1_IN0, CPS1_IN1, CPS1_IN2, CPS1_IN3, CPS1_DSWA, CPS1_DSWB, CPS1_DSWC, CPS1_PORTS };

typedef struct cps1_range { int type, start, end, bank; } cps1_range;

typedef struct cps1_board {
    char set[32];
    uint32_t cpu_clock;
    int id_address, id_value;
    int mult[4];              /* factor1, factor2, result_lo, result_hi */
    int layer_control, priority[4], palette_control, layer_enable[5];
    int bank_sizes[4];
    cps1_range ranges[CPS1_MAX_RANGES];
    int range_count;
    int ports[3];             /* in2, in3, out2 CPS-B offsets (0 = absent) */
    int kludge, rotation;
    uint16_t port_default[CPS1_PORTS];
    uint8_t port_present[CPS1_PORTS];
} cps1_board;

typedef struct cps1_regions {
    const uint8_t *maincpu; size_t maincpu_size;
    const uint8_t *audiocpu; size_t audiocpu_size;
    const uint8_t *gfx; size_t gfx_size;
    const uint8_t *oki; size_t oki_size;
    const uint8_t *stars; size_t stars_size;
} cps1_regions;

/* Parse the board.txt description written by smsrecomp/cps1_board.py. */
int cps1_board_parse(cps1_board *board, const char *text, char *error, size_t error_size);

/* One machine per process: Musashi keeps its CPU state in globals. */
int cps1_init(const cps1_board *board, const cps1_regions *regions);
void cps1_reset(void);
void cps1_shutdown(void);

/* Port values are raw (active low, as the board reads them). */
void cps1_set_port(int port, uint16_t value);
uint16_t cps1_port_default(int port);

/* Run through the next VBLANK to the end of it: the frame is drawn when
 * VBLANK starts and coloured when it ends; its audio is queued. */
void cps1_run_frame(void);
const uint32_t *cps1_framebuffer(void);         /* 384x224 0x00RRGGBB */
const int16_t *cps1_audio(size_t *samples);     /* mono, CPS1_AUDIO_RATE */
uint64_t cps1_frame_number(void);

typedef struct cps1_cpu_state {
    uint32_t m68k_pc, m68k_sr, m68k_d[8], m68k_a[8];
    uint16_t z80_pc, z80_sp, z80_af, z80_bc, z80_de, z80_hl;
} cps1_cpu_state;
void cps1_cpu_state_get(cps1_cpu_state *state);
uint64_t cps1_ram_hash(void);                   /* work RAM, GFX RAM, Z80 RAM */
const uint8_t *cps1_work_ram(void);             /* 0xff0000-0xffffff, big-endian */

/* VPA/E-clock wait on interrupt acknowledge (on by default). */
void cps1_set_iack_model(int enabled, int offset, int base);

/* Board bus, shared by the reference CPU cores and future native code. */
uint8_t cps1_m68k_read8(uint32_t address);
uint16_t cps1_m68k_read16(uint32_t address);
void cps1_m68k_write8(uint32_t address, uint8_t value);
void cps1_m68k_write16(uint32_t address, uint16_t value);

#ifdef __cplusplus
}
#endif
#endif
