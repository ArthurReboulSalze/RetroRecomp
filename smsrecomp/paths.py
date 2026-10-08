"""Portable application paths: always relative to the application, never cwd."""
from pathlib import Path
import json
import os
import sys
import tempfile

def workspace_directory() -> Path:
    """Reuse the local project's compiler cache when its app is in Export."""
    if not getattr(sys, 'frozen', False):
        return Path(__file__).resolve().parents[1]
    application = Path(sys.executable).resolve().parent
    project = application.parent
    if (application.name.casefold() == 'export' and
            (project / 'RetroRecomp.py').is_file() and
            (project / 'smsrecomp/core.py').is_file()):
        return project
    return application


ROOT = workspace_directory()
ASSETS = Path(getattr(sys, "_MEIPASS", ROOT))
APP_NAME = "Retro-Recomp"


def export_directory() -> Path:
    """Sources export under Export; the packaged app uses its own folder."""
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else ROOT / 'Export'


def games_directory(saved: str | None = None, *, system_id: str = "sms") -> Path:
    """Resolve portable preferences against the converter, never the launch cwd."""
    from .systems import get_profile
    system = get_profile(system_id)
    if saved:
        path = Path(saved).expanduser()
        return path.resolve() if path.is_absolute() else (export_directory() / path).resolve()
    return export_directory() / 'Games' / system.export_folder


def games_root(saved: str | None = None) -> Path:
    """Root containing one export directory per console, beside the converter."""
    if saved:
        path = Path(saved).expanduser()
        return path.resolve() if path.is_absolute() else (export_directory() / path).resolve()
    return export_directory() / 'Games'


def preferred_games_root(preferences: dict) -> tuple[Path, bool]:
    """Upgrade the old default SMS path without losing an explicit custom path."""
    saved = preferences.get('output')
    chosen = games_root(saved)
    old_default = games_directory()
    if chosen == old_default:
        chosen = games_root()
    custom = preferences.get('custom_output')
    if custom is None:
        custom = bool(saved) and chosen != games_root()
    return (chosen if custom else games_root()), bool(custom)


def data_directory(root: Path | None = None) -> Path:
    return (root or export_directory()) / "datas"


def boxart_cache_directory(system_id: str) -> Path:
    """Keep downloaded covers beside the converter, separate for each console."""
    from .systems import get_profile
    return data_directory() / 'BoxArt' / get_profile(system_id).id


def load_preferences() -> dict:
    try:
        value = json.loads((data_directory() / "Retro-Recomp.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_preferences(value: dict) -> None:
    value = dict(value)
    if value.get('output'):
        output = games_root(value['output'])
        try:
            value['output'] = str(output.relative_to(export_directory()))
        except ValueError:
            value['output'] = str(output)
    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="Retro-Recomp.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
        os.replace(temporary, directory / "Retro-Recomp.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_game_language(output: Path, language: str) -> None:
    """Update only the language entry in the shared Windows INI."""
    if language not in ('en', 'fr'):
        raise ValueError('Unknown language')
    import ctypes
    directory = data_directory(output.resolve())
    directory.mkdir(parents=True, exist_ok=True)
    write = ctypes.WinDLL('kernel32', use_last_error=True).WritePrivateProfileStringW
    write.argtypes = [ctypes.c_wchar_p] * 4
    write.restype = ctypes.c_int
    if not write('Interface', 'language', language, str(directory / 'Retro-Recomp.ini')):
        raise ctypes.WinError(ctypes.get_last_error())
