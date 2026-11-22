"""Compile independent Z80 vectors through the production AOT emitter.

`--machine msx|sg1000|coleco` runs them through that machine's own build of the generator (`Z80Machine` of systems/msx.py,
sg1000.py, coleco.py: a region map and `m1_wait` wait states per M1 cycle, which its bodies add to the Z80's T-states: one for the
MSX and the ColecoVision, none for the SG-1000): the expected T-states are the vector's plus `m1_wait` per M1 cycle of the
instruction (`m1_cycles`). The reference interpreter adds no wait state, so `--reference` checks the plain count.

`--machine cpc` runs them through the Amstrad CPC's build (`CPC_MACHINE`: its own table of instruction costs and 16-bit ports).
A machine whose profile gives `z80_vector_tstates` (the CPC's bus rule, systems/amstrad_cpc.py) is expected, vector by vector,
the T-states that rule gives for that vector's own bus trace, not the value of its table: the table is per encoding, the rule
per case, so a branch taken or not, a block instruction that repeats, a prefixed form each meet their own count. With
`port_bits` 16 the whole port address of each I/O cycle is checked, not its low byte.

`--machine zxs` runs them through the ZX Spectrum's build with its ULA contention on (`Z80Machine.contention`): each vector starts
at the T-state its profile gives (`z80_vector_start`, inside a 48K frame's contended window), its bodies ask the machine's own C
rule (`z80_vector_files` and `z80_vector_glue`, built beside them with the chain's evaluator), and it is expected the vector's
T-states plus the delay the profile's documented rule gives over its bus cycles (`z80_vector_delay`)."""
import argparse
from collections import Counter
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args, recompiler_build
from retrorecomp.core import dependencies, default_config, read_rom, run
from retrorecomp.cpu import prepare_cpu_headers, prepare_reference
from fetch_z80_vectors import fetch

def m1_cycles(opcode: int, following: int) -> int:
    """The M1 (opcode fetch) cycles of the instruction that begins with these two bytes: two after a CB, ED, DD or FD prefix
    (DD CB d op too: d and op are read without M1), one otherwise. A DD or FD followed by another prefix is an instruction of
    its own, one M1."""
    if opcode in (0xDD, 0xFD):
        return 1 if following in (0xDD, 0xFD, 0xED) else 2
    return 2 if opcode in (0xCB, 0xED) else 1


FIELDS = 'pc sp a f b c d e h l i r ix iy wz af_ bc_ de_ hl_ im iff1 iff2 ei p q cycles'.split()


def expression(field):
    if field.endswith('_'):
        return f'((g_z80.{field[0]}_ << 8) | g_z80.{field[1]}_)'
    return 'g_z80.' + {'cycles': 'cyc', 'ei': 'ei_block'}.get(field, field)


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=32)
    parser.add_argument('--reuse-build', action='store_true')
    parser.add_argument('--reference', action='store_true')
    parser.add_argument('--machine', choices=('sms', 'msx', 'sg1000', 'coleco', 'cpc', 'zxs'), default='sms')
    parser.add_argument('--expect-no-delay', action='store_true',
                        help='positive control for a machine with contention: expect the plain T-states; the delayed vectors must fail')
    args = parser.parse_args()
    machine = tstates = profile = None
    if args.machine != 'sms':
        from retrorecomp.systems import get_profile
        profile = get_profile(args.machine)
        machine = profile.z80_machine
        if not args.reference:
            tstates = getattr(profile, 'z80_vector_tstates', None)
    # A machine with contention: each vector from its own T-state, expected with the delay of the machine's documented rule.
    contention = profile if machine is not None and machine.contention and not args.reference else None
    source = fetch(args.samples)
    vectors = json.loads(source.read_text(encoding='utf-8'))
    cases = vectors['cases']
    game = ROOT / ('.build/banked-vectors' + ('' if machine is None else '-' + args.machine))
    wait = machine.m1_wait if machine is not None and not args.reference else 0
    game.mkdir(parents=True, exist_ok=True)
    # All immediate/displacement values in this corpus are translated as
    # constants. The test binary never executes a generic opcode interpreter.
    def window_of(case):
        state = case['initial']
        memory = dict(state['ram'])
        return bytes(memory.get((state['pc'] + i) & 65535, 0xA5) for i in range(4))
    windows = sorted({window_of(case) for case in cases})
    # A region-map machine translates as many banks of its first source as its bank numbers reach (`bank_values`): the
    # ZX Spectrum and the Amstrad CPC two of 16 KiB. The corpus is then cut in parts that fit, each generated, built and run
    # on its own; a machine whose banks hold the whole corpus runs it in one part, in the folder it always used.
    per_part = len(windows) if machine is None else max(1, (machine.regions.bank_values << machine.regions.region_bits) // 8)
    parts = [windows[i:i + per_part] for i in range(0, len(windows), per_part)]
    part_of = {window: n for n, part in enumerate(parts) for window in part}
    engine, _, cmake, generator = dependencies(machine=machine)
    source_dir = 'recompiler-src' if machine is None else machine.generator_source
    from retrorecomp import core
    emitter_digest = hashlib.sha256((core.ROOT / '.deps' / source_dir / 'src/code_generator.c').read_bytes()).hexdigest()
    tool = build_executable(recompiler_build(), 'SmsRecomp') if machine is None else __import__(
        'retrorecomp.z80_chain_build', fromlist=['generator']).generator(machine)[0]
    target = 'reference_vectors' if args.reference else 'banked_vectors'
    failures, details, runs = Counter(), [], []
    checks = failed = misses = 0
    print(f'Compiling {len(windows)} exact encodings for {len(cases)} vectors'
          + (f' in {len(parts)} parts' if len(parts) > 1 else '') + '...', flush=True)
    for n, part in enumerate(parts):
        folder = game if len(parts) == 1 else game / f'part{n}'
        folder.mkdir(parents=True, exist_ok=True)
        indexes = [i for i, case in enumerate(cases) if part_of[window_of(case)] == n]
        run_part(folder, machine, part, [cases[i] for i in indexes], wait, tstates, engine, emitter_digest, tool, args, parser,
                 cmake, generator, target, contention)
        result = subprocess.run([str(build_executable(folder / 'build', target)), str(folder / 'vectors.bin')],
            capture_output=True, text=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        (folder / f'{target}.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        for line in result.stdout.splitlines():
            if line.startswith(('FAIL ', 'MISS ')):
                fields = line.split()
                case = cases[indexes[int(fields[1])]]
                failures[case['family'] + ':' + (' '.join(fields[2:3]) or 'missing')] += 1
                details.append({'case': case['name'], 'family': case['family'], 'result': line})
            elif line.startswith('CHECKS='):
                counts = dict(item.split('=') for item in line.split())
                checks += int(counts['CHECKS']); failed += int(counts['FAILED']); misses += int(counts['MISSES'])
        runs.append(dict(folder=folder.name, encodings=len(part), cases=len(indexes), exit_code=result.returncode,
                         executable_sha256=hashlib.sha256(build_executable(folder / 'build', target).read_bytes()).hexdigest()))
        if not result.stdout:
            print(result.stderr)
    exit_code = max(r['exit_code'] for r in runs)
    report = dict(corpus_revision=vectors['revision'], corpus_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        checked_utc=datetime.now(timezone.utc).isoformat(), emitter_sha256=emitter_digest,
        reference_sha256=hashlib.sha256((game if len(parts) == 1 else game / 'part0').joinpath('runtime_reference.c').read_bytes()).hexdigest(),
        helpers_sha256=hashlib.sha256((game if len(parts) == 1 else game / 'part0').joinpath('z80_ops.h').read_bytes()).hexdigest(),
        families=len(vectors['families']), cases=len(cases), selected_per_family=args.samples, machine=args.machine,
        m1_wait_added=wait, cycles_expected='machine bus rule per vector' if tstates is not None else
        'vector T-states + the contention delay of the documented rule, from the profile\'s start T-state' if contention is not None
        else 'vector T-states + m1_wait',
        port_bits=16 if machine is not None and machine.port_bits == 16 and not args.reference else 8,
        exact_encodings=len(windows), exit_code=exit_code, failure_counts=dict(failures), failures=details,
        scope='Generated native bodies: registers, flags, WZ/Q/P, total cycles, all memory writes and the I/O ports (low byte, or the whole address with port_bits 16); not bus waveforms or hardware fidelity')
    if len(parts) == 1:
        report['executable_sha256'] = runs[0]['executable_sha256']
    else:
        report['parts'] = runs
    (game / f'{target}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'CHECKS={checks} FAILED={failed} MISSES={misses}')
    print(json.dumps(dict(failures), indent=2))
    if exit_code:
        raise SystemExit(exit_code)


# A machine with 16-bit ports (Z80Machine.port_bits 16): its bodies call sms_io_in16 / sms_io_out16 (game_banked.h declares
# them). The test bus gets them in a copy of native/banked_vectors.c written beside the build, which checks the whole address;
# the file itself, a game input of every machine, stays as it is.
IO16_ANCHOR = '#ifdef VECTOR_REFERENCE\n#include "runtime_reference.h"\n'
IO16_BUS = '''uint8_t sms_io_in16(uint16_t p) {
    if (io_count++ || port_count != 1 || p != (uint16_t)port[0] || port[2] != 'r') io_error = 1;
    return (uint8_t)port[1];
}
void sms_io_out16(uint16_t p, uint8_t v) {
    if (io_count++ || port_count != 1 || p != (uint16_t)port[0] || v != port[1] || port[2] != 'w') io_error = 1;
}
'''


def harness(game, machine) -> Path:
    """The test bus to compile: native/banked_vectors.c, or for 16-bit ports its copy with the two whole-address calls."""
    source = ROOT / 'native/banked_vectors.c'
    if machine is None or machine.port_bits != 16:
        return source
    text = source.read_text(encoding='utf-8')
    if text.count(IO16_ANCHOR) != 1 or 'sms_io_in16' in text:
        raise SystemExit('native/banked_vectors.c changed: the 16-bit ports copy no longer knows where to go.')
    copy = game / 'banked_vectors16.c'
    copy.write_text(text.replace(IO16_ANCHOR, '#ifdef SMSRECOMP_PORT16\n' + IO16_BUS + '#endif\n' + IO16_ANCHOR), encoding='utf-8', newline='\n')
    return copy


def run_part(game, machine, windows, cases, wait, tstates, engine, emitter_digest, tool, args, parser, cmake, generator, target,
             contention=None):
    """One part of the corpus: its encodings as the first source, its vectors, the generated bodies and the test built."""
    rom = b''.join(window + b'\0' * 4 for window in windows)
    rom += b'\0' * (-len(rom) % 16384)
    (game / 'rom.sms').write_bytes(rom)
    if machine is None:
        (game / 'game.toml').write_text(default_config(read_rom(game / 'rom.sms')), encoding='utf-8')
    else:
        # The machine's own generator: the cartridge is source 0 of the region map, a blank BIOS region source 1.
        from retrorecomp.msx_build import GAME_TOML
        (game / 'bios.rom').write_bytes(b'\xFF' * (1 << machine.regions.region_bits))
        (game / 'banked.sources').write_text(str((game / 'bios.rom').resolve()) + '\n', encoding='utf-8', newline='\n')
        (game / 'game.toml').write_text(GAME_TOML, encoding='utf-8', newline='\n')
    with (game / 'vectors.bin').open('wb') as output:
        def words(values):
            values = list(values)
            output.write(struct.pack('<' + 'I' * len(values), *values))
        words([len(cases)])
        for index, case in enumerate(cases):
            start = contention.z80_vector_start(index) if contention is not None else 0
            for phase in ('initial', 'final'):
                state = case[phase]
                if phase == 'final' and wait:
                    memory = dict(case['initial']['ram'])
                    pc = case['initial']['pc']
                    extra = wait * m1_cycles(memory.get(pc, 0xA5), memory.get((pc + 1) & 65535, 0xA5))
                else:
                    extra = 0
                if phase == 'final' and tstates is not None:
                    cycles = tstates([flags for _, _, flags in case['cycles']])
                elif phase == 'final' and contention is not None:
                    cycles = start + len(case['cycles']) + (0 if args.expect_no_delay else contention.z80_vector_delay(case, start))
                else:
                    cycles = len(case['cycles']) + extra
                if phase == 'initial' and contention is not None:
                    words(start if key == 'cycles' else state.get(key, 0) for key in FIELDS)
                else:
                    words(cycles if key == 'cycles' and phase == 'final' else state.get(key, 0) for key in FIELDS)
            for phase in ('initial', 'final'):
                words([len(case[phase]['ram'])])
                for address, value in case[phase]['ram']:
                    words([address, value])
            ports = case.get('ports', [])
            words([len(ports)])
            for address, value, direction in ports:
                words([address, value, ord(direction)])
    header = [f'#define VECTOR_FIELDS {len(FIELDS)}', 'static const char *vector_names[] = {' + ','.join(json.dumps(k) for k in FIELDS) + '};',
              'static void vector_load(const uint32_t *v) {', 'g_z80 = (Z80State){0};']
    for i, field in enumerate(FIELDS):
        if field.endswith('_'):
            header.append(f'g_z80.{field[0]}_ = v[{i}] >> 8; g_z80.{field[1]}_ = v[{i}];')
        else:
            header.append(f'{expression(field)} = v[{i}];')
    header.extend(['}', 'static void vector_save(uint32_t *v) {'])
    header.extend(f'v[{i}] = (uint32_t){expression(field)};' for i, field in enumerate(FIELDS))
    header.append('}')
    (game / 'vector_state.h').write_text('\n'.join(header), encoding='utf-8')
    prepare_cpu_headers(game, engine)
    prepare_reference(game, engine)
    extra_sources = ''
    if contention is not None:
        # The chain's evaluator, the machine's rule and its glue, built into the bodies' test.
        from retrorecomp.z80_timed import render_header, render_source
        (game / 'banked_timed.h').write_text(render_header(), encoding='utf-8', newline='\n')
        (game / 'banked_timed.c').write_text(render_source(), encoding='utf-8', newline='\n')
        (game / 'vector_contention.c').write_text(contention.z80_vector_glue, encoding='utf-8', newline='\n')
        names = ['banked_timed.c', 'vector_contention.c']
        for folder, files in contention.z80_vector_files:
            for name in files:
                (game / name).write_bytes((ROOT / folder / name).read_bytes())
                if name.endswith('.c'):
                    names.append(name)
        extra_sources = ' ' + ' '.join(names)
    stamp = game / 'generated/emitter.sha256'
    if args.reuse_build and (not stamp.exists() or stamp.read_text() != emitter_digest):
        parser.error('Generated bodies do not match the current emitter; run without --reuse-build.')
    if not args.reuse_build:
        for stale in (game / 'generated').glob('game_banked_ops_*.c'):
            stale.unlink()
        run([tool, '--game', game / 'game.toml', '--banked-step'], log=game / 'build.log')
        stamp.write_text(emitter_digest)
    bus = harness(game, machine).resolve().as_posix()
    (game / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.21)
project(BankedVectors C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")
file(GLOB bodies "generated/game_banked_ops_*.c")
add_executable(banked_vectors "{bus}" generated/game_banked_index.c ${{bodies}}{extra_sources})
target_include_directories(banked_vectors PRIVATE "${{CMAKE_CURRENT_SOURCE_DIR}}" "${{CMAKE_CURRENT_SOURCE_DIR}}/generated")
target_compile_definitions(banked_vectors PRIVATE SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS)
target_compile_options(banked_vectors PRIVATE "$<$<C_COMPILER_ID:MSVC>:/W2;/MP4>")
add_executable(reference_vectors "{bus}" runtime_reference.c)
target_include_directories(reference_vectors PRIVATE "${{CMAKE_CURRENT_SOURCE_DIR}}" "${{CMAKE_CURRENT_SOURCE_DIR}}/generated")
target_compile_definitions(reference_vectors PRIVATE VECTOR_REFERENCE _CRT_SECURE_NO_WARNINGS)
''', encoding='utf-8')
    run([cmake, '-S', game, '-B', game / 'build', '-G', generator, *cmake_target_args()], log=game / 'build.log')
    run([cmake, '--build', game / 'build', '--config', 'Release', '--target', target, '--parallel', '4'], log=game / 'build.log', timeout=900)


if __name__ == '__main__':
    main()
