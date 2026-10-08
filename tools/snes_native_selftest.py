"""ROM-free 65816 static-operation, register-width and live-bus checks."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.core import run, toolchain
from smsrecomp.snes_codegen import native_source, adapt_core


def main():
    engine = ROOT / '.deps/snesrecomp'
    project = ROOT / '.build/snes-native-selftest'
    project.mkdir(exist_ok=True, parents=True)
    staged = project / 'engine/runner'
    shutil.copytree(engine / 'runner', staged, dirs_exist_ok=True)
    ppu = staged / 'src/snes/ppu.h'
    ppu.write_text(ppu.read_text(encoding='utf-8').replace(
        'typedef struct PpuPixelPrioBufs {',
        'typedef struct __declspec(align(8)) PpuPixelPrioBufs {').replace(
        '} __attribute__((aligned(8))) PpuPixelPrioBufs;', '} PpuPixelPrioBufs;'),
        encoding='utf-8')
    rom = bytearray([0xea] * 0x8000)
    for opcode in range(256):
        rom[opcode * 8:opcode * 8 + 4] = bytes((opcode, 0x34, 0x12, 0))
    rom[-1] = 0xa9
    (project / 'fixture_rom.h').write_text('static const unsigned char fixture_rom[] = {' +
        ','.join(map(str, rom)) + '};\n', encoding='ascii')
    source = (engine / 'runner/src/snes/interp816.c').read_text(encoding='utf-8')
    (project / 'snes_native_ops.inc').write_text(native_source(source, rom,
        [{'address': 0x7e0100, 'bytes': 'a93412ea'}]), encoding='utf-8')
    (project / 'interp816.c').write_text(adapt_core(source), encoding='utf-8')
    shutil.copy2(ROOT / 'native/snes_native_steps.h', project / 'snes_native_steps.h')
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(SnesNativeChecks C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks interp816.c "{ROOT.as_posix()}/native/snes_native_checks.c")
target_include_directories(checks PRIVATE . "{staged.as_posix()}/src" "{staged.as_posix()}/src/snes")
target_compile_options(checks PRIVATE /utf-8 /wd4996)
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64'], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=project / 'build.log')
    result = json.loads(run([project / 'build/Release/checks.exe']))
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
