"""The 65816 and the SPC700 against single-instruction vectors of an independent corpus (gate G10).

SingleStepTests/65816 and SingleStepTests/spc700 (MIT; generated from other emulators' behaviour, not recorded from a
console) are read from `.deps/snes-vectors/` (fetch them with `tools/fetch_snes_vectors.py`; the first run does it) and never
enter the repository. An evenly spaced sample of every family is run on the converter's cores:
  * the reference (interpreted) core of each CPU, on every case;
  * the compiled core: for the SPC700 on every case, for the 65816 on the cases whose instruction sits in WRAM, the only place
    the game runs compiled code from RAM (the opcode of the other cases sits in a bank the game maps to ROM, I/O or nothing).
What is compared is in `native/snes_cpu/cpu_vector_checks.c` and `native/snes_cpu/spc_vector_checks.c`: registers and memory
after the instruction (semantics), the number of cycles (timing) and the order, address and value of the bus accesses
(ordering). The result says, for each class, how many cases differ and the first mismatching families; it is evidence about
instruction semantics and bus order, not hardware accuracy, and a difference is a finding to read, not a failure of the tool.

    python tools/snes_cpu_vector_selftest.py [--cpu 65816|spc700] [--samples 64] [--details N]
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args  # noqa: E402
from retrorecomp.core import run, toolchain  # noqa: E402
from retrorecomp.console16 import snes_ppu_header  # noqa: E402
from tools.fetch_snes_vectors import CACHE, CORPORA, fetch  # noqa: E402

DEFAULT_SAMPLES = {'65816': 64, 'spc700': 128}


def cases_of(cpu, samples):
    path = fetch(cpu, samples)
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['revision'] == CORPORA[cpu]['revision'] and data['manifest_sha256'] == CORPORA[cpu]['manifest_sha256']
    # A format drift would give no case and no difference: the number of cases is what the corpus and the sample say it is.
    assert len(data['families']) == CORPORA[cpu]['families'], (len(data['families']), CORPORA[cpu]['families'])
    expected = sum(min(samples, family['available']) for family in data['families'])
    assert len(data['cases']) == expected and expected >= CORPORA[cpu]['families'] * min(samples, 200), (len(data['cases']), expected)
    return data['cases']


def number(value):
    return -1 if value is None else value


def write_65816(cases, path):
    lines = []
    for index, case in enumerate(cases):
        i, f = case['initial'], case['final']
        parts = [index, i['e'], i['pc'], i['s'], i['p'], i['a'], i['x'], i['y'], i['dbr'], i['d'], i['pbr'], len(i['ram'])]
        parts += [v for pair in i['ram'] for v in pair]
        parts += [f['e'], f['pc'], f['s'], f['p'], f['a'], f['x'], f['y'], f['dbr'], f['d'], f['pbr'], len(f['ram'])]
        parts += [v for pair in f['ram'] for v in pair]
        parts.append(len(case['cycles']))
        for address, value, flags in case['cycles']:
            kind = 2 if value is None else (0 if flags[3] == 'r' else 1 if flags[3] == 'w' else 2)
            parts += [number(address), number(value), kind]
        lines.append(' '.join(map(str, parts)))
    path.write_text('\n'.join(lines) + '\n', encoding='ascii')


def write_spc700(cases, path):
    lines = []
    for index, case in enumerate(cases):
        i, f = case['initial'], case['final']
        parts = [index, i['pc'], i['a'], i['x'], i['y'], i['sp'], i['psw'], len(i['ram'])] + [v for pair in i['ram'] for v in pair]
        parts += [f['pc'], f['a'], f['x'], f['y'], f['sp'], f['psw'], len(f['ram'])] + [v for pair in f['ram'] for v in pair]
        parts.append(len(case['cycles']))
        for address, value, kind in case['cycles']:
            parts += [number(address), number(value), {'read': 0, 'write': 1}.get(kind, 2)]
        lines.append(' '.join(map(str, parts)))
    path.write_text('\n'.join(lines) + '\n', encoding='ascii')


def stage_engine(project):
    engine = ROOT / '.deps/snesrecomp'
    staged = project / 'engine/runner'
    shutil.copytree(engine / 'runner', staged, dirs_exist_ok=True)
    ppu = staged / 'src/snes/ppu.h'
    ppu.write_text(snes_ppu_header(ppu.read_text(encoding='utf-8')), encoding='utf-8')
    return engine, staged


def build_65816(project):
    from retrorecomp.snes_codegen import native_source, adapt_core, mirrored_rom, read_core
    engine, staged = stage_engine(project)
    rom = bytearray([0xea] * 0x18000)
    (project / 'fixture_rom.h').write_text(
        f'#define FIXTURE_IMAGE_BYTES {len(rom)}u\nstatic const unsigned char fixture_rom[] = {{' +
        ','.join(map(str, mirrored_rom(rom))) + '};\n', encoding='ascii')
    source = read_core(engine)
    (project / 'snes_native_ops.inc').write_text(native_source(source, rom, []), encoding='utf-8')
    (project / 'interp816.c').write_text(adapt_core(source), encoding='utf-8')
    shutil.copy2(ROOT / 'native/snes_native_steps.h', project / 'snes_native_steps.h')
    shutil.copy2(ROOT / 'native/snes_cart.h', project / 'snes_cart.h')
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(SnesCpuVectors C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(vectors interp816.c "{ROOT.as_posix()}/native/snes_cpu/cpu_vector_checks.c")
target_compile_definitions(vectors PRIVATE FIXTURE_CART_TYPE=CART_LOROM)
target_include_directories(vectors PRIVATE . "{staged.as_posix()}/src" "{staged.as_posix()}/src/snes")
target_compile_options(vectors PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8;/wd4996>")
''', encoding='utf-8')


def build_spc700(project):
    from retrorecomp import snes_spc
    from retrorecomp.feedback import stage
    engine, staged = stage_engine(project)
    source = (engine / 'runner/src/snes/spc.c').read_text(encoding='utf-8')
    boot = bytes([0] * 62 + [0xc0, 0xff])
    (project / 'fixture_data.h').write_text('static const uint8_t fixture_boot[64] = {' + ','.join(map(str, boot)) + '};\n',
                                            encoding='ascii')
    code, _ = snes_spc.native_source(source, boot, bytearray(snes_spc.MASK_BYTES))   # no observed position: every one is unobserved
    (project / 'snes_spc_ops.inc').write_text(code, encoding='utf-8')
    (project / 'spc.c').write_text(snes_spc.adapt_core(source), encoding='utf-8')
    for name in ('snes_spc_native.h', 'snes_spc_runtime.c'):
        shutil.copy2(ROOT / 'native' / name, project / name)
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(SpcVectors C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(vectors "{ROOT.as_posix()}/native/snes_cpu/spc_vector_checks.c" spc.c snes_spc_runtime.c)
target_include_directories(vectors PRIVATE . "{staged.as_posix()}/src" "{staged.as_posix()}/src/snes")
target_compile_options(vectors PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8;/wd4996>")
''', encoding='utf-8')
    stage(project, 'snes', '0' * 64, target='vectors')


def exercise(cpu, samples, details):
    project = ROOT / f'.build/snes-cpu-vectors-{cpu}'
    project.mkdir(parents=True, exist_ok=True)
    cases = cases_of(cpu, samples)
    (write_65816 if cpu == '65816' else write_spc700)(cases, project / 'cases.txt')
    (build_65816 if cpu == '65816' else build_spc700)(project)
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=project / 'build.log')
    lines = run([build_executable(project / 'build', 'vectors'), str(project / 'cases.txt')], timeout=3600).strip().splitlines()
    result = json.loads([line for line in lines if line.startswith('{')][-1])
    # Every case was read and every case is in exactly one class, for each core that ran it (the harness says how many of its
    # lines it parsed: a shifted or short file shows here, not as zero differences).
    assert result['cases'] == len(cases), (result['cases'], len(cases))
    for core in ('interpreted', 'compiled'):
        ran = result['compiled_cases'] if (cpu == '65816' and core == 'compiled') else len(cases)
        tally = sum(result[core].get(key, 0) for key in ('semantic', 'timing', 'ordering', 'skipped', 'passed'))
        assert tally == ran, (cpu, core, tally, ran)
    if cpu == 'spc700':
        assert result['interpreted']['skipped'] < len(cases) // 6, 'too many cases skipped for touching I/O'
    else:
        assert result['compiled_cases'] >= len(cases) // 50, 'too few cases reach the compiled core'
    mismatches = [line.split() for line in lines if line.startswith('MISMATCH')]
    names = {1: 'semantic', 2: 'timing', 3: 'ordering'}
    by_family = {}
    by_mode = {}    # the cases the reference core gets wrong, by class and by 65816 mode (".e" emulation, ".n" native in the family name)
    for line in lines:
        if line.startswith('FAIL'):
            _, index, compiled, klass = line.split()
            if not int(compiled):
                family = cases[int(index)]['family']
                key = f"{names[int(klass)]}:{family.rsplit('.', 1)[1] if '.' in family else 'all'}"
                by_mode[key] = by_mode.get(key, 0) + 1
            by_family.setdefault((names[int(klass)], cases[int(index)]['family']), []).append(
                (cases[int(index)]['name'], 'compiled' if int(compiled) else 'interpreted', '', ''))
    for fields in mismatches:   # the first differences, with their detail, replace the bare entries of the same case
        family = cases[int(fields[1])]['family']
        rows = by_family.setdefault((fields[2], family), [])
        rows.insert(0, (cases[int(fields[1])]['name'], fields[3], fields[4], fields[5]))
    result.update({'interpreted_by_mode': dict(sorted(by_mode.items())), 'cpu': cpu, 'revision': CORPORA[cpu]['revision'], 'manifest_sha256': CORPORA[cpu]['manifest_sha256'],
                   'samples_per_family': samples, 'families': len({case['family'] for case in cases}),
                   'case_counts_by_family': {f'{klass}:{family}': len(rows) for (klass, family), rows in sorted(by_family.items())},
                   'first_mismatches': {f'{klass}:{family}': rows[:2] for (klass, family), rows in
                                        sorted(by_family.items())[:details]},
                   'mismatching_families': {klass: sorted({fam for (k, fam) in by_family if k == klass})
                                            for klass in ('semantic', 'timing', 'ordering')}})
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cpu', choices=sorted(CORPORA), action='append')
    parser.add_argument('--samples', type=int)
    parser.add_argument('--details', type=int, default=40)
    args = parser.parse_args()
    for cpu in args.cpu or sorted(CORPORA):
        print(json.dumps(exercise(cpu, args.samples or DEFAULT_SAMPLES[cpu], args.details), indent=2), flush=True)


if __name__ == '__main__':
    main()
