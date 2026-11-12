"""Game Boy Advance profile (experimental, opened in 1.7.0: see docs/GAME_BOY_ADVANCE.md).

Route A: the pinned engine `mstan/gbarecomp` (PolyForm Noncommercial, with the author's permission) and the player's own BIOS.
The machine is listed when the installation carries the converter's native files (`available()`); a `.gba` file is refused as
an unknown console only when those files are missing. A converted game holds code derived from the player's BIOS and stays private.
"""
from __future__ import annotations

from pathlib import Path

from . import Capabilities, ConsoleMismatchError, Cpu, OptionKey, SystemProfile, UnsupportedConsoleError
from .specs import Catalogues, Identify, InputLayout, LibraryLayout, PathSpec, ReportShape, SharedKnowledge

# The CPU shape of the paths (docs/GAME_BOY_ADVANCE.md, "Paths"): function roots are `phys` entries, a ROM offset
# whose low bit says Thumb (an ARM root is word aligned, so the bit is free); IWRAM and EWRAM routines copied from
# the cartridge at run time are `span` rows (RAM address, ROM offset, length). Both are shapes the schema already
# has, so no shared module moves. The conversion (gba_analysis.py) records only those two kinds, read from the engine's miss
# proposals and the IWRAM image of a run; no jump-table or dispatch-target path is kept. They are also what the machine shares
# (gba_knowledge.py: numbers about one exact cartridge, an empty layout, an ARM root a multiple of 4).
_IWRAM = (0x03000000, 0x03008000)
_EWRAM = (0x02000000, 0x02040000)


class GameBoyAdvanceProfile(SystemProfile):
    id = 'gba'
    name = 'Game Boy Advance'
    extensions = ('.gba',)
    # A cartridge is at most 32 MiB; a ZIP may hold one (the shared reader of cartridges in ZIPs reads this table).
    archived_rom_limits = (('.gba', 32 * 1024 * 1024),)
    export_folder = 'Game Boy Advance'
    video_modes = ('agb',)
    status = 'experimental'
    # Counts interpreted ARM and Thumb instructions, in one unit; the save chips and the RTC are not processors.
    cpus = (Cpu('arm7tdmi', 'main', 'instructions'),)
    media_kinds = ('cartridge',)
    # The player's own system ROM (BIOS), hash-checked; the exported game holds code derived from it and stays private.
    firmware = ('bios',)
    quick_state_family = 'gba'
    host_adapter = "adapters/rrhk_gba.c"
    capabilities = Capabilities(battery=True)
    # Witnessed on a Debian 13 PC on 6 November 2026 (six cartridges, docs/GAME_BOY_ADVANCE.md); the player there is not played.
    linux = 'witnessed'
    feedback_kinds = frozenset({21})
    default_frames = 3600
    quick_frames = 1800
    fallback_display = 'opcodes'
    option_keys = (OptionKey('gba_bios', signature=False, kind='path', label='gba_bios'),)
    path_spec = PathSpec(order=11, sections=(('arm7tdmi', 'gba'),),
                         source_bounds=(('rom', (0xC0, 32 * 1024 * 1024)),),
                         required_sources=('rom',), hashed_sources=('rom',),
                         shapes=(('arm7tdmi', 'gba', dict(roles=('rom',), caps={'phys': 262144, 'span': 4096},
                                                          entry_align=1, entry_min=0, entry_tail=1,
                                                          windows=(_EWRAM, _IWRAM), contained=True, length=(2, 16),
                                                          length_align=2, offset_align=2, address_align=1,
                                                          span_max=262144)),))
    report_shape = ReportShape('gba_conversion', 'gba_checks')
    # The experimental tier of the base, schema 3 only, withdrawable in one line (path_profiles.EXPERIMENTAL_SHARED). Rows other players found are used as
    # hints and guide the first pass; the quick check from shared paths is declined because RAM code does not travel (a first conversion must run its own passes).
    shared_knowledge = SharedKnowledge('experimental', withdrawable=True, quick_check_from_shared=False, module='gba_knowledge')
    # The ScreenScraper, TheGamesDB and Wikidata numbers of the platform are added when the box-art stage verifies them.
    catalogues = Catalogues(libretro='libretro-thumbnails/Nintendo_-_Game_Boy_Advance')
    # The player's own paths live in library/gba/<sha256>/<engine revision>/paths.json; the record a passed conversion shares is
    # library/gba/<sha256>/compilation.json (gba_knowledge.library_record). No per-ROM summary is listed, so there is no summary_glob:
    # the memory window has nothing to list (declined in tests/test_machine_registry.py).
    library_layout = LibraryLayout(folder='gba')
    # The pad of the Game Boy plus L and R: the random routes use the Game Boy script writer until they need the shoulders.
    input_layout = InputLayout(('a', 'b'), (), 'select', 180, script_format='gameboy')
    # A cartridge is claimed by its extension, or by a ZIP that holds exactly one: before the ZIP is opened.
    identify = Identify(path_order=50)

    def available(self) -> bool:
        from ..gba import converter_available
        return converter_available()

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        if suffix == '.zip':
            from ..gba import zip_holds_cartridge
            if not zip_holds_cartridge(path):
                return None
        elif suffix not in self.extensions:
            return None
        if not self.available():
            raise UnsupportedConsoleError(
                'The experimental Game Boy Advance profile is unavailable in this installation.')
        if selected_system and selected_system != self.id:
            raise ConsoleMismatchError('Detected Game Boy Advance; choose Automatic or Game Boy Advance.', self.id)
        return self

    def read_rom(self, path: Path):
        from ..gba import read_rom
        return read_rom(path)

    def default_video_mode(self, path: Path) -> str:
        return 'agb'

    def convert(self, path: Path, **options) -> Path:
        from ..gba_conversion import convert
        return convert(path, **options)

    def request_identity(self, item, options: dict, settings: dict) -> None:
        from ..gba import bios_identity
        settings['bios'] = bios_identity(options.get('gba_bios'))
        settings.pop('gba_bios', None)


GAME_BOY_ADVANCE = GameBoyAdvanceProfile()
