"""Authored SPC700 opcode, mutable-code, IPL and bus checks. No game ROMs."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.core import run, toolchain
from smsrecomp import snes_spc


def main():
    project = ROOT / '.build/snes-spc-selftest'
    project.mkdir(parents=True, exist_ok=True)
    engine = ROOT / '.deps/snesrecomp'
    staged = project / 'engine/runner'
    shutil.copytree(engine / 'runner', staged, dirs_exist_ok=True)
    ppu = staged / 'src/snes/ppu.h'
    ppu.write_text(ppu.read_text(encoding='utf-8').replace(
        'typedef struct PpuPixelPrioBufs {',
        'typedef struct __declspec(align(8)) PpuPixelPrioBufs {').replace(
        '} __attribute__((aligned(8))) PpuPixelPrioBufs;', '} PpuPixelPrioBufs;'), encoding='utf-8')
    source = (engine / 'runner/src/snes/spc.c').read_text(encoding='utf-8')
    masks = bytearray(snes_spc.MASK_BYTES)
    for opcode in range(256):
        for pc in (0x2000 + opcode * 8, 0xffff):
            masks[pc * 32 + opcode // 8] |= 1 << (opcode & 7)
    for pc, opcode in ((0xe000, 0xe8), (0xe100, 0xd0), (0xe200, 0xe4)):
        masks[pc * 32 + opcode // 8] |= 1 << (opcode & 7)
    boot = bytes([0] * 62 + [0xc0, 0xff])  # authored reset-vector fixture
    (project / 'fixture_data.h').write_text('static const uint8_t fixture_boot[64] = {' +
        ','.join(map(str, boot)) + '};\n', encoding='ascii')
    code, guarded = snes_spc.native_source(source, boot, masks)
    (project / 'snes_spc_ops.inc').write_text(code, encoding='utf-8')
    (project / 'spc.c').write_text(snes_spc.adapt_core(source), encoding='utf-8')
    for name in ('snes_spc_native.h', 'snes_spc_runtime.c'):
        shutil.copy2(ROOT / 'native' / name, project / name)
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroSnesSpcChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{ROOT.as_posix()}/native/snes_spc_checks.c" spc.c snes_spc_runtime.c)
target_include_directories(checks PRIVATE . "{staged.as_posix()}/src" "{staged.as_posix()}/src/snes")
target_compile_options(checks PRIVATE /utf-8 /wd4996)
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64'], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=project / 'build.log')
    result = json.loads(run([project / 'build/Release/checks.exe']))
    result['guarded_variants'] = guarded
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
