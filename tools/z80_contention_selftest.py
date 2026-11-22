"""ROM-free check of contention on the banked Z80 chain (retrorecomp/z80_chain.py, `Z80Machine.contention`).

The emitter writes a body for every encoding of the Z80 (native/z80_costs_emit.c, with the generator patched for a machine with
contention, or without), and native/z80_contention_checks.c runs each body against the reference CPU of the counted fallback
(cpu.prepare_reference) from the same states under an authored rule (not any real machine's), comparing the T-states and the PC.
Four runs, never a game:

1. contention on both sides: every encoding must agree;
2. bodies with contention, reference without: they must disagree (a positive control: the check sees the delays);
3. neither side: every encoding must agree;
4. the delay of every case (the bodies with contention less the bodies without) must equal retrorecomp/z80_timed.delay, the
   Python walk of the same table, on the same registers, memory and T-state: the bodies capture the right start state and
   T-state and add the right extra (taken when the plain count is above the base's).

The acceptances and the HALT cycle are written by the step loop and the reference's interrupt code, whose texts
tests/test_z80_timed.py checks. Nothing is written outside .build/z80-contention-selftest.
"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

import z80_costs_selftest as costs_check  # noqa: E402

CASE_STATES = 8


def machine(contention: bool):
    from retrorecomp.z80_chain import SEGA_MAPPER, Z80Machine
    return Z80Machine('contention-check', SEGA_MAPPER.regions, contention=contention)


def build_check(bodies: Path, reference_timed: bool, bodies_timed: bool, folder: Path) -> Path:
    from retrorecomp.cpu import prepare_cpu_headers, prepare_reference
    from retrorecomp.z80_timed import render_header, render_source
    engine = ROOT / '.deps' / 'smsggrecomp'
    folder.mkdir(parents=True)
    prepare_cpu_headers(folder, engine)
    prepare_reference(folder, engine, contention=reference_timed)
    (folder / 'banked_timed.h').write_text(render_header(), encoding='utf-8', newline='\n')
    (folder / 'banked_timed.c').write_text(render_source(), encoding='utf-8', newline='\n')
    shutil.copyfile(bodies, folder / 'z80_costs_bodies.inc')
    shutil.copyfile(ROOT / 'native' / 'banked_reference_state.inc', folder / 'banked_reference_state.inc')
    exe = folder / ('z80_contention_checks.exe' if costs_check.os.name == 'nt' else 'z80_contention_checks')
    defines = ['-DSMSRECOMP_BANKED_AOT'] + (['-DRR_CHECK_TIMED'] if bodies_timed else []) + \
        (['-DRR_REFERENCE_TIMED'] if reference_timed else [])
    costs_check._compile([ROOT / 'native' / 'z80_contention_checks.c', folder / 'banked_timed.c'], folder, exe, defines)
    return exe


def run(exe: Path, *args) -> tuple[int, str]:
    ran = subprocess.run([str(exe), *args], capture_output=True, encoding='utf-8', errors='replace', timeout=300,
                         creationflags=costs_check.FLAGS)
    return ran.returncode, ran.stdout


def _encoding(raw: bytes):
    """The group and opcode of a case's bytes (z80_chain.COST_GROUPS), or None for a fragment."""
    if raw[0] in (0xDD, 0xFD):
        if raw[1] == 0xCB:
            return ('ddcb' if raw[0] == 0xDD else 'fdcb'), raw[3]
        if raw[1] in (0xDD, 0xFD):
            return None
        return ('dd' if raw[0] == 0xDD else 'fd'), raw[1]
    if raw[0] in (0xCB, 0xED):
        return ('cb' if raw[0] == 0xCB else 'ed'), raw[1]
    return '', raw[0]


def model_check(timed_dump: str, plain_dump: str) -> tuple[int, int, list]:
    """Each case's delay (bodies with contention less bodies without) against z80_timed.delay."""
    from retrorecomp import z80_timed
    from retrorecomp.z80_timing import cycles, length
    timed = [line.split() for line in timed_dump.splitlines() if line]
    plain = [line.split() for line in plain_dump.splitlines() if line]
    if len(timed) != len(plain):
        raise RuntimeError('the two dumps do not hold the same cases')
    compared, mismatches = 0, []
    for (hexa, state, contended), (hexa2, state2, own) in zip(timed, plain):
        if (hexa, state) != (hexa2, state2):
            raise RuntimeError('the two dumps are not in the same order')
        raw, state = bytes.fromhex(hexa), int(state)
        encoding = _encoding(raw)
        if encoding is None:
            continue
        start = 0x6000 if state & 4 else 0x8000
        memory = {start + k: raw[k] for k in range(4)}
        registers = {'pc': start, 'sp': 0xC000, 'a': 0x5A, 'b': 1 if state & 2 else 2, 'c': 0 if state & 2 else 1, 'd': 0x40,
                     'e': 0x10, 'h': 0x60, 'l': 0x20, 'i': 0x3F, 'r': 0, 'ix': 0x7000, 'iy': 0x7100, 'vec': 0x3FFF}

        def peek(address):
            return memory.get(address, (address * 31 + 7) & 0xFF)

        def rule(t, address):
            if (address & 0xC000) != 0x4000:
                return 0
            line = t % 224
            return (6, 5, 4, 3, 2, 1, 0, 0)[line & 7] if line < 128 else 0

        def io(t, port):
            if not port & 1:
                return 1 + (t & 3)
            return 2 if (port & 0xC000) == 0x4000 else 0

        taken = int(own) > length(cycles(*encoding)[0])
        expected = z80_timed.delay(*encoding, registers, peek, 1000 + 37 * state, rule, io, taken=taken)
        compared += 1
        if int(contended) - int(own) != expected:
            mismatches.append((hexa, state, int(contended) - int(own), expected))
    return compared, len(mismatches), mismatches[:8]


def main() -> int:
    build = ROOT / '.build' / 'z80-contention-selftest'
    if build.exists():
        shutil.rmtree(build)
    timed_bodies = costs_check.emit_bodies(None, build / 'timed', machine(True))
    plain_bodies = costs_check.emit_bodies(None, build / 'plain', machine(False))
    status = 0
    checks = {}
    for label, bodies, reference_timed, bodies_timed, folder, expect in (
            ('contention on both sides: every encoding must agree', timed_bodies, True, True, 'both', False),
            ('contention in the bodies, not in the reference: they must differ (positive control)', timed_bodies, False, True,
             'control', True),
            ('no contention on either side: every encoding must agree', plain_bodies, False, False, 'neither', False)):
        exe = build_check(bodies, reference_timed, bodies_timed, build / folder)
        checks[folder] = exe
        code, text = run(exe, *(['--expect-difference'] if expect else []))
        print(f'{label}: {text.strip().splitlines()[-1] if text.strip() else "(no output)"}  ->  {"ok" if code == 0 else "FAILED"}')
        if code and not expect:
            print(text[-2000:])
        status |= code
    _, timed_dump = run(checks['both'], '--dump')
    _, plain_dump = run(checks['neither'], '--dump')
    compared, differ, examples = model_check(timed_dump, plain_dump)
    ok = compared > 0 and not differ
    print(f'the delays against the Python walk (retrorecomp/z80_timed.delay): compared={compared} differ={differ} {examples}  ->  '
          f'{"ok" if ok else "FAILED"}')
    return status | (0 if ok else 1)


if __name__ == '__main__':
    sys.exit(main())
