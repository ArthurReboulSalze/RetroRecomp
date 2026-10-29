"""The registration list of the machines.

Adding a machine registers its profile here, once: its profile module (`systems/<machine>.py`, which
carries all of the data the registries elsewhere read) and one line below. This module is an interface
module of the stamps (`stamp_inputs.INTERFACE_MODULES`): no stamp hashes it, so registering a machine
moves the stamp of no other console. The profile modules, which are stamped, hold the data; the generic
code in `systems/__init__.py` reads the registered profiles and names none of them.

The order of the registration is the one of the documents and settings (X68000 before CPS-1). The order of
detection is not this one: each profile declares its own `identify` orders.
"""
from __future__ import annotations

from . import SystemProfile
from .cps1 import CPS1
from .game_boy import GAME_BOY
from .game_gear import GAME_GEAR
from .console16 import MEGA_DRIVE, SUPER_NINTENDO
from .master_system import MASTER_SYSTEM
from .neogeo import NEOGEO
from .nes import NES
from .x68000 import X68000

# Extensions of files that are cartridge images or disks of machines the converter does not handle, plus the
# containers and headerless names every machine may sit in. They are listed by `discover_roms` so that the
# window can say "unknown console" instead of skipping them silently. Each machine's own extensions are added
# from its profile.
FOREIGN_EXTENSIONS = frozenset({
    '.zip', '.bin', '.rom', '.gbc', '.gba', '.fds', '.n64', '.z64', '.v64', '.smd', '.pce',
    '.a26', '.a78', '.7z', '.chd', '.cue', '.iso',
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


for _profile in (MASTER_SYSTEM, GAME_GEAR, GAME_BOY, NES, MEGA_DRIVE, SUPER_NINTENDO, NEOGEO, X68000, CPS1):
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
