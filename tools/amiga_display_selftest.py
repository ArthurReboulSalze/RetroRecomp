"""Agnus and Denise recorded, scenario by scenario (no ROM image, no Kickstart, no disk; needs a compiler and a first build of vAmiga's Core).

    python -B tools/amiga_display_selftest.py [--scenarios N] [--frames N] [--seed N]

Each scenario is authored here: a boot ROM of a few instructions, a 68000 program in chip RAM, bitmaps, sprites and a Copper list. The
program sets up a display (lores or hires, one to six planes, dual playfield, HAM, scroll, priorities, sprites, collisions) and then
hammers it: display register writes, chip RAM writes into the displayed bitmap, reads of VHPOSR, VPOSR, CLXDAT, DMACONR and of unmapped
memory, blits into the bitmap and beside it, delays and waits for a line. `native/amiga_machine/amiga_display_checks.cpp` runs it on the
machine an export uses and records every instruction (Agnus's clock and beam position, the 68000's registers) and every frame (the
snapshots of Agnus, Denise, Paula, the CIAs and the CPU, chip and slow RAM, the sound, CLXDAT, every texture row).

Without `--against`, each scenario runs twice in this build: once with the bitplane slots of a line taken in a batch (Agnus step 2),
once with every line on vAmiga's events and line pass (`--per-slot`, steps 2 and 3 off); the records must be equal, and the
lines batched and passed in one loop (Denise step 3) are counted. With
`--against EXE` the second run is a checks program built before a change (side A). Either way an injected fault (a bit of chip RAM, one
colour clock) must be seen and placed. This shows that two runs agree, not that either matches the hardware.

The checks program is built with stage 7's bus model in shadow (`native/amiga_machine/amiga_bus.h`): every line's table of slots is
compared with vAmiga's bus owners and every CPU bus wait the table can predict with the wait vAmiga gave; both must be equal on every
scenario, and each fault planted in the model (`SHADOW_FAULTS`) must be seen. About half the scenarios run with interrupts on and a CIA-B
TOD alarm; programs race their own blits, rewrite sprite data and the Copper's list while they are fetched.
"""
from __future__ import annotations

import argparse
import json
import random
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCENARIOS = 12
FRAMES = 4
CHIP_KB = 512
PROGRAM = 0x1000          # the 68000 program
COPPER = 0x8000           # the Copper list
SPRITES = 0x9000          # eight sprites, 0x200 bytes each
NULL_SPRITE = 0xA000      # an empty sprite (two zero words)
BITMAP = 0x10000          # six planes of 0x8000 bytes
SCRATCH = 0x40000         # blits beside the display, random data read back
SCRATCH_END = 0x7F000
UNTOUCHED = 0x7F800       # never written by a scenario: where the injected RAM fault goes
HANDLER = 0x0F00          # the interrupt handler (scenarios with interrupts on)
UNMAPPED = 0x200000       # no fast RAM in this machine: an open bus
SLOW = 0xC00000           # slow RAM, on Agnus's bus

# Custom registers (offsets from $DFF000).
DMACONR, VPOSR, VHPOSR, JOY0DAT, CLXDAT = 0x002, 0x004, 0x006, 0x00A, 0x00E
BLTCON0, BLTCON1, BLTAFWM, BLTALWM, BLTCPT, BLTBPT, BLTAPT, BLTDPT, BLTSIZE = 0x040, 0x042, 0x044, 0x046, 0x048, 0x04C, 0x050, 0x054, 0x058
BLTCMOD, BLTBMOD, BLTAMOD, BLTDMOD = 0x060, 0x062, 0x064, 0x066
COP1LC, COPJMP1, DIWSTRT, DIWSTOP, DDFSTRT, DDFSTOP, DMACON, CLXCON, INTENA, INTREQ = 0x080, 0x088, 0x08E, 0x090, 0x092, 0x094, 0x096, 0x098, 0x09A, 0x09C
CIAB_TODLO, CIAB_TODMID, CIAB_TODHI, CIAB_ICR, CIAB_CRB = 0xBFD800, 0xBFD900, 0xBFDA00, 0xBFDD00, 0xBFDF00
CIAA_ICR = 0xBFED01
BPLPT, SPRPT = 0x0E0, 0x120
DSKBYTR, DSKLEN, DSKSYNC = 0x01A, 0x024, 0x07E
CIAB_PRB = 0xBFD100
BPLCON0, BPLCON1, BPLCON2, BPL1MOD, BPL2MOD, BPL1DAT, COLOR = 0x100, 0x102, 0x104, 0x108, 0x10A, 0x110, 0x180


class Assembler:
    """The few 68000 forms the scenarios need, big endian words."""

    def __init__(self, origin: int):
        self.origin = origin
        self.words: list[int] = []

    @property
    def here(self) -> int:
        return self.origin + 2 * len(self.words)

    def w(self, *words: int) -> None:
        for word in words:
            self.words.append(word & 0xFFFF)

    def l(self, value: int) -> None:
        self.w(value >> 16, value)

    def move_w_imm_abs(self, value: int, address: int) -> None:
        self.w(0x33FC, value)
        self.l(address)

    def move_l_imm_abs(self, value: int, address: int) -> None:
        self.w(0x23FC)
        self.l(value)
        self.l(address)

    def move_w_abs_d(self, address: int, d: int) -> None:
        self.w(0x3039 | d << 9)
        self.l(address)

    def move_l_abs_d(self, address: int, d: int) -> None:
        self.w(0x2039 | d << 9)
        self.l(address)

    def move_w_d_abs(self, d: int, address: int) -> None:
        self.w(0x33C0 | d)
        self.l(address)

    def moveq(self, value: int, d: int) -> None:
        self.w(0x7000 | d << 9 | value & 0xFF)

    def dbra(self, d: int, target: int) -> None:
        self.w(0x51C8 | d)
        self.w(target - self.here)

    def bra_w(self, target: int) -> None:
        self.w(0x6000)
        self.w(target - self.here)

    def jmp_abs(self, address: int) -> None:
        self.w(0x4EF9)
        self.l(address)

    def lea_abs_a7(self, address: int) -> None:
        self.w(0x4FF9)
        self.l(address)

    def wait_blitter(self) -> None:
        """btst #6,$dff002 ; bne.s back (DMACONR's BBUSY, bit 14)."""
        top = self.here
        self.w(0x0839, 0x0006)
        self.l(0xDFF000 + DMACONR)
        self.w(0x6600 | ((top - (self.here + 2)) & 0xFF))

    def wait_line(self, line: int) -> None:
        """move.w $dff006,d6 ; lsr.w #8,d6 ; cmpi.w #line,d6 ; bcs.s back: until VHPOSR's line byte reaches `line`."""
        top = self.here
        self.move_w_abs_d(0xDFF000 + VHPOSR, 6)
        self.w(0xE04E, 0x0C46, line & 0xFF)
        self.w(0x6500 | ((top - (self.here + 2)) & 0xFF))

    def data(self) -> bytes:
        return b''.join(struct.pack('>H', word) for word in self.words)


def boot_rom() -> bytes:
    """A 512 KiB ROM of our own: the session's quieting sequence (amiga_session.cpp boot_rom), then a jump into the scenario's program."""
    code = Assembler(0xF800D2)
    code.w(0x46FC, 0x2700)                                  # move.w #$2700,sr
    for value, address in ((0x03, 0xBFE201), (0x02, 0xBFE001)):  # CIA-A: OVL and LED out, OVL off (chip RAM at 0)
        code.w(0x13FC, value)
        code.l(address)
    for register in (INTENA, DMACON, INTREQ):
        code.move_w_imm_abs(0x7FFF, 0xDFF000 + register)
    for value, address in ((0xF8, 0xBFD000), (0xFF, 0xBFD100), (0xC0, 0xBFD200), (0xFF, 0xBFD300)):
        code.w(0x13FC, value)
        code.l(address)
    code.lea_abs_a7(0x0007FFF0 if CHIP_KB >= 512 else 0x3FFF0)
    code.jmp_abs(PROGRAM)
    rom = bytearray(512 * 1024)
    rom[0:8] = struct.pack('>4H', 0x1114, 0x4EF9, 0x00F8, 0x00D2)
    body = code.data()
    rom[0xD2:0xD2 + len(body)] = body
    return bytes(rom)


@dataclass
class Scenario:
    seed: int
    ntsc: bool
    frames: int
    regions: list = field(default_factory=list)     # (address, bytes)
    fault_address: int = 0
    summary: dict = field(default_factory=dict)

    def write(self, path: Path) -> None:
        rom = boot_rom()
        out = bytearray(b'RRDS')
        out += struct.pack('<6I', 1, 1 if self.ntsc else 0, CHIP_KB, self.frames, self.fault_address, len(rom))
        out += rom
        out += struct.pack('<I', len(self.regions))
        for address, data in self.regions:
            out += struct.pack('<2I', address, len(data))
            out += data
        path.write_bytes(bytes(out))


def generate(seed: int, frames: int = FRAMES, actions: int = 900) -> Scenario:
    """A random but plausible display and a random program that works on it. Everything stays inside the scenario's own memory."""
    r = random.Random(seed)
    ntsc = r.random() < 0.25
    hires = r.random() < 0.3
    planes = r.randint(1, 4 if hires else 6)
    dual = planes >= 2 and r.random() < 0.25
    ham = not hires and planes == 6 and not dual and r.random() < 0.4
    bplcon0 = planes << 12 | (0x8000 if hires else 0) | (0x0400 if dual else 0) | (0x0800 if ham else 0) | 0x0200
    width = 80 if hires else 40
    stop_line = 0x2C if not ntsc else 0xF4          # PAL stops at line 300 ($12C), NTSC at 244
    diwstrt = (0x2C + r.choice((0, 0, 0, 4, -6))) << 8 | (0x81 + r.choice((0, 0, 8, -8, 16)))
    diwstop = (stop_line + r.choice((0, 0, -8, 8))) << 8 & 0xFF00 | (0xC1 + r.choice((0, 0, -8, 8)))
    ddf = r.choice(((0x3C, 0xD4), (0x38, 0xD0), (0x30, 0xD0), (0x38, 0xC8))) if hires else r.choice(((0x38, 0xD0), (0x38, 0xD0), (0x30, 0xD0), (0x28, 0xD8), (0x40, 0xC8)))
    modulo = lambda: r.choice((0, 0, 0, 2, -2, -width, 8, 40))
    colours = [r.randrange(0x1000) for _ in range(32)]
    plane = lambda n: BITMAP + n * 0x8000

    # Chip RAM: bitmaps of noise with runs of zero (so some lines are plain), random scratch, sprites, the Copper list.
    regions = []
    for n in range(6):
        bitmap = bytearray(r.randbytes(0x8000))
        for _ in range(12):
            start = r.randrange(0x8000)
            end = min(0x8000, start + r.randrange(40, 2000))
            bitmap[start:end] = bytes(end - start)
        regions.append((plane(n), bytes(bitmap)))
    regions.append((SCRATCH, r.randbytes(SCRATCH_END - SCRATCH)))
    sprites = bytearray(8 * 0x200)
    live = [n for n in range(8) if r.random() < 0.5]
    for n in live:
        vstart = r.randrange(0x30, 0xF0)
        height = r.randrange(4, 40)
        hstart = r.randrange(0x40, 0xD8)
        vstop = vstart + height
        ctl = (vstop & 0xFF) << 8 | (0x80 if n % 2 and r.random() < 0.3 else 0) | (vstart >> 8 & 1) << 2 | (vstop >> 8 & 1) << 1 | (hstart & 1)
        words = [(vstart & 0xFF) << 8 | hstart >> 1 & 0xFF, ctl] + [r.randrange(0x10000) for _ in range(2 * height)] + [0, 0]
        sprites[n * 0x200:n * 0x200 + 2 * len(words)] = struct.pack(f'>{len(words)}H', *words)
    regions.append((SPRITES, bytes(sprites)))
    regions.append((NULL_SPRITE, bytes(4)))

    copper = []
    colour_words = []                               # chip addresses of the Copper's colour values, rewritten while it runs
    line = 0x20
    safe = [COLOR + 2 * n for n in range(32)] + [BPLCON1] * 6 + [BPLCON2, BPL1MOD, BPL2MOD] + [BPLPT + 2 + 4 * n for n in range(planes)]
    while line < 0xF0:
        line += r.randrange(1, 24)
        if line >= 0xF0:
            break
        copper += [(line << 8 | (r.randrange(0x20, 0xE0) & 0xFE) | 1), 0xFFFE]
        for _ in range(r.randrange(1, 5)):
            register = r.choice(safe)
            if BPLPT <= register < BPLPT + 0x20:
                value = (plane((register - BPLPT) // 4) + r.randrange(0, 0x6000)) & 0xFFFE
            elif register == BPLCON1:
                value = r.randrange(0x100)
            elif register == BPLCON2:
                value = r.randrange(0x80)
            elif register in (BPL1MOD, BPL2MOD):
                value = modulo() & 0xFFFF
            else:
                value = r.randrange(0x1000)
                colour_words.append(COPPER + 2 * (len(copper) + 1))
            copper += [register, value]
    copper += [0xFFFF, 0xFFFE]
    regions.append((COPPER, struct.pack(f'>{len(copper)}H', *copper)))

    a = Assembler(PROGRAM)
    custom = lambda register: 0xDFF000 + register
    a.move_w_imm_abs(0x7FFF, custom(DMACON))
    for register, value in ((BPLCON0, bplcon0), (BPLCON1, r.randrange(0x100)), (BPLCON2, r.randrange(0x80)), (BPL1MOD, modulo()), (BPL2MOD, modulo()),
                            (DIWSTRT, diwstrt), (DIWSTOP, diwstop), (DDFSTRT, ddf[0]), (DDFSTOP, ddf[1]), (CLXCON, r.randrange(0x10000))):
        a.move_w_imm_abs(value, custom(register))
    for n in range(6):
        a.move_l_imm_abs(plane(n), custom(BPLPT + 4 * n))
    for n in range(8):
        a.move_l_imm_abs(SPRITES + n * 0x200 if n in live else NULL_SPRITE, custom(SPRPT + 4 * n))
    for n, colour in enumerate(colours):
        a.move_w_imm_abs(colour, custom(COLOR + 2 * n))
    a.move_l_imm_abs(COPPER, custom(COP1LC))
    a.move_w_imm_abs(0, custom(COPJMP1))
    blitter_on = r.random() < 0.8
    a.move_w_imm_abs(0x8000 | 0x0200 | 0x0100 | 0x0080 | 0x0020 | (0x0040 if blitter_on else 0), custom(DMACON))
    # Stage 7's barriers: about half the scenarios run with interrupts on (VERTB, the Blitter's end, the CIAs), and CIA-B's TOD alarm
    # set a few lines ahead, so that an interrupt lands inside long bus accesses and on the TOD pulse. The handler clears every source.
    interrupts = r.random() < 0.5
    if interrupts:
        handler = Assembler(HANDLER)
        handler.move_w_imm_abs(0x7FFF, custom(INTREQ))
        handler.w(0x4A39)                                    # tst.b CIA-A ICR
        handler.l(CIAA_ICR)
        handler.w(0x4A39)                                    # tst.b CIA-B ICR
        handler.l(CIAB_ICR)
        handler.w(0x4E73)                                    # rte
        regions.append((HANDLER, handler.data()))
        regions.append((0x64, struct.pack('>7I', *[HANDLER] * 7)))
        for value, address in ((0x00, CIAB_CRB), (0x00, CIAB_TODHI), (0x00, CIAB_TODMID), (0x00, CIAB_TODLO), (0x80, CIAB_CRB),
                               (0x00, CIAB_TODHI), (0x00, CIAB_TODMID), (r.randrange(8, 200), CIAB_TODLO), (0x00, CIAB_CRB), (0x84, CIAB_ICR)):
            a.w(0x13FC, value)
            a.l(address)
        a.move_w_imm_abs(0xC000 | 0x2000 | 0x0040 | 0x0020 | 0x0008, custom(INTENA))
        a.w(0x46FC, 0x2000)                                  # move.w #$2000,sr

    body = a.here
    reads = 0
    fault_address = UNTOUCHED     # a flipped bit there stays: nothing of the program, the Copper or the Blitter writes it
    for _ in range(actions):
        kind = r.random()
        d = reads % 6
        if kind < 0.28:
            register = r.choice([BPLCON1, BPLCON1, BPLCON2, BPL1MOD, BPL2MOD, COLOR + 2 * r.randrange(32), DDFSTRT, DDFSTOP, DIWSTRT, DIWSTOP, BPLCON0, CLXCON, DMACON])
            if register == BPLCON0:
                value = bplcon0 ^ r.choice((0x0400 if planes >= 2 else 0, 0x8000 if planes <= 4 else 0, 0x1000 if planes in (2, 4) else 0, 0))
            elif register == DMACON:
                bit = r.choice((0x0100, 0x0020, 0x0080))
                a.move_w_imm_abs(bit, custom(DMACON))            # off for a moment, then on again
                a.moveq(r.randrange(1, 40), 7)
                loop = a.here
                a.dbra(7, loop)
                value = 0x8000 | bit
            elif register in (DDFSTRT, DDFSTOP):
                value = (ddf[0] if register == DDFSTRT else ddf[1]) + r.choice((0, 0, 4, -4, 8, -8))
                if r.random() < 0.25:                          # anywhere: before the hardware start, past the hardware stop, odd
                    value = r.randrange(0x08, 0xF0) & (0xFF if r.random() < 0.2 else 0xFE)
            elif register in (DIWSTRT, DIWSTOP):
                value = (diwstrt if register == DIWSTRT else diwstop) + r.choice((0, 0, 1, -1, 0x0100, -0x0100))
            elif register in (BPL1MOD, BPL2MOD):
                value = modulo()
            elif register == BPLCON1:
                value = r.randrange(0x100)
            elif register == BPLCON2:
                value = r.randrange(0x80)
            elif register == CLXCON:
                value = r.randrange(0x10000)
            else:
                value = r.randrange(0x1000)
            a.move_w_imm_abs(value & 0xFFFF, custom(register))
        elif kind < 0.48:
            target = plane(r.randrange(planes)) + (r.randrange(0, 0x7F00) & ~1)
            if r.random() < 0.5:
                a.move_w_imm_abs(r.randrange(0x10000), target)
            else:
                a.move_l_imm_abs(r.getrandbits(32), target)
        elif kind < 0.63:
            a.move_w_abs_d(custom(r.choice((VHPOSR, VHPOSR, VPOSR, CLXDAT, DMACONR, JOY0DAT))), d)
            reads += 1
        elif kind < 0.71:
            a.move_w_abs_d(r.choice((plane(r.randrange(6)), SCRATCH)) + (r.randrange(0, 0x7F00) & ~1), d)
            reads += 1
        elif kind < 0.74:
            a.move_w_abs_d(UNMAPPED + (r.randrange(0, 0x1000) & ~1), d)
            reads += 1
        elif kind < 0.76:
            address = SLOW + (r.randrange(0, 0x10000) & ~1)
            a.move_w_imm_abs(r.randrange(0x10000), address)
            a.move_w_abs_d(address, d)
            reads += 1
        elif kind < 0.84 and blitter_on:
            a.wait_blitter()
            into_display = r.random() < 0.3
            destination = (plane(r.randrange(planes)) if into_display else SCRATCH + 0x10000) + (r.randrange(0, 0x4000) & ~1)
            minterm = r.choice((0xF0, 0xCC, 0xCA, 0xAA, 0x0F, 0xFA))
            use = r.choice((0x9, 0xD, 0xF, 0x5, 0xB))
            a.move_w_imm_abs(use << 8 | minterm | r.randrange(16) << 12, custom(BLTCON0))
            a.move_w_imm_abs(r.choice((0, 0, 0x0002 if r.random() < 0.2 else 0)) | r.randrange(16) << 12, custom(BLTCON1))
            a.move_w_imm_abs(0xFFFF, custom(BLTAFWM))
            a.move_w_imm_abs(r.randrange(0x10000), custom(BLTALWM))
            for register in (BLTAPT, BLTBPT, BLTCPT):
                a.move_l_imm_abs(SCRATCH + (r.randrange(0, 0x8000) & ~1), custom(register))
            a.move_l_imm_abs(destination, custom(BLTDPT))
            for register in (BLTAMOD, BLTBMOD, BLTCMOD, BLTDMOD):
                a.move_w_imm_abs(r.choice((0, 2, 8, 38)), custom(register))
            a.move_w_imm_abs(r.randrange(2, 24) << 6 | r.randrange(1, 12), custom(BLTSIZE))
            for _ in range(r.choice((0, 0, 1, 2, 3))):          # the CPU racing the blit it just started
                if r.random() < 0.5:
                    a.move_w_abs_d(destination + (r.randrange(0, 0x200) & ~1), d)
                    reads += 1
                else:
                    a.move_w_imm_abs(r.randrange(0x10000), destination + (r.randrange(0, 0x200) & ~1))
        elif kind < 0.865:
            # A read of a write-only register: the chip writes the last value of the data bus into it (often a bitplane word).
            a.move_w_abs_d(custom(r.choice((BPL1MOD, BPL2MOD, BPLCON1, COLOR + 2 * r.randrange(32)))), d)
            reads += 1
        elif kind < 0.88:
            a.move_w_imm_abs(r.randrange(0x10000), custom(BPL1DAT))
        elif kind < 0.895:
            n = r.randrange(planes)
            a.move_l_imm_abs(plane(n) + (r.randrange(0, 0x6000) & ~1), custom(BPLPT + 4 * n))
        elif kind < 0.915:
            a.moveq(r.randrange(1, 120), 7)
            loop = a.here
            a.dbra(7, loop)
        elif kind < 0.93 and live:
            n = r.choice(live)                                     # a sprite's data rewritten under its fetch
            a.move_w_imm_abs(r.randrange(0x10000), SPRITES + n * 0x200 + 4 + (r.randrange(0, 0x40) & ~1))
        elif kind < 0.945 and colour_words:
            a.move_w_imm_abs(r.randrange(0x1000), r.choice(colour_words))   # the Copper's list rewritten while it runs
        elif kind < 0.96:
            # The disk controller, idle or not (stage 7 holds its idle events back): DSKBYTR read, DSKSYNC (zero now and then), the
            # drive select and motor lines of CIA-B, DSKLEN with DMA off.
            what = r.random()
            if what < 0.4:
                a.move_w_abs_d(custom(DSKBYTR), d)
                reads += 1
            elif what < 0.6:
                a.move_w_imm_abs(r.choice((0x4489, 0x4489, 0x4489, r.randrange(1, 0x10000), 0)), custom(DSKSYNC))
            elif what < 0.85:
                a.w(0x13FC, r.choice((0xFF, 0xFF, 0xF7, 0x77, 0x7F)))      # move.b #v,CIA-B PRB: none, df0, df0 with motor
                a.l(CIAB_PRB)
            else:
                a.move_w_imm_abs(0, custom(DSKLEN))
        else:
            a.wait_line(r.randrange(0x10, 0xF8))
    a.bra_w(body)
    program = a.data()
    if PROGRAM + len(program) > COPPER:
        raise ValueError('The scenario program is too long.')
    regions.insert(0, (PROGRAM, program))
    summary = {'seed': seed, 'ntsc': ntsc, 'hires': hires, 'planes': planes, 'dual': dual, 'ham': ham, 'sprites': len(live), 'blitter': blitter_on, 'interrupts': interrupts,
               'ddf': [hex(ddf[0]), hex(ddf[1])], 'program_bytes': len(program), 'copper_words': len(copper)}
    return Scenario(seed, ntsc, frames, regions, fault_address, summary)


# Records: "RRDR", version, frames, rows; per frame 12 u64 (instructions so far, Agnus, Denise, Paula, CIA-A, CIA-B, CPU, chip RAM,
# slow RAM, sound, CLXDAT, Agnus's clock) and one u64 per texture row; then the instruction count and one u64 per instruction.
FRAME_FIELDS = ('instructions', 'agnus', 'denise', 'paula', 'cia_a', 'cia_b', 'cpu', 'chip', 'slow', 'sound', 'clxdat', 'clock')
# Version 2 adds a 13th: every line's bus owners, hashed (stage 7's shadow builds; 0 in a build without the model).
FRAME_FIELDS_2 = FRAME_FIELDS + ('owners',)


def read_record(path: Path) -> dict:
    data = path.read_bytes()
    if data[:4] != b'RRDR':
        raise ValueError(f'{path} is not a record.')
    version, frames, rows = struct.unpack_from('<3I', data, 4)
    if version not in (1, 2):
        raise ValueError(f'{path}: record version {version}.')
    names = FRAME_FIELDS if version == 1 else FRAME_FIELDS_2
    at = 16
    out = []
    for _ in range(frames):
        fields = dict(zip(names, struct.unpack_from(f'<{len(names)}Q', data, at)))
        at += 8 * len(names)
        fields['rows'] = list(struct.unpack_from(f'<{rows}Q', data, at))
        at += 8 * rows
        out.append(fields)
    (count,) = struct.unpack_from('<Q', data, at)
    steps = list(struct.unpack_from(f'<{count}Q', data, at + 8))
    return {'frames': out, 'steps': steps}


def compare(a: dict, b: dict) -> dict | None:
    """The first difference between two records, or None: the instruction first, then the frame's parts and rows."""
    for index, (x, y) in enumerate(zip(a['steps'], b['steps'])):
        if x != y:
            frame = next((n for n, f in enumerate(a['frames']) if f['instructions'] > index), len(a['frames']))
            return {'at': 'instruction', 'index': index, 'frame': frame}
    if len(a['steps']) != len(b['steps']):
        return {'at': 'instruction', 'index': min(len(a['steps']), len(b['steps'])), 'frame': None}
    for n, (x, y) in enumerate(zip(a['frames'], b['frames'])):
        # The owners are compared only when both records have them (a build before stage 7 writes version 1).
        parts = [name for name in FRAME_FIELDS_2 if name in x and name in y and x[name] != y[name]]
        rows = [i for i, (p, q) in enumerate(zip(x['rows'], y['rows'])) if p != q]
        if parts or rows:
            return {'at': 'frame', 'frame': n, 'parts': parts, 'rows': rows[:20], 'row_count': len(rows)}
    if len(a['frames']) != len(b['frames']):
        return {'at': 'frame', 'frame': min(len(a['frames']), len(b['frames'])), 'parts': ['frame count'], 'rows': [], 'row_count': 0}
    return None


def build(work: Path, core: Path) -> Path:
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args
    machine = (ROOT / 'native' / 'amiga_machine').as_posix()
    source = work / 'cmake'
    source.mkdir(parents=True, exist_ok=True)
    (source / 'CMakeLists.txt').write_text(f"""cmake_minimum_required(VERSION 3.20)
project(RetroAmigaDisplay LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_subdirectory("{core.as_posix()}" vacore)
foreach(RR_TARGET VACore rvlib utlib)
    if(TARGET ${{RR_TARGET}})
        set_property(TARGET ${{RR_TARGET}} PROPERTY INTERFACE_COMPILE_OPTIONS "")
    endif()
endforeach()
# Stage 7's bus model in shadow (amiga_bus.h): compiled into the Core of this program only, never into a game.
target_compile_definitions(VACore PUBLIC RR_AMIGA_SHADOW=1)
target_include_directories(VACore PUBLIC "{machine}")
target_sources(VACore PRIVATE "{machine}/amiga_bus.cpp")
add_executable(amiga_display_checks "{machine}/amiga_display_checks.cpp")
target_link_libraries(amiga_display_checks PRIVATE VACore)
if(WIN32)
    target_link_libraries(amiga_display_checks PRIVATE ws2_32)
endif()
""", encoding='utf-8', newline='\n')
    folder = work / 'build'
    cmake, generator = toolchain()
    run([cmake, '-S', source, '-B', folder, '-G', generator, *cmake_target_args(), '-DCMAKE_BUILD_TYPE=Release'], log=work / 'build.log', cwd=work)
    run([cmake, '--build', folder, '--parallel', build_jobs(), '--target', 'amiga_display_checks'], log=work / 'build.log', timeout=7200, cwd=work)
    return build_executable(folder, 'amiga_display_checks')


def play(program: Path, scenario: Path, record: Path, *extra: str) -> dict:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    result = subprocess.run([str(program), str(scenario), str(record), *extra], capture_output=True, text=True, timeout=1800, creationflags=flags)
    if result.returncode:
        raise RuntimeError(f'{scenario.name}: exit {result.returncode}: {result.stderr[-1500:]}')
    return json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))


# Faults planted in stage 7's bus model (amiga_bus.cpp, `--shadow-fault N`): each must make the model disagree with vAmiga somewhere.
SHADOW_FAULTS = {1: 'refresh at $E2 on a long line', 2: 'audio slots two clocks late', 3: 'bitplane slots given to the wrong plane',
                 4: 'a change of plan inside the line ignored', 5: 'sprite slots outside the sprite area', 6: 'a conditional slot taken for free',
                 7: 'a static wait one clock long', 9: 'our own bitplane plan one fetch unit short'}


def add_bus(total: dict, bus: dict) -> None:
    """Sums the model's figures of several runs (numbers, lists and dicts of them)."""
    for key, value in bus.items():
        if key in ('first', 'fault'):
            continue
        if isinstance(value, dict):
            add_bus(total.setdefault(key, {}), value)
        elif isinstance(value, list):
            have = total.setdefault(key, [0] * len(value))
            total[key] = [x + y for x, y in zip(have, value)]
        else:
            total[key] = total.get(key, 0) + value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--scenarios', type=int, default=SCENARIOS)
    parser.add_argument('--frames', type=int, default=FRAMES)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--workspace', type=Path, default=ROOT, help='where .deps and .build live')
    parser.add_argument('--against', type=Path, help="a checks program built before a change (side A): each scenario's record from it must equal this build's")
    arguments = parser.parse_args()
    from retrorecomp import amiga_vamiga, paths
    paths.ROOT = amiga_vamiga.ROOT = arguments.workspace.resolve()
    work = paths.ROOT / '.build' / 'amiga-display'
    core = amiga_vamiga.adapt(amiga_vamiga.source(), work / 'vamiga')
    program = build(work, core)
    runs = work / 'runs'
    runs.mkdir(parents=True, exist_ok=True)
    failures, seen, placed, instructions = [], 0, 0, 0
    lines = [0, 0, 0]
    quiet = [0, 0]
    bus_total: dict = {}
    scenario_files = []
    disk, disk_controls, disk_seen = [0, 0, 0, 0], 0, 0
    for n in range(arguments.scenarios):
        seed = arguments.seed * 1000 + n
        scenario = generate(seed, arguments.frames)
        path = runs / f'scenario-{seed}.bin'
        scenario.write(path)
        first = play(program, path, runs / f'{seed}-a.rec')
        second = play(arguments.against or program, path, runs / f'{seed}-b.rec', *(() if arguments.against else ('--per-slot',)))
        scenario_files.append(path)
        # Stage 7's model in shadow: its table and its predicted waits equal vAmiga's on both runs.
        for run_name, result in (('batched', first), ('per_slot', second)):
            if 'bus_mismatches' in result and result['bus_mismatches']:
                failures.append({'seed': seed, 'bus': run_name, 'mismatches': result['bus_mismatches'], 'first': result['bus'].get('first', [])[:6]})
        if 'bus' in first:
            add_bus(bus_total, first['bus'])
        lines = [n + m for n, m in zip(lines, first.get('lines', (0, 0, 0)))]
        quiet = [n + m for n, m in zip(quiet, first.get('quiet', (0, 0)))]
        a, b = read_record(runs / f'{seed}-a.rec'), read_record(runs / f'{seed}-b.rec')
        instructions += first['instructions']
        if compare(a, b) is not None:
            failures.append({'seed': seed, 'replay': compare(a, b)})
            continue
        # Positive controls: a bit of displayed chip RAM, and one colour clock, from the middle of the second frame.
        middle = a['frames'][0]['instructions'] + (a['frames'][1]['instructions'] - a['frames'][0]['instructions']) // 2
        for kind in ('ram', 'clock'):
            play(program, path, runs / f'{seed}-{kind}.rec', '--fault', kind, str(middle))
            found = compare(a, read_record(runs / f'{seed}-{kind}.rec'))
            seen += found is not None
            placed += found is not None and (found['at'] == 'frame' or found['index'] >= middle)
            if found is None:
                failures.append({'seed': seed, 'fault': kind, 'missed': True})
        # Stage 7's idle-disk catch-up: one held-back event lost must change the records (where events were held back at all).
        if first.get('disk', [0])[0]:
            disk_controls += 1
            play(program, path, runs / f'{seed}-disk.rec', '--disk-fault', '1')
            if compare(a, read_record(runs / f'{seed}-disk.rec')) is None:
                failures.append({'seed': seed, 'disk_fault': 1, 'missed': True})
            else:
                disk_seen += 1
        disk = [n + m for n, m in zip(disk, first.get('disk', (0, 0, 0, 0)))]
        print(json.dumps({**scenario.summary, 'instructions': first['instructions'], 'lines': first.get('lines'), 'quiet': first.get('quiet'), 'disk': first.get('disk')}), flush=True)
    controls = 2 * (arguments.scenarios - sum(1 for f in failures if 'replay' in f))
    # Planted faults of the model: each must be seen on at least one scenario.
    model_faults = {}
    if bus_total:
        for kind, what in SHADOW_FAULTS.items():
            model_faults[kind] = 0
            for path in scenario_files:
                found = play(program, path, runs / f'model-fault-{kind}.rec', '--shadow-fault', str(kind))
                if found.get('bus_mismatches'):
                    model_faults[kind] += 1
            if not model_faults[kind]:
                failures.append({'model_fault': kind, 'what': what, 'missed': True})
    print(json.dumps({'scenarios': arguments.scenarios, 'frames': arguments.frames, 'instructions': instructions,
                      'lines_batched_events_left': lines, 'lines_one_pass_general': quiet, 'replays_differ': sum(1 for f in failures if 'replay' in f),
                      'faults_seen': seen, 'faults_placed': placed, 'faults_injected': controls, 'model_faults_seen_in_scenarios': model_faults,
                      'disk_batches_at_event_at_barrier_events': disk, 'disk_faults_seen': [disk_seen, disk_controls],
                      'bus': bus_total, 'failures': failures[:10]}))
    if failures or seen != controls or placed != controls:
        print('Display self-test FAILED.')
        return 1
    other = (f'every record equal to the one of {arguments.against.name} (built before the change)' if arguments.against else
             "every record equal to the one of the same build with every line on vAmiga's events and line pass")
    print(f'Display self-test passed: {arguments.scenarios} scenarios of {arguments.frames} frames, {instructions} instructions recorded, '
          f'{lines[0]} lines batched ({lines[2]} of them given back midway) and {lines[1]} on events, {quiet[0]} visible lines passed in one loop and {quiet[1]} on vAmiga\'s pass, {other}, '
          f'{seen} of {controls} injected faults seen at or after their instruction. This shows that two runs agree, not that anything matches the hardware.')
    print(f"Stage 7's idle-disk catch-up: {disk[3]} disk events held back in {disk[0]} batches ({disk[1]} run at their event, {disk[2]} at a barrier), "
          f"every record equal to the run with every disk event on vAmiga's scheduler; one held-back event lost seen in {disk_seen} of {disk_controls} scenarios.")
    if bus_total:
        table = bus_total.get('table', {})
        print(f"Stage 7's bus model in shadow: {bus_total.get('lines_compared', 0)} lines compared slot by slot ({table.get('taken', 0)} certain slots), "
              f"0 differences in the table and in {sum(v[0] for k, v in bus_total.get('waits', {}).items() if k in ('fast', 'static'))} predicted CPU waits; "
              f"{len(model_faults)} planted faults of the model each seen (in {min(model_faults.values()) if model_faults else 0} to "
              f"{max(model_faults.values()) if model_faults else 0} of {arguments.scenarios} scenarios). Equal to vAmiga, not to the hardware.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
