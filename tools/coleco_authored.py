"""The authored programs the ColecoVision's ROM-free checks run (tests/test_coleco_conversion.py, tools/coleco_player_selftest.py): a stand-in
BIOS and a cartridge, both written for the checks, 8 KiB each. No byte of a console's BIOS or of a game is here, and none is needed: the
machine takes any 8 KiB for its BIOS (only the converter's own option accepts nothing but the real image), so a check supplies this one.

The BIOS does what the real one does at the two places that matter to the machine: it starts the Z80 (DI, the stack at the top of the
console's RAM, a jump to the cartridge's code at 8002h, past its header word) and it owns the /NMI vector at 0066h, which it forwards to the
cartridge's handler at 8100h (the real BIOS jumps through a pointer in the cartridge's header). Nothing else of the BIOS is imitated.

The cartridge sets the video chip (graphics 1, a checkerboard, black on the backdrop, in the top third of the picture, display and the frame interrupt on), plays a PSG
tone, builds a three-byte routine in RAM (6010h: INC A, RET; its bytes are computed, so that the translator cannot know them ahead) and halts.
Each /NMI (the VDP's frame interrupt) calls that routine (code run from RAM: the interpreter fallback counts it until the conversion learns
it), acknowledges the status, counts the frame in RAM (6000h), reads the first controller in joystick mode (6001h) and in keypad mode (6002h),
the second controller in keypad and joystick modes (6003h, 6004h), and colours the backdrop from the frame count xor the stick and keypad reads
(never black), so the picture moves and answers the controller. A positive control for every reader: change what a controller holds and the
byte and the picture change.
"""
from __future__ import annotations

# The RAM the cartridge writes (the console's RAM is 6000h-63FFh, mirrored): what a check watches.
FRAME_COUNT, STICK_1, KEYPAD_1, KEYPAD_2, STICK_2 = 0x6000, 0x6001, 0x6002, 0x6003, 0x6004
WATCH = (FRAME_COUNT, STICK_1, KEYPAD_1, KEYPAD_2, STICK_2)
NMI_HANDLER = 0x0100                     # the offset of the handler in the cartridge (8100h)


def authored_bios() -> bytes:
    """8 KiB: reset code at 0000h (DI, LD SP,6400h, JP 8002h: past the cartridge's header word) and the /NMI vector at 0066h (JP 8100h); FFh elsewhere."""
    bios = bytearray(b'\xFF' * 0x2000)
    bios[0x0000:0x0007] = bytes([0xF3, 0x31, 0x00, 0x64, 0xC3, 0x02, 0x80])
    bios[0x0066:0x0069] = bytes([0xC3, NMI_HANDLER & 0xFF, 0x80 | NMI_HANDLER >> 8])
    return bytes(bios)


def authored_cartridge() -> bytes:
    """8 KiB, mapped at 8000h; it begins with the header word the real BIOS looks for (AAh 55h) followed by the start of the program."""
    cart = bytearray(b'\xFF' * 0x2000)

    def put(at: int, data: list) -> None:
        cart[at:at + len(data)] = bytes(data)
    out = lambda port: [0xD3, port]                                                # OUT (port),A
    reg = lambda number, value: [0x3E, value, *out(0xA1), 0x3E, 0x80 | number, *out(0xA1)]          # VDP register `number` = value
    where = lambda address: [0x3E, address & 0xFF, *out(0xA1), 0x3E, 0x40 | address >> 8, *out(0xA1)]   # the VRAM write address
    byte = lambda value: [0x3E, value, *out(0xA0)]                                  # one byte to the VRAM
    program = [0x31, 0x00, 0x64,                                                    # LD SP,6400h
               *reg(0, 0x00), *reg(2, 0x06), *reg(3, 0x80), *reg(4, 0x00), *reg(7, 0x04),      # graphics 1: names 1800h, colours 2000h, patterns 0
               *where(0x0008), *[x for value in (0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x55) for x in byte(value)],   # tile 1: a checkerboard
               *where(0x2000), *byte(0x10),                                         # colours of tiles 0-7: black on the backdrop (colour 0)
               *where(0x1800), 0x06, 0x00, 0x3E, 0x01, *out(0xA0), 0x10, 0xFA,     # 256 names of tile 1 (LD B,0 ... DJNZ): the top third
               *reg(1, 0xE0),                                                       # display and the frame interrupt on
               0x3E, 0x8E, *out(0xE0), 0x3E, 0x0F, *out(0xE0), 0x3E, 0x90, *out(0xE0),      # PSG: a tone on channel 0, full volume
               0x21, 0x10, 0x60, 0x3E, 0x1E, 0x87, 0x77, 0x23, 0x3E, 0xC8, 0x3C, 0x77,     # RAM at 6010h: 3Ch (INC A), C9h (RET), computed
               0xFB, 0x76, 0x18, 0xFD]                                              # EI, HALT, JR back to the HALT
    assert 2 + len(program) < NMI_HANDLER
    put(0x0000, [0xAA, 0x55])                                                      # the header word (not read by the stand-in BIOS)
    put(0x0002, program)
    handler = [0xF5,                                                               # PUSH AF
               0xCD, 0x10, 0x60,                                                   # CALL 6010h: the routine built in RAM (the interpreter runs it)
               0xDB, 0xA1,                                                         # IN A,(A1h): the status, acknowledging the frame flag
               0x3A, 0x00, 0x60, 0x3C, 0x32, 0x00, 0x60,                           # the frame count at 6000h
               *out(0xC0), 0xDB, 0xFC, 0x32, 0x01, 0x60,                           # joystick mode; controller 1 -> 6001h
               *out(0x80), 0xDB, 0xFC, 0x32, 0x02, 0x60,                           # keypad mode; controller 1 -> 6002h
               0xDB, 0xFF, 0x32, 0x03, 0x60,                                       # controller 2 (keypad mode) -> 6003h
               *out(0xC0), 0xDB, 0xFF, 0x32, 0x04, 0x60,                           # joystick mode; controller 2 -> 6004h
               0x3A, 0x01, 0x60, 0x47, 0x3A, 0x02, 0x60, 0x07, 0xA8, 0x47,         # B = the stick read xor the keypad read rotated left (no key held: 0)
               0x3A, 0x00, 0x60, 0xA8, 0xE6, 0x0F, 0xF6, 0x08,                     # A = (frame count xor B) and 0Fh, or 8: never black
               *out(0xA1), 0x3E, 0x87, *out(0xA1),                                 # VDP register 7: the backdrop colour
               0xF1, 0xED, 0x45]                                                   # POP AF, RETN
    put(NMI_HANDLER, handler)
    return bytes(cart)
