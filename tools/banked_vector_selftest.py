"""Compile independent Z80 vectors through the production AOT emitter."""
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
from smsrecomp.core import dependencies, default_config, read_rom, run
from smsrecomp.cpu import prepare_cpu_headers, prepare_reference
from fetch_z80_vectors import fetch

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
    args = parser.parse_args()
    source = fetch(args.samples)
    vectors = json.loads(source.read_text(encoding='utf-8'))
    cases = vectors['cases']
    game = ROOT / '.build/banked-vectors'
    game.mkdir(parents=True, exist_ok=True)
    # All immediate/displacement values in this corpus are translated as
    # constants. The test binary never executes a generic opcode interpreter.
    windows = set()
    for case in cases:
        state = case['initial']
        memory = dict(state['ram'])
        windows.add(bytes(memory.get((state['pc'] + i) & 65535, 0xA5) for i in range(4)))
    rom = b''.join(window + b'\0' * 4 for window in sorted(windows))
    rom += b'\0' * (-len(rom) % 16384)
    (game / 'rom.sms').write_bytes(rom)
    (game / 'game.toml').write_text(default_config(read_rom(game / 'rom.sms')), encoding='utf-8')
    with (game / 'vectors.bin').open('wb') as output:
        def words(values):
            values = list(values)
            output.write(struct.pack('<' + 'I' * len(values), *values))
        words([len(cases)])
        for case in cases:
            for phase in ('initial', 'final'):
                state = case[phase]
                words(len(case['cycles']) if key == 'cycles' and phase == 'final' else state.get(key, 0) for key in FIELDS)
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
    engine, _, cmake, generator = dependencies()
    prepare_cpu_headers(game, engine)
    prepare_reference(game, engine)
    emitter_digest = hashlib.sha256((ROOT / '.deps/recompiler-src/src/code_generator.c').read_bytes()).hexdigest()
    stamp = game / 'generated/emitter.sha256'
    if args.reuse_build and (not stamp.exists() or stamp.read_text() != emitter_digest):
        parser.error('Generated bodies do not match the current emitter; run without --reuse-build.')
    if not args.reuse_build:
        for stale in (game / 'generated').glob('game_banked_ops_*.c'):
            stale.unlink()
        run([ROOT / '.deps/recompiler-build/Release/SmsRecomp.exe', '--game', game / 'game.toml', '--banked-step'], log=game / 'build.log')
        stamp.write_text(emitter_digest)
    (game / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.21)
project(BankedVectors C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")
file(GLOB bodies "generated/game_banked_ops_*.c")
add_executable(banked_vectors "{(ROOT / 'native/banked_vectors.c').as_posix()}" generated/game_banked_index.c ${{bodies}})
target_include_directories(banked_vectors PRIVATE "${{CMAKE_CURRENT_SOURCE_DIR}}" "${{CMAKE_CURRENT_SOURCE_DIR}}/generated")
target_compile_definitions(banked_vectors PRIVATE SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS)
target_compile_options(banked_vectors PRIVATE /W2 /MP4)
add_executable(reference_vectors "{(ROOT / 'native/banked_vectors.c').as_posix()}" runtime_reference.c)
target_include_directories(reference_vectors PRIVATE "${{CMAKE_CURRENT_SOURCE_DIR}}" "${{CMAKE_CURRENT_SOURCE_DIR}}/generated")
target_compile_definitions(reference_vectors PRIVATE VECTOR_REFERENCE _CRT_SECURE_NO_WARNINGS)
''', encoding='utf-8')
    run([cmake, '-S', game, '-B', game / 'build', '-G', generator, '-A', 'x64'], log=game / 'build.log')
    print(f'Compiling {len(windows)} exact encodings for {len(cases)} vectors...', flush=True)
    target = 'reference_vectors' if args.reference else 'banked_vectors'
    run([cmake, '--build', game / 'build', '--config', 'Release', '--target', target, '--parallel', '4'], log=game / 'build.log', timeout=900)
    result = subprocess.run([str(game / f'build/Release/{target}.exe'), str(game / 'vectors.bin')],
        capture_output=True, text=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    (game / f'{target}.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    failures, details = Counter(), []
    for line in result.stdout.splitlines():
        if line.startswith(('FAIL ', 'MISS ')):
            fields = line.split()
            case = cases[int(fields[1])]
            failures[case['family'] + ':' + (' '.join(fields[2:3]) or 'missing')] += 1
            details.append({'case': case['name'], 'family': case['family'], 'result': line})
    report = dict(corpus_revision=vectors['revision'], corpus_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        checked_utc=datetime.now(timezone.utc).isoformat(), emitter_sha256=emitter_digest,
        reference_sha256=hashlib.sha256((game / 'runtime_reference.c').read_bytes()).hexdigest(),
        helpers_sha256=hashlib.sha256((game / 'z80_ops.h').read_bytes()).hexdigest(),
        executable_sha256=hashlib.sha256((game / f'build/Release/{target}.exe').read_bytes()).hexdigest(),
        families=len(vectors['families']), cases=len(cases), selected_per_family=args.samples,
        exact_encodings=len(windows), exit_code=result.returncode, failure_counts=dict(failures), failures=details,
        scope='Generated native bodies: registers, flags, WZ/Q/P, total cycles, all memory writes and low-byte SMS ports; not bus waveforms or hardware fidelity')
    (game / f'{target}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(result.stdout.splitlines()[-1] if result.stdout else result.stderr)
    print(json.dumps(dict(failures), indent=2))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
