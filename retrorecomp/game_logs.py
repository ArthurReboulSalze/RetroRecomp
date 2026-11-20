"""What a game the converter starts says, kept: its stderr and stdout in `datas/logs/games`, one file per launch.

A game started by Compiled Games, the Front-end or a multiplayer room writes its own lines (« [host] … », « [session] … »)
to a file here instead of nowhere, so a game that closes by itself leaves its reason (Mario Kart: Super Circuit's link
cable, 20 Nov 2026: « the link cable stopped: … dispatch entry is missing » was lost on both PCs). The folder stays small:
each file is cut to its last `KEEP_BYTES` once its game is over (or at the next launch), and only the `KEEP_FILES` most
recent are kept. Nothing here is ever sent anywhere: the files stay on this PC.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

KEEP_BYTES = 64 * 1024
KEEP_FILES = 20
# The lines that say why a game stopped, looked for first among its own « [host] » / « [session] » lines.
REASON_WORDS = ('stopped', 'refused', 'error', 'missing', 'lost', 'failed', 'cannot', 'desync')
REASON = re.compile(r'\b(?:' + '|'.join(REASON_WORDS) + r')\b(?!\s*=)', re.IGNORECASE)


def logs_folder(root: Path | None = None) -> Path:
    """`datas/logs` of the converter (the room log and the games' folder live there)."""
    from . import paths
    return paths.data_directory(root) / 'logs'


def _safe(name: str) -> str:
    text = re.sub(r'[^A-Za-z0-9._ -]+', '_', name).strip(' ._')
    return text[:60] or 'game'


def cut(path: Path, keep: int = KEEP_BYTES) -> None:
    """Keeps the last `keep` bytes of a log, from a line start. A file a running game still holds is left as it is."""
    try:
        size = path.stat().st_size
        if size <= keep:
            return
        with open(path, 'rb') as stream:
            stream.seek(size - keep)
            tail = stream.read()
        start = tail.find(b'\n')
        tail = tail[start + 1:] if 0 <= start < len(tail) - 1 else tail
        path.write_bytes(b'[log] the start of this log was cut (only the last 64 KB are kept)\n' + tail)
    except OSError:
        pass


def tidy(folder: Path, room_for: int = 0) -> None:
    """Cuts every log to `KEEP_BYTES` and removes the oldest beyond `KEEP_FILES - room_for` (a new one is coming)."""
    try:
        logs = sorted(folder.glob('*.log'), key=lambda path: path.stat().st_mtime, reverse=True)
    except OSError:
        return
    keep = max(0, KEEP_FILES - room_for)
    for path in logs[keep:]:
        try:
            path.unlink()
        except OSError:
            pass                    # a game still writing it: removed at a later launch
    for path in logs[:keep]:
        cut(path)


def new_game_log(executable, folder: Path | None = None) -> Path | None:
    """The file a game about to start writes its lines to (`<title>-<date-time>.log` in `datas/logs/games`), after the
    folder is tidied; None when the folder cannot be made (the game then starts without one, as before)."""
    folder = Path(folder) if folder is not None else logs_folder() / 'games'
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    tidy(folder, room_for=1)
    stem = f'{_safe(Path(executable).stem)}-{time.strftime("%Y%m%d-%H%M%S")}'
    path, number = folder / f'{stem}.log', 2
    while path.exists():
        path, number = folder / f'{stem}-{number}.log', number + 1
    return path


def reason_line(path: Path | None) -> str:
    """The line of a game's log that best says why it stopped: the last « [host] » / « [session] » line with one of
    `REASON_WORDS`, else its last such line at all; '' when there is none (or no log)."""
    if path is None:
        return ''
    try:
        with open(path, 'rb') as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - KEEP_BYTES))
            text = stream.read().decode('utf-8', 'replace')
    except OSError:
        return ''
    own = [line.strip() for line in text.splitlines() if line.strip().startswith(('[host]', '[session]'))]
    # a word that says why, never a counter of the same name (« missing=326 » in the audio line)
    told = [line for line in own if REASON.search(line)]
    return (told or own or [''])[-1][:300]
