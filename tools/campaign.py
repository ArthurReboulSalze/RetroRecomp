"""Verification campaign tooling for a release (developer tool, never published).

Prepares and runs the pre-release check on a sample of each console's library,
with the verdicts of tools/release_check.py:

    python tools/campaign.py select  [--roms-root DIR] [--count 10 | --random 2] [--seed 160]
    python tools/campaign.py run     CONVERTER [--jobs 4] [--level standard]
    python tools/campaign.py report
    python tools/campaign.py upgrade CONVERTER EXPORT_DIR [EXPORT_DIR ...]
    python tools/campaign.py states  pairs | files

Everything lives under ``.build/campaign-<version>/`` (or --root):

    selection.json     the games chosen per console: paths and SHA-256, never ROM bytes
    out/<console>/     one folder per chunk of games (exports, batch log, release-check.json)
    out/app/           the converter copy and its workspace, shared by every chunk
    journal/<console>/ one verdict file and one log per game (the resume point)
    summary.md/.json   what ``report`` aggregates
    upgrade/           copies of existing exports and the upgrade journal
    states/            results of the F8/F9 compatibility checks

ROM folders are only read. The default ROM root is not written here (the
publication audit forbids private network paths in tracked files): give it with
--roms-root or the RETRO_RECOMP_ROMS environment variable. Conversions are
heavy and keep their new observations in the converter workspace of this
campaign only (out/app for a frozen converter, the checkout for RetroRecomp.py).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for _entry in (str(ROOT), str(TOOLS)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)
import release_check
from retrorecomp.systems import ALL_PROFILES

CONSOLES = release_check.CONSOLES
LEVELS = release_check.LEVELS
SCHEMA = 1
DEFAULT_SEED = 160
RISK_CASES = TOOLS / 'campaign-risk-cases.json'
ROOT_ENV = 'RETRO_RECOMP_ROMS'
# Folder names of a Batocera-style ROM share (override with --folder). They are the share's own names, not the
# profile's: a machine that is not listed is looked for in a folder named after its id.
SHARE_FOLDERS = {'sms': 'mastersystem', 'gg': 'gamegear', 'gb': 'gb', 'nes': 'nes', 'md': 'megadrive',
                 'snes': 'snes', 'ng': 'neogeo', 'cps1': 'fbneo', 'x68': 'x68000'}
# Files a share keeps beside the profile's own extensions (headered and headerless Mega Drive dumps).
SHARE_EXTRA_EXTENSIONS = {'md': ('.smd', '.bin')}
DEFAULT_FOLDERS = {profile.id: SHARE_FOLDERS.get(profile.id, profile.id) for profile in ALL_PROFILES}


def _share_extensions(profile) -> tuple[str, ...]:
    """The files of a share that are games of the machine, from its profile.

    A romset is a ZIP whatever the machine's own extension (Neo Geo also reads .neo); a disk machine reads its
    disk images, not its playlists (.m3u: the disks of a set are grouped by name); a cartridge machine reads
    its cartridge extensions and the ZIPs around them."""
    if 'romset' in profile.media_kinds:
        return ('.zip',)
    own = tuple(extension for extension in profile.extensions if extension != '.m3u')
    if 'disk' in profile.media_kinds:
        return own
    return own + SHARE_EXTRA_EXTENSIONS.get(profile.id, ()) + ('.zip',)


EXTENSIONS = {profile.id: _share_extensions(profile) for profile in ALL_PROFILES}
# Games of these consoles are sets of files in ZIPs, named by their MAME/FBNeo set.
ROMSET_CONSOLES = tuple(profile.id for profile in ALL_PROFILES if 'romset' in profile.media_kinds)
# Conversions of these consoles prove the packed replay (a compressed romset executable) and the fresh-process
# states themselves: the romset machines and the disk machines, whose reports carry that evidence. A machine on
# a plain cartridge does not (its F8/F9 is checked by the compatibility tools, not by the report).
REQUIRE_PACKED = ROMSET_CONSOLES
REQUIRE_STATES = tuple(profile.id for profile in ALL_PROFILES if set(profile.media_kinds) - {'cartridge'})
REGION_ORDER = ('usa', 'world', 'europe', 'japan')
NOT_A_GAME = re.compile(r'\b(bios)\b', re.I)
MEASURES = ('native_code', 'cpu_fidelity', 'hardware_fidelity', 'gameplay', 'latency')


# ------------------------------------------------------------------ small helpers

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.casefold()).strip('-') or 'game'


def default_version() -> str:
    from retrorecomp import __version__
    return __version__


def campaign_root(version: str | None, root: Path | None) -> Path:
    return (root or ROOT / '.build' / f'campaign-{version or default_version()}').resolve()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    os.replace(temporary, path)


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def file_sha256(path: Path) -> str:
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def norm_path(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def normalize_title(text: str) -> str:
    """A file name or a title reduced to its words: no extension, no (tags) or [tags], 'X, The' as 'The X'."""
    stem = re.sub(r'\.(?:zip|7z|sms|gg|gb|gbc|nes|md|gen|smd|bin|sfc|smc|dim|xdf|m3u)$', '', text, flags=re.I)
    stem = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', ' ', stem).strip()
    moved = re.match(r'^(.*?),\s*(the|a|an)$', stem, re.I)
    if moved:
        stem = f'{moved.group(2)} {moved.group(1)}'
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', stem.casefold())).strip()


def tags_of(name: str) -> str:
    return ' '.join(re.findall(r'[\(\[]([^\)\]]*)[\)\]]', name)).casefold()


def region_rank(name: str) -> int:
    tags = tags_of(name)
    rank = next((index for index, region in enumerate(REGION_ORDER) if region in tags), len(REGION_ORDER))
    return rank + (10 if re.search(r'proto|beta|demo|hack|bootleg|unl\b|pirate', tags) else 0)


# ------------------------------------------------------------------ selection

class Candidate:
    """One game of a ROM folder: the file the converter is given, and every file that belongs to it."""

    def __init__(self, console: str, path: Path, files: list[Path] | None = None, eligible: bool = True,
                 key: str | None = None):
        self.console, self.path, self.eligible = console, path, eligible
        self.files = files or [path]
        self.key = key or (path.stem.casefold() if console in ROMSET_CONSOLES else normalize_title(path.name))
        self.title = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', path.stem).strip() or path.stem

    def __repr__(self) -> str:
        return f'Candidate({self.console}, {self.path.name})'


def arcade_catalogue(console: str) -> dict:
    """Set name -> {'parent', 'ok'} from the converter's ROM-free catalogues (ok: inside the supported scope)."""
    if console == 'cps1':
        from retrorecomp import cps1_catalogue
        return {game['set']: {'parent': game['parent'], 'ok': cps1_catalogue.supported(game)}
                for game in cps1_catalogue.games()}
    from retrorecomp import neogeo_catalogue
    return {game['set']: {'parent': game['parent'], 'ok': True} for game in neogeo_catalogue.catalogue()}


def group_disks(entries: list[Path], disk_tag=None) -> list[Candidate]:
    """X68000: a multi-disk set is one game, led by its first disk (the converter finds the others itself)."""
    if disk_tag is None:
        from retrorecomp.rom_sources import disk_tag
    singles, groups = [], {}
    for path in entries:
        tag = disk_tag(path.name)
        if tag is None:
            singles.append(Candidate('x68', path))
        else:
            groups.setdefault((tag[0].casefold(), tag[1].casefold()), []).append((tag[2], path))
    sets = []
    for (prefix, flags), disks in groups.items():
        disks.sort(key=lambda disk: (disk[0], disk[1].name.casefold()))
        files = [path for _, path in disks]
        sets.append(Candidate('x68', files[0], files, key=normalize_title(files[0].name) + flags))
    return singles + sets


def list_candidates(console: str, folder: Path, *, arcade: dict | None = None, disk_tag=None) -> list[Candidate]:
    """Every game of a ROM folder in a fixed order (sorted by name). Nothing is opened."""
    extensions = EXTENSIONS[console]
    entries = sorted((Path(entry.path) for entry in os.scandir(folder)
                      if entry.is_file() and Path(entry.name).suffix.casefold() in extensions
                      and not NOT_A_GAME.search(entry.name)), key=lambda path: (path.name.casefold(), path.name))
    if console == 'x68':
        return sorted(group_disks(entries, disk_tag), key=lambda c: (c.path.name.casefold(), c.path.name))
    result = []
    for path in entries:
        eligible = True
        if console in ROMSET_CONSOLES:
            info = (arcade or {}).get(path.stem)
            eligible = bool(info and info['ok'] and (not info['parent'] or (folder / (info['parent'] + '.zip')).is_file()))
        result.append(Candidate(console, path, eligible=eligible))
    return result


def match_risk(entry: dict, candidates: list[Candidate]) -> Candidate | None:
    """The file that stands for a risk case: same set name, or same words (region and revision tags ignored)."""
    if entry.get('set'):
        pool = [c for c in candidates if c.path.stem.casefold() == entry['set'].casefold()]
    else:
        wanted = normalize_title(entry['title'])
        prefix = bool(entry.get('prefix'))
        pool = [c for c in candidates if (c.key.startswith(wanted) if prefix else c.key == wanted)]
        if not prefix and not pool and entry.get('alternates'):
            alternates = {normalize_title(alternate) for alternate in entry['alternates']}
            pool = [c for c in candidates if c.key in alternates]
    if entry.get('prefer'):
        preferred = [c for c in pool if entry['prefer'].casefold() in tags_of(c.path.name)]
        pool = preferred or pool
    return min(pool, key=lambda c: (region_rank(c.path.name), len(c.path.name), c.path.name.casefold()),
               default=None)


def diversified(matched: list[tuple[dict, Candidate]]) -> list[tuple[dict, Candidate]]:
    """File order, but each category once before any category twice."""
    first, rest, seen = [], [], set()
    for entry, candidate in matched:
        (rest if entry.get('category') in seen else first).append((entry, candidate))
        seen.add(entry.get('category'))
    return first + rest


def identify_verifier(console: str):
    """The converter's own reading of a file: accepted only if it detects the expected console."""
    def verify(candidate: Candidate) -> tuple[bool, dict]:
        if console == 'x68':
            # Sets are grouped and read by the batch command itself.
            return True, {'verified': False}
        from retrorecomp.batch import identify
        item = identify(candidate.path, console)
        if item.error or item.skipped or item.unknown or item.system != console:
            return False, {'reason': item.error or f'detected as {item.system!r}'}
        return True, {'verified': True, 'rom_sha256': item.sha256, 'rom_bytes': item.size}
    return verify


def game_entry(console: str, candidate: Candidate, kind: str, info: dict, hasher, entry: dict | None = None) -> dict:
    files = [{'path': str(path.resolve()), 'sha256': hasher(path), 'bytes': path.stat().st_size}
             for path in candidate.files]
    sha = files[0]['sha256']
    game = {'id': f'{console}-{slug(candidate.title)}-{sha[:12]}', 'console': console, 'kind': kind,
            'title': candidate.title, 'path': str(candidate.path.resolve()), 'name': candidate.path.name,
            'file_sha256': sha, 'rom_sha256': info.get('rom_sha256'), 'verified': bool(info.get('verified')),
            'files': files, 'hermes': False}
    if entry:
        game.update(category=entry.get('category'), reason=entry.get('reason'), source=entry.get('source'),
                    risk_title=entry['title'])
        if entry.get('expect'):
            game['expect'] = entry['expect']
    return game


def select_console(console: str, folder: Path, *, count: int, seed: int, risk_entries: list[dict],
                   verify=None, hasher=file_sha256, risk_share: float = 0.5, hermes: int = 0,
                   arcade: dict | None = None, disk_tag=None, random_games: int | None = None) -> dict:
    """Half the sample from the risk cases found in the folder, the rest drawn at random from the sorted
    list with Random('seed/console'): the same folder, seed and cases always give the same games.
    With `random_games`, every risk case found is taken and exactly that many games are drawn at random
    beside them (`count` is then ignored)."""
    candidates = list_candidates(console, folder, arcade=arcade or (arcade_catalogue(console)
                                 if console in ROMSET_CONSOLES else None), disk_tag=disk_tag)
    verify = verify or (lambda candidate: (True, {}))
    chosen, keys, rejected, unmatched = [], set(), [], []
    quota = len(risk_entries) if random_games is not None else int(count * risk_share)
    matched = []
    for entry in risk_entries:
        candidate = match_risk(entry, candidates)
        if candidate is None:
            unmatched.append({'title': entry['title'], 'category': entry.get('category'), 'why': 'not in the folder'})
        elif not candidate.eligible and entry.get('expect') != 'refusal':
            unmatched.append({'title': entry['title'], 'category': entry.get('category'),
                              'why': 'outside the converter catalogue or its parent set is missing'})
        else:
            matched.append((entry, candidate))
    for entry, candidate in diversified(matched):
        if len(chosen) >= quota:
            break
        if candidate.key in keys:
            continue
        ok, info = (True, {'verified': False}) if entry.get('expect') == 'refusal' else verify(candidate)
        if not ok:
            rejected.append({'path': str(candidate.path), 'title': entry['title'], 'reason': info.get('reason')})
            continue
        keys.add(candidate.key)
        chosen.append(game_entry(console, candidate, 'risk', info, hasher, entry))
    if random_games is not None:
        count = len(chosen) + random_games
    pool = [c for c in candidates if c.eligible and c.key not in keys]
    random.Random(f'{seed}/{console}').shuffle(pool)
    for candidate in pool:
        if len(chosen) >= count:
            break
        if candidate.key in keys:
            continue
        ok, info = verify(candidate)
        if not ok:
            rejected.append({'path': str(candidate.path), 'title': candidate.title, 'reason': info.get('reason')})
            continue
        keys.add(candidate.key)
        chosen.append(game_entry(console, candidate, 'random', info, hasher))
    if hermes:
        marked = random.Random(f'{seed}/hermes/{console}').sample(sorted(game['id'] for game in chosen),
                                                                   min(hermes, len(chosen)))
        for game in chosen:
            game['hermes'] = game['id'] in marked
    return {'folder': str(folder), 'candidates': sum(1 for c in candidates if c.eligible),
            'games': chosen, 'unmatched_risk': unmatched, 'rejected': rejected}


def command_select(args) -> int:
    root = campaign_root(args.version, args.root)
    base = args.roms_root or os.environ.get(ROOT_ENV)
    if not base:
        print(f'FAIL no ROM root: give --roms-root or set {ROOT_ENV}', file=sys.stderr)
        return 2
    base = Path(base)
    folders = {**DEFAULT_FOLDERS, **dict(item.split('=', 1) for item in args.folder)}
    cases = read_json(args.risk_cases)['consoles']
    selection = {'schema': SCHEMA, 'version': args.version or default_version(), 'created_utc': now_utc(),
                 'seed': args.seed, 'count': args.count, 'risk_share': args.risk_share, 'random': args.random,
                 'hermes': args.hermes,
                 'roms_root': str(base), 'risk_cases': str(args.risk_cases),
                 'risk_cases_sha256': file_sha256(args.risk_cases), 'consoles': {}}
    status = 0
    for console in args.consoles or CONSOLES:
        folder = base / folders[console]
        if not folder.is_dir():
            print(f'FAIL {console}: no folder {folder}', file=sys.stderr)
            status = 2
            continue
        verify = (lambda candidate: (True, {})) if args.no_verify else identify_verifier(console)
        result = select_console(console, folder, count=args.count, seed=args.seed, risk_entries=cases.get(console, []),
                                verify=verify, risk_share=args.risk_share, hermes=args.hermes,
                                random_games=args.random)
        selection['consoles'][console] = result
        risk = sum(game['kind'] == 'risk' for game in result['games'])
        print(f"{console}: {len(result['games'])} game(s) ({risk} risk, {len(result['games']) - risk} random) "
              f"from {result['candidates']} candidate(s); {len(result['unmatched_risk'])} risk case(s) unmatched, "
              f"{len(result['rejected'])} rejected")
        for game in result['games']:
            print(f"    {game['kind']:6} {game['title']}" + (f"  [{game['category']}]" if game.get('category') else ''))
    write_json(root / 'selection.json', selection)
    print(f'selection written to {root / "selection.json"}')
    return status


# ------------------------------------------------------------------ run

def journal_path(root: Path, console: str, game_id: str) -> Path:
    return root / 'journal' / console / f'{game_id}.json'


def pending_games(selection: dict, root: Path, *, consoles=None, subset: str = 'all', retry_failed: bool = False,
                  redo: bool = False) -> dict[str, list[dict]]:
    """The selected games with no verdict yet (a failed verdict is kept unless retry_failed or redo)."""
    pending = {}
    for console, block in selection['consoles'].items():
        if consoles and console not in consoles:
            continue
        for game in block['games']:
            if subset == 'hermes' and not game.get('hermes'):
                continue
            path = journal_path(root, console, game['id'])
            if path.is_file() and not redo:
                try:
                    verdict = read_json(path).get('verdict')
                except (OSError, ValueError):
                    verdict = None
                if verdict in ('pass', 'refused') or (verdict == 'fail' and not retry_failed):
                    continue
            pending.setdefault(console, []).append(game)
    return pending


def smallest_games(pending: dict[str, list[dict]], count: int) -> dict[str, list[dict]]:
    """Only the `count` pending games with the fewest bytes (a smoke test of the whole chain)."""
    ranked = sorted(((sum(file['bytes'] for file in game['files']), game['id']) for games in pending.values()
                     for game in games))[:count]
    keep = {game_id for _, game_id in ranked}
    return {console: kept for console, games in pending.items()
            if (kept := [game for game in games if game['id'] in keep])}


def chunk_log_lines(text: str, title: str) -> str:
    return ''.join(line for line in text.splitlines(keepends=True)
                   if f'- {title}]' in line or line.startswith(f'{title}:') or line.startswith(f'{title} :'))


def chunk_records(games: list[dict], check: dict | None, batch: dict | None, *, chunk: str, seconds: float,
                  level: str, returncode: int | None) -> list[dict]:
    """One journal record per game of a chunk, from the batch record and release_check's result."""
    batch_games = (batch or {}).get('games', [])
    checked = {norm_path(row.get('rom')): row for row in (check or {}).get('games', []) if row.get('rom')}
    by_path = {norm_path(row.get('rom')): row for row in batch_games if row.get('rom')}
    records = []
    for index, game in enumerate(games):
        row = by_path.get(norm_path(game['path']))
        if row is None and len(batch_games) == len(games):
            # A multi-disk X68000 set is queued as a generated playlist; the order is kept.
            row = batch_games[index]
        status = row.get('status') if row else 'missing'
        message = (row or {}).get('message') or (row or {}).get('error')
        result = checked.get(norm_path(row.get('rom'))) if row else None
        problems = list(result['problems']) if result else []
        if status != 'success':
            problems.append(f'conversion {status}' + (f': {message}' if message else '')
                            if row else 'no batch result (the converter did not finish)')
        if game.get('expect') == 'refusal':
            if status == 'success':
                verdict, problems = 'fail', ['a refusal was expected, but the cartridge converted'] + problems
            else:
                verdict = 'refused' if status in ('error', 'unrecognized', 'skipped') else 'fail'
        else:
            verdict = 'pass' if status == 'success' and result and not problems else 'fail'
        records.append({'schema': SCHEMA, 'id': game['id'], 'console': game['console'], 'title': game['title'],
                        'kind': game['kind'], 'category': game.get('category'), 'path': game['path'],
                        'expect': game.get('expect'), 'verdict': verdict, 'status': status, 'message': message,
                        'level': level, 'problems': problems,
                        'gates': result.get('gates') if result else None,
                        'counts': result.get('counts') if result else None,
                        'report': (row or {}).get('report'), 'executable': (row or {}).get('executable'),
                        'upgraded': (row or {}).get('upgraded'), 'chunk': chunk, 'chunk_seconds': seconds,
                        'chunk_games': len(games), 'converter_exit': returncode, 'finished_utc': now_utc()})
    return records


def console_options(console: str, args) -> tuple[list[str], list[str]]:
    """(release_check flags, extra converter words) a console needs."""
    flags, extra = [], []
    if console in REQUIRE_PACKED:
        flags.append('--require-packed')
    if console in REQUIRE_STATES:
        flags.append('--require-states')
    if console == 'ng' and args.ng_bios:
        extra += ['--ng-bios', Path(args.ng_bios).as_posix()]
    if console == 'x68':
        for option, value in (('--x68-ipl', args.x68_ipl), ('--x68-cgrom', args.x68_cgrom)):
            if value:
                extra += [option, Path(value).as_posix()]
    return flags, extra


def run_chunk(converter: Path, console: str, games: list[dict], root: Path, number: int, args,
              check=release_check.main) -> list[dict]:
    """One release_check call on a few games of one console, then one journal record per game."""
    name = f'chunk-{number:03d}'
    work = root / 'out' / console / name
    flags, extra = console_options(console, args)
    argv = [str(converter), *[game['path'] for game in games], '--console', console, '--work', str(work),
            '--app', str(root / 'out' / 'app'), '--level', args.level, '--max-fallback', str(args.max_fallback),
            '--jobs', str(min(args.jobs, len(games))), *flags]
    if extra:
        argv.append('--batch-args=' + shlex.join(extra))
    if args.max_device is not None:
        argv += ['--max-device', str(args.max_device)]
    started = time.perf_counter()
    returncode = check(argv)
    seconds = round(time.perf_counter() - started, 1)
    check_json = work / 'release-check.json'
    batch_json = work / 'Games' / 'datas' / 'Retro-Recomp-batch.json'
    records = chunk_records(games, read_json(check_json) if check_json.is_file() else None,
                            read_json(batch_json) if batch_json.is_file() else None,
                            chunk=name, seconds=seconds, level=args.level, returncode=returncode)
    log = work / 'batch.log'
    text = log.read_text(encoding='utf-8', errors='replace') if log.is_file() else ''
    for record in records:
        write_json(journal_path(root, console, record['id']), record)
        lines = chunk_log_lines(text, record['title'])
        verdict = f"{record['verdict'].upper()} {record['title']} ({console}, {record['chunk']})"
        problems = ''.join(f'\n  {problem}' for problem in record['problems'])
        journal_path(root, console, record['id']).with_suffix('.log').write_text(
            verdict + problems + '\n\n' + lines, encoding='utf-8', newline='\n')
    return records


def next_chunk_number(root: Path, console: str) -> int:
    folder = root / 'out' / console
    numbers = [int(path.name.split('-')[1]) for path in folder.glob('chunk-*') if re.fullmatch(r'chunk-\d+', path.name)]
    return max(numbers, default=0) + 1


def command_run(args) -> int:
    root = campaign_root(args.version, args.root)
    selection = read_json(root / 'selection.json')
    if not 1 <= args.jobs <= 8:
        print('FAIL --jobs must be 1-8', file=sys.stderr)
        return 2
    pending = pending_games(selection, root, consoles=args.consoles, subset=args.subset,
                            retry_failed=args.retry_failed, redo=args.redo)
    if args.smallest:
        pending = smallest_games(pending, args.smallest)
    if args.limit:
        taken = 0
        for console in list(pending):
            pending[console] = pending[console][:max(0, args.limit - taken)]
            taken += len(pending[console])
            if not pending[console]:
                del pending[console]
    total = sum(len(games) for games in pending.values())
    print(f'{total} game(s) without a verdict, {args.jobs} conversion(s) at a time, level {args.level}')
    size = args.chunk or max(args.jobs, 2 * args.jobs)
    failed = 0
    try:
        for console, games in pending.items():
            for start in range(0, len(games), size):
                part = games[start:start + size]
                number = next_chunk_number(root, console)
                print(f'[{console}] chunk {number}: ' + ', '.join(game['title'] for game in part), flush=True)
                for record in run_chunk(args.converter.resolve(), console, part, root, number, args):
                    failed += record['verdict'] == 'fail'
                    print(f"  {record['verdict'].upper():7} {record['title']}"
                          + (': ' + '; '.join(record['problems']) if record['problems'] else ''), flush=True)
    except KeyboardInterrupt:
        print('interrupted: games without a journal file run again at the next `run`', file=sys.stderr)
        return 130
    print(f'{total - failed} of {total} without a failed verdict; `report` aggregates them')
    return 1 if failed else 0


# ------------------------------------------------------------------ report

def _max(values):
    values = [value for value in values if value is not None]
    return max(values) if values else None


def fallback_figures(report: dict) -> dict:
    """Interpreter fallback per CPU and per device, apart, from a schema-2 report. None means not measured."""
    from retrorecomp.report_schema import fallback_summary
    sections = []
    for kind, items in (('cpu', report['cpus']), ('device', report['devices'])):
        for item in items:
            scenarios = item.get('scenarios') or []
            sections.append({'kind': kind, 'id': item.get('id'), 'arch': item.get('arch'), 'unit': item.get('unit'),
                             'original_unit': item.get('original_unit'),
                             'fallback_present': item.get('fallback_present'),
                             'max_interpreted': _max(s.get('interpreted') for s in scenarios),
                             'max_cycles': _max((s.get('cycles') or {}).get('interpreted') for s in scenarios)})
    return {'sections': sections, 'summary': fallback_summary(report)}


def measures_of(report: dict) -> dict:
    """The five measures as the report states them, each with its own claim; nothing derived."""
    validation = report['validation']
    keep = {'native_code': ('fallback_present', 'zero_fallback_on_tested_scenarios', 'scenarios_checked', 'claim'),
            'cpu_fidelity': ('passed', 'reference', 'independent_cpu_oracle', 'claim'),
            'hardware_fidelity': ('validated', 'claim'),
            'gameplay': ('validated', 'scenarios_run', 'owner_acceptance', 'claim'),
            'latency': ('measured', 'ms', 'claim')}
    return {name: {key: validation[name].get(key) for key in keys} for name, keys in keep.items()}


def fallback_text(figures: dict | None) -> str:
    if not figures:
        return 'unknown'
    parts = []
    for section in figures['sections']:
        label = section['id'] if section['kind'] == 'device' else f"{section['id']} {section['arch']}"
        present = section['fallback_present']
        if present is None:
            parts.append(f'{label}: not measured')
        elif not present:
            parts.append(f'{label}: none')
        else:
            count = section['max_interpreted']
            cycles = section['max_cycles']
            detail = f'{count:,} {section["unit"]}' if count else ''
            if cycles:
                detail += (' / ' if detail else '') + f'{cycles:,} cycles'
            parts.append(f'{label}: YES ({detail or "counted"})')
    return '; '.join(parts) or 'unknown'


def summarize_game(record: dict, load=None) -> dict:
    """A journal record plus what its conversion report says (read through report_schema)."""
    from retrorecomp.report_schema import read_report, ReportShapeError
    summary = {key: record.get(key) for key in ('id', 'console', 'title', 'kind', 'category', 'expect', 'verdict',
                                                'status', 'level', 'problems', 'message', 'chunk', 'chunk_seconds',
                                                'chunk_games', 'gates')}
    summary.update(seconds=None, fallback=None, measures=None, scan_level=None, report_error=None,
                   upgraded=record.get('upgraded'))
    path = record.get('report')
    if not path:
        return summary
    try:
        document = (load or read_report)(path)
    except (OSError, ValueError, ReportShapeError) as error:
        summary['report_error'] = str(error)
        return summary
    summary.update(seconds=document['build'].get('wall_seconds'), scan_level=document['scan'].get('level'),
                   fallback=fallback_figures(document), measures=measures_of(document))
    return summary


def aggregate(selection: dict, root: Path, load=None) -> dict:
    result = {'schema': SCHEMA, 'version': selection.get('version'), 'generated_utc': now_utc(),
              'seed': selection.get('seed'), 'count': selection.get('count'), 'consoles': {},
              'totals': {'selected': 0, 'pass': 0, 'refused': 0, 'fail': 0, 'pending': 0}}
    for console, block in selection['consoles'].items():
        rows, totals = [], {'selected': 0, 'pass': 0, 'refused': 0, 'fail': 0, 'pending': 0}
        for game in block['games']:
            path = journal_path(root, console, game['id'])
            totals['selected'] += 1
            if not path.is_file():
                rows.append({'id': game['id'], 'console': console, 'title': game['title'], 'kind': game['kind'],
                             'category': game.get('category'), 'verdict': 'pending', 'problems': [],
                             'hermes': game.get('hermes')})
                totals['pending'] += 1
                continue
            row = summarize_game(read_json(path), load)
            row['reason'] = game.get('reason')
            row['hermes'] = game.get('hermes')
            rows.append(row)
            totals[row['verdict']] = totals.get(row['verdict'], 0) + 1
        result['consoles'][console] = {'totals': totals, 'games': rows,
                                       'unmatched_risk': block.get('unmatched_risk', []),
                                       'rejected': block.get('rejected', [])}
        for key, value in totals.items():
            result['totals'][key] += value
    for name, folder in (('upgrades', 'upgrade'), ('states', 'states')):
        summary_path = root / folder / 'summary.json'
        if summary_path.is_file():
            result[name] = read_json(summary_path)
    return result


def render_markdown(summary: dict) -> str:
    totals = summary['totals']
    lines = [f"# Campaign {summary['version']}", '',
             f"Seed {summary['seed']}, {summary['count']} games per console. "
             f"{totals['selected']} selected: {totals['pass']} pass, {totals['refused']} refused as expected, "
             f"{totals['fail']} fail, {totals['pending']} without a verdict.", '',
             'Verdicts come from tools/release_check.py on the report of each conversion. A pass says the '
             'conversion, native/reference agreement, interpreter fallback limit and replay gates held; it is not a '
             'claim of hardware fidelity, full gameplay or physical latency (see the five measures per game). '
             'Interpreter fallback is listed per CPU and device, never folded into a verdict.', '']
    for console, block in summary['consoles'].items():
        lines += [f'## {console}', '',
                  '| Game | Kind | Verdict | Level | Seconds | Interpreter fallback |', '|---|---|---|---|---|---|']
        for row in block['games']:
            kind = row['kind'] + (f" ({row['category']})" if row.get('category') else '')
            seconds = row.get('seconds')
            lines.append(f"| {row['title']} | {kind} | {row['verdict'].upper()} | {row.get('scan_level') or row.get('level') or ''} "
                         f"| {f'{seconds:,.0f}' if seconds else ''} | {fallback_text(row.get('fallback')) if row['verdict'] != 'pending' else ''} |")
        lines.append('')
        for row in block['games']:
            if row['verdict'] == 'pending':
                continue
            lines.append(f"**{row['title']}** ({row['verdict']}, {row.get('status')})")
            for problem in row.get('problems') or []:
                lines.append(f'- problem: {problem}')
            if row['verdict'] == 'refused' and row.get('message'):
                lines.append(f"- the converter refused the cartridge: {row['message']}")
            if row.get('report_error'):
                lines.append(f"- report unreadable: {row['report_error']}")
            if row.get('chunk_seconds') and not row.get('seconds'):
                lines.append(f"- chunk of {row['chunk_games']} game(s): {row['chunk_seconds']:,.0f} s in all")
            measures = row.get('measures')
            if measures:
                n, c, h, g, l = (measures[name] for name in MEASURES)
                lines += [f"- native code: fallback present {n['fallback_present']}, scenarios {n['scenarios_checked']}; {n['claim']}",
                          f"- CPU fidelity: passed {c['passed']}, independent oracle {c['independent_cpu_oracle']}; {c['claim']}",
                          f"- hardware fidelity: validated {h['validated']}; {h['claim']}",
                          f"- gameplay: full game validated {g['validated']}, routes {g['scenarios_run']}; {g['claim']}",
                          f"- physical latency: measured {l['measured']}, ms {l['ms']}; {l['claim']}"]
            lines.append('')
        for item in block.get('unmatched_risk', []):
            lines.append(f"- risk case not selected: {item['title']} ({item['why']})")
        for item in block.get('rejected', []):
            lines.append(f"- candidate rejected at selection: {item['title']} ({item['reason']})")
        lines.append('')
    if summary.get('upgrades'):
        lines += ['## Upgrades of existing exports', '',
                  '| Game | Console | From | Outcome | Verdict |', '|---|---|---|---|---|']
        for row in summary['upgrades']['games']:
            lines.append(f"| {row['title']} | {row['console']} | {row.get('from_version')} | {row['outcome']} | {row['verdict'].upper()} |")
        lines.append('')
    if summary.get('states'):
        lines += ['## F8/F9 states from an earlier build', '', summary['states'].get('limits', ''), '',
                  '| Game | Check | Outcome |', '|---|---|---|']
        for row in summary['states']['results']:
            lines.append(f"| {row['title']} | {row['check']} | {row['outcome']} |")
        lines.append('')
    return '\n'.join(lines) + '\n'


def command_report(args) -> int:
    root = campaign_root(args.version, args.root)
    selection = read_json(root / 'selection.json')
    summary = aggregate(selection, root)
    write_json(root / 'summary.json', summary)
    (root / 'summary.md').write_text(render_markdown(summary), encoding='utf-8', newline='\n')
    totals = summary['totals']
    print(f"{totals['selected']} selected: {totals['pass']} pass, {totals['refused']} refused as expected, "
          f"{totals['fail']} fail, {totals['pending']} pending -> {root / 'summary.md'}")
    return 1 if totals['fail'] else 0


# ------------------------------------------------------------------ upgrade of existing exports

def find_exports(folders: list[Path]) -> list[dict]:
    """Every export with a conversion report under the given folders (an export root or a console folder)."""
    from retrorecomp.report_schema import read_report, ReportShapeError
    found, seen = [], set()
    for base in folders:
        reports = [*base.glob('datas/reports/*/conversion-report.json'),
                   *base.glob('*/datas/reports/*/conversion-report.json')]
        for path in sorted(reports):
            if norm_path(path) in seen:
                continue
            seen.add(norm_path(path))
            folder = path.parents[3]
            try:
                raw = read_json(path)
                document = read_report(raw)
            except (OSError, ValueError, ReportShapeError) as error:
                found.append({'report': str(path), 'error': str(error)})
                continue
            executable = document['build'].get('executable')
            receipt = raw.get('export_receipt') if isinstance(raw, dict) else None
            found.append({'report': str(path), 'folder': str(folder), 'console': document['system']['id'],
                          'title': Path(executable or path.parent.name).stem, 'executable': executable,
                          'sha256': (document['rom'] or {}).get('sha256'), 'from_version': document['version'],
                          'source_rom': document['build'].get('source_rom'), 'level': document['scan'].get('level'),
                          'receipt_schema': receipt.get('schema', 1) if isinstance(receipt, dict) else None})
    return found


def classify_upgrade(row: dict | None, report: dict | None) -> str:
    """What the converter did with an existing export, from its batch row and the new report."""
    if row is None:
        return 'no result'
    status = row.get('status')
    if status == 'current':
        return 'already current'
    if status != 'success':
        return 'failed'
    if row.get('upgraded') or (report or {}).get('upgrade'):
        return 'quick upgrade'
    return 'full reconversion'


def upgrade_group(converter: Path, console: str, level: str, items: list[dict], root: Path, args,
                  runner=subprocess.run) -> dict:
    """Copy the exports into the campaign, run the converter's own batch path without --force, read the outcome."""
    from retrorecomp.systems import get_profile
    work = root / 'upgrade' / 'work' / level
    export = work / get_profile(console).export_folder
    for item in items:
        before = root / 'upgrade' / 'before' / console
        before.mkdir(parents=True, exist_ok=True)
        source = Path(item['folder']) / item['executable']
        shutil.copy2(source, before / item['executable'])
        export.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, export / item['executable'])
        shutil.copytree(Path(item['report']).parent, export / 'datas' / 'reports' / Path(item['report']).parent.name,
                        dirs_exist_ok=True)
    command = release_check.command_for(converter, root / 'out' / 'app')
    flags, extra = console_options(console, args)
    command += ['batch', *[item['source_rom'] for item in items], '--system', console, '--scan-level', level,
                '--jobs', str(min(args.jobs, len(items))), '--no-online-cover', '--output', str(work), *extra]
    work.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with (work / f'batch-{console}.log').open('w', encoding='utf-8') as log:
        completed = runner(command, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    record_path = work / 'datas' / 'Retro-Recomp-batch.json'
    return {'returncode': completed.returncode, 'seconds': round(time.perf_counter() - started, 1),
            'record': read_json(record_path) if record_path.is_file() else None, 'work': str(work),
            'export': str(export)}


def upgrade_records(items: list[dict], group: dict, args) -> list[dict]:
    rows = (group['record'] or {}).get('games', [])
    by_path = {norm_path(row.get('rom')): row for row in rows if row.get('rom')}
    records = []
    for index, item in enumerate(items):
        row = by_path.get(norm_path(item['source_rom']))
        if row is None and len(rows) == len(items):
            row = rows[index]
        document = report = None
        if row and row.get('report') and Path(row['report']).is_file():
            from retrorecomp.report_schema import read_report, ReportShapeError
            try:
                report = read_json(row['report'])
                document = read_report(report)
            except (OSError, ValueError, ReportShapeError):
                report = document = None
        outcome = classify_upgrade(row, document)
        checked = None
        if document:
            level = document['scan'].get('level') or item['level']
            checked = release_check.check_report(report, item['console'], level, args.max_fallback)
        problems = (checked['problems'] if checked else []) + ([] if outcome != 'failed' else
                                                               [f"conversion {row.get('status')}: {row.get('message')}"])
        if outcome == 'no result':
            problems.append('no batch result (the converter did not finish)')
        note = None
        if outcome == 'full reconversion':
            note = ('the export carries no schema-3 receipt, so the converter cannot upgrade it'
                    if item.get('receipt_schema') != 3 else
                    'the game part of the request changed, or the quick check failed and the game was converted in full')
        records.append({'schema': SCHEMA, 'id': f"{item['console']}-{slug(item['title'])}-{(item.get('sha256') or '')[:12]}",
                        'console': item['console'], 'title': item['title'], 'from_version': item['from_version'],
                        'outcome': outcome, 'note': note, 'verdict': 'pass' if not problems and outcome != 'failed' else 'fail',
                        'problems': problems, 'level': (document or {}).get('scan', {}).get('level'),
                        'old_receipt_schema': item.get('receipt_schema'),
                        'upgrade': (document or {}).get('upgrade'),
                        'old_executable': str(Path(group['work']).parents[1] / 'before' / item['console'] / item['executable']),
                        'new_executable': (row or {}).get('executable'), 'report': (row or {}).get('report'),
                        'source_rom': item['source_rom'], 'rom_sha256': item.get('sha256'),
                        'group_seconds': group['seconds'], 'finished_utc': now_utc()})
    return records


def command_upgrade(args) -> int:
    root = campaign_root(args.version, args.root)
    current = args.version or default_version()
    exports = find_exports([Path(folder) for folder in args.exports])
    usable, skipped = [], []
    for item in exports:
        if 'error' in item:
            skipped.append({**item, 'why': 'unreadable report'})
        elif args.from_version and item['from_version'] != args.from_version:
            skipped.append({**item, 'why': f"version {item['from_version']}"})
        elif item['from_version'] == current:
            skipped.append({**item, 'why': 'already built by this version'})
        elif not item['source_rom'] or not Path(item['source_rom']).is_file():
            skipped.append({**item, 'why': 'the source ROM named by the report is not reachable'})
        elif not (Path(item['folder']) / (item['executable'] or '')).is_file():
            skipped.append({**item, 'why': 'the executable is missing'})
        elif args.consoles and item['console'] not in args.consoles:
            skipped.append({**item, 'why': 'console not requested'})
        else:
            usable.append(item)
    if args.limit:
        usable = usable[:args.limit]
    groups = {}
    for item in usable:
        groups.setdefault((item['console'], item['level'] or 'standard'), []).append(item)
    records = []
    for (console, level), items in groups.items():
        print(f'[{console}] upgrading {len(items)} export(s), level {level}: ' + ', '.join(i['title'] for i in items), flush=True)
        group = upgrade_group(args.converter.resolve(), console, level, items, root, args)
        for record in upgrade_records(items, group, args):
            write_json(root / 'journal-upgrade' / console / f"{record['id']}.json", record)
            records.append(record)
            print(f"  {record['verdict'].upper():5} {record['title']}: {record['outcome']}"
                  + (f" ({record['note']})" if record['note'] else ''), flush=True)
    summary = {'schema': SCHEMA, 'generated_utc': now_utc(), 'current_version': current, 'games': records,
               'skipped': [{'title': s.get('title'), 'report': s['report'], 'why': s['why']} for s in skipped],
               'outcomes': {name: sum(r['outcome'] == name for r in records)
                            for name in ('quick upgrade', 'full reconversion', 'already current', 'failed', 'no result')}}
    write_json(root / 'upgrade' / 'summary.json', summary)
    print(f"{len(records)} processed, {len(skipped)} skipped: " + ', '.join(f'{n} {k}' for k, n in summary['outcomes'].items() if n))
    return 1 if any(r['verdict'] == 'fail' for r in records) else 0


# ------------------------------------------------------------------ F8/F9 states of an earlier build

STATES_LIMITS = ('The only 1.5.6 states this tool can produce itself are the ones an old export writes headless '
                 '(--save-state on a scripted route): `pairs` resumes them in the upgraded export through '
                 'tools/state16_cross.py --one-way and reports resumed, diverged or refused. Slots saved by hand in '
                 'the player are checked with `files`, which only proves what it runs: that the new export loads '
                 'the file, and, when the pre-upgrade export is known, that both continue identically. A refusal is '
                 'a clean outcome (STANDARDS rule 6) unless a release note promises that the state migrates.')
STATE_CONSOLES = ('md', 'snes')


def classify_cross(returncode: int, stdout: str, stderr: str) -> dict:
    """state16_cross.py's exit, JSON and error text as one outcome."""
    result = None
    try:
        result = json.loads(stdout[stdout.index('{'):]) if '{' in stdout else None
    except ValueError:
        result = None
    if returncode == 0 and result:
        return {'outcome': 'resumed identically', 'detail': result}
    if result and result.get('states_resume_across_builds'):
        parts = [name for name in ('same_trace_in_both_builds', 'same_final_guest_state')
                 if result.get(name) is False]
        return {'outcome': 'resumed; the two builds differ (' + ', '.join(parts) + ')', 'detail': result}
    if 'diverges' in stderr:
        return {'outcome': 'resumed but diverged', 'detail': stderr[-600:]}
    if 'restored: exit' in stderr:
        return {'outcome': 'refused by the new export', 'detail': stderr[-600:]}
    return {'outcome': f'error (exit {returncode})', 'detail': stderr[-600:]}


def run_cross(old: Path, new: Path, warmup: int, replay: int, runner=subprocess.run) -> dict:
    try:
        completed = runner([sys.executable, '-B', str(TOOLS / 'state16_cross.py'), str(old), str(new), '--one-way',
                            '--warmup', str(warmup), '--replay', str(replay)],
                           capture_output=True, text=True, timeout=3600)
    except subprocess.TimeoutExpired:
        return {'outcome': 'error (timeout after one hour)', 'detail': ''}
    return classify_cross(completed.returncode, completed.stdout, completed.stderr)


def load_state(exe: Path, state: Path, frames: int, scratch: Path, name: str, runner=None):
    """Run an export for a few frames from a state file (tools/console16_state_selftest.run).

    Returns (True, (report, rows)) when the export loaded it, (False, error text) when it refused or crashed.
    """
    import console16_state_selftest as selftest
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        return True, (runner or selftest.run)(exe, scratch, name, frames, '--load-state', state)
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        return False, str(error)


def compare_continuations(old, new) -> dict:
    """Two (report, rows) from the same state file: the new build must continue like the old one."""
    import console16_state_selftest as selftest
    (old_report, old_rows), (new_report, new_rows) = old, new
    columns = [key for key in old_rows[0] if key not in ('native', 'interpreted')] if old_rows else []
    mismatch = next((n for n, (a, b) in enumerate(zip(old_rows, new_rows)) if any(a[k] != b.get(k) for k in columns)), None)
    differing = [k for k in selftest.GUEST_FIELDS if k in old_report and old_report.get(k) != new_report.get(k)]
    if mismatch is None and not differing and len(old_rows) == len(new_rows):
        return {'outcome': 'both builds continue identically', 'frames': len(new_rows)}
    return {'outcome': 'continuations differ', 'first_mismatch': mismatch, 'fields': differing}


def command_states(args) -> int:
    root = campaign_root(args.version, args.root)
    journal = [read_json(path) for path in sorted((root / 'journal-upgrade').glob('*/*.json'))]
    journal = [r for r in journal if r['console'] in STATE_CONSOLES and r.get('new_executable')
               and r['outcome'] in ('quick upgrade', 'full reconversion', 'already current')]
    results = []
    if args.mode == 'pairs':
        for record in journal:
            old = Path(record['old_executable'])
            if not old.is_file():
                results.append({'title': record['title'], 'check': 'pairs', 'outcome': 'pre-upgrade export not kept'})
                continue
            outcome = run_cross(old, Path(record['new_executable']), args.warmup, args.replay)
            results.append({'title': record['title'], 'console': record['console'], 'check': 'pairs',
                            'from_version': record['from_version'], **outcome})
            print(f"{record['title']}: {outcome['outcome']}", flush=True)
    else:
        scratch = root / 'states' / 'scratch'
        files = sorted(Path(args.states_dir).rglob('*.state')) + sorted(Path(args.states_dir).rglob('*.rrstate'))
        for state in files:
            owner = next((r for r in journal if (r.get('rom_sha256') or 'x')[:12] in str(state)), None)
            new = Path(args.exe) if args.exe else (Path(owner['new_executable']) if owner else None)
            if new is None:
                results.append({'title': state.name, 'check': 'files',
                                'outcome': 'no export known for this state (name carries no ROM hash; give --exe)'})
                continue
            title = owner['title'] if owner else new.stem
            loaded, payload = load_state(new, state, args.frames, scratch / 'new', state.stem)
            if not loaded:
                results.append({'title': title, 'check': 'files', 'state': state.name,
                                'outcome': 'refused by the new export', 'detail': payload[-400:]})
            else:
                outcome = {'outcome': 'loaded by the new export (no continuity claim without the old export)'}
                old = Path(owner['old_executable']) if owner else None
                if old and old.is_file():
                    was, earlier = load_state(old, state, args.frames, scratch / 'old', state.stem)
                    outcome = (compare_continuations(earlier, payload) if was
                               else {'outcome': 'loaded by the new export; the old export refused it too'})
                results.append({'title': title, 'check': 'files', 'state': state.name, **outcome})
            print(f"{title} ({state.name}): {results[-1]['outcome']}", flush=True)
    summary = {'schema': SCHEMA, 'generated_utc': now_utc(), 'limits': STATES_LIMITS, 'results': results}
    previous = root / 'states' / 'summary.json'
    if previous.is_file():
        summary['results'] = [r for r in read_json(previous)['results'] if r['check'] != args.mode] + results
    write_json(previous, summary)
    print(f"{len(results)} state check(s) -> {previous}")
    return 0


# ------------------------------------------------------------------ command line

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    # Accepted before or after the subcommand.
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument('--version', default=argparse.SUPPRESS,
                        help='Release being checked (names .build/campaign-VERSION; default: the source version)')
    shared.add_argument('--root', type=Path, default=argparse.SUPPRESS,
                        help='Campaign folder instead of .build/campaign-VERSION')
    parser.add_argument('--version', default=None, help='Release being checked (names .build/campaign-VERSION; '
                        'default: the source version)')
    parser.add_argument('--root', type=Path, default=None, help='Campaign folder instead of .build/campaign-VERSION')
    commands = parser.add_subparsers(dest='command', required=True, parser_class=argparse.ArgumentParser)
    _add = commands.add_parser
    commands.add_parser = lambda name, **kw: _add(name, parents=[shared], **kw)

    select = commands.add_parser('select', help='Choose the games of each console')
    select.add_argument('--roms-root', type=Path, help=f'Folder holding one ROM folder per console (or ${ROOT_ENV})')
    select.add_argument('--folder', action='append', default=[], metavar='CONSOLE=NAME',
                        help='ROM folder name of a console when it differs from the default')
    select.add_argument('--consoles', nargs='+', choices=CONSOLES)
    select.add_argument('--count', type=int, default=10, help='Games per console (8 to 12 suggested)')
    select.add_argument('--seed', type=int, default=DEFAULT_SEED, help='Seed of the random half (same seed, same games)')
    select.add_argument('--risk-share', type=float, default=0.5, help='Part of the sample taken from the risk cases')
    select.add_argument('--random', type=int, default=None,
                        help='Every risk case found plus exactly this many random games per console (ignores --count)')
    select.add_argument('--risk-cases', type=Path, default=RISK_CASES)
    select.add_argument('--hermes', type=int, default=2, help='Games per console marked for the Linux sample')
    select.add_argument('--no-verify', action='store_true', help='Do not ask the converter to read each chosen file')
    select.set_defaults(handler=command_select)

    run = commands.add_parser('run', help='Convert the selected games and write one verdict per game')
    run.add_argument('converter', type=Path, help='Retro-Recomp.exe or RetroRecomp.py')
    run.add_argument('--consoles', nargs='+', choices=CONSOLES)
    run.add_argument('--subset', choices=('all', 'hermes'), default='all')
    run.add_argument('--jobs', type=int, default=4, help='Conversions at once (1-8)')
    run.add_argument('--chunk', type=int, default=0, help='Games per release_check call (default 2 x jobs)')
    run.add_argument('--limit', type=int, default=0, help='Stop after this many games in all')
    run.add_argument('--smallest', type=int, default=0, help='Only the N smallest games without a verdict (smoke test)')
    run.add_argument('--level', choices=LEVELS, default='standard')
    run.add_argument('--max-fallback', type=int, default=0)
    run.add_argument('--max-device', type=int, default=None)
    run.add_argument('--retry-failed', action='store_true', help='Run again the games whose verdict is fail')
    run.add_argument('--redo', action='store_true', help='Run again every selected game')
    run.add_argument('--ng-bios', type=Path, help='Neo Geo BIOS archive')
    run.add_argument('--x68-ipl', type=Path)
    run.add_argument('--x68-cgrom', type=Path)
    run.set_defaults(handler=command_run)

    report = commands.add_parser('report', help='Aggregate the verdicts into summary.md and summary.json')
    report.set_defaults(handler=command_report)

    upgrade = commands.add_parser('upgrade', help='Run the converter upgrade path on copies of existing exports')
    upgrade.add_argument('converter', type=Path)
    upgrade.add_argument('exports', nargs='+', type=Path, help='Export roots or console folders (only read and copied)')
    upgrade.add_argument('--from-version', help='Only the exports built by this version (for example 1.5.6)')
    upgrade.add_argument('--consoles', nargs='+', choices=CONSOLES)
    upgrade.add_argument('--limit', type=int, default=0)
    upgrade.add_argument('--jobs', type=int, default=2)
    upgrade.add_argument('--max-fallback', type=int, default=0)
    upgrade.add_argument('--ng-bios', type=Path)
    upgrade.add_argument('--x68-ipl', type=Path)
    upgrade.add_argument('--x68-cgrom', type=Path)
    upgrade.set_defaults(handler=command_upgrade)

    states = commands.add_parser('states', help='Resume F8/F9 states of an earlier build in the upgraded exports')
    states.add_argument('mode', choices=('pairs', 'files'))
    states.add_argument('--states-dir', type=Path, help='files: folder of .state / .rrstate slots saved by the old build')
    states.add_argument('--exe', type=Path, help='files: the export that must load them, if the name carries no ROM hash')
    states.add_argument('--warmup', type=int, default=1200)
    states.add_argument('--replay', type=int, default=300)
    states.add_argument('--frames', type=int, default=300)
    states.set_defaults(handler=command_states)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == 'states' and args.mode == 'files' and not args.states_dir:
        print('FAIL states files needs --states-dir', file=sys.stderr)
        return 2
    return args.handler(args)


if __name__ == '__main__':
    sys.exit(main())
