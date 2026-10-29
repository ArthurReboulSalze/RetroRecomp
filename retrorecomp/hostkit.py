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

HEADERS = ('hostkit.h', 'hostkit_internal.h')
SHELL = tuple(f'shell/rrhk_{name}.c' for name in
              ('audio', 'events', 'input', 'main', 'menu', 'options', 'pointer', 'ring', 'timing', 'video'))
ADAPTERS = {'md': 'adapters/rrhk_md.c', 'snes': 'adapters/rrhk_snes.c',
            'ng': 'adapters/rrhk_ng.c', 'cps1': 'adapters/rrhk_cps1.c', 'nes': 'adapters/rrhk_nes.c',
            'sms': 'adapters/rrhk_sms.c', 'gg': 'adapters/rrhk_sms.c',
            # An adapter that is included by the platform file of the runtime it belongs to (one translation unit)
            # is staged but not compiled by itself.
            'gb': 'adapters/rrhk_gb.inc'}


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
