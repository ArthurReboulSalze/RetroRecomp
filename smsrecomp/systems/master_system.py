"""Master System cartridge profile; PAL/NTSC defaults are SMS-specific."""
from __future__ import annotations

from pathlib import Path
import re

from . import SystemProfile


class MasterSystemProfile(SystemProfile):
    id = "sms"
    name = "Master System"
    extensions = (".sms",)
    export_folder = "Master System"
    video_modes = ("ntsc", "pal")

    def read_rom(self, path: Path):
        from ..core import read_rom
        return read_rom(path)

    def default_video_mode(self, path: Path) -> str:
        # Dump headers identify export markets, not the host console clock.
        groups = re.findall(r"\(([^()]*)\)|\[([^\[\]]*)\]", path.stem)
        markets = {word.casefold() for pair in groups for group in pair
                   for word in re.split(r"\W+", group) if word}
        return "pal" if "europe" in markets and not markets.intersection(
            {"usa", "world", "japan"}) else "ntsc"

    def convert(self, path: Path, **options) -> Path:
        from ..core import convert
        return convert(path, **options)


MASTER_SYSTEM = MasterSystemProfile()
