/* 93C46 serial EEPROM, 8-bit organisation (128 bytes), as wired on the CPS-1.5 (QSound) boards.
 *
 * The command set, the order of the bits and the line behaviour follow MAME's eepromser.cpp at the revision the CPS-1
 * catalogue is pinned to (BSD-3-Clause, copyright Aaron Giles; see licenses/cps1-machine.md). The internal write cycle is
 * the times of MAME's eeprom.cpp (a write 1.75 ms, an erase 1 ms, write all and erase all 8 ms), counted on the clock
 * the caller passes in: while it runs DO reads low and a new command cannot start, as on the chip. Original adaptation: MIT
 * terms of the repository. */
#ifndef RR_CPS1_EEPROM_H
#define RR_CPS1_EEPROM_H
#include <stddef.h>
#include <stdint.h>

#define CPS1_EEPROM_BYTES 128

typedef struct cps1_eeprom {
    uint8_t data[CPS1_EEPROM_BYTES];
    uint8_t state, cs, clk, di, locked, command, address, changed;
    uint16_t bits, accumulator;
    uint32_t shift;
    uint64_t cs_rise_time, ready_time;
    uint32_t ticks_per_usec;   /* the caller's clock ticks in a microsecond (not part of a state) */
} cps1_eeprom;

void cps1_eeprom_reset(cps1_eeprom *chip, uint32_t ticks_per_usec);   /* blank contents (0xff) and lines low */
/* The three input lines of the board's output port (bit 0 DI, bit 6 CLK, bit 7 CS), applied in that order. `time` is any
 * increasing clock: a CLK edge at the same time as the CS edge is ignored. */
void cps1_eeprom_write_port(cps1_eeprom *chip, unsigned value, uint64_t time);
unsigned cps1_eeprom_read_port(const cps1_eeprom *chip, uint64_t time);   /* bit 0: DO (low while a write cycle runs) */
int cps1_eeprom_take_changed(cps1_eeprom *chip);                  /* 1 once after the contents changed */

/* Quick state: every field, little-endian, no padding. */
#define CPS1_EEPROM_STATE_BYTES (CPS1_EEPROM_BYTES + 8 + 2 + 2 + 4 + 8 + 8)
size_t cps1_eeprom_state_put(const cps1_eeprom *chip, uint8_t *out);
/* `ticks_per_usec` is the board's clock (what `cps1_eeprom_reset` was given): it is not part of a state, and a state restored with
 * another one would end a write cycle at the wrong time. 0 when a field is out of its range; the chip is then untouched. */
int cps1_eeprom_state_get(cps1_eeprom *chip, const uint8_t *in, uint32_t ticks_per_usec);
#endif
