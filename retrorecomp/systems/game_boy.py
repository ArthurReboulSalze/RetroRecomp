"""Original monochrome Game Boy cartridge profile."""
from __future__ import annotations

from pathlib import Path

from . import SystemProfile


class GameBoyProfile(SystemProfile):
    id = "gb"
    name = "Game Boy"
    extensions = (".gb",)
    export_folder = "Game Boy"
    video_modes = ("dmg",)

    def read_rom(self, path: Path):
        from ..gameboy import read_game_boy_rom
        return read_game_boy_rom(path)

    def default_video_mode(self, path: Path) -> str:
        return "dmg"

    def convert(self, path: Path, **options) -> Path:
        from ..gameboy import convert_game_boy
        return convert_game_boy(path, **options)


GAME_BOY = GameBoyProfile()
