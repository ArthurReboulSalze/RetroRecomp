"""Conversion time estimates for the converter window: how long a game, a level or a queue usually takes.

The figures come from one reviewed table, assets/conversion-times.json: the time one game took on the reference PC,
per machine and scan level, measured from the conversion reports (tools/conversion_times.py) and written by hand.
A level a machine was not measured at is derived from its standard time by the table's level factors, the same for
every machine. The first use of the converter (the build tools, the shared pieces, a machine's first engine) is
stated apart, with only what was measured counted in seconds; downloads depend on the player's connection and are
named, never timed.

Everything here is an estimate on the reference PC, never a promise, and the window says so wherever it shows one.
Nothing here is read by a conversion: it changes no game, no report and no stamp.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import json
import math
from pathlib import Path

from .paths import ASSETS

RESOURCE = 'assets/conversion-times.json'
FORMAT = 1
LEVELS = ('quick', 'standard', 'extended', 'thorough')
MAX_BYTES = 256 * 1024


@dataclass(frozen=True)
class GameTime:
    """Seconds one game usually takes: first quartile, median, third quartile, and the longest seen. `measured` is
    False when the level was derived from the machine's standard time."""
    low: float
    typical: float
    high: float
    longest: float
    measured: bool = True


@dataclass(frozen=True)
class QueueEstimate:
    """A queue's estimate: `typical` and `high` seconds for the games the table knows (`games`), `unknown` games without
    one, and the first use apart: `first_build` seconds measured, `first_download` when something must be downloaded,
    `new_machines` converted here for the first time."""
    games: int = 0
    unknown: int = 0
    typical: float = 0.0
    high: float = 0.0
    longest: float = 0.0
    first_build: float = 0.0
    first_download: bool = False
    new_machines: tuple = field(default_factory=tuple)
    paths: bool = False      # a queued machine shares paths (paths_effect)


def _cell(value) -> bool:
    if not isinstance(value, dict):
        return False
    seconds = value.get('seconds')
    return (isinstance(seconds, list) and len(seconds) == 3
            and all(isinstance(x, (int, float)) and x >= 0 for x in seconds)
            and seconds[0] <= seconds[1] <= seconds[2]
            and isinstance(value.get('longest'), (int, float)) and value['longest'] >= seconds[2])


def validate(data) -> dict:
    """The table when it is well formed; ValueError otherwise."""
    if not isinstance(data, dict) or data.get('format') != FORMAT:
        raise ValueError('conversion times: unknown format')
    reference = data.get('reference')
    if not isinstance(reference, dict) or not isinstance(reference.get('label'), str) or not reference['label']:
        raise ValueError('conversion times: no reference PC')
    factors = data.get('level_factors')
    if not isinstance(factors, dict) or set(factors) != set(LEVELS) or factors.get('standard') != 1.0 or not all(
            isinstance(value, (int, float)) and value > 0 for value in factors.values()):
        raise ValueError('conversion times: level factors')
    machines = data.get('machines')
    if not isinstance(machines, dict):
        raise ValueError('conversion times: machines')
    for machine, levels in machines.items():
        if not isinstance(levels, dict) or 'standard' not in levels or not set(levels) <= set(LEVELS) or not all(
                _cell(cell) for cell in levels.values()):
            raise ValueError(f'conversion times: {machine}')
    first = data.get('first_use')
    if not isinstance(first, dict) or not isinstance(first.get('shared_build_seconds'), (int, float)) or not all(
            isinstance(entry, dict) and isinstance(entry.get('seconds'), (int, float))
            for entry in (first.get('machines') or {}).values()):
        raise ValueError('conversion times: first use')
    return data


def load(path: Path | None = None) -> dict:
    path = Path(path) if path is not None else ASSETS / RESOURCE
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('conversion times: file too large')
    return validate(json.loads(path.read_text(encoding='utf-8')))


@lru_cache(maxsize=1)
def table() -> dict | None:
    """The bundled table, or None when it cannot be read (the window then shows no estimate)."""
    try:
        return load()
    except (OSError, ValueError):
        return None


def reference_label(data: dict | None = None) -> str:
    data = table() if data is None else data
    return data['reference']['label'] if data else ''


def game_time(system: str, level: str = 'standard', data: dict | None = None) -> GameTime | None:
    """How long one game of a machine usually takes at a level, or None for a machine the table does not know."""
    data = table() if data is None else data
    if not data:
        return None
    levels = data['machines'].get(system)
    if not levels:
        return None
    level = level if level in LEVELS else 'standard'
    cell = levels.get(level)
    if cell is not None:
        return GameTime(*cell['seconds'], cell['longest'], True)
    factor = data['level_factors'][level]
    base = levels['standard']
    low, typical, high = (value * factor for value in base['seconds'])
    return GameTime(low, typical, high, base['longest'] * factor, False)


def batch_seconds(games, jobs: int, per_console: dict | None = None) -> float:
    """Seconds a batch of (machine, seconds) games takes with `jobs` games at once (and a lower number for some
    machines, as queue_state.job_groups cuts the queue): the work shared by the workers, never shorter than its
    longest game nor than a machine held to fewer workers."""
    games = list(games)
    if not games:
        return 0.0
    jobs = max(1, int(jobs))
    estimate = max(sum(seconds for _, seconds in games) / min(jobs, len(games)), max(seconds for _, seconds in games))
    for console, value in (per_console or {}).items():
        own = max(1, min(int(value), jobs))
        mine = [seconds for system, seconds in games if system == console]
        if mine and own < jobs:
            estimate = max(estimate, sum(mine) / min(own, len(mine)))
    return estimate


def first_use(*, tools_missing=False, shared_missing=False, new_machines=(), data: dict | None = None) -> tuple:
    """(seconds of building measured, whether something is downloaded) for a first use."""
    data = table() if data is None else data
    if not data:
        return 0.0, bool(tools_missing or shared_missing or new_machines)
    first = data['first_use']
    seconds = float(first['shared_build_seconds']) if (tools_missing or shared_missing) else 0.0
    machines = first.get('machines') or {}
    seconds += sum(float(machines[machine]['seconds']) for machine in new_machines if machine in machines)
    return seconds, bool(tools_missing or shared_missing or new_machines)


def queue_estimate(entries, *, jobs: int, per_console: dict | None = None, tools_missing=False, shared_missing=False,
                   converted_machines=None, data: dict | None = None) -> QueueEstimate:
    """The estimate of a queue of (machine, level) entries. `converted_machines` are the machines this PC has
    converted before (None: unknown, no machine counted as new)."""
    data = table() if data is None else data
    typical, high, unknown, longest = [], [], 0, 0.0
    for system, level in entries:
        found = game_time(system, level, data) if data else None
        if found is None:
            unknown += 1
            continue
        typical.append((system, found.typical))
        high.append((system, found.high))
        longest = max(longest, found.longest)
    systems = []
    for system, _ in entries:
        if system not in systems:
            systems.append(system)
    new = tuple(system for system in systems if converted_machines is not None and system not in converted_machines)
    build, download = first_use(tools_missing=tools_missing, shared_missing=shared_missing, new_machines=new, data=data)
    return QueueEstimate(games=len(typical), unknown=unknown, typical=batch_seconds(typical, jobs, per_console),
                         high=batch_seconds(high, jobs, per_console), longest=longest, first_build=build,
                         first_download=download, new_machines=new,
                         paths=any(paths_effect(system) for system in systems))


def paths_effect(system: str) -> str | None:
    """What other players' paths do to a machine's conversion, from its profile (never a time promised):
    'shorter' when the machine shares paths and a conversion whose paths were received at its level runs a quick check
    instead of its discovery (batch.py, `quick_check_from_shared`); 'native' when it shares them but still runs its full
    discovery (the paths add native code: one pass with or without them on the Amiga, the Atari ST and the PlayStation,
    docs/COMPILATION_LIBRARY.md); None when it does not share paths."""
    from .systems import ALL_PROFILES
    profile = next((profile for profile in ALL_PROFILES if profile.id == system), None)
    shared = getattr(profile, 'shared_knowledge', None)
    if shared is None:
        return None
    return 'shorter' if getattr(shared, 'quick_check_from_shared', True) else 'native'


# The display rounds generously: an order of magnitude per console, not a timing. Steps in minutes, by size.
STEPS = ((5, 1), (30, 5), (60, 10))
HOUR_STEP = 30


def step(minutes: float) -> int:
    return next((size for limit, size in STEPS if minutes < limit), HOUR_STEP)


def rounded_minutes(seconds: float, *, up: bool = False, down: bool = False) -> int:
    """Minutes for a display, on the step of their size (1 min under 5 min, 5 min under 30, 10 min under an hour,
    then half hours): to the nearest, or the step below or above for the bounds of a range. 0 means under a minute."""
    minutes = max(0.0, seconds) / 60
    size = step(minutes)
    if up:
        value = math.ceil(minutes / size - 1e-9) * size
        return max(value, 1) if seconds > 0 else 0
    value = (math.floor(minutes / size + 1e-9) if down else round(minutes / size)) * size
    return int(value)


def minutes_text(minutes: int, tr) -> str:
    if minutes <= 0:
        return tr('time_under_minute')
    if minutes < 60:
        return tr('time_minutes', minutes=minutes)
    hours, minutes = divmod(minutes, 60)
    return tr('time_hours', hours=hours, minutes=minutes) if minutes else tr('time_hours_only', hours=hours)


def duration_text(seconds: float, tr, *, up: bool = False, down: bool = False) -> str:
    """'under a minute', 'N min' or 'H h M min' in the interface language (`tr(key, **values)`), rounded generously."""
    return minutes_text(rounded_minutes(seconds, up=up, down=down), tr)


def span_text(low: float, high: float, tr) -> str:
    """A range in the interface language: 'A to B', or 'up to B' when the rounded bounds meet or the low one is under
    a minute."""
    top = rounded_minutes(high, up=True)
    bottom = rounded_minutes(min(low, high), down=True)
    if bottom <= 0 or bottom >= top:
        return tr('time_up_to', high=minutes_text(top, tr))
    return tr('time_range', low=minutes_text(bottom, tr), high=minutes_text(top, tr))


def elapsed_text(seconds: float) -> str:
    """A running clock: 'm:ss', or 'h:mm:ss' past an hour."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{hours}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes}:{seconds:02d}'
