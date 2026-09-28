"""NES cartridge profile, kept separate from the Sega and Game Boy engines."""
from __future__ import annotations

from pathlib import Path

from . import SystemProfile


class NesProfile(SystemProfile):
    id = "nes"
    name = "Nintendo NES"
    extensions = (".nes",)
    export_folder = "Nintendo NES"
    video_modes = ("ntsc",)

    def read_rom(self, path: Path):
        from ..nes import read_nes_rom
        return read_nes_rom(path)

    def default_video_mode(self, path: Path) -> str:
        return self.read_rom(path).video_standard

    def convert(self, path: Path, **options) -> Path:
        from ..nes import convert_nes
        return convert_nes(path, **options)


NES = NesProfile()
