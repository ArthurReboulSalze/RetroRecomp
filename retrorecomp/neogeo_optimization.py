"""Optimize the hardware code of the native Neo Geo game without changing guest execution or checks.

Windows (portable llvm-mingw): ThinLTO and a clang instrumentation profile for the engine (Geolith's video chip, YM2610,
Z80, bus) and the host code. The generated cartridge translation (`steps/`) stays in ordinary objects. The profile only
chooses code layout and inlining, never semantics: the validation that follows runs on the faster executable and compares
it with the interpreted reference as before. RETRO_RECOMP_PGO=0 turns it off; where the training run fails the game is
built without a profile.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from . import timings

# Frames of the private training run: the longest standard route (boot, demo, credit, Start, play) reaches the sprite,
# fix-layer and sound paths of an ordinary session.
TRAINING_ROUTE = 'play'

# Appended to the generated CMakeLists of a native project, after every source is known. The cartridge translation is
# left out of the instrumentation (large, and the training run only chooses layout for the hardware helpers).
CMAKE = r'''
set(NG_PROFILE_MODE "" CACHE STRING "Private hardware profile mode")
set(NG_PROFILE_DIR "" CACHE PATH "Private hardware profile directory")
set(NG_PROFILE_DATA "" CACHE FILEPATH "Merged clang profile of this project")
set(NG_PGO_AVAILABLE FALSE CACHE INTERNAL "Hardware profile support" FORCE)
if(WIN32 AND CMAKE_C_COMPILER_ID STREQUAL "Clang" AND (NG_PROFILE_MODE STREQUAL "generate" OR NG_PROFILE_MODE STREQUAL "use"))
  set(NG_PGO_AVAILABLE TRUE CACHE INTERNAL "Hardware profile support" FORCE)
  foreach(NG_TARGET ng_hardware game)
    get_target_property(NG_SOURCES ${NG_TARGET} SOURCES)
    foreach(NG_SOURCE IN LISTS NG_SOURCES)
      if(NG_SOURCE MATCHES "\\.c$" AND NOT NG_SOURCE MATCHES "(^|/)steps/")
        if(NG_PROFILE_MODE STREQUAL "generate")
          set_property(SOURCE "${NG_SOURCE}" APPEND PROPERTY COMPILE_OPTIONS "-fprofile-instr-generate=${NG_PROFILE_DIR}/ng-%p.profraw")
        else()
          set_property(SOURCE "${NG_SOURCE}" APPEND PROPERTY COMPILE_OPTIONS "-fprofile-instr-use=${NG_PROFILE_DATA}"
                       -Wno-profile-instr-unprofiled -Wno-profile-instr-out-of-date)
        endif()
      endif()
    endforeach()
  endforeach()
  if(NG_PROFILE_MODE STREQUAL "generate")
    target_link_options(game PRIVATE "-fprofile-instr-generate=${NG_PROFILE_DIR}/ng-%p.profraw")
  endif()
endif()
'''


def clang_profile() -> Path | None:
    """llvm-profdata of the portable toolchain when this conversion can use a clang profile (Windows, llvm-mingw),
    else None."""
    if os.name != 'nt' or os.environ.get('RETRO_RECOMP_PGO', '1').strip() == '0':
        return None
    from . import toolchain
    if toolchain.active() != toolchain.LLVM:
        return None
    tool = toolchain.tools_directory() / 'llvm-mingw' / 'bin' / 'llvm-profdata.exe'
    return tool if tool.is_file() else None


def build_game(project: Path, plain, training: tuple[int, Path, list[str]] | None, emit=print) -> Path:
    """Build the native `game` target with a profile when possible, else as `plain(project, 'game', ())` does.

    `training` is (frames, input script, extra game arguments) of the private run, or None. `plain` is the ordinary
    build function: it takes the project, the target and extra CMake arguments and returns the executable."""
    from .conversion_common import spawn
    from .core import ConversionError, run

    tool = clang_profile() if training else None
    if tool is None:
        return plain(project, 'game', ())
    frames, script, arguments = training
    profile_data = project / 'hardware-profile.profdata'

    def configure(mode, profile):
        return (f'-DNG_PROFILE_MODE={mode}', f'-DNG_PROFILE_DIR={profile.as_posix()}',
                f'-DNG_PROFILE_DATA={profile_data.as_posix()}')

    seconds = 0.0
    enabled = False
    with tempfile.TemporaryDirectory(prefix='hardware-profile-', dir=project) as temporary:
        profile = Path(temporary)
        try:
            emit('Windows: optimizing the hardware code on a short native run; full validation follows.')
            start = time.perf_counter()
            with timings.phase('profile_training'):
                instrumented = plain(project, 'game', configure('generate', profile))
                training_folder = profile / 'training'
                training_folder.mkdir()
                private_game = training_folder / 'game.exe'
                shutil.copy2(instrumented, private_game)
                report = training_folder / 'report.json'
                result = spawn([str(private_game), '--headless', *arguments, '--frames', str(frames), '--script', str(script),
                                '--rtc-seed', '1760000000', '--report', str(report)], cwd=training_folder,
                               timeout=max(600, frames / 60 * 12), capture_output=True)
                if result.returncode or json.loads(report.read_text(encoding='utf-8')).get('frames') != frames:
                    raise ConversionError('Hardware profiling did not complete.')
                counters = list(profile.rglob('*.profraw'))
                if not counters:
                    raise ConversionError('Hardware profiling produced no counters.')
                profile_data.unlink(missing_ok=True)
                run([tool, 'merge', f'-output={profile_data.as_posix()}', *counters], log=project / 'build.log',
                    timeout=600)
                if not profile_data.is_file():
                    raise ConversionError('Hardware profiling produced no profile.')
            seconds = time.perf_counter() - start
            enabled = True
            binary = plain(project, 'game', configure('use', profile))
            cache = (project / 'build/CMakeCache.txt').read_text(encoding='utf-8')
            if 'NG_PROFILE_MODE:STRING=use' not in cache:
                raise ConversionError('Refusing to export an instrumented training executable.')
        except (ConversionError, OSError, ValueError, subprocess.TimeoutExpired) as error:
            # The profile only chooses code layout and inlining: where the training run fails (a build error of the
            # instrumented code, a game that stops early) the export is built without it, and the validation that
            # follows judges the game as it always did.
            emit('Windows: no hardware profile (' + str(error).splitlines()[0] + ') - ordinary build.')
            profile_data.unlink(missing_ok=True)
            enabled = False
            binary = plain(project, 'game', configure('', profile))
    (project / 'hardware-optimization.json').write_text(json.dumps({
        'profile_guided': enabled, 'training_route': TRAINING_ROUTE if enabled else None,
        'training_frames': frames if enabled else 0, 'training_seconds': seconds,
        **({'compiler_profile': 'clang-thinlto'} if enabled else {}),
    }, indent=2), encoding='utf-8')
    return binary
