"""PC Engine / TurboGrafx-16 HuCard profile (experimental since 1.6.9: see docs/PC_ENGINE.md).

Scope decided on 5 November 2026: HuCards only (no CD-ROM2, no SuperGrafx), NTSC, 2- and 6-button pads, the
Street Fighter II mapper, the multitap read for four players (the console takes five: Bomberman is the named case; a converted
game is built for two players today).
Engine: rages4calm/pcenginerecomp (MIT), pinned in upstreams.py. Listed to players when the installation carries the converter
files (available()); a .pce file is refused as an unknown console only when those files are missing.
"""
from __future__ import annotations

from pathlib import Path

from . import Cpu, SystemProfile
from .specs import Catalogues, LibraryLayout, PathSpec, ReportShape

# Decoded HuCard sizes: 8 KiB to 1 MiB, or 2.5 MiB for the Street Fighter II board.
HUCARD_BOUNDS = (0x2000, 0x280000)


class PcEngineProfile(SystemProfile):
    id = 'pce'
    name = 'PC Engine / TurboGrafx-16'
    extensions = ('.pce',)
    # HuCards: up to the 2.5 MiB Street Fighter II board, plus a copier header.
    archived_rom_limits = (('.pce', 0x280000 + 512),)
    export_folder = 'PC Engine'
    video_modes = ('ntsc',)
    status = 'experimental'
    scope_note = 'HuCards only; no CD-ROM2 and no SuperGrafx (a SuperGrafx game is refused when its picture never appears). A converted game is built for two players (the multitap seats four at most).'
    # The PSG is part of the HuC6280 chip: the machine has one processor. The engine counts retired
    # instructions, native and interpreted apart.
    cpus = (Cpu('huc6280', 'main', 'instructions'),)
    media_kinds = ('cartridge',)
    # Quick states use the 16-bit family's file (console16_state.c: header, hash, atomic write); the payload is the
    # engine's in-memory checkpoint. The window is the host kit's.
    quick_state_family = 'rr16'
    stamp_groups = ('conversion_gates',)  # delivery_evidence (packed replay, liveness) calls the gates
    host_adapter = 'adapters/rrhk_pce.c'
    feedback_kinds = frozenset({20})
    fallback_display = 'opcodes'
    linux = 'witnessed'   # 9 of 11 cards equal on a Debian 13 PC, 6 November 2026 (QUALIFICATION.md, G13)
    # Provisional paths (stage 3 decides them): ROM code as (decoded offset, logical pc) on 8 KiB banks, and
    # instructions run from work RAM (physical $1F0000..$1F1FFF). The engine's own identity also holds the
    # eight MPRs; a shape for that context is a stage 3 question.
    path_spec = PathSpec(order=10, sections=(('huc6280', 'pce'),), source_bounds=(('rom', HUCARD_BOUNDS),),
                         required_sources=('rom',),
                         shapes=(('huc6280', 'pce', dict(roles=('rom',), caps={'nes_rows': 65536, 'insn': 65536},
                                                         unit=0x2000, pc_window=(0, 0xffff),
                                                         windows=((0x1f0000, 0x1f2000),), contained=True,
                                                         length=(1, 7), guard='full')),))
    report_shape = ReportShape('pce_conversion', 'hucard_checks')
    catalogues = Catalogues(libretro='libretro-thumbnails/NEC_-_PC_Engine_-_TurboGrafx_16')
    library_layout = LibraryLayout(folder='pce')

    def available(self) -> bool:
        from ..pce_rom import converter_available
        return converter_available()

    def read_rom(self, path: Path):
        from ..pce_rom import read_hucard
        return read_hucard(path)

    def default_video_mode(self, path: Path) -> str:
        return 'ntsc'

    def convert(self, path: Path, **options) -> Path:
        from ..pce_conversion import convert
        return convert(path, **options)


PC_ENGINE = PcEngineProfile()
