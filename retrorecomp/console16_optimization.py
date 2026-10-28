"""Optimize the hardware code of 16-bit consoles without changing guest execution or checks.

Linux (GCC, LTO and profile guided): every console of this module.
Windows (portable llvm-mingw): the Super Nintendo only, ThinLTO and a clang instrumentation
profile, `clang_profile()`; RETRO_RECOMP_PGO=0 turns it off.
"""
from pathlib import Path
import json
import os
import shutil
import tempfile
import time

from . import timings
from .core import ConversionError, run
from .platforms import build_executable, build_jobs, cmake_target_args

# Frames of the private training run. The Windows Super Nintendo run is longer: a 600-frame
# boot of the Super FX games has not yet started the code that dominates their frames (Doom
# reaches its first level near frame 1,500); measured, 600 frames give half the gain of 1,800.
TRAINING_FRAMES = 600
CLANG_TRAINING_FRAMES = 1800

CMAKE = r'''
# Keep large cartridge translations in ordinary objects. Cross-file
# optimization and profiles belong to the hot hardware helpers only.
set(RR16_PGO_AVAILABLE FALSE CACHE INTERNAL "Hardware profile support" FORCE)
set(RR16_PROFILE_MODE "" CACHE STRING "Private hardware profile mode")
set(RR16_PROFILE_DIR "" CACHE PATH "Private hardware profile directory")
set(RR16_PROFILE_DATA "" CACHE FILEPATH "Merged clang profile of this project")
option(RR16_CLANG_PGO "ThinLTO and clang instrumentation profiles (Windows llvm-mingw)" OFF)
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
elseif(WIN32 AND RR16_CLANG_PGO AND CMAKE_C_COMPILER_ID STREQUAL "Clang")
  # Same split as above: the cartridge translation stays in ordinary objects, the hardware
  # code (the engine's sources) gets ThinLTO and the profile. A function the training run
  # never reached, or whose body differs, is compiled without profile data (a warning, never
  # an error): the profile only chooses code layout and inlining, not semantics.
  set(RR16_PGO_AVAILABLE TRUE CACHE INTERNAL "Hardware profile support" FORCE)
  get_target_property(RR16_SOURCES game SOURCES)
  foreach(RR16_SOURCE IN LISTS RR16_SOURCES)
    if(RR16_SOURCE MATCHES "\\.(c|cpp)$" AND NOT RR16_SOURCE MATCHES "(^|/)(generated|steps)/" AND NOT RR16_SOURCE MATCHES "md_z80_generated\\.c$")
      set_property(SOURCE "${RR16_SOURCE}" APPEND PROPERTY COMPILE_OPTIONS -flto=thin)
      if(RR16_PROFILE_MODE STREQUAL "generate")
        set_property(SOURCE "${RR16_SOURCE}" APPEND PROPERTY COMPILE_OPTIONS "-fprofile-instr-generate=${RR16_PROFILE_DIR}/rr-%p.profraw")
      endif()
      if(RR16_PROFILE_MODE STREQUAL "use")
        set_property(SOURCE "${RR16_SOURCE}" APPEND PROPERTY COMPILE_OPTIONS "-fprofile-instr-use=${RR16_PROFILE_DATA}"
                     -Wno-profile-instr-unprofiled -Wno-profile-instr-out-of-date)
      endif()
    endif()
  endforeach()
  target_link_options(game PRIVATE -flto=thin)
  if(RR16_PROFILE_MODE STREQUAL "generate")
    target_link_options(game PRIVATE "-fprofile-instr-generate=${RR16_PROFILE_DIR}/rr-%p.profraw")
  endif()
endif()
'''


def clang_profile(system_id=None):
    """llvm-profdata of the portable toolchain when this conversion uses ThinLTO and a clang
    profile (Windows, llvm-mingw, Super Nintendo), else None."""
    if os.name != 'nt' or system_id != 'snes' or os.environ.get('RETRO_RECOMP_PGO', '1').strip() == '0':
        return None
    from . import toolchain
    if toolchain.active() != toolchain.LLVM:
        return None
    tool = toolchain.tools_directory() / 'llvm-mingw' / 'bin' / 'llvm-profdata.exe'
    return tool if tool.is_file() else None


def build_game(project: Path, cmake: Path, generator: str, sdl: Path, emit, system_id=None) -> None:
    clang = clang_profile(system_id)
    frames = CLANG_TRAINING_FRAMES if clang else TRAINING_FRAMES
    # Outside the temporary folder: later rebuilds in this build folder (the checks tools edit and
    # recompile a source) must still find it, and clang refuses a missing profile.
    profile_data = project / 'hardware-profile.profdata'
    with tempfile.TemporaryDirectory(prefix='hardware-profile-', dir=project) as temporary:
        profile = Path(temporary)

        def build(mode):
            with timings.phase('compile'):
                run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args(),
                     f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}', f'-DRR16_PROFILE_MODE={mode}',
                     f'-DRR16_PROFILE_DIR={profile.as_posix()}', f'-DRR16_CLANG_PGO={"ON" if clang else "OFF"}',
                     f'-DRR16_PROFILE_DATA={profile_data.as_posix()}'],
                    log=project / 'build.log', timeout=600)
                run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'game',
                     '--parallel', build_jobs()], log=project / 'build.log', timeout=1800)

        def train():
            """The private training run; returns its counters. Any shortfall raises."""
            training = profile / 'training'
            training.mkdir()
            private_game = training / 'game'
            shutil.copy2(build_executable(project / 'build', 'game'), private_game)
            # No UI, host audio, or ordinary saves. Compiler counters are
            # private temporary data, never shared compilation knowledge.
            report = training / 'report.json'
            run([private_game, '--frames', str(frames), '--play', '--report', report], cwd=training,
                log=project / 'build.log', timeout=1200)
            result = json.loads(report.read_text(encoding='utf-8'))
            counters = list(profile.rglob('*.profraw' if clang else '*.gcda'))
            if result.get('frames') != frames or not counters:
                raise ConversionError('Hardware profiling did not complete. The training executable will not be exported.')
            if clang:
                profile_data.unlink(missing_ok=True)
                run([clang, 'merge', f'-output={profile_data.as_posix()}', *counters],
                    log=project / 'build.log', timeout=600)
                if not profile_data.is_file():
                    raise ConversionError('Hardware profiling produced no profile. The training executable will not be exported.')

        build('generate')
        cache = (project / 'build/CMakeCache.txt').read_text(encoding='utf-8')
        enabled = 'RR16_PGO_AVAILABLE:INTERNAL=TRUE' in cache
        seconds = 0.0
        if enabled:
            emit(('Windows: optimizing the hardware code on a short native run; full validation follows.' if clang else
                  'Linux: optimizing hardware helpers on a short native run; full validation follows.'))
            start = time.perf_counter()
            try:
                with timings.phase('profile_training'):
                    train()
            except ConversionError as error:
                if not clang:
                    raise
                # The profile only chooses code layout and inlining. Where the training run fails (a
                # game that stops before the training frames, a missing tool) the export is built
                # without it; the validation that follows judges the game as it always did.
                emit('Windows: no hardware profile (' + str(error).splitlines()[0] + ') - ordinary build.')
                profile_data.unlink(missing_ok=True)
                clang = None
                enabled = False
                build('')
            else:
                seconds = time.perf_counter() - start
                build('use')
                cache = (project / 'build/CMakeCache.txt').read_text(encoding='utf-8')
                if 'RR16_PROFILE_MODE:STRING=use' not in cache:
                    raise ConversionError('Refusing to export an instrumented training executable.')
        (project / 'hardware-optimization.json').write_text(json.dumps({
            'profile_guided': enabled, 'training_frames': frames if enabled else 0,
            'training_seconds': seconds, **({'compiler_profile': 'clang-thinlto'} if enabled and clang else {}),
        }, indent=2), encoding='utf-8')
