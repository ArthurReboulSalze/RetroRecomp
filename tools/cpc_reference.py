"""The Amstrad CPC on the reference Z80 interpreter, headless: the board of native/cpc_machine run by programs written here.

    python -B tools/cpc_reference.py [--engine DIR] [--json PATH]

Builds `native/cpc_machine/cpc_reference_main.c` with the corrected reference interpreter (retrorecomp.cpu.prepare_reference with the
CPC's costs and 16-bit ports, the same copy as the counted fallback of its games; its pinned source is never edited) and runs
authored programs as the system ROM (no firmware, no game; the player's own ROMs boot the same way once he gives them):

- timing: JP, LD B,100, DJNZ to itself and HALT take 3 + 2 + 99 x 4 + 3 + 1 microseconds, the CPC's costs;
- interrupts and picture: IM 1, a handler at 0038h counting in RAM, the screen filled through LDIR in mode 1 with its pens
  and border set at port 7Fxxh: six interrupts a frame (300 Hz), the pens and the border on the drawn picture;
- disk: a sector of a disk built here read as AMSDOS reads it, through FB7Eh / FB7Fh (wait for RQM, the execution phase while
  bit 5 is set, then seven result bytes): its 512 bytes in RAM, the result "abnormal, end of cylinder";
- written disk: another sector written as AMSDOS writes one (WRITE DATA, the bytes sent while bit 5 is set), then read back:
  its bytes in RAM, the disk marked written and its digest (disk_fnv) changed.

A development check: nothing here is built into a game. The engine checkout is the main checkout's `.deps/smsggrecomp` (a
worktree passes `--engine`).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WORK = ROOT / '.build' / 'cpc-reference'
CPC_US = 4                                           # T-states a microsecond


class Asm:
    """Just enough Z80 to write the checks: bytes, labels, relative and absolute jumps fixed up at the end."""

    def __init__(self, origin: int = 0):
        self.origin = origin
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, str]] = []

    @property
    def here(self) -> int:
        return self.origin + len(self.code)

    def label(self, name: str):
        self.labels[name] = self.here

    def b(self, *values: int):
        self.code += bytes(values)

    def w(self, value: int):
        self.code += bytes((value & 0xFF, value >> 8))

    def jr(self, opcode: int, target: str):
        self.b(opcode, 0)
        self.fixups.append((len(self.code) - 1, target, 'rel'))

    def jp(self, opcode: int, target: str):
        self.b(opcode, 0, 0)
        self.fixups.append((len(self.code) - 2, target, 'abs'))

    def org(self, address: int):
        self.code += bytes(address - self.here)

    def image(self, size: int) -> bytes:
        for at, target, kind in self.fixups:
            address = self.labels[target]
            if kind == 'rel':
                offset = address - (self.origin + at + 1)
                assert -128 <= offset <= 127, target
                self.code[at] = offset & 0xFF
            else:
                self.code[at:at + 2] = bytes((address & 0xFF, address >> 8))
        assert len(self.code) <= size
        return bytes(self.code) + bytes(size - len(self.code))


def system_rom(lower: bytes) -> bytes:
    """A 32 KiB system ROM: the program as the OS (bank 0), the BASIC half empty (C9h, RET)."""
    return lower.ljust(0x4000, b'\0') + b'\xC9' * 0x4000


def timing_program() -> bytes:
    a = Asm()
    a.jp(0xC3, 'main')
    a.org(0x100)
    a.label('main')
    a.b(0x06, 100)                       # LD B,100
    a.label('loop')
    a.jr(0x10, 'loop')                   # DJNZ loop
    a.b(0x76)                            # HALT
    return system_rom(a.image(0x4000))


def interrupt_program() -> bytes:
    a = Asm()
    a.b(0xF3)                            # DI
    a.jp(0xC3, 'main')
    a.org(0x38)
    a.b(0xE5)                            # PUSH HL
    a.b(0x2A); a.w(0x8000)               # LD HL,(8000h)
    a.b(0x23)                            # INC HL
    a.b(0x22); a.w(0x8000)               # LD (8000h),HL
    a.b(0xE1, 0xFB, 0xC9)                # POP HL, EI, RET
    a.org(0x100)
    a.label('main')
    a.b(0x31); a.w(0xBFF0)               # LD SP,BFF0h
    a.b(0xED, 0x56)                      # IM 1
    a.b(0x01); a.w(0x7F89)               # LD BC,7F89h: mode 1, upper ROM off
    a.b(0xED, 0x49)                      # OUT (C),C
    for value in (0x00, 0x54, 0x01, 0x4B, 0x10, 0x44):   # pen 0 black, pen 1 bright white, border blue
        a.b(0x0E, value, 0xED, 0x49)     # LD C,n; OUT (C),C
    a.b(0x21); a.w(0xC000)               # LD HL,C000h
    a.b(0x11); a.w(0xC001)               # LD DE,C001h
    a.b(0x01); a.w(0x3FFF)               # LD BC,3FFFh
    a.b(0x36, 0x80)                      # LD (HL),80h: mode 1, each byte's first pixel pen 1
    a.b(0xED, 0xB0)                      # LDIR
    a.b(0x21); a.w(0)                    # LD HL,0
    a.b(0x22); a.w(0x8000)               # LD (8000h),HL
    a.b(0xFB)                            # EI
    a.label('idle')
    a.b(0x76)                            # HALT
    a.jr(0x18, 'idle')                   # JR idle
    return system_rom(a.image(0x4000))


# The routine the RAM program builds: LD A,(8002h); ADD A,3; LD (8002h),A; RET. Its bytes are written one by one from immediate
# operands, so they appear nowhere in the ROM as a sequence: only learning makes it native.
RAM_ROUTINE = (0x3A, 0x02, 0x80, 0xC6, 0x03, 0x32, 0x02, 0x80, 0xC9)


def ram_program() -> bytes:
    """A routine built byte by byte in RAM at 4000h and called 200 times: code the interpreter runs until it is learned."""
    a = Asm()
    a.b(0xF3)
    a.jp(0xC3, 'main')
    a.org(0x100)
    a.label('main')
    a.b(0x31); a.w(0xBFF0)
    a.b(0x21); a.w(0x4000)               # LD HL,4000h
    for value in RAM_ROUTINE:
        a.b(0x36, value, 0x23)           # LD (HL),n; INC HL
    a.b(0x06, 200)                       # LD B,200
    a.label('again')
    a.b(0xC5)                            # PUSH BC
    a.b(0xCD); a.w(0x4000)               # CALL 4000h
    a.b(0xC1)                            # POP BC
    a.jr(0x10, 'again')                  # DJNZ again
    a.b(0x76)                            # HALT
    return system_rom(a.image(0x4000))


READ_COMMAND = (0x46, 0x00, 0, 0, 0xC1, 2, 0xC1, 0x2A, 0xFF)   # READ DATA, drive A, C0 H0 R C1h N2, EOT C1h


def disk_program() -> bytes:
    a = Asm()
    a.b(0xF3)
    a.jp(0xC3, 'main')
    a.org(0x100)
    a.label('send')                      # A to the controller once it asks (RQM)
    a.b(0x01); a.w(0xFB7E)               # LD BC,FB7Eh
    a.b(0xF5)                            # PUSH AF
    a.label('send_wait')
    a.b(0xED, 0x78, 0x87)                # IN A,(C); ADD A,A (RQM to carry)
    a.jr(0x30, 'send_wait')              # JR NC
    a.b(0xF1, 0x0C, 0xED, 0x79, 0xC9)    # POP AF; INC C; OUT (C),A; RET
    a.label('main')
    a.b(0x31); a.w(0xBFF0)
    a.b(0x01); a.w(0xFA7E)               # the motor on
    a.b(0x3E, 0x01, 0xED, 0x79)
    a.b(0x21); a.w(0x0200)               # LD HL,command
    a.b(0x16, len(READ_COMMAND))         # LD D,9
    a.label('command')
    a.b(0x7E, 0x23)                      # LD A,(HL); INC HL
    a.jp(0xCD, 'send')                   # CALL send
    a.b(0x15)                            # DEC D
    a.jr(0x20, 'command')
    a.b(0x21); a.w(0x4000)               # LD HL,4000h: the sector
    a.b(0x01); a.w(0xFB7E)
    a.label('read')
    a.b(0xED, 0x78, 0x87)                # IN A,(C); ADD A,A: RQM
    a.jr(0x30, 'read')
    a.b(0x87, 0x87)                      # ADD A,A twice: EXM (bit 5) to carry
    a.jr(0x30, 'result')
    a.b(0x0C, 0xED, 0x78, 0x0D, 0x77, 0x23)   # INC C; IN A,(C); DEC C; LD (HL),A; INC HL
    a.jr(0x18, 'read')
    a.label('result')
    a.b(0x21); a.w(0x4200)               # LD HL,4200h: the result bytes
    a.b(0x16, 7)
    a.label('status')
    a.b(0xED, 0x78, 0x87)
    a.jr(0x30, 'status')
    a.b(0x0C, 0xED, 0x78, 0x0D, 0x77, 0x23, 0x15)   # INC C; IN A,(C); DEC C; LD (HL),A; INC HL; DEC D
    a.jr(0x20, 'status')
    a.b(0x76)                            # HALT
    a.org(0x200)
    a.b(*READ_COMMAND)
    return system_rom(a.image(0x4000))


WRITE_COMMAND = (0x45, 0x00, 0, 0, 0xC2, 2, 0xC2, 0x2A, 0xFF)  # WRITE DATA, drive A, C0 H0 R C2h N2, EOT C2h
READ_BACK = (0x46, 0x00, 0, 0, 0xC2, 2, 0xC2, 0x2A, 0xFF)      # READ DATA of the same sector


def written_byte(n: int) -> int:
    return (n * 5 + 11) & 0xFF


def write_program() -> bytes:
    """WRITE DATA of sector C2h as AMSDOS writes one (written_byte(0..511), from the ROM at 0400h), its result bytes at 4200h; then
    READ DATA of the same sector into 4400h, its result at 4210h: the bytes come back from the disk in memory, which the run's
    disk_fnv shows changed."""
    a = Asm()
    a.b(0xF3)
    a.jp(0xC3, 'main')
    a.org(0x100)
    a.label('send')                      # A to the controller once it asks (RQM)
    a.b(0x01); a.w(0xFB7E)               # LD BC,FB7Eh
    a.b(0xF5)                            # PUSH AF
    a.label('send_wait')
    a.b(0xED, 0x78, 0x87)                # IN A,(C); ADD A,A (RQM to carry)
    a.jr(0x30, 'send_wait')              # JR NC
    a.b(0xF1, 0x0C, 0xED, 0x79, 0xC9)    # POP AF; INC C; OUT (C),A; RET
    a.label('commands')                  # the nine command bytes at HL
    a.b(0x16, 9)                         # LD D,9
    a.label('command')
    a.b(0x7E, 0x23)                      # LD A,(HL); INC HL
    a.jp(0xCD, 'send')                   # CALL send
    a.b(0x15)                            # DEC D
    a.jr(0x20, 'command')
    a.b(0xC9)                            # RET
    a.label('results')                   # the seven result bytes to HL
    a.b(0x01); a.w(0xFB7E)
    a.b(0x16, 7)
    a.label('status')
    a.b(0xED, 0x78, 0x87)
    a.jr(0x30, 'status')
    a.b(0x0C, 0xED, 0x78, 0x0D, 0x77, 0x23, 0x15)   # INC C; IN A,(C); DEC C; LD (HL),A; INC HL; DEC D
    a.jr(0x20, 'status')
    a.b(0xC9)
    a.label('main')
    a.b(0x31); a.w(0xBFF0)
    a.b(0x01); a.w(0xFA7E)               # the motor on
    a.b(0x3E, 0x01, 0xED, 0x79)
    a.b(0x21); a.w(0x0200)               # WRITE DATA
    a.jp(0xCD, 'commands')
    a.b(0x21); a.w(0x0400)               # LD HL,0400h: the bytes to write
    a.b(0x01); a.w(0xFB7E)
    a.label('write')
    a.b(0xED, 0x78, 0x87)                # IN A,(C); ADD A,A: RQM
    a.jr(0x30, 'write')
    a.b(0x87, 0x87)                      # ADD A,A twice: EXM (bit 5) to carry
    a.jr(0x30, 'written')
    a.b(0x7E, 0x23, 0x0C, 0xED, 0x79, 0x0D)   # LD A,(HL); INC HL; INC C; OUT (C),A; DEC C
    a.jr(0x18, 'write')
    a.label('written')
    a.b(0x21); a.w(0x4200)
    a.jp(0xCD, 'results')
    a.b(0x21); a.w(0x0209)               # READ DATA of the same sector
    a.jp(0xCD, 'commands')
    a.b(0x21); a.w(0x4400)
    a.b(0x01); a.w(0xFB7E)
    a.label('read')
    a.b(0xED, 0x78, 0x87)
    a.jr(0x30, 'read')
    a.b(0x87, 0x87)
    a.jr(0x30, 'read_done')
    a.b(0x0C, 0xED, 0x78, 0x0D, 0x77, 0x23)   # INC C; IN A,(C); DEC C; LD (HL),A; INC HL
    a.jr(0x18, 'read')
    a.label('read_done')
    a.b(0x21); a.w(0x4210)
    a.jp(0xCD, 'results')
    a.b(0x76)                            # HALT
    a.org(0x200)
    a.b(*WRITE_COMMAND, *READ_BACK)
    a.org(0x400)
    a.b(*(written_byte(n) for n in range(512)))
    return system_rom(a.image(0x4000))


def sector_byte(n: int) -> int:
    return (n * 7 + 3) & 0xFF


def disk_image() -> bytes:
    """One standard AMSDOS data track: sector C1h holds sector_byte(0..511), the others zero."""
    disk = bytearray(256)
    disk[:34] = b'MV - CPCEMU Disk-File\r\nDisk-Info\r\n'
    disk[0x30], disk[0x31], disk[0x32], disk[0x33] = 1, 1, 0x00, 0x13
    track = bytearray(256)
    track[:12] = b'Track-Info\r\n'
    track[0x14], track[0x15] = 2, 9
    for s in range(9):
        track[0x18 + 8 * s:0x20 + 8 * s] = bytes((0, 0, 0xC1 + s, 2, 0, 0, 0, 0))
    data = bytes(sector_byte(i) for i in range(512)) + bytes(8 * 512)
    return bytes(disk + track + data)


def build(engine: Path) -> Path:
    from retrorecomp import cpc_build, z80_chain_build
    from retrorecomp.cpu import prepare_reference
    from retrorecomp.platforms import build_executable, cmake_target_args
    from retrorecomp.systems.amstrad_cpc import CPC_MACHINE
    from retrorecomp import toolchain
    WORK.mkdir(parents=True, exist_ok=True)
    prepare_reference(WORK, engine, m1_counter=CPC_MACHINE.counts_m1, costs=CPC_MACHINE.costs, port16=True)
    z80_chain_build.instrument_reference(WORK / 'runtime_reference.c', cpc_build.ACCEPT, CPC_MACHINE)
    cpc_build.stage_sources(WORK)
    shutil.copyfile(ROOT / 'native' / 'cpc_machine' / 'cpc_reference_main.c', WORK / 'cpc_reference_main.c')
    sources = ' '.join(('cpc_reference_main.c', 'runtime_reference.c', *cpc_build.MACHINE_SOURCES, *cpc_build.DISK_SOURCES,
                        *cpc_build.SHARED_SOURCES))
    (WORK / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.21)
project(RetroCpcReference C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(cpc_reference {sources})
target_include_directories(cpc_reference PRIVATE "${{CMAKE_CURRENT_SOURCE_DIR}}")
''', encoding='utf-8', newline='\n')
    selection = toolchain.select()
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    for step in ([str(selection.cmake), '-S', str(WORK), '-B', str(WORK / 'build'), '-G', selection.generator,
                  '-DCMAKE_BUILD_TYPE=Release', *cmake_target_args()],
                 [str(selection.cmake), '--build', str(WORK / 'build'), '--config', 'Release']):
        result = subprocess.run(step, capture_output=True, text=True, creationflags=flags)
        if result.returncode:
            raise RuntimeError(result.stdout[-4000:] + result.stderr[-2000:])
    return build_executable(WORK / 'build', 'cpc_reference')


def run(exe: Path, rom: bytes, *args: str) -> dict:
    image = WORK / 'program.rom'
    image.write_bytes(rom)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    out = subprocess.run([str(exe), '--system', str(image), *args], capture_output=True, text=True, timeout=300,
                         creationflags=flags)
    if out.returncode:
        raise RuntimeError(out.stderr)
    return json.loads(out.stdout)


def checks(exe: Path) -> dict:
    results: dict[str, bool] = {}
    timing = run(exe, timing_program(), '--frames', '5', '--until-halt')
    results['timing: JP, LD B, 99 DJNZ taken and one not, HALT, in the CPC microseconds'] = (
        timing['cycles'] == (3 + 2 + 99 * 4 + 3 + 1) * CPC_US and timing['halted'] == 1 and (timing['bc'] >> 8) == 0)
    picture = WORK / 'picture.raw'
    irq = run(exe, interrupt_program(), '--frames', '100', '--picture', str(picture), '--watch', '8000', '--watch', '8001')
    counted = irq['watch']['8000'] | irq['watch']['8001'] << 8
    later = run(exe, interrupt_program(), '--frames', '200', '--watch', '8000', '--watch', '8001')
    more = (later['watch']['8000'] | later['watch']['8001'] << 8) - counted
    # The screen's LDIR runs with interrupts off (about five frames: one request waits, the others are not raised twice), so the
    # rate is measured between two runs, once the handler runs.
    results['300 Hz: the handler at 0038h counts six interrupts a frame'] = more == 600 and irq['interrupts'] == counted
    results['the Gate Array took mode 1 and turned the upper ROM off'] = irq['mode'] == 1 and irq['rom_config'] == 0x08
    pixels = picture.read_bytes()
    def pixel(x: int, y: int) -> int:
        at = 4 * (y * 768 + x)
        return int.from_bytes(pixels[at:at + 3], 'little')
    results['the picture: blue border, the screen bytes in pen 1 (white) then pen 0'] = (
        pixel(0, 0) == 0x000080 and pixel(64, 36) == 0xFFFFFF and pixel(66, 36) == 0x000000)
    disk = WORK / 'disk.dsk'
    disk.write_bytes(disk_image())
    sector = run(exe, disk_program(), '--disk', str(disk), '--frames', '5', '--until-halt',
                 *[part for n in (0, 1, 255, 511) for part in ('--watch', f'{0x4000 + n:04X}')],
                 *[part for n in range(7) for part in ('--watch', f'{0x4200 + n:04X}')])
    watched = sector['watch']
    results['a sector read as AMSDOS reads it: its bytes in RAM'] = all(
        watched[f'{0x4000 + n:04X}'] == sector_byte(n) for n in (0, 1, 255, 511))
    results['and the result: abnormal, end of cylinder, next ID C1 R1'] = (
        watched['4200'] == 0x40 and watched['4201'] == 0x80 and watched['4203'] == 1 and watched['4205'] == 1
        and sector['fdc_commands'] == 1)
    disk.write_bytes(disk_image())
    written = run(exe, write_program(), '--disk', str(disk), '--frames', '5', '--until-halt',
                  *[part for n in (0, 1, 255, 511) for part in ('--watch', f'{0x4400 + n:04X}')],
                  *[part for n in (0, 1, 16, 17) for part in ('--watch', f'{0x4200 + n:04X}')])
    watched = written['watch']
    results['a sector written as AMSDOS writes it, then read back: its bytes in RAM, the disk changed'] = (
        all(watched[f'{0x4400 + n:04X}'] == written_byte(n) for n in (0, 1, 255, 511)) and written['disk_written'] == 1
        and written['fdc_commands'] == 2 and written['disk_fnv'] != sector['disk_fnv'])
    results['both results: abnormal, end of cylinder (no terminal count on a CPC)'] = (
        watched['4200'] == 0x40 and watched['4201'] == 0x80 and watched['4210'] == 0x40 and watched['4211'] == 0x80)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--engine', type=Path, default=ROOT / '.deps' / 'smsggrecomp')
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    results = checks(build(args.engine))
    for name, ok in results.items():
        print(('ok   ' if ok else 'FAIL ') + name)
    if args.json:
        args.json.write_text(json.dumps(results, indent=1) + '\n', encoding='utf-8')
    return 0 if all(results.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
