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


def selected_bios_path(value: str | Path | None) -> Path | None:
    """Portable BIOS preference; merely resolving it never writes a file."""
    if not isinstance(value,(str,Path)) or not str(value).strip():
        return None
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (export_directory() / path).resolve()


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
    for field in ('ng_bios', 'x68_ipl', 'x68_cgrom'):
        if value.get(field):
            bios = selected_bios_path(value[field])
            try:
                value[field] = str(bios.relative_to(export_directory()))
            except ValueError:
                value[field] = str(bios)
    if 'feedback_paths' in value:
        folders = {}
        for system, path in feedback_search_paths(value).items():
            try:
                folders[system] = str(path.relative_to(export_directory()))
            except ValueError:
                folders[system] = str(path)
        value['feedback_paths'] = folders
    if 'rom_paths' in value:
        from .rom_sources import rom_folders
        folders={}
        for system,path in rom_folders(value).items():
            try:folders[system]=str(path.resolve().relative_to(export_directory()))
            except ValueError:folders[system]=str(path.resolve())
        value['rom_paths']=folders
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


def feedback_search_paths(preferences: dict) -> dict[str, Path]:
    """Optional read-only gameplay-feedback search root for each console."""
    # Every known console, experimental ones included: a folder saved for
    # the X68000 must survive preference saves even before it graduates.
    from .systems import PROFILES, X68000
    saved = preferences.get('feedback_paths', {})
    if not isinstance(saved, dict):
        return {}
    result = {}
    for profile in (*PROFILES, X68000):
        raw = saved.get(profile.id)
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            path = Path(raw.strip()).expanduser()
            result[profile.id] = path.resolve() if path.is_absolute() else (export_directory()/path).resolve()
        except (OSError, ValueError):
            continue
    return result


def save_game_language(output: Path, language: str) -> None:
    """Update only the language entry in the shared Windows INI."""
    from .languages import GAME_LANGUAGES, LANGUAGES
    if language not in LANGUAGES:
        raise ValueError('Unknown language')
    if language not in GAME_LANGUAGES:
        language = 'en'  # the converter keeps it; games fall back to English
    import ctypes
    directory = data_directory(output.resolve())
    directory.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        import configparser
        import fcntl
        destination = directory / 'Retro-Recomp.ini'
        with destination.with_suffix('.ini.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            config = configparser.ConfigParser(interpolation=None, strict=False)
            config.optionxform = str
            config.read(destination, encoding='utf-8')
            if not config.has_section('Interface'):
                config.add_section('Interface')
            config.set('Interface', 'language', language)
            fd, temporary = tempfile.mkstemp(prefix='Retro-Recomp.', suffix='.tmp', dir=directory)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    config.write(stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, destination)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return
    write = ctypes.WinDLL('kernel32', use_last_error=True).WritePrivateProfileStringW
    write.argtypes = [ctypes.c_wchar_p] * 4
    write.restype = ctypes.c_int
    if not write('Interface', 'language', language, str(directory / 'Retro-Recomp.ini')):
        raise ctypes.WinError(ctypes.get_last_error())
