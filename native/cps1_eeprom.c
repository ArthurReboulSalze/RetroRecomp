/* 93C46 serial EEPROM (8-bit), see cps1_eeprom.h. */
#include "cps1_eeprom.h"
#include <string.h>

enum { IN_RESET, WAIT_START, WAIT_COMMAND, READING, WAIT_DATA, WAIT_COMPLETION };
enum { CMD_INVALID, CMD_READ, CMD_WRITE, CMD_ERASE, CMD_LOCK, CMD_UNLOCK, CMD_WRITEALL, CMD_ERASEALL };
#define address_bits(chip) ((chip)->wide ? 6u : 7u)
#define data_bits(chip) ((chip)->wide ? 16u : 8u)
#define cells(chip) ((chip)->wide ? 64u : 128u)

static uint64_t now_time;     /* the time of the event being handled */

void cps1_eeprom_reset(cps1_eeprom *chip, uint32_t ticks_per_usec)
{
    memset(chip, 0, sizeof *chip);
    chip->ticks_per_usec = ticks_per_usec;
    memset(chip->data, 0xff, sizeof chip->data);
    chip->state = IN_RESET;
    chip->locked = 1;
}

void cps1_eeprom_set_wide(cps1_eeprom *chip, int wide) { chip->wide = wide != 0; }

/* `opcode` is the two bits after the start bit; for opcode 0 the top two address bits pick the operation. */
static void parse_command(cps1_eeprom *chip)
{
    const unsigned bits = address_bits(chip), address = chip->accumulator & ((1u << bits) - 1), opcode = chip->accumulator >> bits;
    chip->command = CMD_INVALID;
    chip->address = (uint8_t)address;
    switch (opcode) {
    case 0:
        switch (address >> (bits - 2)) {
        case 0: chip->command = CMD_LOCK; break;
        case 1: chip->command = CMD_WRITEALL; break;
        case 2: chip->command = CMD_ERASEALL; break;
        case 3: chip->command = CMD_UNLOCK; break;
        }
        chip->address = 0;
        break;
    case 1: chip->command = CMD_WRITE; break;
    case 2: chip->command = CMD_READ; break;
    case 3: chip->command = CMD_ERASE; break;
    }
}

/* The times of eeprom.cpp: write 1750 us, erase 1000 us, write all and erase all 8000 us. */
enum { WRITE_US = 1750, ERASE_US = 1000, ALL_US = 8000 };
static void busy(cps1_eeprom *chip, unsigned microseconds) { chip->ready_time = now_time + (uint64_t)microseconds * chip->ticks_per_usec; }
static int ready(const cps1_eeprom *chip, uint64_t time) { return time >= chip->ready_time; }

/* A cell: one byte, or one big-endian word of the 16-bit organisation. */
static unsigned cell(const cps1_eeprom *chip, unsigned address)
{
    return chip->wide ? (unsigned)(chip->data[2 * address] << 8 | chip->data[2 * address + 1]) : chip->data[address];
}

static void store(cps1_eeprom *chip, unsigned address, unsigned value)
{
    if (cell(chip, address) == (chip->wide ? value & 0xffffu : value & 0xffu)) return;
    if (chip->wide) { chip->data[2 * address] = (uint8_t)(value >> 8); chip->data[2 * address + 1] = (uint8_t)value; }
    else chip->data[address] = (uint8_t)value;
    chip->changed = 1;
}

static void execute_command(cps1_eeprom *chip)
{
    parse_command(chip);
    chip->bits = 0;
    switch (chip->command) {
    case CMD_READ: chip->shift = 0; chip->state = READING; break;     /* the dummy 0 bit before the first clock */
    case CMD_WRITE: case CMD_WRITEALL: chip->shift = 0; chip->state = WAIT_DATA; break;
    case CMD_ERASE:
        if (chip->locked) { chip->state = IN_RESET; break; }
        store(chip, chip->address, 0xffff);
        busy(chip, ERASE_US);
        chip->state = WAIT_COMPLETION;
        break;
    case CMD_LOCK: chip->locked = 1; chip->state = IN_RESET; break;
    case CMD_UNLOCK: chip->locked = 0; chip->state = IN_RESET; break;
    case CMD_ERASEALL:
        if (chip->locked) { chip->state = IN_RESET; break; }
        for (unsigned n = 0; n < cells(chip); n++) store(chip, n, 0xffff);
        busy(chip, ALL_US);
        chip->state = WAIT_COMPLETION;
        break;
    default: chip->state = IN_RESET; break;     /* an invalid command: MAME aborts; the chip just ignores it */
    }
}

static void execute_write(cps1_eeprom *chip)
{
    if (chip->locked) { chip->state = IN_RESET; return; }
    if (chip->command == CMD_WRITE) { store(chip, chip->address, chip->shift); busy(chip, WRITE_US); }
    else { for (unsigned n = 0; n < cells(chip); n++) store(chip, n, cell(chip, n) & chip->shift); busy(chip, ALL_US); }
    chip->state = WAIT_COMPLETION;
}

enum { CS_RISING, CS_FALLING, CLK_RISING };

static void event(cps1_eeprom *chip, int what, uint64_t time)
{
    switch (chip->state) {
    case IN_RESET:
        if (what == CS_RISING) chip->state = WAIT_START;
        break;
    case WAIT_START:
        /* a clock edge at the very time CS rose is ignored */
        if (what == CLK_RISING && chip->di && ready(chip, time) && time > chip->cs_rise_time) {
            chip->accumulator = 0; chip->bits = 0;
            chip->state = WAIT_COMMAND;
        } else if (what == CS_FALLING) chip->state = IN_RESET;
        break;
    case WAIT_COMMAND:
        if (what == CLK_RISING) {
            chip->accumulator = (uint16_t)((chip->accumulator << 1) | chip->di);
            if (++chip->bits == 2 + address_bits(chip)) execute_command(chip);
        } else if (what == CS_FALLING) chip->state = IN_RESET;
        break;
    case READING:
        if (what == CLK_RISING) {
            const unsigned index = chip->bits;
            if (chip->bits < 0xffff) chip->bits++;
            if (index == 0)                                 /* no streaming: only the cell addressed is read */
                chip->shift = (uint32_t)cell(chip, chip->address & (cells(chip) - 1)) << (32 - data_bits(chip));
            else
                chip->shift = (chip->shift << 1) | 1;
        } else if (what == CS_FALLING) chip->state = IN_RESET;
        break;
    case WAIT_DATA:
        if (what == CLK_RISING) {
            chip->shift = (chip->shift << 1) | chip->di;
            if (++chip->bits == data_bits(chip)) execute_write(chip);
        } else if (what == CS_FALLING) chip->state = IN_RESET;
        break;
    case WAIT_COMPLETION:
        if (what == CS_FALLING) chip->state = IN_RESET;
        break;
    }
}

void cps1_eeprom_write_port(cps1_eeprom *chip, unsigned value, uint64_t time)
{
    now_time = time;
    chip->di = value & 1;
    const unsigned clk = value >> 6 & 1, cs = value >> 7 & 1;
    if (clk != chip->clk) {
        chip->clk = (uint8_t)clk;
        if (clk) event(chip, CLK_RISING, time);
    }
    if (cs != chip->cs) {
        chip->cs = (uint8_t)cs;
        if (cs) chip->cs_rise_time = time;
        event(chip, cs ? CS_RISING : CS_FALLING, time);
    }
}

void cps1_eeprom_write_port16(cps1_eeprom *chip, unsigned value, uint64_t time)
{
    cps1_eeprom_write_port(chip, (value >> 12 & 1) | (value >> 13 & 1) << 6 | (value >> 14 & 1) << 7, time);
}

unsigned cps1_eeprom_read_port(const cps1_eeprom *chip, uint64_t time)
{
    /* DO is high (pulled up) except while a read clocks out a 0 bit; waiting for a start bit it is the READY/BUSY line */
    if (chip->state == READING) return (chip->shift >> 31) & 1;
    if (chip->state == WAIT_START) return ready(chip, time);
    return 1;
}

int cps1_eeprom_take_changed(cps1_eeprom *chip)
{
    const int changed = chip->changed;
    chip->changed = 0;
    return changed;
}

static void put_le(uint8_t *out, uint64_t value, unsigned bytes)
{
    for (unsigned n = 0; n < bytes; n++) out[n] = (uint8_t)(value >> (8 * n));
}

static uint64_t get_le(const uint8_t *in, unsigned bytes)
{
    uint64_t value = 0;
    for (unsigned n = 0; n < bytes; n++) value |= (uint64_t)in[n] << (8 * n);
    return value;
}

size_t cps1_eeprom_state_put(const cps1_eeprom *chip, uint8_t *out)
{
    memcpy(out, chip->data, CPS1_EEPROM_BYTES);
    uint8_t *p = out + CPS1_EEPROM_BYTES;
    *p++ = chip->state; *p++ = chip->cs; *p++ = chip->clk; *p++ = chip->di;
    *p++ = chip->locked; *p++ = chip->command; *p++ = chip->address; *p++ = chip->changed;
    put_le(p, chip->bits, 2); p += 2;
    put_le(p, chip->accumulator, 2); p += 2;
    put_le(p, chip->shift, 4); p += 4;
    put_le(p, chip->cs_rise_time, 8); p += 8;
    put_le(p, chip->ready_time, 8);
    return CPS1_EEPROM_STATE_BYTES;
}

int cps1_eeprom_state_get(cps1_eeprom *chip, const uint8_t *in, uint32_t ticks_per_usec)
{
    cps1_eeprom next = {{0}};
    memcpy(next.data, in, CPS1_EEPROM_BYTES);
    const uint8_t *p = in + CPS1_EEPROM_BYTES;
    next.state = *p++; next.cs = *p++; next.clk = *p++; next.di = *p++;
    next.locked = *p++; next.command = *p++; next.address = *p++; next.changed = *p++;
    next.bits = (uint16_t)get_le(p, 2); p += 2;
    next.accumulator = (uint16_t)get_le(p, 2); p += 2;
    next.shift = (uint32_t)get_le(p, 4); p += 4;
    next.cs_rise_time = get_le(p, 8); p += 8;
    next.ready_time = get_le(p, 8);
    next.ticks_per_usec = ticks_per_usec;
    next.wide = chip->wide;
    if (next.state > WAIT_COMPLETION || next.cs > 1 || next.clk > 1 || next.di > 1 || next.locked > 1 || next.command > CMD_ERASEALL ||
        next.address >= CPS1_EEPROM_BYTES || next.changed > 1) return 0;
    *chip = next;
    return 1;
}
