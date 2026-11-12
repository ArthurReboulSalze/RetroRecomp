"""MSX1 on the reference Z80 interpreter, headless: C-BIOS boots, the picture, the sound and the inputs (stages 1 and 3).

Builds `native/msx_machine` with the corrected reference interpreter (`retrorecomp.cpu.prepare_reference`, the same
fallback and oracle as the Master System; its pinned source is never edited) and runs C-BIOS 0.29a with no cartridge
and with authored cartridges (small programs written here, no game). Stage 3 adds the TMS9918A and AY-3-8910 fixtures
(native/msx_machine/msx_hardware_checks.c), the C-BIOS logo and text screen as drawn by our renderer (pinned after
inspection), the keyboard and joystick read through the BIOS (SNSMAT, GTSTCK, GTTRIG) and a tone set through WRTPSG
measured in the recorded sound. Stage 1 checks that:

- C-BIOS boots to its logo: the display is on and VRAM holds the logo after the boot;
- C-BIOS scans the slots, finds the cartridge header and calls INIT through its interslot routines;
- a 32 KB cartridge selects its own slot in page 2 with RSLREG / EXPTBL / SLTTBL / ENASLT (the BIOS's RAM helpers at F380h);
- the interrupt path runs: VDP frame flag -> 0038h in the BIOS -> the H.TIMI hook in RAM -> the cartridge's handler,
  once per frame, as JIFFY counts;
- the same holds with slot 3 expanded (RAM in 3-2, the secondary-slot register at FFFFh);
- the MSX's M1 wait state is counted, and a 50 Hz machine (C-BIOS EU) runs 313 lines per frame.

C-BIOS is fetched on first use from its official release archive (SourceForge) and pinned by size and SHA-256, archive
and members; it is BSD-2-Clause (doc/cbios.txt). A development check only: nothing here is built into a game.

    python -B tools/msx_reference.py [--frames 300] [--json PATH]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp.msx_cbios import ARCHIVE, MEMBERS, URL, VERSION  # noqa: E402  (the pin lives in the converter)
JIFFY = 0xFC9E
WORK = ROOT / '.build' / 'msx-reference'
# FNV-1a of the 16 KB VRAM after 300 frames with no cartridge (C-BIOS 0.29a MSX1, 60 Hz): rendered and inspected on
# 12 Nov 2026 (the 'No cartridge found' text screen in Graphic 1).
NO_CARTRIDGE_VRAM_300 = 821520027
# FNV-1a of the drawn picture (192 x 256 colour indices, then the 192 border colours): the C-BIOS logo after 120 frames
# and the 'No cartridge found' text screen after 300, rendered as PNG and inspected before they were pinned.
LOGO_FRAME_120 = 0x3198C337
NO_CARTRIDGE_FRAME_300 = 0x6F9CD703
MSX_CLOCK = 3579545


def cbios() -> Path:
    """The folder holding the pinned C-BIOS images (retrorecomp/msx_cbios.py: fetched and checked on first use)."""
    from retrorecomp import msx_cbios
    return msx_cbios.fetch(lambda text: print(text, flush=True))


# Authored cartridges (no game): an "AB" header whose INIT installs a handler on H.TIMI (FD9Fh) that counts frames.
INIT = 0x4010


def _tail(at: int) -> bytes:
    """Counter at E001h = 0, JP handler on H.TIMI, EI, HALT loop; the handler follows."""
    handler = at + 22
    code = bytes([0x21, 0x00, 0x00, 0x22, 0x01, 0xE0, 0xF3, 0x3E, 0xC3, 0x32, 0x9F, 0xFD,
                  0x21, handler & 0xFF, handler >> 8, 0x22, 0xA0, 0xFD, 0xFB, 0x76, 0x18, 0xFD])
    assert len(code) == 22
    return code + bytes([0x2A, 0x01, 0xE0, 0x23, 0x22, 0x01, 0xE0, 0xC9])


def _cartridge(size: int, init: bytes) -> bytes:
    image = bytearray(b'\xFF' * size)
    image[0:16] = b'AB' + INIT.to_bytes(2, 'little') + bytes(12)
    body = init + _tail(INIT + len(init))
    image[0x10:0x10 + len(body)] = body
    return bytes(image)


def cartridge_16k() -> bytes:
    """16 KB at 4000h: INIT writes 5Ah at E000h."""
    return _cartridge(0x4000, bytes([0x3E, 0x5A, 0x32, 0x00, 0xE0]))


def cartridge_polling() -> bytes:
    """16 KB: INIT enables interrupts and polls the VDP status forever (EI; loop: IN A,(99h); JR loop)."""
    image = bytearray(b'\xFF' * 0x4000)
    image[0:16] = b'AB' + INIT.to_bytes(2, 'little') + bytes(12)
    image[0x10:0x15] = bytes([0xFB, 0xDB, 0x99, 0x18, 0xFC])
    return bytes(image)


def cartridge_input() -> bytes:
    """16 KB: every frame (EI; HALT) reads keyboard row 8 with SNSMAT, joystick 1 with GTSTCK and its trigger A with
    GTTRIG, through the BIOS, into E010h, E011h and E012h."""
    image = bytearray(b'\xFF' * 0x4000)
    image[0:16] = b'AB' + INIT.to_bytes(2, 'little') + bytes(12)
    code = bytes([0xFB, 0x76,                      # 4010h: EI; 4011h: loop: HALT
                  0x3E, 0x08, 0xCD, 0x41, 0x01,    # LD A,8; CALL SNSMAT
                  0x32, 0x10, 0xE0,                # LD (E010h),A
                  0x3E, 0x01, 0xCD, 0xD5, 0x00,    # LD A,1; CALL GTSTCK
                  0x32, 0x11, 0xE0,                # LD (E011h),A
                  0x3E, 0x01, 0xCD, 0xD8, 0x00,    # LD A,1; CALL GTTRIG
                  0x32, 0x12, 0xE0,                # LD (E012h),A
                  0x18, 0xE5])                     # 402Ah: JR loop (402Ch - 27 = 4011h)
    assert 0x10 + len(code) == 0x2C and 0x2C - 27 == 0x11
    image[0x10:0x10 + len(code)] = code
    return bytes(image)


def cartridge_sound() -> bytes:
    """16 KB: sets tone A to period 254 at full volume through the BIOS's WRTPSG, then idles (EI; HALT)."""
    image = bytearray(b'\xFF' * 0x4000)
    image[0:16] = b'AB' + INIT.to_bytes(2, 'little') + bytes(12)
    code = b''.join(bytes([0x3E, r, 0x1E, v, 0xCD, 0x93, 0x00]) for r, v in ((0, 254), (1, 0), (7, 0xBE), (8, 15)))
    code += bytes([0xFB, 0x76, 0x18, 0xFD])        # EI; HALT; JR -3
    image[0x10:0x10 + len(code)] = code
    return bytes(image)


def cartridge_32k() -> bytes:
    """32 KB at 4000h-BFFFh: INIT selects its own slot in page 2 the standard way, then copies 8000h and BFFFh."""
    init = PAGE2 + bytes([
        0x3A, 0x00, 0x80, 0x32, 0x00, 0xE0,   # ld a,(8000h); ld (E000h),a
        0x3A, 0xFF, 0xBF, 0x32, 0x03, 0xE0,   # ld a,(BFFFh); ld (E003h),a
    ])
    assert INIT + 0x1F == 0x402F and init[0x1F] == 0x79
    image = bytearray(_cartridge(0x8000, init))
    image[0x4000] = 0xA5
    image[0x7FFF] = 0x3C
    return bytes(image)


def _ld_write(address: int, value: int) -> bytes:
    """LD A,value; LD (address),A"""
    return bytes([0x3E, value, 0x32, address & 0xFF, address >> 8])


def _ld_copy(source: int, target: int) -> bytes:
    """LD A,(source); LD (target),A"""
    return bytes([0x3A, source & 0xFF, source >> 8, 0x32, target & 0xFF, target >> 8])


# Authored 128 KB mapper cartridges: every 8 KB block ends with C0h + its number. INIT selects page 2 (PAGE2), switches
# banks through the mapper's registers and copies four block markers to E020h-E023h; the Konami SCC one then plays
# channel 1 (a square wave of 16 x 7Fh and 16 x 80h, period 126: 3,579,545 / (32 x 127) = 880.79 Hz) at volume 15.
MAPPER_CARTRIDGES = {
    'konami': (_ld_write(0x6000, 5) + _ld_write(0x8000, 9) + _ld_write(0xA000, 15) + _ld_write(0x5000, 7)
               + _ld_copy(0x7FFF, 0xE020) + _ld_copy(0x9FFF, 0xE021) + _ld_copy(0xBFFF, 0xE022) + _ld_copy(0x5FFF, 0xE023),
               (0xC5, 0xC9, 0xCF, 0xC0)),
    'konami-scc': (_ld_write(0x7000, 5) + _ld_write(0x9000, 9) + _ld_write(0xB000, 15)
                   + _ld_copy(0x7FFF, 0xE020) + _ld_copy(0x9FFF, 0xE021) + _ld_copy(0xBFFF, 0xE022)
                   + _ld_write(0x9000, 0x3F)
                   + bytes([0x21, 0x00, 0x98, 0x06, 0x10, 0x36, 0x7F, 0x23, 0x10, 0xFB,    # 16 x 7Fh at 9800h
                            0x06, 0x10, 0x36, 0x80, 0x23, 0x10, 0xFB])                    # 16 x 80h
                   + _ld_write(0x9880, 126) + _ld_write(0x9881, 0) + _ld_write(0x988A, 15) + _ld_write(0x988F, 1)
                   + _ld_copy(0x9800, 0xE023),
                   (0xC5, 0xC9, 0xCF, 0x7F)),
    'ascii8': (_ld_write(0x6800, 5) + _ld_write(0x7000, 9) + _ld_write(0x7800, 15) + _ld_write(0x6000, 0)
               + _ld_copy(0x7FFF, 0xE020) + _ld_copy(0x9FFF, 0xE021) + _ld_copy(0xBFFF, 0xE022) + _ld_copy(0x5FFF, 0xE023),
               (0xC5, 0xC9, 0xCF, 0xC0)),
    'ascii16': (_ld_write(0x6000, 0) + _ld_write(0x77FF, 3)
                + _ld_copy(0x5FFF, 0xE020) + _ld_copy(0x7FFF, 0xE021) + _ld_copy(0x9FFF, 0xE022) + _ld_copy(0xBFFF, 0xE023),
                (0xC0, 0xC1, 0xC6, 0xC7)),
}


def cartridge_mapper(kind: str) -> bytes:
    image = bytearray(_cartridge(0x20000, PAGE2 + MAPPER_CARTRIDGES[kind][0]))
    for block in range(16):
        image[block * 0x2000 + 0x1FFF] = 0xC0 + block
    return bytes(image)


PAGE2 = bytes([
        0xCD, 0x38, 0x01,        # call RSLREG
        0x0F, 0x0F, 0xE6, 0x03,  # rrca; rrca; and 3      -> primary slot of page 1
        0x4F, 0x06, 0x00,        # ld c,a; ld b,0
        0x21, 0xC1, 0xFC,        # ld hl,EXPTBL
        0x09, 0x7E,              # add hl,bc; ld a,(hl)
        0xE6, 0x80, 0xB1, 0x4F,  # and 80h; or c; ld c,a
        0xF2, 0x2F, 0x40,        # jp p,402Fh            (not expanded)
        0x23, 0x23, 0x23, 0x23,  # inc hl x4             -> SLTTBL
        0x7E, 0xE6, 0x0C,        # ld a,(hl); and 0Ch    -> secondary slot of page 1
        0xB1, 0x4F,              # or c; ld c,a
        0x79, 0x26, 0x80,        # 402Fh: ld a,c; ld h,80h
        0xCD, 0x24, 0x00,        # call ENASLT
])
"""INIT's start in the 32 KB and mapper cartridges: select the cartridge's own slot in page 2 (RSLREG, EXPTBL, SLTTBL,
ENASLT), the standard way. Its JP P target is absolute: it must start at INIT (4010h)."""


def instrument(path: Path) -> None:
    """One MSX addition to the generated interpreter copy (behaviour unchanged): its own interrupt acceptance exported,
    so the runner reads /INT after each instruction. The M1 count is the shared one (cpu.prepare_reference, m1_counter)."""
    source = path.read_text(encoding='utf-8')
    if 'static inline void process_interrupts(z80* const z)' not in source:
        raise ValueError('Pinned CPU source changed: process_interrupts')
    source += '\nvoid msx_reference_accept(z80* const z) { process_interrupts(z); }\n'
    path.write_text(source, encoding='utf-8', newline='\n')


# Authored timing program for the M1 wait state, run bare (no BIOS) until HALT. Each entry: bytes, MSX cycles from
# openMSX's table (cpu/Z80.hh, WAIT_CYCLES = 1), standard Z80 cycles. LDIR copies three bytes: two repeats and a last.
M1_PROGRAM = (
    (bytes([0xF3]), 5, 4),                          # DI
    (bytes([0x3E, 0xC0]), 8, 7),                    # LD A,C0h
    (bytes([0xD3, 0xA8]), 12, 11),                  # OUT (A8h),A        page 3 -> slot 3 (RAM)
    (bytes([0x00]), 5, 4),                          # NOP
    (bytes([0x3A, 0x00, 0x00]), 14, 13),            # LD A,(0000h)
    (bytes([0xCB, 0x47]), 10, 8),                   # BIT 0,A
    (bytes([0xED, 0x44]), 10, 8),                   # NEG
    (bytes([0xDD, 0x21, 0x00, 0xC0]), 16, 14),      # LD IX,C000h
    (bytes([0xDD, 0x7E, 0x00]), 21, 19),            # LD A,(IX+0)
    (bytes([0xDD, 0xCB, 0x00, 0xC6]), 25, 23),      # SET 0,(IX+0)       DD CB: two M1, the fourth byte is not one
    (bytes([0x21, 0x00, 0x00]), 11, 10),            # LD HL,0000h
    (bytes([0x11, 0x00, 0xC1]), 11, 10),            # LD DE,C100h
    (bytes([0x01, 0x03, 0x00]), 11, 10),            # LD BC,3
    (bytes([0xED, 0xB0]), 23 + 23 + 18, 21 + 21 + 16),  # LDIR
    (bytes([0x31, 0x00, 0xD0]), 11, 10),            # LD SP,D000h
    (bytes([0xE3]), 20, 19),                        # EX (SP),HL
    (bytes([0xDB, 0xA8]), 12, 11),                  # IN A,(A8h)
    (bytes([0xED, 0x4F]), 11, 9),                   # LD R,A
    (bytes([0xDD, 0xED, 0x4F]), 16, 13),            # DD, LD R,A         a discarded prefix is one more M1
    (bytes([0x76]), 5, 4),                          # HALT
)


def m1_program() -> bytes:
    return b''.join(code for code, _, _ in M1_PROGRAM)


def build() -> Path:
    from retrorecomp import toolchain
    from retrorecomp.cpu import prepare_reference
    from retrorecomp.platforms import build_executable, cmake_target_args
    WORK.mkdir(parents=True, exist_ok=True)
    engine = ROOT / '.deps' / 'smsggrecomp'
    prepare_reference(WORK, engine, m1_counter=True)
    instrument(WORK / 'runtime_reference.c')
    native = (ROOT / 'native' / 'msx_machine').as_posix()
    (WORK / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.21)
project(MsxReference C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")
set(machine "{native}/msx_machine.c" "{native}/msx_video.c" "{native}/msx_psg.c" "{native}/msx_cart.c")
add_executable(msx_reference "{native}/msx_reference_main.c" ${{machine}} runtime_reference.c)
target_include_directories(msx_reference PRIVATE "${{CMAKE_CURRENT_SOURCE_DIR}}" "{native}")
add_executable(msx_hardware_checks "{native}/msx_hardware_checks.c" ${{machine}})
target_include_directories(msx_hardware_checks PRIVATE "{native}")
foreach(target msx_reference msx_hardware_checks)
  target_compile_definitions(${{target}} PRIVATE _CRT_SECURE_NO_WARNINGS)
  if(NOT WIN32)
    target_link_libraries(${{target}} PRIVATE m)
  endif()
endforeach()
''', encoding='utf-8', newline='\n')
    selection = toolchain.select()
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    log = WORK / 'build.log'
    with log.open('w', encoding='utf-8') as out:
        for step in ([str(selection.cmake), '-S', str(WORK), '-B', str(WORK / 'build'), '-G', selection.generator,
                      '-DCMAKE_BUILD_TYPE=Release', *cmake_target_args()],
                     [str(selection.cmake), '--build', str(WORK / 'build'), '--config', 'Release']):
            result = subprocess.run(step, stdout=out, stderr=subprocess.STDOUT, timeout=600, creationflags=flags)
            if result.returncode:
                raise SystemExit(f'build failed, see {log}')
    return build_executable(WORK / 'build', 'msx_reference')


def hardware_checks() -> list[str]:
    """Run the TMS9918A / AY-3-8910 fixtures (built with the reference); returns the failed lines."""
    from retrorecomp.platforms import build_executable
    exe = build_executable(WORK / 'build', 'msx_hardware_checks')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=300, creationflags=flags)
    print('hardware fixtures')
    for line in result.stdout.splitlines()[:-1]:
        print('  ' + line)
    failed = [line for line in result.stdout.splitlines() if line.startswith('FAIL ')]
    if result.returncode and not failed:
        failed = [f'msx_hardware_checks exited {result.returncode}: {result.stderr.strip()}']
    return failed


# The TMS9918A palette as RGB, for looking at a picture only (the machine gives colour indices).
PALETTE = ((0, 0, 0), (0, 0, 0), (33, 200, 66), (94, 220, 120), (84, 85, 237), (125, 118, 252), (212, 82, 77),
           (66, 235, 245), (252, 85, 84), (255, 121, 120), (212, 193, 84), (230, 206, 128), (33, 176, 59),
           (201, 91, 186), (204, 204, 204), (255, 255, 255))


def png(frame: Path, target: Path) -> None:
    """A frame dump (192 x 256 indices, then 192 border colours) as a PNG with an 8-pixel border, to look at."""
    import struct
    import zlib
    data = frame.read_bytes()
    pixels, border = data[:192 * 256], data[192 * 256:]
    width, height = 272, 208
    rows = []
    for y in range(height):
        line = y - 8
        edge = PALETTE[border[min(max(line, 0), 191)]]
        row = [edge] * width
        if 0 <= line < 192:
            row[8:264] = [PALETTE[i] for i in pixels[line * 256:(line + 1) * 256]]
        rows.append(b'\0' + bytes(c for rgb in row for c in rgb))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xFFFFFFFF)
    target.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                       + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))


# 7Fh x 15 >> 4 = 119 and 80h x 15 >> 4 = -120, scaled x 32,767 / 600 (6,498 and -6,553), mixed x 21,000 / 58,000
# (2,352 and -2,372), x 4/5 (1,881 and -1,897), C integer division.
SCC_SQUARE_SWING = 1881 + 1897


def tone_range(audio: Path, seconds: float = 1.0) -> tuple[int, int]:
    import array
    samples = array.array('h')
    samples.frombytes(audio.read_bytes())
    tail = samples[-int(44100 * seconds):]
    return min(tail), max(tail)


def tone_frequency(audio: Path, seconds: float = 1.0) -> float:
    """Rising crossings of the mean over the last `seconds` of a raw 16-bit mono recording at 44,100 Hz."""
    import array
    samples = array.array('h')
    samples.frombytes(audio.read_bytes())
    tail = samples[-int(44100 * seconds):]
    mean = sum(tail) / len(tail)
    crossings = sum(1 for a, b in zip(tail, tail[1:]) if a < mean <= b)
    return crossings / seconds


def run(exe: Path, *args: str) -> dict:
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    result = subprocess.run([str(exe), *args], capture_output=True, text=True, timeout=300, creationflags=flags)
    if result.returncode:
        raise SystemExit(f'{exe.name} {" ".join(args)} failed: {result.stderr.strip()}')
    return json.loads(result.stdout)


def word(report: dict, address: int) -> int:
    return report['watch'][f'{address:04X}'] | report['watch'][f'{address + 1:04X}'] << 8


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--frames', type=int, default=300)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    roms = cbios()
    exe = build()
    carts = WORK / 'carts'
    carts.mkdir(exist_ok=True)
    (carts / 'authored16.rom').write_bytes(cartridge_16k())
    (carts / 'authored32.rom').write_bytes(cartridge_32k())
    (carts / 'polling.rom').write_bytes(cartridge_polling())
    frames = str(args.frames)
    bios = ['--main', str(roms / 'cbios_main_msx1.rom'), '--logo', str(roms / 'cbios_logo_msx1.rom')]
    watch = [w for a in (0xE000, 0xE001, 0xE002, 0xE003, JIFFY, JIFFY + 1) for w in ('--watch', f'{a:04X}')]
    runs = {
        'no-cartridge': run(exe, *bios, '--frames', frames, '--vram', str(WORK / 'vram-logo.bin'), *watch),
        'authored16': run(exe, *bios, '--cart', str(carts / 'authored16.rom'), '--frames', frames, *watch),
        'authored16-expanded': run(exe, *bios, '--cart', str(carts / 'authored16.rom'), '--layout', 'expanded',
                                   '--frames', frames, *watch),
        'authored32': run(exe, *bios, '--cart', str(carts / 'authored32.rom'), '--frames', frames, *watch),
        'authored32-expanded': run(exe, *bios, '--cart', str(carts / 'authored32.rom'), '--layout', 'expanded',
                                   '--frames', frames, *watch),
        'authored16-pal': run(exe, '--main', str(roms / 'cbios_main_msx1_eu.rom'), '--logo',
                              str(roms / 'cbios_logo_msx1.rom'), '--pal', '--cart', str(carts / 'authored16.rom'),
                              '--frames', frames, *watch),
        'polling': run(exe, *bios, '--cart', str(carts / 'polling.rom'), '--frames', frames, *watch),
    }
    (carts / 'm1.rom').write_bytes(m1_program())
    m1 = run(exe, '--main', str(carts / 'm1.rom'), '--until-halt', '--frames', '1')
    failures = []

    def check(name: str, condition: bool, detail: str) -> None:
        print(f'  {"ok  " if condition else "FAIL"} {name}: {detail}')
        if not condition:
            failures.append(f'{name}: {detail}')

    n = args.frames
    print('m1-table')
    want = sum(msx for _, msx, _ in M1_PROGRAM), sum(z80 for _, _, z80 in M1_PROGRAM)
    check('m1-table', m1['halted'] and m1['z80_cycles'] == want[1] and m1['cycles'] == want[0]
          and m1['m1_waits'] == want[0] - want[1],
          f"{m1['cycles']} MSX cycles = {m1['z80_cycles']} Z80 T-states + {m1['m1_waits']} M1 waits "
          f"(openMSX's table: {want[0]} = {want[1]} + {want[0] - want[1]})")
    for name, report in runs.items():
        print(name)
        lines = 313 if name.endswith('-pal') else 262
        frame = lines * 228
        check(name, report['frames'] == n and n * frame <= report['cycles'] < n * frame + 64,
              f"{report['frames']} frames, {report['cycles']} cycles ({lines} lines of 228)")
        ratio = report['m1_waits'] / max(1, report['z80_cycles'])
        check(name, 0.05 < ratio < 0.35, f"M1 wait states {report['m1_waits']} = {ratio:.1%} of the Z80 T-states")
        check(name, report['vdp_regs'][1] & 0x60 == 0x60, f"VDP R#1 = {report['vdp_regs'][1]:02X}h (display and frame interrupt on)")
        jiffy = word(report, JIFFY)
        check(name, jiffy == report['interrupts'] and report['interrupts'] >= n - 12,
              f"{report['interrupts']} interrupts accepted, JIFFY = {jiffy}")
        if name == 'no-cartridge':
            check(name, report['pc_slot'] & 3 == 0 and report['vram_nonzero'] > 1000,
                  f"PC {report['pc']:04X}h in slot {report['pc_slot']:02X}h, {report['vram_nonzero']} VRAM bytes set (logo)")
            if n == 300:
                check(name, report['vram_fnv'] == NO_CARTRIDGE_VRAM_300,
                      f"VRAM after 300 frames {report['vram_fnv']:08X}h (pinned {NO_CARTRIDGE_VRAM_300:08X}h: the 'No cartridge found' screen)")
            continue
        if name == 'polling':
            check(name, report['pc_slot'] & 3 == 1, f"the cartridge polls the VDP status in slot {report['pc_slot']:02X}h")
            continue
        counter = word(report, 0xE001)
        check(name, report['watch']['E000'] == (0x5A if '16' in name else 0xA5),
              f"INIT reached (E000h = {report['watch']['E000']:02X}h)")
        if '32' in name:
            check(name, report['watch']['E003'] == 0x3C, f"page 2 selected by ENASLT (BFFFh read {report['watch']['E003']:02X}h)")
        check(name, report['halted'] and report['pc_slot'] & 3 == 1 and counter > n // 2 and abs(jiffy - counter) < n // 2,
              f"H.TIMI handler ran {counter} times (JIFFY {jiffy}), CPU halted in slot {report['pc_slot']:02X}h")
        if 'expanded' in name:
            check(name, report['secondary'][3] & 0xC0 == 0x80, f"slot 3 secondary register = {report['secondary'][3]:02X}h (page 3 in 3-2)")
    # Stage 3: the picture, the sound and the inputs.
    failures.extend(hardware_checks())
    (carts / 'input.rom').write_bytes(cartridge_input())
    (carts / 'sound.rom').write_bytes(cartridge_sound())
    pictures = {}
    for name, count, pin in (('logo', '120', LOGO_FRAME_120), ('no-cartridge-text', '300', NO_CARTRIDGE_FRAME_300)):
        dump = WORK / f'frame-{name}.bin'
        pictures[name] = run(exe, *bios, '--frames', count, '--frame', str(dump))
        png(dump, WORK / f'frame-{name}.png')
        print(name)
        got = pictures[name]['frame_fnv']
        check(name, pin is None or got == pin,
              f"picture {got:08X}h after {count} frames ({'pinned' if pin else 'not pinned yet'}; see {dump.stem}.png)")
    keys = [w for a in (0xE010, 0xE011, 0xE012) for w in ('--watch', f'{a:04X}')]
    idle = run(exe, *bios, '--cart', str(carts / 'input.rom'), '--frames', frames, *keys)
    press = n - 50
    pressed = run(exe, *bios, '--cart', str(carts / 'input.rom'), '--frames', frames, *keys,
                  '--event', f'{press}:key:8:0:1', '--event', f'{press}:joy:0:2E')
    print('input')
    values = lambda r: (r['watch']['E010'], r['watch']['E011'], r['watch']['E012'])
    check('input', values(idle) == (0xFF, 0, 0),
          'nothing pressed: SNSMAT(8) = {:02X}h, GTSTCK(1) = {}, GTTRIG(1) = {:02X}h'.format(*values(idle)))
    check('input', values(pressed) == (0xFE, 1, 0xFF),
          'SPACE, joystick 1 up and trigger A: SNSMAT(8) = {:02X}h, GTSTCK(1) = {}, GTTRIG(1) = {:02X}h'.format(*values(pressed)))
    audio = WORK / 'sound.raw'
    sound = run(exe, *bios, '--cart', str(carts / 'sound.rom'), '--frames', frames, '--audio', str(audio))
    print('sound')
    expected = n * 262 * 228 / MSX_CLOCK * 44100
    check('sound', abs(sound['audio_samples'] - expected) < 2 and sound['audio_dropped'] == 0,
          f"{sound['audio_samples']} samples at 44,100 Hz for {n} frames ({expected:.0f} expected), none dropped")
    frequency = tone_frequency(audio)
    check('sound', 439 <= frequency <= 442,
          f'tone A set through WRTPSG: {frequency:.0f} Hz over the last second (1,789,772.5 / (16 x 254) = 440.39)')

    # Stage 4: the mappers, the SCC and the mapper guess, on authored cartridges booted by C-BIOS.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from retrorecomp import msx_rom
    for name, image in (('authored16', cartridge_16k()), ('authored32', cartridge_32k())):
        g = msx_rom.guess(image)
        print(f'guess {name}')
        check(f'guess {name}', (g.mapper, g.base) == ('plain', 0x4000), f'{g.mapper} at {g.base:04X}h ({g.reason})')
    markers = [w for a in (0xE020, 0xE021, 0xE022, 0xE023) for w in ('--watch', f'{a:04X}')]
    for kind, (_, expected_markers) in MAPPER_CARTRIDGES.items():
        image = cartridge_mapper(kind)
        path = carts / f'mapper-{kind}.rom'
        path.write_bytes(image)
        g = msx_rom.guess(image)
        print(f'mapper {kind}')
        check(kind, g.mapper == kind, f'guessed {g.mapper} ({g.reason}; votes {dict(g.votes)})')
        audio = WORK / f'mapper-{kind}.raw'
        report = run(exe, *bios, '--cart', str(path), *g.arguments(), '--frames', frames, *markers, '--audio', str(audio))
        got = tuple(report['watch'][f'{a:04X}'] for a in (0xE020, 0xE021, 0xE022, 0xE023))
        check(kind, got == expected_markers,
              'banks read back ' + ' '.join(f'{v:02X}h' for v in got) + ' (expected '
              + ' '.join(f'{v:02X}h' for v in expected_markers) + ')')
        check(kind, report['halted'] and report['pc_slot'] & 3 == 1, f"the program halts in its slot ({report['pc_slot']:02X}h)")
        if kind == 'konami-scc':
            frequency = tone_frequency(audio)
            check(kind, 880 <= frequency <= 882,
                  f'SCC channel 1, period 126: {frequency:.0f} Hz over the last second (3,579,545 / (32 x 127) = 880.79;'
                  ' without the +1 it would be 887.8)')
            low, high = tone_range(audio)
            check(kind, high - low == SCC_SQUARE_SWING,
                  f'SCC square 7Fh / 80h at volume 15: swing {high - low} (119 and -120 through the mix: {SCC_SQUARE_SWING})')
    if args.json:
        args.json.write_text(json.dumps({'cbios': VERSION, 'frames': n, 'runs': runs, 'failures': failures}, indent=1),
                             encoding='utf-8')
    print('MSX reference:', 'PASS' if not failures else f'{len(failures)} failure(s)')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
