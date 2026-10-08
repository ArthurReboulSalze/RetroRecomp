"""Bounded mixed-console ROM queue and atomic per-console exports."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from threading import Event, Lock

from .core import slug, executable_name, ConversionError
from .library import atomic_json
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
        return BatchItem(path, title, system.id, rom.sha256, len(rom.data),
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


def _export_records(output: Path):
    """Recover exact ROM ownership from reports or branded generated EXEs."""
    reported = set()
    for path in (output / 'datas/reports').glob('*/conversion-report.json'):
        try:
            report = json.loads(path.read_text(encoding='utf-8'))
            name, identity = report['executable'], report['rom']['sha256']
            if Path(name).name != name or not name.lower().endswith('.exe'):
                continue
            reported.add(name.casefold())
            yield name, identity
        except (OSError, ValueError, KeyError, TypeError):
            continue
    # Reports can be deleted while games and the converter library remain.
    # Every generated runtime embeds its full null-terminated ROM SHA256.
    # Require our runtime marker and a unique identity; preserve unknown files.
    for path in output.glob('*.exe'):
        if path.name.casefold() in reported:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if not data.startswith(b'MZ') or b'[Retro-Recomp]' not in data:
            continue
        identities = set(re.findall(rb'(?<![0-9a-f])[0-9a-f]{64}\x00', data))
        if len(identities) == 1:
            yield path.name, identities.pop()[:-1].decode('ascii')


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
        if name == base or re.fullmatch(re.escape(Path(base).stem) + r' \(\d+\)\.exe', name):
            if owners.get(name.casefold()) == {item.sha256}:
                return output / name
    existing = {path.name.casefold() for path in output.iterdir()}
    candidate = base
    index = 2
    while candidate.casefold() in existing and owners.get(candidate.casefold()) != {item.sha256}:
        candidate = f'{Path(base).stem} ({index}).exe'
        index += 1
    return output / candidate


def system_output(output: Path, system_id: str) -> Path:
    """Route every batch, including a custom destination, by console."""
    return output.resolve() / get_profile(system_id).export_folder


class _OutputNames:
    """Snapshot existing ownership before workers start writing reports."""

    def __init__(self, output: Path):
        self.output = output
        self.owners: dict[str, set[str]] = {}
        self.original: list[tuple[Path, str]] = []
        self.sources: dict[str, str] = {}
        for path in (output / 'datas/reports').glob('*/conversion-report.json'):
            try:
                report = json.loads(path.read_text(encoding='utf-8'))
                name = report['executable']
                source = report['rom']['name']
                if Path(name).name == name and isinstance(source, str):
                    self.sources[name.casefold()] = source
            except (OSError, ValueError, KeyError, TypeError):
                continue
        for name, identity in _export_records(output):
            self.owners.setdefault(name.casefold(), set()).add(identity)
            self.original.append((output / name, identity))
        self.existing = {path.name.casefold() for path in output.iterdir()}
        self.reserved: dict[str, str] = {}

    def matching_export(self, item: BatchItem) -> Path | None:
        return next((path for path, identity in self.original
                     if identity == item.sha256 and path.is_file()), None)

    def same_source_name(self, item: BatchItem, previous: Path) -> bool:
        original = self.sources.get(previous.name.casefold())
        return (Path(original).stem.casefold() == item.path.stem.casefold() if original else
                previous.stem.casefold() == item.title.casefold() or
                previous.stem.casefold().startswith(item.title.casefold() + ' (') or
                previous.stem.casefold() == item.key.casefold())

    def reserve(self, item: BatchItem, export_title: str | None = None) -> tuple[Path, list[Path]]:
        base = executable_name(export_title or item.title)
        own_names = [path.name for path, identity in self.original if identity == item.sha256]
        target = None
        for name in sorted(own_names, key=lambda value: (value.casefold() != base.casefold(), value.casefold())):
            preserved_edition = (export_title is None and
                re.fullmatch(re.escape(Path(base).stem) + r' \([^)]*\)\.exe', name))
            if (name == base or preserved_edition or
                    re.fullmatch(re.escape(Path(base).stem) + r' \(\d+\)\.exe', name)) and \
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
                candidate = f'{Path(base).stem} ({suffix}).exe'
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
        settings = dict(options)
        if system.id != 'md':
            settings.pop('md_advanced_scan', None)
        if system.id != 'gb':
            settings.pop('gb_deep_validation', None)
            settings.pop('gb_parallel_games', None)
        if item.standard_override is not None:
            settings['standard_override'] = item.standard_override
        if system.id in ('sms', 'gg'):
            settings['publish_result'] = False
        executable = system.convert(item.path, title=item.title, output=reports, cover=item.cover,
            emit=lambda message: emit(f"[{index+1}/{count} · {item.title}] {message}"), **settings)
        temporary = reports / "published-executable.tmp"
        report_path = reports / "conversion-report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        shutil.copy2(Path(report.get('build_executable', executable)), temporary)
        report.setdefault('rom', {})['sha256'] = item.sha256
        report.update(executable=target.name, published_directory=str(game_output))
        atomic_json(report_path, report)
        # Finish the report before replacing a working executable.
        try:
            pending = publish_executable(temporary, target, compact=True)
        finally:
            temporary.unlink(missing_ok=True)
        if pending:
            emit(f"Nouvelle version prête ; remplacement à la fermeture du jeu : {target}")
        else:
            for previous_executable in previous_executables:
                try:
                    previous_executable.unlink(missing_ok=True)
                except OSError as exc:
                    emit(f"Ancien exécutable conservé : {previous_executable.name} : {exc}")
        try:
            if executable != target and executable != Path(report.get('build_executable', '')):
                executable.unlink()
        except OSError:
            pass
        measured = [check.get("interpreter_percent") for check in report["final_checks"]]
        result.update(status="success", executable=str(target), report=str(report_path),
            conversion_stage=report.get('status'),
            main_interpreted_opcodes=max((c.get('interpreted_opcodes', 0) for c in report['final_checks']), default=0),
            audio_cpu=report.get('audio_cpu'),
            audio_interpreted_opcodes=max((c.get('audio_interpreted_opcodes', 0) for c in report['final_checks']), default=0),
            pending_install=pending,
            video_standard=report.get('video_model', {}).get('standard', item.video_hint),
            interpreter_percent=max((p for p in measured if p is not None), default=None),
            interpreter_cycles=max((c.get("interpreter_cycles", 0) for c in report["final_checks"]), default=0),
            reference_vdp_trace_match=report.get("reference_vdp_trace_match"))
    except Exception as exc:
        result.update(status="error", message=str(exc))
        emit(f"{item.title} : {exc}")
    return result


def convert_batch(items: list[BatchItem], output: Path, *, cancel: Event | None = None,
                  on_event=lambda kind, index, value: None, emit=print, jobs: int = 1,
                  overwrite: bool = True,
                  **options) -> dict:
    if not isinstance(jobs, int) or not 1 <= jobs <= 8:
        raise ValueError('Concurrent conversions must be between 1 and 8.')
    options = {**options, 'gb_parallel_games': jobs}
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    results: list[dict | None] = [None] * len(items)
    seen: dict[tuple[str, str], str] = {}
    active: set[tuple[str, str]] = set()
    names: dict[str, _OutputNames] = {}
    variant_titles = _variant_titles(items)
    emit_lock = Lock()
    original_emit = emit

    def emit(message):
        with emit_lock:
            original_emit(message)

    stopped = False
    next_index = 0
    with ThreadPoolExecutor(max_workers=jobs, thread_name_prefix='retro-recomp') as executor:
        pending = {}
        while next_index < len(items) or pending:
            while next_index < len(items) and len(pending) < jobs and not (cancel and cancel.is_set()):
                index, item = next_index, items[next_index]
                identity = (item.system, item.sha256)
                # A second copy of the same ROM waits for the first result: if
                # the first failed, the later copy is still allowed to retry.
                if identity in active:
                    break
                on_event("start", index, item.title)
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
                                names[system.id] = _OutputNames(game_output)
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
                                future = executor.submit(_convert_one, index, item, len(items), system,
                                    game_output, reports, target, previous, emit, options)
                                pending[future] = (index, identity, target)
                                active.add(identity)
                                next_index += 1
                                continue
                except Exception as exc:
                    result.update(status="error", message=str(exc))
                    emit(f"{item.title} : {exc}")
                results[index] = result
                on_event("result", index, result)
                next_index += 1
            if pending:
                finished, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in sorted(finished, key=lambda value: pending[value][0]):
                    index, identity, target = pending.pop(future)
                    active.remove(identity)
                    result = future.result()
                    succeeded = result['status'] == 'success'
                    names[identity[0]].finish(target, identity[1], succeeded)
                    if succeeded:
                        seen[identity] = items[index].title
                    results[index] = result
                    on_event("result", index, result)
            elif cancel and cancel.is_set():
                stopped = next_index < len(items)
                break
    completed = [result for result in results if result is not None]
    record = {"tool": "Retro-Recomp", "version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(), "output": str(output),
        "requested": len(items), "jobs": jobs, "cancelled": stopped,
        "pending": len(items)-len(completed),
        "succeeded": sum(r["status"] == "success" for r in completed),
        "failed": sum(r["status"] == "error" for r in completed),
        "unrecognized": sum(r["status"] == "unrecognized" for r in completed),
        "skipped": sum(r["status"] == "skipped" for r in completed),
        "duplicates": sum(r["status"] == "duplicate" for r in completed), "games": completed}
    record['existing'] = sum(r['status'] == 'existing' for r in completed)
    record['pending_installations'] = sum(r.get('pending_install', False) for r in completed)
    directory = output / "datas"
    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(directory / "Retro-Recomp-batch.json", record)
    return record
