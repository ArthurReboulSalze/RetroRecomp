"""NES cartridge profile, kept separate from the Sega and Game Boy engines."""
from __future__ import annotations

from pathlib import Path

from . import Capabilities, Cpu, OptionKey, SystemProfile


class NesProfile(SystemProfile):
    id = "nes"
    name = "Nintendo NES"
    extensions = (".nes",)
    export_folder = "Nintendo NES"
    video_modes = ("ntsc", "pal")
    cpus = (Cpu("6502", "main", "cycles"),)
    quick_state_family = "nes"
    capabilities = Capabilities(guns=("zapper",), battery=True)
    feedback_kinds = frozenset({3, 4})
    option_keys = (OptionKey("nes_advanced_scan"),)

    def read_rom(self, path: Path):
        from ..nes import read_nes_rom
        return read_nes_rom(path)

    def default_video_mode(self, path: Path) -> str:
        value = self.read_rom(path).video_standard
        return 'ntsc' if value == 'multi' else value

    def convert(self, path: Path, **options) -> Path:
        from ..nes import convert_nes
        return convert_nes(path, **options)


NES = NesProfile()
