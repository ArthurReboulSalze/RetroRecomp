"""Console profiles used by identification, batch conversion and output paths.

Each future console registers its own reader, converter and timing vocabulary.
No timing rule or cartridge format is shared implicitly between systems.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from zipfile import ZipFile, BadZipFile

MAX_ARCHIVED_ROM_BYTES = {'.sms': 4 * 1024 * 1024 + 512,
                          '.gg': 4 * 1024 * 1024 + 512,
                          '.gb': 8 * 1024 * 1024,
                          '.nes': 128 * 1024 * 1024 + 528,
                          '.md': 8 * 1024 * 1024,
                          '.gen': 8 * 1024 * 1024,
                          '.sfc': 8 * 1024 * 1024 + 512,
                          '.smc': 8 * 1024 * 1024 + 512,
                          '.bin': 8 * 1024 * 1024,
                          '.rom': 8 * 1024 * 1024}

ROM_CANDIDATE_EXTENSIONS = frozenset({
    '.sms', '.gg', '.gb', '.zip', '.bin', '.rom', '.gbc', '.gba', '.nes',
    '.fds', '.sfc', '.smc', '.n64', '.z64', '.v64', '.md', '.gen', '.smd', '.pce',
    '.a26', '.a78', '.7z', '.chd', '.cue', '.iso',
})


class UnsupportedConsoleError(ValueError):
    """The source may be a ROM, but no safe console choice was established."""


class ConsoleMismatchError(UnsupportedConsoleError):
    def __init__(self, message: str, detected_system: str):
        super().__init__(message)
        self.detected_system = detected_system


def discover_roms(folder: Path) -> list[Path]:
    """Scan without writing beside source ROMs, including foreign systems."""
    return sorted((path for path in folder.rglob('*')
                   if path.is_file() and path.suffix.casefold() in ROM_CANDIDATE_EXTENSIONS
                   and (path.suffix.casefold() != '.md' or path.stat().st_size >= 0x8000)),
                  key=lambda path: str(path).casefold())


def archive_rom(path: Path) -> tuple[str, bytes]:
    """Read one cartridge from a ZIP without extracting beside the source."""
    try:
        with ZipFile(path) as archive:
            candidates = [entry for entry in archive.infolist()
                          if not entry.is_dir() and Path(entry.filename).suffix.casefold() in MAX_ARCHIVED_ROM_BYTES]
            if not candidates:
                raise UnsupportedConsoleError(
                    'Unknown console in ZIP: no supported cartridge extension found.')
            if len(candidates) != 1:
                raise ValueError('ZIP must contain exactly one supported cartridge.')
            entry = candidates[0]
            suffix = Path(entry.filename).suffix.casefold()
            maximum = MAX_ARCHIVED_ROM_BYTES[suffix]
            if entry.file_size > maximum:
                raise ValueError('Archived ROM exceeds the cartridge size limit.')
            with archive.open(entry) as source:
                data = source.read(maximum + 1)
            if len(data) > maximum:
                raise ValueError('Archived ROM exceeds the cartridge size limit.')
            return suffix, data
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise ValueError(f'Cannot read cartridge ZIP: {exc}') from exc


class SystemProfile(ABC):
    id: str
    name: str
    extensions: tuple[str, ...]
    export_folder: str
    video_modes: tuple[str, ...]

    @abstractmethod
    def read_rom(self, path: Path):
        """Validate and identify one cartridge without changing it."""

    @abstractmethod
    def default_video_mode(self, path: Path) -> str:
        """Return this console's default timing, with no fidelity claim."""

    @abstractmethod
    def convert(self, path: Path, **options) -> Path:
        """Build the console-specific runtime and executable."""


from .master_system import MASTER_SYSTEM  # noqa: E402
from .game_gear import GAME_GEAR  # noqa: E402
from .game_boy import GAME_BOY  # noqa: E402
from .nes import NES  # noqa: E402
from .console16 import MEGA_DRIVE, SUPER_NINTENDO  # noqa: E402

PROFILES: tuple[SystemProfile, ...] = (MASTER_SYSTEM, GAME_GEAR, GAME_BOY, NES, MEGA_DRIVE, SUPER_NINTENDO)


def get_profile(system_id: str) -> SystemProfile:
    for profile in PROFILES:
        if profile.id == system_id:
            return profile
    raise ValueError(f"Unsupported console profile: {system_id}")


def profile_for_path(path: Path, selected_system: str | None = None) -> SystemProfile:
    suffix = path.suffix.casefold()
    data = None
    if suffix == '.zip':
        suffix, data = archive_rom(path)
    matches = [profile for profile in PROFILES if suffix in profile.extensions]
    if len(matches) == 1:
        profile = matches[0]
        if selected_system and selected_system != profile.id:
            raise ConsoleMismatchError(
                f'Detected {profile.name}; selected {get_profile(selected_system).name}. '
                'Choose Automatic or the matching console.', profile.id)
        return profile
    if suffix not in ('.bin', '.rom'):
        raise UnsupportedConsoleError(f'Unknown console for {path.name} ({suffix or "no extension"}).')
    if data is None:
        with path.open('rb') as source:
            data = source.read(8 * 1024 * 1024 + 513)
    detected = None
    from ..cartridge16 import is_megadrive, snes_header
    if is_megadrive(data):
        detected = MEGA_DRIVE
    if data.startswith(b'NES\x1a'):
        detected = NES
    offset = 512 if len(data) % 16384 == 512 else 0
    sega = data[offset:]
    for header in (() if detected is not None else (0x7ff0, 0x3ff0, 0x1ff0)):
        if sega[header:header + 8] == b'TMR SEGA':
            region = sega[header + 15] >> 4
            if region in (3, 4):
                detected = MASTER_SYSTEM
            if region in (5, 6, 7):
                detected = GAME_GEAR
            if detected is not None:
                break
    if detected is None and snes_header(sega) is not None:
        detected = SUPER_NINTENDO
    if detected is None and len(data) >= 0x8000 and len(data) % 0x4000 == 0:
        checksum = 0
        for value in data[0x134:0x14d]:
            checksum = (checksum - value - 1) & 0xff
        title = data[0x134:0x143].split(b'\0', 1)[0]
        size_code = data[0x148]
        declared_size = (0x8000 << size_code) if size_code <= 8 else {
            0x52: 72 * 0x4000, 0x53: 80 * 0x4000,
            0x54: 96 * 0x4000}.get(size_code)
        if (checksum == data[0x14d] and declared_size == len(data)
                and title and all(32 <= value < 127 for value in title)):
            detected = GAME_BOY
    if selected_system:
        if detected is not None and detected.id != selected_system:
            raise ConsoleMismatchError(
                f'Detected {detected.name}; selected {get_profile(selected_system).name}. '
                'Choose Automatic or the matching console.', detected.id)
        # Explicit choice resolves a headerless dump; readers still validate
        # cartridge size and reject unsupported formats.
        return get_profile(selected_system)
    if detected is not None:
        return detected
    raise UnsupportedConsoleError(
        f'Unknown console for {path.name}: no recognized cartridge header. '
        'Choose the console manually if this is a headerless ROM.')
