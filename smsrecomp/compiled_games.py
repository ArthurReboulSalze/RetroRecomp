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
from threading import Event, Lock

from .paths import data_directory, games_root, preferred_games_root, feedback_search_paths
from .systems import PROFILES, get_profile
from .library import atomic_json
from . import __version__

SHA = re.compile('[0-9a-f]{64}')
MAX_JSON = 16 * 1024 * 1024
MAX_GAMES = 50000
SKIP = {'.git', '.build', 'datas', 'artwork', 'boxart', 'boxarts', 'cache', 'states'}
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

    @property
    def key(self):
        return os.path.normcase(os.path.abspath(self.executable))


class Inventory:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_directory() / 'compiled-games.json'
        self.games = {}
        self.roots = []
        self.lock = Lock()
        try:
            data = read_json(self.path)
            if data.get('schema') != 1 or not isinstance(data.get('games'), list):
                return
            for raw in data['games'][:MAX_GAMES]:
                try:
                    game = Game(**raw)
                    get_profile(game.system)
                    if (SHA.fullmatch(game.identity) and Path(game.executable).is_absolute()
                            and game.status in STATUSES and type(game.hints) is int and game.hints >= 0
                            and type(game.favorite) is bool
                            and all(isinstance(getattr(game,key),str) for key in
                                    ('title','report','version','target','source','digest'))):
                        self.games[game.key] = game
                except (TypeError, ValueError, KeyError):
                    continue
            self.roots = [p for p in data.get('roots', []) if isinstance(p, str) and Path(p).is_absolute()][:64]
        except (OSError, ValueError, TypeError):
            pass

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(self.path, {'schema': 1, 'roots': self.roots,
                'games': [asdict(game) for game in self.games.values()]})

    def snapshot(self):
        with self.lock:
            return list(self.games.values())

    def remember(self, game):
        with self.lock:
            old = self.games.get(game.key)
            if old and not game.source:
                game.source = old.source
            game.favorite = old.favorite if old else game.favorite or any(g.favorite for g in self.games.values()
                if (g.system,g.identity)==(game.system,game.identity))
            self.games[game.key] = game

    def set_favorite(self, game, value):
        with self.lock:
            for entry in self.games.values():
                if (entry.system,entry.identity)==(game.system,game.identity):entry.favorite=bool(value)
        self.save()


def default_roots(preferences):
    selected, _ = preferred_games_root(preferences)
    return list(dict.fromkeys([games_root(), selected, *feedback_search_paths(preferences).values()]))


def _folders(roots, cancel):
    seen = set()
    for root in roots:
        root = Path(root).resolve()
        if linked(root) or not root.is_dir():
            continue
        for base, dirs, files in os.walk(root, followlinks=False):
            if cancel.is_set() or len(seen) >= MAX_GAMES:
                return
            folder = Path(base)
            key = os.path.normcase(str(folder))
            if key in seen:
                dirs[:] = []
                continue
            seen.add(key)
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
    checks = data.get('final_checks', [])
    fallback = any(any(float(check.get(key) or 0) > 0 for key in
        ('interpreter_percent', 'interpreter_cycles', 'interpreted_opcodes', 'audio_interpreted_opcodes'))
        for check in checks if isinstance(check, dict))
    title = data.get('title') or (Path(name).stem if name.lower().endswith('.exe') else name)
    return Game(str(target.resolve()), system, identity, str(title), str(Path(path).resolve()),
                str(data.get('version', '')), str(data.get('target') or
                    ('windows-x86_64' if name.lower().endswith('.exe') else '')),
                source or str(data.get('source_rom','')),
                status='fallback' if fallback else 'no_hints', tested_fallback=fallback)


def refresh(game, preferences=None, *, verify_binary=False):
    """Check one exact binary and its saved hints; no ROM reads or processes."""
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
    roots = list(dict.fromkeys(Path(p).resolve() for p in roots))
    sources = {}
    for root in roots:
        try:
            batch = read_json(root / 'datas/Retro-Recomp-batch.json')
            for item in batch.get('games', []):
                sources[(item.get('system'), item.get('sha256'))] = item.get('rom', '')
        except (OSError, ValueError, TypeError):
            pass
    count, found = 0, set()
    for folder, names in _folders(roots, cancel):
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
    # Keep missing entries visible rather than silently losing the collection.
    for game in inventory.snapshot():
        if game.key not in found and any(Path(game.executable).is_relative_to(root) for root in roots):
            if not Path(game.executable).is_file():
                game.status = 'missing'
    inventory.save()
    return count
