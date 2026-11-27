"""Commodore Amiga profile (supported since 1.7.5, open as experimental in 1.7.0: see docs/AMIGA.md).

The machine is listed when the installation carries the converter's own files (`available()`); an `.lha` is refused
with a sentence otherwise.

What it converts: an Amiga 500 game installed for WHDLoad (an LHA archive holding a `.Slave` and the game's files), run without
WHDLoad by our MIT resload layer on the vAmiga machine (MPL-2.0), with the 68000 instructions it runs
from RAM compiled to native code (Moira's code specialised per opcode) and the rest counted on the interpreter. An install that
asks for a Kickstart 1.x runs it from the player's own image (Options); its instructions seen running become native code too,
the rest is counted on the interpreter. Not yet: disk images (ADF); the Amiga 1200 is its own profile below. Linux is
witnessed, not played.
"""
from pathlib import Path

from . import Capabilities, ConsoleMismatchError, Cpu, OptionKey, SimulationSource, SystemProfile, UnsupportedConsoleError
from .specs import Catalogues, Identify, LibraryLayout, ObservedCode, PathSpec, ReportShape, SharedKnowledge

# The Amiga 500 as the converter lays it out for a WHDLoad install: chip RAM from 0 (up to 2 MiB), fast RAM at $200000
# (up to 8 MiB), slow RAM at $C00000 (1.5 MiB: ExpMem, then the slave). No code runs from the ROM (an authored boot ROM).
APERTURES = ((0, 0x200000, 0x200000), (0x200000, 0xa00000, 0xa00000), (0xc00000, 0xdc0000, 0xdc0000))
# Where the player's Kickstart 1.x runs (its writable-ROM alias, 256 KiB): a shared path may name an instruction there (retrorecomp/amiga_knowledge.py).
KICKSTART_WINDOW = (0xfc0000, 0x1000000)


class AmigaProfile(SystemProfile):
    id = 'amiga'
    # The per-game generated files of the simulation identity (retrorecomp/simulation_identity.py), below the build project.
    # The Amiga 1200 inherits the list.
    simulation_sources = (SimulationSource('native/steps/*.cpp'),
                          SimulationSource('native/steps/*.c'),
                          SimulationSource('native/step_semantics.h'),
                          SimulationSource('payload/amiga_payload.h', drop=('RR_AMIGA_GAME_TITLE',)),)
    # The third-party components compiled into its games (retrorecomp/notices.py); the player shell's are added.
    notice_files = ('licenses/vamiga.md',)
    name = 'Commodore Amiga'
    extensions = ('.lha',)
    export_folder = 'Amiga'
    video_modes = ('native',)
    status = 'supported'
    scope_note = "Amiga 500 WHDLoad installs (Kickstart 1.x installs with the player's own image)"
    cpus = (Cpu('m68000', 'main', 'instructions'),)
    media_kinds = ('whdload',)
    # The player's own Kickstart (a file or a folder of images, recognised by content: retrorecomp/amiga_kickstart.py). Optional:
    # an install that asks for none converts without one; one that asks for a Kickstart is stopped before it starts, with a
    # sentence naming the image (the QSound DSP ROM of the CPS-1.5 works the same way). The option itself is not part of
    # the request signature (signature=False).
    firmware = ('kickstart',)
    option_keys = (OptionKey('amiga_kickstart', signature=False, kind='path', label='amiga_kickstart_label'),)
    quick_state_family = 'amiga'
    capabilities = Capabilities(mouse=True, keyboard=True)
    # Rick Dangerous converted and validated on a Debian 13 PC with the system GCC (tree fd953b8c, 6 November 2026: both
    # routes, the compressed copy and the quick state); on 13 November 2026 the panel's installs gave the same traces there as on Windows (G13 Y).
    linux = 'witnessed'
    feedback_kinds = frozenset({22})
    default_frames = 3000
    quick_frames = 3000
    fallback_display = 'opcodes'
    stamp_groups = ('m68k_observed', 'hostkit_computer', 'conversion_gates', 'm68k_media_knowledge', 'path_records')
    # A record's sources (retrorecomp/amiga_knowledge.py): the install's media (the slave and its files, each padded to an even length) and,
    # when it holds Kickstart rows, the 256 KiB Kickstart they belong to. Spans run in RAM, Kickstart rows in the Kickstart window.
    path_spec = PathSpec(order=12, sections=(('m68k', 'amiga'),),
                         source_bounds=(('install', (2, 1 << 30)), ('kickstart', (0x40000, 0x40000))),
                         shapes=(('m68k', 'amiga', dict(roles=('install', 'kickstart'), caps={'insn': 65536, 'span': 16384},
                                                        windows=tuple((low, last) for low, last, _ in APERTURES) + (KICKSTART_WINDOW,),
                                                        contained=True, length=(2, 16), length_align=2,
                                                        offset_align=2, address_align=2, span_max=131072)),))
    # The instructions run from RAM become native code, Moira's code specialised per opcode (C++ with C linkage); the index that
    # finds them is C (retrorecomp/amiga_codegen.py).
    observed_code = ObservedCode('amiga_codegen:moira_bodies', 'rr_amiga_', 'RrAmigaStep', APERTURES,
                                 source_extension='.cpp', steps_head='#include "step_semantics.h"\n', index_extension='.c')
    # Shares its paths as the experimental tier of the shared base, like the X68000: schema 3 only, withdrawable (docs/COMPILATION_LIBRARY.md). The quick
    # check from shared paths is declined: code a game unpacks is not in the install's files and does not travel, so a first conversion runs its own routes.
    shared_knowledge = SharedKnowledge('experimental', withdrawable=True, quick_check_from_shared=False, module='amiga_knowledge')
    # Multiplayer (the next release): the kit adapter gives the digest and the in-process snapshot (rollback, the host's F8 / F9 for everyone);
    # two joysticks, the keyboard and the mouse not carried yet; proof on Lotus 2 (docs/AMIGA.md, section 8).
    netplay_session = True
    report_shape = ReportShape('amiga_conversion', 'whdload')
    catalogues = Catalogues(libretro='libretro-thumbnails/Commodore_-_Amiga', screenscraper=64, thegamesdb=4911,
                            igdb='amiga')
    library_layout = LibraryLayout(folder='amiga', summary_glob='*/compilation.json')
    # A `.lha` is the Amiga's only when it holds a WHDLoad slave; the archive's member names are read, never run.
    identify = Identify(path_order=40)

    def available(self) -> bool:
        from ..amiga import converter_available
        return converter_available()

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        if suffix not in self.extensions:
            return None
        if not self.available():
            raise UnsupportedConsoleError('The Commodore Amiga profile is unavailable in this installation.')
        from ..amiga import no_install_reason, slave_member
        if slave_member(path) is None:
            raise UnsupportedConsoleError(no_install_reason(path))
        if selected_system and selected_system != self.id:
            raise ConsoleMismatchError('Detected Commodore Amiga; choose Automatic or Commodore Amiga.', self.id)
        return self

    def cover_titles(self, path: Path) -> tuple[str, ...]:
        """The slave's own name, cleaned, as a further name for the box (artwork.profile_cover_titles): the archive's
        name is often a short label (Lotus 2) where the slave names the game (Lotus Turbo Challenge II)."""
        from ..amiga import archive_title, cover_title, read_input
        from ..core import ConversionError
        names = []
        try:
            names.append(cover_title(read_input(path).title))
        except (OSError, ConversionError, ValueError):
            pass             # the archive is gone or unreadable: its name still says which game it is
        names.append(archive_title(Path(path).stem))
        return tuple(dict.fromkeys(name for name in names if name))

    def read_rom(self, path: Path):
        from ..amiga import read_input
        return read_input(path)

    def default_video_mode(self, path): return 'native'

    def convert(self, path, **options):
        from ..amiga_conversion import convert
        return convert(path, **options)


AMIGA = AmigaProfile()


# Folders a player keeps A1200 installs in: an .lha found there is the A1200's (as the NAS's `amiga1200`).
A1200_FOLDERS = frozenset(('amiga1200', 'amiga 1200', 'amiga-1200', 'a1200', 'amigaaga', 'amiga aga', 'aga'))
# The Kickstart 3.x an A1200 install may ask for: 512 KiB at $F80000.
KICKSTART_3X_WINDOW = (0xf80000, 0x1000000)


class Amiga1200Profile(AmigaProfile):
    """The Amiga 1200 beside the Amiga 500, as the MSX2+ beside the MSX2: one converter, one session and one host adapter, run with the
    A1200 model (68EC020 with its instruction cache, AGA, 2 MiB of chip RAM on a 32-bit bus: vAmiga's own A1200 scheme). Its own id,
    status, qualification column, library folder, quick-state family and path section; the Amiga 500 profile is untouched by it."""
    id = 'a1200'
    name = 'Commodore Amiga 1200'
    # ScreenScraper files the AGA games apart (111); TheGamesDB and IGDB have one Amiga.
    catalogues = Catalogues(libretro='libretro-thumbnails/Commodore_-_Amiga', screenscraper=111, thegamesdb=4911,
                            igdb='amiga')
    export_folder = 'Amiga 1200'
    status = 'supported'     # from 1.7.8, on the owner's G14 of 16 November 2026 (open as experimental in 1.7.6)
    scope_note = 'Amiga 1200 WHDLoad installs (68EC020, AGA)'
    cpus = (Cpu('m68ec020', 'main', 'instructions'),)
    option_keys = (OptionKey('a1200_kickstart', signature=False, kind='path', label='amiga_kickstart_label'),)
    quick_state_family = 'a1200'
    linux = 'witnessed'      # Slam Tilt on a Debian 13 PC, then three installs on WSL Debian 13 (GCC), 16 November 2026: every report field equals Windows'
    feedback_kinds = frozenset({22})       # RR_FB_AMIGA, shared with the Amiga 500 as the MSX2+ shares the MSX2's: one record format
    path_spec = PathSpec(order=19, sections=(('m68k', 'a1200'),),
                         source_bounds=(('install', (2, 1 << 30)), ('kickstart', (0x40000, 0x80000))),
                         shapes=(('m68k', 'a1200', dict(roles=('install', 'kickstart'), caps={'insn': 65536, 'span': 16384},
                                                            windows=tuple((low, last) for low, last, _ in APERTURES) + (KICKSTART_3X_WINDOW,),
                                                            contained=True, length=(2, 22), length_align=2,
                                                            offset_align=2, address_align=2, span_max=131072)),))
    # Shares its paths from 1.7.9 like the Amiga 500, in the experimental tier, withdrawable, on the owner's word of 16 November 2026 (play reaches
    # code the routes do not: other players gain it); its own module binds the Amiga 1200's rules (retrorecomp/a1200_knowledge.py).
    shared_knowledge = SharedKnowledge('experimental', withdrawable=True, quick_check_from_shared=False, module='a1200_knowledge')
    library_layout = LibraryLayout(folder='a1200', summary_glob='*/compilation.json')
    # Before the Amiga 500 (40): an install in an A1200 folder, or one whose slave asks for a 68020 or AGA, is the A1200's.
    identify = Identify(path_order=39)

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        if suffix not in self.extensions:
            return None
        if selected_system not in (None, self.id):
            return None
        if not self.available():
            raise UnsupportedConsoleError('The Commodore Amiga 1200 profile is unavailable in this installation.')
        from ..amiga import no_install_reason, slave_member, slave_wants_a1200
        if slave_member(path) is None:
            if selected_system == self.id:
                raise UnsupportedConsoleError(no_install_reason(path))
            return None
        if selected_system == self.id or path.parent.name.lower() in A1200_FOLDERS or slave_wants_a1200(path):
            return self
        return None

    def convert(self, path, **options):
        from ..amiga_conversion import convert
        options['amiga_kickstart'] = options.pop('a1200_kickstart', None)
        return convert(path, system=self.id, **options)


AMIGA1200 = Amiga1200Profile()
