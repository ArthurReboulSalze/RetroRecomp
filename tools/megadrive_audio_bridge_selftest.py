"""Compare host resampling PCM with the pinned, unmodified bridge; no ROM."""
from pathlib import Path
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.platforms import build_executable, cmake_target_args, build_jobs
from retrorecomp.megadrive_audio import bridge


def main():
    project = ROOT / '.build/md-audio-bridge-selftest'
    project.mkdir(parents=True, exist_ok=True)
    original = (ROOT / '.deps/segagenesisrecomp/runner/recomp_audio_drc.h').read_text(encoding='utf-8')
    for name, text in (('reference', original), ('ntt', '#define RR_MD_AUDIO_NTT_ONLY 1\n'+bridge(original)),
                       ('optimized', bridge(original))):
        folder = project / name
        folder.mkdir(exist_ok=True)
        (folder / 'bridge.h').write_text(text, encoding='utf-8')
        for resource in ('md_audio_bridge_checks.c', 'md_audio_loop.inc', 'md_audio_resample.inc'):
            shutil.copy2(ROOT / 'native' / resource, folder / resource)
    for resource in ('md_audio_mix.h', 'md_audio_mix_checks.c'):
        shutil.copy2(ROOT / 'native' / resource, project / resource)
    (project / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.20)
project(MdAudioBridgeChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(mix md_audio_mix_checks.c)
foreach(name reference ntt optimized)
  add_executable(${name} ${name}/md_audio_bridge_checks.c)
  if(MSVC)
    target_compile_options(${name} PRIVATE /O2 /fp:precise)
  else()
    target_compile_options(${name} PRIVATE -O3)
    target_link_libraries(${name} PRIVATE m)
  endif()
endforeach()
''', encoding='utf-8')
    cmake, generator = toolchain()
    log = project / 'build.log'
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=log)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()], log=log)
    results = {name: json.loads(run([build_executable(project / 'build', name)], timeout=180))
               for name in ('reference', 'ntt', 'optimized')}
    for name in ('ntt','optimized'):
        for key in ('hash', 'searches', 'pulls', 'stretches'):
            if results['reference'][key] != results[name][key]:
                raise AssertionError(f'Host audio mismatch: {name}/{key}: {results}')
    assert results['optimized']['stretches'] > 0
    verification = json.loads(run([build_executable(project / 'build', 'optimized'), '--verify-transform'], timeout=180))
    assert verification['hash'] == results['reference']['hash']
    assert verification['transform_checks'] > 0
    results['exact_integer_dot_checks'] = verification['transform_checks']
    results['mixer'] = json.loads(run([build_executable(project / 'build', 'mix')], timeout=120))
    results['steady'] = {name: json.loads(run([build_executable(project / 'build', name), '--steady'], timeout=30))
                         for name in ('reference', 'optimized')}
    assert results['steady']['reference']['hash'] == results['steady']['optimized']['hash']
    (project / 'result.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
