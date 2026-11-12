"""The registration list of the machines.

Adding a machine registers its profile here, once: its profile module (`systems/<machine>.py`, which
carries all of the data the registries elsewhere read) and one line below. This module is an interface
module of the stamps (`stamp_inputs.INTERFACE_MODULES`): no stamp hashes it, so registering a machine
moves the stamp of no other console. The profile modules, which are stamped, hold the data; the generic
code in `systems/__init__.py` reads the registered profiles and names none of them.

The order of the registration is the one of the documents and settings (X68000 before CPS-1). The order of
detection is not this one: each profile declares its own `identify` orders.

Two optional capabilities of a profile are read here and by the registry and report checks with `getattr`, so that
declaring them in a profile module moves no stamp of another console (the profile base class is a stamp input of all):
* `emulated` (str): the machine runs its games in an emulator instead of recompiling them, and says why in one sentence.
  It declares no CPU; its report has no CPU section, a native share of 0 and an `engine` section (report_schema).
* `accepts_folders` (bool): the machine takes a game folder as its input. `discover_folders` offers a folder to the
  machine's `find_folders(root, notice)`; the machine's `identify_path` claims a folder it recognises. File discovery
  (`systems.discover_roms`) is not changed: the folders are added beside the files.
"""
from __future__ import annotations

from pathlib import Path

from . import SystemProfile
from .amiga import AMIGA
from .atari_st import ATARI_ST
from .cps1 import CPS1
from .cps2 import CPS2
from .game_boy import GAME_BOY
from .game_gear import GAME_GEAR
from .gba import GAME_BOY_ADVANCE
from .console16 import MEGA_DRIVE, SUPER_NINTENDO
from .master_system import MASTER_SYSTEM
from .msx import MSX, MSX2
from .n64 import NINTENDO_64
from .neogeo import NEOGEO
from .nes import NES
from .pc_engine import PC_ENGINE
from .scummvm import SCUMMVM
from .psx import PLAYSTATION
from .x68000 import X68000

# Extensions of files that are cartridge images or disks of machines the converter does not handle, plus the
# containers and headerless names every machine may sit in. They are listed by `discover_roms` so that the
# window can say "unknown console" instead of skipping them silently. Each machine's own extensions are added
# from its profile.
FOREIGN_EXTENSIONS = frozenset({
    '.zip', '.bin', '.rom', '.gbc', '.fds', '.smd',
    '.a26', '.a78', '.7z', '.chd',
})

_REGISTERED: list[SystemProfile] = []


def register(profile: SystemProfile) -> None:
    """Add one machine. Its id and its identification orders must not collide with a registered one."""
    if not isinstance(profile, SystemProfile):
        raise TypeError('only a SystemProfile can be registered')
    if any(known.id == profile.id for known in _REGISTERED):
        raise ValueError(f'console id already registered: {profile.id}')
    for stage in ('path_order', 'content_order'):
        order = getattr(profile.identify, stage)
        if order is not None and any(getattr(known.identify, stage) == order for known in _REGISTERED):
            raise ValueError(f'identification order {order} ({stage}) is already taken: {profile.id}')
    _REGISTERED.append(profile)


def unregister(system_id: str) -> SystemProfile:
    """Remove one machine (tests that register a synthetic profile put the registry back this way)."""
    for index, profile in enumerate(_REGISTERED):
        if profile.id == system_id:
            return _REGISTERED.pop(index)
    raise KeyError(system_id)


for _profile in (MASTER_SYSTEM, GAME_GEAR, GAME_BOY, NES, MEGA_DRIVE, SUPER_NINTENDO, NEOGEO, X68000, CPS1, CPS2, PC_ENGINE, GAME_BOY_ADVANCE, AMIGA, ATARI_ST, NINTENDO_64, SCUMMVM, PLAYSTATION, MSX, MSX2):
    register(_profile)
del _profile


def all_profiles() -> tuple[SystemProfile, ...]:
    """Every console the converter knows, whether or not this installation can convert it."""
    return tuple(_REGISTERED)


def listed_profiles() -> tuple[SystemProfile, ...]:
    """The machines every installation carries, in registration order (`systems.PROFILES`)."""
    return tuple(profile for profile in _REGISTERED if not profile.developer_only)


def convertible_profiles() -> tuple[SystemProfile, ...]:
    """The profiles this installation can convert: the developer-only ones only with their files."""
    return listed_profiles() + tuple(profile for profile in _REGISTERED
                                     if profile.developer_only and profile.available())


def experimental_profiles() -> tuple[SystemProfile, ...]:
    # Read from the profiles' own status attribute, so this registry cannot drift from the statuses the
    # documents and interface lint against.
    return tuple(profile for profile in convertible_profiles() if profile.status == 'experimental')


def rom_candidate_extensions() -> frozenset:
    """Every extension `discover_roms` lists: the machines' own and the foreign ones."""
    return frozenset(extension for profile in _REGISTERED for extension in profile.extensions) | FOREIGN_EXTENSIONS


def path_stage() -> tuple[SystemProfile, ...]:
    """The profiles that look at the file itself, in the order they are asked."""
    return tuple(sorted((profile for profile in _REGISTERED if profile.identify.path_order is not None),
                        key=lambda profile: profile.identify.path_order))


def content_stage() -> tuple[SystemProfile, ...]:
    """The profiles that sniff the bytes of a headerless dump, in the order they are asked."""
    return tuple(sorted((profile for profile in _REGISTERED if profile.identify.content_order is not None),
                        key=lambda profile: profile.identify.content_order))


def emulated(profile: SystemProfile) -> str:
    """The reason a machine is emulated (empty for a recompiled machine)."""
    return getattr(profile, 'emulated', '') or ''


def folder_profiles() -> tuple[SystemProfile, ...]:
    """The registered machines that take a game folder as their input."""
    return tuple(profile for profile in _REGISTERED if getattr(profile, 'accepts_folders', False))


class FolderDiscoveryUnavailable(Exception):
    """A machine's folder discovery cannot run yet (its build tools are missing). `key` is the interface sentence that says so."""

    def __init__(self, key: str, message: str = ''):
        super().__init__(message or key)
        self.key = key


def discover_folders(folder, unavailable: list | None = None, notice=None) -> list:
    """The game folders at or below `folder` that a machine taking folders recognises, beside `discover_roms`.
    A machine whose discovery cannot run (FolderDiscoveryUnavailable) is skipped; its exception is appended to
    `unavailable` when the caller gives a list, so the interface can say why nothing was found. `notice` receives the
    interface sentence of a long step that starts during the discovery (the first build of a machine's detection)."""
    found = {}
    for profile in folder_profiles():
        if profile.available():
            try:
                paths = profile.find_folders(folder, notice)
            except FolderDiscoveryUnavailable as exc:
                if unavailable is not None:
                    unavailable.append(exc)
                continue
            for path in paths:
                found.setdefault(str(path).casefold(), path)
    return sorted(found.values(), key=lambda path: str(path).casefold())


def discover_games(folder, unavailable: list | None = None, notice=None) -> tuple[list, list]:
    """(cartridge files, game folders) at or below `folder`, for the window and the command line alike.
    The files of a folder a machine recognised as a game are that game's data, not cartridges: a `.bin` of an
    adventure's data is never offered as a ROM of its own (it would be an unrecognised row, or an error)."""
    from . import discover_roms
    roms = discover_roms(Path(folder))
    games = discover_folders(folder, unavailable, notice)
    roots = [Path(game) for game in games]
    return [rom for rom in roms if not any(root == rom or root in rom.parents for root in roots)], games


_LISTS = {'ALL_PROFILES': all_profiles, 'PROFILES': listed_profiles,
          'EXPERIMENTAL_PROFILES': experimental_profiles, 'ROM_CANDIDATE_EXTENSIONS': rom_candidate_extensions}


def __getattr__(name: str):
    if name in _LISTS:
        return _LISTS[name]()
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def exported(name: str):
    """What `retrorecomp.systems` hands out under this name: a list above or a profile constant."""
    if name in _LISTS:
        return _LISTS[name]()
    value = globals().get(name)
    if isinstance(value, SystemProfile):
        return value
    raise KeyError(name)
