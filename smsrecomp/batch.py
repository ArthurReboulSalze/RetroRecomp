"""Sequential mixed-console ROM queue and atomic per-console exports."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from threading import Event

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


def convert_batch(items: list[BatchItem], output: Path, *, cancel: Event | None = None,
                  on_event=lambda kind, index, value: None, emit=print, **options) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    results, seen = [], set()
    stopped = False
    for index, item in enumerate(items):
        if cancel is not None and cancel.is_set():
            stopped = True
            break
        on_event("start", index, item.title)
        result = {"rom": str(item.path), "title": item.title, "system": item.system,
                  "sha256": item.sha256}
        try:
            if item.skipped:
                result.update(status="skipped", message=item.error)
                emit(f"{item.title} : {item.error}")
                results.append(result)
                on_event("result", index, result)
                continue
            if item.unknown:
                result.update(status="unrecognized", message=item.error)
                emit(f"{item.title} : {item.error}")
                results.append(result)
                on_event("result", index, result)
                continue
            if item.error:
                raise ConversionError(item.error)
            system = get_profile(item.system)
            if profile_for_path(item.path, item.selected_system or None).id != system.id:
                raise ConversionError("La console de cette ROM a changé depuis son ajout au lot.")
            if system.read_rom(item.path).sha256 != item.sha256:
                raise ConversionError("La ROM a changé depuis son ajout au lot ; ajoute-la à nouveau.")
            if (system.id, item.sha256) in seen:
                result.update(status="duplicate", message="Même ROM déjà présente dans le lot.")
            else:
                game_output = system_output(output, system.id)
                game_output.mkdir(parents=True, exist_ok=True)
                reports = game_output / "datas/reports" / item.key
                target = export_target(item, game_output)
                owned_names = {}
                for previous_name, identity in _export_records(game_output):
                    owned_names.setdefault(game_output / previous_name, set()).add(identity)
                previous_executables = [path for path, identities in owned_names.items()
                    if identities == {item.sha256} and path != target]
                settings = dict(options)
                if system.id != 'gb':
                    settings.pop('gb_deep_validation', None)
                if item.standard_override is not None:
                    settings['standard_override'] = item.standard_override
                if system.id in ('sms', 'gg'):
                    # The batch owns final publication; the Sega compiler only
                    # needs to leave its validated build in the private cache.
                    settings['publish_result'] = False
                executable = system.convert(item.path, title=item.title, output=reports, cover=item.cover,
                    emit=lambda text: emit(f"[{index+1}/{len(items)} · {item.title}] {text}"), **settings)
                temporary = reports / "published-executable.tmp"
                report_path = reports / "conversion-report.json"
                report = json.loads(report_path.read_text(encoding="utf-8"))
                shutil.copy2(Path(report.get('build_executable', executable)), temporary)
                report.setdefault('rom', {})['sha256'] = item.sha256
                report.update(executable=target.name, published_directory=str(game_output))
                atomic_json(report_path, report)
                # Complete the conversion report before replacing a user's
                # working executable. Failure here leaves the previous game.
                try:
                    pending = publish_executable(temporary, target, compact=True)
                finally:
                    temporary.unlink(missing_ok=True)
                if pending:
                    emit(f"Nouvelle version prête ; remplacement à la fermeture du jeu : {target}")
                # Regeneration keeps one executable, without archiving an old
                # filename. Only retire a report-owned file once publication
                # has succeeded; unknown files and failed exports stay intact.
                if not pending:
                    for previous_executable in previous_executables:
                        try:
                            previous_executable.unlink(missing_ok=True)
                        except OSError as exc:
                            emit(f"Ancien exécutable conservé : {previous_executable.name} : {exc}")
                try:
                    if executable != target and executable != Path(report.get('build_executable', '')):
                        executable.unlink()
                except OSError:
                    pass  # Optional cleanup in datas cannot invalidate a published game.
                measured = [c.get("interpreter_percent") for c in report["final_checks"]]
                result.update(status="success", executable=str(target), report=str(report_path),
                    pending_install=pending,
                    video_standard=report.get('video_model', {}).get('standard', item.video_hint),
                    interpreter_percent=max((p for p in measured if p is not None), default=None),
                    interpreter_cycles=max((c.get("interpreter_cycles", 0) for c in report["final_checks"]), default=0),
                    reference_vdp_trace_match=report.get("reference_vdp_trace_match"))
                seen.add((system.id, item.sha256))
        except Exception as exc:
            result.update(status="error", message=str(exc))
            emit(f"{item.title} : {exc}")
        results.append(result)
        on_event("result", index, result)
    record = {"tool": "Retro-Recomp", "version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(), "output": str(output),
        "requested": len(items), "cancelled": stopped, "pending": len(items)-len(results),
        "succeeded": sum(r["status"] == "success" for r in results),
        "failed": sum(r["status"] == "error" for r in results),
        "unrecognized": sum(r["status"] == "unrecognized" for r in results),
        "skipped": sum(r["status"] == "skipped" for r in results),
        "duplicates": sum(r["status"] == "duplicate" for r in results), "games": results}
    record['pending_installations'] = sum(r.get('pending_install', False) for r in results)
    directory = output / "datas"
    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(directory / "Retro-Recomp-batch.json", record)
    return record
