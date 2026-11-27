"""Delete a converted game from the player's disk: Compiled Games' « Delete game… » (the owner's request of 27 November 2026;
never in the front-end, the couch view).

What goes: the game's executable and its conversion report folder (`datas/reports/<game>/`), and, only when the player ticks
it, its saves and quick states (`datas/games/<…>-<ROM identity>`). What never goes: the source ROM, the library's
observations and the shared paths (knowledge, not the game), another game's files.

Only what the converter itself made: the executable must carry the game's ROM identity (the identity every export embeds),
the report must name that executable and that identity, and everything must lie inside the configured output folders.
Files go to the Recycle Bin on a fixed Windows drive, to the trash on Linux (`gio trash`, else the freedesktop trash of the
home's file system); where there is none (a network or removable drive, no trash), the dialog says the deletion is final.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


class Refused(Exception):
    """This game's files cannot be shown to be the converter's own (or lie outside the output folders): nothing is deleted."""


@dataclass
class Plan:
    game: object
    files: list = field(default_factory=list)      # the executable and the report folder
    saves: list = field(default_factory=list)      # saves and quick states, deleted only when asked
    trash: bool = True                             # False: no Recycle Bin or trash for these files, the deletion is final


def _inside(path: Path, roots) -> bool:
    try:
        path = path.resolve()
    except OSError:
        return False
    return any(path == root or path.is_relative_to(root) for root in roots)


def _identity_of(executable: Path) -> str | None:
    from .batch import _embedded_export_identity
    try:
        return _embedded_export_identity(executable)
    except (OSError, ValueError):
        return None


def save_entries(game) -> list:
    """The saves and quick states of `game` beside its executable: entries of `datas/games` named after its ROM identity
    (`<name>-<first 12 hex>` or `<console>-<full identity>`, a folder or a `.sav`)."""
    folder = Path(game.executable).parent / 'datas' / 'games'
    short, full = '-' + game.identity[:12], '-' + game.identity
    found = []
    try:
        entries = list(folder.iterdir())
    except OSError:
        return found
    for entry in entries:
        stem = entry.name if entry.is_dir() else entry.stem
        if stem.endswith(short) or stem.endswith(full):
            found.append(entry)
    return sorted(found)


def plan(game, roots) -> Plan:
    """What deleting `game` removes, or Refused when its files cannot be shown to be the converter's own."""
    roots = [Path(root).resolve() for root in roots if root]
    executable = Path(game.executable)
    if not _inside(executable.parent, roots):
        raise Refused('outside the output folders')
    result = Plan(game)
    if executable.exists():
        if executable.is_dir() or _identity_of(executable) != game.identity:
            raise Refused('the executable does not carry this game')
        result.files.append(executable)
    if game.report:
        report = Path(game.report)
        if report.exists():
            try:
                data = json.loads(report.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                raise Refused('the report cannot be read')
            folder = report.parent
            if (data.get('rom', {}).get('sha256') != game.identity or data.get('executable') != executable.name
                    or folder.parent != executable.parent / 'datas' / 'reports' or not _inside(folder, roots)):
                raise Refused('the report is not this game\'s')
            result.files.append(folder)
    if not result.files:
        raise Refused('nothing of this game is left')
    result.saves = [entry for entry in save_entries(game) if _inside(entry, roots)]
    result.trash = all(trash_available(path) for path in result.files + result.saves)
    return result


# ---- the Recycle Bin / trash --------------------------------------------------------------------------------------------

def _windows_fixed_drive(path: Path) -> bool:
    import ctypes
    anchor = Path(path).resolve().anchor
    if not anchor or anchor.startswith('\\\\'):
        return False                                    # a network share: no Recycle Bin
    return ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(anchor)) == 3    # DRIVE_FIXED


def _xdg_trash() -> Path | None:
    data = os.environ.get('XDG_DATA_HOME') or str(Path.home() / '.local' / 'share')
    return Path(data) / 'Trash'


def trash_available(path) -> bool:
    """Can `path` go to a Recycle Bin or trash (else its deletion is final)?"""
    path = Path(path)
    if sys.platform == 'win32':
        try:
            return _windows_fixed_drive(path)
        except OSError:
            return False
    if shutil.which('gio'):
        return True
    trash = _xdg_trash()
    try:
        return trash is not None and os.stat(path).st_dev == os.stat(Path.home()).st_dev
    except OSError:
        return False


def _windows_trash(paths) -> None:
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [('hwnd', wintypes.HWND), ('wFunc', wintypes.UINT), ('pFrom', wintypes.LPCWSTR), ('pTo', wintypes.LPCWSTR),
                    ('fFlags', ctypes.c_ushort), ('fAnyOperationsAborted', wintypes.BOOL), ('hNameMappings', ctypes.c_void_p),
                    ('lpszProgressTitle', wintypes.LPCWSTR)]
    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    names = ''.join(str(Path(path).resolve()) + '\0' for path in paths) + '\0'
    operation = SHFILEOPSTRUCTW(None, FO_DELETE, names, None, FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI,
                                False, None, None)
    code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if code or operation.fAnyOperationsAborted:
        raise OSError(f'the Recycle Bin refused the files (code {code})')


def _xdg_move(path: Path) -> None:
    from datetime import datetime
    from urllib.parse import quote
    trash = _xdg_trash()
    (trash / 'files').mkdir(parents=True, exist_ok=True)
    (trash / 'info').mkdir(parents=True, exist_ok=True)
    name, number = path.name, 1
    while (trash / 'files' / name).exists() or (trash / 'info' / (name + '.trashinfo')).exists():
        number += 1
        name = f'{path.stem}.{number}{path.suffix}' if path.is_file() else f'{path.name}.{number}'
    (trash / 'info' / (name + '.trashinfo')).write_text(
        f'[Trash Info]\nPath={quote(str(path.resolve()))}\nDeletionDate={datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}\n',
        encoding='utf-8')
    shutil.move(str(path), str(trash / 'files' / name))


def to_trash(paths) -> None:
    paths = [Path(path) for path in paths if Path(path).exists()]
    if not paths:
        return
    if sys.platform == 'win32':
        _windows_trash(paths)
        return
    if shutil.which('gio'):
        subprocess.run(['gio', 'trash', '--', *map(str, paths)], check=True, capture_output=True, timeout=60)
        return
    for path in paths:
        _xdg_move(path)


def delete(plan: Plan, with_saves: bool) -> None:
    """Delete what `plan` lists (the saves only `with_saves`): to the trash when it has one, else for good."""
    paths = plan.files + (plan.saves if with_saves else [])
    if plan.trash:
        to_trash(paths)
        return
    for path in paths:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()
