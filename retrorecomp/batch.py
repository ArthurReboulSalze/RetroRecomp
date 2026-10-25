"""Bounded mixed-console ROM queue and atomic per-console exports."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
from threading import Event, Lock
import time

from .core import slug, executable_name, ConversionError, StopRequested, reset_stop
from .library import atomic_json
from .build_cleanup import release_build
from . import __version__
from .publishing import publish_executable
from .systems import profile_for_path, get_profile, UnsupportedConsoleError, ConsoleMismatchError


@dataclass
class BatchItem:
    path: Path
    title: str
    system: str = ""
    sha256: str = ""
    size: int = 0
    error: str = ""
    cover: Path | None = None
    video_hint: str = ""
    standard_override: str | None = None
    selected_system: str = ""
    unknown: bool = False
    skipped: bool = False

    @property
    def key(self) -> str:
        return f"{slug(self.title)}-{self.sha256[:12]}"


def identify(path: Path, selected_system: str | None = None) -> BatchItem:
    path = path.resolve()
    title = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", path.stem).strip() or path.stem
    try:
        system = profile_for_path(path, selected_system)
        rom = system.read_rom(path)
        if system.id in ('ng', 'cps1'):
            title = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", rom.title.split(' / ',1)[0]).strip() or path.stem
        byte_size = rom.size if hasattr(rom, 'size') else len(rom.data)
        return BatchItem(path, title, system.id, rom.sha256, byte_size,
                         video_hint=system.default_video_mode(path),
                         selected_system=selected_system or "")
    except ConsoleMismatchError as exc:
        return BatchItem(path, title, system=exc.detected_system, error=str(exc),
                         selected_system=selected_system or "", skipped=True)
    except UnsupportedConsoleError as exc:
        return BatchItem(path, title, error=str(exc), unknown=True,
                         selected_system=selected_system or "")
    except (ConversionError, OSError, ValueError) as exc:
        return BatchItem(path, title, error=str(exc), selected_system=selected_system or "")


def _edition_hint(item: BatchItem) -> str:
    """Use source labels as labels, never as proof of PAL/NTSC timing."""
    return ', '.join(re.findall(r'[\(\[]([^\)\]]+)[\)\]]', item.path.stem)).strip()


def _version_letter(number: int) -> str:
    label = ''
    while number >= 0:
        label = chr(65 + number % 26) + label
        number = number // 26 - 1
    return label


def _variant_titles(items: list[BatchItem]) -> dict[int, str]:
    """Name distinct ROM editions from source labels, then stable A/B labels."""
    groups = defaultdict(list)
    for index, item in enumerate(items):
        if item.system and item.sha256 and not item.error:
            groups[(item.system, item.title.casefold())].append((index, item))
    result = {}
    for group in groups.values():
        if len({item.sha256 for _, item in group}) < 2:
            continue
        editions = {}
        for index, item in group:
            editions.setdefault(item.sha256, (index, item))
        hints = defaultdict(list)
        for sha, (index, item) in editions.items():
            hints[_edition_hint(item).casefold()].append((sha, index, item))
        for members in hints.values():
            for number, (_, index, item) in enumerate(sorted(members, key=lambda entry: entry[0])):
                hint = _edition_hint(item)
                suffix = (hint + ', ' if hint else '') + 'version ' + _version_letter(number) \
                    if len(members) > 1 or not hint else hint
                result[index] = f'{item.title} ({suffix})'
        # Every alias of one SHA uses the same destination title.
        for index, item in group:
            result[index] = result[editions[item.sha256][0]]
    return result


def _embedded_export_identity(path: Path) -> str | None:
    """Recover our exact cartridge marker, including from compacted EXEs."""
    explicit = re.compile(re.escape(b'[Retro-Recomp]\x00') + rb'([0-9a-f]{64})\x00')
    legacy = re.compile(rb'(?<![0-9a-f])([0-9a-f]{64})\x00')
    branded = False
    try:
        with path.open('rb') as stream:
            header = stream.read(4)
            if not header.startswith((b'MZ', b'\x7fELF')):
                return None
            def scan(pattern, track_brand=False):
                nonlocal branded
                found, carry = set(), b''
                stream.seek(0)
                while chunk := stream.read(1024 * 1024):
                    data = carry + chunk
                    if track_brand:
                        branded |= b'[Retro-Recomp]' in data
                    # Enough overlap for a full marker plus its lookbehind.
                    # Ignore matches wholly inside it: the first overlap byte
                    # is not the file start and must not invent a legacy SHA.
                    for match in pattern.finditer(data):
                        if match.end() > len(carry):
                            found.add(match[1])
                            if len(found) == 2:
                                return found
                    carry = data[-96:]
                return found
            marked = scan(explicit, track_brand=True)
            if marked:
                return next(iter(marked)).decode('ascii') if len(marked) == 1 else None
            # Legacy SHA scanning is costlier. Modern explicit markers do not
            # need it, even when the marker is at the very end of a large game.
            identities = scan(legacy) if branded else set()
    except OSError:
        return None
    if not branded:
        return None
    # Older generated runtimes used separate brand and null-terminated SHA
    # strings. Preserve their existing fail-closed, unique-identity rule.
    return next(iter(identities)).decode('ascii') if len(identities) == 1 else None


def _foreign_binary(path: Path) -> bool:
    """Never retire another target's game from a shared export folder."""
    try:
        with path.open('rb') as stream:
            header = stream.read(20)
    except OSError:
        return False
    if header.startswith(b'MZ'):
        return os.name != 'nt'
    if header.startswith(b'\x7fELF'):
        if os.name == 'nt':
            return True
        from .platforms import target_id
        machine = 183 if target_id().endswith('arm64') else 62
        return len(header) < 20 or header[4:6] != b'\x02\x01' or int.from_bytes(header[18:20], 'little') != machine
    return False


def _export_records(output: Path, *, identities: set[str] | None = None, cancel=None):
    """Recover exact ROM ownership from reports or branded generated EXEs."""
    reported = {}
    for path in (output / 'datas/reports').glob('*/conversion-report.json'):
        if cancel and cancel.is_set():
            return
        try:
            report = json.loads(path.read_text(encoding='utf-8'))
            name, identity = report['executable'], report['rom']['sha256']
            if Path(name).name != name or (os.name == 'nt' and not name.lower().endswith('.exe')):
                continue
            from .platforms import target_id
            if report.get('target', target_id()) != target_id():
                continue
            if not isinstance(identity, str) or not re.fullmatch('[0-9a-f]{64}', identity):
                continue
            record = reported.setdefault(name.casefold(), (name, set()))
            record[1].add(identity)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    for name, claims in reported.values():
        if cancel and cancel.is_set():
            return
        # Reports are cheap metadata. Opening every unrelated generated EXE
        # can make a one-game conversion wait on hundreds of filesystem checks.
        # Keep *all* claims for a selected filename to detect stale/conflicting
        # revision reports, but inspect only identities needed by this queue.
        if identities is not None and claims.isdisjoint(identities):
            continue
        if _foreign_binary(output / name):
            continue
        # A deleted/replaced export can leave older revision reports using the
        # same filename. The current binary's branded identity wins over those
        # conflicting records; ambiguous/unbranded files remain protected.
        embedded = _embedded_export_identity(output / name) if len(claims) > 1 else None
        for identity in ({embedded} if embedded else claims):
            if identities is None or identity in identities or len(claims) > 1 and not embedded:
                yield name, identity
    # Reports can be deleted while games and the converter library remain.
    # Every generated runtime embeds its full null-terminated ROM SHA256.
    # Require our runtime marker and a unique identity; preserve unknown files.
    for path in (output.glob('*.exe') if os.name == 'nt' else output.iterdir()):
        if cancel and cancel.is_set():
            return
        if not path.is_file():
            continue
        if path.name.casefold() in reported:
            continue
        if _foreign_binary(path):
            continue
        identity = _embedded_export_identity(path)
        if identity and (identities is None or identity in identities):
            yield path.name, identity


def reported_owner(path: Path, identity: str) -> bool:
    """The queue's ownership rule for one file: reports beside it claim it for
    this exact cartridge only. Old exports (before receipts and embedded
    markers) are recognized this way, as the batch already overwrites them."""
    claims = {found for name, found in _export_records(path.parent, identities={identity})
              if name.casefold() == path.name.casefold()}
    return claims == {identity}


def export_target(item: BatchItem, output: Path) -> Path:
    """Readable filenames; only identical titles need a numeric suffix.

    Keep existing files of unknown ownership and other cartridge revisions.
    Reports and generated EXEs retain the full ROM identity, so reconversion
    reuses the same name even after deleting the reports.
    """
    owners = {}
    own_names = []
    for name, identity in _export_records(output):
        owners.setdefault(name.casefold(), set()).add(identity)
        if identity == item.sha256:
            own_names.append(name)
    base = executable_name(item.title)
    for name in sorted(own_names, key=lambda name: (name.casefold() != base.casefold(), name.casefold())):
        # Upgrade legacy hash/underscore filenames to the current readable form.
        if name == base or re.fullmatch(re.escape((base[:-4] if os.name == 'nt' else base)) + r' \(\d+\)' + (r'\.exe' if os.name == 'nt' else ''), name):
            if owners.get(name.casefold()) == {item.sha256}:
                return output / name
    existing = {path.name.casefold() for path in output.iterdir()}
    candidate = base
    index = 2
    while candidate.casefold() in existing and owners.get(candidate.casefold()) != {item.sha256}:
        candidate = executable_name(item.title, suffix=f' ({index})')
        index += 1
    return output / candidate


def system_output(output: Path, system_id: str) -> Path:
    """Route every batch, including a custom destination, by console."""
    return output.resolve() / get_profile(system_id).export_folder


class _OutputNames:
    """Snapshot existing ownership before workers start writing reports."""

    def __init__(self, output: Path, *, identities: set[str] | None = None, cancel=None):
        self.output = output
        self.owners: dict[str, set[str]] = {}
        self.original: list[tuple[Path, str]] = []
        self.sources: dict[tuple[str, str], set[str]] = {}
        for path in (output / 'datas/reports').glob('*/conversion-report.json'):
            if cancel and cancel.is_set():
                break
            try:
                report = json.loads(path.read_text(encoding='utf-8'))
                name = report['executable']
                source = report['rom']['name']
                identity = report['rom']['sha256']
                if Path(name).name == name and isinstance(source, str) and isinstance(identity, str):
                    self.sources.setdefault((name.casefold(), identity), set()).add(Path(source).stem.casefold())
            except (OSError, ValueError, KeyError, TypeError):
                continue
        for name, identity in _export_records(output, identities=identities, cancel=cancel):
            self.owners.setdefault(name.casefold(), set()).add(identity)
            self.original.append((output / name, identity))
        self.existing = {path.name.casefold() for path in output.iterdir()}
        self.reserved: dict[str, str] = {}

    def matching_export(self, item: BatchItem) -> Path | None:
        return next((path for path, identity in self.original
                     if identity == item.sha256 and path.is_file()), None)

    def same_source_name(self, item: BatchItem, previous: Path) -> bool:
        original = self.sources.get((previous.name.casefold(), item.sha256))
        return (item.path.stem.casefold() in original if original else
                previous.stem.casefold() == item.title.casefold() or
                previous.stem.casefold().startswith(item.title.casefold() + ' (') or
                previous.stem.casefold() == item.key.casefold())

    def reserve(self, item: BatchItem, export_title: str | None = None) -> tuple[Path, list[Path]]:
        base = executable_name(export_title or item.title)
        own_names = [path.name for path, identity in self.original if identity == item.sha256]
        target = None
        for name in sorted(own_names, key=lambda value: (value.casefold() != base.casefold(), value.casefold())):
            preserved_edition = (export_title is None and
                re.fullmatch(re.escape((base[:-4] if os.name == 'nt' else base)) + r' \([^)]*\)' + (r'\.exe' if os.name == 'nt' else ''), name))
            if (name == base or preserved_edition or
                    re.fullmatch(re.escape((base[:-4] if os.name == 'nt' else base)) + r' \(\d+\)' + (r'\.exe' if os.name == 'nt' else ''), name)) and \
                    self.owners.get(name.casefold()) == {item.sha256} and \
                    name.casefold() not in self.reserved:
                target = self.output / name
                break
        if target is None:
            candidate = base
            suffix = 2
            while (candidate.casefold() in self.reserved or
                   (candidate.casefold() in self.existing and
                    self.owners.get(candidate.casefold()) != {item.sha256})):
                candidate = executable_name(export_title or item.title, suffix=f' ({suffix})')
                suffix += 1
            target = self.output / candidate
        self.reserved[target.name.casefold()] = item.sha256
        previous = [path for path, identity in self.original
                    if identity == item.sha256 and self.owners[path.name.casefold()] == {item.sha256}
                    and path != target]
        return target, previous

    def finish(self, target: Path, identity: str, succeeded: bool) -> None:
        self.reserved.pop(target.name.casefold(), None)
        if succeeded:
            self.existing.add(target.name.casefold())
            self.owners[target.name.casefold()] = {identity}


def _convert_one(index: int, item: BatchItem, count: int, system, game_output: Path,
                 reports: Path, target: Path, previous_executables: list[Path],
                 emit, options: dict) -> dict:
    result = {"rom": str(item.path), "title": item.title, "system": item.system,
              "sha256": item.sha256}
    try:
        if item.cover is None:
            from .compiled_games import Game
            from .game_details import Cards
            item.cover = Cards().override(Game('',item.system,item.sha256,item.title))
        settings = dict(options)
        force = settings.pop('force', False)
        # Forcing from the queue rediscovers; Reconvert may still upgrade.
        rediscover = settings.pop('rediscover', force)
        # What the shared base gave this ROM before the batch (online.prepare_batch):
        # it may choose the quick plan below and is never part of the request.
        shared = (settings.pop('shared_paths', None) or {}).get(f'{system.id}:{item.sha256}')
        if system.id != 'x68':
            for key in ('x68_ipl', 'x68_cgrom', 'x68_ram'): settings.pop(key, None)
        if system.id != 'ng':
            settings.pop('ng_bios', None)
            settings.pop('ng_qualification_routes', None)
            settings.pop('ng_parallel_games', None)
        if system.id not in ('md', 'snes'):
            settings.pop('md_advanced_scan', None)
        if system.id != 'nes':
            settings.pop('nes_advanced_scan', None)
        # Scan level, pass limit and frame budget resolve per console: a
        # command-line level, else the console's saved entry, else the former
        # switches. The former switch keys keep their meaning (and the request
        # signature of standard conversions) for the consoles that had them.
        from .scan_levels import plan_for
        plan = plan_for(system.id, settings.pop('console_scan', None),
                        passes=settings.get('passes', 3), frames=settings.get('frames'),
                        level=settings.pop('scan_level', None),
                        md_advanced_scan=bool(settings.get('md_advanced_scan')),
                        nes_advanced_scan=bool(settings.get('nes_advanced_scan')))
        settings['passes'], settings['frames'] = plan.passes, plan.frames
        if system.id in ('md', 'snes'):
            settings['md_advanced_scan'] = plan.level in ('extended', 'thorough')
        if system.id == 'nes':
            settings['nes_advanced_scan'] = plan.level in ('extended', 'thorough')
        if plan.level != 'standard':
            settings['scan_level'] = plan.level
        if system.id != 'gb':
            settings.pop('gb_deep_validation', None)
            settings.pop('gb_parallel_games', None)
        if item.standard_override is not None:
            settings['standard_override'] = item.standard_override
        if system.id in ('sms', 'gg'):
            settings['publish_result'] = False
        from .freshness import request_parts, current, digest, feedback, upgradable, upgrade_record
        parts = request_parts(item, settings)
        signature = parts['request']
        from .paths import save_game_language
        save_game_language(game_output, settings.get('language', 'en'))
        report_path = reports / 'conversion-report.json'
        if not force and target.is_file() and current(item, target, report_path, signature, emit):
            from .linux_desktop import publish_launcher
            publish_launcher(target, report_path, json.loads(report_path.read_text(encoding='utf-8')))
            emit(f'{item.title}: up to date; same version/settings and no new fallback hints.')
            result.update(status='current', executable=str(target), report=str(report_path))
            return result
        # Only the player shell changed and no new paths were found: rebuild
        # from the paths already learned, checked on the quick routes only.
        inherited = None if rediscover or not target.is_file() else upgradable(
            item, target, report_path, parts, emit)
        run_settings = settings
        legacy = inherited.get('legacy_release') if inherited else None
        if legacy:
            emit(f'{item.title}: exported by Retro-Recomp {legacy}; its game code is listed as equivalent, so the '
                 'executable is rebuilt with the current tools and rechecked on the quick routes '
                 '(a full conversion follows if that does not pass).')
        elif inherited:
            emit(f'{item.title}: only menus/presentation changed and no new paths were found; '
                 'upgrading the executable without rediscovery (quick check).')
        shared_used = None
        if shared and not inherited:
            from .knowledge import imported_observations, imported_record
            from .scan_levels import LEVELS
            # Only while the imported banks hold them (not set aside after a failure).
            if imported_record(system.id, item.sha256) or imported_observations(system.id, item.sha256):
                level = shared.get('level') if shared.get('level') in LEVELS else None
                shared_used = {'level': level, 'records': int(shared.get('records') or 0),
                               'quick': bool(level and not rediscover
                                             and LEVELS.index(level) >= LEVELS.index(plan.level))}
                emit(f'{item.title}: shared paths, level {level}: quick check instead of discovery.'
                     if shared_used['quick'] else
                     f'{item.title}: shared paths{f", level {level}" if level else ""}: '
                     f'{plan.level} discovery starting from them.')
        # A game the bundled snapshot already knows: its paths come from a qualified
        # Standard conversion, so a Standard scan would find nothing more. Rebuild
        # from them with the quick check rather than rediscover (Extended and
        # Thorough still search further).
        known_used = None
        if not inherited and not (shared_used and shared_used['quick']) and not rediscover and plan.level == 'standard':
            from .knowledge_exchange import _bundled, _entries
            if _entries(system.id, _bundled(system.id, item.sha256)):
                known_used = {'level': 'standard', 'quick': True}
                emit(f'{item.title}: already known to the bundled knowledge: quick check instead of discovery.')
        if inherited or (shared_used and shared_used['quick']) or known_used:
            quick = plan_for(system.id, None, passes=settings['passes'], frames=settings['frames'], level='quick')
            run_settings = {**settings, 'passes': quick.passes, 'frames': quick.frames, 'scan_level': 'quick'}
            for key in ('md_advanced_scan', 'nes_advanced_scan'):
                if key in run_settings:
                    run_settings[key] = False
        def convert_with(arguments):
            return system.convert(item.path, title=item.title, output=reports, cover=item.cover,
                emit=lambda message: emit(f"[{index+1}/{count} - {item.title}] {message}"), **arguments)
        try:
            executable = convert_with(run_settings)
        except Exception as exc:
            if not (legacy or known_used) or isinstance(exc, StopRequested):
                raise
            # The earlier export is still in place: nothing was published. Never leave it
            # half-upgraded; convert the game in full, with every route, instead.
            reason = str(exc).strip().splitlines()[0][:200] if str(exc).strip() else type(exc).__name__
            emit(f'{item.title}: the rebuilt export of Retro-Recomp {legacy} did not pass its checks ({reason}); '
                 'converting the game in full instead.' if legacy else
                 f'{item.title}: the quick check from the bundled knowledge did not pass ({reason}); '
                 'discovering the game in full instead.')
            inherited, known_used, run_settings = None, None, settings
            executable = convert_with(run_settings)
        temporary = reports / "published-executable.tmp"
        report_path = reports / "conversion-report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        from .languages import LANGUAGES
        report.update(ui_languages=list(LANGUAGES),language_switch_key='F7',
                      language_scope='Retro-Recomp host menus; cartridge text unchanged')
        if inherited:
            report['upgrade'] = upgrade_record(inherited)
        if shared_used:
            report['shared_paths'] = shared_used
        if known_used:
            report['bundled_paths'] = known_used
        shutil.copy2(Path(report.get('build_executable', executable)), temporary)
        report.setdefault('rom', {})['sha256'] = item.sha256
        report.update(executable=target.name, published_directory=str(game_output),
                      source_rom=str(item.path.resolve()))
        atomic_json(report_path, report)
        # Finish the report before replacing a working executable.
        try:
            pending = publish_executable(temporary, target, compact=True)
        finally:
            temporary.unlink(missing_ok=True)
        if pending:
            emit(f"Nouvelle version prête ; remplacement à la fermeture du jeu : {target}")
        else:
            from .linux_desktop import publish_launcher
            publish_launcher(target, report_path, report)
            for previous_executable in previous_executables:
                try:
                    previous_executable.unlink(missing_ok=True)
                    from .linux_desktop import retire_launcher
                    retire_launcher(previous_executable,item.sha256)
                except OSError as exc:
                    emit(f"Ancien exécutable conservé : {previous_executable.name} : {exc}")
        if report.get('version') == __version__ and feedback(report).get('fingerprint'):
            if pending:
                from .publishing import job_path
                published_hash = json.loads(job_path(target).read_text(encoding='utf-8'))['sha256']
            else:
                published_hash = digest(target)
            report['export_receipt'] = {'schema': 3, 'request': signature, 'game': parts['game'],
                                       'host': parts['host'], 'sha256': published_hash}
            atomic_json(report_path, report)
        try:
            if executable != target and executable != Path(report.get('build_executable', '')):
                executable.unlink()
        except OSError:
            pass
        # Published: nothing reads the game's build project again.
        release_build(item, report, emit)
        measured = [check.get("interpreter_percent") for check in report["final_checks"]]
        result.update(status="success", executable=str(target), report=str(report_path),
            conversion_stage=report.get('status'), upgraded=bool(inherited),
            main_interpreted_opcodes=max((c.get('interpreted_opcodes', 0) for c in report['final_checks']), default=0),
            audio_cpu=report.get('audio_cpu'),
            audio_interpreted_opcodes=max((c.get('audio_interpreted_opcodes', 0) for c in report['final_checks']), default=0),
            pending_install=pending,
            video_standard=report.get('video_model', {}).get('standard', item.video_hint),
            interpreter_percent=max((p for p in measured if p is not None), default=None),
            interpreter_cycles=max((c.get("interpreter_cycles", 0) for c in report["final_checks"]), default=0),
            reference_vdp_trace_match=report.get("reference_vdp_trace_match"))
        if shared_used:
            result['shared_paths'] = shared_used
    except StopRequested:
        # Killed by Stop: the earlier export, if any, is untouched.
        result.update(status="stopped", message="Conversion arrêtée ; l’export précédent est conservé.")
        emit(f"{item.title} : {result['message']}")
    except Exception as exc:
        result.update(status="error", message=str(exc))
        emit(f"{item.title} : {exc}")
    return result


def _convert_in_budget(parallel_games, *args):
    # Context-local caps cannot leak between simultaneous workers.
    from .platforms import compilation_budget
    from .knowledge import discard_imported, imported_observations, imported_record, imported_set_aside
    item, emit = args[1], args[8]
    with compilation_budget(parallel_games):
        result = _convert_one(*args)
        # Shared hints may come from another converter and be wrong: a failed
        # conversion that had some (hints or observations) is retried once
        # without them. If it then succeeds, they caused the failure and leave
        # the imported banks.
        if result['status'] != 'error' or not item.system or not (
                imported_record(item.system, item.sha256) or imported_observations(item.system, item.sha256)):
            return result
        emit(f'{item.title}: failed with imported discoveries; converting again without them.')
        with imported_set_aside(item.system, item.sha256):
            retry = _convert_one(*args)
        if retry['status'] in ('success', 'current'):
            discard_imported(item.system, item.sha256, result.get('message', ''))
            emit(f'{item.title}: imported discoveries for this cartridge set aside; they caused the failure.')
            retry['imported_hints_rejected'] = True
        return retry


def convert_batch(items: list[BatchItem], output: Path, *, cancel: Event | None = None,
                  on_event=lambda kind, index, value: None, emit=print, jobs: int = 1,
                  overwrite: bool = True,
                  **options) -> dict:
    if not isinstance(jobs, int) or not 1 <= jobs <= 8:
        raise ValueError('Concurrent conversions must be between 1 and 8.')
    options = {**options, 'gb_parallel_games': jobs, 'ng_parallel_games': jobs}
    started = time.perf_counter()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    results: list[dict | None] = [None] * len(items)
    seen: dict[tuple[str, str], str] = {}
    active: set[tuple[str, str]] = set()
    names: dict[str, _OutputNames] = {}
    variant_titles = _variant_titles(items)
    requested_identities = defaultdict(set)
    for item in items:
        if item.system and item.sha256 and not item.error:
            requested_identities[item.system].add(item.sha256)
    emit_lock = Lock()
    original_emit = emit

    def emit(message):
        with emit_lock:
            original_emit(message)

    stopped = False
    queued = list(range(len(items)))
    reset_stop()
    with ThreadPoolExecutor(max_workers=jobs, thread_name_prefix='retro-recomp') as executor:
        pending = {}
        while queued or pending:
            while queued and len(pending) < jobs and not (cancel and cancel.is_set()):
                # A second copy of the same ROM waits for the first result: if
                # the first failed, the later copy is still allowed to retry.
                # It must not prevent unrelated ROMs from using vacant workers.
                position = next((p for p, i in enumerate(queued)
                    if (items[i].system, items[i].sha256) not in active), None)
                if position is None:
                    break
                index = queued.pop(position)
                item = items[index]
                identity = (item.system, item.sha256)
                result = {"rom": str(item.path), "title": item.title, "system": item.system,
                          "sha256": item.sha256}
                try:
                    if item.skipped or item.unknown:
                        result.update(status="skipped" if item.skipped else "unrecognized",
                                      message=item.error)
                        emit(f"{item.title} : {item.error}")
                    elif item.error:
                        raise ConversionError(item.error)
                    else:
                        system = get_profile(item.system)
                        if profile_for_path(item.path, item.selected_system or None).id != system.id:
                            raise ConversionError("La console de cette ROM a changé depuis son ajout au lot.")
                        if system.read_rom(item.path).sha256 != item.sha256:
                            raise ConversionError("La ROM a changé depuis son ajout au lot ; ajoute-la à nouveau.")
                        if identity in seen:
                            result.update(status="duplicate", duplicate_of=seen[identity],
                                message=f"Contenu ROM identique à « {seen[identity]} » malgré le nom différent.")
                            emit(f"{item.title} : {result['message']}")
                        else:
                            game_output = system_output(output, system.id)
                            game_output.mkdir(parents=True, exist_ok=True)
                            if system.id not in names:
                                emit(f'{system.name}: checking existing exports for the queued ROMs...')
                                names[system.id] = _OutputNames(game_output,
                                    identities=requested_identities[system.id], cancel=cancel)
                            if cancel and cancel.is_set():
                                # No compiler owns this row yet. Leave it
                                # pending rather than starting after Stop.
                                queued.insert(0, index)
                                break
                            previous_export = names[system.id].matching_export(item)
                            if previous_export and not names[system.id].same_source_name(item, previous_export):
                                result.update(status='duplicate', duplicate_of=previous_export.stem,
                                    message=f"Contenu ROM identique à « {previous_export.stem} » malgré le nom différent.")
                                emit(f"{item.title} : {result['message']}")
                            elif previous_export and not overwrite:
                                result.update(status='existing', executable=str(previous_export),
                                    message='Jeu déjà généré ; remplacement désactivé.')
                                seen[identity] = item.title
                                emit(f"{item.title} : {result['message']}")
                            else:
                                target, previous = names[system.id].reserve(item, variant_titles.get(index))
                                reports = game_output / "datas/reports" / item.key
                                on_event("start", index, item.title)
                                future = executor.submit(_convert_in_budget, jobs, index, item, len(items), system,
                                    game_output, reports, target, previous, emit, options)
                                pending[future] = (index, identity, target)
                                active.add(identity)
                                continue
                except Exception as exc:
                    result.update(status="error", message=str(exc))
                    emit(f"{item.title} : {exc}")
                on_event("start", index, item.title)
                results[index] = result
                on_event("result", index, result)
            if pending:
                finished, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in sorted(finished, key=lambda value: pending[value][0]):
                    index, identity, target = pending.pop(future)
                    active.remove(identity)
                    result = future.result()
                    succeeded = result['status'] in ('success', 'current')
                    names[identity[0]].finish(target, identity[1], succeeded)
                    if succeeded:
                        seen[identity] = items[index].title
                    results[index] = result
                    on_event("result", index, result)
            elif cancel and cancel.is_set():
                stopped = bool(queued)
                break
    completed = [result for result in results if result is not None]
    record = {"tool": "Retro-Recomp", "version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(), "output": str(output),
        "requested": len(items), "jobs": jobs, "cancelled": stopped,
        # Rows killed by Stop count as remaining: they were not converted.
        "pending": len(items)-len(completed) + sum(r["status"] == "stopped" for r in completed),
        "stopped": sum(r["status"] == "stopped" for r in completed),
        "succeeded": sum(r["status"] == "success" for r in completed),
        "failed": sum(r["status"] == "error" for r in completed),
        "unrecognized": sum(r["status"] == "unrecognized" for r in completed),
        "skipped": sum(r["status"] == "skipped" for r in completed),
        "duplicates": sum(r["status"] == "duplicate" for r in completed), "games": completed}
    record['existing'] = sum(r['status'] == 'existing' for r in completed)
    record['current'] = sum(r['status'] == 'current' for r in completed)
    record['pending_installations'] = sum(r.get('pending_install', False) for r in completed)
    record['elapsed_seconds'] = round(time.perf_counter() - started, 3)
    directory = output / "datas"
    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(directory / "Retro-Recomp-batch.json", record)
    return record
