"""Game Boy Advance profile (experimental: see docs/GAME_BOY_ADVANCE.md).

Stage 2 of the machine: the profile, the cartridge reader and the report writer exist, nothing converts. The machine
is a developer-only profile until it does (like the X68000 before its files shipped): the window and the batch do not
list it, and a `.gba` file says so instead of being called an unknown console.
"""
from __future__ import annotations

from pathlib import Path

from . import Capabilities, ConsoleMismatchError, Cpu, OptionKey, SystemProfile, UnsupportedConsoleError
from .specs import Catalogues, Identify, InputLayout, LibraryLayout, PathSpec, ReportShape

# The CPU shape of the paths (docs/GAME_BOY_ADVANCE.md, "Paths"): function roots are `phys` entries, a ROM offset
# whose low bit says Thumb (an ARM root is word aligned, so the bit is free); IWRAM and EWRAM routines copied from
# the cartridge at run time are `span` rows (RAM address, ROM offset, length). Both are shapes the schema already
# has, so no shared module moves. The jump-table and dispatch-target shapes come with the conversion.
_IWRAM = (0x03000000, 0x03008000)
_EWRAM = (0x02000000, 0x02040000)


class GameBoyAdvanceProfile(SystemProfile):
    id = 'gba'
    name = 'Game Boy Advance'
    extensions = ('.gba',)
    export_folder = 'Game Boy Advance'
    video_modes = ('agb',)
    status = 'experimental'
    # Counts interpreted ARM and Thumb instructions, in one unit; the save chips and the RTC are not processors.
    cpus = (Cpu('arm7tdmi', 'main', 'instructions'),)
    media_kinds = ('cartridge',)
    # The player's own system ROM (BIOS), hash-checked; the exported game holds code derived from it and stays private.
    firmware = ('bios',)
    quick_state_family = 'gba'
    capabilities = Capabilities(battery=True)
    linux = 'pending'
    feedback_kinds = frozenset({18})
    default_frames = 3600
    quick_frames = 1800
    fallback_display = 'opcodes'
    option_keys = (OptionKey('gba_bios', signature=False, kind='path', label='gba_bios'),)
    developer_only = True
    path_spec = PathSpec(order=9, sections=(('arm7tdmi', 'gba'),),
                         source_bounds=(('rom', (0xC0, 32 * 1024 * 1024)),),
                         required_sources=('rom',), hashed_sources=('rom',),
                         shapes=(('arm7tdmi', 'gba', dict(roles=('rom',), caps={'phys': 262144, 'span': 4096},
                                                          entry_align=1, entry_min=0, entry_tail=1,
                                                          windows=(_EWRAM, _IWRAM), contained=True, length=(2, 16),
                                                          length_align=2, offset_align=2, address_align=1,
                                                          span_max=262144)),))
    report_shape = ReportShape('gba_conversion', 'gba_checks')
    # The ScreenScraper, TheGamesDB and Wikidata numbers of the platform are added when the box-art stage verifies them.
    catalogues = Catalogues(libretro='libretro-thumbnails/Nintendo_-_Game_Boy_Advance')
    library_layout = LibraryLayout(folder='gba', summary_glob='*/compilation.json')
    # The pad of the Game Boy plus L and R: the random routes use the Game Boy script writer until they need the shoulders.
    input_layout = InputLayout(('a', 'b'), (), 'select', 180, script_format='gameboy')
    # A cartridge is claimed by its extension, or by a ZIP that holds exactly one: before the ZIP is opened.
    identify = Identify(path_order=50)

    def available(self) -> bool:
        from ..gba import developer_available
        return developer_available()

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
