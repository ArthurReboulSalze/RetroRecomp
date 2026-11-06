"""Atari ST profile (experimental, from 1.7.1: see docs/ATARI_ST.md).

The machine is listed when the installation carries the converter's own files (`available()`); a ST floppy image is refused with a
sentence otherwise.

What it converts: a game on the floppy images of a plain ST, STF or Mega ST (IPF, STX, MSA or ST images, alone or in a ZIP that
holds only them), run on Hatari (GPL-2.0, its cycle-exact 68000) with the player's own TOS 1.00-1.04 or EmuTOS. The 68000
instructions it is seen running (RAM, TOS ROM, cartridge area) become guarded native steps that call Hatari's own handler of their
opcode; the rest runs on Hatari's interpreter, counted. Not yet:
the STE, the Mega STE, the TT and the Falcon, hard disks, the monochrome monitor, Linux.
"""
from pathlib import Path

from . import Capabilities, ConsoleMismatchError, Cpu, OptionKey, SystemProfile, UnsupportedConsoleError
from .specs import Catalogues, Identify, LibraryLayout, ObservedCode, PathSpec, ReportShape

# Where the 68000 of an ST runs code: the ST RAM (up to 4 MiB), the cartridge area and the TOS ROM of a 192 KiB TOS.
APERTURES = ((0, 0x400000, 0x400000), (0xFA0000, 0xFC0000, 0xFC0000), (0xFC0000, 0xFF0000, 0xFF0000))


class AtariStProfile(SystemProfile):
    id = 'atarist'
    name = 'Atari ST'
    extensions = ('.ipf', '.stx', '.msa', '.st', '.zip')
    export_folder = 'Atari ST'
    video_modes = ('native',)
    status = 'experimental'
    scope_note = 'Atari ST, STF and Mega ST floppy games (IPF, STX, MSA, ST), with EmuTOS or the player\'s own TOS 1.0x'
    cpus = (Cpu('m68000', 'main', 'instructions'),)
    media_kinds = ('disk',)
    # The player's own TOS (a file or a folder of images, recognised by content: retrorecomp/atarist_tos.py). Optional: without
    # one the machine boots EmuTOS. The option itself is not part of the request signature (signature=False); the identity of the
    # TOS used is (request_identity).
    firmware = ('tos',)
    option_keys = (OptionKey('atarist_tos', signature=False, kind='path', label='atarist_tos_label'),)
    quick_state_family = 'atarist'
    capabilities = Capabilities(mouse=True, keyboard=True, disks=True)
    linux = 'pending'
    feedback_kinds = frozenset({24})
    default_frames = 3000
    quick_frames = 3000
    fallback_display = 'opcodes'
    stamp_groups = ('m68k_observed', 'hostkit_computer', 'conversion_gates')
    path_spec = PathSpec(order=13, sections=(('m68k', 'atarist'),),
                         source_bounds=(('disk', (1, 1 << 30)), ('tos', (1, 1 << 20))),
                         shapes=(('m68k', 'atarist', dict(roles=('disk', 'tos'), caps={'insn': 65536, 'span': 16384},
                                                          windows=tuple((low, last) for low, last, _ in APERTURES),
                                                          contained=True, length=(2, 16), length_align=2,
                                                          offset_align=2, address_align=2, span_max=262144)),))
    # The instructions the game runs become guarded native steps that call Hatari's own handler of their opcode (C); the index that
    # lists them is C too (retrorecomp/atarist_codegen.py).
    observed_code = ObservedCode('atarist_codegen:hatari_bodies', 'rr_st_', 'RrStStep', APERTURES,
                                 source_extension='.c', steps_head='#include "step_semantics.h"\n', index_extension='.c')
    report_shape = ReportShape('atarist_conversion', 'floppy')
    catalogues = Catalogues(libretro='libretro-thumbnails/Atari_-_ST')
    library_layout = LibraryLayout(folder='atarist', summary_glob='*/compilation.json')
    # A .zip is the ST's only when every member is a ST floppy image (before the arcade sets, which never hold one).
    identify = Identify(path_order=35)

    def available(self) -> bool:
        from ..atarist import converter_available
        return converter_available()

    def identify_path(self, path: Path, suffix: str, selected_system: str | None):
        from ..atarist import DISK_EXTENSIONS, disk_members
        if suffix == '.zip':
            if disk_members(path) is None:
                return None
        elif suffix not in DISK_EXTENSIONS:
            return None
        if not self.available():
            raise UnsupportedConsoleError('The experimental Atari ST profile is unavailable in this installation.')
        if selected_system and selected_system != self.id:
            raise ConsoleMismatchError('Detected Atari ST; choose Automatic or Atari ST.', self.id)
        return self

    def request_identity(self, item, options: dict, settings: dict) -> None:
        """The TOS the machine boots is part of the request: the player's own image (its SHA-256), or EmuTOS (its pin)."""
        from .. import atarist_tos
        try:
            tos = atarist_tos.require(options.get('atarist_tos'))
        except (OSError, ValueError):
            tos = None
        settings['atarist_tos'] = tos.sha256 if tos is not None else 'emutos'

    def read_rom(self, path: Path):
        from ..atarist import read_input
        return read_input(path)

    def default_video_mode(self, path): return 'native'

    def convert(self, path, **options):
        from ..atarist_conversion import convert
        return convert(path, **options)


ATARI_ST = AtariStProfile()
