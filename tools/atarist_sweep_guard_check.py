"""The guard of a swept instruction (a guard check of the Atari ST's sweep over images of memory).

    python -B tools/atarist_sweep_guard_check.py        (needs a compiler, no ROM, no TOS, no game)

A sweep reaches code the conversion's routes never ran, from an image of the memory at the routes' end. What an image holds is not proof that the game will still have it there: a
program may rewrite the block before it jumps in. A swept instruction has no more proof than that, so it carries the guard of every native instruction: its routine runs only when the
opcode the 68000 has latched is the one it was compiled for, and its handler (Hatari's own) reads the extension words on the bus when it runs.

Authored program (no TOS, no disk of anyone), copied to RAM at $10000: `CLR.L D0`, a long delay (`SUBQ.L #1,D3`, `BEQ.W after`, `BRA.S loop`) that the conversion's run of 60 frames never
leaves, then, in `after`, two words copied from the TOS ROM (the variant: they are data, so every variant is the same code) over the block Y at $10200, `ADDI.W #1,D0; BRA.S *`, and `JMP Y`.
The conversion observes the delay only: `after` and Y are reached by the sweep, from the observed (never taken) `BEQ.W`, over the image taken at frame 60. Then the program runs for 150
frames with the delay over, three ways, native and on the interpreter (--reference-cpu), the traces of every frame byte-identical:

  1. Y unchanged: the swept routines run (native_swept above 0: the positive control), D0 = 1.
  2. another opcode at Y (`SUBI.W #1,D0`): the swept routine of Y's first instruction never runs, the interpreter does (the native count is one less, the interpreted one more), D0 = $FFFF.
  3. the same opcode, another extension word (`ADDI.W #2,D0`): the routine runs and the result uses the new word, D0 = 2.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WORK = ROOT / '.build' / 'atarist-sweep-guard-check'
TOS_BYTES = 196608
ROUTINE_RAM, ROUTINE_ROM, PATCH_ROM = 0x10000, 0xfc0100, 0xfc0400
BLOCK = ROUTINE_RAM + 0x200
DELAY = 500000                   # iterations of the delay: about 94 frames (30 cycles each)
OBSERVED_FRAMES, RUN_FRAMES = 60, 150
VARIANTS = [('1 unchanged', 0x0640, 0x0001, 1), ('2 another opcode', 0x0440, 0x0001, 0xffff), ('3 another extension word', 0x0640, 0x0002, 2)]


def words(*values: int) -> bytes:
    return b''.join(struct.pack('>H', v & 0xffff) for v in values)


def long(value: int) -> bytes:
    return struct.pack('>I', value & 0xffffffff)


def routine() -> bytes:
    code = bytearray(0x206)
    def put(at: int, data: bytes) -> None:
        code[at:at + len(data)] = data
    put(0x00, words(0x4280))                                           # CLR.L D0
    put(0x02, words(0x263c) + long(DELAY))                             # MOVE.L #DELAY,D3
    put(0x08, words(0x5383))                                           # loop: SUBQ.L #1,D3
    put(0x0a, words(0x6700, 0x0014))                                   # BEQ.W after (never taken while the conversion observes)
    put(0x0e, words(0x60f8))                                           # BRA.S loop
    put(0x20, words(0x33f9) + long(PATCH_ROM) + long(BLOCK))           # after: MOVE.W (patch1).L,(Y).L
    put(0x2a, words(0x33f9) + long(PATCH_ROM + 2) + long(BLOCK + 2))   # MOVE.W (patch2).L,(Y+2).L
    put(0x34, words(0x4ef9) + long(BLOCK))                             # JMP Y
    put(0x200, words(0x0640, 0x0001, 0x60fe))                          # Y: ADDI.W #1,D0 ; BRA.S *
    return bytes(code)


def authored_tos(first: int, second: int) -> bytes:
    program = routine()
    code = words(0x13fc, 0x0005) + long(0x00ff8001)                    # MOVE.B #5,$FF8001.L (memory configuration)
    code += words(0x46fc, 0x2700)                                      # MOVE #$2700,SR
    code += words(0x207c) + long(ROUTINE_ROM)                          # MOVEA.L #rom,A0
    code += words(0x227c) + long(ROUTINE_RAM)                          # MOVEA.L #ram,A1
    code += words(0x3e3c, len(program) // 2 - 1)                       # MOVE.W #count-1,D7
    code += words(0x32d8, 0x51cf, 0xfffc)                              # copy: MOVE.W (A0)+,(A1)+ ; DBF D7,copy
    code += words(0x4ef9) + long(ROUTINE_RAM)                          # JMP ram
    tos = bytearray(TOS_BYTES)
    tos[0:4] = bytes((0x60, 0x1e, 0x01, 0x04))
    tos[4:8] = long(0x00fc0020)
    tos[8:12] = long(0x00fc0000)
    tos[0x20:0x20 + len(code)] = code
    tos[0x100:0x100 + len(program)] = program
    tos[0x400:0x404] = words(first, second)
    assert 0x20 + len(code) <= 0x100 and 0x100 + len(program) <= 0x400
    return bytes(tos)


def blank_disk() -> bytes:
    disk = bytearray(80 * 2 * 9 * 512)
    boot = bytearray(512)
    boot[11:19] = struct.pack('<HBHBH', 512, 2, 1, 2, 112)
    boot[19:21] = struct.pack('<H', 1440)
    boot[22:28] = struct.pack('<HHH', 5, 9, 2)
    disk[:512] = boot
    return bytes(disk)


def final_d0(trace: Path) -> int:
    rows = [line.split('\t') for line in trace.read_text(encoding='ascii').splitlines()]
    return int(rows[-1][rows[0].index('D0')], 16)


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
    disk = WORK / 'disk1.st'
    disk.write_bytes(blank_disk())
    tos_files = []
    for name, first, second, _ in VARIANTS:
        tos_files.append(WORK / f'tos-{name[0]}.img')
        tos_files[-1].write_bytes(authored_tos(first, second))
    events = c.write_events(WORK / 'none.txt', [])
    _, lengths = c.decoder_lengths(WORK / 'native')
    table = c.opcode_map(reference, WORK / 'map', [disk], tos_files[0])
    # The conversion's own step: a fresh reference run of 60 frames observes, and leaves the image of the memory at its last frame.
    c.replay(reference, WORK / 'reference', OBSERVED_FRAMES, events, disks=[disk], tos=tos_files[0], observe=True, lengths=lengths,
             extra=['--ram-dump-at', OBSERVED_FRAMES, '--ram-dump', WORK / 'reference' / c.MEMORY_IMAGE])
    samples = c.read_observations(WORK / 'reference' / 'observations.txt')
    images = c.sweep_images([WORK / 'reference'], tos_files[0])
    if len(images) != 1 or (WORK / 'reference' / c.MEMORY_IMAGE).exists():
        raise SystemExit('the reference run left no image of the memory, or the file was kept')
    observed_pcs = {pc for pc, _ in samples}
    never_run = [pc for pc in (ROUTINE_RAM + 0x20, ROUTINE_RAM + 0x34, BLOCK, BLOCK + 4) if pc not in observed_pcs]
    generation = c.generate(WORK / 'native', sorted(samples), table, hatari_build, lengths=lengths, images=images)
    print(f"observed {len(samples)} instructions; the sweep reached {generation['swept_instructions']} more: {generation['sweep']}")
    player = c.cmake_build(WORK / 'build', tree, hatari_build, generated=WORK / 'native', stamp=stamp)
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    results = []
    for (name, _, _, expected), tos in zip(VARIANTS, tos_files):
        interpreted = c.replay(player, WORK / f'interpreted-{name[0]}', RUN_FRAMES, events, disks=[disk], tos=tos)          # --reference-cpu: every instruction on the interpreter
        folder = WORK / f'native-{name[0]}'
        folder.mkdir()
        done = subprocess.run([str(player), '--headless', '--frames', str(RUN_FRAMES), '--tos', str(tos), '--disk', str(disk), '--machine', 'st', '--memory', '1024',
                               '--input-events', str(events), '--trace', str(folder / 'trace.tsv'), '--report', str(folder / 'result.json')],
                              cwd=folder, env=env, capture_output=True, text=True, timeout=600)
        if done.returncode:
            raise SystemExit(f'the native player failed: {done.stderr[-400:]}')
        native = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
        same = (WORK / f'interpreted-{name[0]}' / 'trace.tsv').read_bytes() == (folder / 'trace.tsv').read_bytes()
        d0 = final_d0(folder / 'trace.tsv')
        results.append((name, expected, d0, final_d0(WORK / f'interpreted-{name[0]}' / 'trace.tsv'), same, native, interpreted))
        print(f"variant {name}: D0 native {d0:#x}, interpreted {results[-1][3]:#x}, expected {expected:#x}; trace of every frame equal: {same}; "
              f"native {native['native']} of which swept {native['native_swept']}, interpreted {native['interpreted']}")
    (_, _, _, _, _, one, _), (_, _, _, _, _, two, _), (_, _, _, _, _, three, _) = results
    checks = {
        'the swept code was not observed (the sweep, not a run, reached it)': len(never_run) == 4 and generation['swept_instructions'] > 0,
        'every variant: native and interpreted traces equal, and the result is the new code\'s': all(same and d0 == expected and ref == expected for _, expected, d0, ref, same, _, _ in results),
        '1 (positive control): the swept routines run': one['native_swept'] > 0,
        '2: the swept routine of the rewritten opcode never runs, the interpreter does': two['native_swept'] == one['native_swept'] - 1 and two['interpreted'] == one['interpreted'] + 1,
        '3: the same opcode with another extension word still runs its routine': three['native_swept'] == one['native_swept'] and three['interpreted'] == one['interpreted'],
    }
    for text, passed in checks.items():
        print(('ok      ' if passed else 'FAILED  ') + text)
    ok = all(checks.values())
    print('OK' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
