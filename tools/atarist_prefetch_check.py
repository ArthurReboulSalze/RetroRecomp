"""A program that rewrites the very next instruction, through the native steps (a guard check of the Atari ST).

    python -B tools/atarist_prefetch_check.py        (needs a compiler, no ROM, no TOS, no game)

The 68000 has already fetched the word of the next instruction when the one before it runs, so a write over that word changes memory but
not the opcode the CPU executes next (it executes the old one). A step guarded by the words in memory alone would run the handler of the
NEW word. The Atari ST's step hook compares the opcode Hatari latched in its prefetch queue with the step's own and the steps call Hatari's
own handler of that opcode, so the case must come out as the interpreter's.

Authored program (no TOS, no disk of anyone), in RAM: D2 = $5440 (ADDQ.W #2,D0), A2 = the address of `patch`; four times `MOVE.W D2,(A2)`
followed by `patch: ADDQ.W #1,D0`. The first time the old opcode (+1) still runs, the three following times memory is already $5440
(+2): D0 = 7 after the loop (a guard on memory alone gives 8). The check converts it the way a game is converted: a fresh reference run
observes the instructions, the generator writes the steps, the player is built with them, and both runs must give the same trace, with the
instruction at `patch` run natively on none of the four passes it would differ on.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WORK = ROOT / '.build' / 'atarist-prefetch-check'
TOS_BYTES = 196608
ROUTINE_RAM, ROUTINE_ROM = 0x10000, 0xfc0100
EXPECTED_D0 = 7


def words(*values: int) -> bytes:
    return b''.join(struct.pack('>H', v & 0xffff) for v in values)


def long(value: int) -> bytes:
    return struct.pack('>I', value & 0xffffffff)


def routine() -> bytes:
    patch = ROUTINE_RAM + 0x12
    code = words(0x4280)                                            # 10000 CLR.L D0
    code += words(0x7203)                                           # 10002 MOVEQ #3,D1
    code += words(0x243c) + long(0x5440)                            # 10004 MOVE.L #$5440,D2
    code += words(0x247c) + long(patch)                             # 1000A MOVEA.L #patch,A2
    code += words(0x3482)                                           # 10010 loop: MOVE.W D2,(A2): the word of `patch` is in the prefetch queue
    code += words(0x5240)                                           # 10012 patch: ADDQ.W #1,D0
    code += words(0x51c9, 0xfffa)                                   # 10014 DBF D1,loop
    code += words(0x60fe)                                           # 10018 BRA.S *
    assert len(code) == 0x1a and ROUTINE_RAM + 0x10 + 2 == patch
    return code


def authored_tos() -> bytes:
    code = words(0x13fc, 0x0005) + long(0x00ff8001)                 # MOVE.B #5,$FF8001.L (memory configuration)
    code += words(0x46fc, 0x2700)                                   # MOVE #$2700,SR
    code += words(0x207c) + long(ROUTINE_ROM)                       # MOVEA.L #rom,A0
    code += words(0x227c) + long(ROUTINE_RAM)                       # MOVEA.L #ram,A1
    code += words(*([0x32d8] * (len(routine()) // 2)))              # MOVE.W (A0)+,(A1)+ x13
    code += words(0x4ef9) + long(ROUTINE_RAM)                       # JMP ram
    tos = bytearray(TOS_BYTES)
    tos[0:4] = bytes((0x60, 0x1e, 0x01, 0x04))
    tos[4:8] = long(0x00fc0020)
    tos[8:12] = long(0x00fc0000)
    tos[0x20:0x20 + len(code)] = code
    tos[0x100:0x100 + len(routine())] = routine()
    assert 0x20 + len(code) <= 0x100
    return bytes(tos)


def blank_disk() -> bytes:
    disk = bytearray(80 * 2 * 9 * 512)
    boot = bytearray(512)
    boot[11:19] = struct.pack('<HBHBH', 512, 2, 1, 2, 112)
    boot[19:21] = struct.pack('<H', 1440)
    boot[22:28] = struct.pack('<HHH', 5, 9, 2)
    disk[:512] = boot
    return bytes(disk)


def main() -> int:
    os.environ.setdefault('RETRO_RECOMP_TOOLCHAIN', 'llvm')
    from retrorecomp import atarist_conversion as c
    from retrorecomp.console16 import dependencies16
    from retrorecomp.toolchain import suffix as toolchain_suffix
    stamp = c.sdk_stamp()
    base = ROOT / '.build/atarist' / (('win' + toolchain_suffix()) if os.name == 'nt' else 'linux') / stamp[:12]
    base.mkdir(parents=True, exist_ok=True)
    dependencies16('md', print)
    tree, hatari_build = c.machine_core(base.parent, print)
    reference = c.reference_build(base, tree, hatari_build, stamp, print)
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    tos, disk = WORK / 'tos.img', WORK / 'disk1.st'
    tos.write_bytes(authored_tos())
    disk.write_bytes(blank_disk())
    events = c.write_events(WORK / 'none.txt', [])
    _, lengths = c.decoder_lengths(WORK / 'native')
    table = c.opcode_map(reference, WORK / 'map', [disk], tos)
    frames = 60
    ref = c.replay(reference, WORK / 'reference', frames, events, disks=[disk], tos=tos, observe=True, lengths=lengths)
    samples = c.read_observations(WORK / 'reference' / 'observations.txt')
    patch_pc = ROUTINE_RAM + 0x12
    seen = sorted(words_ for pc, words_ in samples if pc == patch_pc)
    c.generate(WORK / 'native', sorted(samples), table, hatari_build)
    player = c.cmake_build(WORK / 'build', tree, hatari_build, generated=WORK / 'native', stamp=stamp)
    nat = c.replay(player, WORK / 'native-run', frames, events, disks=[disk], tos=tos)
    # the native run is the player without --reference-cpu: replay() adds it with a TOS, so run it directly
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    folder = WORK / 'native-run'
    folder.mkdir(exist_ok=True)
    done = subprocess.run([str(player), '--headless', '--frames', str(frames), '--tos', str(tos), '--disk', str(disk), '--machine', 'st',
                           '--memory', '1024', '--input-events', str(events), '--trace', str(folder / 'trace.tsv'),
                           '--report', str(folder / 'result.json')], cwd=folder, env=env, capture_output=True, text=True, timeout=600)
    if done.returncode:
        raise SystemExit(f'the native player failed: {done.stderr[-400:]}')
    import json
    nat = json.loads((folder / 'result.json').read_text(encoding='utf-8'))

    def final_d0(trace: Path) -> int:
        rows = [line.split('\t') for line in trace.read_text(encoding='ascii').splitlines()]
        return int(rows[-1][rows[0].index('D0')], 16)

    ref_d0, nat_d0 = final_d0(WORK / 'reference' / 'trace.tsv'), final_d0(folder / 'trace.tsv')
    same_trace = (WORK / 'reference' / 'trace.tsv').read_bytes() == (folder / 'trace.tsv').read_bytes()
    print(f'observed at patch ({patch_pc:#x}): {seen}')
    print(f'D0 after the loop: reference {ref_d0}, native steps {nat_d0}, expected {EXPECTED_D0}')
    print(f'native instructions {nat["native"]}, interpreted {nat["interpreted"]}; trace of every frame equal: {same_trace}')
    ok = ref_d0 == EXPECTED_D0 and nat_d0 == EXPECTED_D0 and same_trace and nat['native'] > 0
    # both words were seen at `patch`: the old opcode was latched while memory already held the new one, so the observation holds the
    # new word and its step is the new handler: the case a memory-only guard gets wrong
    ok = ok and any(w.startswith('5440') for w in seen)
    print('OK' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
