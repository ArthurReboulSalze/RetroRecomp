"""Independent hardware evidence for the Atari ST (gate G11): named behaviours measured from inside the machine.

    python -B tools/atarist_hardware_check.py [behaviour ...] [--mame PATH-TO-mame.exe]
                                                              (needs a compiler and the pinned Hatari tree; no ROM, no TOS, no disk)

RR_ATARIST_HATARI_DIR (default .build/atarist-hatari) holds the adapted Hatari and its build, which is made when missing or when its adaptation is
out of date; RR_ATARIST_HARDWARE_WORK (default .build/atarist-hardware-check) holds the driver, the images, the dumps and results.json.
With --mame, the behaviours MAME's ST can run (video, mfp-prescalers, mfp-timer-b, wd1772) are repeated on MAME 0.289's `st_uk` driver and
printed beside Hatari's numbers (results-mame.json); MAME's verdicts never make the run pass or fail.

Each behaviour is a tiny 68000 program authored here (assembled by `tools/atarist_hardware_asm.py`: authored words only, no firmware
and no cross-compiler) that the ST session boots as its TOS image (`native/atarist_machine/atarist_hardware_checks.c`). The program
measures one thing of the machine from inside it (MFP timers, the video frame, the IKBD, the YM2149 and the WD1772 as the 68000 sees
them) and leaves its numbers in ST RAM; the tool reads them back together with the picture, the sound and the scripted inputs'
effects, and compares them with values computed here from the hardware's DOCUMENTATION (the source of every number is in `SOURCES`
and in the docstring of its check), never from Hatari. A difference is a finding and is reported with both numbers; nothing is
bent to fit the emulator. `RECORDED` lists the findings that are known and explained: a difference that is not listed there makes
the run fail, and so does a listed one that disappeared.

What this is: hardware-fidelity evidence that the named behaviours agree with the documentation. What it is not: a proof that the
machine is reproduced, a measure of native code, gameplay or physical latency. Timing is in guest cycles and in samples; nothing
here reads a host clock.

Behaviours: video (frame and line structure at 50 and 60 Hz), mfp-prescalers, mfp-timer-b, mfp-timer-d, mfp-timer-d-signs (the detector of the games that use timer D as TOS left it), picture, ym2149, ikbd, wd1772.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

from atarist_hardware_asm import Assembler   # noqa: E402

WORK = Path(os.environ.get('RR_ATARIST_HARDWARE_WORK') or ROOT / '.build' / 'atarist-hardware-check')
HATARI = Path(os.environ.get('RR_ATARIST_HATARI_DIR') or ROOT / '.build' / 'atarist-hatari')

# ------------------------------------------------------------------------------------------------ the documented numbers
SOURCES = {
    'atari-st-internals': 'The Atari ST Internals (STINTERN), "General Information": 512 clock cycles per line and 313 lines per VBL at 50 Hz, '
                          '160,256 clock cycles per VBL, 508 cycles per line at 60 Hz; MFP prescalers 4, 10, 16, 50, 64, 100, 200 for timers A to D',
    # What each entry rests on was reread on 9 November 2026. Read: STINTERN, the MC68901 and YM2149 data sheets, the ikbd protocol text. Not reached: the Atari Compendium, the ST
    # service schematics, the WD1772 data sheet. What only an emulator or a model states is said so: nothing here was measured on a real ST.
    'st-crystal': 'PAL Atari ST master crystal 32.084988 MHz, CPU clock = crystal / 4 = 8.021247 MHz (the constants of MAME atarist.cpp and Hatari clocks_timings.c, which agree; '
                  'the service schematics were not reached)',
    'glue-vertical-counter': 'The GLUE\'s vertical counter: reloaded at its overflow (512) with 199 at 50 Hz, 249 at 60 Hz and 11 at 71 Hz, so 313, 263 and 501 lines. The GLUE as modelled '
                             'in MAME stvideo.cpp; the replica of the schematics gstmcu (vsyncgen.v) loads exactly 50 less at 50 Hz than at 60 Hz. No real ST was counted',
    'mc68901': 'Motorola MC68901 MFP data sheet (January 1984): delay-mode prescalers /4 /10 /16 /50 /64 /100 /200 (Fig. 5-3), TxDR counts down and reloads (5.1.1), event-count mode '
               '(TxCR = 8) counts the pulses of the external input (5.1.3). The ST\'s timer clock 2.4576 MHz is the sheet\'s typical crystal and the constant of Hatari and MAME',
    'st-timer-b': 'MFP timer B input is the GLUE\'s display-enable signal, so in event-count mode it counts the lines on which the Shifter displays (200 per frame in low and medium '
                  'resolution): the GLUE as modelled in MAME stvideo.cpp, and Brandt\'s fullscreen.txt. The Atari Compendium was not reached',
    'st-shifter': 'Atari ST Shifter: 16 colours of 3 bits per component (STINTERN, Screen Display); bitplane words interleaved plane 0 first, the leftmost pixel in the most significant '
                  'bit, plane 0 the least significant bit of the colour index (MAME stvideo.cpp); 320x200 pixels in 32,000 bytes (arithmetic); the border shows colour 0 (no document read '
                  'says it). The Atari Compendium was not reached',
    'ym2149': 'Yamaha YM2149 data sheet: tone frequency = clock / (16 x TP) with TP = 256 x coarse + fine (register pairs 0-1, 2-3, 4-5); mixer register 7 (a 0 bit enables), volume '
              'registers 8-10; 2 MHz is the sheet\'s maximum with SEL high. The ST feeds it crystal / 16 = 2.005 MHz (MAME, Hatari)',
    'ikbd': 'Atari "Intelligent Keyboard (ikbd) Protocol" document: command $14 sets joystick event reporting: a change of joystick 0 (mouse port) is reported as $FE + state byte, of '
            'joystick 1 (joystick port) as $FF + state byte, bit 7 of the state is fire; a key press is its scancode and the release the scancode + $80; command $08 sets relative '
            'mouse reporting: header $F8 + (left button << 1 | right button), then signed dx and dy. The 7812.5 baud of the keyboard ACIA (MC6850), 8N1, and the direction bits (3 right, '
            '2 left, 1 down, 0 up) are Hatari\'s (ikbd.c, joy.h): the document does not give them',
    'wd1772': 'WD1772 and the ST floppy interface: Type I step rates r1r0 = 00, 01, 10, 11 are 6, 12, 2, 3 ms (Hatari fdc.c, MAME wd_fdc.cpp, STINTERN\'s seek rates; the data sheet was not '
              'reached and one transcription of its summary gives 2, 3, 5, 6 ms); the force-interrupt command $D4 raises the interrupt on every index pulse (the same transcription); '
              'drive speed 300 rpm, so an index pulse every 200 ms (a comment of Hatari fdc.c); a Read Sector command with DMA fills the DMA address (advancing by the 512 bytes) and sets '
              'the DMA status bit 0 (no error)',
}
CPU_HZ = 32_084_988 / 4          # PAL ST: 8,021,247 Hz
MFP_HZ = 2_457_600
LINES_50, LINE_CYCLES_50 = 313, 512
LINE_CYCLES_60 = 508
LINES_60 = 263                    # 512 - 249: SOURCES['glue-vertical-counter'] (STINTERN's 315 fits no frame)
FRAME_CYCLES_50 = LINES_50 * LINE_CYCLES_50          # 160,256
PRESCALERS = {1: 4, 2: 10, 3: 16, 4: 50, 5: 64, 6: 100, 7: 200}   # TxCR delay-mode code -> divider

# Known and explained findings, by check id (see the report). A listed difference must still be there; an unlisted one fails the run.
RECORDED: dict[str, str] = {
    'ym2149-clock-nominal': 'the manuals say 2 MHz; on a PAL ST the PSG clock is the CPU clock / 4 = crystal / 16 = 2.005312 MHz, 0.27 % above the round number '
                            '(the tone rows expect the crystal-derived value; see check_ym2149)',
    'mfp-timer-d-tos': "the machine runs Hatari's timer D patch on purpose: when the code that starts the timer is in the TOS's addresses, Hatari starts it at prescaler 200, data 100 "
                       "(docs/ATARI_ST.md, known limits). From RAM, as a game, the timer keeps the data sheet's rate (mfp-timer-d-game)",
}

# ----------------------------------------------------------------------------------------------------- the authored machine
TOS_BYTES = 196608
RAM_KB = 4096
DONE = 0x444F4E45


def tos_image(code: bytes) -> bytes:
    """A 192 KiB TOS-shaped image whose reset runs `code` (assembled at $FC0020). The header is the minimum Hatari accepts: a branch word,
    the version word, the reset stack pointer (24-bit RAM) and the reset program counter / ROM base (as the vector harness builds it)."""
    image = bytearray(TOS_BYTES)
    image[0:4] = bytes([0x60, 0x1E, 0x01, 0x04])
    image[4:8] = (0x00FC0020).to_bytes(4, 'big')
    image[8:12] = (0x00FC0000).to_bytes(4, 'big')
    if 0x20 + len(code) > TOS_BYTES:
        raise ValueError('program too large')
    image[0x20:0x20 + len(code)] = code
    return bytes(image)


def assemble(source: str) -> bytes:
    return tos_image(Assembler(0xFC0020).assemble(source))


# The start of every program: the MMU configuration (without it RAM is partly unmapped), interrupts off, a stack, clean variables
# ($1000-$3FFF), every vector sent to a stub that leaves its vector number at $3FF2, the frame at $3F00 and $0BAD at $3FF0, then the program's own setup.
PROLOGUE = """
start:  move.b  #$0a,$ff8001
        move.w  #$2700,sr
        lea     $f000,sp
        lea     $1000,a0
        move.w  #$bff,d0
clr:    clr.l   (a0)+
        dbra    d0,clr
        lea     8,a0
        lea     stubs,a1
        move.w  #253,d0
vec:    move.l  a1,(a0)+
        lea     10(a1),a1
        dbra    d0,vec
        move.l  #nullint,$70
"""
STUBS = ''.join(f'        move.b  #{n},$3ff2.w\n        bra     unexpected\n' for n in range(2, 256))   # 10 bytes each
TRAP = """
stubs:
""" + STUBS + """
nullint: rte
unexpected:
        move.l  (sp),$3f00
        move.l  4(sp),$3f04
        move.l  8(sp),$3f08
        move.l  12(sp),$3f0c
        move.w  #$0bad,$3ff0
        bra.s   *
"""


# ------------------------------------------------------------------------------------------------------------- the runner
class HarnessError(RuntimeError):
    pass


def ensure_hatari() -> tuple[Path, Path]:
    """The adapted Hatari tree and its build with `libretro-hatari.a` (built when missing: the adaptation of the pinned checkout)."""
    from retrorecomp import atarist_hatari
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_jobs, cmake_target_args
    tree, build = HATARI / 'hatari', HATARI / 'build'
    library = build / 'src' / 'libretro-hatari.a'
    ready = HATARI / 'ready.json'
    current = ready.exists() and json.loads(ready.read_text(encoding='utf-8')).get('adaptation') == atarist_hatari.adaptation_digest()   # the core is keyed by the adaptation
    if not current or not (tree / 'src' / 'retro' / 'main_retro.c').exists() or not library.exists() or not (build / 'src' / 'cpu' / 'cputbl.h').exists():
        tree = atarist_hatari.adapt(atarist_hatari.source(), HATARI)
        build.mkdir(parents=True, exist_ok=True)
        cmake, generator = toolchain()
        run([cmake, '-S', tree, '-B', build, '-G', generator, *cmake_target_args(),
             *atarist_hatari.configure_arguments(ROOT / 'native' / 'atarist_machine' / 'libretro')], log=HATARI / 'configure.log')
        run([cmake, '--build', build, '--parallel', build_jobs(), '--target', 'retro-hatari'], log=HATARI / 'build.log', timeout=3600)
    return tree, build


def build_driver() -> Path:
    """The native driver linked with the session and the adapted Hatari."""
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args
    tree, build = ensure_hatari()
    machine = (ROOT / 'native' / 'atarist_machine').as_posix()
    folder = WORK / 'driver'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'CMakeLists.txt').write_text(f"""cmake_minimum_required(VERSION 3.20)
project(RetroAtariSTHardware C)
set(CMAKE_C_STANDARD 11)
set(RR_HATARI_TREE "{tree.as_posix()}")
set(RR_HATARI_BUILD "{build.as_posix()}")
find_library(RR_HATARI_CORE NAMES retro-hatari libretro-hatari PATHS "${{RR_HATARI_BUILD}}/src" NO_DEFAULT_PATH REQUIRED)
add_executable(checks "{machine}/atarist_hardware_checks.c" "{machine}/atarist_session.c")
target_include_directories(checks PRIVATE "{machine}" "{machine}/libretro" "${{RR_HATARI_BUILD}}"
    "${{RR_HATARI_TREE}}/src/includes" "${{RR_HATARI_TREE}}/src/cpu" "${{RR_HATARI_TREE}}/src/cpu/softfloat" "${{RR_HATARI_TREE}}/src/debug"
    "${{RR_HATARI_TREE}}/src/falcon" "${{RR_HATARI_TREE}}/src" "${{RR_HATARI_TREE}}" "${{RR_HATARI_BUILD}}/src/cpu")
target_link_libraries(checks PRIVATE "${{RR_HATARI_CORE}}")
if(NOT WIN32)
  target_link_libraries(checks PRIVATE m)
else()
  target_link_libraries(checks PRIVATE ws2_32)
endif()
target_compile_options(checks PRIVATE -O2 -fno-fast-math)
""", encoding='utf-8', newline='\n')
    cmake, generator = toolchain()
    run([cmake, '-S', folder, '-B', folder / 'build', '-G', generator, *cmake_target_args(), '-DCMAKE_BUILD_TYPE=Release'], log=folder / 'build.log')
    run([cmake, '--build', folder / 'build', '--parallel', build_jobs(), ], log=folder / 'build.log', timeout=1800)
    return build_executable(folder / 'build', 'checks')


class Result:
    """What one run of a program gave: the machine's RAM, picture, sound and the driver's own counts."""

    def __init__(self, info: dict, prefix: Path):
        self.info = info
        self.ram = (prefix.parent / (prefix.name + '.ram')).read_bytes()
        self.picture = (prefix.parent / (prefix.name + '.picture')).read_bytes()
        self.pcm = (prefix.parent / (prefix.name + '.pcm')).read_bytes()

    def long(self, address: int) -> int:
        return struct.unpack('>I', self.ram[address:address + 4])[0]

    def word(self, address: int) -> int:
        return struct.unpack('>H', self.ram[address:address + 2])[0]

    def longs(self, address: int, count: int) -> list[int]:
        return list(struct.unpack(f'>{count}I', self.ram[address:address + 4 * count]))

    def samples(self) -> list[int]:
        """The left channel of the sound (the ST's PSG is mono: both channels are equal)."""
        return list(struct.unpack(f'<{len(self.pcm) // 2}h', self.pcm))[0::2]


def run_program(driver, name: str, image: bytes, frames: int, *, disk: bytes | None = None, events: list[str] | None = None,
                done: int | None = None, dump: int = 0x40000, timeout: int = 120, extra: tuple = ()) -> Result:
    if isinstance(driver, Mame):
        return driver.run(name, image, frames, disk, timeout)
    folder = WORK / 'runs'
    folder.mkdir(parents=True, exist_ok=True)
    prefix = folder / name
    (folder / f'{name}.tos').write_bytes(image)
    command = [str(driver), '--tos', str(folder / f'{name}.tos'), '--out', str(prefix), '--frames', str(frames), '--dump', str(dump)]
    if disk is not None:
        (folder / f'{name}.st').write_bytes(disk)
        command += ['--disk', str(folder / f'{name}.st')]
    if events:
        (folder / f'{name}.events').write_text('\n'.join(events) + '\n', encoding='ascii', newline='\n')
        command += ['--events', str(folder / f'{name}.events')]
    if done is not None:
        command += ['--done', str(done)]
    command += [str(value) for value in extra]
    environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    try:
        completed = subprocess.run(command, cwd=folder, capture_output=True, text=True, timeout=timeout, env=environment)
    except subprocess.TimeoutExpired as error:
        raise HarnessError(f'{name}: the driver did not finish in {timeout} s') from error
    if completed.returncode:
        raise HarnessError(f'{name}: the driver failed ({completed.returncode}): {completed.stderr.strip()[-300:]}')
    line = next((entry for entry in completed.stdout.splitlines() if entry.startswith('{')), None)
    if line is None:
        raise HarnessError(f'{name}: the driver printed no result')
    return Result(json.loads(line), prefix)


# -------------------------------------------------------------------------------------------- MAME as a second opinion (optional)
MAME_LUA = """-- Waits for the authored program's DONE flag at $2000 (or RR_LIMIT emulated seconds), dumps ST RAM $0000-$3FFF and the two
-- DMA buffer pages $30000-$307FF (big-endian) to the file named by RR_OUT, then exits.
local out = os.getenv("RR_OUT")
local limit = tonumber(os.getenv("RR_LIMIT") or "20")
local finished = false
local function dump()
  local mem = manager.machine.devices[":m68000"].spaces["program"]
  local f = io.open(out, "wb")
  for a = 0, 0x3fff, 4 do f:write(string.pack(">I4", mem:read_u32(a))) end
  for a = 0x30000, 0x307fc, 4 do f:write(string.pack(">I4", mem:read_u32(a))) end
  f:close()
end
emu.register_periodic(function()
  if finished then return end
  local mem = manager.machine.devices[":m68000"].spaces["program"]
  if mem:read_u32(0x2000) == 0x444F4E45 or manager.machine.time:as_double() >= limit then
    finished = true
    dump()
    manager.machine:exit()
  end
end)
"""


class Mame:
    """MAME's `st_uk` driver (flagged not working) running the same authored image as its TOS. MAME also wants the 4 KiB ROM of the keyboard
    controller: an all-zero authored file stands in for it (MAME warns about the checksums and runs), so the IKBD does not work there and
    is not compared. No video and no sound: only RAM is read back through a Lua script. A weak witness, as the matrix says of MAME's ST."""

    def __init__(self, executable: Path):
        self.executable = Path(executable)

    def run(self, name: str, image: bytes, frames: int, disk: bytes | None, timeout: int) -> 'MameResult':
        base = WORK / 'mame'
        roms = base / 'roms' / 'st_uk'
        roms.mkdir(parents=True, exist_ok=True)
        if image[0x20:0x24] != bytes.fromhex('13fc000a'):
            raise HarnessError('the program does not start with the MMU configuration write')
        # MAME's ST has 1 MiB of RAM at most (256K, 512K or 1M): the memory configuration is two banks of 512 KiB ($05), not the 2 x 2 MiB ($0A) of the session
        (roms / 'tos104uk.bin').write_bytes(image[:0x23] + b'' + image[0x24:])
        (roms / 'keyboard.u1').write_bytes(bytes(4096))
        (base / 'dump.lua').write_text(MAME_LUA, encoding='ascii', newline='\n')
        output = base / f'{name}.ram'
        output.unlink(missing_ok=True)
        command = [str(self.executable), 'st_uk', '-rompath', str(base / 'roms'), '-bios', 'tos104', '-video', 'none', '-sound', 'none', '-nothrottle',
                   '-seconds_to_run', str(max(10, frames // 25) + 5), '-autoboot_script', str(base / 'dump.lua'), '-homepath', str(base / 'home'),
                   '-cfg_directory', str(base / 'home' / 'cfg'), '-nvram_directory', str(base / 'home' / 'nvram'), '-skip_gameinfo']
        if disk is not None:
            (base / f'{name}.st').write_bytes(disk)
            command += ['-flop1', str(base / f'{name}.st')]
        environment = dict(os.environ, RR_OUT=str(output), RR_LIMIT=str(max(10, frames // 25)), SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
        try:
            subprocess.run(command, cwd=base, capture_output=True, text=True, timeout=timeout, env=environment)
        except subprocess.TimeoutExpired as error:
            raise HarnessError(f'{name}: MAME did not finish in {timeout} s') from error
        if not output.exists():
            raise HarnessError(f'{name}: MAME wrote no RAM dump')
        return MameResult(output.read_bytes())


class MameResult(Result):
    def __init__(self, dump: bytes):
        ram = bytearray(0x30800)
        ram[:0x4000] = dump[:0x4000]
        ram[0x30000:0x30800] = dump[0x4000:0x4800]
        self.ram, self.picture, self.pcm = bytes(ram), b'', b''
        self.info = {'frame_cycles': [], 'audio_counts': [], 'refresh': None, 'width': 0, 'height': 0, 'audio_rate': 0}


def finding(check: str, what: str, source: str, expected, measured, verdict: str, detail: str = '') -> dict:
    return {'check': check, 'what': what, 'source': source, 'expected': expected, 'measured': measured, 'verdict': verdict, 'detail': detail}


def close(measured: float, expected: float, tolerance: float) -> bool:
    return abs(measured - expected) <= tolerance


# ------------------------------------------------------------------------------------- the timing program (video, MFP A and B)
ROW_BASE, ROW_BYTES, ROW_LIMIT = 0x2100, 32, 64


def timer_program(sync: int, a_code: int, a_data: int, frames: int, b_data: int = 0) -> bytes:
    """A program that samples, at every vertical blank, the HBL count, Timer A (an interrupt count, its counter and its pending bit) and
    the interrupt count of Timer B, for `frames` blanks. Row n at $2100 + 32 n: HBL total, A interrupts, A counter, A pending, B
    interrupts. Timer A runs in delay mode with the prescaler code `a_code` and data `a_data` (0: 256); Timer B in event-count mode with
    `b_data` (0: off). The video sync register is `sync` (2: 50 Hz, 0: 60 Hz)."""
    rows = min(frames + 1, ROW_LIMIT)
    setup_b = f"""
        move.b  #{b_data},$fffa21
        move.b  #8,$fffa1b
        move.b  #$21,$fffa07
        move.b  #$21,$fffa13
""" if b_data else """
        move.b  #$20,$fffa07
        move.b  #$20,$fffa13
"""
    source = PROLOGUE + f"""
        move.l  #hbl,$68
        move.l  #vbl,$70
        move.l  #timer_a,$134
        move.l  #timer_b,$120
        move.b  #{sync},$ff820a
        move.b  #0,$ff8260
        clr.b   $fffa07
        clr.b   $fffa09
        clr.b   $fffa13
        clr.b   $fffa15
        clr.b   $fffa19
        clr.b   $fffa1b
        move.b  #$40,$fffa17
        move.b  #{a_data & 255},$fffa1f
        move.b  #{a_code},$fffa19
{setup_b}
        move.w  #$2000,sr
wait:   stop    #$2000
        cmpi.l  #{rows},$2008.w
        blt     wait
        move.w  #$2700,sr
        move.l  #{DONE},$2000
        bra.s   *

hbl:    addq.l  #1,$2004.w
        rte
timer_a: addq.l #1,$2010.w
        rte
timer_b: addq.l #1,$2014.w
        rte
vbl:    move.w  #$2600,sr
        move.l  d0,-(sp)
        move.l  d1,-(sp)
        move.l  d2,-(sp)
        move.l  d3,-(sp)
        move.l  a0,-(sp)
        move.l  $2008.w,d0
        cmpi.l  #{rows},d0
        bcc.s   vdone
        lsl.l   #5,d0
        lea     {ROW_BASE},a0
        adda.l  d0,a0
sample: move.b  $fffa0b,d1
        move.b  $fffa1f,d2
        move.b  $fffa0b,d3
        cmp.b   d1,d3
        bne.s   sample
        andi.l  #$20,d1
        lsr.l   #5,d1
        andi.l  #$ff,d2
        move.l  $2004.w,(a0)
        move.l  $2010.w,4(a0)
        move.l  d2,8(a0)
        move.l  d1,12(a0)
        move.l  $2014.w,16(a0)
        addq.l  #1,$2008.w
vdone:  move.l  (sp)+,a0
        move.l  (sp)+,d3
        move.l  (sp)+,d2
        move.l  (sp)+,d1
        move.l  (sp)+,d0
        rte
""" + TRAP
    return assemble(source)


def timer_rows(result: Result, frames: int) -> list[dict]:
    rows = []
    for n in range(min(frames + 1, ROW_LIMIT)):
        hbl, ints, counter, pending, b_ints = result.longs(ROW_BASE + n * ROW_BYTES, 5)
        rows.append({'hbl': hbl, 'a_ints': ints, 'a_counter': counter, 'a_pending': pending, 'b_ints': b_ints})
    return rows


def timer_ticks(row: dict, data: int) -> int:
    """Timer A prescaled ticks since it was started, from a sample: whole reloads (the interrupts, plus one when the request is still
    pending: the counter has reloaded but its interrupt has not run) and the part of the current countdown already elapsed."""
    period = data or 256
    counter = row['a_counter'] or period
    return (row['a_ints'] + row['a_pending']) * period + (period - counter)


def run_timer(driver: Path, name: str, sync: int, a_code: int, a_data: int, frames: int, b_data: int = 0) -> tuple[Result, list[dict]]:
    result = run_program(driver, name, timer_program(sync, a_code, a_data, frames, b_data), frames + 40, done=0x2000)
    if result.long(0x2000) != DONE or result.word(0x3FF0):
        raise HarnessError(f'{name}: the program did not finish (done {result.long(0x2000):08x}, trap {result.word(0x3FF0):04x})')
    return result, timer_rows(result, frames)


# ---------------------------------------------------------------------------------------------------- video: frame and line
def check_video(driver: Path) -> list[dict]:
    """The frame and line structure at 50 and 60 Hz, measured with the MFP's 2.4576 MHz clock against the vertical blank.

    The program counts HBL interrupts between vertical blanks and reads Timer A (delay mode, /4, data 256) at each blank. Over 50
    frames the elapsed MFP clocks, times the documented ratio CPU clock / MFP clock (8.021247 MHz / 2.4576 MHz), give the CPU cycles per
    frame: 160,256 at 50 Hz (313 lines of 512 cycles). The HBL total over the same frames gives the lines per frame. The MFP crystal is
    independent of the machine's video timing, so a wrong frame length shows. At 60 Hz the line is 508 cycles and the frame 263 lines, from the
    GLUE's vertical counter as MAME and gstmcu model it (`glue-vertical-counter`); no real ST was counted. STINTERN's 315 lines fit no frame, and a forum's 262 was not read."""
    out = []
    frames = 50
    for sync, label, lines, line_cycles, source in ((2, '50 Hz', LINES_50, LINE_CYCLES_50, 'atari-st-internals'), (0, '60 Hz', LINES_60, LINE_CYCLES_60, 'glue-vertical-counter')):
        result, rows = run_timer(driver, f'video{label[:2]}', sync, 1, 0, frames)
        used = frames - 1       # the first sample is left out: a vertical blank pending at start-up can come early (MAME's does, 54 lines after)
        hbl_total = rows[frames]['hbl'] - rows[1]['hbl']
        lines_measured = hbl_total / used
        clocks = (timer_ticks(rows[frames], 0) - timer_ticks(rows[1], 0)) * 4
        frame_cycles = clocks * CPU_HZ / MFP_HZ / used
        line_measured = frame_cycles / lines_measured
        deltas = result.info['frame_cycles'][2:frames + 1] or [0]
        out.append(finding(f'video-{label[:2]}-lines', f'{label}: lines per frame (HBL interrupts per vertical blank, mean of {used})', source,
                           lines, round(lines_measured, 3), 'agree' if abs(lines_measured - lines) < 0.05 else 'differ'))
        if sync == 2:
            expected_frame = lines * line_cycles
            out.append(finding(f'video-{label[:2]}-frame', f'{label}: CPU cycles per frame measured by the MFP clock', 'atari-st-internals + st-crystal + mc68901',
                               expected_frame, round(frame_cycles, 1), 'agree' if close(frame_cycles, expected_frame, expected_frame * 0.0002) else 'differ',
                               (f"Hatari's own cycle counter per frame: mean {sum(deltas) / len(deltas):.1f}, min {min(deltas)}, max {max(deltas)}" if max(deltas) else '')))
        else:
            out.append(finding(f'video-{label[:2]}-line', f'{label}: CPU cycles per line (frame cycles measured by the MFP clock / lines measured)', 'atari-st-internals',
                               line_cycles, round(line_measured, 2), 'agree' if close(line_measured, line_cycles, 0.05) else 'differ',
                               f'frame {frame_cycles:.1f} cycles' + (f'; Hatari counter mean {sum(deltas) / len(deltas):.1f}' if max(deltas) else '')))
        out[-1]['refresh_reported'] = result.info['refresh']
    return out


# ---------------------------------------------------------------------------------------------------------- the MFP timers
PRESCALER_DATA = {1: 0, 2: 0, 3: 0, 4: 64, 5: 50, 6: 32, 7: 16}    # data registers giving 1,024 to 4,096 MFP clocks per interrupt


def check_mfp_prescalers(driver: Path) -> list[dict]:
    """The seven delay-mode prescalers of Timer A. For each, the program starts the timer with the prescaler and a data value, reads it at
    every blank of 40 frames, and the tool converts the elapsed prescaled ticks to MFP clocks (ticks x divider) and compares them with
    the clocks the documented frame holds: 40 frames x 160,256 cycles x 2.4576 MHz / 8.021247 MHz. Interrupt counts follow from the
    data register by construction and are not what is compared; the counter value is."""
    out = []
    frames = 40
    for code, divider in PRESCALERS.items():
        data = PRESCALER_DATA[code]
        _, rows = run_timer(driver, f'prescaler{divider}', 2, code, data, frames)
        ticks = timer_ticks(rows[frames], data) - timer_ticks(rows[1], data)      # from the second blank: see check_video
        measured = ticks * divider
        expected = (frames - 1) * FRAME_CYCLES_50 * MFP_HZ / CPU_HZ
        tolerance = max(expected * 0.0002, 2 * divider + 30)
        out.append(finding(f'mfp-prescaler-{divider}', f'Timer A /{divider}, data {data or 256}: MFP clocks elapsed in {frames - 1} frames', 'mc68901 + st-crystal',
                           round(expected, 1), measured, 'agree' if close(measured, expected, tolerance) else 'differ',
                           f'{ticks} ticks of {divider} clocks; difference {measured - expected:+.1f} clocks ({(measured - expected) / expected * 100:+.4f} %)'))
    return out


TIMER_D_CODE, TIMER_D_DATA = 4, 64          # /50, data 64: 3,200 MFP clocks per interrupt


def timer_d_program(from_ram: bool, frames: int) -> bytes:
    """Timer D started with its interrupt on, by code running where a game runs (RAM) or where TOS runs (the ROM). Counts its interrupts between the second and the last vertical blank."""
    setup = f"""
setup:  move.b  #{TIMER_D_DATA},$fffa25
        move.b  #{TIMER_D_CODE},$fffa1d
        rts
setup_end:
"""
    call = ("""
        lea     setup,a0
        lea     $3000,a1
        move.w  #63,d0
copy:   move.b  (a0)+,(a1)+
        dbra    d0,copy
        jsr     $3000
""" if from_ram else """
        jsr     setup
""")
    source = PROLOGUE + f"""
        move.l  #hbl,$68
        move.l  #vbl,$70
        move.l  #timer_d,$110
        move.b  #2,$ff820a
        clr.b   $fffa07
        clr.b   $fffa13
        clr.b   $fffa19
        clr.b   $fffa1b
        move.b  #$40,$fffa17
        clr.b   $fffa1d
        move.b  #$10,$fffa09
        move.b  #$10,$fffa15
{call}
        move.w  #$2000,sr
wait:   stop    #$2000
        cmpi.l  #{frames},$2008.w
        blt     wait
        move.w  #$2700,sr
        move.l  $2010.w,$2018.w
        move.l  #{DONE},$2000
        bra.s   *

hbl:    rte
timer_d: addq.l #1,$2010.w
        rte
vbl:    addq.l  #1,$2008.w
        cmpi.l  #2,$2008.w
        bne.s   vdone
        move.l  $2010.w,$2014.w
vdone:  rte
{setup}
""" + TRAP
    return assemble(source)


def check_mfp_timer_d(driver: Path) -> list[dict]:
    """Hatari's timer D patch, which this machine runs on purpose (`hatari_timerd`, docs/ATARI_ST.md): the same setup of timer D, /50 with data 64, by code in RAM, as a game has it, must give the data
    sheet's rate; by code in the ROM, as TOS has it, it gives Hatari's slower one (prescaler 200, data 100). That second row is a recorded difference: it is the limit, measured."""
    out = []
    frames = 41
    expected = (frames - 2) * FRAME_CYCLES_50 * MFP_HZ / CPU_HZ / (PRESCALERS[TIMER_D_CODE] * TIMER_D_DATA)
    for label, from_ram in (('game', True), ('tos', False)):
        result = run_program(driver, f'timerd-{label}', timer_d_program(from_ram, frames), frames + 40, done=0x2000)
        if result.long(0x2000) != DONE or result.word(0x3FF0):
            raise HarnessError(f'timerd-{label}: the program did not finish (done {result.long(0x2000):08x}, trap {result.word(0x3FF0):04x})')
        measured = result.long(0x2018) - result.long(0x2014)
        out.append(finding(f'mfp-timer-d-{label}', f'Timer D /50, data 64, started from {"RAM, as a game" if from_ram else "the ROM, as TOS"}: interrupts in {frames - 2} frames', 'mc68901 + st-crystal',
                           round(expected, 1), measured, 'agree' if close(measured, expected, 2) else 'differ'))
    return out


# The detector of the games that use timer D as the TOS left it (retrorecomp/atarist_hatari.py, docs/ATARI_ST.md): authored accesses to the MFP's
# registers, made by code in RAM (as a game) or in the ROM (as TOS); the counts A, B, C and D the session reports are what the definition says.
DETECTOR_CASES = (       # (name, where, instructions, expected (A, B, C, D))
    ('rom', 'rom', ('move.b $fffa25,d0', 'move.b $fffa1d,d0', 'move.b #64,$fffa25', 'move.b #4,$fffa1d', 'move.b #$10,$fffa09', 'move.b #$10,$fffa15'), (0, 0, 0, 0)),
    ('tddr-read', 'ram', ('move.b $fffa25,d0',), (1, 0, 0, 0)),
    ('tcdcr-read', 'ram', ('move.b $fffa1d,d0',), (0, 0, 0, 1)),
    ('start-before-data', 'ram', ('move.b #4,$fffa1d',), (0, 0, 1, 0)),
    ('enable-only', 'ram', ('move.b #$10,$fffa09', 'move.b #$10,$fffa15'), (0, 1, 0, 0)),
    ('enable-masked', 'ram', ('move.b #$10,$fffa09',), (0, 0, 0, 0)),
    ('own-setup', 'ram', ('move.b #64,$fffa25', 'move.b #4,$fffa1d', 'move.b #$10,$fffa09', 'move.b #$10,$fffa15'), (0, 0, 0, 0)),
)
DETECTOR_EXACT = ('rom', 'tddr-read', 'enable-only', 'own-setup')        # the cases repeated with the patch off


def detector_program(where: str, code: tuple) -> bytes:
    """Timer D's registers cleared, then `code` run from RAM (copied to $3000, as a game's) or from the ROM (as TOS's), then DONE."""
    call = ("""
        lea     setup,a0
        lea     $3000,a1
        move.w  #63,d0
copy:   move.b  (a0)+,(a1)+
        dbra    d0,copy
        jsr     $3000
""" if where == 'ram' else """
        jsr     setup
""")
    body = '\n        '.join(code)
    return assemble(PROLOGUE + f"""
        clr.b   $fffa07
        clr.b   $fffa13
        clr.b   $fffa09
        clr.b   $fffa15
        clr.b   $fffa1d
{call}
        move.l  #{DONE},$2000
        bra.s   *
setup:  {body}
        rts
setup_end:
""" + TRAP)


def check_mfp_timer_d_signs(driver: Path) -> list[dict]:
    """The detector counts, from RAM, a read of TDDR (A), timer D's interrupt left enabled and unmasked without a write of TDDR or a start (B), TCDCR started before
    any write of TDDR (C) and a read of TCDCR (D); it counts nothing for the same accesses made from the ROM, for a masked interrupt, or for the order a game that sets
    the timer up itself uses; the counts are the same with the patch off (`--timer-d exact`); and with the patch off, timer D started from the TOS's addresses runs at the
    data sheet's rate (the patch is what slows it)."""
    out = []
    for name, where, code, expected in DETECTOR_CASES:
        for mode in ('patched', 'exact'):
            if mode == 'exact' and name not in DETECTOR_EXACT:
                continue
            label = f'timerd-signs-{name}-{mode}'
            result = run_program(driver, label, detector_program(where, code), 6, done=0x2000, extra=('--timer-d', mode))
            if result.long(0x2000) != DONE or result.word(0x3FF0):
                raise HarnessError(f'{label}: the program did not finish (done {result.long(0x2000):08x}, trap {result.word(0x3FF0):04x})')
            seen = result.info['timer_d_signs']
            measured = tuple(seen[letter][0] for letter in 'ABCD')
            first = ', '.join(f'{letter} at frame {seen[letter][1]}, pc ${seen[letter][2]:06x}' for letter in 'ABCD' if seen[letter][0])
            out.append(finding(f'mfp-timer-d-signs-{name}' + ('' if mode == 'patched' else '-exact'),
                               f'Timer D signs A B C D for {" ; ".join(code)}, made from {"the ROM, as TOS" if where == "rom" else "RAM, as a game"} (patch {"on" if mode == "patched" else "off"})',
                               'the detector\'s definition (docs/ATARI_ST.md)', list(expected), list(measured),
                               'agree' if measured == expected and bool(result.info['timer_d_patch']) == (mode == 'patched') else 'differ', first))
    frames = 41
    expected_rate = (frames - 2) * FRAME_CYCLES_50 * MFP_HZ / CPU_HZ / (PRESCALERS[TIMER_D_CODE] * TIMER_D_DATA)
    result = run_program(driver, 'timerd-tos-exact', timer_d_program(False, frames), frames + 40, done=0x2000, extra=('--timer-d', 'exact'))
    if result.long(0x2000) != DONE or result.word(0x3FF0):
        raise HarnessError('timerd-tos-exact: the program did not finish')
    measured = result.long(0x2018) - result.long(0x2014)
    out.append(finding('mfp-timer-d-tos-exact', f'Timer D /50, data 64, started from the ROM, as TOS, with the patch off: interrupts in {frames - 2} frames', 'mc68901 + st-crystal',
                       round(expected_rate, 1), measured, 'agree' if close(measured, expected_rate, 2) else 'differ'))
    return out


def check_mfp_timer_b(driver: Path) -> list[dict]:
    """Timer B in event-count mode counts the GLUE's display-enable pulses: one per displayed line, 200 per frame in low and medium
    resolution at both 50 and 60 Hz. With the data register N it interrupts every N lines, so 200 / N times per frame. The vertical
    blank lies outside the displayed lines, so every frame between two blanks holds exactly that many."""
    out = []
    frames = 20
    for sync, label, n in ((2, '50 Hz', 1), (0, '60 Hz', 1), (2, '50 Hz', 50)):
        _, rows = run_timer(driver, f'timerb{label[:2]}-{n}', sync, 1, 0, frames, b_data=n)
        deltas = [rows[i + 1]['b_ints'] - rows[i]['b_ints'] for i in range(1, frames)]
        expected = 200 // n
        out.append(finding(f'mfp-timer-b-{label[:2]}-{n}', f'Timer B event count, data {n}, {label}: interrupts per frame', 'st-timer-b + mc68901',
                           expected, sorted(set(deltas)) if len(set(deltas)) > 1 else deltas[0], 'agree' if set(deltas) == {expected} else 'differ',
                           f'{frames - 1} frames: ' + (f'always {deltas[0]}' if len(set(deltas)) == 1 else f'varies, mean {sum(deltas) / len(deltas):.2f}')))
    return out


# ------------------------------------------------------------------------------------------------------------ the picture
SCREEN_BASE = 0x20000
PALETTE = [((i * 3 + 2) % 8) << 8 | ((i * 5 + 1) % 8) << 4 | ((i * 7 + i // 8) % 8) for i in range(16)]   # 16 distinct 3-bit colours


def expected_indices() -> list[list[int]]:
    """The colour index of each pixel of the 320x200 picture the pattern in ST RAM gives: pixel k of 16-pixel chunk c on line r is k xor ((r + c) and 15)."""
    return [[k ^ ((r + c) & 15) for c in range(20) for k in range(16)] for r in range(200)]


def screen_for(levels: list[int]) -> list[list[int]]:
    """The expected picture when the eight levels of a component show as `levels` (0x00RRGGBB, the same table for the three components)."""
    colours = [levels[w >> 8 & 7] << 16 | levels[w >> 4 & 7] << 8 | levels[w & 7] for w in PALETTE]
    return [[colours[i] for i in row] for row in expected_indices()]


def picture_program() -> bytes:
    planes = ('$5555', '$3333', '$0f0f', '$00ff')
    body = ''
    for plane, base in enumerate(planes):
        body += f"""        move.w  d0,d2
        lsr.w   #{plane},d2
        andi.w  #1,d2
        neg.w   d2
        move.w  #{base},d1
        eor.w   d2,d1
        move.w  d1,(a2)+
""" if plane else f"""        move.w  d0,d2
        andi.w  #1,d2
        neg.w   d2
        move.w  #{base},d1
        eor.w   d2,d1
        move.w  d1,(a2)+
"""
    source = PROLOGUE + f"""
        move.b  #2,$ff820a
        move.b  #0,$ff8260
        lea     $ff8240,a0
        lea     palette,a1
        moveq   #15,d0
pl:     move.w  (a1)+,(a0)+
        dbra    d0,pl
        move.b  #{SCREEN_BASE >> 16},$ff8201
        move.b  #{SCREEN_BASE >> 8 & 255},$ff8203
        lea     {SCREEN_BASE},a2
        moveq   #0,d3
rowlp:  moveq   #0,d4
chlp:   move.w  d3,d0
        add.w   d4,d0
        andi.w  #15,d0
{body}        addq.w  #1,d4
        cmpi.w  #20,d4
        blt     chlp
        addq.w  #1,d3
        cmpi.w  #200,d3
        blt     rowlp
        move.l  #{DONE},$2000
        bra.s   *
palette: dc.w {', '.join(f'${word:04x}' for word in PALETTE)}
""" + TRAP
    return assemble(source)


def check_picture(driver: Path) -> list[dict]:
    """The visible picture of an authored palette and bitplane pattern, pixel by pixel, in ST low resolution (320x200, 16 colours of 3 bits
    per component). The program writes the 16 palette registers, points the Shifter at a screen it fills with the interleaved bitplane
    words, and the tool compares every pixel with the picture the documented layout gives.

    The documents fix which of the eight levels each 3-bit component selects, not the 8-bit number a host picture writes for it (the
    ST's output is analogue), so the table is read from the picture: each of the three components must show exactly eight distinct
    levels, in increasing order, and the same eight for the three components. The window is then found and every pixel compared under
    that table. The border must show colour 0."""
    result = run_program(driver, 'picture', picture_program(), 12, done=0x2000)
    if result.long(0x2000) != DONE or result.word(0x3FF0):
        raise HarnessError('picture: the program did not finish')
    width, height = result.info['width'], result.info['height']
    pixels = list(struct.unpack(f'<{width * height}I', result.picture))
    channels = [sorted({p >> shift & 255 for p in pixels}) for shift in (16, 8, 0)]
    out = []
    table_ok = all(len(c) == 8 for c in channels) and channels[0] == channels[1] == channels[2]
    out.append(finding('picture-levels', 'each colour component shows 8 distinct levels in increasing order, the same for red, green and blue', 'st-shifter', '8, 8, 8 levels; one table',
                       f'{len(channels[0])}, {len(channels[1])}, {len(channels[2])} levels; ' + ('one table' if channels[0] == channels[1] == channels[2] else 'tables differ'),
                       'agree' if table_ok else 'differ', 'levels: ' + ' '.join(f'{v:02x}' for v in channels[0]) +
                       " (the 8-bit numbers are the host picture's convention, not a documented value; the top level is not 255)"))
    if not table_ok:
        return out
    screen = screen_for(channels[0])
    expected_row0 = struct.pack('<320I', *screen[0])
    found = None
    for y in range(height - 199):
        raw = struct.pack(f'<{width}I', *pixels[y * width:(y + 1) * width])
        x = raw.find(expected_row0)
        while x >= 0:
            if x % 4 == 0 and all(pixels[(y + r) * width + x // 4:(y + r) * width + x // 4 + 320] == screen[r] for r in range(200)):
                found = (x // 4, y)
                break
            x = raw.find(expected_row0, x + 1)
        if found:
            break
    if found is None:
        out.append(finding('picture-pixels', f'320x200 window of the {width}x{height} picture equals the pattern', 'st-shifter', '64000 of 64000 pixels equal',
                           'no window equals the pattern', 'differ', 'the pattern was not found at any offset'))
        return out
    ox, oy = found
    out.append(finding('picture-pixels', f'320x200 pixels of the {width}x{height} picture (window at {ox},{oy}) against the documented bitplane layout and palette', 'st-shifter',
                       '64000 of 64000 pixels equal', '64000 of 64000 pixels equal', 'agree', '16 distinct palette entries; plane 0 is the low bit of the index, the leftmost pixel the high bit of the word'))
    border = screen_for(channels[0])[0][0]    # colour 0 as the table shows it
    outside = [pixels[y * width + x] for y in range(height) for x in range(width) if not (oy <= y < oy + 200 and ox <= x < ox + 320)]
    same = sum(1 for p in outside if p == border)
    out.append(finding('picture-border', 'border pixels show colour 0', 'st-shifter', f'{len(outside)} of {len(outside)}', f'{same} of {len(outside)}',
                       'agree' if same == len(outside) else 'differ', f'border width: left {ox}, right {width - ox - 320}, top {oy}, bottom {height - oy - 200}'))
    return out


# ------------------------------------------------------------------------------------------------------------------ YM2149
def psg_program(period: int, mixer: int = 0xFE, volume: int = 15) -> bytes:
    """Channel A: tone period `period`, volume `volume`, mixer register `mixer` (bit 0 = 0 enables the tone; bits 6 and 7 keep the I/O
    ports as outputs, as TOS does); then an endless loop with interrupts off, so the sound is the PSG's alone."""
    def write(register: int, value: int) -> str:
        return f'        move.b  #{register},$ff8800\n        move.b  #{value},$ff8802\n'
    source = PROLOGUE + '        move.b  #2,$ff820a\n' + write(0, period & 255) + write(1, period >> 8) + write(7, mixer) + write(8, volume) + write(9, 0) + write(10, 0) + \
        f"        move.l  #{DONE},$2000\n        bra.s   *\n" + TRAP
    return assemble(source)


def rising_crossings(samples: list[int], threshold: float, hysteresis: float) -> list[float]:
    """Sample positions (interpolated) where the signal rises through `threshold`, after having been below threshold - hysteresis."""
    out, armed = [], bool(samples) and samples[0] < threshold - hysteresis
    for n in range(1, len(samples)):
        if samples[n] < threshold - hysteresis:
            armed = True
        if armed and samples[n - 1] < threshold <= samples[n]:
            out.append(n - 1 + (threshold - samples[n - 1]) / (samples[n] - samples[n - 1]))
            armed = False
    return out


PSG_HZ_NOMINAL = 2_000_000
PSG_HZ = 32_084_988 / 16        # the PSG's clock comes from the same crystal as the CPU's (CPU clock / 4): 2,005,311.75 Hz on a PAL ST


def check_ym2149(driver: Path) -> list[dict]:
    """Channel A tone frequency = clock / (16 x TP), measured on the sound the session produces. The sound's period is the mean distance
    between rising zero crossings (interpolated) over about 100 frames, in samples, converted to hertz with the samples that really came
    per second of guest time (100 frames x 160,256 cycles / 8.021247 MHz); the nominal audio rate is reported beside it.

    The data sheet and the ST manuals say the PSG runs at "2 MHz". On the machine that is the CPU clock divided by four, so on a PAL ST
    with the 32.084988 MHz crystal it is 2.005312 MHz (0.27 % above the round number). The first measurement of this check, against the
    round 2 MHz, differed by +0.265 %; the crystal-derived value is therefore what the tone rows expect (that expectation was adopted
    after seeing the number, which makes these rows weaker than the ones whose expectation was fixed beforehand), and the 2 MHz row
    keeps the difference on record. A mixer register that disables the tone must leave no oscillation."""
    out = []
    frames = 120
    first = 20
    clocks = []
    for period in (127, 254, 508):
        result = run_program(driver, f'ym{period}', psg_program(period), frames)
        samples = result.samples()
        counts = result.info['audio_counts']
        window = samples[sum(counts[:first]):]
        rate = result.info['audio_rate']
        if not window:
            raise HarnessError('ym2149: no sound')
        mean = sum(window) / len(window)
        swing = max(window) - min(window)
        crossings = rising_crossings(window, mean, swing * 0.1)
        if len(crossings) < 20:
            out.append(finding(f'ym2149-tone-{period}', f'tone period {period}: frequency', 'ym2149', round(PSG_HZ / (16 * period), 3), f'{len(crossings)} crossings', 'differ', 'no tone found'))
            continue
        period_samples = (crossings[-1] - crossings[0]) / (len(crossings) - 1)
        f_nominal = rate / period_samples
        guest_seconds = (frames - first) * FRAME_CYCLES_50 / CPU_HZ
        f_guest = len(window) / guest_seconds / period_samples
        clocks.append(f_guest * 16 * period)
        expected = PSG_HZ / (16 * period)
        high = sum(1 for v in window if v > mean) / len(window)
        out.append(finding(f'ym2149-tone-{period}', f'tone period {period}: frequency of channel A (guest time), against clock / (16 x TP) with the clock = crystal / 16', 'ym2149 + st-crystal',
                           round(expected, 3), round(f_guest, 3), 'agree' if close(f_guest, expected, expected * 0.0002) else 'differ',
                           f'round 2 MHz would give {2_000_000 / (16 * period):.3f} Hz; at the nominal {rate} Hz audio rate: {f_nominal:.3f} Hz; {len(window)} samples for '
                           f'{guest_seconds:.3f} s of guest time; {len(crossings)} periods; share of samples above the mean {high:.3f}'))
    if clocks:
        mean_clock = sum(clocks) / len(clocks)
        out.append(finding('ym2149-clock-nominal', 'PSG clock implied by the three tones, against the round 2 MHz of the manuals', 'ym2149', PSG_HZ_NOMINAL, round(mean_clock, 1),
                           'agree' if close(mean_clock, PSG_HZ_NOMINAL, PSG_HZ_NOMINAL * 0.0002) else 'differ',
                           f'{(mean_clock / PSG_HZ_NOMINAL - 1) * 100:+.3f} % from 2 MHz; crystal / 16 is {PSG_HZ:.2f} Hz'))
    result = run_program(driver, 'ym-off', psg_program(254, mixer=0xFF), 40)
    window = result.samples()[sum(result.info['audio_counts'][:20]):]
    swing = max(window) - min(window) if window else 0
    reference = run_program(driver, 'ym-on', psg_program(254), 40)
    on = reference.samples()[sum(reference.info['audio_counts'][:20]):]
    out.append(finding('ym2149-mixer', 'mixer bit 0 = 1 disables the tone of channel A (peak-to-peak swing of the output)', 'ym2149', 'no oscillation (swing 0)',
                       f'swing {swing} with the tone off, {max(on) - min(on)} with it on', 'agree' if swing == 0 and max(on) - min(on) > 1000 else 'differ'))
    return out


# --------------------------------------------------------------------------------------------------------------------- IKBD
LOG_BASE, LOG_LIMIT = 0x2200, 200
SETTLE_LINES = 20000    # the IKBD ignores some commands for a while after its reset (about 1.3 s of guest time pass first)


def ikbd_program(commands: list[int]) -> bytes:
    """Initialises the keyboard ACIA (master reset, divide by 64, 8N1: $96, as TOS does), sends `commands` to the IKBD, then logs every
    byte received as a long word (HBL count << 8 | byte) at $2200, count at $2008. The HBL count (one per 512 cycles) is the clock."""
    sends = ''.join(f'        move.b  #{c},d0\n        bsr     send\n' for c in commands)
    source = PROLOGUE + f"""
        move.b  #2,$ff820a
        move.l  #hbl,$68
        move.b  #$03,$fffc00
        move.b  #$96,$fffc00
        move.w  #$2000,sr
settle: cmpi.l  #{SETTLE_LINES},$2004.w
        blt.s   settle
        move.b  $fffc02,d1
{sends}
rx:     btst    #0,$fffc00
        beq.s   rx
        move.b  $fffc02,d1
        move.l  $2004.w,d2
        lsl.l   #8,d2
        andi.l  #$ff,d1
        or.l    d1,d2
        move.l  $2008.w,d3
        cmpi.l  #{LOG_LIMIT},d3
        bcc.s   rx
        lsl.l   #2,d3
        lea     {LOG_BASE},a1
        adda.l  d3,a1
        move.l  d2,(a1)
        addq.l  #1,$2008.w
        bra.s   rx
send:   btst    #1,$fffc00
        beq.s   send
        move.b  d0,$fffc02
        rts
hbl:    addq.l  #1,$2004.w
        rte
""" + TRAP
    return assemble(source)


def ikbd_log(result: Result) -> list[tuple[int, int]]:
    """(HBL count, byte) of every byte the program received, in order."""
    count = min(result.long(0x2008), LOG_LIMIT)
    return [(value >> 8, value & 255) for value in result.longs(LOG_BASE, count)]


# --------------------------------------------------------------------------------------------------------------------- WD1772
INDEX_BASE, SEEK_BASE, READ_BASE = 0x2100, 0x2140, 0x2200
DMA_BUFFERS = (0x30000, 0x30200, 0x30400)
SEEKS = ((20, 0), (40, 1), (60, 2), (40, 3))                 # (target track, step-rate code): 20 steps of 6, 12, 2 and 3 ms
STEP_MS = {0: 6, 1: 12, 2: 2, 3: 3}
READS = ((7, 1), (3, 0), (9, 1))                             # (sector, side): at track 40 side 1, track 40 side 0, then track 79 side 1
READ_TRACKS = (40, 40, 79)
IRQ_TIMEOUT = 100000    # lines (6.4 s of guest time): a command that has not ended by then is reported as a time-out
INDEX_PULSES = 6


def disk_image() -> bytes:
    """A 720 KiB raw .ST image (80 tracks, 2 sides, 9 sectors of 512 bytes) with a pattern that tells every byte of every sector apart:
    authored, no game or system data."""
    out = bytearray()
    for lba in range(1440):
        x = ((lba + 1) * 2654435761) & 0xFFFFFFFF      # a linear congruential generator seeded by the sector number
        for _ in range(512):
            x = (x * 1103515245 + 12345) & 0xFFFFFFFF
            out.append(x >> 16 & 255)
    return bytes(out)


def lba_of(track: int, side: int, sector: int) -> int:
    return (track * 2 + side) * 9 + sector - 1


def wd_program() -> bytes:
    side_register = {0: 0xFD, 1: 0xFC}      # PSG port A: bit 0 = 0 selects side 1, bit 1 = 0 selects drive A, bit 2 = 1 deselects drive B
    seeks = ''.join(f'        moveq   #{track},d2\n        moveq   #{rate},d3\n        bsr     seek\n' for track, rate in SEEKS)
    reads = ''
    for n, ((sector, side), track) in enumerate(zip(READS, READ_TRACKS)):
        if n == 2:
            reads += '        moveq   #79,d2\n        moveq   #3,d3\n        bsr     seek\n'
        reads += f'        moveq   #{sector},d2\n        move.b  #{side_register[side]},d3\n        lea     {DMA_BUFFERS[n]},a2\n        bsr     read\n'
    source = PROLOGUE + f"""
        move.b  #2,$ff820a
        move.l  #hbl,$68
        move.w  #$2000,sr
        move.b  #14,$ff8800
        move.b  #{side_register[0]},$ff8802
        lea     {SEEK_BASE},a3
        lea     {READ_BASE},a5
        move.w  #$80,d0
        move.w  #$03,d1
        bsr     wreg
        bsr     wait_irq
        move.l  d4,$2010.w
        move.w  #$80,d0
        bsr     rreg
        move.l  d1,$2014.w
        move.w  #$80,d0
        move.w  #$d4,d1
        bsr     wreg
        lea     {INDEX_BASE},a4
        moveq   #{INDEX_PULSES - 1},d2
ix:     bsr     wait_irq
        move.l  $2004.w,(a4)+
        move.w  #$80,d0
        bsr     rreg
        dbra    d2,ix
        move.w  #$80,d0
        move.w  #$d0,d1
        bsr     wreg
        move.w  #$80,d0
        bsr     rreg
{seeks}{reads}        move.l  #{DONE},$2000
        bra.s   *

wreg:   move.w  d0,$ff8606
        bsr     delay
        move.w  d1,$ff8604
        bra     delay
rreg:   move.w  d0,$ff8606
        bsr     delay
        move.w  $ff8604,d1
        andi.l  #$ff,d1
        rts
delay:  moveq   #20,d6
dl:     dbra    d6,dl
        rts
wait_irq: move.l $2004.w,d5
        addi.l  #{IRQ_TIMEOUT},d5
wi:     btst    #5,$fffa01
        beq.s   wi_ok
        cmp.l   $2004.w,d5
        bhi.s   wi
        moveq   #1,d4
        rts
wi_ok:  moveq   #0,d4
        rts

seek:   move.w  #$86,d0
        move.w  d2,d1
        bsr     wreg
        move.l  $2004.w,(a3)
        move.w  #$80,d0
        move.w  d3,d1
        addi.w  #$18,d1
        bsr     wreg
        bsr     wait_irq
        move.l  $2004.w,4(a3)
        move.w  #$80,d0
        bsr     rreg
        move.l  d1,8(a3)
        move.l  d4,12(a3)
        lea     16(a3),a3
        rts

read:   move.b  #14,$ff8800
        move.b  d3,$ff8802
        move.l  a2,d0
        move.b  d0,$ff860d
        lsr.l   #8,d0
        move.b  d0,$ff860b
        lsr.l   #8,d0
        move.b  d0,$ff8609
        move.w  #$84,d0
        move.w  d2,d1
        bsr     wreg
        move.w  #$190,$ff8606
        bsr     delay
        move.w  #$90,$ff8606
        bsr     delay
        move.w  #1,$ff8604
        bsr     delay
        move.w  #$80,d0
        move.w  #$80,d1
        bsr     wreg
        bsr     wait_irq
        move.l  d4,(a5)
        move.w  #$90,$ff8606
        bsr     delay
        moveq   #0,d1
        move.w  $ff8606,d1
        move.l  d1,4(a5)
        move.w  #$80,d0
        bsr     rreg
        move.l  d1,8(a5)
        moveq   #0,d0
        move.b  $ff8609,d0
        lsl.l   #8,d0
        move.b  $ff860b,d0
        lsl.l   #8,d0
        move.b  $ff860d,d0
        move.l  d0,12(a5)
        lea     16(a5),a5
        rts

hbl:    addq.l  #1,$2004.w
        rte
""" + TRAP
    return assemble(source)


def check_wd1772(driver: Path) -> list[dict]:
    """The floppy controller as the 68000 drives it (the sequences of a real TOS, EmuTOS's floppy.c):
      * the index pulse: after a Force Interrupt on index ($D4) the interrupt line (MFP GPIP bit 5) falls at every index pulse; the pulse
        comes every 200 ms at 300 rpm, timed here in HBL lines (512 cycles) over 5 intervals;
      * the Type I step rates: a Seek of 20 tracks takes 20 steps of 6, 12, 2 or 3 ms (r1r0 = 00, 01, 10, 11);
      * Read Sector with DMA: the 512 bytes of the sector of an authored .ST image reach the DMA address, the DMA address advances by
        512, the DMA status says no error and the FDC status has no record-not-found, CRC or lost-data bit."""
    image = disk_image()
    result = run_program(driver, 'wd1772', wd_program(), 700, disk=image, done=0x2000, timeout=300)
    out = []
    if result.long(0x2000) != DONE or result.word(0x3FF0):
        raise HarnessError(f'wd1772: the program did not finish (done {result.long(0x2000):08x}, trap {result.word(0x3FF0):04x}, vector {result.ram[0x3FF2]}, '
                           f'restore timeout {result.long(0x2010)})')
    stamps = result.longs(INDEX_BASE, INDEX_PULSES)
    lines_per_second = CPU_HZ / LINE_CYCLES_50
    period = (stamps[-1] - stamps[0]) / (INDEX_PULSES - 1)
    expected = 0.2 * lines_per_second
    out.append(finding('wd1772-index', 'index pulse period (HBL lines of 512 cycles, mean of 5 intervals) at 300 rpm = 200 ms', 'wd1772 + st-crystal', round(expected, 1),
                       round(period, 1), 'agree' if close(period, expected, 1.5) else 'differ', f'{period / lines_per_second * 1000:.2f} ms; stamps {stamps}'))
    track_before = [0] + [t for t, _ in SEEKS]
    for n, (track, rate) in enumerate(SEEKS):
        start, end, status, timeout = result.longs(SEEK_BASE + 16 * n, 4)
        steps = abs(track - track_before[n])
        # The data sheet gives the rate in milliseconds of a controller clocked at 8 MHz. The ST feeds it with the 8 MHz of its own
        # crystal chain, so in CPU cycles the time is steps x ms x 8,000,000 (the controller's clock cycles are CPU cycles); measured
        # against a wall-clock reading of the same milliseconds (x 8,021,247) the answer differs by 0.27 %. Both are computed and the
        # measurement must lie between them, with 4 lines (0.26 ms) for the command's own latency (two register writes, a polling loop).
        low = steps * STEP_MS[rate] / 1000 * 8_000_000 / LINE_CYCLES_50
        high = steps * STEP_MS[rate] / 1000 * lines_per_second
        measured = end - start
        fits = 'between' if low - 1 <= measured <= high + 4 else 'outside'
        out.append(finding(f'wd1772-seek-{STEP_MS[rate]}ms', f'Seek of {steps} tracks at {STEP_MS[rate]} ms per step (r1r0 = {rate:02b}), lines from command to interrupt',
                           'wd1772 + st-crystal', f'{low:.1f} (8 MHz clock in CPU cycles) to {high:.1f} (wall-clock ms)', measured,
                           'agree' if not timeout and fits == 'between' else 'differ',
                           f'{measured / lines_per_second * 1000:.2f} ms of guest time for {steps * STEP_MS[rate]} ms; {measured - low:+.1f} lines from the 8 MHz-clock figure; status ${status:02x}' +
                           ('; TIMED OUT' if timeout else '')))
    for n, ((sector, side), track) in enumerate(zip(READS, READ_TRACKS)):
        timeout, dma_status, fdc_status, address = result.longs(READ_BASE + 16 * n, 4)
        base = DMA_BUFFERS[n]
        lba = lba_of(track, side, sector)
        wanted = image[lba * 512:(lba + 1) * 512]
        got = result.ram[base:base + 512]
        wrong = sum(1 for a, b in zip(wanted, got) if a != b)
        ok = not timeout and wrong == 0 and address == base + 512 and dma_status & 1 and not fdc_status & 0x1C   # the DMA status has only bits 0-2 defined
        out.append(finding(f'wd1772-read-{n + 1}', f'Read Sector track {track} side {side} sector {sector} with DMA: 512 bytes, DMA address, DMA status, FDC status', 'wd1772',
                           f'512 of 512 bytes equal; address {base + 512:#x}; DMA status bit 0 set; FDC error bits clear',
                           f'{512 - wrong} of 512 bytes equal; address {address:#x}; DMA status bits {dma_status & 7:#x}; FDC status {fdc_status:#04x}' +
                           ('; TIMED OUT' if timeout else ''), 'agree' if ok else 'differ'))
    return out


def packet_gaps(log: list[tuple[int, int]]) -> list[int]:
    """Lines between consecutive bytes of the same burst (less than 100 lines apart: a packet is sent back to back)."""
    return [b[0] - a[0] for a, b in zip(log, log[1:]) if b[0] - a[0] < 100]


def hex_bytes(values) -> str:
    return ' '.join(f'{b:02X}' for b in values)


def check_ikbd(driver: Path) -> list[dict]:
    """The keyboard controller through the keyboard ACIA, with commands sent after the IKBD has settled (it ignores some commands for a
    while after its reset, a real-firmware behaviour):
      * $12 then $14 (joystick event reporting): directions of joystick 1 and joystick 0 arrive as $FF / $FE + state byte, the fire button
        as bit 7, a key press as its scancode and its release as the scancode + $80;
      * $1A then $08 (relative mouse): $F8 + buttons, dx, dy, a motion of 300 split into signed bytes of at most 127;
      * the bytes of a packet arrive at 7812.5 baud, 10 bits each: one byte every 20.05 lines of 512 cycles."""
    out = []
    joystick_events = ['80 joy 1 8', '90 joy 1 0', '100 joy 0 1', '110 joy 0 0', '120 joy 1 6', '130 joy 1 0', '140 key 97 1', '150 key 97 0',
                       '160 joy 1 16', '170 joy 1 0', '180 joy 0 16', '190 joy 0 0']      # joystick bits: up 1, down 2, left 4, right 8, fire 16; 97 is 'a'
    result = run_program(driver, 'ikbd-joystick', ikbd_program([0x12, 0x14]), 215, events=joystick_events)
    log = [entry for entry in ikbd_log(result) if entry[0] >= SETTLE_LINES]
    stream = [byte for _, byte in log]
    wanted = {'directions': [0xFF, 0x08, 0xFF, 0x00, 0xFE, 0x01, 0xFE, 0x00, 0xFF, 0x06, 0xFF, 0x00],
              'key': [0x1E, 0x9E],
              'fire': [0xFF, 0x80, 0xFF, 0x00, 0xFE, 0x80, 0xFE, 0x00]}
    what = {'directions': 'joystick event reporting: right on joystick 1, up on joystick 0, left+down on joystick 1, with their releases',
            'key': 'a key press and release: scancode $1E then $9E',
            'fire': 'joystick event reporting: fire on joystick 1 then on joystick 0 (bit 7), with releases'}
    position = 0
    for name, expected in wanted.items():
        got = stream[position:position + len(expected)]
        position += len(expected)
        out.append(finding(f'ikbd-{name}', what[name], 'ikbd', hex_bytes(expected), hex_bytes(got), 'agree' if got == expected else 'differ'))
    if len(stream) != position:
        out[-1]['detail'] = f'{len(stream) - position} more byte(s) followed: ' + hex_bytes(stream[position:])
        out[-1]['verdict'] = 'differ'
    mouse_events = ['80 mouse 5 -3 1 0', '90 mouse 0 0 0 1', '100 mouse -10 7 0 0', '110 mouse 300 0 0 0',
                    '120 mouse 5080 0 0 0']
    mouse = run_program(driver, 'ikbd-mouse', ikbd_program([0x1A, 0x08]), 170, events=mouse_events)
    mouse_log = [entry for entry in ikbd_log(mouse) if entry[0] >= SETTLE_LINES]
    mouse_stream = [byte for _, byte in mouse_log]
    packets = [mouse_stream[n:n + 3] for n in range(0, len(mouse_stream), 3)]

    def signed(b: int) -> int:
        return b - 256 if b > 127 else b

    expected_three = [[0xFA, 0x05, 0xFD], [0xF9, 0x00, 0x00], [0xF8, 0xF6, 0x07]]
    out.append(finding('ikbd-mouse', 'relative mouse: left button + (5, -3); right button alone; (-10, 7) with no button', 'ikbd',
                       ' | '.join(hex_bytes(p) for p in expected_three), ' | '.join(hex_bytes(p) for p in packets[:3]),
                       'agree' if packets[:3] == expected_three else 'differ'))
    big, burst = packets[3:6], packets[6:]
    total = sum(signed(p[1]) for p in big)
    valid = all(p[0] == 0xF8 and abs(signed(p[1])) <= 127 for p in big) and len(mouse_stream) == 3 * len(packets)
    out.append(finding('ikbd-mouse-split', 'relative mouse: a motion of 300 is reported as signed bytes, each at most 127, in packets with header $F8', 'ikbd',
                       'dx sum 300, each at most 127, dy 0', f'dx sum {total} (' + ' '.join(str(signed(p[1])) for p in big) + f'), dy {sum(signed(p[2]) for p in big)}',
                       'agree' if valid and total == 300 and sum(signed(p[2]) for p in big) == 0 else 'differ'))
    burst_log = mouse_log[18:]
    out.append(finding('ikbd-mouse-burst', 'relative mouse: a motion of 5080 is 40 packets of 127, back to back', 'ikbd', '40 packets $F8 7F 00', f'{len(burst)} packets, ' +
                       ('all $F8 7F 00' if all(p == [0xF8, 0x7F, 0x00] for p in burst) else 'others: ' + ' | '.join(hex_bytes(p) for p in burst if p != [0xF8, 0x7F, 0x00])),
                       'agree' if len(burst) == 40 and all(p == [0xF8, 0x7F, 0x00] for p in burst) else 'differ'))
    # Byte time. 7812.5 baud is 1.28 ms per 10-bit byte; the documents do not say whether that is real time (the keyboard controller has its
    # own crystal: 20.055 lines of 512 cycles at 8.021247 MHz) or counted on the CPU clock (10 x 1,024 cycles = exactly 20 lines); the
    # measurement must lie between the two, and the detail says which end it is at.
    span = (burst_log[-1][0] - burst_log[0][0]) / (len(burst_log) - 1) if len(burst_log) > 40 else 0
    real_time = 10 * CPU_HZ / 7812.5 / LINE_CYCLES_50
    cpu_counted = 10 * 8_000_000 / 7812.5 / LINE_CYCLES_50
    fits = cpu_counted - 0.03 <= span <= real_time + 0.03
    out.append(finding('ikbd-baud', 'time between the bytes of a back-to-back burst at 7812.5 baud, 8N1 (10 bits): lines of 512 cycles', 'ikbd + st-crystal',
                       f'{cpu_counted:.3f} (counted on an 8 MHz CPU clock) to {real_time:.3f} (real time at 8.021247 MHz)', round(span, 3), 'agree' if fits else 'differ',
                       f'{len(burst_log)} bytes; {(span - cpu_counted):+.3f} lines from the CPU-counted figure, {(span - real_time):+.3f} from the real-time one; resolution about '
                       f'{2 / max(len(burst_log) - 1, 1):.3f} lines'))
    return out


# ------------------------------------------------------------------------------------------------------------------ the tool
CHECKS = {'video': check_video, 'mfp-prescalers': check_mfp_prescalers, 'mfp-timer-b': check_mfp_timer_b, 'mfp-timer-d': check_mfp_timer_d, 'mfp-timer-d-signs': check_mfp_timer_d_signs, 'picture': check_picture,
          'ym2149': check_ym2149, 'ikbd': check_ikbd, 'wd1772': check_wd1772}


def summary(entry: dict) -> str:
    return f"{entry['verdict']:<12} {entry['check']:<22} expected {entry['expected']} | measured {entry['measured']}" + (f" | {entry['detail']}" if entry['detail'] else '')


def problems(entries: list[dict]) -> list[str]:
    """A difference that is not recorded is a problem; so is a recorded one that is gone."""
    found = [f"{e['check']}: differs (expected {e['expected']}, measured {e['measured']}) and is not recorded" for e in entries
             if e['verdict'] == 'differ' and e['check'] not in RECORDED]
    seen = {e['check']: e['verdict'] for e in entries}
    found += [f'{check}: recorded as a difference but it now {seen[check]}' for check in RECORDED if check in seen and seen[check] != 'differ']
    return found


MAME_CHECKS = ('video', 'mfp-prescalers', 'mfp-timer-b', 'wd1772')     # the behaviours MAME's ST can run without the keyboard ROM, the sound or a picture


def compare_with_mame(mame: Mame, wanted: list[str], hatari: list[dict]) -> list[dict]:
    """The same checks on MAME, printed beside Hatari's numbers; MAME's verdicts are never part of the pass/fail of the run."""
    by_check = {entry['check']: entry for entry in hatari}
    rows = []
    for name in wanted:
        if name not in MAME_CHECKS:
            continue
        try:
            found = CHECKS[name](mame)
        except (HarnessError, KeyError, IndexError, ValueError, struct.error) as error:
            print(f'mame         {name:<22} did not run: {error}')
            rows.append({'check': name, 'verdict': 'did not run', 'detail': str(error)})
            continue
        for entry in found:
            other = by_check.get(entry['check'])
            rows.append(dict(entry, hatari_measured=other['measured'] if other else None, hatari_verdict=other['verdict'] if other else None))
            print(f"mame {entry['verdict']:<12} {entry['check']:<22} expected {entry['expected']} | MAME {entry['measured']} | Hatari {rows[-1]['hatari_measured']}")
    return rows


def main(names=None) -> int:
    arguments = list(names or [])
    mame = None
    if '--mame' in arguments:
        at = arguments.index('--mame')
        mame = Mame(Path(arguments[at + 1]))
        del arguments[at:at + 2]
    wanted = arguments or list(CHECKS)
    unknown = [name for name in wanted if name not in CHECKS]
    if unknown:
        print('unknown behaviour:', ', '.join(unknown), '- known:', ', '.join(CHECKS))
        return 2
    driver = build_driver()
    entries: list[dict] = []
    for name in wanted:
        entries += CHECKS[name](driver)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / 'results.json').write_text(json.dumps(entries, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    for entry in entries:
        print(summary(entry))
        if entry['check'] in RECORDED and entry['verdict'] == 'differ':
            print(f"             recorded: {RECORDED[entry['check']]}")
    count = {verdict: sum(1 for e in entries if e['verdict'] == verdict) for verdict in ('agree', 'differ', 'inconclusive')}
    print(f"{len(entries)} measurements: {count['agree']} agree with the documentation, {count['differ']} differ, {count['inconclusive']} not decided by the documents")
    failed = problems(entries)
    for text in failed:
        print('PROBLEM', text)
    if mame is not None:
        rows = compare_with_mame(mame, wanted, entries)
        (WORK / 'results-mame.json').write_text(json.dumps(rows, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:] or None))
