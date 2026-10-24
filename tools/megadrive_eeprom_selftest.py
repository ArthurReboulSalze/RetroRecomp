"""Manufacturer-derived, ROM-free serial EEPROM transactions and edge replay."""
from pathlib import Path
import json
import sys
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp import megadrive_sram, megadrive_memory, megadrive_cart


def main():
    project = ROOT / '.build/megadrive-eeprom-selftest'
    project.mkdir(parents=True, exist_ok=True)
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdEepromChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{ROOT.as_posix()}/native/md_eeprom_checks.c")
target_include_directories(checks PRIVATE "{ROOT.as_posix()}/native")
target_compile_options(checks PRIVATE /utf-8 /W4)
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project/'build', '-G', generator, '-A', 'x64'], log=project/'build.log')
    run([cmake, '--build', project/'build', '--config', 'Release', '--parallel', '4'], log=project/'build.log')
    result = json.loads(run([project/'build/Release/checks.exe']).strip())
    bus_project = project / 'bus'
    bus_project.mkdir(exist_ok=True)
    runtime = bus_project / 'runtime'
    shutil.copytree(ROOT/'.deps/segagenesisrecomp/runner',runtime,dirs_exist_ok=True)
    header=runtime/'video/genesis_bus.h'
    header.write_text(megadrive_sram.bus_header(header.read_text()),encoding='utf-8')
    source=runtime/'video/genesis_bus.c'
    source.write_text(megadrive_cart.bus(megadrive_memory.runtime_source(
        megadrive_sram.bus_source(source.read_text()),'bus')),encoding='utf-8')
    for name in ('md_cart.h','md_cart.inc','md_eeprom.h','md_timing.h','md_battery.h','md_battery.c'):
        shutil.copy2(ROOT/'native'/name,bus_project/name)
    (bus_project/'retro_md_game.h').write_text('#define RR_MD_ROM_BYTES 0x200000u\n',encoding='ascii')
    (bus_project/'retro16_state_config.h').write_text(
        '#define RR16_STATE_NAME "Authored EEPROM"\n#define RR16_STATE_ROM "'+'cd'*32+'"\n',encoding='ascii')
    stubs=(ROOT/'native/md_sram_checks.c').read_text().split('static GenesisBus bus;')[0]
    (bus_project/'fixture.c').write_text(stubs+'\n'+(ROOT/'native/md_cart_checks.c').read_text(),encoding='utf-8')
    cmake_text='''cmake_minimum_required(VERSION 3.20)
project(RetroMdEepromBusChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
'''
    for kind in (1,2,3):
        cmake_text+=f'''add_executable(bus{kind} fixture.c runtime/video/genesis_bus.c md_battery.c)
target_include_directories(bus{kind} PRIVATE . runtime)
target_compile_options(bus{kind} PRIVATE /utf-8)
target_compile_definitions(bus{kind} PRIVATE RR_MD_EEPROM_KIND={kind} RR_MD_EEPROM_WIRING={kind})
'''
    (bus_project/'CMakeLists.txt').write_text(cmake_text,encoding='utf-8')
    run([cmake,'-S',bus_project,'-B',bus_project/'build','-G',generator,'-A','x64'],log=bus_project/'build.log')
    run([cmake,'--build',bus_project/'build','--config','Release','--parallel','3'],log=bus_project/'build.log')
    result['bus']=[]
    with tempfile.TemporaryDirectory(prefix='rr-eeprom-') as temp:
        root=Path(temp)
        for kind in (1,2,3):
            exe=bus_project/f'build/Release/bus{kind}.exe'
            result['bus'].append(json.loads(run([exe]).strip()))
            clean=root/f'clean{kind}/datas/saves/authored.rrsram'
            run([exe,'clean',clean]);assert not clean.parent.parent.exists()
            path=root/f'written{kind}/datas/saves/authored.rrsram'
            run([exe,'write',path]);payload=path.read_bytes();stamp=path.stat().st_mtime_ns
            run([exe,'read',path]);assert path.read_bytes()==payload and path.stat().st_mtime_ns==stamp
    result['fresh_process_battery_reload']=True
    result['clean_launch_creates_nothing']=True
    (project/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
