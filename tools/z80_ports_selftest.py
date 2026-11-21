"""ROM-free check of 16-bit ports on the banked Z80 chain (retrorecomp/z80_chain.py, `Z80Machine.port_bits`).

The generator patched for a machine with 16-bit ports writes the bodies of every I/O encoding (native/z80_ports_emit.c: IN A,(n),
OUT (n),A, the same behind a DD or FD prefix, IN r,(C) and the undocumented IN (C), OUT (C),r and the undocumented OUT (C),0, INI,
IND, INIR, INDR, OUTI, OUTD, OTIR, OTDR) and re-spells them as a conversion does; native/z80_ports_checks.c runs each against the
reference CPU copied with `cpu.prepare_reference(port16=True)` from five register states, recording every port access. Two runs,
never a game:

1. the 16-bit reference: every encoding must agree on the accesses (direction, 16-bit address, value), PC, B, C and the cycles, and
   the first address must be the one the Z80 puts on the bus (A and n, BC, or B - 1 and C for the OUTI forms);
2. the reference left at 8 bits: the addresses must differ (a positive control).
Nothing is written outside .build/z80-ports-selftest.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


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


def _compile(sources, include: Path, output: Path, defines=()) -> None:
    command = [compiler(), '-std=gnu11', '-O1', '-w', *defines, '-I', str(include), *map(str, sources), '-o', str(output)]
    built = subprocess.run(command, capture_output=True, encoding='utf-8', errors='replace', creationflags=FLAGS)
    if built.returncode:
        raise RuntimeError(f'{output.name} did not build:\n{built.stdout}{built.stderr}'[-4000:])


def emit_bodies(folder: Path) -> Path:
    from retrorecomp.core import patched_generator_source
    from retrorecomp.z80_chain import Z80Machine, Z80RegionMap
    engine = ROOT / '.deps' / 'smsggrecomp'
    machine = Z80Machine('ports-check', Z80RegionMap(region_bits=14, sources=('rom',), bank_values=2, scope='ports-check'),
                         irq_sample='instruction_end', step_begin=True, reference_state=True, port_bits=16)
    stage = folder / 'generator'
    stage.mkdir(parents=True)
    for path in (engine / 'recompiler' / 'src').iterdir():
        if path.is_file():
            shutil.copyfile(path, stage / path.name)
    text = (engine / 'recompiler/src/code_generator.c').read_text(encoding='utf-8')
    (stage / 'code_generator.c').write_text(patched_generator_source(text, machine), encoding='utf-8', newline='\n')
    sources = [p for p in stage.glob('*.c') if p.name not in ('main_sms.c', 'code_generator.c')]
    exe = folder / ('z80_ports_emit.exe' if os.name == 'nt' else 'z80_ports_emit')
    _compile([*sources, ROOT / 'native' / 'z80_ports_emit.c'], stage, exe, ('-DSMSRECOMP_BANKED_AOT',))
    bodies = folder / 'z80_ports_bodies.inc'
    ran = subprocess.run([str(exe), str(bodies)], capture_output=True, encoding='utf-8', errors='replace', timeout=120,
                         creationflags=FLAGS)
    if ran.returncode:
        raise RuntimeError(f'the emitter failed: {ran.stdout}{ran.stderr}')
    text = bodies.read_text(encoding='utf-8')
    if 'sms_io_in(' in text or 'sms_io_out(' in text or 'sms_io_in16(' not in text or 'sms_io_out16(' not in text:
        raise RuntimeError('the bodies were not re-spelled with 16-bit ports')
    return bodies


def check(bodies: Path, port16: bool, folder: Path) -> tuple[int, str]:
    from retrorecomp.cpu import prepare_cpu_headers, prepare_reference
    engine = ROOT / '.deps' / 'smsggrecomp'
    folder.mkdir(parents=True)
    prepare_cpu_headers(folder, engine)
    prepare_reference(folder, engine, port16=port16)
    shutil.copyfile(bodies, folder / 'z80_ports_bodies.inc')
    shutil.copyfile(ROOT / 'native' / 'banked_reference_state.inc', folder / 'banked_reference_state.inc')
    exe = folder / ('z80_ports_checks.exe' if os.name == 'nt' else 'z80_ports_checks')
    _compile([ROOT / 'native' / 'z80_ports_checks.c'], folder, exe,
             ('-DSMSRECOMP_BANKED_AOT', *(() if port16 else ('-DRR_REFERENCE_PORT8',))))
    ran = subprocess.run([str(exe)] + ([] if port16 else ['--expect-difference']), capture_output=True, encoding='utf-8',
                         errors='replace', timeout=120, creationflags=FLAGS)
    return ran.returncode, ran.stdout.strip()


def main() -> int:
    build = ROOT / '.build' / 'z80-ports-selftest'
    if build.exists():
        shutil.rmtree(build)
    bodies = emit_bodies(build / 'emit')
    status = 0
    for label, port16, folder in (('16-bit reference: every I/O encoding must agree, at the Z80\'s own address', True, 'ports16'),
                                  ('reference left at 8 bits: it must differ (positive control)', False, 'ports8')):
        code, text = check(bodies, port16, build / folder)
        print(f'{label}: {text}  ->  {"ok" if code == 0 else "FAILED"}')
        status |= code
    return status


if __name__ == '__main__':
    sys.exit(main())
