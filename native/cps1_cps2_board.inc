/* The Capcom CPS-2 board inside the CPS-1 machine (included by cps1_machine.c after its state code; one translation unit, so it uses the
 * machine's statics). Adapted from MAME's cps2.cpp (BSD-3-Clause, Paul Leaman, Andreas Naive, Nicola Salmoria): the object chip, the
 * frame, the 68000 space with the EEPROM port and the service switch, the raster counters, and the board's part of a quick state.
 * Original Retro-Recomp code: MIT, derived from the files named in licenses/cps1-machine.md. */

/* The CPS-2 graphics ROMs are stored shuffled: in each 2 MiB bank the 8-byte items are permuted by MAME's recursive `unshuffle`
 * (cps2_state::unshuffle), after which the bank has the CPS-1 layout. */
static void unshuffle(uint64_t *buffer, size_t length)
{
    if (length == 2) return;
    length /= 2;
    unshuffle(buffer, length);
    unshuffle(buffer + length, length);
    for (size_t i = 0; i < length / 2; i++) {
        const uint64_t item = buffer[length / 2 + i];
        buffer[length / 2 + i] = buffer[length + i];
        buffer[length + i] = item;
    }
}

/* The 68000 here reads at the start of an instruction, MAME's clock reads it a few bus cycles later (a MOVE.W from an absolute address
 * reads in its last four cycles). The raster counters change every line, so a read near the end of a line must see the same line:
 * measured on mmatrix against MAME's taps (reads about 5 pixels, writes about 10 pixels later than ours), 8 cycles. */
#define CPS2_READ_DELAY 8

static int cps2_cps_b_read(int offset, uint16_t *value)
{
    const uint64_t now = m68k_now() + CPS2_READ_DELAY;
    if (offset == 0x0e / 2) {                 /* the position in the line, relative to counter 3, and the unknown bit 0 */
        const int pixel = (int)((now - M.line_start) * PIXEL_CLOCK / M.board.cpu_clock) / 2;
        *value = (uint16_t)((((int)M.raster_counter[2] - pixel) << 1 & 0x1fe) | (M.cps_b[0x0e / 2] & 1));
        return 1;
    }
    if (offset == 0x10 / 2 || offset == 0x12 / 2) {
        /* MAME's counter changes at the start of the line, on the clock; the 68000 here runs a line in one slice, so a read made past the end
         * of the line by an instruction that crosses it sees the next line's value */
        uint16_t counter = M.raster_counter[offset & 1];
        if (now >= M.m68k_target)
            counter = (M.line + 1) % LINES == 0 ? M.raster_reload[offset & 1] : (uint16_t)(counter - 1);
        *value = counter & 0x1ff;
        return 1;
    }
    return 0;
}

/* The CPS-2 object chip (MAME's cps2_render_sprites): 0x400 sprites of four words in the latched object RAM, drawn from the last
 * one down, each with its own 3-bit priority against the tile layers, 10-bit coordinates, block sprites, and the offsets of the
 * output registers. Sprites address the graphics ROM linearly (no bank mapper). */
static void draw_sprites_cps2(const uint32_t primasks[8])
{
    int last = 0x1000 - 4;
    for (int offset = 0; offset < 0x1000; offset += 4)
        if (M.obj2[offset + 1] >= 0x8000 || M.obj2[offset + 3] >= 0xff00) { last = offset - 4; break; }
    const int xoffs = 64 - M.output[CPS2_XOFFS], yoffs = 16 - M.output[CPS2_YOFFS];
    for (int i = last; i >= 0; i -= 4) {
        const uint16_t *s = &M.obj2[i];
        int x = s[0], y = s[1];
        const int priority = x >> 13 & 7, code = s[2] + ((y & 0x6000) << 3), colour = s[3], col = colour & 0x1f;
        const int flipx = colour >> 5 & 1, flipy = colour >> 6 & 1;
        const uint32_t pmask = primasks[priority];
        if (colour & 0x80) { x += M.output[CPS2_XOFFS]; y += M.output[CPS2_YOFFS]; }
        if (colour & 0xff00) {
            const int nx = ((colour & 0x0f00) >> 8) + 1, ny = ((colour & 0xf000) >> 12) + 1;
            for (int nys = 0; nys < ny; nys++) {
                const int sy = (y + nys * 16 + yoffs) & 0x3ff;
                for (int nxs = 0; nxs < nx; nxs++) {
                    const int sx = (x + nxs * 16 + xoffs) & 0x3ff;
                    int block;
                    if (flipy) block = flipx ? code + (nx - 1) - nxs + 0x10 * (ny - 1 - nys) : code + nxs + 0x10 * (ny - 1 - nys);
                    else block = flipx ? code + (nx - 1) - nxs + 0x10 * nys : (code & ~0xf) + ((code + nxs) & 0xf) + 0x10 * nys;
                    draw_sprite(block, col, flipx, flipy, sx, sy, pmask);
                }
            }
        } else {
            draw_sprite(code, col, flipx, flipy, (x + xoffs) & 0x3ff, (y + yoffs) & 0x3ff, pmask);
        }
    }
}

/* The CPS-2 frame (MAME's cps2_state::render_layers): the sprite layer of the layer-control word is taken out, the three tile
 * layers are drawn in the order it gives, each writing its value (1, 2, 4) into the priority plane, and the sprites last, each
 * tested against the plane with the mask its own priority and the latched priority word select. */
static void render_rows_cps2(int first, int last)
{
    row_first = first; row_last = last;
    for (size_t i = (size_t)first * CPS1_SCREEN_W; i < (size_t)last * CPS1_SCREEN_W; i++) { M.pens[i] = 0xbff; M.priority[i] = 0; }
    const uint16_t control = M.cps_b[M.board.layer_control / 2];
    int l0 = control >> 6 & 3, l1 = control >> 8 & 3, l2 = control >> 10 & 3, l3 = control >> 12 & 3;
    int p0 = M.pri_ctrl >> (4 * l0) & 15, p1 = M.pri_ctrl >> (4 * l1) & 15, p2 = M.pri_ctrl >> (4 * l2) & 15;
    const int p3 = M.pri_ctrl >> (4 * l3) & 15;
    if (l0 == 0) { l0 = l1; l1 = 0; p0 = p1; }
    if (l1 == 0) { l1 = l2; l2 = 0; p1 = p2; }
    if (l2 == 0) { l2 = l3; l3 = 0; p2 = p3; }
    uint32_t primasks[8], mask0 = 0xaa, mask1 = 0xcc;
    if (p0 > p1) mask0 &= ~0x88u;
    if (p0 > p2) mask0 &= ~0xa0u;
    if (p1 > p2) mask1 &= ~0xc0u;
    primasks[0] = 0xff;
    for (int i = 1; i < 8; i++) {
        if (i <= p0 && i <= p1 && i <= p2) { primasks[i] = 0xfe; continue; }
        primasks[i] = 0;
        if (i <= p0) primasks[i] |= mask0;
        if (i <= p1) primasks[i] |= mask1;
        if (i <= p2) primasks[i] |= 0xf0;
    }
    const int layers[3] = {l0, l1, l2};
    for (int i = 0; i < 3; i++) {
        if (!layers[i]) continue;
        tile_priority = 1 << i;
        render_layer(layers[i], 0);
    }
    tile_priority = 0;
    draw_sprites_cps2(primasks);
    row_first = 0; row_last = CPS1_SCREEN_H;
}

/* The rest of the picture at VBLANK, or the rows up to the line of a raster interrupt (MAME's update_partial): the registers the game
 * changes after the interrupt apply from the next row on. */
static void render_to_row(int last)
{
    if (last > CPS1_SCREEN_H) last = CPS1_SCREEN_H;
    if (last <= M.rendered_rows) return;
    render_rows_cps2(M.rendered_rows, last);
    M.rendered_rows = last;
}

/* The CPS-2 board's 68000 space (MAME's cps2_state::cps2_map): the program ROM, the object chip's output registers, the RAM shared
 * with the Z80 (low bytes), two object RAM banks, the CPS-A/B registers (mirrored), the inputs with the EEPROM's DO bit, the volume
 * register, the graphics RAM and the work RAM. */
#ifdef RR_CPS2_IOTRACE
/* Development only: the hardware accesses (0x400000-0x8fffff) of the first frames, to compare with MAME's taps on the same bus. */
static void io_trace(char kind, uint32_t address, uint16_t value)
{
    static FILE *file; static int opened;
    if (!opened) { opened = 1; const char *path = getenv("RR_IOTRACE"); file = path ? fopen(path, "w") : NULL; }
    if (file && address >= 0x400000 && address < 0x930000)
        fprintf(file, "%llu %c %06x %04x %d %d\n", (unsigned long long)M.frame_number, kind, address, value, M.line,
                (int)((m68k_now() - M.line_start) * PIXEL_CLOCK / M.board.cpu_clock));
}
#endif

#define CPS2_SERVICE_BIT 0x80u       /* bit 7 of the third switch bank: the service switch, clear = pressed */

static uint16_t cps2_read_bus(uint32_t address);
static uint16_t cps2_read(uint32_t address)
{
    const uint16_t value = cps2_read_bus(address);
#ifdef RR_CPS2_IOTRACE
    io_trace('R', address, value);
#endif
    return value;
}

static uint16_t cps2_read_bus(uint32_t address)
{
    if (address < 0x400000) return address + 1 < M.rom.maincpu_size ? (uint16_t)(M.rom.maincpu[address] << 8 | M.rom.maincpu[address + 1]) : 0;
    if (address >= 0xff0000) return (uint16_t)(M.ram[address & 0xffff] << 8 | M.ram[(address & 0xffff) + 1]);
    if (address >= 0x900000 && address < 0x900000 + GFXRAM_BYTES) return M.gfxram[(address - 0x900000) / 2];
    if (address >= 0x400000 && address < 0x40000c) return M.output[(address - 0x400000) / 2];
    if (address >= 0x618000 && address < 0x61a000) return (uint16_t)(M.qram[0][(address - 0x618000) / 2] | 0xff00);
    if (address >= 0x660000 && address < 0x664002) return (uint16_t)(M.extra_ram[address - 0x660000] << 8 | M.extra_ram[address - 0x660000 + 1]);
    if (address >= 0x708000 && address < 0x710000) return M.objram[M.objram_bank ^ 1][(address & 0x1fff) / 2];
    if ((address >= 0x800140 && address < 0x800180) || (address >= 0x804140 && address < 0x804180)) return cps_b_read((int)(address & 0x3f) / 2);
    if (address == 0x804000) return M.ports[CPS1_IN0];
    if (address == 0x804010) return M.ports[CPS1_IN1];
    /* The board's service switch (IN2 bit 1, active low, MAME's PORT_SERVICE_NO_TOGGLE) is the switch page's "test menu" setting: bit 7 of the
     * third bank, which the game never sees there (a production board has no switch banks, the game reads them as released). */
    if (address == 0x804020) return (uint16_t)(((M.ports[CPS1_IN2] & ~1u) | (cps1_eeprom_read_port(&M.eeprom, m68k_now()) & 1u)) &
                                              ((M.ports[CPS1_DSWC] & CPS2_SERVICE_BIT) ? 0xffffu : ~2u));
    if (address == 0x804030) return 0xe021;                 /* the digital volume at its maximum, no extra memory, no network adapter */
    /* The three switch banks of the development hardware (MAME's lr8 handlers at 0x8040b0 to 0x8040b2): a production board reads them
     * released, and some games do read them (mmatrix at boot). One byte each, on the high lane for the even addresses. */
    if (address == 0x8040b0) return (uint16_t)((M.ports[CPS1_DSWA] & 0xff) << 8 | (M.ports[CPS1_DSWB] & 0xff));
    if (address == 0x8040b2) return (uint16_t)(((M.ports[CPS1_DSWC] | CPS2_SERVICE_BIT) & 0xff) << 8);
    return 0;
}

static void cps2_write_bus(uint32_t address, uint16_t data, uint16_t mask);
static void cps2_write(uint32_t address, uint16_t data, uint16_t mask)
{
#ifdef RR_CPS2_IOTRACE
    io_trace('W', address, data);
#endif
    cps2_write_bus(address, data, mask);
}

static void cps2_write_bus(uint32_t address, uint16_t data, uint16_t mask)
{
    if (address >= 0xff0000) {
        if (mask & 0xff00) M.ram[address & 0xffff] = (uint8_t)(data >> 8);
        if (mask & 0x00ff) M.ram[(address & 0xffff) + 1] = (uint8_t)data;
        return;
    }
    if (address >= 0x900000 && address < 0x900000 + GFXRAM_BYTES) {
        uint16_t *word = &M.gfxram[(address - 0x900000) / 2];
        *word = (uint16_t)((*word & ~mask) | (data & mask));
        return;
    }
    if (address >= 0x400000 && address < 0x40000c) {
        uint16_t *word = &M.output[(address - 0x400000) / 2];
        *word = (uint16_t)((*word & ~mask) | (data & mask));
        return;
    }
    if (address >= 0x618000 && address < 0x61a000) { if (mask & 0x00ff) M.qram[0][(address - 0x618000) / 2] = (uint8_t)data; return; }
    if (address >= 0x660000 && address < 0x664002) {
        if (mask & 0xff00) M.extra_ram[address - 0x660000] = (uint8_t)(data >> 8);
        if (mask & 0x00ff) M.extra_ram[address - 0x660000 + 1] = (uint8_t)data;
        return;
    }
    if (address >= 0x700000 && address < 0x702000) {
        uint16_t *word = &M.objram[M.objram_bank][(address - 0x700000) / 2];
        *word = (uint16_t)((*word & ~mask) | (data & mask));
        return;
    }
    if (address >= 0x708000 && address < 0x710000) {
        uint16_t *word = &M.objram[M.objram_bank ^ 1][(address & 0x1fff) / 2];
        *word = (uint16_t)((*word & ~mask) | (data & mask));
        return;
    }
    if ((address >= 0x800100 && address < 0x800140) || (address >= 0x804100 && address < 0x804140)) {
        const int offset = (int)(address & 0x3f) / 2;
        M.cps_a[offset] = (uint16_t)((M.cps_a[offset] & ~mask) | (data & mask));
        if (offset == A_PALETTE) build_palette();
        return;
    }
    if ((address >= 0x800140 && address < 0x800180) || (address >= 0x804140 && address < 0x804180)) {
        const int offset = (int)(address & 0x3f) / 2;
        M.cps_b[offset] = (uint16_t)((M.cps_b[offset] & ~mask) | (data & mask));
        if (offset == 0x0e / 2) M.raster_reload[2] = M.cps_b[offset] >> 1 & 0xff;
        else if (offset == 0x10 / 2 || offset == 0x12 / 2) {
            M.raster_reload[offset & 1] = M.cps_b[offset] & 0x1ff;
            if (M.cps_b[offset] >> 15 & 1) M.raster_counter[offset & 1] = M.raster_reload[offset & 1];     /* manual reload */
        }
        return;
    }
    if (address == 0x8040e0) { if (mask & 0x00ff) M.objram_bank = data & 1; return; }
    if (address == 0x804040) {
        if (mask & 0xff00) cps1_eeprom_write_port16(&M.eeprom, data & 0x7000u, m68k_now());
        if (mask & 0x00ff) {                      /* bit 3 lets the Z80 run (held in reset while it is low); the coin lines have no visible state */
            const int run = data >> 3 & 1;
            if (!run && M.z80_run) z80_reset(&M.cpu);
            M.z80_run = (uint8_t)run;
        }
        return;
    }
    /* 0x8040a0 and the other unknown writes: no visible state */
}

/* MAME's cps_state::raster_scanline, at the start of line `scanline` of the 262: the two counters reload on line 0 and count down, and a
 * counter reaching zero schedules the interrupt (IPL2) at the position in the line the third register gives. */
static void raster_line(int scanline)
{
    int pending = 0;
    for (int i = 0; i < 2; i++) {
        if (scanline == 0) M.raster_counter[i] = M.raster_reload[i];
        else M.raster_counter[i] = (uint16_t)((M.raster_counter[i] - 1) & 0x1ff);
        if (M.raster_counter[i] == 0) pending = 1;
    }
    M.raster_counter[2] = M.raster_reload[2];
    M.raster_pending = (uint8_t)pending;
}

static void raster_fire(void)
{
    M.irq4 = 1;
    m68k_set_irq(4 | (M.irq2 ? 2 : 0));
    /* the picture is drawn up to this line: what the game's handler changes next applies below it */
    render_to_row(M.line - VISIBLE_Y + 1);
}

/* The board's part of a quick state, after the QSound side: the two object RAM banks and the latched copy, the output registers, the
 * priorities, the bank and Z80 reset lines, the extra RAM, the raster counters and the partial-picture bookkeeping. */
static void cps2_state_put(writer_t *w)
{
    put(w, M.objram, sizeof M.objram); put(w, M.obj2, sizeof M.obj2); put(w, M.output, sizeof M.output);
    put(w, &M.pri_ctrl, sizeof M.pri_ctrl); put(w, &M.objram_bank, 1); put(w, &M.z80_run, 1);
    put(w, M.extra_ram, sizeof M.extra_ram); put(w, M.raster_counter, sizeof M.raster_counter);
    put(w, M.raster_reload, sizeof M.raster_reload); put(w, &M.raster_pending, 1); put(w, &M.irq4, 1);
    put_le(w, (uint32_t)M.rendered_rows, 4); put_le(w, M.line_start, 8);
}

static int cps2_state_get(cps2_tail *tail, const uint8_t *data)
{
    reader_t more = {data, CPS2_TAIL_BYTES, 0, 0};
    tail->z80_run = 1;
    get(&more, tail->objram, sizeof tail->objram); get(&more, tail->obj2, sizeof tail->obj2); get(&more, tail->output, sizeof tail->output);
    get(&more, &tail->pri_ctrl, sizeof tail->pri_ctrl); get(&more, &tail->objram_bank, 1); get(&more, &tail->z80_run, 1);
    get(&more, tail->extra_ram, sizeof tail->extra_ram); get(&more, tail->raster_counter, sizeof tail->raster_counter);
    get(&more, tail->raster_reload, sizeof tail->raster_reload); get(&more, &tail->raster_pending, 1); get(&more, &tail->irq4, 1);
    tail->rendered_rows = (int)get_le(&more, 4); tail->line_start = get_le(&more, 8);
    return !(more.bad || tail->objram_bank > 1 || tail->z80_run > 1 || tail->raster_pending > 1 || tail->irq4 > 1 ||
             tail->rendered_rows < 0 || tail->rendered_rows > CPS1_SCREEN_H);
}

static void cps2_state_commit(const cps2_tail *tail)
{
    memcpy(M.objram, tail->objram, sizeof M.objram); memcpy(M.obj2, tail->obj2, sizeof M.obj2); memcpy(M.output, tail->output, sizeof M.output);
    M.pri_ctrl = tail->pri_ctrl; M.objram_bank = tail->objram_bank; M.z80_run = tail->z80_run;
    memcpy(M.extra_ram, tail->extra_ram, sizeof M.extra_ram);
    memcpy(M.raster_counter, tail->raster_counter, sizeof M.raster_counter); memcpy(M.raster_reload, tail->raster_reload, sizeof M.raster_reload);
    M.raster_pending = tail->raster_pending; M.irq4 = tail->irq4; M.rendered_rows = tail->rendered_rows; M.line_start = tail->line_start;
}

/* The line a raster interrupt falls in: the 68000 runs to the interrupt's position, takes it, and the picture is drawn up to there. */
static void cps2_raster_in_line(void)
{
    uint64_t fire = M.line_start + (uint64_t)M.raster_reload[2] * 2 * M.board.cpu_clock / PIXEL_CLOCK;
    if (fire > M.m68k_target) fire = M.m68k_target;
    while (M.m68k_cycles < fire) {
        m68k_running = 1;
        M.m68k_cycles += (uint64_t)m68k_execute((int)(fire - M.m68k_cycles));
        m68k_running = 0;
    }
    if (M.m68k_cycles - fire < IRQ_SAMPLE_CYCLES) {         /* the 68000 samples its lines before the last cycles of an instruction */
        m68k_running = 1;
        M.m68k_cycles += (uint64_t)m68k_execute(1);
        m68k_running = 0;
    }
    M.raster_pending = 0;
    raster_fire();
}

/* The board's state at power on and at a reset. */
static void cps2_reset_board(void)
{
    memset(M.objram, 0, sizeof M.objram);
    memset(M.obj2, 0, sizeof M.obj2);
    memset(M.output, 0, sizeof M.output);
    memset(M.extra_ram, 0, sizeof M.extra_ram);
    M.pri_ctrl = 0; M.objram_bank = 0; M.z80_run = 1;
    memset(M.raster_counter, 0, sizeof M.raster_counter); memset(M.raster_reload, 0, sizeof M.raster_reload);
    M.raster_reload[0] = M.raster_reload[1] = 0x1ff;
    M.raster_pending = 0; M.irq4 = 0; M.rendered_rows = 0; M.line_start = 0;
}
