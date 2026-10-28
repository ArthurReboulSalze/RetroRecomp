"""Game Gear cartridge profile; its LCD and controls are not SMS defaults."""
from __future__ import annotations

from pathlib import Path

from . import Cpu, SystemProfile
from .master_system import refine_by_header
from .specs import (CARTRIDGE_BOUNDS, Catalogues, InputLayout, LibraryLayout, PathSpec, ReportShape,
                    SharedKnowledge)


class GameGearProfile(SystemProfile):
    id = "gg"
    name = "Game Gear"
    extensions = (".gg",)
    export_folder = "Game Gear"
    # The original handheld uses the 262-line, ~3.58 MHz timing path.
    video_modes = ("ntsc",)
    cpus = (Cpu("z80", "main", "cycles"),)
    quick_state_family = "gamestate"
    feedback_kinds = frozenset({1})
    converter_publishes = True
    options_tab = "options_game_gear"
    path_spec = PathSpec(order=1, sections=(("z80", "sms"),), source_bounds=(("rom", CARTRIDGE_BOUNDS),),
                         required_sources=("rom",))
    report_shape = ReportShape("core", "strict_checks")
    catalogues = Catalogues(libretro="libretro-thumbnails/Sega_-_Game_Gear", screenscraper=21, thegamesdb=20,
                            wikidata=("Q751719",), cover_references=True)
    library_layout = LibraryLayout(folder="gg", summary_glob="*/compilation.json", companion="observations.log")
    input_layout = InputLayout(("a", "b"), (), None, 240, script_format="sega")
    shared_knowledge = SharedKnowledge("stable", site_builder=True)

    def refine_match(self, path: Path, data: bytes | None):
        return refine_by_header(self, path, data)

    def read_rom(self, path: Path):
        from ..core import read_game_gear_rom
        return read_game_gear_rom(path)

    def default_video_mode(self, path: Path) -> str:
        return "ntsc"

    def convert(self, path: Path, **options) -> Path:
        from .master_system import convert_checked
        return convert_checked(self, path, **options)


GAME_GEAR = GameGearProfile()
