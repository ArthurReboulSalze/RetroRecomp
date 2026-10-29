"""ROM-free 65816 static-operation, register-width and live-bus checks."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args
from retrorecomp.core import run, toolchain
from retrorecomp.snes_codegen import native_source, adapt_core, mirrored_rom, read_core
from retrorecomp.console16 import snes_ppu_header


def main():
    engine = ROOT / '.deps/snesrecomp'
    project = ROOT / '.build/snes-native-selftest'
    project.mkdir(exist_ok=True, parents=True)
    staged = project / 'engine/runner'
    shutil.copytree(engine / 'runner', staged, dirs_exist_ok=True)
    ppu = staged / 'src/snes/ppu.h'
    ppu.write_text(snes_ppu_header(ppu.read_text(encoding='utf-8')), encoding='utf-8')
    # Three authored 32 KiB blocks also exercise the loader's non-power-of-two
    # storage. Put the opcode grid in each mapping's first visible CPU window.
    rom = bytearray([0xea] * 0x18000)
    for opcode in range(256):
        rom[opcode * 8:opcode * 8 + 4] = bytes((opcode, 0x34, 0x12, 0))
        rom[0x8000 + opcode * 8:0x8000 + opcode * 8 + 4] = bytes((opcode, 0x34, 0x12, 0))
    rom[0x7fff] = rom[0xffff] = 0xa9
    # Distinct software-interrupt vectors (native COP $FFE4, native BRK $FFE6, emulation
    # COP $FFF4; emulation BRK $FFFE keeps the $A9 byte above, so it reads $A9FE) in the
    # last bytes of the first bank under either mapping.
    for base in (0x7fe4, 0xffe4):
        rom[base:base + 4] = bytes((0xe4, 0xc0, 0xe6, 0xc0))
        rom[base + 0x10:base + 0x12] = bytes((0xf4, 0xc0))
        rom[base + 0x1a] = 0xfe
    (project / 'fixture_rom.h').write_text(
        f'#define FIXTURE_IMAGE_BYTES {len(rom)}u\n'
        'static const unsigned char fixture_rom[] = {' +
        ','.join(map(str, mirrored_rom(rom))) + '};\n', encoding='ascii')
    source = read_core(engine)
    guards = [{'address': 0x7e0100, 'bytes': 'a93412ea'}] + [
        {'address':0x7e1000+4*n,'bytes':'a93412ea'} for n in reversed(range(4096))] + [
        {'address': address, 'bytes': raw} for address, raw in (
            (0x7e2000, 'a93412ea'), (0x7e2000, 'ea3412ea'), (0x000300, 'a93412ea'), (0x7e0300, 'ea3412ea'))]
    (project / 'snes_native_ops.inc').write_text(native_source(source, rom, guards), encoding='utf-8')
    (project / 'snes_hirom_ops.inc').write_text(native_source(source, rom, guards, mapping='hirom'), encoding='utf-8')
    (project / 'interp816.c').write_text(adapt_core(source), encoding='utf-8')
    (project / 'interp816_hirom.c').write_text(adapt_core(source).replace(
        '#include "snes_native_ops.inc"', '#include "snes_hirom_ops.inc"'), encoding='utf-8')
    shutil.copy2(ROOT / 'native/snes_native_steps.h', project / 'snes_native_steps.h')
    shutil.copy2(ROOT / 'native/snes_cart.h', project / 'snes_cart.h')
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(SnesNativeChecks C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks interp816.c "{ROOT.as_posix()}/native/snes_cpu/interrupt_checks.c")
add_executable(checks_hirom interp816_hirom.c "{ROOT.as_posix()}/native/snes_cpu/interrupt_checks.c")
target_compile_definitions(checks PRIVATE FIXTURE_CART_TYPE=CART_LOROM)
target_compile_definitions(checks_hirom PRIVATE FIXTURE_CART_TYPE=CART_HIROM)
foreach(target checks checks_hirom)
  target_include_directories(${{target}} PRIVATE . "{staged.as_posix()}/src" "{staged.as_posix()}/src/snes")
  target_compile_options(${{target}} PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8;/wd4996>")
endforeach()
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=project / 'build.log')
    results = {mapping: json.loads(run([build_executable(project / 'build', f'{name}')]))
               for mapping, name in (('lorom', 'checks'), ('hirom', 'checks_hirom'))}
    # The executables first run BRK and COP in both modes against the manual (cycles, stack, vector) and
    # exit with a failure otherwise (native/snes_cpu/interrupt_checks.c): reaching here means they passed.
    for row in results.values():
        row['software_interrupt_cycles'] = 'passed'
    result = {'mappings': results, 'instruction_state_bus_comparisons':
              sum(row['instruction_state_bus_comparisons'] for row in results.values()),
              'passed': all(row['passed'] for row in results.values())}
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
