"""Console profiles used by identification, batch conversion and output paths.

Each future console registers its own reader, converter and timing vocabulary.
No timing rule or cartridge format is shared implicitly between systems.

This module holds the types (`SystemProfile` and its data), the generic functions that read the registered
profiles (identification, option filtering, lookups) and nothing that names a console. The registration list
is `systems/registry.py`, which is not an input of any stamp: a new machine adds its profile module and one
line there. The lists (`ALL_PROFILES`, `PROFILES`, `EXPERIMENTAL_PROFILES`, `ROM_CANDIDATE_EXTENSIONS`) and
the profile constants (`MASTER_SYSTEM`...) are read from it on access (module `__getattr__`), so every
existing `from retrorecomp.systems import ...` keeps working.
"""
from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile, BadZipFile

from .specs import (Catalogues, Identify, InputLayout, LibraryLayout, PathSpec, ReportShape,  # noqa: F401
                    SharedKnowledge)

MAX_ARCHIVED_ROM_BYTES = {'.sms': 4 * 1024 * 1024 + 512,
                          '.gg': 4 * 1024 * 1024 + 512,
                          '.gb': 8 * 1024 * 1024,
                          '.nes': 128 * 1024 * 1024 + 528,
                          '.md': 8 * 1024 * 1024,
                          '.gen': 8 * 1024 * 1024,
                          '.sfc': 8 * 1024 * 1024 + 512,
                          '.smc': 8 * 1024 * 1024 + 512,
                          '.fig': 8 * 1024 * 1024 + 512,
                          '.bin': 8 * 1024 * 1024,
                          '.rom': 8 * 1024 * 1024}


class UnsupportedConsoleError(ValueError):
    """The source may be a ROM, but no safe console choice was established."""


class ConsoleMismatchError(UnsupportedConsoleError):
    def __init__(self, message: str, detected_system: str):
        super().__init__(message)
        self.detected_system = detected_system


def discover_roms(folder: Path) -> list[Path]:
    """Scan without writing beside source ROMs, including foreign systems."""
    candidates = _registry().ROM_CANDIDATE_EXTENSIONS
    return sorted((path for path in folder.rglob('*')
                   if path.is_file() and path.suffix.casefold() in candidates
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
    counts) and must never change the export's request signature.

    ``kind`` says what the option is, so that the interface and the command line can build a control from it:
    'flag' (on or off), 'path' (a file the player supplies, saved relative to the export folder), 'choice' (one
    of ``choices``), 'count' (a number of workers, never shown) or 'plan' (a table the converter passes to
    itself, never shown). ``label`` is the interface string key of the control, or the text itself where no
    key exists; ``hint`` the key of its tooltip; ``default`` the value used when nothing was chosen."""
    name: str
    signature: bool = True
    kind: str = 'flag'
    label: str = ''
    hint: str = ''
    choices: tuple = ()
    default: object = None


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
    # The game's key in the paths banks is only known once a conversion has run (Neo Geo: a ZIP set
    # has no prepared cartridge before). The batch then computes the request parts again before it
    # writes the receipt, so that the receipt carries what the conversion used.
    knowledge_identity_after_conversion: bool = False
    # The data below is what the registries elsewhere used to hold for every console (docs/NEW_MACHINE.md).
    # ``None`` means the machine has no entry in that registry (it declines it, on the record).
    path_spec: PathSpec | None = None
    report_shape: ReportShape | None = None
    catalogues: Catalogues | None = None
    library_layout: LibraryLayout | None = None
    input_layout: InputLayout | None = None
    shared_knowledge: SharedKnowledge | None = None
    # The host-kit adapter file below native/hostkit (hostkit.py), for the machines on the common host kit.
    host_adapter: str | None = None
    # Recognition of a file (systems.profile_for_path) and the machine's presence in an installation.
    identify: Identify = Identify()
    # The machine is only convertible when the installation carries its files (``available``).
    developer_only: bool = False
    # The shared groups of source files (stamp_inputs.py, keys ``shares:<name>``) this machine's game is built from:
    # a machine that reuses the Mega Drive code generator names it here instead of editing a list of consoles.
    stamp_groups: tuple[str, ...] = ()

    @property
    def options_tab(self) -> str:
        """The interface string key of the machine's options tab."""
        return 'options_' + self.id

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

    def available(self) -> bool:
        """True when this installation can convert the machine (True unless ``developer_only``)."""
        return True

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        """Claim a file from its path before a ZIP is opened: return this profile, or None when the file is not
        this machine's. May raise ``UnsupportedConsoleError`` or ``ConsoleMismatchError``."""
        return None

    def refine_match(self, path: Path, data: bytes | None):
        """The profile that finally owns a file whose extension named this one (two machines may share a
        cartridge format and tell each other apart by header). ``data`` is the bytes of a ZIP member, else None."""
        return self

    def identify_content(self, data: bytes):
        """Sniff the bytes of a ``.bin`` or ``.rom``: return the profile that owns them, or None."""
        return None

    def knowledge_identity(self, item, settings: dict) -> str:
        """The key of this game in the paths banks: the ROM's hash, unless the console names its
        games otherwise (Neo Geo: its prepared cartridge and BIOS). `settings` is what
        `request_identity` filled in."""
        return item.sha256

    @abstractmethod
    def read_rom(self, path: Path):
        """Validate and identify one cartridge without changing it."""

    @abstractmethod
    def default_video_mode(self, path: Path) -> str:
        """Return this console's default timing, with no fidelity claim."""

    @abstractmethod
    def convert(self, path: Path, **options) -> Path:
        """Build the console-specific runtime and executable."""


def _registry():
    # importlib, not ``from . import registry``: that form asks this module for the attribute first.
    return importlib.import_module('.registry', __name__)


def __getattr__(name: str):
    """The lists and the profile constants are read from the registry when asked for."""
    if name.startswith('__') or name == 'registry':
        raise AttributeError(name)
    try:
        return _registry().exported(name)
    except KeyError:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}') from None


def convertible_profiles() -> tuple[SystemProfile, ...]:
    """The profiles this installation can convert: a developer-only machine (X68000) only with its files."""
    return _registry().convertible_profiles()


def available_profiles():
    return convertible_profiles()


def find_profile(system_id: str) -> SystemProfile | None:
    """The profile of one console id, or None for an id nobody registered."""
    return next((profile for profile in _registry().all_profiles() if profile.id == system_id), None)


def system_ids() -> tuple[str, ...]:
    """The ids of every console, in registration order."""
    return tuple(profile.id for profile in _registry().all_profiles())


def get_profile(system_id: str) -> SystemProfile:
    # Metadata, cache and saved-feedback paths remain readable for an existing
    # X68000 export even when this installation cannot compile that prototype.
    # Conversion availability is checked by profile_for_path and convert.
    for profile in _registry().all_profiles():
        if profile.id == system_id:
            return profile
    raise ValueError(f"Unsupported console profile: {system_id}")


def console_option_keys() -> frozenset:
    """Every console-specific option name, whichever console accepts it."""
    return frozenset(name for profile in _registry().all_profiles() for name in profile.option_key_names)


def unsigned_option_keys() -> frozenset:
    """Options that never enter a request signature (they only size the work)."""
    return frozenset(key.name for profile in _registry().all_profiles() for key in profile.option_keys
                     if not key.signature)


def drop_foreign_options(system_id: str, settings: dict) -> None:
    """Remove, in place, the console-specific options another console owns."""
    own = get_profile(system_id).option_key_names
    for name in console_option_keys() - own:
        settings.pop(name, None)


def profile_for_path(path: Path, selected_system: str | None = None) -> SystemProfile:
    """Recognise a file: each registered profile's hooks in their declared order (the file itself, before a ZIP
    is opened), then the extension, then the bytes of a headerless ``.bin`` or ``.rom``. An explicit choice
    settles only a headerless dump."""
    registry = _registry()
    suffix = path.suffix.casefold()
    data = None
    for profile in registry.path_stage():
        found = profile.identify_path(path, suffix, selected_system)
        if found is not None:
            return found
    if suffix == '.zip':
        suffix, data = archive_rom(path)
    matches = [profile for profile in registry.listed_profiles() if suffix in profile.extensions]
    if len(matches) == 1:
        profile = matches[0].refine_match(path, data)
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
    for profile in registry.content_stage():
        detected = profile.identify_content(data)
        if detected is not None:
            break
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
