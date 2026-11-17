"""Check the Amiga's in-process snapshot (a multiplayer session's rollback) without a game.

    python -B tools/amiga_rollback_selftest.py [--work .build/amiga-rollback-selftest] [--vamiga PATH] [--warm 100] [--frames 200]

Authors a WHDLoad slave of its own (no game, no ROM, no Kickstart): its 68000 program shows one bitplane through a copper list, blits
in a loop whose size follows the frame count, plays a sample on audio channel 0, takes the VBL, copper, blitter, CIA-A timer and audio
interrupts (the keyboard's bytes taken with their handshake), reads a file of the install through resload_LoadFile, saves a file with resload_SaveFile at its VBL 120 and reads it back
at 160. Then builds native/amiga_machine/amiga_rollback_checks.cpp on the session (interpreted CPU) and runs it on the Amiga 500 and
the Amiga 1200: a snapshot after every frame changes nothing, a load at any frame replays the same frames and digests, a load is
complete at once, wrong sizes are refused, the session's saves are taken back by a load, and a snapshot call allocates nothing
(amiga_rollback_checks.cpp says each check). Exit status 0 only when both models pass. A developer check, never part of a conversion.
"""
import argparse
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / 'tools'):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from amiga_display_selftest import Assembler  # noqa: E402

PROGRAM = 0x8000          # where the game loader copies the program (chip RAM, inside BaseMem)
COPPER, PLANE, BLIT_TO, SAMPLE, WORK = 0x20000, 0x30000, 0x34000, 0x40000, 0x50000
COUNTERS = 0x60000        # +0 VBLs, +4 CIA-A timer A, +8 audio, +12 saved, +16 loaded twice, +20 loaded once
NAME, SAVED, LOADED = 0x60100, 0x60200, 0x60400
KEY = 0x60018           # the last byte the keyboard sent
SAVE_AT, LOAD_AT, FIRST_LOAD_AT = 120, 160, 40
RESLOAD_LOADFILE, RESLOAD_SAVEFILE = 8, 12
CUSTOM = 0xDFF000


class Program(Assembler):
    """The scenario's few extra forms, and forward branches patched once their target is known."""

    def move_b_imm_abs(self, value: int, address: int) -> None:
        self.w(0x13FC, value & 0xFF)
        self.l(address)

    def lea_abs(self, address: int, a: int) -> None:
        self.w(0x41F9 | a << 9)
        self.l(address)

    def addq_l_abs(self, address: int) -> None:            # addq.l #1,address
        self.w(0x52B9)
        self.l(address)

    def bne_forward(self) -> int:
        self.w(0x6600)
        return len(self.words) - 1

    def land(self, at: int) -> None:
        """A forward bcc.s at word `at` lands here."""
        distance = 2 * len(self.words) - (2 * at + 2)
        assert 0 < distance < 128, distance
        self.words[at] |= distance

    def once_at(self, vbl: int, flag: int) -> int:
        """cmpi.l #vbl,COUNTERS ; bne.s skip ; tst.l flag ; bne.s skip ; addq.l #1,flag: the body runs once, at that VBL."""
        self.w(0x0CB9)
        self.l(vbl)
        self.l(COUNTERS)
        first = self.bne_forward()
        self.w(0x4AB9)
        self.l(flag)
        second = self.bne_forward()
        self.addq_l_abs(flag)
        return first, second

    def resload(self, offset: int) -> None:                 # jsr offset(a5)
        self.w(0x4EAD, offset)


def program() -> bytes:
    code = Program(PROGRAM)
    code.w(0x6000, 0)                                       # bra.w main (patched below)
    # Level 3: VBL counted; VBL, copper and blitter acknowledged.
    level3 = code.here
    code.w(0x48E7, 0x8080)                                  # movem.l d0/a0,-(sp)
    code.move_w_abs_d(CUSTOM + 0x01E, 0)                    # move.w INTREQR,d0
    code.w(0x0240, 0x0070)                                  # and.w #$70,d0
    code.w(0x0800, 0x0005, 0x6706)                          # btst #5,d0 ; beq.s +6
    code.addq_l_abs(COUNTERS)
    code.move_w_d_abs(0, CUSTOM + 0x09C)                    # move.w d0,INTREQ
    code.w(0x4CDF, 0x0101, 0x4E73)                          # movem.l (sp)+,d0/a0 ; rte
    # Level 2: CIA-A's timer A, and the keyboard: its byte kept at KEY, then the handshake (SP low about 140 us) that lets it send the next.
    level2 = code.here
    code.w(0x2F00)                                          # move.l d0,-(sp)
    code.w(0x1039)
    code.l(0xBFED01)                                        # move.b ICR,d0 (read: acknowledged)
    code.w(0x0800, 0x0003, 0x6720)                          # btst #3,d0 ; beq.s past the handshake (32 bytes)
    code.w(0x13F9)
    code.l(0xBFEC01)
    code.l(KEY)                                             # move.b SDR,KEY
    code.w(0x08F9, 0x0006)
    code.l(0xBFEE01)                                        # bset #6,CRA (SP output, low)
    code.w(0x7000 | 100, 0x51C8, 0xFFFE)                    # moveq #100,d0 ; dbra d0,*
    code.w(0x08B9, 0x0006)
    code.l(0xBFEE01)                                        # bclr #6,CRA
    code.addq_l_abs(COUNTERS + 4)
    code.move_w_imm_abs(0x0008, CUSTOM + 0x09C)
    code.w(0x201F, 0x4E73)                                  # move.l (sp)+,d0 ; rte
    # Level 4: audio channel 0.
    level4 = code.here
    code.addq_l_abs(COUNTERS + 8)
    code.move_w_imm_abs(0x0080, CUSTOM + 0x09C)
    code.w(0x4E73)
    main = code.here
    code.words[1] = (main - (PROGRAM + 2)) & 0xFFFF
    code.w(0x2A48)                                          # move.l a0,a5 (resload)
    for register in (0x09A, 0x096, 0x09C):
        code.move_w_imm_abs(0x7FFF, CUSTOM + register)
    for vector, handler in ((0x68, level2), (0x6C, level3), (0x70, level4)):
        code.move_l_imm_abs(handler, vector)
    copper = [0x00E0, PLANE >> 16, 0x00E2, PLANE & 0xFFFF, 0x0180, 0x0000, 0x6001, 0xFFFE, 0x0180, 0x0F00,
              0x009C, 0x8010, 0xA001, 0xFFFE, 0x0180, 0x00F0, 0xFFFF, 0xFFFE]
    for n in range(0, len(copper), 2):
        code.move_l_imm_abs(copper[n] << 16 | copper[n + 1], COPPER + 2 * n)
    code.move_l_imm_abs(COPPER, CUSTOM + 0x080)
    code.move_w_imm_abs(0, CUSTOM + 0x088)                  # COPJMP1
    for register, value in ((0x08E, 0x2C81), (0x090, 0x2CC1), (0x092, 0x0038), (0x094, 0x00D0), (0x100, 0x1200), (0x108, 0)):
        code.move_w_imm_abs(value, CUSTOM + register)
    code.lea_abs(PLANE, 0)
    code.w(0x323C, 2559)                                    # move.w #2559,d1
    code.w(0x20C1, 0x51C9, 0xFFFC)                          # move.l d1,(a0)+ ; dbra d1,*-2
    code.lea_abs(SAMPLE, 0)
    code.w(0x7200 | 31)                                     # moveq #31,d1
    code.w(0x30FC, 0x7F81, 0x51C9, 0xFFFA)                  # move.w #$7f81,(a0)+ ; dbra d1,*-4
    code.move_l_imm_abs(SAMPLE, CUSTOM + 0x0A0)
    for register, value in ((0x0A4, 32), (0x0A6, 400), (0x0A8, 64)):
        code.move_w_imm_abs(value, CUSTOM + register)
    for address, value in ((0xBFED01, 0x7F), (0xBFED01, 0x89), (0xBFE401, 0x00), (0xBFE501, 0x20), (0xBFEE01, 0x11)):
        code.move_b_imm_abs(value, address)
    for address in range(COUNTERS, COUNTERS + 24, 4):
        code.move_l_imm_abs(0, address)
    for n, byte in enumerate(b'score\x00'):
        code.move_b_imm_abs(byte, NAME + n)
    code.move_w_imm_abs(0xC0F8, CUSTOM + 0x09A)             # INTENA: VBL, copper, blitter, ports, audio 0
    code.move_w_imm_abs(0x83C1, CUSTOM + 0x096)             # DMACON: bitplane, copper, blitter, audio 0
    code.w(0x46FC, 0x2000)                                  # move.w #$2000,sr
    loop = code.here
    code.wait_blitter()
    code.move_w_imm_abs(0x09F0, CUSTOM + 0x040)
    code.move_w_imm_abs(0, CUSTOM + 0x042)
    code.move_l_imm_abs(0xFFFFFFFF, CUSTOM + 0x044)
    code.move_l_imm_abs(PLANE, CUSTOM + 0x050)
    code.move_l_imm_abs(BLIT_TO, CUSTOM + 0x054)
    code.move_l_imm_abs(0, CUSTOM + 0x064)
    code.move_l_abs_d(COUNTERS, 2)
    code.w(0x0242, 0x001F, 0x5242, 0xED4A, 0x5042)          # and.w #$1f,d2 ; addq.w #1,d2 ; lsl.w #6,d2 ; addq.w #8,d2
    code.move_w_d_abs(2, CUSTOM + 0x058)                    # BLTSIZE: 8 words, 1 to 32 lines
    code.move_l_abs_d(COUNTERS + 4, 3)
    code.w(0xD883, 0xE79C)                                  # add.l d3,d4 ; rol.l #3,d4
    code.w(0x23C4)
    code.l(WORK)                                            # move.l d4,WORK
    # The install's file at VBL 40, the save at 120, the saved file read back at 160 (each once).
    for vbl, flag, call in ((FIRST_LOAD_AT, COUNTERS + 20, 'load'), (SAVE_AT, COUNTERS + 12, 'save'), (LOAD_AT, COUNTERS + 16, 'load')):
        skips = code.once_at(vbl, flag)
        if call == 'save':
            code.w(0x23C4)
            code.l(SAVED)                                   # move.l d4,SAVED
            code.w(0x23F9)
            code.l(COUNTERS)
            code.l(SAVED + 4)                               # move.l COUNTERS,SAVED+4
            code.w(0x7000 | 64)                             # moveq #64,d0
            code.lea_abs(NAME, 0)
            code.lea_abs(SAVED, 1)
            code.resload(RESLOAD_SAVEFILE)
        else:
            code.lea_abs(NAME, 0)
            code.lea_abs(LOADED, 1)
            code.resload(RESLOAD_LOADFILE)
        for at in skips:
            code.land(at)
    code.bra_w(loop)
    return code.data()


def slave(body: bytes) -> bytes:
    """A version 10 slave: the ws_ header, its strings, a game loader that copies the program to PROGRAM and jumps there."""
    strings = bytearray()
    where = {}
    for key, value in (('dir', b'data/'), ('name', b'Rollback check'), ('copy', b'2026 Retro-Recomp'), ('info', b'authored')):
        where[key] = 0x30 + len(strings)
        strings += value + b'\x00'
    if len(strings) % 2:
        strings += b'\x00'
    header = bytearray(0x30)
    header[0:4] = bytes.fromhex('70ff4e75')                 # moveq #-1,d0 ; rts
    header[4:12] = b'WHDLOADS'
    loader_at = 0x30 + len(strings)
    struct.pack_into('>HHIIHHH', header, 12, 10, 0, 0x80000, 0, loader_at, where['dir'], 0)
    header[30], header[31] = 0, 0x59
    struct.pack_into('>iHHH', header, 32, 0, where['name'], where['copy'], where['info'])
    loader = Program(0)
    loader.w(0x43FA, 0)                                     # lea body(pc),a1 (patched)
    lea_at = len(loader.words) - 1
    loader.w(0x45F9)
    loader.l(PROGRAM)                                       # lea PROGRAM,a2
    loader.w(0x323C, len(body) // 2 - 1)                    # move.w #words-1,d1
    loader.w(0x34D9, 0x51C9, 0xFFFC)                        # move.w (a1)+,(a2)+ ; dbra d1,*-2
    loader.jmp_abs(PROGRAM)
    loader.words[lea_at] = 2 * len(loader.words) - 2 * lea_at
    code = bytes(header) + bytes(strings) + loader.data() + body
    code += b'\x00' * (-len(code) % 4)
    out = struct.pack('>IIIII', 0x3F3, 0, 1, 0, 0) + struct.pack('>I', len(code) // 4)
    out += struct.pack('>II', 0x3E9, len(code) // 4) + code + struct.pack('>I', 0x3F2)
    return out


def build(work: Path, core: Path) -> Path:
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args
    machine = (ROOT / 'native' / 'amiga_machine').as_posix()
    whdload = (ROOT / 'native' / 'amiga_whdload').as_posix()
    source = work / 'cmake'
    source.mkdir(parents=True, exist_ok=True)
    (source / 'CMakeLists.txt').write_text(f"""cmake_minimum_required(VERSION 3.20)
project(RetroAmigaRollback LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_subdirectory("{core.as_posix()}" vacore)
foreach(RR_TARGET VACore rvlib utlib)
    if(TARGET ${{RR_TARGET}})
        set_property(TARGET ${{RR_TARGET}} PROPERTY INTERFACE_COMPILE_OPTIONS "")
    endif()
endforeach()
add_library(rr_amiga_session STATIC "{machine}/amiga_session.cpp" "{whdload}/rr_resload.c" "{whdload}/rr_decrunch.c")
target_include_directories(rr_amiga_session PUBLIC "{machine}" "{whdload}")
target_link_libraries(rr_amiga_session PUBLIC VACore)
add_executable(amiga_rollback_checks "{machine}/amiga_rollback_checks.cpp")
target_link_libraries(amiga_rollback_checks PRIVATE rr_amiga_session)
if(WIN32)
    target_link_libraries(rr_amiga_session PUBLIC ws2_32)
endif()
""", encoding='utf-8', newline='\n')
    folder = work / 'build'
    cmake, generator = toolchain()
    run([cmake, '-S', source, '-B', folder, '-G', generator, *cmake_target_args(), '-DCMAKE_BUILD_TYPE=Release'], log=work / 'build.log', cwd=work)
    run([cmake, '--build', folder, '--parallel', build_jobs(), '--target', 'amiga_rollback_checks'], log=work / 'build.log', timeout=7200, cwd=work)
    return build_executable(folder, 'amiga_rollback_checks')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'amiga-rollback-selftest')
    parser.add_argument('--vamiga', type=Path, help='the pinned vAmiga checkout (default: the workspace .deps)')
    parser.add_argument('--warm', type=int, default=100)
    parser.add_argument('--frames', type=int, default=200)
    args = parser.parse_args()
    from retrorecomp import amiga_vamiga
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    core = amiga_vamiga.adapt(args.vamiga or amiga_vamiga.source(), work / 'vamiga')
    checks = build(work, core)
    (work / 'rollback.slave').write_bytes(slave(program()))
    (work / 'score').write_bytes(bytes(range(64)))
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    results = []
    for model in (0, 1):
        done = subprocess.run([str(checks), str(work / 'rollback.slave'), str(work / 'score'), str(model), str(args.warm), str(args.frames)],
                              capture_output=True, text=True, timeout=1800, creationflags=flags)
        line = next((line for line in done.stdout.splitlines() if line.startswith('{')), None)
        result = json.loads(line) if line else {'model': model, 'passed': False, 'error': done.stderr[-1500:]}
        result['exit'] = done.returncode
        if line and done.stderr.strip():
            result['notes'] = done.stderr.strip()[-1500:]
        results.append(result)
    passed = all(r.get('passed') and r['exit'] == 0 for r in results)
    print(json.dumps({'passed': passed, 'models': results}, indent=1))
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
