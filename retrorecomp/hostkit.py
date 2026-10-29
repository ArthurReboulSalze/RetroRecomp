"""The sources of the host kit that exported games link (docs/HOST_KIT.md).

The player shell of a generated game (window, picture, controls, menus,
audio output, quick-state requests) is a set of files below native/hostkit: a
shell shared by every machine, and one adapter per machine (phase 1: Mega Drive,
Super Nintendo, Neo Geo, CPS-1; phase 2: NES; phase 4: Master System and Game Gear,
which share one adapter; phase 5: Game Boy). This module lists
them and copies them into a game project. It is a host input: a change here or
in the kit upgrades an export without rediscovering its code, and the headless
runs that discover and validate a game never use the shell.
"""
from pathlib import Path

from .paths import ASSETS
from .systems.registry import all_profiles

HEADERS = ('hostkit.h', 'hostkit_internal.h')
SHELL = tuple(f'shell/rrhk_{name}.c' for name in
              ('audio', 'events', 'input', 'main', 'menu', 'options', 'pointer', 'ring', 'timing', 'video'))
# The adapter file of each machine on the kit, below native/hostkit: the profile's `host_adapter` (the Master
# System and the Game Gear share one; an adapter an engine's own platform file includes, `.inc`, is staged but
# not compiled by itself). A new machine adds no line here.
ADAPTERS = {profile.id: profile.host_adapter for profile in all_profiles() if profile.host_adapter}


def sources(family: str) -> list[str]:
    """The kit's C files of one machine, as the project-relative paths a build lists."""
    return ['hostkit/' + name for name in (*SHELL, ADAPTERS[family]) if name.endswith('.c')]


def stage(project: Path, family: str) -> list[str]:
    """Copy the kit's headers, shell and the machine's adapter into `project/hostkit`; returns the C files to compile."""
    for name in (*HEADERS, *SHELL, ADAPTERS[family]):
        target = project / 'hostkit' / name
        data = (ASSETS / 'native/hostkit' / name).read_bytes()
        if target.is_file() and target.read_bytes() == data:
            continue  # keep the timestamp: an unchanged file rebuilds nothing
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return sources(family)
