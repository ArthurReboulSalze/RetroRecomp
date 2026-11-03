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


# How the static SDL2 of a game is built, besides its revision (1.6.7). The install and the build folder are named after a
# key of these settings, so a library built another way is a different folder: it is never overwritten, never deleted, and a
# tree that still wants the old settings keeps its own library (no half-written libSDL2.a under a game being linked, no
# ping-pong between two branches that share a .deps). Change SDL_BUILD_FLAGS when the way SDL is configured changes.
#   path-map-1: -ffile-prefix-map writes the player's SDL folder as `SDL` in the strings the library keeps (SDL_render_gl.c,
#   SDL_render_gles2.c and SDL_render_sw.c keep their file name for assertions), so that the same game built in two folders is
#   the same file and no folder of the player's computer is in it.
SDL_BUILD_FLAGS = "path-map-1"
SDL_INSTALL_MARKER = "retro-recomp-sdl.txt"      # written last in an install: a folder without it is unfinished
SDL_PATH_NAME = "SDL"


def sdl_install_key() -> str:
    """What the static SDL2 is built with: revision (core.SDL_REV), build flags and toolchain."""
    from . import toolchain
    from .core import SDL_REV
    return f"sdl={SDL_REV};flags={SDL_BUILD_FLAGS};toolchain={toolchain.active()}"


def _sdl_folder(kind: str) -> Path:
    import hashlib
    from . import toolchain
    from .paths import ROOT
    digest = hashlib.sha256(sdl_install_key().encode()).hexdigest()[:8]
    return ROOT / '.deps/SDL' / f'{kind}{toolchain.suffix()}-{digest}'


def sdl_install() -> Path:
    """The pinned SDL2 static build for the active toolchain and the current build settings (sdl_install_key)."""
    return _sdl_folder('install')


def sdl_build_folder() -> Path:
    """Where that SDL2 is compiled: one folder per key too, kept when a build stops so that the next one goes on."""
    return _sdl_folder('build')


def sdl_install_current(prefix: Path | None = None) -> bool:
    """Whether the static SDL2 of the current key is installed completely (its library and its marker)."""
    prefix = sdl_install() if prefix is None else prefix
    try:
        return ((prefix / sdl_library()).exists()
                and (prefix / SDL_INSTALL_MARKER).read_text(encoding="utf-8").strip() == sdl_install_key())
    except OSError:
        return False


def sdl_compiler_flags(source: Path) -> list[str]:
    """The CMake argument that maps the SDL source folder to `SDL` in the compiled library (quoted when the path has a space)."""
    from . import toolchain
    if toolchain.active() == toolchain.MSVC:
        return []           # cl.exe has no such option; the Visual Studio fallback keeps its folder in the library
    flag = f"-ffile-prefix-map={Path(source).as_posix()}={SDL_PATH_NAME}"
    return [f'-DCMAKE_C_FLAGS="{flag}"' if " " in flag else f"-DCMAKE_C_FLAGS={flag}"]


def sdl_library() -> str:
    from . import toolchain
    return 'lib/SDL2-static.lib' if os.name == 'nt' and toolchain.active() == toolchain.MSVC else 'lib/libSDL2.a'


def build_jobs() -> str:
    # Windows: a game converted alone may use up to eight compiler jobs (its CPU share), a game of a batch its share
    # under compilation_budget. 1.6.4 used four even alone, which left most of the CPUs idle during a large Neo Geo
    # compilation. Linux keeps two: the build hosts there are small machines.
    default = min(8, game_cpu_share()) if os.name == 'nt' else 2
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
    if os.name == 'nt':
        return
    from .systems import ALL_PROFILES
    if system not in {profile.id for profile in ALL_PROFILES if profile.linux == 'witnessed'}:
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
