"""Original monochrome Game Boy cartridge profile."""
from __future__ import annotations

from pathlib import Path

from . import Capabilities, Cpu, OptionKey, SystemProfile
from .specs import (CARTRIDGE_BOUNDS, Catalogues, Identify, InputLayout, LibraryLayout, PathSpec, ReportShape,
                    SharedKnowledge)


class GameBoyProfile(SystemProfile):
    id = "gb"
    name = "Game Boy"
    extensions = (".gb",)
    export_folder = "Game Boy"
    video_modes = ("dmg",)
    cpus = (Cpu("sm83", "main", "cycles"),)
    quick_state_family = "gb"
    capabilities = Capabilities(battery=True)
    feedback_kinds = frozenset({2})
    option_keys = (OptionKey("gb_deep_validation", label="gb_deep_validation", hint="tip_gb_deep_validation",
                             default=True),
                   OptionKey("gb_parallel_games", signature=False, kind="count", default=1))
    parallel_games_option = "gb_parallel_games"
    options_tab = "options_game_boy"
    path_spec = PathSpec(order=2, sections=(("sm83", "gb"),), source_bounds=(("rom", CARTRIDGE_BOUNDS),),
                         required_sources=("rom",))
    report_shape = ReportShape("gameboy", "generated_build")
    catalogues = Catalogues(libretro="libretro-thumbnails/Nintendo_-_Game_Boy", screenscraper=9, thegamesdb=4,
                            wikidata=("Q186437",), cover_references=True)
    library_layout = LibraryLayout(folder="gb", summary_glob="*/trace.json", companion="entries.trace")
    input_layout = InputLayout(("a", "b"), (), "select", 180, script_format="gameboy")
    shared_knowledge = SharedKnowledge("stable", site_builder=True)
    # A headerless dump is a Game Boy cartridge when its header checksum, declared size and title agree.
    identify = Identify(content_order=5)

    def identify_content(self, data: bytes):
        if len(data) >= 0x8000 and len(data) % 0x4000 == 0:
            checksum = 0
            for value in data[0x134:0x14d]:
                checksum = (checksum - value - 1) & 0xff
            title = data[0x134:0x143].split(b'\0', 1)[0]
            size_code = data[0x148]
            declared_size = (0x8000 << size_code) if size_code <= 8 else {
                0x52: 72 * 0x4000, 0x53: 80 * 0x4000,
                0x54: 96 * 0x4000}.get(size_code)
            if (checksum == data[0x14d] and declared_size == len(data)
                    and title and all(32 <= value < 127 for value in title)):
                return self
        return None

    def read_rom(self, path: Path):
        from ..gameboy import read_game_boy_rom
        return read_game_boy_rom(path)

    def default_video_mode(self, path: Path) -> str:
        return "dmg"

    def convert(self, path: Path, **options) -> Path:
        from ..gameboy import convert_game_boy
        return convert_game_boy(path, **options)


GAME_BOY = GameBoyProfile()
