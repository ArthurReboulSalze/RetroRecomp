"""Console-neutral CPU interface and Neo Geo normal-frame/bounds checks."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args
from retrorecomp.core import run,toolchain
from retrorecomp.megadrive_codegen import write_changed

def main():
    project=ROOT/'.build/neogeo-prototype-20261013/cpu-boundary'
    project.mkdir(parents=True,exist_ok=True)
    for name in ('m68000_backend.c','m68000_backend.h','m68000_state_helpers.h',
                 'neogeo_input.h','m68000_backend_checks.c'):
        write_changed(project/name,(ROOT/'native'/name).read_text(encoding='utf-8'))
    write_changed(project/'CMakeLists.txt','''cmake_minimum_required(VERSION 3.20)
project(RetroCpuBoundary C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks m68000_backend.c m68000_backend_checks.c)
target_compile_options(checks PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8;/W4;/WX>")
''')
    cmake,generator=toolchain()
    run([cmake,'-S',project,'-B',project/'build','-G',generator,*cmake_target_args()],log=project/'build.log')
    run([cmake,'--build',project/'build','--config','Release','--parallel','4'],log=project/'build.log')
    print(run([build_executable(project / 'build', 'checks')]))

if __name__=='__main__':main()
