"""Build and run the ROM-free check of the Neo Geo fix-layer edge-mask detector (native/neogeo_fixmask.h)."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args
from retrorecomp.core import toolchain,run


def main():
    p=ROOT/'.build/neogeo-fixmask-selftest';p.mkdir(parents=True,exist_ok=True)
    # Assertions remain enabled in the Release executable.
    (p/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(NeoGeoFixMask C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{(ROOT/'native/neogeo_fixmask_checks.c').as_posix()}")
target_include_directories(checks PRIVATE "{(ROOT/'native').as_posix()}")
target_compile_options(checks PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8;/UNDEBUG;/W4>" "$<$<NOT:$<C_COMPILER_ID:MSVC>>:-Wall;-Wextra;-UNDEBUG>")
''',encoding='utf-8')
    cmake,generator=toolchain()
    run([cmake,'-S',p,'-B',p/'build','-G',generator,*cmake_target_args()],log=p/'build.log')
    run([cmake,'--build',p/'build','--config','Release','--parallel','4'],log=p/'build.log')
    result=run([build_executable(p/'build','checks')]);(p/'result.json').write_text(result,encoding='utf-8');print(result.strip())
if __name__=='__main__':main()
