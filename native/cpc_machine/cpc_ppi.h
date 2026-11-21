/* The Amstrad CPC's PPI 8255 and keyboard matrix: port A the AY-3-8912's data bus, port B the machine's inputs (VSYNC, the
 * manufacturer and refresh links, the expansion and printer lines, the tape), port C the keyboard row (bits 0-3), the tape motor
 * and write (bits 4-5) and the AY's bus control BDIR/BC1 (bits 7-6). The AY's I/O port A reads the row the PPI selects: ten rows
 * of eight keys, a key down reading 0. The joystick port is wired on row 9; a second joystick (through the first, as the AMSOFT
 * JY1 / a doubler) on row 6, sharing its lines with keys. MIT, Retro-Recomp.
 *
 * Written from Intel's 8255A data sheet and the CPC's documented port and matrix tables. The AY itself is the machine's (the
 * shared AY-3-8910 module); this file only drives it through a small bus (CpcPsgBus). Port B's fixed bits are the documented
 * defaults of a 6128 sold by Amstrad in a 50 Hz country with nothing on its expansion or printer ports: links 1-3 set
 * (Amstrad), bit 4 set (50 Hz), bit 5 set (no expansion), bit 6 set (no printer, busy pulled up), bit 7 the tape's data (0).
 *
 * The joystick lines of row 6 for the second stick (up, down, left, right, fire 2, fire 1 on bits 0-5) follow the layout of the
 * first on row 9; to be confirmed on a game that reads them (Match Day II is the panel's case). */
#ifndef RR_CPC_PPI_H
#define RR_CPC_PPI_H
#include <stdint.h>

enum { CPC_KEY_ROWS = 10 };

/* A key: row * 8 + bit. The ones a game's controls use (the full matrix is the documented table). */
enum {
    CPC_KEY_UP = 0 * 8 + 0, CPC_KEY_RIGHT = 0 * 8 + 1, CPC_KEY_DOWN = 0 * 8 + 2, CPC_KEY_F9 = 0 * 8 + 3, CPC_KEY_F6 = 0 * 8 + 4,
    CPC_KEY_F3 = 0 * 8 + 5, CPC_KEY_ENTER = 0 * 8 + 6, CPC_KEY_FDOT = 0 * 8 + 7,
    CPC_KEY_LEFT = 1 * 8 + 0, CPC_KEY_COPY = 1 * 8 + 1, CPC_KEY_F7 = 1 * 8 + 2, CPC_KEY_F8 = 1 * 8 + 3, CPC_KEY_F5 = 1 * 8 + 4,
    CPC_KEY_F1 = 1 * 8 + 5, CPC_KEY_F2 = 1 * 8 + 6, CPC_KEY_F0 = 1 * 8 + 7,
    CPC_KEY_CLR = 2 * 8 + 0, CPC_KEY_LBRACKET = 2 * 8 + 1, CPC_KEY_RETURN = 2 * 8 + 2, CPC_KEY_RBRACKET = 2 * 8 + 3,
    CPC_KEY_F4 = 2 * 8 + 4, CPC_KEY_SHIFT = 2 * 8 + 5, CPC_KEY_BACKSLASH = 2 * 8 + 6, CPC_KEY_CONTROL = 2 * 8 + 7,
    CPC_KEY_CARET = 3 * 8 + 0, CPC_KEY_MINUS = 3 * 8 + 1, CPC_KEY_AT = 3 * 8 + 2, CPC_KEY_P = 3 * 8 + 3,
    CPC_KEY_SEMICOLON = 3 * 8 + 4, CPC_KEY_COLON = 3 * 8 + 5, CPC_KEY_SLASH = 3 * 8 + 6, CPC_KEY_DOT = 3 * 8 + 7,
    CPC_KEY_0 = 4 * 8 + 0, CPC_KEY_9 = 4 * 8 + 1, CPC_KEY_O = 4 * 8 + 2, CPC_KEY_I = 4 * 8 + 3, CPC_KEY_L = 4 * 8 + 4,
    CPC_KEY_K = 4 * 8 + 5, CPC_KEY_M = 4 * 8 + 6, CPC_KEY_COMMA = 4 * 8 + 7,
    CPC_KEY_8 = 5 * 8 + 0, CPC_KEY_7 = 5 * 8 + 1, CPC_KEY_U = 5 * 8 + 2, CPC_KEY_Y = 5 * 8 + 3, CPC_KEY_H = 5 * 8 + 4,
    CPC_KEY_J = 5 * 8 + 5, CPC_KEY_N = 5 * 8 + 6, CPC_KEY_SPACE = 5 * 8 + 7,
    CPC_KEY_6 = 6 * 8 + 0, CPC_KEY_5 = 6 * 8 + 1, CPC_KEY_R = 6 * 8 + 2, CPC_KEY_T = 6 * 8 + 3, CPC_KEY_G = 6 * 8 + 4,
    CPC_KEY_F = 6 * 8 + 5, CPC_KEY_B = 6 * 8 + 6, CPC_KEY_V = 6 * 8 + 7,
    CPC_KEY_4 = 7 * 8 + 0, CPC_KEY_3 = 7 * 8 + 1, CPC_KEY_E = 7 * 8 + 2, CPC_KEY_W = 7 * 8 + 3, CPC_KEY_S = 7 * 8 + 4,
    CPC_KEY_D = 7 * 8 + 5, CPC_KEY_C = 7 * 8 + 6, CPC_KEY_X = 7 * 8 + 7,
    CPC_KEY_1 = 8 * 8 + 0, CPC_KEY_2 = 8 * 8 + 1, CPC_KEY_ESC = 8 * 8 + 2, CPC_KEY_Q = 8 * 8 + 3, CPC_KEY_TAB = 8 * 8 + 4,
    CPC_KEY_A = 8 * 8 + 5, CPC_KEY_CAPSLOCK = 8 * 8 + 6, CPC_KEY_Z = 8 * 8 + 7,
    CPC_KEY_DEL = 9 * 8 + 7,
};

/* Joystick lines, the bit in the stick's row (row 9 for the first, row 6 for the second). */
enum { CPC_JOY_UP = 0x01, CPC_JOY_DOWN = 0x02, CPC_JOY_LEFT = 0x04, CPC_JOY_RIGHT = 0x08, CPC_JOY_FIRE2 = 0x10,
       CPC_JOY_FIRE1 = 0x20 };

/* The AY's bus as the PPI drives it. */
typedef struct {
    void *context;
    void (*latch)(void *context, uint8_t reg);       /* BDIR/BC1 = 11: select an AY register */
    void (*write)(void *context, uint8_t value);     /* 10: write it */
    uint8_t (*read)(void *context);                  /* 01: read it (register 14 reads the keyboard row: cpc_ppi_row) */
} CpcPsgBus;

typedef struct {
    uint8_t control;        /* the last mode byte: bit 4 port A input, bit 3 port C upper input, bit 1 port B input, bit 0 C lower */
    uint8_t port_a;         /* port A's output latch */
    uint8_t port_c;         /* port C's output latch */
    uint8_t psg_data;       /* what the AY put on the bus at its last read */
    /* Inputs, set by the machine each frame (part of the state: the next frames read them). */
    uint8_t keys[CPC_KEY_ROWS];      /* a bit set: the key is down */
    uint8_t joystick[2];             /* CPC_JOY_* bits, joystick 1 then 2 */
} CpcPpi;

void cpc_ppi_reset(CpcPpi *p);
/* Port F4xxh (A), F5xxh (B), F6xxh (C), F7xxh (control): offset 0-3. `vsync` is the CRTC's, read on port B bit 0. */
uint8_t cpc_ppi_read(CpcPpi *p, unsigned offset, int vsync, const CpcPsgBus *psg);
void cpc_ppi_write(CpcPpi *p, unsigned offset, uint8_t value, const CpcPsgBus *psg);
/* The keyboard row the PPI selects, as the AY's port A reads it (0 for a key down; FFh past row 9). */
uint8_t cpc_ppi_row(const CpcPpi *p);
void cpc_ppi_key(CpcPpi *p, unsigned key, int down);
#endif
