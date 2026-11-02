/* Checks of the 93C46 model (native/cps1_eeprom.c) by clocking commands in as a game does: through the three lines of the board's
 * port (DI bit 0, CLK bit 6, CS bit 7). Built by tools/cps1_eeprom_selftest.py; no ROM, no board. */
#include <stdio.h>
#include <string.h>
#include "cps1_eeprom.h"

static cps1_eeprom chip;
static uint64_t now;
static unsigned passed, failed;

static void expect(const char *what, int ok)
{
    if (ok) ++passed; else { ++failed; fprintf(stderr, "FAIL: %s\n", what); }
}

/* one bit: DI set up, CLK rises, CLK falls, each a little later (a CLK edge in the same instant as CS rising is ignored) */
static void bit(int value, int cs)
{
    now += 100; cps1_eeprom_write_port(&chip, (unsigned)value | (cs ? 0x80u : 0), now);
    now += 100; cps1_eeprom_write_port(&chip, (unsigned)value | 0x40u | (cs ? 0x80u : 0), now);
    now += 100; cps1_eeprom_write_port(&chip, (unsigned)value | (cs ? 0x80u : 0), now);
}
static void select(void) { now += 100; cps1_eeprom_write_port(&chip, 0x80, now); }
static void deselect(void) { now += 100; cps1_eeprom_write_port(&chip, 0, now); }
static void bits(unsigned value, int count) { for (int n = count - 1; n >= 0; n--) bit((value >> n) & 1, 1); }
static void command(unsigned opcode, unsigned address) { bits(1, 1); bits(opcode, 2); bits(address, 7); }
static unsigned read_byte(unsigned address)
{
    unsigned value = 0;
    select(); command(2, address);
    for (int n = 0; n < 8; n++) {
        bit(0, 1);
        value = value << 1 | cps1_eeprom_read_port(&chip, now);
    }
    deselect();
    return value;
}
static void unlock(void) { select(); command(0, 0x60); deselect(); }       /* EWEN: opcode 00, address 11xxxxx */
static void write_byte(unsigned address, unsigned value) { select(); command(1, address); bits(value, 8); deselect(); }

int main(void)
{
    cps1_eeprom_reset(&chip, 12);                 /* a 12 MHz clock: 12 ticks a microsecond */
    expect("a blank chip reads 0xff", read_byte(5) == 0xff);
    write_byte(5, 0xa7);
    expect("a write is refused while the chip is locked", chip.data[5] == 0xff && !cps1_eeprom_take_changed(&chip));
    unlock();
    write_byte(5, 0xa7);
    expect("a write after the unlock command lands", chip.data[5] == 0xa7 && cps1_eeprom_take_changed(&chip));
    expect("the change is reported once", !cps1_eeprom_take_changed(&chip));
    /* the write cycle: DO reads low (busy) while the chip waits for a start bit, until 1.75 ms have gone by */
    select();
    expect("DO is low while the write cycle runs", cps1_eeprom_read_port(&chip, now) == 0);
    now += 12 * 1800;
    expect("DO is high once it has finished", cps1_eeprom_read_port(&chip, now) == 1);
    deselect();
    unlock();
    now += 12 * 1800;
    expect("the value reads back", read_byte(5) == 0xa7 && read_byte(6) == 0xff);
    now += 12 * 1800;
    select(); command(3, 5); deselect();                                        /* ERASE address 5 */
    now += 12 * 1800;
    expect("an erase sets the cell back to 0xff", chip.data[5] == 0xff);
    write_byte(0x7f, 0x12);
    now += 12 * 1800;
    expect("the last cell is addressable", read_byte(0x7f) == 0x12);
    /* a command started while the chip is busy is ignored: the start bit is not taken */
    write_byte(9, 0x34);
    select(); command(1, 10); bits(0x55, 8); deselect();
    expect("no command is taken during a write cycle", chip.data[10] == 0xff);
    /* a state survives a save and a load */
    uint8_t state[CPS1_EEPROM_STATE_BYTES];
    expect("the state has its documented size", cps1_eeprom_state_put(&chip, state) == CPS1_EEPROM_STATE_BYTES);
    cps1_eeprom copy;
    cps1_eeprom_reset(&copy, 12);
    expect("a state loads", cps1_eeprom_state_get(&copy, state) == 1);
    uint8_t again[CPS1_EEPROM_STATE_BYTES];
    cps1_eeprom_state_put(&copy, again);
    expect("a loaded state saves the same bytes", !memcmp(state, again, sizeof state));
    state[CPS1_EEPROM_BYTES] = 9;                 /* a state byte out of range */
    expect("a state with an impossible field is refused", cps1_eeprom_state_get(&copy, state) == 0);
    printf("{\"passed\":%u,\"failed\":%u}\n", passed, failed);
    return failed ? 1 : 0;
}
