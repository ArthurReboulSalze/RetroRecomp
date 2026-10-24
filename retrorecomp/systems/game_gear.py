"""Game Gear cartridge profile; its LCD and controls are not SMS defaults."""
from __future__ import annotations

from pathlib import Path

from . import SystemProfile


class GameGearProfile(SystemProfile):
    id = "gg"
    name = "Game Gear"
    extensions = (".gg",)
    export_folder = "Game Gear"
    # The original handheld uses the 262-line, ~3.58 MHz timing path.
    video_modes = ("ntsc",)

    def read_rom(self, path: Path):
        from ..core import read_game_gear_rom
        return read_game_gear_rom(path)

    def default_video_mode(self, path: Path) -> str:
        return "ntsc"

    def convert(self, path: Path, **options) -> Path:
        from ..core import convert
        return convert(path, **options)


GAME_GEAR = GameGearProfile()
