"""Build and run the simplest ROM-free C self-tests with one CMake setup."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Callable, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class Target:
    name: str
    sources: tuple[str, ...]
    defines: tuple[str, ...] = ()
    include_dirs: tuple[str, ...] = ()
    compile_options: tuple[str, ...] = ()
    link_options: tuple[str, ...] = ()
    link_libraries: tuple[str, ...] = ()


def _quoted(path: Path | str) -> str:
    return '"' + Path(path).as_posix() + '"'


def _definition(value: str | tuple[str, str | int]) -> str:
    if isinstance(value, tuple):
        return f'{value[0]}={value[1]}'
    return value


def _target_lines(target: Target) -> list[str]:
    lines = [f'add_executable({target.name} ' + ' '.join(map(_quoted, target.sources)) + ')']
    if target.include_dirs:
        lines.append('target_include_directories(' + target.name + ' PRIVATE '
                     + ' '.join(map(_quoted, target.include_dirs)) + ')')
    if target.defines:
        definitions = ' '.join(_definition(value) for value in target.defines)
        lines.append(f'target_compile_definitions({target.name} PRIVATE {definitions})')
    if target.compile_options:
        options = ' '.join(target.compile_options)
        lines.append(f'target_compile_options({target.name} PRIVATE {options})')
    if target.link_options:
        options = ' '.join(target.link_options)
        lines.append(f'target_link_options({target.name} PRIVATE {options})')
    if target.link_libraries:
        libraries = ' '.join(target.link_libraries)
        lines.append(f'target_link_libraries({target.name} PRIVATE {libraries})')
    return lines


def compile_and_run(
    project: Path,
    sources: str | Path | Iterable[str | Path],
    defines: Iterable[str | tuple[str, str | int]] = (),
    *,
    target: str = 'checks',
    include_dirs: Iterable[str | Path] = (),
    requires_sdl: bool = False,
    sdl_config: str | None = 'CONFIG',
    sdl_func: Callable[[], Path] | None = None,
    link_libraries: Iterable[str] = (),
    link_options: Iterable[str] = (),
    compile_options: Iterable[str] = (),
    cmake_extras: str = '',
    cmake_version: str = '3.21',
    c_standard: int | None = 11,
    msvc_runtime: bool = True,
    arguments: Sequence[str | Path] = (),
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    timeout: int = 60,
    parallel: int = 4,
    log: Path | bool | None = None,
    combined_output: bool = True,
    toolchain_func: Callable[[], tuple[Path, str]] | None = None,
    target_args_func: Callable[[], list[str]] | None = None,
    executable_func: Callable[[Path, str], Path] | None = None,
    run_func: Callable[..., str] | None = None,
    process_func: Callable[..., subprocess.CompletedProcess] | None = None,
) -> str | subprocess.CompletedProcess:
    """Configure, build and run one check target; return its output or process.

    The callable parameters are test seams. Production callers use the normal
    Retro-Recomp toolchain helpers without importing a compiler here.
    """
    project = Path(project)
    project.mkdir(parents=True, exist_ok=True)
    if isinstance(sources, (str, Path)):
        source_tuple = (sources,)
    else:
        source_tuple = tuple(sources)
    check = Target(target, source_tuple, tuple(defines), tuple(include_dirs), tuple(compile_options),
                   tuple(link_options), tuple(link_libraries))
    header = [f'cmake_minimum_required(VERSION {cmake_version})', f'project({target.title()}Checks C)']
    if c_standard is not None:
        header.append(f'set(CMAKE_C_STANDARD {c_standard})')
    if msvc_runtime:
        header.append('set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")')
    if requires_sdl:
        mode = ' CONFIG REQUIRED' if sdl_config == 'CONFIG' else ' REQUIRED' if sdl_config else ''
        header.append(f'find_package(SDL2{mode})')
    cmake_text = '\n'.join([*header, *_target_lines(check)])
    if cmake_extras:
        cmake_text += '\n' + cmake_extras
    (project / 'CMakeLists.txt').write_text(cmake_text + '\n', encoding='utf-8')

    if toolchain_func is None:
        from retrorecomp.core import toolchain
        toolchain_func = toolchain
    if target_args_func is None:
        from retrorecomp.platforms import cmake_target_args
        target_args_func = cmake_target_args
    if executable_func is None:
        from retrorecomp.platforms import build_executable
        executable_func = build_executable
    if run_func is None:
        from retrorecomp.core import run
        run_func = run
    if process_func is None:
        process_func = subprocess.run

    cmake, generator = toolchain_func()
    build_log = project / 'build.log' if log is True else log
    prefix = []
    if requires_sdl:
        if sdl_config is not None and sdl_config != 'CONFIG':
            raise ValueError("SDL configuration must be 'CONFIG', 'REQUIRED' or None")
        if sdl_func is None:
            # Like the checks did before: build the pinned SDL2 when this checkout has none yet.
            from retrorecomp.core import dependencies
            def sdl_func():
                return dependencies(lambda _: None)[1]
        prefix.append(f'-DCMAKE_PREFIX_PATH={sdl_func().as_posix()}')
    run_func([cmake, '-S', project, '-B', project / 'build', '-G', generator,
              *target_args_func(), *prefix], log=build_log)
    run_func([cmake, '--build', project / 'build', '--config', 'Release',
              '--parallel', parallel], log=build_log)
    command = [executable_func(project / 'build', target), *arguments]
    if combined_output:
        return run_func(command, timeout=timeout)
    return process_func([str(argument) for argument in command], env=env,
                        cwd=cwd if cwd is not None else Path.cwd(), capture_output=True,
                        text=True, timeout=timeout)
