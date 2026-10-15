"""Local build target and tool invocation; no cross compilation."""
import os
import platform
import subprocess
import json
import sys
from pathlib import Path


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
    return ['-A', 'x64'] if os.name == 'nt' else ['-DCMAKE_BUILD_TYPE=Release']


def build_executable(build: Path, name: str) -> Path:
    return build / 'Release' / (name + '.exe') if os.name == 'nt' else build / name


def build_jobs() -> str:
    default = 4 if os.name == 'nt' else 2
    return str(max(1, min(8, int(os.environ.get('RETRO_RECOMP_BUILD_JOBS', default)))))


def open_local(path: Path) -> None:
    if os.name == 'nt':
        os.startfile(path)
    else:
        path = path.resolve()
        subprocess.Popen(['xdg-open', str(path)] if path.is_dir() else [str(path)],
                         cwd=path.parent, start_new_session=True)


def require_backend(system: str) -> None:
    if os.name != 'nt' and system not in ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng'):
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
