"""Persistent, private inventory of generated games. Never executes scanned files.

Inventory is presentation metadata, not compilation knowledge or qualification.
Saved feedback remains bounded and every regeneration retains the normal gates.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
from threading import Event, Lock

from .paths import data_directory, games_root, preferred_games_root, feedback_search_paths
from .systems import available_profiles, get_profile
PROFILES = available_profiles()
from .library import atomic_json
from . import __version__

SHA = re.compile('[0-9a-f]{64}')
MAX_JSON = 16 * 1024 * 1024
MAX_GAMES = 50000
SKIP = {'.git', '.build', '.deps', '__pycache__', 'uninstall', 'datas', 'artwork', 'boxart', 'boxarts', 'cache', 'states'}
STATUSES = {'no_hints','new_hints','fallback','covered','missing','changed','unreadable','unverified'}


def read_json(path, limit=MAX_JSON):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Metadata file is too large.')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Invalid metadata.')
    return value


def linked(path):
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except OSError:
        return True


# Consoles whose reports keep the scan level under advanced_scan, and the
# revision of how the collection reads levels (1.5.6).
ADVANCED_SCAN_SYSTEMS = ('md', 'snes', 'nes')
LEVELS_REVISION = 2


@dataclass
class Game:
    executable: str
    system: str
    identity: str
    title: str
    report: str = ''
    version: str = ''
    target: str = ''
    source: str = ''
    status: str = 'no_hints'
    hints: int = 0
    tested_fallback: bool = False
    size: int = 0
    modified: int = 0
    digest: str = ''
    feedback_error: bool = False
    receipt_hash: str = ''
    favorite: bool = False
    # Sizes and dates of the files this row depends on (see watch_signature).
    watch: str = ''
    # The deepest scan level a discovery of this export completed (report_level):
    # standard, extended or thorough; '' until its report is read.
    level: str = ''

    @property
    def key(self):
        return os.path.normcase(os.path.abspath(self.executable))


class Inventory:
    def __init__(self, path=None, *, base=None):
        self.path = (Path(path) if path else data_directory() / 'compiled-games.json').resolve()
        self.base = (Path(base).resolve() if base is not None else
            self.path.parent.parent if self.path.parent.name.casefold() == 'datas' else self.path.parent)
        self.games = {}
        self.roots = []
        self.lock = Lock()
        self.relocation_pending = self.legacy_paths = False
        try:
            data = read_json(self.path)
            if data.get('schema') != 1 or not isinstance(data.get('games'), list):
                return
            # Saved before 1.5.6: Mega Drive, Super Nintendo and NES levels were
            # read as Standard; those rows read their report once more.
            reread_levels = data.get('levels') != LEVELS_REVISION
            previous = data.get('base')
            previous = Path(previous) if isinstance(previous, str) and Path(previous).is_absolute() else None
            self.legacy_paths = previous is None or data.get('legacy_paths') is True
            self.relocation_pending = bool(data['games']) and (self.legacy_paths or previous != self.base)
            for raw in data['games'][:MAX_GAMES]:
                try:
                    game = Game(**raw)
                    get_profile(game.system)
                    if (SHA.fullmatch(game.identity) and Path(game.executable).is_absolute()
                            and game.status in STATUSES and type(game.hints) is int and game.hints >= 0
                            and type(game.favorite) is bool
                            and all(isinstance(getattr(game,key),str) for key in
                                    ('title','report','version','target','source','digest','level'))):
                        if previous is not None:
                            for field in ('executable', 'report', 'source'):
                                setattr(game, field, _rebase(getattr(game, field), previous, self.base))
                        if reread_levels and game.system in ADVANCED_SCAN_SYSTEMS and game.level == 'standard':
                            game.level = ''
                        old = self.games.get(game.key)
                        if old and (old.system, old.identity) == (game.system, game.identity):
                            game.favorite |= old.favorite
                            game.source = game.source or old.source
                        self.games[game.key] = game
                except (TypeError, ValueError, KeyError):
                    continue
            self.roots = [p for p in data.get('roots', []) if isinstance(p, str) and Path(p).is_absolute()][:64]
            if previous is not None:
                self.roots = list(dict.fromkeys(_rebase(p, previous, self.base) for p in self.roots))
        except (OSError, ValueError, TypeError):
            pass

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(self.path, {'schema': 1, 'levels': LEVELS_REVISION, 'base': str(self.base), 'legacy_paths': self.legacy_paths, 'roots': self.roots,
                'games': [asdict(game) for game in self.games.values()]})

    def snapshot(self):
        with self.lock:
            return list(self.games.values())

    def remember(self, game):
        with self.lock:
            old = self.games.get(game.key)
            if old and (old.system, old.identity) != (game.system, game.identity):
                old = None
            if old and not game.source:
                game.source = old.source
            game.favorite = game.favorite or (old.favorite if old else any(g.favorite for g in self.games.values()
                if (g.system,g.identity)==(game.system,game.identity)))
            self.games[game.key] = game

    def relocate(self):
        """Repair known local paths only; never walk folders or open game binaries.

        Modern inventories retain the converter base, so rebasing happens while
        loading. Legacy migration uses the copied report or an exact existing
        collection entry, never a title-only match. Called in the view's worker.
        """
        if not self.relocation_pending:
            return 0
        backup = self.path.with_name(self.path.stem + '.before-path-migration.json')
        try:
            with self.path.open('rb') as original, backup.open('xb') as output:
                shutil.copyfileobj(original, output)
        except FileExistsError:
            pass
        changed, bases = 0, set()
        if self.legacy_paths:
            for game in self.snapshot():
                old_base = _legacy_base(game)
                if old_base is None or old_base == self.base:
                    continue
                executable = Path(_rebase(game.executable, old_base, self.base))
                if not executable.is_file() or linked(executable):
                    continue
                candidate = Game(**{**asdict(game), 'executable': str(executable),
                                  'report': _rebase(game.report, old_base, self.base)})
                with self.lock:
                    local = self.games.get(candidate.key)
                if local and (local.system, local.identity) != (game.system, game.identity):
                    continue
                if local is None:
                    try:
                        if not candidate.report or linked(Path(candidate.report)):
                            continue
                        report = game_from_report(Path(candidate.report), executable.parent)
                        if (report.system, report.identity, report.key) != (game.system, game.identity, candidate.key):
                            continue
                        candidate.target = candidate.target or report.target
                        candidate.version = candidate.version or report.version
                    except (OSError, ValueError, TypeError, KeyError):
                        continue
                else:
                    candidate = Game(**{**asdict(local), 'favorite': local.favorite or game.favorite,
                                      'source': local.source or game.source,
                                      'report': local.report or candidate.report})
                self.remember(candidate)
                with self.lock:
                    self.games.pop(game.key, None)
                bases.add(old_base)
                changed += 1
            for old_base in bases:
                self.roots = [_rebase(root, old_base, self.base) for root in self.roots]
            self.roots = list(dict.fromkeys(self.roots))
        self.legacy_paths = self.legacy_paths and any(
            (previous := _legacy_base(game)) is not None and previous != self.base
            for game in self.snapshot())
        self.relocation_pending = False
        self.save()
        return changed

    def set_favorite(self, game, value):
        with self.lock:
            for entry in self.games.values():
                if (entry.system,entry.identity)==(game.system,game.identity):entry.favorite=bool(value)
        self.save()


def _rebase(value, previous, current):
    if not value:
        return value
    try:
        return str(current / Path(value).relative_to(previous))
    except ValueError:
        return value


def _legacy_base(game):
    """Recognize only the app's conventional Games/<console>/... hierarchy."""
    path = Path(game.executable)
    console = get_profile(game.system).export_folder.casefold()
    for index in range(1, len(path.parts)-2):
        if path.parts[index].casefold() == 'games' and path.parts[index+1].casefold() == console:
            return Path(*path.parts[:index])
    return None


def default_roots(preferences):
    selected, _ = preferred_games_root(preferences)
    return list(dict.fromkeys([games_root(), selected, *feedback_search_paths(preferences).values()]))


def _folders(roots, cancel, visited, errors):
    seen = set()
    for root in roots:
        root = Path(root).resolve()
        if linked(root) or not root.is_dir():
            errors.add(root)
            continue
        def error(exc):
            errors.add(Path(exc.filename).resolve() if exc.filename else root)
        for base, dirs, files in os.walk(root, followlinks=False, onerror=error):
            if cancel.is_set() or len(seen) >= MAX_GAMES:
                errors.add(None)
                return
            folder = Path(base)
            key = os.path.normcase(str(folder))
            if key in seen:
                dirs[:] = []
                continue
            seen.add(key)
            visited.add(folder)
            errors.update(folder / name for name in dirs if linked(folder / name))
            dirs[:] = [name for name in dirs if name.casefold() not in SKIP
                       and not linked(folder / name)] if len(folder.relative_to(root).parts) < 12 else []
            yield folder, files


def _platform(path):
    with path.open('rb') as stream:
        head = stream.read(20)
    if head[:2] == b'MZ':
        return 'windows-x86_64'
    if head[:6] == b'\x7fELF\x02\x01':
        return {62: 'linux-x86_64', 183: 'linux-arm64'}.get(int.from_bytes(head[18:20], 'little'), '')
    return ''


def game_from_report(path, folder=None, *, source=''):
    data = read_json(path)
    if data.get('tool') != 'Retro-Recomp':
        raise ValueError('Unrecognized conversion report.')
    system = data['system']['id']
    get_profile(system)
    identity = data['rom']['sha256']
    name = data['executable']
    if (not isinstance(identity, str) or not SHA.fullmatch(identity) or not isinstance(name, str)
            or name in ('', '.', '..') or '/' in name or '\\' in name):
        raise ValueError('Invalid exported identity.')
    if folder is None:
        # Current layout: <console>/datas/reports/<game>/conversion-report.json
        folder = Path(path).parents[3]
    target = Path(folder) / name
    # An upgraded export also carries the checks of the discovery it inherits.
    checks = [*data.get('final_checks', []),
              *data.get('upgrade', {}).get('discovery', {}).get('final_checks', [])]
    # Main CPU, sound CPU and a cartridge device are separate figures, but
    # interpreted device instructions still count as fallback here: never hidden.
    fallback = any(any(float(check.get(key) or 0) > 0 for key in
        ('interpreter_percent', 'interpreter_cycles', 'main_interpreted_opcodes', 'interpreted_opcodes',
         'audio_interpreted_opcodes', 'coprocessor_instructions'))
        for check in checks if isinstance(check, dict))
    title = data.get('title') or (Path(name).stem if name.lower().endswith('.exe') else name)
    return Game(str(target.resolve()), system, identity, str(title), str(Path(path).resolve()),
                str(data.get('version', '')), str(data.get('target') or
                    ('windows-x86_64' if name.lower().endswith('.exe') else '')),
                source or str(data.get('source_rom','')),
                status='fallback' if fallback else 'no_hints', tested_fallback=fallback,
                level=report_level(data))


LEVEL_STARS = {'standard': 1, 'extended': 2, 'thorough': 3}


def report_level(report) -> str:
    """The deepest scan level a conversion report's discovery completed:
    'extended' or 'thorough' when it ran (or an upgraded export inherited it),
    else 'standard'. A quick check from known or shared paths counts as
    standard: it only rechecked paths found before."""
    report = report if isinstance(report, dict) else {}
    # Mega Drive, Super Nintendo and NES reports kept their level under
    # advanced_scan only; 1.5.2-1.5.5 read only the top level and took them for
    # Standard (stars and the depth coins of their conversions). Every writer
    # now also writes scan_level and the schema-2 scan section, but exports
    # made before keep the old places, so all of them are read.
    advanced, scan = report.get('advanced_scan'), report.get('scan')
    levels = [report.get('scan_level'), scan.get('level') if isinstance(scan, dict) else None,
              advanced.get('level') if isinstance(advanced, dict) else None,
              ((report.get('upgrade') or {}).get('discovery') or {}).get('scan_level')]
    deepest = max((LEVEL_STARS.get(level, 1) for level in levels if isinstance(level, str)), default=1)
    return {1: 'standard', 2: 'extended', 3: 'thorough'}[deepest]


def watch_signature(game):
    """Stat-only signature of what a row shows: the EXE, its report and the
    gameplay feedback beside it or in the converter bank. No file is read."""
    from .feedback import private_file
    executable = Path(game.executable)
    paths = [executable, Path(game.report) if game.report else None,
             executable.parent / 'datas/fallbacks' / f'{game.system}-{game.identity}.rrfb']
    try:
        paths.append(private_file(game.system, game.identity))
    except ValueError:
        pass
    parts = []
    for path in paths:
        try:
            stat = path.stat() if path else None
            parts.append(f'{stat.st_size}:{stat.st_mtime_ns}' if stat else '-')
        except OSError:
            parts.append('-')
    return '|'.join(parts)


def refresh_changed(inventory, preferences=None, games=None, *, cancel=None, budget=None):
    """Refresh only the rows whose files changed since they were last read;
    the full scan stays available for new folders and moved games. With a
    `budget` in seconds (closing), stop once it is spent."""
    changed = 0
    deadline = time.monotonic() + budget if budget is not None else None
    for game in (inventory.snapshot() if games is None else games):
        if cancel is not None and cancel.is_set() or deadline is not None and time.monotonic() > deadline:
            break
        # A row saved before scan levels were shown is read once more for its level.
        if watch_signature(game) == game.watch and (game.level or not game.report):
            continue
        try:
            inventory.remember(refresh(Game(**asdict(game)), preferences))
        except (OSError, ValueError, TypeError, KeyError):
            continue
        changed += 1
    if changed:
        inventory.save()
    return changed


def refresh(game, preferences=None, *, verify_binary=False):
    """Check one exact binary and its saved hints; no ROM reads or processes."""
    game = _refresh(game, preferences, verify_binary=verify_binary)
    # After the check: merging feedback may have rewritten the bank file.
    game.watch = watch_signature(game)
    return game


def _refresh(game, preferences=None, *, verify_binary=False):
    from .feedback import _load, private_file, encode, _retain
    from .freshness import feedback, digest
    path = Path(game.executable)
    try:
        stat = path.stat()
        platform = _platform(path) if verify_binary or not game.target else game.target
        if linked(path) or not path.is_file() or not platform:
            game.status = 'unverified'
            return game
    except OSError:
        game.status = 'missing'
        return game
    report = {}
    if game.report:
        try:
            candidate = read_json(game.report)
            if candidate.get('rom', {}).get('sha256') == game.identity and candidate.get('executable') == path.name:
                report = candidate
        except (OSError, ValueError, TypeError):
            pass
    if report:
        game.level = report_level(report)
    receipt = report.get('export_receipt', {})
    expected = receipt.get('sha256', '')
    different = (game.size, game.modified) != (stat.st_size, stat.st_mtime_ns)
    changed = bool(game.modified and different or game.status=='changed') and game.receipt_hash == expected
    # The collection's routine scan reads metadata and bounded feedback. Hashing
    # every large game is unnecessary here; explicit row rescans can verify it.
    # Reconvert independently checks ownership and hashes before replacement.
    if verify_binary:
        if different or not game.digest:game.digest = digest(path)
        changed = bool(expected and expected != game.digest)
    elif different:
        game.digest = ''
    game.size, game.modified = stat.st_size, stat.st_mtime_ns
    game.receipt_hash = expected
    game.target = platform
    old = feedback(report)
    if not isinstance(old, dict):old = {}
    identities = [old.get('identity', game.identity)]
    if isinstance(old.get('aes'), dict) and old['aes'].get('identity'):
        identities.append(old['aes']['identity'])
    game.hints, game.feedback_error = 0, False
    new = False
    # Known exact paths only: a row rescan never walks the full library.
    directories = [path.parent, *(Path(game.report).parents if game.report else [])]
    for root in default_roots(preferences or {}):
        directories += [root, root / get_profile(game.system).export_folder]
    for identity in identities:
        if not isinstance(identity, str) or not SHA.fullmatch(identity):
            game.feedback_error = True
            continue
        records = {}
        dropped = 0
        files = [private_file(game.system, identity)]
        files += [root / 'datas/fallbacks' / f'{game.system}-{identity}.rrfb' for root in directories]
        for file in dict.fromkeys(files):
            if not file.is_file():
                continue
            try:
                rows, overflow = _load(file, game.system, identity)
                stamp = file.stat().st_mtime_ns
                for row in rows:records[row] = max(stamp,records.get(row,0))
                dropped = max(dropped,overflow,len(records)-4096)
            except (OSError, ValueError):
                game.feedback_error = True
        if records:
            rows, overflow, _ = _retain(game.system, identity,
                sorted(records,key=lambda row:(-records[row],row)),dropped)
            game.hints += len(rows)
            previous = old if identity == identities[0] else old.get('aes', {})
            new |= hashlib.sha256(encode(sorted(rows), game.system, identity)).hexdigest() != previous.get('fingerprint')
    game.status = ('changed' if changed else 'new_hints' if new else 'unreadable' if game.feedback_error
                   else 'fallback' if game.tested_fallback else 'covered' if game.hints else 'no_hints')
    return game


def scan(inventory, roots, preferences=None, *, cancel=None, progress=lambda n: None):
    from .batch import _embedded_export_identity
    cancel = cancel or Event()
    if not cancel.is_set():
        inventory.relocate()
    roots = list(dict.fromkeys(Path(p).resolve() for p in roots))
    sources = {}
    for root in roots:
        try:
            batch = read_json(root / 'datas/Retro-Recomp-batch.json')
            for item in batch.get('games', []):
                sources[(item.get('system'), item.get('sha256'))] = item.get('rom', '')
        except (OSError, ValueError, TypeError):
            pass
    count, found, visited, errors = 0, set(), set(), set()
    for folder, names in _folders(roots, cancel, visited, errors):
        claims = {}
        for report in (folder / 'datas/reports').glob('*/conversion-report.json'):
            if linked(report):continue
            try:
                game = game_from_report(report, folder)
                if Path(game.executable).name not in names:
                    continue
                claims.setdefault(game.key, []).append(game)
            except (OSError, ValueError, TypeError, KeyError):
                continue
        for games in claims.values():
            if cancel.is_set():
                break
            game = games[0]
            if len({g.identity for g in games}) > 1:
                actual = _embedded_export_identity(Path(game.executable))
                matches = [g for g in games if g.identity == actual]
                if len(matches) != 1:
                    continue
                game = matches[0]
            else:
                game = max(games, key=lambda g: Path(g.report).stat().st_mtime_ns)
            game.source = game.source or sources.get((game.system, game.identity), '')
            cached = next((g for g in inventory.snapshot() if g.key==game.key and g.identity==game.identity),None)
            if cached:
                for field in ('size','modified','digest','receipt_hash','status'):
                    setattr(game,field,getattr(cached,field))
            inventory.remember(game)
            try:refresh(game, preferences)
            except (OSError,ValueError,TypeError,KeyError):game.status='unreadable'
            found.add(game.key)
            count += 1
            progress(count)
        # Recover moved standalone files even if their reports were not moved.
        for name in names:
            if cancel.is_set() or len(found) >= MAX_GAMES:
                break
            path = folder / name
            key = os.path.normcase(str(path))
            if key in found or linked(path) or path.suffix.lower() in ('.json', '.png', '.jpg', '.desktop', '.ini', '.rrfb'):
                continue
            try:
                if not _platform(path):
                    continue
                identity = _embedded_export_identity(path)
                if not identity:
                    continue
                old = next((g for g in inventory.snapshot() if g.identity == identity), None)
                system = next((p.id for p in PROFILES if folder.name == p.export_folder), None)
                if old is not None:
                    game = Game(**{**asdict(old), 'executable': str(path)})
                elif system:
                    game = Game(str(path), system, identity, path.stem if path.suffix.lower() == '.exe' else name)
                else:
                    continue
                inventory.remember(refresh(game, preferences))
                found.add(game.key)
                count += 1
                progress(count)
            except (OSError, ValueError, TypeError):
                continue
    # Reconcile all saved paths, including stale aliases outside the new scan
    # roots. Do not prune an interrupted scan or an unavailable drive/subtree.
    if not cancel.is_set() and None not in errors and len(found) < MAX_GAMES:
        for game in inventory.snapshot():
            path = Path(game.executable)
            try:
                path.stat()
                continue
            except FileNotFoundError:
                game.status = 'missing'
            except OSError:
                game.status = 'missing'
                continue
            if not visited or any(path.is_relative_to(root) for root in errors):
                continue
            confirmed = any(parent in visited for parent in path.parents)
            if not confirmed:
                try:
                    with os.scandir(path.parent):
                        confirmed = True
                except OSError:
                    pass
            if confirmed:
                with inventory.lock:
                    inventory.games.pop(game.key, None)
    inventory.save()
    return count
