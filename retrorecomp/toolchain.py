"""Which C toolchain builds the games on this computer.

Windows has two: the portable one (llvm-mingw clang with CMake and Ninja, kept
in datas/tools by the converter's installer, no administrator rights) and a
Visual Studio Build Tools installation, which stays a fallback. Linux compiles
with the distribution's GCC and Ninja and never reaches this module's choice.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

LLVM = 'llvm'
MSVC = 'msvc'
NATIVE = 'native'

# Pinned portable tools. The installer (updater.install_toolchain) downloads
# these exact archives and checks their SHA-256 before unpacking.
LLVM_MINGW_VERSION = '20261006'
LLVM_MINGW_URL = ('https://github.com/mstorsjo/llvm-mingw/releases/download/'
                  f'{LLVM_MINGW_VERSION}/llvm-mingw-{LLVM_MINGW_VERSION}-ucrt-x86_64.zip')
LLVM_MINGW_SHA256 = '317492c456aa27ee607a5919f1d2d38dcdc1112516a24d0bf4b00d078f52d17a'
LLVM_MINGW_BYTES = 190836485
CMAKE_VERSION = '4.4.4'
CMAKE_URL = f'https://github.com/Kitware/CMake/releases/download/v{CMAKE_VERSION}/cmake-{CMAKE_VERSION}-windows-x86_64.zip'
CMAKE_SHA256 = 'bace36e94b31c68ab6fa295f26dfa11219e0701cf7c94b0284a7d1cb13dac536'
CMAKE_BYTES = 54400562
NINJA_VERSION = '1.13.2'
NINJA_URL = f'https://github.com/ninja-build/ninja/releases/download/v{NINJA_VERSION}/ninja-win.zip'
NINJA_SHA256 = '07fc8261b42b20e71d1720b39068c2e14ffcee6396b76fb7a795fb460b78dc65'
NINJA_BYTES = 291570
STAMP = 'retro-recomp-tool.json'


class ToolchainError(RuntimeError):
    """No usable toolchain; the message is for the user."""


@dataclass(frozen=True)
class Selection:
    kind: str
    cmake: Path
    generator: str


def tools_directory() -> Path:
    from .paths import data_directory
    return data_directory() / 'tools'


def _pinned() -> dict[str, tuple[str, str]]:
    """folder -> (version, a file that must exist, relative to the folder)."""
    return {'llvm-mingw': (LLVM_MINGW_VERSION, 'bin/clang.exe'),
            'cmake': (CMAKE_VERSION, 'bin/cmake.exe'),
            'ninja': (NINJA_VERSION, 'ninja.exe')}


def portable_installed() -> bool:
    """True when all three tools are present at exactly the pinned versions."""
    tools = tools_directory()
    for folder, (version, marker) in _pinned().items():
        try:
            stamp = json.loads((tools / folder / STAMP).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return False
        if not isinstance(stamp, dict) or stamp.get('version') != version or not (tools / folder / marker).is_file():
            return False
    return True


def portable_path_entries() -> list[Path]:
    tools = tools_directory()
    return [tools / 'llvm-mingw' / 'bin', tools / 'cmake' / 'bin', tools / 'ninja']


@lru_cache(maxsize=1)
def visual_studio() -> tuple[Path, str] | None:
    """(cmake, generator) of a Visual Studio with the x64 C++ tools, if any."""
    vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    if not vswhere.exists():
        return None
    try:
        result = subprocess.run([str(vswhere), '-all', '-products', '*', '-requires',
                                 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-format', 'json'],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, encoding='utf-8',
                                errors='replace', timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        installations = json.loads(result.stdout or '[]')
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    for major, generator in ((17, 'Visual Studio 17 2022'), (18, 'Visual Studio 18 2026')):
        for install in installations:
            if not str(install.get('installationVersion', '')).startswith(f'{major}.'):
                continue
            cmake = Path(install['installationPath']) / 'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
            candidate = shutil.which('cmake')
            if not cmake.exists() and candidate:
                cmake = Path(candidate)
            if cmake.exists():
                return cmake, generator
    return None


def requested() -> str | None:
    value = os.environ.get('RETRO_RECOMP_TOOLCHAIN', '').strip().lower()
    return value if value in (LLVM, MSVC) else None


def select() -> Selection:
    """The toolchain every build uses: RETRO_RECOMP_TOOLCHAIN=llvm|msvc, else
    the portable tools when installed, else Visual Studio when present."""
    if os.name != 'nt':
        return Selection(NATIVE, Path(shutil.which('cmake') or 'cmake'), 'Ninja')
    want = requested()
    if want != MSVC and portable_installed():
        _prepare_path()
        return Selection(LLVM, tools_directory() / 'cmake' / 'bin' / 'cmake.exe', 'Ninja')
    if want == LLVM:
        raise ToolchainError('The portable build tools (llvm-mingw, CMake, Ninja) are not installed.')
    studio = visual_studio()
    if studio:
        return Selection(MSVC, *studio)
    raise ToolchainError('No C compiler found: install the portable build tools offered by Retro-Recomp, '
                         'or Visual Studio Build Tools (C++ x64 and CMake).')


def active() -> str:
    """'llvm', 'msvc' or 'native'; 'msvc' also when nothing is installed yet."""
    try:
        return select().kind
    except ToolchainError:
        return MSVC if os.name == 'nt' else NATIVE


def _prepare_path() -> None:
    entries = os.environ.get('PATH', '').split(os.pathsep)
    wanted = [str(path) for path in portable_path_entries() if str(path) not in entries]
    if wanted:
        os.environ['PATH'] = os.pathsep.join([*wanted, *entries])


def cmake_arguments() -> list[str]:
    """Generator-independent configure arguments for the active toolchain."""
    if os.name != 'nt':
        return ['-DCMAKE_BUILD_TYPE=Release']
    if select().kind != LLVM:
        return ['-A', 'x64']
    llvm = tools_directory() / 'llvm-mingw' / 'bin'
    # -static keeps clang's C++ runtime (libc++, libunwind, winpthread) inside
    # every program, converter tools included: nothing needs this folder at run
    # time. -s drops the symbol and debug tables (a quarter of the raw size).
    return ['-DCMAKE_BUILD_TYPE=Release',
            f'-DCMAKE_C_COMPILER={(llvm / "clang.exe").as_posix()}',
            f'-DCMAKE_CXX_COMPILER={(llvm / "clang++.exe").as_posix()}',
            f'-DCMAKE_RC_COMPILER={(llvm / "llvm-windres.exe").as_posix()}',
            f'-DCMAKE_MAKE_PROGRAM={(tools_directory() / "ninja" / "ninja.exe").as_posix()}',
            '-DCMAKE_EXE_LINKER_FLAGS=-static -s']


def suffix() -> str:
    """Folder suffix for caches that two toolchains must not share."""
    return '-llvm' if os.name == 'nt' and active() == LLVM else ''


def describe() -> dict:
    """Receipt fields: which compiler built an export."""
    kind = active()
    if kind == LLVM:
        return {'kind': LLVM, 'compiler': f'llvm-mingw {LLVM_MINGW_VERSION}', 'cmake': CMAKE_VERSION, 'ninja': NINJA_VERSION}
    return {'kind': kind}


def reset_incompatible_cache(command, cwd=None) -> None:
    """Delete a CMake build folder configured by another generator or compiler.

    A folder cannot be reused after switching between Visual Studio and the
    portable tools; rebuilding it is the only correct outcome.
    """
    if os.name != 'nt' or len(command) < 4 or Path(str(command[0])).stem.lower() != 'cmake':
        return
    command = [str(part) for part in command]
    if '-B' not in command or '-G' not in command:
        return
    build = Path(command[command.index('-B') + 1])
    if not build.is_absolute() and cwd:
        build = Path(cwd) / build
    try:
        entries = dict(line.split('=', 1) for line in (build / 'CMakeCache.txt').read_text(
            encoding='utf-8', errors='replace').splitlines() if '=' in line and not line.startswith(('//', '#')))
    except OSError:
        return
    generator = command[command.index('-G') + 1]
    compiler = next((part.split('=', 1)[1] for part in command if part.startswith('-DCMAKE_C_COMPILER=')), None)
    cached_compiler = entries.get('CMAKE_C_COMPILER:FILEPATH', '')
    stale = entries.get('CMAKE_GENERATOR:INTERNAL') != generator
    if compiler and cached_compiler and Path(cached_compiler).as_posix().lower() != Path(compiler).as_posix().lower():
        stale = True
    if stale:
        shutil.rmtree(build, ignore_errors=True)
