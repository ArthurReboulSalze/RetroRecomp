"""Numeric shared-settings check; no video driver or screen capture."""
from pathlib import Path
import sys,subprocess,shutil,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from smsrecomp.core import dependencies,run
def main():
    project=ROOT/'.build/display-settings-selftest'; project.mkdir(parents=True,exist_ok=True)
    _,sdl,cmake,generator=dependencies(lambda t:None)
    (project/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(DisplaySettings C)
find_package(SDL2 REQUIRED)
add_executable(checks "{(ROOT/'native/display_settings_checks.c').as_posix()}")
target_include_directories(checks PRIVATE "{(ROOT/'native').as_posix()}")
target_link_libraries(checks PRIVATE SDL2::SDL2-static)
target_compile_options(checks PRIVATE /utf-8)
''',encoding='utf-8')
    run([cmake,'-S',project,'-B',project/'build','-G',generator,'-A','x64',f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'],log=project/'build.log')
    run([cmake,'--build',project/'build','--config','Release','--parallel','4'],log=project/'build.log')
    with tempfile.TemporaryDirectory(prefix='rr-display-') as temp:
        print(run([project/'build/Release/checks.exe',Path(temp)/'Été settings']).strip())
if __name__=='__main__': main()
