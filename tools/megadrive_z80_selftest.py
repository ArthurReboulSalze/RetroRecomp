"""Authored Z80 opcode/RAM/bank/interrupt AOT checks, without commercial ROMs."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.core import run, toolchain
from smsrecomp import megadrive_z80


def main():
    project = ROOT / '.build/megadrive-z80-selftest'
    project.mkdir(parents=True, exist_ok=True)
    engine = ROOT / '.deps/segagenesisrecomp'
    variants, payload = [], []
    for op in range(256):
        if op not in (0xcb, 0xdd, 0xed, 0xfd):
            payload.append(bytes([op, 0x9a, 0x1e, 0x5d]))
        for prefix in (0xcb, 0xed):
            payload.append(bytes([prefix, op, 0x9a, 0x1e]))
        for prefix in (0xdd, 0xfd):
            if op not in (0xcb, 0xdd, 0xed, 0xfd):
                payload.append(bytes([prefix, op, 0xf9, 0x1e]))
            payload.append(bytes([prefix, 0xcb, 0xf9, op]))
    payload.extend(bytes.fromhex(raw) for raw in ('dded4300', 'ddfd2100', 'fddd7600', 'ddedb000'))
    for index, raw in enumerate(payload):
        variants.append({'address': index * 4, 'bytes': raw.hex()})
    # Banked code and an instruction wrapping the PC's 16-bit boundary.
    variants += [{'address': 0xffff, 'bytes': '3e9a0000'}, {'address': 0x8000, 'bytes': '211eff00'}]
    stats = megadrive_z80.generate(project, engine, variants)
    fixture = 'static const unsigned char instructions[][4] = {\n' + \
        ',\n'.join('{' + ','.join(map(str, raw)) + '}' for raw in payload) + '\n};\n'
    (project / 'fixture_data.h').write_text(fixture, encoding='ascii')
    for name in ('md_z80_native.h', 'md_z80_runtime.c'):
        shutil.copy2(ROOT / 'native' / name, project / name)
    source = (engine / 'runner/external/superzazu/z80.c').read_text(encoding='utf-8')
    (project / 'reference.c').write_text(megadrive_z80.adapt_reference(source), encoding='utf-8')
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdZ80Checks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{ROOT.as_posix()}/native/md_z80_checks.c"
  md_z80_runtime.c md_z80_generated.c reference.c)
target_include_directories(checks PRIVATE . "{engine.as_posix()}/runner/external/superzazu")
target_compile_options(checks PRIVATE /utf-8 /wd4996)
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64'], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=project / 'build.log')
    output = run([project / 'build/Release/checks.exe'])
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    result['analysis'] = stats
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
