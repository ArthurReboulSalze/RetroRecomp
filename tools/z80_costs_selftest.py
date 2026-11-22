"""ROM-free check of a machine's instruction costs on the banked Z80 chain (retrorecomp/z80_chain.py, `Z80Costs`).

The emitter writes a body for every encoding of the Z80 (native/z80_costs_emit.c, compiled with the generator's source as the
converter patches it for one machine), and native/z80_costs_checks.c runs each body against the reference CPU of the counted
fallback (cpu.prepare_reference) from the same states, comparing the T-states and the PC. Three runs, never a game:

1. an authored table (a third of the encodings of every group given counts of their own, every taken-branch extra, the repeat
   and the CPIR/CPDR repeat apart, the fragment changed), on both sides: every encoding must agree;
2. the same bodies against a reference copied without the table: they must disagree (a positive control);
3. the Z80's own counts on both sides: every encoding must agree (the check itself is sound without any table).

The interrupt acceptances and the HALT cycle are written by the step loop and the reference's interrupt code, whose text
tests/test_z80_chain.py checks. Nothing is written outside .build/z80-costs-selftest.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def authored():
    """The authored table: not any real machine's (the Amstrad CPC fills its own), only values that differ from the Z80's."""
    from retrorecomp.z80_chain import COST_GROUPS, Z80Costs
    base = tuple((group, opcode, 4 + (index * 256 + opcode) * 7 % 37)
                 for index, group in enumerate(COST_GROUPS) for opcode in range(256) if (index * 256 + opcode) % 3 == 0)
    return Z80Costs(base=base, jr_taken=3, djnz_taken=6, ret_taken=9, call_taken=2, repeat=8, repeat_compare=3, irq=15, irq_im2=22, nmi=12,
                    halt=6, fragment=5)


def compiler() -> str:
    try:
        from retrorecomp import toolchain
        candidate = toolchain.tools_directory() / 'llvm-mingw' / 'bin' / ('clang.exe' if os.name == 'nt' else 'clang')
        if candidate.is_file():
            return str(candidate)
    except Exception:
        pass
    for name in ('clang', 'gcc', 'cc'):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit('No C compiler found.')


FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def _compile(sources, include: Path, output: Path, defines=()) -> None:
    command = [compiler(), '-std=gnu11', '-O1', '-w', *defines, '-I', str(include), *map(str, sources), '-o', str(output)]
    built = subprocess.run(command, capture_output=True, encoding='utf-8', errors='replace', creationflags=FLAGS)
    if built.returncode:
        raise RuntimeError(f'{output.name} did not build:\n{built.stdout}{built.stderr}'[-4000:])


def emit_bodies(costs, folder: Path, machine=None) -> Path:
    """The emitter's bodies for every encoding, built with the generator patched for a machine with these costs (or for `machine`,
    as tools/z80_contention_selftest.py asks)."""
    from retrorecomp.core import patched_generator_source
    from retrorecomp.z80_chain import SEGA_MAPPER, Z80Machine
    engine = ROOT / '.deps' / 'smsggrecomp'
    machine = machine or Z80Machine('costs-check', SEGA_MAPPER.regions, costs=costs)
    stage = folder / 'generator'
    stage.mkdir(parents=True)
    for path in (engine / 'recompiler' / 'src').iterdir():
        if path.is_file():
            shutil.copyfile(path, stage / path.name)
    text = (engine / 'recompiler/src/code_generator.c').read_text(encoding='utf-8')
    (stage / 'code_generator.c').write_text(patched_generator_source(text, machine), encoding='utf-8', newline='\n')
    sources = [p for p in stage.glob('*.c') if p.name not in ('main_sms.c', 'code_generator.c')]
    exe = folder / ('z80_costs_emit.exe' if os.name == 'nt' else 'z80_costs_emit')
    _compile([*sources, ROOT / 'native' / 'z80_costs_emit.c'], stage, exe, ('-DSMSRECOMP_BANKED_AOT',))
    bodies = folder / 'z80_costs_bodies.inc'
    ran = subprocess.run([str(exe), str(bodies)], capture_output=True, encoding='utf-8', errors='replace', timeout=120,
                         creationflags=FLAGS)
    if ran.returncode:
        raise RuntimeError(f'the emitter failed: {ran.stdout}{ran.stderr}')
    return bodies


def check(bodies: Path, reference_costs, folder: Path, expect_difference: bool) -> tuple[int, str]:
    from retrorecomp.cpu import prepare_cpu_headers, prepare_reference
    engine = ROOT / '.deps' / 'smsggrecomp'
    folder.mkdir(parents=True)
    prepare_cpu_headers(folder, engine)
    prepare_reference(folder, engine, costs=reference_costs)
    shutil.copyfile(bodies, folder / 'z80_costs_bodies.inc')
    shutil.copyfile(ROOT / 'native' / 'banked_reference_state.inc', folder / 'banked_reference_state.inc')
    exe = folder / ('z80_costs_checks.exe' if os.name == 'nt' else 'z80_costs_checks')
    _compile([ROOT / 'native' / 'z80_costs_checks.c'], folder, exe, ('-DSMSRECOMP_BANKED_AOT',))
    ran = subprocess.run([str(exe)] + (['--expect-difference'] if expect_difference else []), capture_output=True,
                         encoding='utf-8', errors='replace', timeout=300, creationflags=FLAGS)
    return ran.returncode, ran.stdout.strip()


def main() -> int:
    build = ROOT / '.build' / 'z80-costs-selftest'
    if build.exists():
        shutil.rmtree(build)
    table = authored()
    status = 0
    with_table = emit_bodies(table, build / 'table')
    plain = emit_bodies(None, build / 'plain')
    for label, bodies, reference, folder, expect in (
            ('authored table on both sides: every encoding must agree', with_table, table, 'table-check', False),
            ('authored bodies, reference without the table: they must differ (positive control)', with_table, None, 'control', True),
            ("the Z80's own counts on both sides: every encoding must agree", plain, None, 'plain-check', False)):
        code, text = check(bodies, reference, build / folder, expect)
        print(f'{label}: {text}  ->  {"ok" if code == 0 else "FAILED"}')
        status |= code
    return status


if __name__ == '__main__':
    sys.exit(main())
