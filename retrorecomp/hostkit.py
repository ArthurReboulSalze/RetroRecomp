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

HEADERS = ('hostkit.h', 'hostkit_internal.h', 'hostkit_session.h')
SHELL = tuple(f'shell/rrhk_{name}.c' for name in
              ('audio', 'events', 'input', 'main', 'menu', 'options', 'pointer', 'ring', 'timing', 'video'))
# Shell files rrhk_main.c includes (staged beside it, never compiled by themselves): multiplayer stays out of every machine's
# build list, so the machines that compile the kit from their own CMake file need no change.
SHELL_INCLUDED = ('shell/rrhk_session.inc', 'shell/rrhk_chat.inc',   # rrhk_session.inc includes the chat
                  'shell/rrhk_crt_shader.inc', 'shell/rrhk_crts.inc')   # rrhk_video.c: the CRT looks' GPU pass (D35)
# The adapter file of each machine on the kit, below native/hostkit: the profile's `host_adapter` (the Master
# System and the Game Gear share one; an adapter an engine's own platform file includes, `.inc`, is staged but
# not compiled by itself). A new machine adds no line here.
ADAPTERS = {profile.id: profile.host_adapter for profile in all_profiles() if profile.host_adapter}
# A piece several adapters include and that no build lists by itself: staged beside the adapter that includes it.
ADAPTER_PIECES = ('adapters/rrhk_sprite_option.inc',)


def sources(family: str) -> list[str]:
    """The kit's C files of one machine, as the project-relative paths a build lists."""
    return ['hostkit/' + name for name in (*SHELL, ADAPTERS[family]) if name.endswith('.c')]


def adapter_includes(family: str) -> list[str]:
    """The shared adapter pieces the machine's adapter includes that are staged with it (ADAPTER_PIECES, below native/hostkit)."""
    adapter = (ASSETS / 'native/hostkit' / ADAPTERS[family]).read_text(encoding='utf-8')
    return [name for name in ADAPTER_PIECES if f'#include "hostkit/{name}"' in adapter]


def stage(project: Path, family: str) -> list[str]:
    """Copy the kit's headers, shell and the machine's adapter into `project/hostkit`; returns the C files to compile."""
    for name in (*HEADERS, *SHELL, *SHELL_INCLUDED, ADAPTERS[family], *adapter_includes(family)):
        target = project / 'hostkit' / name
        data = (ASSETS / 'native/hostkit' / name).read_bytes()
        if target.is_file() and target.read_bytes() == data:
            continue  # keep the timestamp: an unchanged file rebuilds nothing
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return sources(family)
