/* Checks of the CPC's CRTC (cpc_crtc.c), Gate Array (cpc_gate_array.c) and PPI with its keyboard (cpc_ppi.c), stepped as the
 * machine steps them, one character (1 us) at a time: the firmware's 50 Hz frame and its 300 Hz interrupt, the screen
 * addresses, what differs by CRTC type, the picture of a known screen, the AY bus and the keyboard matrix as the firmware
 * scans it. Built by tools/cpc_hardware_selftest.py; no ROM, no game. MIT, Retro-Recomp. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cpc_bus.h"
#include "cpc_crtc.h"
#include "cpc_gate_array.h"
#include "cpc_ppi.h"

static unsigned passed, failed;

static void expect(const char *what, int ok)
{
    if (ok) ++passed; else { ++failed; fprintf(stderr, "FAIL: %s\n", what); }
}

static CpcCrtc crtc;
static CpcGateArray ga;
static uint8_t ram[65536];
static uint32_t picture[CPC_SCREEN_WIDTH * CPC_SCREEN_HEIGHT];

/* Step until the VSYNC starts (a frame boundary); the characters stepped, or 0 after a million. */
static unsigned to_vsync(void)
{
    unsigned steps = 0;
    int was = cpc_crtc_out(&crtc).vsync;
    while (++steps < 1000000) {
        cpc_crtc_step(&crtc);
        int now = cpc_crtc_out(&crtc).vsync;
        if (now && !was) return steps;
        was = now;
    }
    return 0;
}

static void check_crtc(void)
{
    cpc_crtc_reset(&crtc, CPC_CRTC_TYPE1);
    to_vsync();
    expect("the firmware's frame: 64 x 312 characters from VSYNC to VSYNC (50.08 Hz)", to_vsync() == 64 * 312);
    unsigned display = 0, hsync = 0, vsync = 0;
    for (unsigned i = 0; i < 64 * 312; ++i) {
        CpcCrtcOut o = cpc_crtc_out(&crtc);
        display += o.display;
        hsync += o.hsync;
        vsync += o.vsync;
        cpc_crtc_step(&crtc);
    }
    expect("40 x 200 characters displayed a frame", display == 40 * 200);
    expect("an HSYNC of 14 characters each of the 312 lines", hsync == 14 * 312);
    expect("type 1: a VSYNC of 16 lines", vsync == 16 * 64);

    /* The first displayed character: MA 3000h, the byte at C000h; its next line C800h; the next row C050h. */
    cpc_crtc_reset(&crtc, CPC_CRTC_TYPE1);
    to_vsync();
    while (!cpc_crtc_out(&crtc).display) cpc_crtc_step(&crtc);
    CpcCrtcOut o = cpc_crtc_out(&crtc);
    expect("the screen starts at C000h", o.ma == 0x3000 && o.ra == 0 && cpc_crtc_address(o.ma, o.ra, 0) == 0xC000);
    for (unsigned i = 0; i < 64; ++i) cpc_crtc_step(&crtc);
    o = cpc_crtc_out(&crtc);
    expect("its second line at C800h", o.ra == 1 && cpc_crtc_address(o.ma, o.ra, 1) == 0xC801);
    for (unsigned i = 0; i < 7 * 64; ++i) cpc_crtc_step(&crtc);
    o = cpc_crtc_out(&crtc);
    expect("the second row at C050h", o.ra == 0 && o.ma == 0x3000 + 40 && cpc_crtc_address(o.ma, o.ra, 0) == 0xC050);

    /* R12/R13 written during row 0: type 1 takes them at the next line, type 0 at the next frame. */
    for (int type = CPC_CRTC_TYPE0; type <= CPC_CRTC_TYPE1; ++type) {
        cpc_crtc_reset(&crtc, (uint8_t)type);
        to_vsync();
        while (!cpc_crtc_out(&crtc).display) cpc_crtc_step(&crtc);
        cpc_crtc_select(&crtc, 13);
        cpc_crtc_write(&crtc, 0x20);
        for (unsigned i = 0; i < 64; ++i) cpc_crtc_step(&crtc);
        while (!cpc_crtc_out(&crtc).display) cpc_crtc_step(&crtc);
        uint16_t ma = cpc_crtc_out(&crtc).ma;
        if (type == CPC_CRTC_TYPE1)
            expect("type 1: R13 written in row 0 shows from the next line", ma == 0x3020);
        else
            expect("type 0: R13 written in row 0 waits for the next frame", ma == 0x3000);
        to_vsync();
        while (!cpc_crtc_out(&crtc).display) cpc_crtc_step(&crtc);
        if (type == CPC_CRTC_TYPE0)
            expect("type 0: and shows in the next frame", cpc_crtc_out(&crtc).ma == 0x3020);
    }

    cpc_crtc_reset(&crtc, CPC_CRTC_TYPE0);
    to_vsync();
    vsync = 0;
    for (unsigned i = 0; i < 64 * 312; ++i) { vsync += cpc_crtc_out(&crtc).vsync; cpc_crtc_step(&crtc); }
    expect("type 0: the VSYNC width from R3 (8 lines for 8Eh)", vsync == 8 * 64);
    cpc_crtc_select(&crtc, 5);
    cpc_crtc_write(&crtc, 2);
    to_vsync();
    expect("R5 adds lines to the frame (314)", to_vsync() == 64 * 314);

    cpc_crtc_reset(&crtc, CPC_CRTC_TYPE0);
    cpc_crtc_select(&crtc, 12);
    expect("type 0 reads R12 back", cpc_crtc_read(&crtc) == 0x30);
    cpc_crtc_reset(&crtc, CPC_CRTC_TYPE1);
    cpc_crtc_select(&crtc, 12);
    uint8_t r12 = cpc_crtc_read(&crtc);
    cpc_crtc_select(&crtc, 31);
    expect("type 1 reads R12 as 0 and R31 as FFh", r12 == 0x00 && cpc_crtc_read(&crtc) == 0xFF);
    cpc_crtc_select(&crtc, 14);
    cpc_crtc_write(&crtc, 0xFF);
    expect("R14 keeps its six bits", cpc_crtc_read(&crtc) == 0x3F);
    cpc_crtc_reset(&crtc, CPC_CRTC_TYPE2);
    cpc_crtc_select(&crtc, 12);
    expect("type 2 reads R12 as 0", cpc_crtc_read(&crtc) == 0x00);
    cpc_crtc_reset(&crtc, CPC_CRTC_TYPE1);
    to_vsync();
    expect("type 1 status: bit 5 in the vertical blanking", (cpc_crtc_status(&crtc) & 0x20) == 0x20);
    while (!cpc_crtc_out(&crtc).display) cpc_crtc_step(&crtc);
    expect("and clear on screen", (cpc_crtc_status(&crtc) & 0x20) == 0);
}

/* The machine's loop: one character of the CRTC and the Gate Array; the interrupts and frames seen. */
static unsigned run(unsigned characters, unsigned *interrupts, unsigned *frames, int acknowledge, uint32_t *pic)
{
    unsigned last_irq_line = 0;
    for (unsigned i = 0; i < characters; ++i) {
        cpc_crtc_step(&crtc);
        unsigned events = cpc_ga_tick(&ga, cpc_crtc_out(&crtc), ram, pic);
        if (events & CPC_GA_INTERRUPT) {
            ++*interrupts;
            last_irq_line = ga.beam_y;
            if (acknowledge) cpc_ga_acknowledge(&ga);
        }
        if (events & CPC_GA_FRAME) ++*frames;
    }
    return last_irq_line;
}

static void check_gate_array(void)
{
    uint8_t pens[8];
    expect("mode 2: eight pixels, bit 7 first", cpc_byte_pens(2, 0x81, pens) == 8 && pens[0] == 1 && pens[1] == 0
        && pens[7] == 1);
    expect("mode 1: four pixels, pen bits 7/3 for the first", cpc_byte_pens(1, 0x88, pens) == 4 && pens[0] == 3
        && pens[1] == 0);
    expect("mode 1: bit 4 alone is the last pixel's pen 1", cpc_byte_pens(1, 0x10, pens) == 4 && pens[3] == 1);
    expect("mode 0: two pixels, pen bits 7, 3, 5, 1 for the first", cpc_byte_pens(0, 0xAA, pens) == 2 && pens[0] == 15
        && pens[1] == 0);
    expect("mode 0: bits 6, 2, 4, 0 for the second", cpc_byte_pens(0, 0x41, pens) == 2 && pens[1] == 9 && pens[0] == 0);
    expect("mode 3: mode 0's pixels on four pens", cpc_byte_pens(3, 0xAA, pens) == 2 && pens[0] == 3);
    expect("colours: 14h black, 0Bh bright white, 00h white (50 %), 1Ch red (50 %)", cpc_colour(0x14) == 0
        && cpc_colour(0x0B) == 0xFFFFFF && cpc_colour(0x00) == 0x808080 && cpc_colour(0x1C) == 0x800000);
    int distinct = 0;
    for (unsigned a = 0; a < 32; ++a) {
        int seen = 0;
        for (unsigned b = 0; b < a; ++b) seen |= cpc_colour((uint8_t)a) == cpc_colour((uint8_t)b);
        distinct += !seen;
    }
    expect("27 distinct colours among the 32", distinct == 27);

    uint8_t banks[4];
    cpc_ram_banks(0, banks);
    int ok = banks[0] == 0 && banks[3] == 3;
    cpc_ram_banks(1, banks);
    ok &= banks[3] == 7 && banks[2] == 2;
    cpc_ram_banks(2, banks);
    ok &= banks[0] == 4 && banks[3] == 7;
    cpc_ram_banks(3, banks);
    ok &= banks[1] == 3 && banks[3] == 7;
    cpc_ram_banks(6, banks);
    ok &= banks[1] == 6 && banks[0] == 0;
    expect("the 6128's eight RAM configurations", ok);
    ga.has_ram_pal = 0;
    cpc_ga_reset(&ga);
    cpc_ga_write(&ga, 0xC2);
    expect("no PAL (464, 664): the RAM configuration is ignored", ga.ram_config == 0);
    ga.has_ram_pal = 1;
    cpc_ga_reset(&ga);
    cpc_ga_write(&ga, 0xC2);
    expect("6128: the PAL takes it", ga.ram_config == 2 && ga.has_ram_pal);

    cpc_crtc_reset(&crtc, CPC_CRTC_TYPE1);
    cpc_ga_reset(&ga);
    unsigned interrupts = 0, frames = 0;
    run(64 * 312 * 3, &interrupts, &frames, 1, NULL);
    interrupts = frames = 0;
    unsigned line = run(64 * 312 * 10, &interrupts, &frames, 1, NULL);
    expect("300 Hz: six interrupts a frame, ten frames", interrupts == 60 && frames == 10);
    /* From any counter, the VSYNC brings the interrupts to the same lines within two frames. */
    unsigned lines[2];
    for (unsigned k = 0; k < 2; ++k) {
        cpc_crtc_reset(&crtc, CPC_CRTC_TYPE1);
        cpc_ga_reset(&ga);
        ga.counter = (uint8_t)(k ? 40 : 7);
        interrupts = frames = 0;
        run(64 * 312 * 3 + 64 * 100, &interrupts, &frames, 1, NULL);
        lines[k] = line = run(64 * 312, &interrupts, &frames, 1, NULL);
    }
    expect("the VSYNC sets the interrupt phase, whatever the counter was", lines[0] == lines[1]);
    ga.counter = 40;
    ga.interrupt = 1;
    cpc_ga_acknowledge(&ga);
    expect("the acknowledge clears the counter's bit 5 and the request", ga.counter == 8 && !ga.interrupt);
    ga.counter = 30;
    cpc_ga_write(&ga, 0x80 | 0x10 | 0x01);
    expect("mode byte with bit 4: counter cleared; the mode waits for the HSYNC", ga.counter == 0 && ga.mode_next == 1);
    cpc_ga_write(&ga, 0x82);
    while (!cpc_crtc_out(&crtc).hsync) { cpc_crtc_step(&crtc); cpc_ga_tick(&ga, cpc_crtc_out(&crtc), NULL, NULL); }
    expect("the mode written is taken at the HSYNC", ga.mode == 2 && ga.rom_config == 0);
    cpc_ga_write(&ga, 0x8C);
    expect("the ROM enables: both off", ga.rom_config == 0x0C);
    unsigned no_ack = 0;
    cpc_crtc_reset(&crtc, CPC_CRTC_TYPE1);
    cpc_ga_reset(&ga);
    frames = 0;
    run(64 * 312 * 4, &no_ack, &frames, 0, NULL);
    expect("without acknowledge the counter still raises six a frame (the request stays up)", no_ack == 24 && ga.interrupt);
}

static void check_picture(void)
{
    cpc_crtc_reset(&crtc, CPC_CRTC_TYPE1);
    cpc_ga_reset(&ga);
    memset(ram, 0, sizeof ram);
    memset(ram + 0xC000, 0x80, 0x4000);                              /* mode 1: each byte's first pixel pen 1 */
    cpc_ga_write(&ga, 0x10); cpc_ga_write(&ga, 0x40 | 0x04);         /* border: blue */
    cpc_ga_write(&ga, 0x00); cpc_ga_write(&ga, 0x40 | 0x14);         /* pen 0: black */
    cpc_ga_write(&ga, 0x01); cpc_ga_write(&ga, 0x40 | 0x0B);         /* pen 1: bright white */
    unsigned interrupts = 0, frames = 0;
    run(64 * 312 * 2, &interrupts, &frames, 1, picture);
    uint32_t border = cpc_colour(0x04), white = 0xFFFFFF;
    expect("the border's colour at the window's corner", picture[0] == border && picture[767] == border
        && picture[271 * 768] == border);
    /* The display starts after the 4-character, 36-line border: pixel (64, 36) is the first byte's first pixel. */
    expect("the first screen byte: pen 1 for two mode-2 pixels, then pen 0", picture[36 * 768 + 64] == white
        && picture[36 * 768 + 65] == white && picture[36 * 768 + 66] == 0);
    expect("the display ends 40 characters later", picture[36 * 768 + 64 + 640] == border
        && picture[36 * 768 + 64 + 639] == 0);
    expect("and 200 lines lower", picture[(36 + 199) * 768 + 64] == white && picture[(36 + 200) * 768 + 64] == border);
    ram[0xC000] = 0x08;                                              /* first pixel pen 2 (black: not set), second... */
    cpc_ga_write(&ga, 0x02); cpc_ga_write(&ga, 0x40 | 0x0C);         /* pen 2: bright red */
    run(64 * 312, &interrupts, &frames, 1, picture);
    expect("a byte changed shows in the next frame (pen 2)", picture[36 * 768 + 64] == 0xFF0000);
}

/* A stand-in AY: register 14 reads the keyboard row, every write recorded. */
static CpcPpi ppi;
static uint8_t ay_reg[16], ay_selected;
static unsigned ay_writes;
static void ay_latch(void *c, uint8_t r) { (void)c; ay_selected = r & 15; }
static void ay_write(void *c, uint8_t v) { (void)c; ay_reg[ay_selected] = v; ++ay_writes; }
static uint8_t ay_read(void *c) { (void)c; return ay_selected == 14 ? cpc_ppi_row(&ppi) : ay_reg[ay_selected]; }

/* The firmware's way of reading one row of the matrix. */
static uint8_t scan_row(const CpcPsgBus *bus, uint8_t row)
{
    cpc_ppi_write(&ppi, 0, 14, bus);                                 /* F4xx: register 14 */
    cpc_ppi_write(&ppi, 2, 0xC0, bus);                               /* F6xx: latch */
    cpc_ppi_write(&ppi, 2, 0x00, bus);                               /* inactive */
    cpc_ppi_write(&ppi, 3, 0x92, bus);                               /* F7xx: port A input */
    cpc_ppi_write(&ppi, 2, (uint8_t)(0x40 | row), bus);              /* read, with the row */
    uint8_t v = cpc_ppi_read(&ppi, 0, 0, bus);
    cpc_ppi_write(&ppi, 3, 0x82, bus);                               /* port A output again */
    return v;
}

static void check_ppi(void)
{
    CpcPsgBus bus = { NULL, ay_latch, ay_write, ay_read };
    memset(&ppi, 0, sizeof ppi);
    cpc_ppi_reset(&ppi);
    cpc_ppi_write(&ppi, 3, 0x82, &bus);
    cpc_ppi_write(&ppi, 0, 7, &bus);
    cpc_ppi_write(&ppi, 2, 0xC0, &bus);
    cpc_ppi_write(&ppi, 2, 0x00, &bus);
    cpc_ppi_write(&ppi, 0, 0x3F, &bus);
    cpc_ppi_write(&ppi, 2, 0x80, &bus);
    cpc_ppi_write(&ppi, 2, 0x00, &bus);
    expect("the AY is written through the PPI: register 7 holds 3Fh", ay_reg[7] == 0x3F && ay_writes == 1);
    expect("no key: every row reads FFh", scan_row(&bus, 0) == 0xFF && scan_row(&bus, 9) == 0xFF);
    cpc_ppi_key(&ppi, CPC_KEY_ESC, 1);
    expect("ESC down: row 8 reads FBh", scan_row(&bus, 8) == 0xFB && scan_row(&bus, 7) == 0xFF);
    cpc_ppi_key(&ppi, CPC_KEY_ESC, 0);
    ppi.joystick[0] = CPC_JOY_FIRE1 | CPC_JOY_LEFT;
    expect("joystick 1 on row 9 (fire 1 bit 5, left bit 2)", scan_row(&bus, 9) == (uint8_t)~0x24);
    ppi.joystick[1] = CPC_JOY_UP;
    expect("joystick 2 on row 6, shared with the 6 key", scan_row(&bus, 6) == 0xFE);
    cpc_ppi_key(&ppi, CPC_KEY_6, 1);
    expect("the key and the stick read as one line", scan_row(&bus, 6) == 0xFE);
    expect("rows past 9 read FFh", scan_row(&bus, 12) == 0xFF);
    expect("port B: Amstrad, 50 Hz, VSYNC on bit 0", cpc_ppi_read(&ppi, 1, 1, &bus) == 0x7F
        && cpc_ppi_read(&ppi, 1, 0, &bus) == 0x7E);
    cpc_ppi_write(&ppi, 3, 0x82, &bus);
    cpc_ppi_write(&ppi, 3, 0x09, &bus);                              /* bit set: C4, the tape motor */
    expect("bit set / reset of port C (the tape motor)", (ppi.port_c & 0x10) && cpc_ppi_read(&ppi, 2, 0, &bus) == 0x10);
    cpc_ppi_write(&ppi, 3, 0x08, &bus);
    expect("and reset", (ppi.port_c & 0x10) == 0);
    cpc_ppi_write(&ppi, 2, 0x45, &bus);
    cpc_ppi_write(&ppi, 3, 0x82, &bus);
    expect("a mode byte clears the outputs", ppi.port_c == 0 && ppi.port_a == 0);
}

static void check_bus(void)
{
    expect("7F00h: the Gate Array only", cpc_io_devices(0x7F00) == CPC_IO_GATE_ARRAY);
    expect("BC00h: the CRTC, select", cpc_io_devices(0xBC00) == CPC_IO_CRTC && cpc_io_function(0xBC00) == 0);
    expect("BD00h: the CRTC, write; BF00h read", cpc_io_function(0xBD00) == 1 && cpc_io_function(0xBF00) == 3
        && cpc_io_devices(0xBF00) == CPC_IO_CRTC);
    expect("DF00h: the upper ROM select", cpc_io_devices(0xDF00) == CPC_IO_ROM_SELECT);
    expect("EF00h: the printer", cpc_io_devices(0xEF00) == CPC_IO_PRINTER);
    expect("F400h-F700h: the PPI ports", cpc_io_devices(0xF400) == CPC_IO_PPI && cpc_io_function(0xF600) == 2
        && cpc_io_function(0xF700) == 3);
    expect("FA7Eh: the floppy motor", cpc_io_devices(0xFA7E) == CPC_IO_FDC_MOTOR);
    expect("FB7Eh, FB7Fh: the floppy controller", cpc_io_devices(0xFB7E) == CPC_IO_FDC && cpc_io_devices(0xFB7F) == CPC_IO_FDC);
    expect("a careless 0000h reaches the CRTC, ROM select, printer, PPI and motor at once",
        cpc_io_devices(0x0000) == (CPC_IO_CRTC | CPC_IO_ROM_SELECT | CPC_IO_PRINTER | CPC_IO_PPI | CPC_IO_FDC_MOTOR));
    CpcGateArray g;
    g.has_ram_pal = 1;
    cpc_ga_reset(&g);
    CpcMap m = cpc_memory_map(&g, 0);
    expect("at reset: lower ROM, RAM, RAM, BASIC", m.source[0] == CPC_SOURCE_LOWER_ROM && m.source[1] == CPC_SOURCE_RAM
        && m.source[3] == CPC_SOURCE_BASIC && m.ram[3] == 3);
    m = cpc_memory_map(&g, 7);
    expect("upper ROM 7: AMSDOS", m.source[3] == CPC_SOURCE_AMSDOS);
    cpc_ga_write(&g, 0x8C);
    cpc_ga_write(&g, 0xC1);
    m = cpc_memory_map(&g, 7);
    expect("both ROMs off and configuration 1: RAM banks 0, 1, 2, 7", m.source[0] == CPC_SOURCE_RAM
        && m.source[3] == CPC_SOURCE_RAM && m.ram[0] == 0 && m.ram[3] == 7);
    g.has_ram_pal = 0;
    m = cpc_memory_map(&g, 0);
    expect("a 64 KiB machine ignores the configuration", m.ram[3] == 3);
}

int main(void)
{
    check_bus();
    check_crtc();
    check_gate_array();
    check_picture();
    check_ppi();
    printf("{\"passed\": %u, \"failed\": %u}\n", passed, failed);
    return failed ? 1 : 0;
}
