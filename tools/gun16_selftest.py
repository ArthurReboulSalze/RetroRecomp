"""Build authored 16-bit gun fixtures against the pinned controller headers.

No commercial ROM, GUI window or gameplay capture is used.
"""
from pathlib import Path
import json
import shutil
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.core import run, toolchain
from smsrecomp.gun16_runtime import snes_joypad


def main():
    results = []
    for kind in (0, 1, 2, 3):
        project = ROOT / '.build' / f'gun16-checks-{kind}'
        project.mkdir(parents=True, exist_ok=True)
        for name in ('gun16.h', 'gun16.c', 'retro_console16.h', 'md_timing.h', 'snes_timing.h', 'gun16_checks.c'):
            shutil.copy2(ROOT / 'native' / name, project / name)
        (project / 'retro_md_game.h').write_text(
            '#define RR_MD_PAL 0\n#define RR_MD_SIX_BUTTONS 0\n', encoding='ascii')
        (project / 'retro_snes_game.h').write_text('#define RR_SN_PAL 0\n', encoding='ascii')
        (project / 'retro_gun_game.h').write_text(
            f'#define RR16_GUN {kind}\n#define RR16_GUN_X_OFFSET {82 if kind == 1 else 0}\n'
            '#define RR16_GUN_Y_OFFSET 0\n', encoding='ascii')
        engine = ROOT / '.deps' / ('segagenesisrecomp' if kind < 3 else 'snesrecomp')
        prefix = engine.as_posix()
        extra = ''
        if kind < 3:
            includes = f'"{prefix}/runner/include" "{prefix}/runner" "{prefix}/runner/external/superzazu"'
        else:
            shutil.copytree(engine / 'runner/src/snes', project / 'snes', dirs_exist_ok=True)
            shutil.copy2(engine / 'runner/src/types.h', project / 'types.h')
            ppu = project / 'snes/ppu.h'
            ppu.write_text(ppu.read_text(encoding='utf-8').replace('typedef struct PpuPixelPrioBufs {',
                'typedef struct __declspec(align(8)) PpuPixelPrioBufs {').replace(
                '} __attribute__((aligned(8))) PpuPixelPrioBufs;', '} PpuPixelPrioBufs;'), encoding='utf-8')
            joypad = project / 'snes/joypad.c'
            joypad.write_text(snes_joypad(joypad.read_text(encoding='utf-8')), encoding='utf-8')
            includes = f'"{prefix}/runner/src"'
            extra = 'snes/joypad.c'
        (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroGun16Checks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks gun16_checks.c gun16.c {extra})
target_include_directories(checks PRIVATE . {includes})
target_compile_definitions(checks PRIVATE RR16_MD={int(kind < 3)})
target_compile_options(checks PRIVATE /utf-8 /wd4996)
''', encoding='utf-8')
        cmake, generator = toolchain()
        run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64'], log=project / 'build.log')
        run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=project / 'build.log')
        results.append(json.loads(run([project / 'build/Release/checks.exe']).strip()))
    (ROOT / '.build/gun16-results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
