"""Check exact tile rows/Scale2x pixels against previous scalar renderers."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrorecomp.core import run,toolchain
from retrorecomp.platforms import build_executable,build_jobs,cmake_target_args

def main():
    project=ROOT/'.build/pixel-optimization-selftest';project.mkdir(parents=True,exist_ok=True)
    (project/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.21)
project(PresentationChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
foreach(mode optimized scalar)
  add_executable(${{mode}} "{ROOT.as_posix()}/native/pixel_optimization_checks.c")
  target_include_directories(${{mode}} PRIVATE "{ROOT.as_posix()}/tests/fixtures/presentation")
endforeach()
target_compile_definitions(scalar PRIVATE RR_SCALE2X_SCALAR=1 RR_STEREO_FIR_SCALAR=1)
''')
    cmake,generator=toolchain();log=project/'build.log'
    run([cmake,'-S',project,'-B',project/'build','-G',generator,*cmake_target_args()],log=log)
    run([cmake,'--build',project/'build','--config','Release','--parallel',build_jobs()],log=log)
    results={mode:json.loads(run([build_executable(project/'build',mode)],timeout=120)) for mode in ('optimized','scalar')}
    assert all(r['passed'] for r in results.values())
    (project/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))
if __name__=='__main__':main()
