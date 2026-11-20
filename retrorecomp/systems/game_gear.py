"""Game Gear cartridge profile; its LCD and controls are not SMS defaults."""
from __future__ import annotations

from pathlib import Path

from . import Cpu, SimulationSource, SystemProfile
from ..z80_chain import SEGA_MAPPER
from .master_system import refine_by_header
from .specs import (CARTRIDGE_BOUNDS, Catalogues, InputLayout, LibraryLayout, PathSpec, ReportShape,
                    SharedKnowledge)


class GameGearProfile(SystemProfile):
    id = "gg"
    netplay_session = True
    netplay_portable = False
    netplay_seats = 1
    netplay_shared_only = True
    netplay_link_seats = 2     # the Gear-to-Gear cable plays in a session: 2 seats on one PC with equal digests, Super Columns in its Versus mode (docs/GAME_GEAR.md)
    # The per-game generated files of the simulation identity (retrorecomp/simulation_identity.py), below the build project.
    # As the Master System (one engine).
    simulation_sources = (SimulationSource('generated/*.c'),
                          SimulationSource('generated/*.h'),
                          SimulationSource('runtime_glue.c'),
                          SimulationSource('sms_clocks.h'),
                          SimulationSource('game.toml'),
                          SimulationSource('embedded_rom.c', keep='const int sms_light_phaser\\w* = -?\\d+;'),)
    # The third-party components compiled into its games (retrorecomp/notices.py); the player shell's are added.
    notice_files = ('licenses/smsggrecomp.md', 'licenses/z80-recomp-core.md', 'licenses/superzazu-z80.md')
    name = "Game Gear"
    extensions = (".gg",)
    archived_rom_limits = (('.gg', 4 * 1024 * 1024 + 512),)
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
    host_adapter = "adapters/rrhk_sms.c"
    # delivery_evidence (G5 and G8, retrorecomp/sega_evidence.py); the banked Z80 chain (retrorecomp/z80_chain.py, cpu.py)
    stamp_groups = ('conversion_gates', 'z80_main')
    z80_machine = SEGA_MAPPER   # the same mapper and Z80 timing as the Master System

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
