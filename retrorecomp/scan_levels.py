"""Scan levels: how long each console's automatic discovery runs.

Every console profile converts with the same four levels. *Standard* is what
each converter ran before levels existed; *quick* trims it for fast iteration;
*extended* and *thorough* add reproducible pseudo-random play routes (see
``random_routes``) and, where a console already had authored replays, keep
them. The per-console budgets live here so that the converters, the options
panel, the command line and the reports agree on one vocabulary.

Preferences keep one entry per console::

    {"md": {"level": "extended", "passes": 2, "frames": null}, ...}

``passes`` and ``frames`` override the shared defaults when set; ``null`` or a
missing key keeps the shared value. Nothing here patches a game: a level only
chooses which host-input scenarios run and for how long.
"""
from __future__ import annotations

from dataclasses import dataclass

from .systems import ALL_PROFILES, system_ids

LEVELS = ('quick', 'standard', 'extended', 'thorough')
# The consoles and their scenario lengths come from the profiles.
CONSOLES = system_ids()
DEFAULT_PASSES = 3
DEFAULT_FRAMES = {profile.id: profile.default_frames for profile in ALL_PROFILES}
# A quick scan caps the scenario length and runs a single pass.
QUICK_FRAMES = {profile.id: profile.quick_frames for profile in ALL_PROFILES}
LONG_ROUTE_FRAMES = 18000
# Pseudo-random routes added on top of the standard scenarios.
LONG_ROUTES = {'quick': 0, 'standard': 0, 'extended': 1, 'thorough': 2}


@dataclass(frozen=True)
class ScanPlan:
    console: str
    level: str
    passes: int
    frames: int

    @property
    def long_routes(self) -> int:
        return LONG_ROUTES[self.level]

    def as_dict(self) -> dict:
        return {'console': self.console, 'level': self.level, 'passes': self.passes,
                'frames': self.frames, 'long_routes': self.long_routes}


def normalize(raw) -> dict:
    """Keep only well-formed per-console entries; everything else is dropped."""
    settings = {}
    if not isinstance(raw, dict):
        return settings
    for console, entry in raw.items():
        if console not in CONSOLES or not isinstance(entry, dict):
            continue
        clean = {}
        level = entry.get('level')
        if level in LEVELS:
            clean['level'] = level
        passes = entry.get('passes')
        if isinstance(passes, int) and not isinstance(passes, bool) and 1 <= passes <= 10:
            clean['passes'] = passes
        frames = entry.get('frames')
        if isinstance(frames, int) and not isinstance(frames, bool) and 1 <= frames <= 10000:
            clean['frames'] = frames
        if clean:
            settings[console] = clean
    return settings


def legacy_level(console: str, *, md_advanced_scan=False, nes_advanced_scan=False) -> str:
    """The level the former per-console switches meant."""
    if console in ('md', 'snes') and md_advanced_scan:
        return 'thorough'
    if console == 'nes' and nes_advanced_scan:
        return 'extended'
    return 'standard'


def plan_for(console: str, console_scan=None, *, passes: int = DEFAULT_PASSES, frames=None,
             level: str | None = None, md_advanced_scan=False, nes_advanced_scan=False) -> ScanPlan:
    """Resolve the level, pass limit and frame budget one console converts with.

    ``level`` (a command-line override) wins over the saved per-console entry,
    which wins over the former switches. A quick scan always runs one pass on a
    capped scenario length."""
    if console not in CONSOLES:
        raise ValueError(f'Unknown console for scan levels: {console!r}')
    entry = normalize(console_scan).get(console, {})
    chosen = level or entry.get('level') or legacy_level(
        console, md_advanced_scan=md_advanced_scan, nes_advanced_scan=nes_advanced_scan)
    if chosen not in LEVELS:
        raise ValueError(f'Unknown scan level: {chosen!r}')
    chosen_passes = entry.get('passes') or passes
    chosen_frames = entry.get('frames') or frames or DEFAULT_FRAMES[console]
    if chosen == 'quick':
        chosen_passes = 1
        chosen_frames = min(chosen_frames, QUICK_FRAMES[console])
    return ScanPlan(console, chosen, int(chosen_passes), int(chosen_frames))


def console16_budget(level: str, frames: int) -> dict:
    """Mega Drive / Super Nintendo: attract length, authored replays, routes."""
    if level in ('quick', 'standard'):
        return {'advanced': False, 'demo_frames': frames, 'route_count': 0, 'route_frames': LONG_ROUTE_FRAMES}
    demo = 12000 if level == 'extended' else 24000
    return {'advanced': True, 'demo_frames': max(frames, demo), 'route_count': LONG_ROUTES[level],
            'route_frames': LONG_ROUTE_FRAMES}


def x68000_budget(level: str) -> dict:
    """Sharp X68000: mouse/keyboard exploration and long routes. Thorough keeps
    the three 36,000-frame routes that qualified the library."""
    if level == 'quick':
        return {'exploration': False, 'long_count': 0, 'long_frames': LONG_ROUTE_FRAMES}
    if level == 'standard':
        return {'exploration': True, 'long_count': 0, 'long_frames': LONG_ROUTE_FRAMES}
    if level == 'extended':
        return {'exploration': True, 'long_count': 1, 'long_frames': LONG_ROUTE_FRAMES}
    return {'exploration': True, 'long_count': 3, 'long_frames': 36000}


def nes_budget(level: str) -> dict:
    """NES: the authored menu/dialogue/varied replays arrive with extended;
    thorough adds the pseudo-random routes. Quick keeps boot and one play run."""
    return {'advanced': level in ('extended', 'thorough'), 'play_left': level != 'quick',
            'route_count': LONG_ROUTES[level] if level == 'thorough' else 0,
            'route_frames': LONG_ROUTE_FRAMES}


def gameboy_budget(level: str) -> dict:
    """Game Boy: quick skips the varied replay and the deep CPU comparison."""
    return {'varied': level != 'quick', 'deep_allowed': level != 'quick',
            'route_count': LONG_ROUTES[level], 'route_frames': LONG_ROUTE_FRAMES}


def sega_budget(level: str) -> dict:
    """Master System / Game Gear: demo and play, plus pseudo-random routes."""
    return {'route_count': LONG_ROUTES[level], 'route_frames': LONG_ROUTE_FRAMES}


def cps1_budget(level: str) -> dict:
    """CPS-1: attract and a credited play route (quick keeps the play route
    only); extended and thorough add credited pseudo-random routes."""
    return {'attract': level != 'quick', 'route_count': LONG_ROUTES[level],
            'route_frames': LONG_ROUTE_FRAMES}


def neogeo_budget(level: str) -> dict:
    """Neo Geo: the qualification routes are the minimum (quick equals
    standard); extended and thorough add credited pseudo-random routes."""
    return {'route_count': LONG_ROUTES[level], 'route_frames': LONG_ROUTE_FRAMES}
