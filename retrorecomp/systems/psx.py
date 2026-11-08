"""Sony PlayStation profile (experimental since 1.7.1: see docs/PLAYSTATION.md).

The machine is listed when the installation carries the converter's own files (`available()`).

What it converts: a PlayStation disc as the player gives it (a PS1 Classics EBOOT, a CUE sheet with its BIN files, a CloneCD image,
a bare raw image or an ISO), run on the Beetle PSX machine (GPL-2.0, pinned) with the player's own BIOS embedded in the game
(OpenBIOS when he has none: the report then says "free BIOS"), the disc appended to the executable and read in place. The
R3000A instructions it runs become guarded native steps that call the core's own instruction code; the rest runs, counted, on the
core's interpreter. The game executable is GPL-2.0 as a whole and holds no noncommercial code.
"""
from pathlib import Path

from . import Capabilities, ConsoleMismatchError, Cpu, OptionKey, SystemProfile, UnsupportedConsoleError
from .specs import Catalogues, Identify, LibraryLayout, PathSpec, ReportShape

# Physical addresses where R3000A code may run: main RAM (2 MiB), the scratchpad (1 KiB) and the BIOS ROM (512 KiB). The
# segments KUSEG, KSEG0 and KSEG1 are views of the same memory, so a path keeps the physical address only.
APERTURES = ((0x00000000, 0x00200000), (0x1f800000, 0x1f800400), (0x1fc00000, 0x1fc80000))
# The extensions only the PlayStation reads here (`.img` is a CloneCD or raw disc image, read by no other machine); a `.bin` is
# shared with the cartridge machines and claimed by its content only (identify_path), so it stays in the registry's foreign list.
# `.m3u` is the X68000's (its disk sets): a PlayStation playlist is not claimed until that machine checks the content too.
DISC_EXTENSIONS = ('.pbp', '.cue', '.ccd', '.iso', '.img')
RAW_EXTENSIONS = ('.bin',)


class PlayStationProfile(SystemProfile):
    id = 'psx'
    name = 'Sony PlayStation'
    extensions = DISC_EXTENSIONS
    export_folder = 'PlayStation'
    video_modes = ('ntsc', 'pal')
    status = 'experimental'
    scope_note = 'PlayStation discs (NTSC-U, NTSC-J, PAL), software rendering'
    cpus = (Cpu('r3000a', 'main', 'instructions'),)
    media_kinds = ('disc',)
    firmware = ('bios',)
    quick_state_family = 'rr16'          # the quick-state file of the 16-bit family (console16_state.c), machine number 6
    capabilities = Capabilities(battery=True)
    linux = 'witnessed'                  # Ape Escape on a Debian 13 PC, 8 November 2026: same hashes as Windows (QUALIFICATION.md)
    feedback_kinds = frozenset({23})
    default_frames = 3600
    quick_frames = 3600
    fallback_display = 'opcodes'
    option_keys = (OptionKey('psx_bios', kind='path', label='psx_bios'),)
    stamp_groups = ('conversion_gates',)
    host_adapter = 'adapters/rrhk_psx.c'
    path_spec = PathSpec(order=14, sections=(('r3000a', 'psx'),),
                         source_bounds=(('disc', (1, 1 << 32)), ('bios', (1, 1 << 20))),
                         shapes=(('r3000a', 'psx', dict(roles=('disc', 'bios'), caps={'insn': 262144, 'span': 65536},
                                                        windows=APERTURES, contained=True, length=(4, 4), length_align=4,
                                                        offset_align=4, address_align=4, span_max=1 << 21)),))
    report_shape = ReportShape('psx_conversion', 'disc')
    # The observations of a game live under the library's psx folder; no record the memory window summarises yet.
    library_layout = LibraryLayout(folder='psx')
    catalogues = Catalogues(libretro='libretro-thumbnails/Sony_-_PlayStation')
    # A disc is recognised by what it holds (an ISO 9660 volume of system "PLAYSTATION" and its boot executable), never by its
    # extension alone: .bin, .img and .iso are shared with other machines.
    identify = Identify(path_order=60)

    def available(self) -> bool:
        from ..psx import converter_available
        return converter_available()

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        if suffix not in self.extensions and suffix not in RAW_EXTENSIONS:
            return None
        from ..psx import recognise
        verdict = recognise(path)
        if verdict is None:
            return None
        if not self.available():
            raise UnsupportedConsoleError('The Sony PlayStation profile is unavailable in this installation.')
        if isinstance(verdict, str):
            raise UnsupportedConsoleError(verdict)
        if selected_system and selected_system != self.id:
            raise ConsoleMismatchError('Detected Sony PlayStation; choose Automatic or Sony PlayStation.', self.id)
        return self

    def read_rom(self, path: Path):
        from ..psx import read_input
        return read_input(path)

    def default_video_mode(self, path):
        from ..psx import video_mode
        return video_mode(path)

    def convert(self, path, **options):
        from ..psx_conversion import convert
        return convert(path, **options)

    def request_identity(self, item, options: dict, settings: dict) -> None:
        from ..psx import machine_identity
        settings['machine_identity'] = machine_identity(item, options.get('psx_bios'))
        settings.pop('psx_bios', None)


PLAYSTATION = PlayStationProfile()
