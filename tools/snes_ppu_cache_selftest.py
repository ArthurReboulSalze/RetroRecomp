"""Compare exact decoded tile rows against the pinned scalar sampler."""
from pathlib import Path
import json
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.platforms import build_executable, cmake_target_args, build_jobs
from retrorecomp.snes_video import legacy


def main():
    project = ROOT / '.build/snes-ppu-cache-selftest'
    source = ROOT / '.deps/snesrecomp/runner/src'
    staged = project / 'snes'
    staged.mkdir(parents=True, exist_ok=True)
    for header_path in source.rglob('*.h'):
        target = project / header_path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(header_path, target)
    (staged / 'ppu_legacy.c').write_text(legacy((source / 'snes/ppu_legacy.c').read_text(), checks=True), encoding='utf-8')
    header = (source / 'snes/ppu.h').read_text()
    if os.name == 'nt':
        header = header.replace('typedef struct PpuPixelPrioBufs {', 'typedef struct __declspec(align(8)) PpuPixelPrioBufs {')
        header = header.replace('} __attribute__((aligned(8))) PpuPixelPrioBufs;', '} PpuPixelPrioBufs;')
    (staged / 'ppu.h').write_text(header, encoding='utf-8')
    for name in ('snes_ppu_cache.inc', 'snes_ppu_cache_checks.c', 'planar_rows.h'):
        shutil.copy2(ROOT / 'native' / name, project / name)
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(SnesPpuCacheChecks C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks snes_ppu_cache_checks.c)
target_include_directories(checks PRIVATE . "{source.as_posix()}" "{(source / 'snes').as_posix()}")
if(MSVC)
  target_compile_options(checks PRIVATE /O2 /Gy /utf-8)
  target_link_options(checks PRIVATE /OPT:REF)
else()
  target_compile_options(checks PRIVATE -O2 -ffunction-sections -fdata-sections)
  target_link_options(checks PRIVATE -Wl,--gc-sections)
endif()
''', encoding='utf-8')
    cmake, generator = toolchain()
    log = project / 'build.log'
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=log)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()], log=log)
    result = json.loads(run([build_executable(project / 'build', 'checks')]))
    (project / 'result.json').write_text(json.dumps(result, indent=2), encoding='ascii')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
