"""Game Boy Color cartridge profile: the second machine of the Game Boy engine (docs/GAME_BOY_COLOR.md).

The same SM83 and the same pinned recompiler as the original Game Boy (retrorecomp/gameboy.py takes a variant), started in the colour
hardware's model: double speed, the second video bank, the eight work-RAM banks, the colour palettes, HDMA. The Color gets its own profile as the
Game Gear has its own on the Master System's engine: its own evidence and gates, its own library and paths, its own settings. Cartridges whose
header says Color-only (flag C0) or Color-enhanced (flag 80) go here when the file is a .gbc, and Color-only ones also when they sit in a .gb or a
ZIP; the one Color-flagged cartridge a player keeps as a monochrome .gb stays with the Game Boy (Arthur, 21 November 2026).
"""
from __future__ import annotations

from pathlib import Path

from . import Capabilities, Cpu, OptionKey, SimulationSource, SystemProfile
from .game_boy import GAME_BOY
from .specs import (CARTRIDGE_BOUNDS, Catalogues, Identify, InputLayout, LibraryLayout, PathSpec, ReportShape,
                    SharedKnowledge)


class GameBoyColorProfile(SystemProfile):
    id = "gbc"
    status = "experimental"
    linux = "pending"
    # Multiplayer: the Game Boy's session and its link cable (GBC with GBC only; docs/GAME_BOY_COLOR.md). Set once the pair of Color consoles was proved
    # on one PC: tools/gameboy_link_selftest.py --model cgb (every pairing of normal and double speed, normal and fast serial clock) and the room's smoke test.
    netplay_seats = 1
    netplay_shared_only = True
    netplay_link_seats = 2
    netplay_session = True
    # The per-game generated files of the simulation identity (retrorecomp/simulation_identity.py): the original Game Boy's, one engine.
    simulation_sources = (SimulationSource('game.c'),
                          SimulationSource('game.h'),
                          SimulationSource('game_internal.h'),
                          SimulationSource('game_funcs_*.c'),
                          SimulationSource('game_dispatch_chunk_*.c'),
                          SimulationSource('game_main.c', drop=('datas/games/', 'gb_context_set_save_id')),)
    # The third-party components compiled into its games (retrorecomp/notices.py); the player shell's are added.
    notice_files = ('licenses/gb-recompiled.md', 'licenses/dear-imgui.md')
    name = "Game Boy Color"
    extensions = (".gbc",)
    archived_rom_limits = (('.gbc', 8 * 1024 * 1024),)
    export_folder = "Game Boy Color"
    video_modes = ("cgb",)
    cpus = (Cpu("sm83", "main", "cycles"),)
    quick_state_family = "gbc"
    host_adapter = "adapters/rrhk_gb.inc"
    capabilities = Capabilities(battery=True)
    stamp_groups = ('conversion_gates', 'gameboy')
    feedback_kinds = frozenset({2})          # RR_FB_GB: one record format, as the Game Gear shares the Master System's
    option_keys = (OptionKey("gbc_deep_validation", label="gb_deep_validation", hint="tip_gb_deep_validation",
                             default=True),
                   OptionKey("gbc_parallel_games", signature=False, kind="count", default=1))
    parallel_games_option = "gbc_parallel_games"
    path_spec = PathSpec(order=23, sections=(("sm83", "gbc"),), source_bounds=(("rom", CARTRIDGE_BOUNDS),),
                         required_sources=("rom",),
                         shapes=(("sm83", "gbc", dict(roles=("rom",), caps={"gb_offsets": 65536, "gb_rows": 65536},
                                                      unit=0x4000, pc_window=(0, 0x7fff))),))
    report_shape = ReportShape("gameboy", "generated_build")
    catalogues = Catalogues(libretro="libretro-thumbnails/Nintendo_-_Game_Boy_Color", screenscraper=10, thegamesdb=41,
                            igdb="gbc", wikidata=("Q203992",), cover_references=True)
    library_layout = LibraryLayout(folder="gbc", summary_glob="*/trace.json", companion="entries.trace")
    input_layout = InputLayout(("a", "b"), (), "select", 180, script_format="gameboy")
    shared_knowledge = None
    # A headerless dump is a Color cartridge when its header checksum, declared size and title agree and its flag says Color-only.
    identify = Identify(content_order=7)

    def identify_content(self, data: bytes):
        if len(data) >= 0x150 and data[0x143] == 0xC0 and GAME_BOY.header_matches(data):
            return self
        return None

    def read_rom(self, path: Path):
        from ..gameboy import COLOR, read_game_boy_rom
        return read_game_boy_rom(path, COLOR)

    def default_video_mode(self, path: Path) -> str:
        return "cgb"

    def convert(self, path: Path, **options) -> Path:
        from ..gameboy import COLOR, convert_game_boy
        options = {("gb_" + name[4:] if name.startswith("gbc_") else name): value for name, value in options.items()}
        return convert_game_boy(path, variant=COLOR, **options)


GAME_BOY_COLOR = GameBoyColorProfile()
