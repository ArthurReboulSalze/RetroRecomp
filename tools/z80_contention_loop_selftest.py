"""ROM-free gate for the contention lines of the banked Z80 chain's STEP LOOP (retrorecomp/z80_chain.py, `Z80Machine.contention`).

tools/z80_contention_selftest.py compiles and runs every instruction's body against the reference CPU. What it cannot reach are the lines
that the step loop and the reference's interrupt code carry: the delay of a HALT cycle, of the acceptance of /INT in mode 1 and in mode 2
(the vector read at I:FFh), of the acceptance of /NMI, and the reference's epoch for the counted fallback. This gate compiles them.

It builds, from an AUTHORED cartridge (no ROM, nothing of a commercial game) and the SG-1000's machine with `contention=True`
(dataclasses.replace: no machine of the converter turns contention on), the generated bodies, the step loop rendered for it, the
reference runner and the headless native check, under an authored contention rule (native/z80_contention_gate.c, not any machine's), and
proves:

  (a) two programs, one that runs HALT, /INT in mode 1 and /NMI (the Pause button) and one in mode 2 (I = 03h, the vector at 03FFh):
      the native check equals the reference runner on every common field of the report (the T-state count, the registers, the
      counters) and on the per-frame rows, byte for byte; the programs really exercise what they claim (halted steps, /INT and
      /NMI taken, and a count of T-states that differs from the same programs without contention);
  (b) the same with a reference built WITHOUT contention against the check WITH it: they must differ (the delays are visible);
  (c) positive controls on the loop, one mutation of its text at a time (the HALT delay, the NMI delay, the mode-1 delay, the mode-2
      delay taken as the mode-1 walk): each mutated check must differ from the reference, and a mutation of a line the program does not
      reach (mode 1 in the mode-2 program) must not.

What it does not prove: that any real machine's rule is right (the Spectrum's is checked with its own evidence), nothing about a real
cartridge, a real display or a console's timing; and that the loop is correct on every state (the instructions' bodies are the other
self-test's). The five measures stay separate.

    python -B tools/z80_contention_loop_selftest.py [--work DIR]

Everything is written under .build/z80-contention-loop (default); no window, every run bounded.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

import sg1000_player_selftest as sg  # noqa: E402  (the authored cartridge, the route and the headless runs)

FRAMES = 840
# The self-test's route with more presses of Pause (each one an /NMI), at frames that do not repeat a phase of the frame: the authored rule
# delays an acceptance only for some T-states, so one press may see none.
ROUTE = sorted(sg.ROUTE + [f'{frame}:pause' for frame in (440, 463, 487, 521, 553, 591, 618, 655, 689, 727, 779, 803)],
               key=lambda event: int(event.split(':')[0]))
# The lines of the step loop that the mutations remove or change: each must occur exactly once in the rendered loop, and a change of the
# rendered text that moves one makes this gate fail (tests/test_z80_contention_loop.py checks the anchors without a compiler).
LOOP_NAME = 'sg1000_banked_loop.inc'
MUTATIONS = {
    'halt': ('rr_timed_special_delay(RR_TIMED_HALT, &rr_hs, g_z80.cyc)', '0'),
    'nmi': ('rr_timed_special_delay(RR_TIMED_NMI, &rr_ns, g_z80.cyc)', '0'),
    'im1': ('rr_timed_special_delay(g_z80.im == 2 ? RR_TIMED_IM2 : RR_TIMED_IM1, &rr_is, g_z80.cyc)',
            '(g_z80.im == 2 ? rr_timed_special_delay(RR_TIMED_IM2, &rr_is, g_z80.cyc) : 0)'),
    'im2': ('rr_timed_special_delay(g_z80.im == 2 ? RR_TIMED_IM2 : RR_TIMED_IM1, &rr_is, g_z80.cyc)',
            'rr_timed_special_delay(RR_TIMED_IM1, &rr_is, g_z80.cyc)'),
}
# What each program reaches: the mutations that must change it, and the one that must not (the mode it does not run).
EXPECT = {'mode1': {'halt': True, 'nmi': True, 'im1': True, 'im2': False},
          'mode2': {'halt': True, 'nmi': True, 'im1': False, 'im2': True}}


def contention_machine(on: bool = True):
    from retrorecomp.systems.sg1000 import SG1000_MACHINE
    # Its own generator build (`generator_tag`): the converter's SG-1000 generator is never rebuilt with the contention text.
    return dataclasses.replace(SG1000_MACHINE, contention=True, generator_tag='-sgc') if on else SG1000_MACHINE


def mode1_cartridge() -> bytes:
    """The self-test's authored SG-1000 cartridge: IM 1, `EI; HALT`, the /INT handler at 0200h, the Pause handler (/NMI) at 0066h."""
    return sg.authored_cartridge()


def mode2_cartridge() -> bytes:
    """The same program in interrupt mode 2: the entry jumps to a stub at 0300h that loads I with 03h and goes on; `IM 1` becomes `IM 2`;
    the vector at 03FFh (I:FFh, the chain's fixed data byte) points to the /INT handler at 0200h."""
    image = bytearray(mode1_cartridge())
    assert image[0:7] == bytes([0xF3, 0x31, 0x00, 0xC4, 0xC3, 0x00, 0x01]) and image[0x100:0x102] == bytes([0xED, 0x56])
    image[0x0004:0x0007] = bytes([0xC3, 0x00, 0x03])                       # JP 0300h
    image[0x0100:0x0102] = bytes([0xED, 0x5E])                             # IM 2
    image[0x0300:0x0307] = bytes([0x3E, 0x03, 0xED, 0x47, 0xC3, 0x00, 0x01])   # LD A,03h; LD I,A; JP 0100h
    image[0x03FF:0x0401] = bytes([0x00, 0x02])                             # the vector at I:FFh: 0200h
    return bytes(image)


def rom_table(cartridge: bytes) -> str:
    """native/z80_contention_gate.c's `rr_gate_rom`: the cartridge as the machine sees it, 0000h-BFFFh (the 8 KiB regions mirrored)."""
    from retrorecomp.systems.sg1000 import SG1000_MACHINE
    padded = SG1000_MACHINE.regions.image(cartridge)
    table = (padded * (0xC000 // len(padded) + 1))[:0xC000]
    rows = ',\n'.join(','.join(str(b) for b in table[i:i + 32]) for i in range(0, len(table), 32))
    return f'/* Written by tools/z80_contention_loop_selftest.py. */\nconst unsigned char rr_gate_rom[0xC000] = {{\n{rows}\n}};\n'


def project(contention: bool) -> str:
    from retrorecomp import sg1000_build, z80_chain_build
    sources = (*sg1000_build.MACHINE_SOURCES, *sg1000_build.SHARED_SOURCES,
               *(('banked_timed.c', 'z80_contention_gate.c', 'z80_contention_gate_rom.c') if contention else ()))
    return z80_chain_build.chain_project_cmake('sg1000', 'ContentionLoop', reference_main='sg1000_reference_main.c',
                                               native_main='sg1000_native_main.c', machine_sources=sources, bodies=True)


def prepare(work: Path, cartridge: bytes, contention: bool) -> None:
    """The generated bodies, the step loop and the reference copy for the machine (with or without contention), the staged sources and the
    authored rule."""
    from retrorecomp import sg1000_build, z80_chain_build
    from retrorecomp.paths import ASSETS
    work.mkdir(parents=True, exist_ok=True)
    machine = contention_machine(contention)
    z80_chain_build.generate_bodies(work, machine, machine.regions.image(cartridge), (), sg1000_build.GAME_TOML, lambda message: None,
                                    loop_name=LOOP_NAME, accept='sg1000_reference_accept', error=RuntimeError)
    native = ASSETS / 'native'
    z80_chain_build.stage_files(work, ((native / 'sg1000_machine', sg1000_build.MACHINE_FILES),
                                       *((native / folder, (*sources, *files)) for folder, sources, files in sg1000_build.SHARED_MODULES),
                                       (native, sg1000_build.CHAIN_FILES)))
    if contention:
        z80_chain_build.write_if_changed(work / 'z80_contention_gate.c', (native / 'z80_contention_gate.c').read_bytes())
        z80_chain_build.write_if_changed(work / 'z80_contention_gate_rom.c', rom_table(cartridge).encode('utf-8'))


def build(work: Path, contention: bool, targets: tuple[str, ...]) -> dict[str, Path]:
    from retrorecomp import z80_chain_build
    return z80_chain_build.build_project(work, targets, project(contention))


def mutate(work: Path, name: str, destination: Path) -> None:
    """A copy of `work` (sources only) whose step loop has one mutation."""
    old, new = MUTATIONS[name]
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(work, destination, ignore=shutil.ignore_patterns('build', '*.log'))
    loop = destination / LOOP_NAME
    text = loop.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise RuntimeError(f'the step loop no longer holds the line the {name!r} mutation removes exactly once: this gate must follow it')
    loop.write_text(text.replace(old, new), encoding='utf-8', newline='\n')


def comparison(check: dict, reference: dict) -> tuple[bool, dict]:
    """Whether a native check's run equals the reference's on every common field and on the per-frame rows (`sg.prove_equal_runs`'s rule)."""
    c, r = check['json'], reference['json']
    different = {key: (c.get(key), r.get(key)) for key in sorted(set(c) & set(r)) if key not in ('engine', *sg.NATIVE_ONLY) and c[key] != r[key]}
    same_rows = check['rows'].read_bytes() == reference['rows'].read_bytes()
    return (not different and same_rows), {'fields': different, 'rows_equal': same_rows}


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    os.environ.setdefault('RETRO_RECOMP_TOOLCHAIN', 'llvm')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'z80-contention-loop')
    args = parser.parse_args()
    base = args.work.resolve()
    res = sg.Results()
    for mode, cartridge in (('mode1', mode1_cartridge()), ('mode2', mode2_cartridge())):
        print(f'{mode}: {"IM 1" if mode == "mode1" else "IM 2, the vector at I:FFh"}, HALT and the Pause button (/NMI)')
        work, plain = base / mode, base / (mode + '-plain')
        runs = base / (mode + '-runs')
        runs.mkdir(parents=True, exist_ok=True)
        cart_file = runs / 'authored.sg'
        cart_file.write_bytes(cartridge)
        prepare(work, cartridge, True)
        exes = build(work, True, ('sg1000_reference', 'sg1000_check'))
        prepare(plain, cartridge, False)
        plain_exes = build(plain, False, ('sg1000_reference', 'sg1000_check'))

        def run(exe: Path, name: str) -> dict:
            return sg.headless(exe, runs, name, FRAMES, ['--cart', cart_file], ROUTE, game=False)

        check, reference = run(exes['sg1000_check'], 'check'), run(exes['sg1000_reference'], 'reference')
        plain_check, plain_reference = run(plain_exes['sg1000_check'], 'plain-check'), run(plain_exes['sg1000_reference'], 'plain-reference')
        ok = all(r['code'] == 0 and r['json'] for r in (check, reference, plain_check, plain_reference))
        res.check(ok, f'{mode}: the four programs ran to the end', str([r['code'] for r in (check, reference, plain_check, plain_reference)]))
        if not ok:
            continue
        c = check['json']
        # (a) the loop's contention lines against the reference's, compiled.
        same, detail = comparison(check, reference)
        res.check(same, f'{mode}: the check with contention equals the reference with it on every common field and every frame row', str(detail)[:400])
        res.check(c['halt_steps'] > 0 and c['interrupts'] > 20 and c['nmi'] >= 10,
                  f'{mode}: the program reaches what it claims (halted steps {c["halt_steps"]}, /INT {c["interrupts"]}, /NMI {c["nmi"]})')
        # The report's `cycles` is the machine's clock at the end of the last frame (the frames are the hardware's), so the delays show in
        # where the instructions land: the halted steps (a HALT cycle that is held off is longer: fewer of them) and the frame rows.
        res.check(c['halt_steps'] != plain_check['json']['halt_steps'] and check['rows'].read_bytes() != plain_check['rows'].read_bytes(),
                  f'{mode}: the delays are in the run ({c["halt_steps"]} halted steps with contention, {plain_check["json"]["halt_steps"]} without; the rows differ)')
        same_plain, _ = comparison(plain_check, plain_reference)
        res.check(same_plain, f'{mode}: with no contention on either side the check and the reference agree (the loop is the old text)')
        # (b) a reference without contention must differ from the check with it.
        mismatch, _ = comparison(check, plain_reference)
        res.check(not mismatch, f'{mode}: positive control: the check with contention against a reference without it differ')
        # (c) one mutation of the loop at a time.
        for name, must_differ in EXPECT[mode].items():
            mutant = base / f'{mode}-mut-{name}'
            mutate(work, name, mutant)
            exe = build(mutant, True, ('sg1000_check',))['sg1000_check']
            got = run(exe, f'mut-{name}')
            if not (got['code'] == 0 and got['json']):
                res.check(False, f'{mode}: the {name} mutation ran', str(got['code']))
                continue
            equal, detail = comparison(got, reference)
            if must_differ:
                res.check(not equal, f'{mode}: positive control: without the {name} delay the loop differs from the reference',
                          'it did not differ: the program does not reach this line, or the check cannot see it')
            else:
                res.check(equal, f'{mode}: the {name} line is not reached by this program: its mutation changes nothing', str(detail)[:300])
    print(f'{res.checks} checks, {len(res.failures)} failed')
    for failure in res.failures:
        print('FAILED:', failure)
    return 1 if res.failures else 0


if __name__ == '__main__':
    sys.exit(main())
