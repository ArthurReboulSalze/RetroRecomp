"""Read-only ROM lookup by the console reader's exact content identity.

Names only order candidates. This private index is never compilation knowledge.
"""
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import os
import re
from threading import Event

from .compiled_games import read_json, linked, MAX_GAMES, SKIP
from .library import atomic_json
from .paths import data_directory, export_directory
from .systems import get_profile, profile_for_path


# Multi-disk X68000 games named "(Disk 1 of 2)", "(Disk 2)" or "(Disk B)".
# Grouping only arranges the player's own files: the console reader still
# hashes every disk, and a set keeps the identity of the equivalent M3U. It
# lives here, outside the fingerprinted compiler modules, so it never changes
# an exported game's stamp.
DISK_TAG = re.compile(r'\(\s*dis[kc]\s+(\d{1,2}|[a-z])(?:\s+of\s+(\d{1,2}))?\s*\)', re.I)
DISK_SUFFIXES = ('.dim', '.xdf')
MAX_SET_DISKS = 10


@dataclass
class DiskSets:
    paths: list
    grouped: int = 0
    # (title, missing disk numbers, total) for sets named with gaps.
    incomplete: list = field(default_factory=list)


def disk_tag(name):
    """(prefix, dump flags, number, total) of a disk named as part of a set."""
    stem = Path(name).stem
    match = DISK_TAG.search(stem)
    if not match:
        return None
    value = match.group(1)
    number = int(value) if value.isdigit() else ord(value.casefold()) - ord('a') + 1
    total = int(match.group(2)) if match.group(2) else None
    if number < 1 or (total is not None and not number <= total <= MAX_SET_DISKS):
        return None
    # "[a]" alternate dumps form their own set, never mixed with the originals.
    flags = ''.join(re.findall(r'\[[^\]]*\]', stem[match.end():]))
    return stem[:match.start()].rstrip(), flags, number, total


def _normalized(path):
    # No resolve(): on a network share it would open every disk of the folder.
    return os.path.normcase(os.path.abspath(path))


def playlist_disks(path):
    """Disks a player's own M3U names, resolved like the console reader."""
    try:
        if path.stat().st_size > 32768:
            return set()
        lines = path.read_text(encoding='utf-8-sig').splitlines()
    except (OSError, ValueError):
        return set()
    disks = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or '\x00' in line or '://' in line:
            continue
        value = Path(line)
        disks.add(_normalized(value if value.is_absolute() else path.parent / value))
    return disks


def _write_playlist(directory, name, disks):
    lines = [str(path) for path in disks]
    digest = hashlib.sha256('\0'.join(map(os.path.normcase, lines)).encode('utf-8')).hexdigest()[:16]
    target = directory / digest / (name + '.m3u')
    text = '# Retro-Recomp: disks grouped by name; the originals stay in place.\n' + '\n'.join(lines) + '\n'
    try:
        if target.read_text(encoding='utf-8') == text:
            return target
    except (OSError, ValueError):
        pass
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.tmp')
    temporary.write_text(text, encoding='utf-8', newline='\n')
    os.replace(temporary, target)
    return target


def disk_sets(paths, directory=None):
    """Queue each multi-disk set once, as an ordered playlist.

    Disks named by a player's own M3U in the list stay inside it. Other disks
    of one folder that share a title and dump flags become one generated M3U
    under datas; nothing is written beside the ROMs. The other disks of an
    explicitly added one join it. A set that repeats a disk number, disagrees
    on its size or exceeds ten disks is left as separate files.
    """
    paths = [Path(path) for path in paths]
    covered = set()
    for path in paths:
        if path.suffix.casefold() == '.m3u' and path.is_file():
            covered |= playlist_disks(path)
    groups, membership, listed, folders = {}, {}, set(), {}
    for path in paths:
        tag = disk_tag(path.name) if path.suffix.casefold() in DISK_SUFFIXES else None
        if not tag or not path.is_file():
            continue
        name = _normalized(path)
        if name in covered:
            continue
        parent = os.path.normcase(os.path.abspath(path.parent))
        key = (parent, tag[0].casefold(), tag[1].casefold())
        if parent not in folders:
            try:
                folders[parent] = [Path(entry.path) for entry in os.scandir(path.parent)
                                   if Path(entry.name).suffix.casefold() in DISK_SUFFIXES and entry.is_file()]
            except OSError:
                folders[parent] = []
        if key not in groups:
            groups[key] = {}
            for sibling in [path, *folders[parent]]:
                other = disk_tag(sibling.name)
                if (other and (other[0].casefold(), other[1].casefold()) == key[1:]
                        and _normalized(sibling) not in covered):
                    groups[key].setdefault(_normalized(sibling), (*other, sibling))
        membership[name] = key
        listed.add(name)
    result, emitted = [], set()
    grouped, incomplete = 0, []
    folder = directory or data_directory() / 'x68000-sets'
    for path in paths:
        name = _normalized(path) if path.suffix.casefold() in DISK_SUFFIXES else None
        if name in covered:
            continue
        key = membership.get(name)
        if key is None:
            result.append(path)
            continue
        if key in emitted:
            continue
        emitted.add(key)
        disks = sorted(groups[key].values(), key=lambda disk: disk[2])
        # Absolute: the generated playlist lives elsewhere than the disks.
        files = [Path(os.path.abspath(disk[4])) for disk in disks]
        numbers = [disk[2] for disk in disks]
        totals = {disk[3] for disk in disks if disk[3]}
        total = max(totals or numbers)
        if len(set(numbers)) != len(numbers) or len(totals) > 1 or total > MAX_SET_DISKS:
            result.extend(file for file in files if _normalized(file) in listed)
            continue
        prefix, flags = disks[0][0], disks[0][1]
        missing = sorted(set(range(1, total + 1)) - set(numbers))
        if missing:
            # Full name: an alternate dump's flags tell it from a complete set.
            incomplete.append(((prefix + flags) or files[0].stem, missing, total))
        if len(files) == 1:
            result.append(files[0])
            continue
        try:
            result.append(_write_playlist(folder, (prefix + flags) or 'Disks', files))
            grouped += 1
        except OSError:
            result.extend(files)
    return DiskSets(result, grouped, incomplete)


def rom_folders(preferences):
    saved = preferences.get('rom_paths', {})
    if not isinstance(saved, dict):return {}
    result = {}
    for system, raw in saved.items():
        try:
            get_profile(system)
            if not isinstance(raw, str) or not raw.strip():continue
            path = Path(raw.strip()).expanduser()
            result[system] = path if path.is_absolute() else export_directory()/path
        except (ValueError, OSError):pass
    return result


class RomSources:
    def __init__(self, directory=None):
        self.path = (directory or data_directory())/'rom-index.json'
        try:self.records = read_json(self.path).get('files', {})
        except (OSError, ValueError):self.records = {}
        if not isinstance(self.records, dict):self.records = {}

    def identify(self, path, system):
        path = Path(path).expanduser().resolve()
        stat = path.stat()
        if not path.is_file() or linked(path):return ''
        signature = [stat.st_size, stat.st_mtime_ns]
        key = os.path.normcase(str(path))
        old = self.records.get(key, {})
        # Neo Geo sets may depend on parent ZIPs: validate that context afresh.
        if (system != 'ng' and isinstance(old, dict) and old.get('system') == system
                and old.get('stamp') == signature):
            return old.get('identity', '')
        profile = profile_for_path(path, system)
        identity = profile.read_rom(path).sha256
        self.records[key] = dict(system=system, identity=identity, stamp=signature)
        return identity

    def matches(self, path, game):
        from .core import ConversionError
        try:return self.identify(path, game.system) == game.identity
        except (OSError, ValueError, KeyError, TypeError, ConversionError):return False

    def resolve(self, games, preferences, *, known=(), cancel=None, progress=lambda title:None):
        """Worker-only: bounded recursive lookup, ZIPs included, no writes to ROMs."""
        cancel = cancel or Event()
        roots = rom_folders(preferences)
        candidates = {}
        resolved = []
        for game in games:
            if cancel.is_set():break
            progress(game.title)
            direct = [game.source, *(g.source for g in known if
                g.system == game.system and g.identity == game.identity)]
            try:
                report = read_json(game.report)
                direct += [report.get('source_rom', ''), report.get('rom', {}).get('path', '')]
            except (OSError, ValueError, TypeError):pass
            source = next((Path(p) for p in dict.fromkeys(direct) if p and self.matches(p, game)), None)
            if source is None and game.system in roots:
                if game.system not in candidates:
                    extensions = {*get_profile(game.system).extensions, '.zip', '.bin', '.rom'}
                    files = []
                    root = roots[game.system]
                    for base, dirs, names in os.walk(root, followlinks=False):
                        if cancel.is_set() or len(files) >= MAX_GAMES:break
                        folder = Path(base)
                        dirs[:] = [d for d in dirs if d.casefold() not in SKIP and not linked(folder/d)]
                        if len(folder.relative_to(root).parts) >= 12:dirs[:] = []
                        files.extend(folder/n for n in names if Path(n).suffix.casefold() in extensions)
                    if game.system == 'x68':
                        # A multi-disk set has its own identity, never one disk's.
                        files = disk_sets(files, self.path.parent / 'x68000-sets').paths
                    candidates[game.system] = files[:MAX_GAMES]
                from .cover_titles import normalized
                title = normalized(game.title, base=True)
                ordered = sorted(candidates[game.system], key=lambda p:(
                    normalized(p.stem, base=True) != title, str(p).casefold()))
                for path in ordered:
                    if cancel.is_set():break
                    if self.matches(path, game):
                        source = path
                        break
            resolved.append((game, source))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(self.path, {'schema':1, 'files':dict(list(self.records.items())[-MAX_GAMES:])})
        return resolved
