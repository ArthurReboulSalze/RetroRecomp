"""The newest converter version an export is compatible with (Arthur, 20 Nov 2026).

A release that changes only the converter (its window, its tools) leaves an export as it is: its role stamps (game,
host and build, `compilation_inputs.role_stamps`, the inputs the upgrade logic compares through the receipt's game and
host parts) are those of the running converter, so nothing would be rebuilt. The library then shows that export as
compatible with the running version (« Converti avec 1.9.0 · compatible 1.9.1 »).

The stamps an export was made with are not in its report (the receipt keeps only hashes of whole request parts), so
each release records its own role stamps, per console, in `assets/release-stamps.json` (tools/release_stamps.py, at
release time). An export whose release is recorded there with the running converter's stamps for its console is
compatible; one whose release is not recorded, or whose stamps differ in any role, is not: it gets upgraded or
reconverted as today and then carries the new version itself.

Only the library's row is stamped (`Game.compatible`). The conversion report keeps the version it was made with, and
the game keeps showing that version (RR_RECOMP_VERSION): no file of the export is written, no stamp moves.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from . import __version__
from .paths import ASSETS

RESOURCE = 'assets/release-stamps.json'
SCHEMA = 1
ROLES = ('game', 'host', 'build')
KEEP_RELEASES = 12              # the oldest entries are dropped when a release adds its own
# Rows whose export cannot be vouched for: gone, not a file the converter can read, or changed since its receipt.
UNVOUCHED = frozenset(('missing', 'unverified', 'changed'))


def load(path: Path | None = None) -> dict:
    """{version: {console: {'game', 'host', 'build'}}}; {} for a missing or unknown file (nothing is then compatible)."""
    try:
        data = json.loads((Path(path) if path is not None else ASSETS / RESOURCE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get('schema') != SCHEMA or not isinstance(data.get('releases'), dict):
        return {}
    return {version: consoles for version, consoles in data['releases'].items()
            if isinstance(version, str) and isinstance(consoles, dict)}


@lru_cache(maxsize=None)
def _table() -> dict:
    return load()


@lru_cache(maxsize=None)
def running_stamps(system: str) -> tuple:
    """The running converter's role stamps for one console, in ROLES order."""
    from .compilation_inputs import role_stamps
    stamps = role_stamps(system)
    return tuple(stamps.get(role, '') for role in ROLES)


def compatible_version(version: str, system: str, table: dict | None = None, stamps=running_stamps,
                       running: str = __version__) -> str:
    """`running` when an export made by release `version` for `system` would be left as it is by the running converter
    (every role stamp recorded for that release equals the running one); '' otherwise, and for an export of the running
    version itself."""
    if not version or version == running:
        return ''
    recorded = (table if table is not None else _table()).get(version, {}).get(system)
    if not isinstance(recorded, dict):
        return ''
    try:
        now = stamps(system)
    except (OSError, ValueError, KeyError):
        return ''
    return running if all(recorded.get(role) == value and value for role, value in zip(ROLES, now)) else ''


def update(inventory, table: dict | None = None, stamps=running_stamps, running: str = __version__) -> int:
    """Stamp every row of the library with its compatible version (or clear it); the number of rows changed. The caller
    saves the library."""
    changed = 0
    for game in inventory.snapshot():
        value = '' if game.status in UNVOUCHED else compatible_version(game.version, game.system, table, stamps, running)
        if game.compatible != value:
            game.compatible = value
            changed += 1
    return changed


def record(path: Path, version: str, consoles: dict) -> dict:
    """The table with `version`'s stamps ({console: {role: stamp}}) added or replaced, the oldest releases dropped."""
    releases = load(path)
    releases.pop(version, None)
    releases[version] = consoles
    kept = dict(list(releases.items())[-KEEP_RELEASES:])
    return {'schema': SCHEMA, 'releases': kept}
