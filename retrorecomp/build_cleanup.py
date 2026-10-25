"""Per-game build projects under the converter's workspace (ROOT/.build).

Every conversion builds its game in a project folder of its own: generated C,
object files, raw executables and validation runs, 25 MB to several hundred MB
per game. Once the game is copied to the games folder nothing reads that
project again: learned paths live in the library under ``datas``, and reports
keep its paths as text only. Retro-Recomp removes it after a successful
publication (``release_build``) and lists and removes, on request, the projects
earlier conversions left (``leftover_projects`` / ``remove_projects``, Options
> Common > Disk space).

Only folders positively identified as one game's project are touched, by an
explicit rule per console (``classify``). Shared caches (``.deps``,
``.build/native-source``, ``nes-compiler``, ``megadrive-compiler``, the step
decoders, ``neogeo-preparation``, ``cps1-reference``, the X68000 SDK bases),
research and test folders never match. Links and junctions are never followed,
nothing outside ``ROOT/.build`` is accepted, and a project touched within the
last hour (``RECENT_SECONDS``) or locked by a running CPS-1/X68000 conversion
is kept, since another Retro-Recomp process may still be using it.
``RETRO_RECOMP_KEEP_BUILD=1`` (or ``--keep-build``) keeps projects for the
developer checks that read them after a conversion.
"""
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid

from .paths import ROOT

KEEP_VARIABLE = 'RETRO_RECOMP_KEEP_BUILD'
# A project touched this recently may belong to a conversion running in
# another Retro-Recomp process sharing this workspace: it is kept.
RECENT_SECONDS = 3600
# A removal first renames the project to this name, so a new conversion of the
# same game starts in a fresh folder; an interrupted removal is finished later.
REMOVING = '.retro-recomp-removing-'

# One rule per console, on the folder names the converters create:
#   sms/gg  core.py            sms_<title>_<CRC32>_<sha12>[_banked]
#   gb      gameboy.py         gb_<title>_<sha12>_<engine8>
#   nes     nes.py             nes_<title>_<sha12>_<engine8>[_ntsc|_pal]
#   md      console16.py       md-rom-<sha64>, md-<exact-ROM catalogue id>
#   snes    supernintendo.py   snes-rom-<sha16|32|64>, snes-<exact-ROM catalogue id>
#   ng      neogeo_build.py    ng-<cart+BIOS identity20>[-native|-<random8>]
#   cps1    cps1_conversion.py cps1/<set>-<sha12>
#   x68     x68000_conversion  x68/<win|win-llvm|linux>/<SDK12>/<machine16>
#                              (the <SDK12> base is shared: only the game below)
_SEGA = re.compile(r'(sms|gg)_.+_[0-9A-F]{8}_([0-9a-f]{12})(?:_banked)?')
_GB = re.compile(r'gb_.+_([0-9a-f]{12})_[0-9a-f]{8}')
_NES = re.compile(r'nes_.+_([0-9a-f]{12})_[0-9a-f]{8}(?:_(?:ntsc|pal))?')
_MD = re.compile(r'md-rom-([0-9a-f]{64})')
_SNES = re.compile(r'snes-rom-([0-9a-f]{16}|[0-9a-f]{32}|[0-9a-f]{64})')
_NG = re.compile(r'ng-([0-9a-f]{20})(?:-native|-[0-9a-f]{8})?')
_CPS1 = re.compile(r'[0-9a-z_]+-([0-9a-f]{12})')
_X68_HOST = re.compile(r'win(?:-llvm)?|linux')
_X68_SDK = re.compile(r'[0-9a-f]{12}')
_X68_GAME = re.compile(r'[0-9a-f]{16}')
_REMOVING = re.compile(re.escape(REMOVING) + r'[0-9a-f]{16}')
_SHA = re.compile(r'[0-9a-f]{64}')


@dataclass(frozen=True)
class Project:
    """One per-game project: its console, apparent size and whether it is kept
    (recently used, or locked by a conversion in progress)."""
    path: Path
    system: str
    size: int
    in_use: bool = False


def build_root(root: Path | None = None) -> Path:
    return Path(os.path.abspath(root or ROOT)) / '.build'


@lru_cache(maxsize=2)
def _catalogue(system: str) -> dict[str, str]:
    """Exact-ROM catalogue folders of a 16-bit console: {id: ROM SHA-256}."""
    try:
        if system == 'md':
            from .megadrive import PROFILES
        else:
            from .supernintendo import PROFILES
    except ImportError:
        return {}
    return {profile['id']: sha for sha, profile in PROFILES.items() if isinstance(profile.get('id'), str)}


def classify(parts) -> tuple[str, str] | None:
    """(console, ROM key) when a path under .build, given as its parts, is one
    game's project by name; None for anything else. The key is the SHA-256
    prefix the folder carries (the Neo Geo cartridge+BIOS identity, the X68000
    machine identity)."""
    parts = tuple(parts)
    if len(parts) == 1:
        name = parts[0]
        for pattern, system in ((_GB, 'gb'), (_NES, 'nes'), (_MD, 'md'), (_SNES, 'snes'), (_NG, 'ng')):
            if match := pattern.fullmatch(name):
                return system, match[1]
        if match := _SEGA.fullmatch(name):
            return match[1], match[2]
        if _REMOVING.fullmatch(name):
            return 'removing', ''
        for system in ('md', 'snes'):
            if name.startswith(system + '-'):
                sha = _catalogue(system).get(name[len(system) + 1:])
                if sha:
                    return system, sha
        return None
    if len(parts) == 2 and parts[0] == 'cps1' and (match := _CPS1.fullmatch(parts[1])):
        return 'cps1', match[1]
    if (len(parts) == 4 and parts[0] == 'x68' and _X68_HOST.fullmatch(parts[1])
            and _X68_SDK.fullmatch(parts[2]) and _X68_GAME.fullmatch(parts[3])):
        return 'x68', parts[3]
    return None


def _link(info) -> bool:
    # FILE_ATTRIBUTE_REPARSE_POINT also covers Windows junctions.
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def _native(path) -> str:
    """Absolute path; on Windows in its long form, as MSBuild trees exceed 260."""
    text = os.path.abspath(path)
    if os.name != 'nt' or text.startswith('\\\\?\\'):
        return text
    if text.startswith('\\\\'):
        return '\\\\?\\UNC\\' + text[2:]
    return '\\\\?\\' + text


def _relative(path, build: Path) -> tuple[str, ...] | None:
    """Parts of ``path`` below ``build``, compared without following links."""
    text, base = os.path.abspath(path), os.path.abspath(build)
    prefix = os.path.normcase(base).rstrip(os.sep) + os.sep
    if not os.path.normcase(text).startswith(prefix):
        return None
    return tuple(part for part in text[len(prefix):].split(os.sep) if part)


def _checked(path, build: Path) -> tuple[str, ...] | None:
    """The project's parts below .build after every safety check; None when it
    no longer exists. Refuses (ValueError) anything outside .build, anything
    that is not a per-game project, and links or junctions on the way."""
    parts = _relative(path, build)
    if not parts:
        raise ValueError(f'Not inside the build folder: {path}')
    if classify(parts) is None:
        raise ValueError(f'Not a per-game build project: {path}')
    current = build
    for part in ('', *parts):
        current = current / part if part else current
        try:
            info = os.lstat(_native(current))
        except FileNotFoundError:
            return None
        if _link(info):
            raise ValueError(f'Link or junction, not followed: {current}')
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f'Not a folder: {current}')
    return parts


def _measure(path, cancel=None) -> tuple[int, float]:
    """Apparent size and newest modification time; links count for nothing."""
    top = _native(path)
    total, newest = 0, os.lstat(top).st_mtime
    stack = [top]
    while stack:
        if cancel is not None and cancel.is_set():
            raise InterruptedError('Measurement cancelled.')
        try:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    newest = max(newest, info.st_mtime)
                    if _link(info):
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        stack.append(entry.path)
                    else:
                        total += info.st_size
        except OSError:
            continue
    return total, newest


def _locked(path: Path, system: str) -> bool:
    """CPS-1 and X68000 conversions hold an entry lock on their project."""
    lock = {'cps1': path / 'entry.lock', 'x68': path / 'lock' / 'entry.lock'}.get(system)
    if lock is None or not lock.is_file():
        return False
    from .library import entry_lock
    try:
        with entry_lock(lock.parent, timeout=0):
            return False
    except (TimeoutError, OSError):
        return True


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        os.unlink(path)


def _rmdir(path: str) -> None:
    try:
        os.rmdir(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
        os.rmdir(path)


def _delete_tree(top: str) -> None:
    """Remove a folder; a link or junction inside is removed itself, never
    followed. Read-only files (Git checkouts) are made writable first."""
    with os.scandir(top) as entries:
        children = list(entries)
    for entry in children:
        info = entry.stat(follow_symlinks=False)
        if _link(info):
            try:
                os.unlink(entry.path)
            except OSError:
                os.rmdir(entry.path)    # a directory link or junction
        elif stat.S_ISDIR(info.st_mode):
            _delete_tree(entry.path)
        else:
            _unlink(entry.path)
    _rmdir(top)


def _remove(path, build: Path, *, keep_recent: bool, cancel=None) -> tuple[str, int]:
    """('removed' | 'in_use' | 'missing', bytes). ValueError when refused;
    OSError when the removal stopped part way (finished by a later removal)."""
    parts = _checked(path, build)
    if parts is None:
        return 'missing', 0
    path = build.joinpath(*parts)
    system = classify(parts)[0]
    size, newest = _measure(path, cancel)
    if (keep_recent and newest > time.time() - RECENT_SECONDS) or _locked(path, system):
        return 'in_use', size
    target = path
    if system != 'removing':
        target = build / (REMOVING + uuid.uuid4().hex[:16])
        # Windows refuses to rename a folder while a process has a file open
        # in it: that project is in use. The retries cover antivirus scans.
        for attempt in range(3):
            try:
                os.rename(_native(path), _native(target))
                break
            except FileNotFoundError:
                return 'missing', 0
            except OSError:
                if attempt == 2:
                    return 'in_use', size
                time.sleep(.25)
    _delete_tree(_native(target))
    return 'removed', size


def _megabytes(count: int) -> str:
    return f'{count / 1048576:.1f} MB' if count >= 104858 else f'{count / 1024:.0f} KB'


# ------------------------------------------------------- after a publication

def _owner(path: Path, system: str) -> str | None:
    """The full ROM SHA-256 a Neo Geo or SNES project records, if any."""
    try:
        if system == 'ng':
            value = json.loads((path / 'input.json').read_text(encoding='utf-8'))['source']['sha256']
        else:
            value = json.loads((path / 'generation-identity.json').read_text(encoding='utf-8'))['rom']
        return value if isinstance(value, str) and _SHA.fullmatch(value) else None
    except (OSError, ValueError, KeyError, TypeError):
        pass
    cartridge = path / 'cartridge.sfc'
    if system == 'snes' and cartridge.is_file():
        try:
            with cartridge.open('rb') as file:
                return hashlib.file_digest(file, 'sha256').hexdigest()
        except OSError:
            return None
    return None


def _same_rom(system: str, key: str, sha256: str, path: Path, machine: str = '') -> bool:
    if system in ('sms', 'gg', 'gb', 'nes', 'cps1'):
        return key == sha256[:12]
    if system == 'md':
        return key == sha256
    if system == 'snes':
        return key == sha256 or (len(key) < 64 and sha256.startswith(key) and
                                 _owner(path, 'snes') in (sha256, None))
    if system == 'ng':
        return _owner(path, 'ng') == sha256
    if system == 'x68':
        return bool(machine) and key == machine[:16]
    return False


def report_project(system: str, report: dict, root: Path | None = None) -> Path | None:
    """The per-game project a conversion report names (build_directory, else
    build_executable at any depth: Visual Studio and Ninja builds differ)."""
    build = build_root(root)
    for key in ('build_directory', 'build_executable'):
        value = report.get(key)
        if not isinstance(value, str) or not value:
            continue
        parts = _relative(value, build)
        for depth in range(1, len(parts or ()) + 1):
            found = classify(parts[:depth])
            if found:
                return build.joinpath(*parts[:depth]) if found[0] == system else None
    return None


def _subfolders(path: Path):
    """Real subfolders; nothing below a link or junction."""
    try:
        if _link(os.lstat(_native(path))):
            return []
        with os.scandir(_native(path)) as entries:
            return sorted(entry.name for entry in entries
                          if entry.is_dir(follow_symlinks=False) and not _link(entry.stat(follow_symlinks=False)))
    except OSError:
        return []


def game_projects(system: str, sha256: str, report: dict, root: Path | None = None) -> list[Path]:
    """The project this conversion's report names, then the same cartridge's
    projects left by earlier versions (another engine revision, title, video
    standard or back end). Empty unless the report names its project and that
    project carries this ROM's identity."""
    build = build_root(root)
    if not _SHA.fullmatch(sha256 or ''):
        return []
    machine = report.get('source_identity', '') if system == 'x68' else ''
    machine = machine if isinstance(machine, str) and _SHA.fullmatch(machine) else ''
    project = report_project(system, report, root)
    if project is None:
        return []
    key = classify(_relative(project, build))[1]
    # The report itself names this project: a Neo Geo project that does not
    # record its source yet still belongs to this conversion.
    if not (_same_rom(system, key, sha256, project, machine) or
            system == 'ng' and _owner(project, 'ng') is None):
        return []
    found = [project]
    if system == 'cps1':
        candidates = [build / 'cps1' / name for name in _subfolders(build / 'cps1')]
    elif system == 'x68':
        candidates = [build / 'x68' / host / sdk / name
                      for host in _subfolders(build / 'x68') for sdk in _subfolders(build / 'x68' / host)
                      for name in _subfolders(build / 'x68' / host / sdk)]
    else:
        candidates = [build / name for name in _subfolders(build)]
    for path in candidates:
        found_key = classify(_relative(path, build))
        if (path != project and found_key and found_key[0] == system and
                _same_rom(system, found_key[1], sha256, path, machine)):
            found.append(path)
    return found


def keep_requested() -> bool:
    return os.environ.get(KEEP_VARIABLE, '').strip().casefold() not in ('', '0', 'false', 'no')


def release_build(item, report: dict, emit=print, root: Path | None = None) -> int:
    """After a successful publication: remove the game's build project and the
    same cartridge's older ones. Never raises; returns the bytes freed.

    The batch converts one cartridge at a time (two queue rows with the same
    ROM never run together), so no other conversion of this batch uses these
    folders. Older projects of the same ROM are kept if touched within the
    hour, for another Retro-Recomp process sharing this workspace.
    """
    title = getattr(item, 'title', '') or 'Game'
    if keep_requested():
        emit(f'{title}: build folder kept ({KEEP_VARIABLE}).')
        return 0
    build = build_root(root)
    freed, kept = 0, []
    try:
        projects = game_projects(item.system, item.sha256, report, root)
    except Exception as exc:
        emit(f'{title}: build folder kept: {exc}')
        return 0
    for number, path in enumerate(projects):
        try:
            outcome, size = _remove(path, build, keep_recent=number > 0)
        except Exception as exc:
            kept.append(f'{path.name} ({exc})')
            continue
        if outcome == 'removed':
            freed += size
        elif outcome == 'in_use':
            kept.append(f'{path.name} (in use)')
    if freed:
        emit(f'{title}: build files removed after publication, {_megabytes(freed)} freed.')
    if kept:
        emit(f'{title}: build folder kept: ' + '; '.join(kept))
    return freed


# ------------------------------------------------------------- free space

def leftover_projects(root: Path | None = None, *, cancel=None) -> list[Project]:
    """Every per-game project under .build with its size, including removals
    an earlier session could not finish. Read only; may take a while."""
    build = build_root(root)
    try:
        if _link(os.lstat(_native(build))):
            return []
    except OSError:
        return []
    candidates = [(name,) for name in _subfolders(build)]
    candidates += [('cps1', name) for name in _subfolders(build / 'cps1')]
    candidates += [('x68', host, sdk, name) for host in _subfolders(build / 'x68')
                   for sdk in _subfolders(build / 'x68' / host)
                   for name in _subfolders(build / 'x68' / host / sdk)]
    found = []
    now = time.time()
    for parts in candidates:
        kind = classify(parts)
        if kind is None:
            continue
        path = build.joinpath(*parts)
        try:
            size, newest = _measure(path, cancel)
        except InterruptedError:
            raise
        except OSError:
            continue
        in_use = newest > now - RECENT_SECONDS or _locked(path, kind[0])
        found.append(Project(path, kind[0], size, in_use))
    return found


def remove_projects(projects, root: Path | None = None, *, cancel=None, emit=None) -> dict:
    """Remove listed projects that are still per-game projects and not in use.
    Each one is checked again (rules, links, recent use, locks) first."""
    build = build_root(root)
    summary = {'removed': 0, 'freed': 0, 'kept': 0, 'kept_bytes': 0, 'errors': []}
    for project in projects:
        if cancel is not None and cancel.is_set():
            break
        try:
            outcome, size = _remove(project.path, build, keep_recent=True, cancel=cancel)
        except InterruptedError:
            break
        except (OSError, ValueError) as exc:
            summary['errors'].append(f'{project.path.name}: {exc}')
            continue
        if outcome == 'removed':
            summary['removed'] += 1
            summary['freed'] += size
        elif outcome == 'in_use':
            summary['kept'] += 1
            summary['kept_bytes'] += size
    if emit:
        emit(f"Disk space: {summary['removed']} build folders removed, {_megabytes(summary['freed'])} freed; "
             f"{summary['kept']} kept in use." + ''.join('\n  ' + error for error in summary['errors']))
    return summary
