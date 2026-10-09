"""Per-ROM learning, separate from generated files and game preferences.

The converter's headless probes append observations to a SHA256 directory;
game executables do not learn during gameplay. The converter
rechecks every ROM byte signature, then regenerates code with the current
compiler. No generated machine code is cached here. RAM windows are only data
for conversion; native execution requires exact live-byte guards.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import tomllib
import unicodedata
from .paths import data_directory

SCHEMA = 1
LINE = re.compile(r"^([0-9a-fA-F]{1,4})\s+([0-9a-fA-F]{1,2})\s+([0-9a-fA-F]{1,2})\s+([0-9a-fA-F]{1,2})\s+([0-9a-fA-F]{1,8})$")
PATTERN_LIMIT = 4096
PATTERN_FILE = "native.patterns"


def read_code_patterns(path: Path, *, limit: int | None = PATTERN_LIMIT) -> set[bytes]:
    result = set()
    try:
        with path.open(encoding="ascii", errors="replace") as file:
            for line in file:
                text = line.strip()
                if re.fullmatch(r"[0-9a-fA-F]{8}", text):
                    result.add(bytes.fromhex(text))
                    if limit is not None and len(result) >= limit:
                        break
    except FileNotFoundError:
        pass
    return result


def write_code_patterns(path: Path, patterns: set[bytes]) -> None:
    path.write_text("".join(raw.hex().upper() + "\n" for raw in sorted(patterns)), encoding="ascii")


def library_root(system_id: str = "sms") -> Path:
    from .systems import get_profile
    get_profile(system_id)
    custom = os.environ.get("RETRO_RECOMP_LIBRARY_DIR") or os.environ.get("SMSRECOMP_LIBRARY_DIR")
    base = Path(custom).expanduser().resolve() if custom else data_directory() / "library"
    # Preserve the existing Master System library; future backends get an
    # explicit namespace rather than sharing the same ROM-hash directory.
    return base if system_id == "sms" else base / system_id


def read_observations(path: Path) -> set[tuple[int, int, int, int, int]]:
    result = set()
    try:
        with path.open(encoding="ascii", errors="replace") as file:
            for line in file:
                match = LINE.fullmatch(line.strip())
                if match:
                    result.add(tuple(int(field, 16) for field in match.groups()))
    except FileNotFoundError:
        pass
    return result


def observation_line(entry: tuple) -> str:
    return f"{entry[0]:04X} {entry[1]:02X} {entry[2]:02X} {entry[3]:02X} {entry[4]:08X}"


def classify(rom, entry: tuple) -> str:
    """Match the live bus's 256-byte FNV signature, including bank mirroring.

    Windows touching RAM cannot be checked against ROM. Keep them as known
    limitations, never use their checksum as permission to compile ROM bytes.
    """
    address, *banks, expected = entry
    if address + 255 >= 0xC000:
        return "ram"
    h = 2166136261
    for addr in range(address, address + 256):
        offset = addr if addr < 0x400 else banks[addr >> 14] * 0x4000 + (addr & 0x3FFF)
        h = ((h ^ rom.data[offset % len(rom.data)]) * 16777619) & 0xFFFFFFFF
    return "rom" if h == expected else "rejected"


def write_manifest(path: Path, entries: set) -> None:
    path.write_text("".join(observation_line(entry) + "\n" for entry in sorted(entries)), encoding="ascii")


@contextmanager
def entry_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "entry.lock").open("a+b") as file:
        # CRT and Win32 both permit a range beyond EOF. Never initialize a
        # byte before locking: a native writer may already hold that range.
        file.seek(0)
        if os.name == "nt":
            import msvcrt
            until = time.monotonic() + 10
            while True:
                try:
                    msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= until:
                        raise
                    time.sleep(.02)
            try:
                yield
            finally:
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(file, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(file, fcntl.LOCK_UN)


def atomic_json(path: Path, value: dict) -> None:
    # A unique sibling temp also avoids collisions with a second converter.
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(value, file, indent=2, ensure_ascii=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class GameMemory:
    def __init__(self, rom, root: Path | None = None):
        self.rom = rom
        base = root or library_root()
        existing = sorted(p for p in base.glob(f"*-{rom.sha256}") if p.is_dir())
        old_directory = base / rom.sha256
        title = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", rom.path.stem).strip()
        label = re.sub(r"[^A-Za-z0-9]+", "_", unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()).strip("_")[:60] or "Game"
        self.directory = existing[0] if existing else (old_directory if old_directory.is_dir() else base / f"{label}-{rom.sha256}")
        self.journal = self.directory / "observations.log"
        self.record = self.directory / "compilation.json"
        self.code_journal = self.directory / PATTERN_FILE
        from .knowledge import record_for
        from .core import ENGINE_REV
        system = getattr(rom, 'system_id', 'sms')
        self.bundled = (record_for(system, rom, ENGINE_REV)
                        if root is None or root == library_root(system) else {})
        old_patterns = self.directory / "native-patterns.txt"
        if old_patterns.is_file():
            with entry_lock(self.directory):
                if old_patterns.exists():
                    if not self.code_journal.exists():
                        os.replace(old_patterns, self.code_journal)
                    else:
                        # Preserve the complete union even if older concurrent
                        # writers exceeded the current compiler's 4096 limit.
                        self._append_patterns(read_code_patterns(old_patterns, limit=None), limit=None)
                        old_patterns.unlink()
        if root is None and not (os.environ.get("RETRO_RECOMP_LIBRARY_DIR") or os.environ.get("SMSRECOMP_LIBRARY_DIR")):
            legacy_base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData/Local")
            legacy = Path(legacy_base) / "SMSRecomp/library" / rom.sha256
            if legacy.exists() and legacy.resolve() != self.directory.resolve():
                self.import_manifest(legacy / "observations.log")
                self.import_code_patterns(legacy / "native-patterns.txt")
                if not self.record.exists():
                    try:
                        old = json.loads((legacy / "compilation.json").read_text(encoding="utf-8"))
                        if old.get("schema") == SCHEMA and old.get("rom", {}).get("sha256") == rom.sha256:
                            with entry_lock(self.directory):
                                if not self.record.exists():
                                    atomic_json(self.record, old)
                    except (OSError, ValueError, AttributeError):
                        pass

    def summary(self) -> dict:
        entries = read_observations(self.journal) | {tuple(e) for e in self.bundled.get('rom_entries', [])}
        counts = {kind: 0 for kind in ("rom", "ram", "rejected")}
        for entry in entries:
            counts[classify(self.rom, entry)] += 1
        metadata = self.metadata()
        return {"sha256": self.rom.sha256, "directory": str(self.directory),
                "observations": len(entries), "rom_entries": counts["rom"],
                "ram_entries": counts["ram"], "rejected_entries": counts["rejected"],
                "generations": metadata.get("total_generations", len(metadata.get("generations", []))),
                "native_pattern_windows": len(self.code_patterns()),
                "bundled_rom_entries": len(self.bundled.get('rom_entries', [])),
                "known": bool(entries or metadata or self.code_patterns())}

    def metadata(self) -> dict:
        try:
            result = json.loads(self.record.read_text(encoding="utf-8"))
            if result.get("schema") == SCHEMA and result.get("rom", {}).get("sha256") == self.rom.sha256:
                return result
        except (OSError, ValueError, AttributeError):
            pass
        return {}

    def import_entries(self, entries: set) -> dict:
        verified = {entry for entry in entries if classify(self.rom, entry) == "rom"}
        ram = {entry for entry in entries if classify(self.rom, entry) == "ram"}
        with entry_lock(self.directory):
            existing = read_observations(self.journal)
            additions = (verified | ram) - existing
            if additions:
                with self.journal.open("a", encoding="ascii", newline="\n") as file:
                    file.write("".join(observation_line(e) + "\n" for e in sorted(additions)))
                    file.flush()
                    os.fsync(file.fileno())
        return {"added": len(additions), "verified": len(verified), "ram": len(ram),
                "rejected": len(entries - verified - ram)}

    def import_manifest(self, path: Path) -> dict:
        return self.import_entries(read_observations(path))

    def seeds(self) -> set:
        entries = read_observations(self.journal) | {tuple(e) for e in self.bundled.get('rom_entries', [])}
        return {entry for entry in entries if classify(self.rom, entry) == "rom"}

    def code_patterns(self) -> set[bytes]:
        local = read_code_patterns(self.code_journal)
        shared = {self.rom.data[offset:offset+4] for (offset,) in self.bundled.get('pattern_refs', [])}
        return local | set(sorted(shared - local)[:max(0, PATTERN_LIMIT - len(local))])

    def import_code_patterns(self, path: Path) -> int:
        incoming = read_code_patterns(path)
        with entry_lock(self.directory):
            return self._append_patterns(incoming)

    def _append_patterns(self, incoming: set[bytes], *, limit: int | None = PATTERN_LIMIT) -> int:
        """Caller holds entry_lock, also during migration from older games."""
        existing = read_code_patterns(self.code_journal, limit=limit)
        additions = sorted(incoming - existing)
        if limit is not None:
            additions = additions[:max(0, limit-len(existing))]
        if additions:
            with self.code_journal.open("a", encoding="ascii", newline="\n") as file:
                file.write("".join(raw.hex().upper() + "\n" for raw in additions))
                file.flush()
                os.fsync(file.fileno())
        return len(additions)

    def recipe(self, engine_revision: str) -> str | None:
        metadata = self.metadata()
        recipe = metadata.get("recipe", {})
        if not isinstance(recipe, dict):
            return None
        text = recipe.get("toml")
        if (recipe.get("engine_revision") == engine_revision and isinstance(text, str) and
                recipe.get("sha256") == hashlib.sha256(text.encode()).hexdigest()):
            return text
        return None

    def video_standard(self) -> str | None:
        """Keep the selected SMS console timing across compiler revisions.

        The full compilation recipe is engine-scoped. For records written
        before video selection had its own field, recover only the timing from
        an intact, ROM-matched recipe; never reuse its compiler settings.
        """
        from .systems import MASTER_SYSTEM
        metadata = self.metadata()
        choice = metadata.get("video_selection", {})
        if (isinstance(choice, dict) and choice.get("system_id") == MASTER_SYSTEM.id and
                choice.get("standard") in MASTER_SYSTEM.video_modes):
            return choice["standard"]
        recipe = metadata.get("recipe", {})
        if not isinstance(recipe, dict):
            return None
        text = recipe.get("toml")
        if not isinstance(text, str) or recipe.get("sha256") != hashlib.sha256(text.encode()).hexdigest():
            return None
        try:
            parsed = tomllib.loads(text)
            game = parsed.get("game", {})
            video = parsed.get("video", {})
            if (not isinstance(game, dict) or not isinstance(video, dict) or
                    game.get("platform") != MASTER_SYSTEM.id or
                    game.get("crc32") != self.rom.crc32 or
                    game.get("sha256", self.rom.sha256) != self.rom.sha256):
                return None
            standard = video.get("standard")
            return standard if standard in MASTER_SYSTEM.video_modes else None
        except (tomllib.TOMLDecodeError, TypeError, ValueError):
            return None

    def remember(self, title: str, config: str, report: dict, compiler_signature: str) -> None:
        with entry_lock(self.directory):
            metadata = self.metadata()
            generations = metadata.get("generations", [])
            if not isinstance(generations, list):
                generations = []
            total = metadata.get("total_generations", len(generations))
            if not isinstance(total, int) or total < 0:
                total = len(generations)
            generations.append({"created_utc": report["created_utc"], "compiler_signature": compiler_signature,
                "engine_revision": report["engine_revision"], "smsrecomp_version": report["version"],
                "executable": report["executable"], "checks": report["final_checks"],
                "strict_checks": report["strict_checks"], "learning": report["learning"],
                "reference_vdp_trace_match": report["reference_vdp_trace_match"]})
            # The checks are evidence about tested paths, never a certification
            # of the game or of every learned entry's complete CPU behaviour.
            metadata = {"schema": SCHEMA, "title": title, "rom": self.rom.metadata(),
                "updated_utc": datetime.now(timezone.utc).isoformat(),
                "recipe": {"toml": config, "sha256": hashlib.sha256(config.encode()).hexdigest(),
                           "engine_revision": report["engine_revision"]},
                "total_generations": total + 1, "generations": generations[-100:]}
            from .systems import MASTER_SYSTEM
            system = report.get("system", {})
            video = report.get("video_model", {})
            if (isinstance(system, dict) and isinstance(video, dict) and
                    system.get("id") == MASTER_SYSTEM.id and
                    video.get("standard") in MASTER_SYSTEM.video_modes):
                metadata["video_selection"] = {"system_id": MASTER_SYSTEM.id,
                                               "standard": video["standard"]}
            atomic_json(self.record, metadata)


def list_games(root: Path | None = None) -> list[dict]:
    root = root or library_root()
    if not root.exists():
        return []
    result = []
    for directory in sorted(root.iterdir()):
        match = re.fullmatch(r"(?:.*-)?([0-9a-f]{64})", directory.name)
        if not directory.is_dir() or not match:
            continue
        sha256 = match[1]
        title = directory.name.rsplit("-", 1)[0] if "-" in directory.name else sha256[:12]
        try:
            record = json.loads((directory / "compilation.json").read_text(encoding="utf-8"))
            if record.get("rom", {}).get("sha256") == sha256:
                title = record.get("title", title)
        except (OSError, ValueError, AttributeError):
            pass
        result.append({"title": title, "sha256": sha256,
                       "observations": len(read_observations(directory / "observations.log")),
                       "directory": str(directory)})
    return result
