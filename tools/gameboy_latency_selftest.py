"""Compile the real adapted host against an authored empty cartridge; no visuals."""
from pathlib import Path
import os
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.gameboy import _dependencies
from smsrecomp.gameboy_runtime import adapt_generated_project
from smsrecomp.paths import ROOT, ASSETS
from smsrecomp.core import run


def main():
    project = ROOT / '.build/gb-latency-selftest'
    project.mkdir(parents=True, exist_ok=True)
    rom = bytearray(32768)
    rom[0x100:0x103] = b'\xc3\x00\x01'  # Authored JP $0100 loop.
    (project / 'fixture.gb').write_bytes(rom)
    engine, compiler, sdl, cmake, generator = _dependencies(print)
    log = project / 'build.log'
    run([compiler, project / 'fixture.gb', '-o', project, '--runtime-dir', engine / 'runtime',
         '--output-prefix', 'game', '--no-comments'], log=log, timeout=600)
    adapt_generated_project(project, 'latency-fixture', '0' * 64, 'Authored latency fixture')
    (project / 'game_resources.rc').write_text('1 RCDATA { 0 }\n', encoding='utf-8')
    with (project / 'CMakeLists.txt').open('a', encoding='utf-8') as out:
        out.write(f'''\nadd_executable(retro_gb_latency_checks "{(ASSETS / 'native/gb_latency_checks.cpp').as_posix()}")
target_compile_definitions(retro_gb_latency_checks PRIVATE GBRT_ENABLE_TEST_HOOKS)
target_include_directories(retro_gb_latency_checks PRIVATE "${{GBRT_DIR}}/src")
target_link_libraries(retro_gb_latency_checks PRIVATE gbrt)
''')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64',
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=log)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--target',
         'retro_gb_latency_checks', '--parallel', '4'], log=log, timeout=600)
    result = subprocess.run([str(project / 'build/Release/retro_gb_latency_checks.exe')],
        cwd=project, capture_output=True, text=True, timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    (project / 'checks.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    print(result.stdout + result.stderr)
    if result.returncode: raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
