"""Commodore Amiga profile (experimental since 1.7.0: see docs/AMIGA.md).

The machine is listed when the installation carries the converter's own files (`available()`); an `.lha` is refused
with a sentence otherwise.

What it converts: an Amiga 500 game installed for WHDLoad (an LHA archive holding a `.Slave` and the game's files), run without
WHDLoad by our MIT resload layer on the vAmiga machine (MPL-2.0), with the 68000 instructions it runs
from RAM compiled to native code (Moira's code specialised per opcode) and the rest counted on the interpreter. An install that
asks for a Kickstart 1.x runs it from the player's own image (Options); its code stays interpreted and counted. Not yet:
Kickstart 3.x installs, the Amiga 1200, disk images (ADF), Linux.
"""
from pathlib import Path

from . import Capabilities, ConsoleMismatchError, Cpu, OptionKey, SystemProfile, UnsupportedConsoleError
from .specs import Catalogues, Identify, LibraryLayout, ObservedCode, PathSpec, ReportShape

# The Amiga 500 as the converter lays it out for a WHDLoad install: chip RAM from 0 (up to 2 MiB), fast RAM at $200000
# (up to 8 MiB), slow RAM at $C00000 (1.5 MiB: ExpMem, then the slave). No code runs from the ROM (an authored boot ROM).
APERTURES = ((0, 0x200000, 0x200000), (0x200000, 0xa00000, 0xa00000), (0xc00000, 0xdc0000, 0xdc0000))


class AmigaProfile(SystemProfile):
    id = 'amiga'
    name = 'Commodore Amiga'
    extensions = ('.lha',)
    export_folder = 'Amiga'
    video_modes = ('native',)
    status = 'experimental'
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
    # routes, the compressed copy and the quick state), the same evidence class as the other experimental machines (G13 P).
    linux = 'witnessed'
    feedback_kinds = frozenset({22})
    default_frames = 3000
    quick_frames = 3000
    fallback_display = 'opcodes'
    stamp_groups = ('m68k_observed', 'hostkit_computer', 'conversion_gates')
    path_spec = PathSpec(order=12, sections=(('m68k', 'amiga'),),
                         source_bounds=(('lha', (1, 1 << 30)),),
                         shapes=(('m68k', 'amiga', dict(roles=('lha',), caps={'insn': 65536, 'span': 16384},
                                                        windows=tuple((low, last) for low, last, _ in APERTURES),
                                                        contained=True, length=(2, 16), length_align=2,
                                                        offset_align=2, address_align=2, span_max=131072)),))
    # The instructions run from RAM become native code, Moira's code specialised per opcode (C++ with C linkage); the index that
    # finds them is C (retrorecomp/amiga_codegen.py).
    observed_code = ObservedCode('amiga_codegen:moira_bodies', 'rr_amiga_', 'RrAmigaStep', APERTURES,
                                 source_extension='.cpp', steps_head='#include "step_semantics.h"\n', index_extension='.c')
    report_shape = ReportShape('amiga_conversion', 'whdload')
    catalogues = Catalogues(libretro='libretro-thumbnails/Commodore_-_Amiga')
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
            raise UnsupportedConsoleError('The experimental Commodore Amiga profile is unavailable in this installation.')
        from ..amiga import slave_member
        if slave_member(path) is None:
            raise UnsupportedConsoleError(f'{path.name} holds no WHDLoad slave (.Slave): not an Amiga WHDLoad install.')
        if selected_system and selected_system != self.id:
            raise ConsoleMismatchError('Detected Commodore Amiga; choose Automatic or Commodore Amiga.', self.id)
        return self

    def cover_titles(self, path: Path) -> tuple[str, ...]:
        """The slave's own name, cleaned, as a further name for the box (artwork.profile_cover_titles): the archive's
        name is often a short label (Lotus 2) where the slave names the game (Lotus Turbo Challenge II)."""
        from ..amiga import cover_title, read_input
        name = cover_title(read_input(path).title)
        return (name,) if name else ()

    def read_rom(self, path: Path):
        from ..amiga import read_input
        return read_input(path)

    def default_video_mode(self, path): return 'native'

    def convert(self, path, **options):
        from ..amiga_conversion import convert
        return convert(path, **options)


AMIGA = AmigaProfile()
