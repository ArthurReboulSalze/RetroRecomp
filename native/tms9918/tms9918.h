/* The TMS9918A video chip (and the TMS9928A / TMS9929A, which differ only in their outputs): the state, the CPU's port access,
 * the picture one line at a time and the line the frame flag rises on. Shared by every machine that has the chip: the MSX
 * (msx_machine.c), the SG-1000 and the ColecoVision. MIT, Retro-Recomp.
 *
 * The chip knows nothing of the machine around it: which ports reach it, how /INT or /NMI is wired to the frame flag, the
 * clock that moves its lines and the palette of the host are the machine's. The machine calls `tms9918_line_end` each time
 * the chip's line counter runs out (228 cycles at 3.579545 MHz), reads the pins through `tms9918_irq` and the ports through
 * `tms9918_read_*` / `tms9918_write_*`. A line is drawn with the registers and VRAM as they are when the line ends (line
 * granularity); VRAM access slots are not modelled. */
#ifndef TMS9918_H
#define TMS9918_H

#include <stdint.h>

enum { TMS_WIDTH = 256, TMS_HEIGHT = 192, TMS_VBLANK_LINE = 192 };

typedef struct {
    uint8_t vram[16384];
    uint8_t reg[8];
    uint8_t status;
    uint16_t address;
    uint8_t latch, first, readahead;
    /* The picture, one line at a time: colour indices 0-15 (colour 0 already replaced by the backdrop), and the
     * border colour of each line (R#7 low nibble when the line was drawn). Text mode draws 240 pixels from x = 6. */
    uint8_t frame[TMS_HEIGHT][TMS_WIDTH];
    uint8_t border[TMS_HEIGHT];
} Tms9918;

/* The CPU's access: data port (VRAM read and write) and control port (the address and register writes, the status read). */
uint8_t tms9918_read_data(Tms9918 *v);
void tms9918_write_data(Tms9918 *v, uint8_t value);
uint8_t tms9918_read_status(Tms9918 *v);
void tms9918_write_control(Tms9918 *v, uint8_t value);

/* The interrupt output: the frame flag while R#1 bit 5 enables it. A level; an edge is made by the machine that wires it to /NMI. */
static inline int tms9918_irq(const Tms9918 *v) { return (v->status & 0x80) && (v->reg[1] & 0x20); }

/* The line that just ended (`*line`, counted from 0) is drawn with the state it ended with; the sprites of the last visible
 * line set their flags before the frame flag; the counter moves on and the frame flag rises at line 192; at
 * `lines_per_frame` (262 NTSC, 313 PAL) the counter wraps. Returns 1 when it wrapped (a frame is complete). */
int tms9918_line_end(Tms9918 *v, unsigned *line, unsigned lines_per_frame);

/* The two halves of it, for a machine that moves its lines itself. */
void tms9918_draw_line(Tms9918 *v, int line);
void tms9918_check_line(Tms9918 *v, int line);

#endif
