"""PC Engine CD (CD-ROM2, Super CD-ROM2) profile: experimental, developer installations only (see docs/PC_ENGINE_CD.md).

Scope decided on 21 November 2026 (the study and the owner's answers): discs as the player gives them (a CHD of version 4 or 5, a
CUE sheet with its BIN files, an ISO), run on the same HuC6280, video and PSG as the PC Engine with the CD drive, CD audio, ADPCM
and backup memory of the pinned engine, the player's own System Card (checked by its hash, never shipped), the disc appended to the
game executable and read in place, authentic drive timing. Out of this version: the Arcade Card, SuperGrafx and the unlisted cards.
Engine: rages4calm/pcenginerecomp (MIT) and libchdr (BSD-3-Clause), pinned in upstreams.py.
"""
from pathlib import Path

from . import Capabilities, ConsoleMismatchError, Cpu, OptionKey, SimulationSource, SystemProfile, UnsupportedConsoleError
from .specs import Catalogues, Identify, LibraryLayout, PathSpec, ReportShape

# Physical addresses where HuC6280 code may run in a CD game: the System Card ROM and the RAM it loads the program into
# (banks $00-$7F of the card's map, the CD RAM $80-$87, the work RAM $F8): a path is the logical pc and the eight MPRs, as the HuCard's.
CONTEXT_WINDOW = (0, 4096 << 16)


class PcEngineCdProfile(SystemProfile):
    id = 'pcecd'
    # The per-game generated files of the simulation identity, below the build project: as the PC Engine's.
    simulation_sources = (SimulationSource('n/pce_game.h', drop=('RR_PCE_TITLE', 'RR_PCE_VERSION')),)
    # The third-party components compiled into its games (retrorecomp/notices.py); the player shell's are added.
    notice_files = ('licenses/pcenginerecomp.md', 'licenses/libchdr.md')
    name = 'PC Engine CD / TurboGrafx-CD'
    extensions = ('.chd', '.cue', '.iso')
    export_folder = 'PC Engine CD'
    video_modes = ('ntsc',)
    status = 'experimental'
    developer_only = True
    scope_note = "CD-ROM2 and Super CD-ROM2 discs with the player's own System Card; no Arcade Card, no SuperGrafx."
    cpus = (Cpu('huc6280', 'main', 'instructions'),)
    media_kinds = ('disc',)
    firmware = ('system_card',)
    # The quick state is the 16-bit family's file, the payload the engine's checkpoint (as the PC Engine).
    quick_state_family = 'rr16'
    capabilities = Capabilities(battery=True)
    linux = 'pending'
    # The PC Engine's record kind (RR_FB_PCE, 20), shared as the Amiga 1200 shares the Amiga's: nothing is recorded for a disc yet, and
    # reserving no new number moves no shared header (native/runtime_feedback.h).
    feedback_kinds = frozenset({20})
    default_frames = 3600
    quick_frames = 3600
    fallback_display = 'opcodes'
    option_keys = (OptionKey('pcecd_system_card', kind='path', label='pcecd_system_card'),)
    stamp_groups = ('conversion_gates',)
    host_adapter = 'adapters/rrhk_pcecd.c'
    # Paths: an instruction is its logical pc, its eight MPRs and its bytes (as the HuCard's), so a row is `insn` and the contexts are
    # `opcode_ptr` rows; the sources are the disc (the data tracks' user bytes) and the System Card.
    path_spec = PathSpec(order=20, sections=(('huc6280', 'pcecd'),),
                         source_bounds=(('disc', (1, 1 << 32)), ('card', (1, 1 << 20))),
                         required_sources=('disc',), hashed_sources=('disc', 'card'),
                         shapes=(('huc6280', 'pcecd', dict(roles=('disc', 'card'), caps={'insn': 65536, 'opcode_ptr': 4096 * 8},
                                                           windows=(CONTEXT_WINDOW,), contained=True,
                                                           length=(1, 7), guard='full')),))
    report_shape = ReportShape('pcecd_conversion', 'disc_checks')
    # ScreenScraper 114 and TheGamesDB 4955 were read on their own platform pages on 21 November 2026. IGDB's pages answered 403 that day: no
    # slug is declared (the empty string) until its platform is read.
    catalogues = Catalogues(libretro='libretro-thumbnails/NEC_-_PC_Engine_CD_-_TurboGrafx-CD', screenscraper=114, thegamesdb=4955, igdb='')
    library_layout = LibraryLayout(folder='pcecd')
    # A CHD, a CUE sheet or an ISO is also the container of other machines' discs: it is claimed by what the disc holds (the IPL of the
    # first data track), never by its extension.
    identify = Identify(path_order=61)

    def available(self) -> bool:
        from ..pcecd import converter_available
        return converter_available()

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        if suffix not in self.extensions:
            return None
        from ..pcecd import recognise
        if not recognise(path):
            return None
        if not self.available():
            raise UnsupportedConsoleError('The PC Engine CD profile is unavailable in this installation.')
        if selected_system and selected_system != self.id:
            raise ConsoleMismatchError('Detected PC Engine CD; choose Automatic or PC Engine CD.', self.id)
        return self

    def read_rom(self, path: Path):
        from ..pcecd import read_input
        return read_input(path)

    def default_video_mode(self, path):
        return 'ntsc'

    def convert(self, path, **options):
        from ..pcecd_conversion import convert
        return convert(path, **options)

    def request_identity(self, item, options: dict, settings: dict) -> None:
        from ..pcecd import machine_identity
        settings['machine_identity'] = machine_identity(item, options.get('pcecd_system_card'))
        settings.pop('pcecd_system_card', None)


PC_ENGINE_CD = PcEngineCdProfile()
