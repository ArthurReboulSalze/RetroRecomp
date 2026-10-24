"""Use the existing synthetic prefetch corpus to check and time static plans."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.platforms import build_executable, cmake_target_args, build_jobs


def main():
    # First run megadrive_prefetch_selftest.py to stage its decoded fixture.
    fixture = ROOT / '.build/megadrive-prefetch-selftest'
    assert (fixture / 'results.json').is_file()
    output = ROOT / '.build/megadrive-prefetch-plan-selftest'
    output.mkdir(exist_ok=True)
    engine = ROOT / '.deps/segagenesisrecomp'
    # Both included units must resolve the same staged headers. pragma once
    # does not merge identical headers copied to different filesystem paths.
    corpus = fixture / 'plan-corpus.inc'
    corpus.write_text((ROOT/'native/md_prefetch_checks.c').read_text(encoding='utf-8'), encoding='utf-8')
    harness = (ROOT/'native/md_prefetch_plan_checks.c').read_text(encoding='utf-8')
    (output/'checks.c').write_text(harness.replace('"md_prefetch_checks.c"',
        '"'+corpus.as_posix()+'"'), encoding='utf-8')
    (output / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdPrefetchPlans C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
file(GLOB STEPS "{fixture.as_posix()}/steps/*.c")
add_executable(checks checks.c ${{STEPS}}
 "{engine.as_posix()}/recompiler/src/m68k_decoder.c" "{engine.as_posix()}/recompiler/src/rom_parser.c")
target_include_directories(checks PRIVATE "{fixture.as_posix()}" "{engine.as_posix()}/runner"
 "{engine.as_posix()}/runner/include" "{engine.as_posix()}/recompiler/src")
if(MSVC)
 target_compile_options(checks PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8;/wd4996>")
endif()
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', output, '-B', output/'build', '-G', generator, *cmake_target_args()], log=output/'build.log')
    run([cmake, '--build', output/'build', '--config', 'Release', '--parallel', build_jobs()], log=output/'build.log')
    text = run([build_executable(output/'build', 'checks')])
    result = json.loads(text.strip().splitlines()[-1])
    (output/'results.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
