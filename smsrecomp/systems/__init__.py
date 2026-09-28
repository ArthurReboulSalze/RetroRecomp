"""Console profiles used by identification, batch conversion and output paths.

Each future console registers its own reader, converter and timing vocabulary.
No timing rule or cartridge format is shared implicitly between systems.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class SystemProfile(ABC):
    id: str
    name: str
    extensions: tuple[str, ...]
    export_folder: str
    video_modes: tuple[str, ...]

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

PROFILES: tuple[SystemProfile, ...] = (MASTER_SYSTEM,)


def get_profile(system_id: str) -> SystemProfile:
    for profile in PROFILES:
        if profile.id == system_id:
            return profile
    raise ValueError(f"Unsupported console profile: {system_id}")


def profile_for_path(path: Path) -> SystemProfile:
    matches = [profile for profile in PROFILES if path.suffix.casefold() in profile.extensions]
    if len(matches) != 1:
        raise ValueError(f"No supported console profile for {path.suffix or 'this file'}")
    return matches[0]
