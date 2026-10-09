"""Compare guarded AOT RAM helpers with the pinned internal SM83 reference."""
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.core import run
from smsrecomp.gameboy import _dependencies
from smsrecomp.gameboy_runtime import adapt_generated_project
from smsrecomp.paths import ASSETS

def main():
    project = ROOT / '.build/gb-ram-selftest'
    project.mkdir(parents=True, exist_ok=True)
    rom = bytearray(32768)
    # 65,535 guest calls/returns before enabling the LCD. Native host recursion
    # must stay bounded even when no frame/interrupt can end the loop.
    rom[0x100:0x116] = bytes.fromhex('f3 af e0 40 11 ff ff cd 20 01 1b 7a b3 20 f8 3e 91 e0 40 76 18 fd')
    rom[0x120] = 0xC9
    (project / 'fixture.gb').write_bytes(rom)
    engine, compiler, sdl, cmake, generator = _dependencies(print)
    log = project / 'build.log'
    run([compiler, project / 'fixture.gb', '-o', project, '--runtime-dir', engine / 'runtime',
         '--output-prefix', 'game', '--no-comments'], log=log, timeout=600)
    adapt_generated_project(project, 'ram-fixture', '0' * 64, 'Authored RAM fixture')
    (project / 'game_resources.rc').write_text('1 RCDATA { 0 }\n', encoding='utf-8')
    with (project / 'CMakeLists.txt').open('a', encoding='utf-8') as out:
        out.write(f'''\nadd_executable(retro_gb_ram_checks "{(ASSETS / 'native/gb_ram_checks.c').as_posix()}")
target_link_libraries(retro_gb_ram_checks PRIVATE gbrt)
''')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64',
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=log)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--target',
         'retro_gb_ram_checks', 'game', '--parallel', '4'], log=log, timeout=600)
    output = run([project / 'build/Release/retro_gb_ram_checks.exe'], timeout=180)
    (project / 'checks.log').write_text(output, encoding='utf-8')
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    from smsrecomp.gameboy import CPU_MATCH
    executable = project / 'build/Release/game.exe'
    cpu = run([executable, '--differential', '--differential-frames', '1'], timeout=180)
    assert CPU_MATCH.search(cpu), cpu
    native = run([executable, '--headless', '--limit-frames', '1',
                  '--dump-state', project / 'trampoline-state.json'], timeout=180)
    assert '[LIMIT] Reached frame limit 1' in native, native
    state = json.loads((project / 'trampoline-state.json').read_text(encoding='utf-8'))
    expected = {'d': 0, 'e': 0, 'sp': 65534, 'pc': 276,
                'cycles': 4522088, 'dispatch_fallbacks': 0}
    assert all(state.get(key) == value for key, value in expected.items()), {
        key: state.get(key) for key in expected}
    result['long_guest_loop'] = {'guest_calls': 65535, 'host_stack_bounded': True,
                                'final_native_state': expected,
                                'cpu_comparison': CPU_MATCH.search(cpu).group(0)}
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)

if __name__ == '__main__':
    main()
