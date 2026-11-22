"""ROM-free check that nothing the interpreter ran from RAM is dropped on the banked Z80 chain (native/z80_learned_set.h,
native/z80_chain_glue.inc, native/banked_emitter.inc's banked_learn, retrorecomp/z80_chain_build.py's learn_passes).

Until this check the chain kept at most 4,096 windows twice over: a headless run learned at most 4,096 (`learned[4096]`) and the
emitter read at most the first 4,096 lines of `native.patterns`, which `learn_passes` writes SORTED, so past 4,096 words the subset
that was translated shifted from pass to pass (Carrier Command on the CPC: 3.96M, 0.53M, 3.43M interpreted steps). It builds, from an
AUTHORED cartridge (no ROM), the SG-1000's machine (the chain is the same for every machine) and proves:

  (a) the set of windows alone (native/z80_learned_set_checks.c): 200,000 distinct windows kept, each once, in first-seen order;
  (b) the emitter translates every window of `native.patterns`, far past 4,096: 6,000 distinct windows give 6,000 windows loaded and as
      many new native bodies in banked-coverage.json (nothing left out), and a table that has to grow does not change a byte of what is
      written for fewer windows (checked in the A/B of the change, tests/test_z80_learn_cap.py keeps the anchors);
  (c) the whole loop, with `learn_passes`: a program that writes and runs 5,120 different routines from RAM learns all 5,120 windows in
      the first pass and runs on the interpreter for none of them in the second (the passes shrink to 0), where a 4,096 bound
      leaves 1,024 of them for a third.

What it does not prove: anything about a real cartridge; the machine's own chips (the other self-tests). Everything is written under
.build/z80-learn-cap (default); no window, every run bounded.

    python -B tools/z80_learn_cap_selftest.py [--work DIR]
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
sys.path.insert(0, str(ROOT / 'tools'))

ROUTINES = 0x1400          # 5,120 different routines, each written to RAM and run once
FRAMES = 60


def authored_cartridge() -> bytes:
    """A program that, 5,120 times, writes `LD HL,nn; RET` to C100h with a different `nn` and calls it: 5,120 different windows of code
    run from RAM, none of them in the cartridge."""
    image = bytearray(b'\xFF' * 0x2000)
    image[0x0000:0x0007] = bytes([0xF3, 0x31, 0x00, 0xC4, 0xC3, 0x00, 0x01])                  # DI; LD SP,C400h; JP 0100h
    program = bytes([
        0x11, 0x00, 0x00,          # LD DE,0000h
        0x21, 0x00, 0xC1,          # again: LD HL,C100h
        0x36, 0x21,                # LD (HL),21h        LD HL,nn
        0x23, 0x73,                # INC HL; LD (HL),E
        0x23, 0x72,                # INC HL; LD (HL),D
        0x23, 0x36, 0xC9,          # INC HL; LD (HL),C9h   RET
        0xCD, 0x00, 0xC1,          # CALL C100h
        0x13, 0x7A,                # INC DE; LD A,D
        0xFE, ROUTINES >> 8,       # CP 14h
        0x20, 0xEB,                # JR NZ,again
        0x76, 0x18, 0xFD,          # HALT; JR HALT
    ])
    image[0x0100:0x0100 + len(program)] = program
    return bytes(image)


def stage(work: Path) -> None:
    from retrorecomp import sg1000_build, z80_chain_build
    from retrorecomp.paths import ASSETS
    native = ASSETS / 'native'
    z80_chain_build.stage_files(work, ((native / 'sg1000_machine', sg1000_build.MACHINE_FILES),
                                       *((native / folder, (*sources, *files)) for folder, sources, files in sg1000_build.SHARED_MODULES),
                                       (native, sg1000_build.CHAIN_FILES)))


def generate(work: Path, cartridge: bytes) -> None:
    from retrorecomp import sg1000_build, z80_chain_build
    from retrorecomp.systems.sg1000 import SG1000_MACHINE
    z80_chain_build.generate_bodies(work, SG1000_MACHINE, SG1000_MACHINE.regions.image(cartridge), (), sg1000_build.GAME_TOML, lambda m: None,
                                    loop_name='sg1000_banked_loop.inc', accept='sg1000_reference_accept', error=RuntimeError)
    stage(work)


def build_check(work: Path) -> Path:
    from retrorecomp import sg1000_build, z80_chain_build
    return z80_chain_build.build_project(work, ('sg1000_check',), sg1000_build.project_cmake(False, True))['sg1000_check']


def coverage(work: Path) -> dict:
    return json.loads((work / 'generated' / 'banked-coverage.json').read_text(encoding='utf-8'))


class Results:
    def __init__(self) -> None:
        self.checks, self.failures = 0, []

    def check(self, condition: bool, text: str, detail: str = '') -> bool:
        self.checks += 1
        print(('  ok    ' if condition else '  FAIL  ') + text + (f'  [{detail}]' if detail and not condition else ''))
        if not condition:
            self.failures.append(text)
        return condition


def prove_set(res: Results, folder: Path) -> None:
    print('(a) the set of learned windows has no bound')
    import z80_costs_selftest as costs_check
    exe = folder / ('z80_learned_set_checks.exe' if os.name == 'nt' else 'z80_learned_set_checks')
    costs_check._compile([ROOT / 'native' / 'z80_learned_set_checks.c'], ROOT / 'native', exe)
    ran = subprocess.run([str(exe)], capture_output=True, encoding='utf-8', errors='replace', timeout=120)
    res.check(ran.returncode == 0, 'native/z80_learned_set_checks.c: ' + ran.stdout.strip().splitlines()[-1] if ran.stdout.strip() else 'ran', ran.stdout[-300:])


def prove_emitter(res: Results, work: Path) -> None:
    print('(b) the emitter translates every window of native.patterns')
    cartridge = authored_cartridge()
    generate(work, cartridge)
    rom_bodies = coverage(work)['unique_native_bodies']
    for windows in (3000, 6000):
        words = ''.join(f'21{(0x2000 + i) & 255:02X}{(0x2000 + i) >> 8:02X}00\n' for i in range(windows))      # LD HL,nn: one body each
        (work / 'native.patterns').write_text(words, encoding='utf-8', newline='\n')
        generate(work, cartridge)
        report = coverage(work)
        res.check(report['profile_windows_loaded'] == windows, f'{windows} windows in the file: {report["profile_windows_loaded"]} loaded')
        res.check(report['profile_added_native_bodies'] == windows and report['unique_native_bodies'] == rom_bodies + windows,
                  f'{windows} windows in the file: {report["profile_added_native_bodies"]} new native bodies (the ROM\'s own: {rom_bodies})',
                  str(report))
    (work / 'native.patterns').unlink()


def prove_loop(res: Results, work: Path) -> None:
    print('(c) the loop: every window the interpreter ran is learned, and the passes shrink to nothing')
    from retrorecomp import z80_chain_build
    cartridge = authored_cartridge()
    work.mkdir(parents=True, exist_ok=True)
    cart_file = work / 'authored.sg'
    cart_file.write_bytes(cartridge)
    (work / 'native.patterns').unlink(missing_ok=True)

    def run_check(check: Path, args: list, learned: Path) -> int:
        report = work / 'learn-report.json'
        ran = subprocess.run([str(check), *args, '--report', str(report)], capture_output=True, timeout=600)
        if ran.returncode:
            raise RuntimeError(f'{check.name} failed: {ran.stderr.decode(errors="replace")[-300:]}')
        return int(json.loads(report.read_text(encoding='utf-8'))['fallback_steps'])

    check, counts = z80_chain_build.learn_passes(
        work, [['--frames', str(FRAMES), '--cart', str(cart_file)]], generate=lambda: generate(work, cartridge),
        build_check=lambda: build_check(work), run_check=run_check, passes=4)
    words = len((work / 'native.patterns').read_text(encoding='utf-8').split())
    res.check(words >= ROUTINES, f'every window is learned in the first pass ({words} words, at least {ROUTINES})')
    res.check(len(counts) >= 2 and counts[0] >= ROUTINES and counts[-1] == 0, f'the interpreter runs for none of them in the end (steps per pass: {counts})')
    res.check(all(a > b for a, b in zip(counts, counts[1:])), f'the passes shrink at every step (monotonically: {counts})')
    report = coverage(work)
    res.check(report['profile_windows_loaded'] == words and report['profile_added_native_bodies'] >= ROUTINES,
              f'every learned window became a native body ({report["profile_added_native_bodies"]} new bodies for {report["profile_windows_loaded"]} windows)')


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    os.environ.setdefault('RETRO_RECOMP_TOOLCHAIN', 'llvm')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'z80-learn-cap')
    parser.add_argument('--skip-set', action='store_true', help='skip (a): to run (b) and (c) on a tree that has no native/z80_learned_set.h (the old chain, to see them fail)')
    args = parser.parse_args()
    base = args.work.resolve()
    base.mkdir(parents=True, exist_ok=True)
    res = Results()
    if not args.skip_set:
        prove_set(res, base)
    prove_emitter(res, base / 'emitter')
    prove_loop(res, base / 'loop')
    print(f'{res.checks} checks, {len(res.failures)} failed')
    for failure in res.failures:
        print('FAILED:', failure)
    return 1 if res.failures else 0


if __name__ == '__main__':
    sys.exit(main())
