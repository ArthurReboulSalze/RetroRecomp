"""Optimize GCC hardware code before fresh native/reference validation.

Instrumented programs are private training inputs only. The caller receives
control after the non-instrumented build succeeds, or an exception on failure.
"""
from pathlib import Path
import re
import shutil
import tempfile
import time

from . import timings
from .core import ConversionError, run
from .platforms import build_executable, build_jobs, cmake_target_args


def build_game(project: Path, cmake: Path, generator: str, sdl: Path,
               play_script: Path | None, emit) -> dict:
    configure_seconds = build_seconds = 0.0
    with tempfile.TemporaryDirectory(prefix='hardware-profile-', dir=project) as temporary:
        profile = Path(temporary)

        def build(mode):
            nonlocal configure_seconds, build_seconds
            start = time.perf_counter()
            with timings.phase('compile'):
                run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args(),
                     f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}', f'-DRR_NES_PROFILE_MODE={mode}',
                     f'-DRR_NES_PROFILE_DIR={profile.as_posix()}'], cwd=project,
                    log=project / 'build.log', timeout=600)
            configure_seconds += time.perf_counter() - start
            cache = (project / 'build/CMakeCache.txt').read_text(encoding='utf-8')
            training = mode == 'generate' and 'RR_NES_PGO_AVAILABLE:INTERNAL=TRUE' in cache
            start = time.perf_counter()
            with timings.phase('compile'):
                run([cmake, '--build', project / 'build', '--config', 'Release',
                     '--target', 'nes_profile' if training else 'game', '--parallel', build_jobs()],
                    cwd=project, log=project / 'build.log', timeout=1800)
            build_seconds += time.perf_counter() - start

        build('generate')
        cache = (project / 'build/CMakeCache.txt').read_text(encoding='utf-8')
        enabled = 'RR_NES_PGO_AVAILABLE:INTERNAL=TRUE' in cache
        training_seconds = 0.0
        if enabled:
            emit('NES Linux: optimizing hardware code with short boot/play profiles; fresh checks follow.')
            executable = build_executable(project / 'build', 'nes_profile')
            start = time.perf_counter()
            # Training cannot read or change a user's ordinary saves. PCM and
            # compiler counters are private temporary files, never knowledge.
            training = profile / 'training'
            training.mkdir()
            private_game = training / executable.name
            shutil.copy2(executable, private_game)
            for frames, script in ((240, None), (600, play_script)):
                command = [private_game, project / 'rom.nes', '--frames', str(frames),
                           '--wav-out', training / 'samples.wav']
                if script:
                    command += ['--input', script]
                with timings.phase('profile_training'):
                    output = run(command, cwd=training, log=project / 'build.log', timeout=600)
                if not re.search(rf'\bmode=native frames={frames}\b', output):
                    raise ConversionError('NES hardware profiling did not complete its bounded native run.')
            training_seconds = time.perf_counter() - start
            if not any(profile.rglob('*.gcda')):
                raise ConversionError('NES compiler produced no usable hardware profile; refusing to export the training build.')
            build('use')
            # A failed configure/rebuild propagates before the caller's normal
            # validation or export. Never hand back an instrumented program.
            cache = (project / 'build/CMakeCache.txt').read_text(encoding='utf-8')
            if 'RR_NES_PROFILE_MODE:STRING=use' not in cache:
                raise ConversionError('NES export is still configured for profiling.')
    return dict(configure_seconds=configure_seconds, build_seconds=build_seconds,
                hardware_profile_guided=enabled, profile_training_seconds=training_seconds,
                profile_frames=[240, 600] if enabled else [])
