"""Steps every console's converter used to carry its own copy of (docs/STANDARDS.md rules 1 and 7).

Each helper keeps what differed between the copies as a parameter: the text and the language of a message, the error
raised, which statuses count as a success, the keyword arguments handed on. A converter that adopts one gets the same
result it had with its copy; `tests/test_conversion_common.py` pins that with values recorded before the copies were
removed. Nothing here reads a ROM, knows a console or decides what a game is: only the shell around a conversion.

Adopted by the Master System, Game Gear, Game Boy and NES converters, then by the 16-bit consoles, Neo Geo and CPS-1
(`spawn` and `check_exit` for the probes and replays, `replace_counted` for the pinned-source patches,
`write_if_changed` for the staged files, `resolve_scan_level` and `check_run_budget` for the checks, `pinned_checkout`
for the engines cloned at a pinned revision). The X68000 converter still carries its copies and adopts them in its own
package. What compares a candidate with its reference (packed candidate, traces, saved-state continuation) is in
`conversion_gates`.
`core` imports this module, so the module imports `core` (for `ConversionError` and `run_process`) only inside
functions.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
from pathlib import Path
import subprocess
from typing import Callable, Iterable

from . import timings
from .artwork import ArtworkError, prepare_icon

PASS_LIMIT = 10
FRAME_LIMIT = 10000


def _conversion_error(text: str) -> Exception:
    from .core import ConversionError
    return ConversionError(text)


# --------------------------------------------------------------------------- single-ROM path and checks

def convert_single(rom_path: Path, root: Path, *, title: str | None, cover: Path | None, identify_arguments: tuple = (),
                   success_only: bool = False, **options) -> Path:
    """Convert one ROM the way the window and the batch do: through `convert_batch`, into the games `root`.

    `title` and `cover` go on the identified item; `options` are handed to `convert_batch` as they are (each
    console passes the ones it has). The batch row decides: an executable path comes back when the conversion
    ended well, `ConversionError(message)` otherwise. `success_only` says what ended well: the Master System and
    Game Gear accept only a fresh `success`, the other consoles refuse only an `error` row (a `current` export,
    already up to date, is a result).
    """
    from .batch import convert_batch, identify
    item = identify(rom_path, *identify_arguments)
    if title:
        item.title = title
    item.cover = cover
    game = convert_batch([item], root, **options)['games'][0]
    if (game['status'] != 'success') if success_only else (game['status'] == 'error'):
        raise _conversion_error(game['message'])
    return Path(game['executable'])


def resolve_scan_level(scan_level: str | None, default: str = 'standard') -> str:
    """The scan level a conversion runs at: the one asked for, else `default`; an unknown name is refused."""
    from .scan_levels import LEVELS
    level = scan_level or default
    if level not in LEVELS:
        raise _conversion_error(f'Unknown scan level: {level!r}.')
    return level


def check_run_budget(passes: int, frames: int, message: str, *, max_frames: int = FRAME_LIMIT) -> None:
    """Refuse a number of learning passes or of frames per test outside its range, with the console's own `message`."""
    if not 1 <= passes <= PASS_LIMIT or not 1 <= frames <= max_frames:
        raise _conversion_error(message)


def prepare_game_icon(game: Path, rom_path: Path, title: str, directory: Path, **options) -> dict:
    """`artwork.prepare_icon` for a box-art `directory` (resolved here), its failures (`ArtworkError`, `OSError`,
    resolving the folder included) raised as the converter's `ConversionError`."""
    try:
        return prepare_icon(game, rom_path, title, directory.resolve(), **options)
    except (ArtworkError, OSError) as exc:
        raise _conversion_error(str(exc)) from exc


# --------------------------------------------------------------------------- the spawn layer of probes and replays

def no_window() -> int:
    """The `creationflags` that keep a console window from opening on Windows (none elsewhere)."""
    return subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def probe_environment(remove: Iterable[str] = (), **values: str) -> dict[str, str]:
    """A copy of the environment without the `remove` names and with `values` set: a probe's own, isolated one."""
    environment = os.environ.copy()
    for name in remove:
        environment.pop(name, None)
    environment.update(values)
    return environment


def spawn(command: Iterable, *, cwd: Path, timeout: float, env: dict[str, str] | None = None, phase: str | None = None,
          **streams) -> subprocess.CompletedProcess:
    """Start a game executable for a probe or a replay and wait for it, interruptibly (Stop kills it).

    The folder `cwd` is created first, every argument is passed as text, no console window opens on Windows, and the
    wait counts in the timings `phase` when one is named. `streams` are the usual `stdout=`/`stderr=`/`text=`/
    `capture_output=` of `subprocess.run`. The exit code is not judged here: `check_exit` does that, or the caller
    reads `returncode` itself.
    """
    from .core import run_process
    cwd.mkdir(parents=True, exist_ok=True)
    with timings.phase(phase) if phase else contextlib.nullcontext():
        return run_process([str(argument) for argument in command], cwd=cwd, **({} if env is None else {'env': env}),
                           timeout=timeout, creationflags=no_window(), **streams)


def check_exit(result: subprocess.CompletedProcess, error: Callable[[subprocess.CompletedProcess], Exception]) -> None:
    """Raise `error(result)` when the process ended with a non-zero exit code."""
    if result.returncode:
        raise error(result)


# --------------------------------------------------------------------------- engines cloned at a pinned revision

def pinned_checkout(checkout: Path, revision: str, git: Callable[..., str], *, present: bool, clone: Callable[[], None],
                    moved: Callable[[str], None], dirty: Callable[[], Exception], fill: Callable[[], None] | None = None,
                    dirty_first: bool = False,
                    status: tuple[str, ...] = ('status', '--porcelain', '--untracked-files=no')) -> None:
    """Make sure `checkout` is a clean checkout of `revision`: clone it when absent, then verify it.

    Which git commands run, in which order and with which options is each console's own (the cached engines were
    cloned that way, and those commands are what a player's machine already ran), so they come in as parameters:
    `git(*arguments, **options)` runs one git command against the checkout and returns its output; `present` says
    whether it is cloned already and `clone()` clones (and checks out) it; `fill()`, when given, populates a clone
    that holds no file (a `--no-checkout` clone) and runs whenever the folder is empty; `moved(head)` is called when
    HEAD is not `revision` (it brings the checkout there or raises); `dirty()` builds the exception raised when
    tracked files carry edits. The edit check runs before the revision check when `dirty_first`, else after it. An
    existing checkout is never reset: only a missing or empty one is written.
    """
    if not present:
        clone()
    if fill is not None and not any(item.name != '.git' for item in checkout.iterdir()):
        fill()

    def clean() -> None:
        if git(*status).strip():
            raise dirty()

    def at_revision() -> None:
        head = git('rev-parse', 'HEAD').strip()
        if head != revision:
            moved(head)
    for step in (clean, at_revision) if dirty_first else (at_revision, clean):
        step()


# --------------------------------------------------------------------------- patching pinned sources, writing files

def replace_counted(source: str, old: str, new: str, *, count: int | None = 1,
                    error: Callable[[str], Exception]) -> str:
    """Replace every occurrence of `old`, provided it occurs exactly `count` times (`count=None`: at least once).

    A pinned engine whose text moved is not patched blindly: `error(old)` is raised instead, so the converter says
    where the engine changed. `error` builds the exception (its class and its text are each console's).
    """
    found = source.count(old)
    if (not found) if count is None else (found != count):
        raise error(old)
    return source.replace(old, new)


def write_if_changed(path: Path, data: bytes) -> bool:
    """Write `data` to `path` unless the file already holds exactly these bytes. True when it was written.

    A file left alone keeps its timestamp: an unchanged generated file recompiles nothing.
    """
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


@contextlib.contextmanager
def preserve_unchanged(files: Callable[[], Iterable[Path]]):
    """Let a step rewrite files, then give back the timestamp of every one whose content did not change.

    `files()` lists the files to watch, called on entry. Rewriting a host source with the same bytes would
    otherwise rebuild it; a file that really changed, or is new, keeps its new timestamp.
    """
    previous = {}
    for path in files():
        with path.open('rb') as stream:
            previous[path] = (path.stat().st_mtime_ns, path.stat().st_size,
                              hashlib.file_digest(stream, 'sha256').digest())
    yield
    for path, (mtime, size, digest) in previous.items():
        if path.is_file() and path.stat().st_size == size:
            with path.open('rb') as stream:
                current = hashlib.file_digest(stream, 'sha256').digest()
            if current == digest:
                os.utime(path, ns=(path.stat().st_atime_ns, mtime))
