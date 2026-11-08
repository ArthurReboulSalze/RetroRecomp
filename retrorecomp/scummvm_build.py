"""Build of the ScummVM runtime behind the adventure exes (docs/SCUMMVM.md).

This module is Retro-Recomp's own build script (MIT). It drives the build of a separate GPL program: the pinned ScummVM
release with the patch series of native/scummvm (GPL-3.0-or-later). Nothing of ScummVM is imported, copied or linked here;
ScummVM and FreeType are fetched into .deps at build time like the other upstreams (docs/UPSTREAMS.md).

One runtime is built per engine family; the family of a game comes from the engine ScummVM's own detection reports, through
`FAMILY_OF_ENGINE` (an engine missing from the table is its own family). No game is named here. The runtime carries only the
five game-menu languages (en, fr, it, es, de) and no CJK font. A separate "detect" runtime holds the detection tables of every
engine and is used only to ask which game a folder holds.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Callable

# Never from this file's location: a packaged exe runs its modules from a temporary folder removed when it closes. ROOT is where .deps
# lives (the exe's folder, or the project when the exe is in Export); the patches travel inside the exe (ASSETS).
from .paths import ASSETS, ROOT

PATCH_DIRECTORY = ASSETS / 'native' / 'scummvm' / 'patches'

SCUMMVM_URL = 'https://github.com/scummvm/scummvm.git'
SCUMMVM_TAG = 'v2026.4.0'
SCUMMVM_REV = '7d2709da5136866589f7602f5f5a7b17de03420e'
FREETYPE_URL = 'https://github.com/freetype/freetype.git'
FREETYPE_TAG = 'VER-2-13-3'
FREETYPE_REV = '42608f77f20749dd6ddc9e0536788eaad70ea4b5'

# The GUI translations kept in the runtime: with English (the source language), the five game-menu languages.
GUI_TRANSLATIONS = ('fr_FR', 'de_DE', 'es_ES', 'it_IT')
# The fonts of dists/engine-data/fonts.dat kept for the menus of those languages (prefixes of the member names).
KEPT_FONTS = ('Liberation', 'GoMono', 'SourceCodeVariable', 'ms_sans_serif', 'system', 'README', 'version')

DISABLED_LIBRARIES = ('zlib', 'mad', 'fribidi', 'ogg', 'vorbis', 'flac', 'png', 'mpeg2', 'theoradec', 'jpeg', 'fluidsynth',
                      'libcurl', 'sdlnet')
DISABLED_FEATURES = ('opengl', 'opengl_game_classic', 'opengl_game_shaders', 'tinygl', '3d', 'http', 'basic-net', 'cloud',
                     'enet', 'taskbar', 'printing', 'dialogs', 'tts', 'nasm', 'updates')

# Engine reported by ScummVM's detection -> build family; an engine missing here is a family of its own.
FAMILY_OF_ENGINE: dict[str, str] = {}
# Family -> the create_project engines it enables (the sub-engines a detected engine may need).
FAMILY_ENGINES: dict[str, tuple[str, ...]] = {
    'scumm': ('scumm', 'scumm_7_8'),
    'sci': ('sci', 'sci32'),
    'kyra': ('kyra', 'lol', 'eob'),
    'agos': ('agos', 'agos2'),
}
# The detection runtime: the detection tables of all engines (--enable-detection-full), plus the engines whose fallback
# detection (unknown variants of known games) needs the engine itself: those whose MetaEngine implements
# fallbackDetectExtern, read from the ScummVM tree (`fallback_engines`), and a small engine when there is none.
DETECT_FAMILY = 'detect'
DETECT_ENGINES = ('lure',)

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


# What the player reads when a build stops. The window shows them in its language: i18n.log_text finds each one by its English
# text, which is the 'scummvm_download_failed' and 'scummvm_build_failed' of its catalogue. The raw output stays in the log.
DOWNLOAD_FAILED = "ScummVM's files could not be downloaded. Check the internet connection, then try again. Details: {log}"
BUILD_FAILED = "ScummVM could not be built on this computer, so nothing was converted. Try again; the details are in {log}"


class ScummvmBuildError(RuntimeError):
    """`key`: the interface sentence of a folder scan that this stopped (the conversion of one game shows the text itself)."""
    key = 'scummvm_detect_failed'


class ScummvmToolsMissing(ScummvmBuildError):
    """The build tools are not installed: nothing was started (discovery and the interface answer with a sentence)."""
    key = 'scummvm_tools_missing'


class ScummvmDownloadFailed(ScummvmBuildError):
    """A pinned source could not be fetched: no network, most of the time."""
    key = 'scummvm_detect_offline'


def family_for(engine: str) -> str:
    """The build family of an engine id reported by ScummVM's detection."""
    return FAMILY_OF_ENGINE.get(engine, engine)


def fallback_engines(tree: Path | None = None) -> tuple[str, ...]:
    """The engines of the ScummVM tree whose fallback detection needs the engine (fallbackDetectExtern in its sources)."""
    tree = tree or scummvm_checkout()
    found = set()
    for source in (tree / 'engines').glob('*/*.cpp'):
        try:
            if 'fallbackDetectExtern' in source.read_text(encoding='utf-8', errors='replace'):
                found.add(source.parent.name)
        except OSError:
            continue
    return tuple(sorted(found))


def engines_for(family: str) -> tuple[str, ...]:
    if family == DETECT_FAMILY:
        return fallback_engines() or DETECT_ENGINES
    return FAMILY_ENGINES.get(family, (family,))


def deps_directory() -> Path:
    return ROOT / '.deps'


def scummvm_checkout() -> Path:
    return deps_directory() / 'scummvm'


def freetype_checkout() -> Path:
    return deps_directory() / 'freetype'


def build_root() -> Path:
    return deps_directory() / 'scummvm-build'


def runtime_path(family: str) -> Path:
    """The stripped runtime of a family (Windows: .exe)."""
    return build_root() / family / ('scummvm-runtime' + ('.exe' if os.name == 'nt' else ''))


def data_path(family: str) -> Path:
    """Where a runtime's data files are collected when the platform has no embedded resources (Linux): the engine data
    (`lure.dat`...), the GUI themes and fonts, packed into every exe as `.rr/data`. Windows embeds them in the runtime."""
    return build_root() / family / 'data'


# The theme of every ScummVM menu, recoloured by the patch series, and the files of its zip (as gui/themes/scummtheme.py builds it).
THEME = 'scummremastered'
THEME_FILES = ('.stx', '.bmp', '.fcc', '.ttf', '.png', '.svg')
# The GUI files the Windows resource script embeds and a pack must carry elsewhere (shaders need OpenGL: not carried).
GUI_DATA = ('scummclassic.zip', 'scummmodern.zip', 'scummremastered.zip', 'gui-icons.dat', 'translations.dat')
_LIST_ENTRY = re.compile(r'^DIST_FILES_LIST\s*\+=\s*(\S+)', re.M)
_LIST_BLOCK = re.compile(r'^ifdef\s+(\w+)\n(.*?)^endif', re.M | re.S)


def data_files(tree: Path, engines: tuple) -> list:
    """The data files ScummVM's own make lists (`dists/engine-data/engine_data*.mk`) name for these engines: the core files,
    the engine data of the enabled engines, and fonts.dat (FreeType is linked). Same content as what the Windows build embeds
    through its resource lists; the CJK fonts list (engine_data_big.mk) is left out."""
    folder = tree / 'dists' / 'engine-data'
    enabled = {f'ENABLE_{engine.upper()}' for engine in engines} | {'USE_FREETYPE2'}
    found = _LIST_ENTRY.findall((folder / 'engine_data_core.mk').read_text(encoding='utf-8'))
    text = (folder / 'engine_data.mk').read_text(encoding='utf-8')
    for condition, body in _LIST_BLOCK.findall(text):
        if condition in enabled:
            found += _LIST_ENTRY.findall(body)
    return [tree / relative for relative in dict.fromkeys(found)]


def collect_data(tree: Path, family_dir: Path, engines: tuple) -> list:
    """Copy the runtime's data files (data_files and GUI_DATA) to <family>/data; returns their names."""
    target = family_dir / 'data'
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for source in [*(tree / 'gui' / 'themes' / name for name in GUI_DATA), *data_files(tree, engines)]:
        if source.is_file():
            shutil.copy2(source, target / source.name)
    return sorted(path.name for path in target.iterdir())


def patch_digest() -> str:
    """SHA-256 of the patch series, in file-name order: part of the identity of every runtime."""
    digest = hashlib.sha256()
    for patch in sorted(PATCH_DIRECTORY.glob('*.patch')):
        digest.update(patch.name.encode('utf-8') + b'\0' + patch.read_bytes())
    return digest.hexdigest()


def runtime_identity(family: str) -> dict:
    return {'scummvm_tag': SCUMMVM_TAG, 'scummvm_commit': SCUMMVM_REV, 'freetype_commit': FREETYPE_REV,
            'patch_sha256': patch_digest(), 'family': family, 'engines': list(engines_for(family)),
            'gui_languages': ['en', *(code.split('_')[0] for code in GUI_TRANSLATIONS)],
            'data': 'resources' if os.name == 'nt' else 'pack'}


# --- running ---------------------------------------------------------------------------------------------------------

def _environment() -> dict:
    """Windows: only the converter's own tools (the portable Git and llvm-mingw, CMake and Ninja of datas/tools) come first
    on PATH; nothing the player installed (Visual Studio, MSYS2, GNU make) is needed or used. Linux: the system's GCC,
    CMake, Ninja and Git (the packages the converter asks for)."""
    env = dict(os.environ)
    if os.name == 'nt':
        from .toolchain import portable_path_entries, tools_directory
        git = tools_directory() / 'mingit' / 'cmd'
        env['PATH'] = os.pathsep.join([*([str(git)] if (git / 'git.exe').is_file() else []),
                                       *(str(path) for path in portable_path_entries()), env.get('PATH', '')])
    return env


def _require_portable_tools() -> None:
    """Windows builds of the runtime use the portable llvm-mingw toolchain only (Visual Studio is never used for it)."""
    if os.name != 'nt':
        from .core import ConversionError, toolchain
        try:
            toolchain()
        except ConversionError as exc:
            raise ScummvmToolsMissing(f"The ScummVM runtime is built with the system's build tools: {exc}") from exc
        return
    from .toolchain import LLVM, ToolchainError, portable_installed, select
    try:
        kind = select().kind
    except ToolchainError:
        kind = ''
    if kind != LLVM or not portable_installed() or not shutil.which('git', path=_environment()['PATH']):
        raise ScummvmToolsMissing('The ScummVM runtime is built with the portable tools Retro-Recomp installs '
                                  '(Git, llvm-mingw, CMake, Ninja): install them from the converter, Visual Studio is not used.')


def _run(command: list, cwd: Path, log: Path, timeout: int = 3600) -> str:
    with open(log, 'a', encoding='utf-8', errors='replace') as out:
        out.write('\n$ ' + ' '.join(str(part) for part in command) + '\n')
    env = _environment()
    program = str(command[0])
    if not os.path.dirname(program):
        # Windows resolves a bare program name with the PATH of this process, not the one given to the child.
        program = shutil.which(program, path=env['PATH']) or program
    try:
        result = subprocess.run([program, *(str(part) for part in command[1:])], cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=timeout,
                                creationflags=NO_WINDOW)
    except FileNotFoundError as exc:
        raise ScummvmToolsMissing(f"{Path(program).name} is missing. Retro-Recomp's build tools install it: start a "
                                  'conversion from the window, or use the ScummVM pack button in its options.') from exc
    except (OSError, subprocess.SubprocessError) as exc:
        with open(log, 'a', encoding='utf-8', errors='replace') as out:
            out.write(f'{exc}\n')
        raise ScummvmBuildError(BUILD_FAILED.format(log=log)) from exc
    with open(log, 'a', encoding='utf-8', errors='replace') as out:
        out.write(result.stdout)
    if result.returncode != 0:
        with open(log, 'a', encoding='utf-8', errors='replace') as out:
            out.write(f'{Path(program).name} failed ({result.returncode})\n')
        raise ScummvmBuildError(BUILD_FAILED.format(log=log))
    return result.stdout


def _configure(cmake, source: Path, build: Path, generator: str, flags: list, cwd: Path, log: Path) -> None:
    """Configure `build`, in a folder that this same command made with these same compilers, or in a new one.

    A CMake cache belongs to the folders and the compiler it was made with. When the compiler name now resolves to another
    folder (the converter moved, or another copy of it made the build), CMake deletes the cache and goes on without the -D values
    of its command line: SDL2_DIR and CMAKE_PREFIX_PATH are lost and find_package(SDL2) fails. When the source moved, it refuses.
    Another command's folder is removed, objects included: they came from the other compiler."""
    command = [cmake, '-S', source, '-B', build, '-G', generator, *flags]
    path = _environment()['PATH']
    wanted = _json({'command': [str(part) for part in command],
                    'compilers': [shutil.which(name, path=path) for name in (('clang', 'clang++') if os.name == 'nt'
                                                                             else ('cc', 'c++'))]})
    marker = build / '.retrorecomp-configure'
    try:
        same = marker.read_text(encoding='utf-8') == wanted
    except OSError:
        same = False
    if same:
        marker.unlink()          # a configure that fails here leaves a cache nothing should go on from
    elif build.exists():
        shutil.rmtree(build, onexc=_make_writable)
    _run(command, cwd, log)
    build.mkdir(parents=True, exist_ok=True)
    marker.write_text(wanted, encoding='utf-8')


def _make_writable(function, path, _error) -> None:
    os.chmod(path, 0o666)       # the read-only pack files of a git checkout
    function(path)


def _rename_retrying(source: Path, target: Path, attempts: int = 10) -> None:
    """Windows refuses to move a folder while an antivirus or the indexer still reads a file just written in it."""
    for attempt in range(attempts):
        try:
            source.rename(target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(1)


def _checkout(path: Path, url: str, tag: str, revision: str, log: Path, emit: Callable[[str], None]) -> None:
    """A clean checkout of `revision` (shallow clone of `tag`); a checkout at another revision is refused, not replaced."""
    if not (path / '.git').exists():
        emit(f'Téléchargement de {path.name} {tag}…')
        path.parent.mkdir(parents=True, exist_ok=True)
        # Cloned beside its place, then moved: a window closed during the download leaves nothing that looks like a checkout.
        partial = path.with_name(path.name + '.partial')
        try:
            if partial.exists():
                shutil.rmtree(partial, onexc=_make_writable)
            try:
                _run(['git', 'clone', '--depth', '1', '--branch', tag, url, partial], deps_directory(), log)
            except ScummvmToolsMissing:
                raise
            except ScummvmBuildError as exc:
                raise ScummvmDownloadFailed(DOWNLOAD_FAILED.format(log=log)) from exc
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
            _rename_retrying(partial, path)
        except OSError as exc:
            raise ScummvmBuildError(f'{path.name} could not be placed in {path.parent}: {exc}') from exc
    head = _run(['git', '-C', path, 'rev-parse', 'HEAD'], deps_directory(), log).strip()
    if head != revision:
        raise ScummvmBuildError(f'{path} is at {head[:12]}, not the pinned {revision[:12]}; remove the folder to fetch it again')


def prepare_sources(log: Path, emit: Callable[[str], None] = print) -> Path:
    """The pinned ScummVM tree with the patch series applied once (a marker records the patch digest)."""
    tree = scummvm_checkout()
    _checkout(tree, SCUMMVM_URL, SCUMMVM_TAG, SCUMMVM_REV, log, emit)
    _checkout(freetype_checkout(), FREETYPE_URL, FREETYPE_TAG, FREETYPE_REV, log, emit)
    marker = tree / '.retrorecomp-patch'
    wanted = patch_digest()
    if marker.exists() and marker.read_text(encoding='utf-8').strip() == wanted:
        return tree
    emit('Application du correctif Retro-Recomp à ScummVM…')
    _run(['git', '-C', tree, 'checkout', '--', '.'], deps_directory(), log)
    _run(['git', '-C', tree, 'clean', '-fdq', '--', 'backends/fs/packed'], deps_directory(), log)
    for patch in sorted(PATCH_DIRECTORY.glob('*.patch')):
        _run(['git', '-C', tree, 'apply', '--whitespace=nowarn', patch], deps_directory(), log)
    _trim_resources(tree, log)
    marker.write_text(wanted + '\n', encoding='utf-8')
    return tree


def _host_tool(name: str, sources: list[Path], log: Path) -> Path:
    out = build_root() / 'tools' / (name + ('.exe' if os.name == 'nt' else ''))
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    compiler = 'clang++' if os.name == 'nt' else 'c++'
    _run([compiler, '-std=c++17', '-O1', *(['-static'] if os.name == 'nt' else []), '-o', out, *sources], build_root(), log)
    return out


def _trim_resources(tree: Path, log: Path) -> None:
    """Five GUI languages only and no font outside KEPT_FONTS (build files of the .deps tree, never the repository)."""
    tool = _host_tool('create_translations', sorted((tree / 'devtools/create_translations').glob('*.cpp')), log)
    _run([tool, tree / 'gui/themes/translations.dat', *(tree / 'po' / f'{code}.po' for code in GUI_TRANSLATIONS)], tree, log)
    fonts = tree / 'dists/engine-data/fonts.dat'
    trimmed = fonts.with_suffix('.trim')
    with zipfile.ZipFile(fonts) as source, zipfile.ZipFile(trimmed, 'w', zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            if item.filename.startswith(KEPT_FONTS):
                target.writestr(item, source.read(item.filename))
    trimmed.replace(fonts)
    _pack_theme(tree)


def _pack_theme(tree: Path) -> None:
    """ScummVM reads a theme from its zip, which the sources carry already built: the default theme's is made again from its
    patched folder. Its own files first, then the folders its THEMERC names with %using."""
    folder = tree / 'gui' / 'themes' / THEME
    places = [folder]
    for line in (folder / 'THEMERC').read_text(encoding='utf-8').splitlines():
        if line.startswith('%using '):
            places.append(folder / line[len('%using '):].strip())
    members = {'THEMERC': folder / 'THEMERC'}
    for place in places:
        for path in sorted(place.iterdir()):
            if path.is_file() and not path.name.startswith('.') and path.name.endswith(THEME_FILES):
                members.setdefault(path.name, path)
    with zipfile.ZipFile(folder.with_suffix('.zip'), 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for name, path in members.items():
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))      # the same bytes at every build
            info.compress_type = zipfile.ZIP_DEFLATED
            out.writestr(info, path.read_bytes())


def _build_freetype(log: Path, emit: Callable[[str], None] = print) -> Path:
    prefix = build_root() / 'freetype-install'
    if (prefix / 'lib' / 'libfreetype.a').exists():
        return prefix
    emit('Compilation de FreeType…')
    build = build_root() / 'freetype-build'
    from .core import toolchain
    cmake, generator = toolchain()
    _configure(cmake, freetype_checkout(), build, generator,
               ['-DCMAKE_BUILD_TYPE=Release', *(['-DCMAKE_C_COMPILER=clang'] if os.name == 'nt' else []),
                f'-DCMAKE_INSTALL_PREFIX={prefix.as_posix()}', '-DBUILD_SHARED_LIBS=OFF', '-DFT_DISABLE_ZLIB=ON',
                '-DFT_DISABLE_BZIP2=ON', '-DFT_DISABLE_PNG=ON', '-DFT_DISABLE_HARFBUZZ=ON', '-DFT_DISABLE_BROTLI=ON'],
               build_root(), log)
    _run([cmake, '--build', build, '--config', 'Release'], build_root(), log)
    _run([cmake, '--install', build, '--config', 'Release'], build_root(), log)
    return prefix


def static_system_libraries(prefix: Path) -> list:
    """The system libraries a static SDL2 needs on Linux: the `Libs.private` of its own pkg-config file (m, dl, pthread, rt...),
    so the link line follows the SDL the converter built; m, dl and pthread when the file is absent."""
    for folder in ('lib', 'lib64'):
        try:
            text = (prefix / folder / 'pkgconfig' / 'sdl2.pc').read_text(encoding='utf-8')
        except OSError:
            continue
        for line in text.splitlines():
            if line.startswith('Libs.private:'):
                found = [flag[2:] for flag in line.split(':', 1)[1].split() if flag.startswith('-l') and len(flag) > 2]
                if found:
                    return list(dict.fromkeys(found))
    return ['m', 'dl', 'pthread']


def _sdl_shim(folder: Path) -> Path:
    """A CMake package file pointing at the converter's own static SDL2 (core.SDL_REV), so no second SDL is built."""
    from .platforms import sdl_install
    prefix = sdl_install()
    folder.mkdir(parents=True, exist_ok=True)
    libs = ('mingw32 "${p}/lib/libSDL2main.a" "${p}/lib/libSDL2.a" m kernel32 user32 gdi32 winmm imm32 ole32 oleaut32 '
            'version uuid advapi32 setupapi shell32 dinput8 -mwindows') if os.name == 'nt' else \
        '"${p}/lib/libSDL2main.a" "${p}/lib/libSDL2.a" ' + ' '.join(static_system_libraries(prefix))
    (folder / 'SDL2Config.cmake').write_text(
        '# Generated by retrorecomp/scummvm_build.py: the converter\'s own static SDL2.\n'
        f'set(p "{prefix.as_posix()}")\nset(SDL2_FOUND TRUE)\n'
        'set(SDL2_INCLUDE_DIRS "${p}/include/SDL2")\n'
        f'set(SDL2_LIBRARIES {libs})\n', encoding='utf-8')
    return folder


def _ensure_sdl(log: Path, emit: Callable[[str], None]) -> None:
    """The converter's own static SDL2 at its pin (core.SDL_REV), built by the converter's own code if needed."""
    from . import core
    from .platforms import sdl_install
    cmake, generator = core.toolchain()
    sdl = deps_directory() / 'SDL'
    try:
        core.follow_pin(sdl, 'https://github.com/libsdl-org/SDL.git', core.SDL_REV, log, emit)
    except core.StopRequested:
        raise
    except core.ConversionError as exc:
        # A failed git command, or a fetch that says so. A folder it refuses to touch keeps its own sentence (what to do with it).
        if str(exc).startswith(('Commande interrompue', 'Impossible de récupérer')):
            raise ScummvmDownloadFailed(DOWNLOAD_FAILED.format(log=log)) from exc
        raise ScummvmBuildError(str(exc)) from exc
    try:
        core.ensure_sdl(cmake, generator, sdl, sdl_install(), log, emit)
    except core.StopRequested:
        raise
    except core.ConversionError as exc:
        raise ScummvmBuildError(BUILD_FAILED.format(log=log)) from exc


def runtime_current(family: str) -> bool:
    """Whether the runtime of a family is built, from these sources and these patches."""
    out = runtime_path(family)
    stamp = out.with_suffix('.json')
    return out.exists() and stamp.exists() and stamp.read_text(encoding='utf-8') == _json(runtime_identity(family))


def prepare_pack(emit: Callable[[str], None] = print) -> bool:
    """The ScummVM pack: what adventure games need before their first conversion, made ahead of time. The pinned sources of
    ScummVM, FreeType and SDL, FreeType and SDL built, and the detection runtime, which is what a folder scan waits for. False
    when it is already there. The runtime of an engine family is still built by the first conversion that needs it."""
    if runtime_current(DETECT_FAMILY):
        return False
    build_runtime(DETECT_FAMILY, emit)
    return True


def build_runtime(family: str, emit: Callable[[str], None] = print, started: Callable[[], None] | None = None) -> Path:
    """Build (once) the stripped runtime of an engine family and return its path (one build at a time: create_project
    rewrites shared files of the ScummVM tree). `started` is called only when a build really begins."""
    from .core import serialized_setup
    return serialized_setup(_build_runtime)(family, emit, started)


def _build_runtime(family: str, emit: Callable[[str], None], started: Callable[[], None] | None = None) -> Path:
    out = runtime_path(family)
    stamp = out.with_suffix('.json')
    if runtime_current(family):
        return out
    _require_portable_tools()
    if started is not None:
        started()
    root = build_root()
    root.mkdir(parents=True, exist_ok=True)
    log = root / f'{family}.log'
    log.write_text('', encoding='utf-8')
    tree = prepare_sources(log, emit)
    freetype = _build_freetype(log, emit)
    _ensure_sdl(log, emit)
    create_project = _host_tool('create_project', sorted((tree / 'devtools/create_project').glob('*.cpp')), log)
    family_dir = root / family
    config = family_dir / 'cfg'
    config.mkdir(parents=True, exist_ok=True)
    emit(f'Préparation de ScummVM ({family})…')
    # create_project rewrites dists/*.rh of the shared tree: families are built one at a time (serialized_setup).
    _run([create_project, tree, '--cmake', '--sdl2', '--file-prefix', os.path.relpath(tree, config).replace('\\', '/'),
          '--output-dir', config, '--disable-all-engines', '--enable-engine=' + ','.join(engines_for(family)),
          *(['--enable-detection-full'] if family == DETECT_FAMILY else []),
          *(f'--disable-{name}' for name in (*DISABLED_LIBRARIES, *DISABLED_FEATURES))], root, log)
    (tree / 'dists/scummvm_rc_engine_data_big.rh').write_text('// Retro-Recomp: no CJK fonts in the exes\n',
                                                                encoding='utf-8')
    (tree / 'dists/scummvm.rc').touch()
    if os.name != 'nt':
        emit(f'Données de ScummVM ({family}) : {len(collect_data(tree, family_dir, engines_for(family)))} fichiers.')
    from .core import toolchain
    cmake, generator = toolchain()
    build = family_dir / 'build'
    emit(f'Compilation de ScummVM ({family})…')
    _configure(cmake, config, build, generator,
               ['-DCMAKE_BUILD_TYPE=Release',
                *(['-DCMAKE_C_COMPILER=clang', '-DCMAKE_CXX_COMPILER=clang++', '-DCMAKE_EXE_LINKER_FLAGS=-static']
                  if os.name == 'nt'
                  # Linux: the generated CMake asks pkg-config for SDL (a hard REQUIRED) before find_package; the converter's own
                  # SDL and FreeType are reached through the shim and the prefix, as on Windows (which has no pkg-config).
                  else ['-DCMAKE_DISABLE_FIND_PACKAGE_PkgConfig=TRUE']),
                f'-DCMAKE_PREFIX_PATH={freetype.as_posix()}', f'-DSDL2_DIR={_sdl_shim(family_dir / "sdl2").as_posix()}'],
               root, log)
    _run([cmake, '--build', build, '--config', 'Release'], root, log, timeout=7200)
    built = build / ('scummvm' + ('.exe' if os.name == 'nt' else ''))
    strip = 'llvm-strip' if os.name == 'nt' else 'strip'
    _run([strip, '-o', out, built], root, log)
    # Read again now the tree exists: on a first build the detection family's engines come from the sources just fetched, and
    # the identity read before them would call this runtime stale at once (a second full build).
    stamp.write_text(_json(runtime_identity(family)), encoding='utf-8')
    return out


def _json(data: dict) -> str:
    import json
    return json.dumps(data, indent=2, sort_keys=True) + '\n'
