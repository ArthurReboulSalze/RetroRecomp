"""NES cartridge profile, kept separate from the Sega and Game Boy engines."""
from __future__ import annotations

from pathlib import Path

from . import Capabilities, Cpu, OptionKey, SystemProfile
from .specs import (CARTRIDGE_BOUNDS, Catalogues, Identify, InputLayout, LibraryLayout, PathSpec, ReportShape,
                    SharedKnowledge)


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
    path_spec = PathSpec(order=3, sections=(("mos6502", "nes"),), source_bounds=(("rom", CARTRIDGE_BOUNDS),),
                         required_sources=("rom",))
    report_shape = ReportShape("nes", "host_audio")
    catalogues = Catalogues(libretro="libretro-thumbnails/Nintendo_-_Nintendo_Entertainment_System",
                            screenscraper=3, thegamesdb=7, wikidata=("Q172742",), cover_references=True)
    library_layout = LibraryLayout(folder="nes", summary_glob="*/*/cycle-seeds.trace", identity="grandfolder")
    input_layout = InputLayout(("a", "b"), (), "select", 180, script_format="nes", script_suffix=".input")
    shared_knowledge = SharedKnowledge("stable", site_builder=True)
    host_adapter = "adapters/rrhk_nes.c"
    # The iNES signature wins over every other header in a headerless dump.
    identify = Identify(content_order=1)

    def identify_content(self, data: bytes):
        return self if data.startswith(b"NES\x1a") else None

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
