"""Optimize Linux hardware helpers without changing guest execution or checks."""
from pathlib import Path
import json
import shutil
import tempfile
import time

from .core import ConversionError, run
from .platforms import build_executable, build_jobs, cmake_target_args

CMAKE = r'''
# Keep large cartridge translations in ordinary objects. Cross-file
# optimization and profiles belong to the hot hardware helpers only.
set(RR16_PGO_AVAILABLE FALSE CACHE INTERNAL "Hardware profile support" FORCE)
set(RR16_PROFILE_MODE "" CACHE STRING "Private hardware profile mode")
set(RR16_PROFILE_DIR "" CACHE PATH "Private hardware profile directory")
if(UNIX AND CMAKE_C_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
  include(CheckIPOSupported)
  check_ipo_supported(RESULT _rr16_ipo LANGUAGES C CXX)
  if(_rr16_ipo)
    set(RR16_PGO_AVAILABLE TRUE CACHE INTERNAL "Hardware profile support" FORCE)
    get_target_property(RR16_SOURCES game SOURCES)
    foreach(RR16_SOURCE IN LISTS RR16_SOURCES)
      if(RR16_SOURCE MATCHES "\\.(c|cpp)$" AND NOT RR16_SOURCE MATCHES "(^|/)(generated|steps)/" AND NOT RR16_SOURCE MATCHES "md_z80_generated\\.c$")
        set_property(SOURCE "${RR16_SOURCE}" APPEND PROPERTY COMPILE_OPTIONS -flto=2)
        if(RR16_PROFILE_MODE STREQUAL "generate" OR RR16_PROFILE_MODE STREQUAL "use")
          set_property(SOURCE "${RR16_SOURCE}" APPEND PROPERTY COMPILE_OPTIONS "-fprofile-${RR16_PROFILE_MODE}=${RR16_PROFILE_DIR}")
        endif()
        if(RR16_PROFILE_MODE STREQUAL "use")
          set_property(SOURCE "${RR16_SOURCE}" APPEND PROPERTY COMPILE_OPTIONS -fprofile-partial-training -Werror=coverage-mismatch)
        endif()
      endif()
    endforeach()
    target_link_options(game PRIVATE -flto=2)
    if(RR16_PROFILE_MODE STREQUAL "generate" OR RR16_PROFILE_MODE STREQUAL "use")
      target_link_options(game PRIVATE "-fprofile-${RR16_PROFILE_MODE}=${RR16_PROFILE_DIR}")
    endif()
  endif()
endif()
'''


def build_game(project: Path, cmake: Path, generator: str, sdl: Path, emit) -> None:
    with tempfile.TemporaryDirectory(prefix='hardware-profile-', dir=project) as temporary:
        profile = Path(temporary)

        def build(mode):
            run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args(),
                 f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}', f'-DRR16_PROFILE_MODE={mode}',
                 f'-DRR16_PROFILE_DIR={profile.as_posix()}'], log=project / 'build.log', timeout=600)
            run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'game',
                 '--parallel', build_jobs()], log=project / 'build.log', timeout=1800)

        build('generate')
        cache = (project / 'build/CMakeCache.txt').read_text(encoding='utf-8')
        enabled = 'RR16_PGO_AVAILABLE:INTERNAL=TRUE' in cache
        seconds = 0.0
        if enabled:
            emit('Linux: optimizing hardware helpers on a short native run; full validation follows.')
            training = profile / 'training'
            training.mkdir()
            private_game = training / 'game'
            shutil.copy2(build_executable(project / 'build', 'game'), private_game)
            start = time.perf_counter()
            # No UI, host audio, or ordinary saves. Compiler counters are
            # private temporary data, never shared compilation knowledge.
            report = training / 'report.json'
            run([private_game, '--frames', '600', '--play', '--report', report], cwd=training,
                log=project / 'build.log', timeout=600)
            result = json.loads(report.read_text(encoding='utf-8'))
            if result.get('frames') != 600 or not any(profile.rglob('*.gcda')):
                raise ConversionError('Linux hardware profiling did not complete. The training executable will not be exported.')
            seconds = time.perf_counter() - start
            build('use')
            cache = (project / 'build/CMakeCache.txt').read_text(encoding='utf-8')
            if 'RR16_PROFILE_MODE:STRING=use' not in cache:
                raise ConversionError('Refusing to export an instrumented training executable.')
        (project / 'hardware-optimization.json').write_text(json.dumps({
            'profile_guided': enabled, 'training_frames': 600 if enabled else 0,
            'training_seconds': seconds,
        }, indent=2), encoding='utf-8')
