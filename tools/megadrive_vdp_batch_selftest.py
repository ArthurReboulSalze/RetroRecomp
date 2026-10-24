"""Compare production scalar/batched VDP pixels and flags on authored data."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.megadrive_runtime import timing_vdp
from retrorecomp.platforms import cmake_target_args, build_executable, build_jobs


def main():
    work = ROOT/'.build/megadrive-vdp-batch-selftest'
    work.mkdir(parents=True, exist_ok=True)
    runner = ROOT/'.deps/segagenesisrecomp/runner'
    (work/'vdp.c').write_text(timing_vdp((runner/'video/genesis_vdp.c').read_text()), encoding='utf-8')
    (work/'retro_md_game.h').write_text('/* Authored patterns, no cartridge. */\n')
    (work/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdVdpBatchChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
foreach(PAL RANGE 0 1)
 foreach(BATCH RANGE 0 2)
  if(BATCH EQUAL 0)
   set(BATCHED 0)
  else()
   set(BATCHED 1)
  endif()
  if(BATCH EQUAL 2)
   set(REFERENCE 0)
  else()
   set(REFERENCE 1)
  endif()
  foreach(FIXTURE vdp_batch raster)
   set(NAME ${{FIXTURE}}_${{PAL}}_${{BATCH}})
   add_executable(${{NAME}} "{ROOT.as_posix()}/native/md_${{FIXTURE}}_checks.c" vdp.c)
   target_compile_definitions(${{NAME}} PRIVATE RR_MD_PAL=${{PAL}} GENESIS_BATCHED_PLANES=${{BATCHED}} RR_MD_REFERENCE_PIXELS=${{REFERENCE}})
   target_include_directories(${{NAME}} PRIVATE . "{ROOT.as_posix()}/native" "{runner.as_posix()}" "{runner.as_posix()}/video")
   if(MSVC)
    target_compile_options(${{NAME}} PRIVATE /utf-8)
   endif()
  endforeach()
 endforeach()
endforeach()
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', work, '-B', work/'build', '-G', generator, *cmake_target_args()], log=work/'build.log')
    run([cmake, '--build', work/'build', '--config', 'Release', '--parallel', build_jobs()], log=work/'build.log')
    results = []
    for pal in range(2):
        variants = []
        for batch in range(3):
            data = {name: json.loads(run([build_executable(work/'build', f'{name}_{pal}_{batch}')]).strip())
                    for name in ('vdp_batch', 'raster')}
            data['authored_benchmark']=json.loads(run([
                build_executable(work/'build',f'vdp_batch_{pal}_{batch}'),'--benchmark']).strip())
            variants.append(data)
        assert len({v['vdp_batch']['hash'] for v in variants})==1, variants
        assert all(v['raster']==variants[0]['raster'] for v in variants), variants
        assert len({v['authored_benchmark']['sample'] for v in variants})==1, variants
        results.append(dict(standard='PAL' if pal else 'NTSC', scalar=variants[0], batched=variants[1], packed_sse2=variants[2]))
    result = dict(passed=True, pixels_and_flags_equal=True, results=results, gameplay_tested=False)
    (work/'results.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
