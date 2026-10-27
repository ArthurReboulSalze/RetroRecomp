"""Console profiles used by identification, batch conversion and output paths.

Each future console registers its own reader, converter and timing vocabulary.
No timing rule or cartridge format is shared implicitly between systems.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
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
    '.a26', '.a78', '.7z', '.chd', '.cue', '.iso', '.neo',
    '.dim', '.xdf', '.m3u',
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


@dataclass(frozen=True)
class Cpu:
    """One processor of a machine: its architecture, its role and the unit its
    interpreter-fallback counters use. Units are never added across CPUs."""
    arch: str
    role: str  # 'main' or 'sound'
    unit: str  # 'cycles' or 'instructions'


@dataclass(frozen=True)
class OptionKey:
    """A converter option only one family of consoles accepts.

    ``signature`` is False for options that tune how a conversion runs (worker
    counts) and must never change the export's request signature."""
    name: str
    signature: bool = True


@dataclass(frozen=True)
class Capabilities:
    """What a machine offers the player shell beyond a plain pad."""
    guns: tuple[str, ...] = ()
    mouse: bool = False
    keyboard: bool = False
    battery: bool = False
    disks: bool = False


STATUSES = ('experimental', 'supported')


class SystemProfile(ABC):
    """One console, described by data first (every attribute below has a
    default) and by a few hooks where the behaviour differs.

    Registries and branches elsewhere in the converter read these attributes
    instead of listing console ids (docs/STANDARDS.md, rule 3)."""
    id: str
    name: str
    extensions: tuple[str, ...]
    export_folder: str
    video_modes: tuple[str, ...]
    # 'experimental' or 'supported' (see the checklist in docs/STANDARDS.md).
    status: str = 'supported'
    scope_note: str = ''
    cpus: tuple[Cpu, ...] = ()
    # Cartridge circuits integrated and counted apart from the CPUs.
    cartridge_devices: tuple[str, ...] = ()
    # 'cartridge' (one image), 'romset' (several files in a ZIP), 'disk'.
    media_kinds: tuple[str, ...] = ('cartridge',)
    # Firmware the user supplies separately from the game.
    firmware: tuple[str, ...] = ()
    # Family of the quick-state ABI: consoles of one family share the format.
    quick_state_family: str = ''
    capabilities: Capabilities = Capabilities()
    # 'witnessed' (converted and played on Linux) or 'pending'.
    linux: str = 'witnessed'
    # Runtime-feedback record kinds (feedback.py) this console may write.
    feedback_kinds: frozenset = frozenset()
    default_frames: int = 3600
    quick_frames: int = 1800
    # How the result summary counts the fallback: 'cycles' or 'opcodes'.
    fallback_display: str = 'cycles'
    # The title comes from the romset description, not the file name.
    title_from_romset: bool = False
    # The converter publishes the executable itself unless the batch, which
    # publishes it, says otherwise (``publish_result=False``).
    converter_publishes: bool = False
    # Console-specific converter options. The batch lets each one through to
    # this console's converter only; every other console never sees it.
    option_keys: tuple[OptionKey, ...] = ()
    # The option (one of option_keys) that carries the batch's worker count.
    parallel_games_option: str | None = None

    @property
    def experimental(self) -> bool:
        """Read-only compatibility with the former ad-hoc attribute."""
        return self.status != 'supported'

    @property
    def option_key_names(self) -> frozenset:
        return frozenset(key.name for key in self.option_keys)

    def request_identity(self, item, options: dict, settings: dict) -> None:
        """Add the console's own identity (firmware, machine) to the request
        settings that are about to be hashed. Most consoles have none."""

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
from .neogeo import NEOGEO  # noqa: E402
from .cps1 import CPS1  # noqa: E402
from .x68000 import X68000  # noqa: E402

PROFILES: tuple[SystemProfile, ...] = (MASTER_SYSTEM, GAME_GEAR, GAME_BOY, NES, MEGA_DRIVE, SUPER_NINTENDO, NEOGEO,
                                       CPS1)
# Availability in the converter does not imply the profile has left development.
from ..x68000 import developer_available  # noqa: E402
EXPERIMENTAL_PROFILES: tuple[SystemProfile, ...] = (X68000,) if developer_available() else ()


# Every console the converter knows, whether or not this installation can
# convert it: the registry the lists of console ids elsewhere are read from.
# The order is the one of the documents and settings (X68000 before CPS-1);
# PROFILES keeps the order detection tries them in.
ALL_PROFILES: tuple[SystemProfile, ...] = (MASTER_SYSTEM, GAME_GEAR, GAME_BOY, NES, MEGA_DRIVE, SUPER_NINTENDO,
                                           NEOGEO, X68000, CPS1)


def available_profiles():
    return PROFILES + EXPERIMENTAL_PROFILES


def find_profile(system_id: str) -> SystemProfile | None:
    """The profile of one console id, or None for an id nobody registered."""
    return next((profile for profile in ALL_PROFILES if profile.id == system_id), None)


def system_ids() -> tuple[str, ...]:
    """The ids of every console, in registration order."""
    return tuple(profile.id for profile in ALL_PROFILES)


def get_profile(system_id: str) -> SystemProfile:
    # Metadata, cache and saved-feedback paths remain readable for an existing
    # X68000 export even when this installation cannot compile that prototype.
    # Conversion availability is checked by profile_for_path and convert.
    for profile in ALL_PROFILES:
        if profile.id == system_id:
            return profile
    raise ValueError(f"Unsupported console profile: {system_id}")


def console_option_keys() -> frozenset:
    """Every console-specific option name, whichever console accepts it."""
    return frozenset(name for profile in ALL_PROFILES for name in profile.option_key_names)


def unsigned_option_keys() -> frozenset:
    """Options that never enter a request signature (they only size the work)."""
    return frozenset(key.name for profile in ALL_PROFILES for key in profile.option_keys
                     if not key.signature)


def drop_foreign_options(system_id: str, settings: dict) -> None:
    """Remove, in place, the console-specific options another console owns."""
    own = get_profile(system_id).option_key_names
    for name in console_option_keys() - own:
        settings.pop(name, None)


def _sega_profile(data: bytes, byte_size: int) -> SystemProfile | None:
    offset = 512 if byte_size % 16384 == 512 else 0
    sega = data[offset:]
    for header in (0x7ff0, 0x3ff0, 0x1ff0):
        if sega[header:header + 8] == b'TMR SEGA' and len(sega) > header + 15:
            region = sega[header + 15] >> 4
            if region in (3, 4): return MASTER_SYSTEM
            if region in (5, 6, 7): return GAME_GEAR
    return None


def profile_for_path(path: Path, selected_system: str | None = None) -> SystemProfile:
    suffix = path.suffix.casefold()
    data = None
    if suffix in X68000.extensions:
        if not developer_available():
            raise UnsupportedConsoleError('The X68000 development SDK is unavailable in this installation.')
        if selected_system and selected_system != 'x68':
            raise ConsoleMismatchError('Detected Sharp X68000; choose Automatic or Sharp X68000.', 'x68')
        return X68000
    if suffix == '.zip' and selected_system in (None, 'cps1'):
        # Arcade romsets are recognised by their program ROM CRCs, never by name.
        from ..cps1 import looks_like_cps1_zip
        try:
            detected_cps1 = selected_system == 'cps1' or looks_like_cps1_zip(path)
        except ValueError:
            detected_cps1 = False
        if detected_cps1:
            return CPS1
    if suffix in ('.neo', '.zip'):
        from ..neogeo import looks_like_neogeo_zip, parse_neo
        detected_ng = suffix == '.neo' or selected_system == 'ng' or looks_like_neogeo_zip(path)
        if detected_ng:
            if suffix == '.neo': parse_neo(path)
            if selected_system and selected_system != 'ng':
                raise ConsoleMismatchError('Detected Neo Geo; choose Automatic or Neo Geo.', 'ng')
            return NEOGEO
    if suffix == '.zip':
        suffix, data = archive_rom(path)
    matches = [profile for profile in PROFILES if suffix in profile.extensions]
    if len(matches) == 1:
        profile = matches[0]
        if profile.id in ('sms', 'gg') and (data is not None or path.is_file()):
            # These consoles share a cartridge format. A known header is
            # stronger evidence than a misnamed extension, also inside ZIPs.
            if data is None:
                byte_size = path.stat().st_size
                with path.open('rb') as source:
                    data = source.read(0x8000 + 512)
            else:
                byte_size = len(data)
            profile = _sega_profile(data, byte_size) or profile
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
    if detected is None:
        detected = _sega_profile(data, len(data))
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
