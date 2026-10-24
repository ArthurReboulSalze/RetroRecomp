"""ROM-free SRAM bus fixtures and fresh-process Windows persistence checks."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.megadrive_sram import bus_header, bus_source
from retrorecomp.megadrive_memory import runtime_source


def main():
    project = ROOT / '.build/megadrive-sram-selftest'
    project.mkdir(parents=True, exist_ok=True)
    engine = ROOT / '.deps/segagenesisrecomp/runner'
    runtime = project / 'runtime'
    shutil.copytree(engine, runtime, dirs_exist_ok=True)
    header = runtime / 'video/genesis_bus.h'
    header.write_text(bus_header(header.read_text()), encoding='utf-8')
    source = runtime / 'video/genesis_bus.c'
    source.write_text(runtime_source(bus_source(source.read_text()), 'bus'), encoding='utf-8')
    (project / 'retro_md_game.h').write_text('#define RR_MD_ROM_BYTES 0x100000u\n', encoding='ascii')
    (project / 'retro16_state_config.h').write_text(
        '#define RR16_STATE_NAME "Authored SRAM"\n#define RR16_STATE_ROM "' + 'ab'*32 + '"\n', encoding='ascii')
    shutil.copy2(ROOT / 'native/md_battery.h', project / 'md_battery.h')
    shutil.copy2(ROOT / 'native/md_battery.c', project / 'md_battery.c')
    stubs = (ROOT/'native/md_sram_checks.c').read_text().split('static GenesisBus bus;')[0]
    (project/'baseline.c').write_text(stubs + '''int main(int argc,char **argv) {
    GenesisBus bus; gbus_init(&bus,NULL);
    if(argc>1) { gbus_write16(&bus,0xe01234,0x1234);
        CHECK(gbus_read16(&bus,0xff1234)==0x1234); return 0; }
    g_rom[0x1b0]='R'; g_rom[0x1b1]='A'; g_rom[0x1b2]=0xf8; g_rom[0x1b3]=0x20;
    g_rom[0x1b5]=0x20; g_rom[0x1b7]=1; g_rom[0x1b9]=0x20; g_rom[0x1bb]=7;
    gbus_sram_setup(&bus); gbus_write8(&bus,0xa130f1,1);
    gbus_write8(&bus,0x200001,0x34);
    CHECK(gbus_read16(&bus,0x200000)==0xff34);
    return 0;
}
''', encoding='utf-8')
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdSramChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{ROOT.as_posix()}/native/md_sram_checks.c" runtime/video/genesis_bus.c md_battery.c)
target_include_directories(checks PRIVATE . runtime "{ROOT.as_posix()}/native")
target_compile_options(checks PRIVATE /utf-8)
add_executable(baseline baseline.c "{engine.as_posix()}/video/genesis_bus.c")
target_include_directories(baseline PRIVATE . "{engine.as_posix()}")
target_compile_options(baseline PRIVATE /utf-8)
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project/'build', '-G', generator, '-A', 'x64'], log=project/'build.log')
    run([cmake, '--build', project/'build', '--config', 'Release', '--parallel', '4'], log=project/'build.log')
    exe = project/'build/Release/checks.exe'
    def check(*args):
        return json.loads(run([exe,*args]).strip())
    result = check()
    baseline = subprocess.run([project/'build/Release/baseline.exe'],capture_output=True,text=True)
    assert baseline.returncode == 1 and 'gbus_read16(&bus,0x200000)==0xff34' in baseline.stderr
    result['upstream_parallel_ram_regression_reproduced'] = True
    mirror = subprocess.run([project/'build/Release/baseline.exe','mirror'],capture_output=True,text=True)
    assert mirror.returncode == 1 and 'gbus_read16(&bus,0xff1234)==0x1234' in mirror.stderr
    result['upstream_work_ram_mirror_regression_reproduced'] = True
    with tempfile.TemporaryDirectory(prefix='rr-sram-') as temp:
        root = Path(temp)
        for mode in ('unchanged','headless','volatile','reverted'):
            path = root/mode/'datas/saves/authored.rrsram'
            check(mode,str(path))
            assert not path.parent.exists(), mode
        path = root/'writes/datas/saves/authored.rrsram'
        check('write',str(path))
        original = path.read_bytes(); stamp = path.stat().st_mtime_ns
        assert len(original) == 112+8192
        check('read',str(path))
        assert path.read_bytes() == original and path.stat().st_mtime_ns == stamp
        # Rejected files leave both live blank RAM and the disk bytes untouched.
        invalid = [original[:-1], original+b'x']
        for offset in (8,12,16,20,24,32,40,112):
            invalid.append(original[:offset]+bytes([original[offset]^1])+original[offset+1:])
        for payload in invalid:
            path.write_bytes(payload); check('invalid',str(path)); assert path.read_bytes() == payload
        deferred = root/'deferred/datas/saves/authored.rrsram'
        check('deferred',str(deferred)); assert deferred.read_bytes() == original
        blocked = root/'file-not-directory'; blocked.write_bytes(b'preserve')
        check('blocked',str(blocked/'authored.rrsram')); assert blocked.read_bytes() == b'preserve'
        assert not list(root.rglob('*.tmp'))
        result.update(persistence_bytes=len(original), fresh_process_reload=True,
            unchanged_headless_volatile_reverted_create_nothing=True, invalid_files_rejected=len(invalid),
            deferred_atomic_writes=True, blocked_write_reported=True)
    (project/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
