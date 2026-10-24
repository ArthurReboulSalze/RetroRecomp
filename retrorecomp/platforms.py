"""Local build target and tool invocation; no cross compilation."""
import os
import platform
import subprocess
import json
import sys
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar

_BUILD_BUDGET = ContextVar('retro_recomp_build_budget', default=None)


def restore_system_library_path() -> None:
    """Do not pass PyInstaller's private libraries to GCC, SDL games or xdg-open.

    The ELF loader has already consumed its search path for this process. A
    frozen child bootloader installs its own path again when it starts.
    """
    if getattr(sys, 'frozen', False) and platform.system() == 'Linux':
        original = os.environ.get('LD_LIBRARY_PATH_ORIG')
        if original is None:
            os.environ.pop('LD_LIBRARY_PATH', None)
        else:
            os.environ['LD_LIBRARY_PATH'] = original


def target_id() -> str:
    machine = platform.machine().lower()
    arch = {'amd64': 'x86_64', 'x86_64': 'x86_64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(machine)
    if not arch or (os.name != 'nt' and platform.system() != 'Linux'):
        raise RuntimeError(f'Unsupported local build target: {platform.system()} {machine}')
    return f"{'windows' if os.name == 'nt' else 'linux'}-{arch}"


def cmake_target_args() -> list[str]:
    from . import toolchain
    return toolchain.cmake_arguments()


def build_executable(build: Path, name: str) -> Path:
    """Where a CMake build leaves a program: Visual Studio builds keep one
    folder per configuration, Ninja builds (portable tools, Linux) do not."""
    from . import toolchain
    if os.name == 'nt' and toolchain.active() == toolchain.MSVC:
        return build / 'Release' / (name + '.exe')
    return build / (name + '.exe' if os.name == 'nt' else name)


def recompiler_build() -> Path:
    """Where the Master System / Game Gear translator is built."""
    from . import toolchain
    from .paths import ROOT
    return ROOT / ('.deps/recompiler-build' + toolchain.suffix())


def sdl_install() -> Path:
    """The pinned SDL2 static build for the active toolchain."""
    from . import toolchain
    from .paths import ROOT
    return ROOT / '.deps/SDL' / ('install' + toolchain.suffix())


def sdl_library() -> str:
    from . import toolchain
    return 'lib/SDL2-static.lib' if os.name == 'nt' and toolchain.active() == toolchain.MSVC else 'lib/libSDL2.a'


def build_jobs() -> str:
    default = 4 if os.name == 'nt' else 2
    requested = max(1, min(8, int(os.environ.get('RETRO_RECOMP_BUILD_JOBS', default))))
    budget = _BUILD_BUDGET.get()
    return str(min(requested, budget) if budget is not None else requested)


def game_cpu_share() -> int:
    """Host CPUs one game may keep busy with its own replays: its share under
    compilation_budget, or every CPU when it converts alone."""
    budget = _BUILD_BUDGET.get()
    return max(1, budget if budget is not None else available_cpus())


@contextmanager
def compilation_budget(parallel_games):
    """Share host compiler workers across games, without changing validation."""
    budget = max(1, available_cpus() // max(1, parallel_games))
    previous = _BUILD_BUDGET.get()
    token = _BUILD_BUDGET.set(min(previous, budget) if previous is not None else budget)
    try:
        yield
    finally:
        _BUILD_BUDGET.reset(token)


def available_cpus():
    return (os.process_cpu_count() if hasattr(os,'process_cpu_count') else os.cpu_count()) or 1


def open_local(path: Path) -> None:
    if os.name == 'nt':
        os.startfile(path)
    else:
        path = path.resolve()
        subprocess.Popen(['xdg-open', str(path)] if path.is_dir() else [str(path)],
                         cwd=path.parent, start_new_session=True)


def require_backend(system: str) -> None:
    if os.name != 'nt' and system not in ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'x68'):
        from .core import ConversionError
        raise ConversionError(f'{system}: Linux integration is still pending for this console profile.')


def claim_cache(root: Path) -> None:
    """A workspace belongs to one local target; copied foreign caches fail closed."""
    from .library import atomic_json
    from .core import ConversionError
    marker = root / 'local-target.json'
    identity = target_id()
    if marker.exists():
        if json.loads(marker.read_text(encoding='utf-8')).get('target') != identity:
            raise ConversionError('This compiler cache belongs to another OS/architecture. Use a separate workspace for ' + identity + '.')
    elif os.name != 'nt' and (root/'recompiler-build/Release/SmsRecomp.exe').exists():
        raise ConversionError('Windows compiler cache found. Start Linux from a source-only workspace.')
    else:
        root.mkdir(parents=True, exist_ok=True)
        atomic_json(marker, {'schema': 1, 'target': identity})
