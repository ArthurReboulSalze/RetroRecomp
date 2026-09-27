"""Sequential ROM queue, isolated reports and atomic flat executable exports."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from threading import Event

from .core import convert, read_rom, slug, executable_name, ConversionError
from .library import atomic_json
from . import __version__
from .publishing import publish_executable


@dataclass
class BatchItem:
    path: Path
    title: str
    sha256: str = ""
    size: int = 0
    error: str = ""
    cover: Path | None = None

    @property
    def key(self) -> str:
        return f"{slug(self.title)}-{self.sha256[:12]}"


def identify(path: Path) -> BatchItem:
    path = path.resolve()
    title = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", path.stem).strip() or path.stem
    try:
        rom = read_rom(path)
        return BatchItem(path, title, rom.sha256, len(rom.data))
    except (ConversionError, OSError) as exc:
        return BatchItem(path, title, error=str(exc))


def _export_records(output: Path):
    """Read only report-owned executable names, scoped to the exact ROM."""
    for path in (output / 'datas/reports').glob('*/conversion-report.json'):
        try:
            report = json.loads(path.read_text(encoding='utf-8'))
            name, identity = report['executable'], report['rom']['sha256']
            if Path(name).name != name or not name.lower().endswith('.exe'):
                continue
            yield name, identity
        except (OSError, ValueError, KeyError, TypeError):
            continue


def export_target(item: BatchItem, output: Path) -> Path:
    """Readable filenames; only identical titles need a numeric suffix.

    Keep existing files of unknown ownership and other cartridge revisions.
    Reports retain the full ROM identity, so reconversion reuses the same name.
    """
    owners = {}
    own_names = []
    for name, identity in _export_records(output):
        owners.setdefault(name.casefold(), set()).add(identity)
        if identity == item.sha256:
            own_names.append(name)
    base = executable_name(item.title)
    for name in own_names:
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
        result = {"rom": str(item.path), "title": item.title, "sha256": item.sha256}
        try:
            if item.error:
                raise ConversionError(item.error)
            if read_rom(item.path).sha256 != item.sha256:
                raise ConversionError("La ROM a changé depuis son ajout au lot ; ajoute-la à nouveau.")
            if item.sha256 in seen:
                result.update(status="duplicate", message="Même ROM déjà présente dans le lot.")
            else:
                reports = output / "datas/reports" / item.key
                target = export_target(item, output)
                owned_names = {}
                for previous_name, identity in _export_records(output):
                    owned_names.setdefault(output / previous_name, set()).add(identity)
                previous_executables = [path for path, identities in owned_names.items()
                    if identities == {item.sha256} and path != target]
                executable = convert(item.path, title=item.title, output=reports, cover=item.cover,
                    emit=lambda text: emit(f"[{index+1}/{len(items)} · {item.title}] {text}"), **options)
                temporary = reports / "published-executable.tmp"
                report_path = reports / "conversion-report.json"
                report = json.loads(report_path.read_text(encoding="utf-8"))
                shutil.copy2(Path(report.get('build_executable', executable)), temporary)
                report.setdefault('rom', {})['sha256'] = item.sha256
                report.update(executable=target.name, published_directory=str(output))
                atomic_json(report_path, report)
                # Complete the conversion report before replacing a user's
                # working executable. Failure here leaves the previous game.
                pending = publish_executable(temporary, target)
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
                    if executable != target:
                        executable.unlink()
                except OSError:
                    pass  # Optional cleanup in datas cannot invalidate a published game.
                result.update(status="success", executable=str(target), report=str(report_path),
                    pending_install=pending,
                    interpreter_percent=max((c.get("interpreter_percent") or 0) for c in report["final_checks"]),
                    reference_vdp_trace_match=report["reference_vdp_trace_match"])
                seen.add(item.sha256)
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
        "duplicates": sum(r["status"] == "duplicate" for r in results), "games": results}
    record['pending_installations'] = sum(r.get('pending_install', False) for r in results)
    directory = output / "datas"
    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(directory / "Retro-Recomp-batch.json", record)
    return record
