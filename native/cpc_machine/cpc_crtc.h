/* The Amstrad CPC's CRT controller, a 6845, stepped one character (1 us, two bytes of screen) at a time. MIT, Retro-Recomp.
 *
 * Written from the HD6845S / UM6845R / MC6845 data sheets' register descriptions and the CPC's documented wiring; floooh/chips
 * mc6845.h (zlib) and Clock Signal's CRTC6845.hpp (MIT) were read as documentation, nothing of them copied. The CRTC type is a
 * machine setting: type 1 (UM6845R, the usual 6128) by default, types 0 (HD6845S / UM6845) and 2 (MC6845) for a game whose
 * reviewed data asks for one (by the dump's SHA-256, never by title). Types 3 and 4 (the Plus range's ASIC) are not modelled.
 *
 * Registers: R0 horizontal total - 1, R1 displayed, R2 HSYNC position, R3 sync widths (bits 0-3 HSYNC, bits 4-7 VSYNC),
 * R4 vertical total - 1 (character rows), R5 vertical total adjust (lines), R6 rows displayed, R7 VSYNC position (row),
 * R8 interlace and skew (not modelled), R9 maximum raster address (lines per row - 1), R10/R11 cursor (no output on the CPC),
 * R12/R13 start address, R14/R15 cursor address, R16/R17 light pen.
 *
 * What differs by type here, as the data sheets and the CPC documentation give it: the VSYNC width (types 1 and 2: always 16
 * lines; type 0: R3's high nibble, 0 meaning 16), an HSYNC width of 0 (types 0 and 1: no HSYNC; type 2: 16), the registers a
 * program can read back (type 0: R12-R17; type 1: R14-R17 and R31 reading 0FFh, the status at port BExxh; type 2: R14-R17),
 * and when R12/R13 are taken (type 1: at the start of each row of the first character row, so a change during row 0 shows at
 * once; types 0 and 2: at the start of the frame only).
 *
 * Not modelled: interlace (R8), skew, the cursor and light pen outputs, the "R1 > R0" border byte of types 0 and 2, the
 * exact moment within a character at which a register write takes effect (it takes effect for the next character). A demo
 * that depends on them is not a goal. */
#ifndef RR_CPC_CRTC_H
#define RR_CPC_CRTC_H
#include <stdint.h>

enum { CPC_CRTC_TYPE0 = 0, CPC_CRTC_TYPE1 = 1, CPC_CRTC_TYPE2 = 2 };

typedef struct {
    uint8_t type;           /* CPC_CRTC_TYPE*, set before reset */
    uint8_t reg[18];
    uint8_t select;         /* the register addressed (0-31) */
    uint8_t hcc;            /* character in the line */
    uint8_t vcc;            /* character row */
    uint8_t ra;             /* line in the row (raster address) */
    uint8_t adjust;         /* lines of the vertical total adjust so far */
    uint8_t in_adjust;      /* the frame is in its vertical total adjust */
    uint8_t h_display, v_display;
    uint8_t hsync, hsync_count;
    uint8_t vsync, vsync_count;
    uint16_t ma_row;        /* memory address of the row's first character */
    uint16_t ma_next;       /* memory address taken at character R1, the next row's start */
    uint16_t ma;            /* memory address of the current character */
} CpcCrtc;

/* What the CRTC shows for the character it is on (before cpc_crtc_step moves it on). */
typedef struct {
    uint16_t ma;
    uint8_t ra;
    uint8_t display;        /* display enable */
    uint8_t hsync, vsync;
} CpcCrtcOut;

/* Reset with the given type; the registers take the values the CPC firmware programs (a 50 Hz screen), so a picture comes out
 * before a program sets them. */
void cpc_crtc_reset(CpcCrtc *c, uint8_t type);
void cpc_crtc_select(CpcCrtc *c, uint8_t reg);
void cpc_crtc_write(CpcCrtc *c, uint8_t value);
/* Port BFxxh (data) and, type 1, BExxh (status); others read 0 where the register cannot be read. */
uint8_t cpc_crtc_read(const CpcCrtc *c);
uint8_t cpc_crtc_status(const CpcCrtc *c);
CpcCrtcOut cpc_crtc_out(const CpcCrtc *c);
/* One character time. */
void cpc_crtc_step(CpcCrtc *c);
/* The CPC's address of a screen byte: MA13-12 the 16 KiB page, RA2-0 to A13-11, MA9-0 to A10-1, the byte (0 or 1) to A0. */
static inline uint16_t cpc_crtc_address(uint16_t ma, uint8_t ra, unsigned byte)
{
    return (uint16_t)(((ma & 0x3000) << 2) | ((ra & 7) << 11) | ((ma & 0x3FF) << 1) | (byte & 1));
}
#endif
