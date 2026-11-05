"""PC Engine / TurboGrafx-16 HuCard profile (experimental, in development: see docs/PC_ENGINE.md).

Scope decided on 5 November 2026: HuCards only (no CD-ROM2, no SuperGrafx), NTSC, 2- and 6-button pads, the
Street Fighter II mapper, the multitap read for four players (the console takes five: Bomberman is the named case).
Engine: rages4calm/pcenginerecomp (MIT), pinned in upstreams.py. Developer-only until the conversion loop exists:
players see no PC Engine entry, and a .pce file is refused as an unknown console.
"""
from __future__ import annotations

from pathlib import Path

from . import Cpu, SystemProfile
from .specs import Catalogues, LibraryLayout, PathSpec, ReportShape

# Decoded HuCard sizes: 8 KiB to 1 MiB, or 2.5 MiB for the Street Fighter II board.
HUCARD_BOUNDS = (0x2000, 0x280000)


class PcEngineProfile(SystemProfile):
    id = 'pce'
    name = 'PC Engine'
    extensions = ('.pce',)
    # HuCards: up to the 2.5 MiB Street Fighter II board, plus a copier header.
    archived_rom_limits = (('.pce', 0x280000 + 512),)
    export_folder = 'PC Engine'
    video_modes = ('ntsc',)
    status = 'experimental'
    scope_note = 'HuCards only; no CD-ROM2 and no SuperGrafx. Four players at most (the multitap takes five).'
    # The PSG is part of the HuC6280 chip: the machine has one processor. The engine counts retired
    # instructions, native and interpreted apart.
    cpus = (Cpu('huc6280', 'main', 'instructions'),)
    media_kinds = ('cartridge',)
    # Quick states use the 16-bit family's file (console16_state.c: header, hash, atomic write); the payload is the
    # engine's in-memory checkpoint. The window is the host kit's.
    quick_state_family = 'rr16'
    host_adapter = 'adapters/rrhk_pce.c'
    feedback_kinds = frozenset({17})
    fallback_display = 'opcodes'
    linux = 'pending'
    developer_only = True
    # Provisional paths (stage 3 decides them): ROM code as (decoded offset, logical pc) on 8 KiB banks, and
    # instructions run from work RAM (physical $1F0000..$1F1FFF). The engine's own identity also holds the
    # eight MPRs; a shape for that context is a stage 3 question.
    path_spec = PathSpec(order=9, sections=(('huc6280', 'pce'),), source_bounds=(('rom', HUCARD_BOUNDS),),
                         required_sources=('rom',),
                         shapes=(('huc6280', 'pce', dict(roles=('rom',), caps={'nes_rows': 65536, 'insn': 65536},
                                                         unit=0x2000, pc_window=(0, 0xffff),
                                                         windows=((0x1f0000, 0x1f2000),), contained=True,
                                                         length=(1, 7), guard='full')),))
    report_shape = ReportShape('pce_conversion', 'hucard_checks')
    catalogues = Catalogues(libretro='libretro-thumbnails/NEC_-_PC_Engine_-_TurboGrafx_16')
    library_layout = LibraryLayout(folder='pce')

    def available(self) -> bool:
        # Closed to players until the owner opens the machine; a developer converts with RETRO_RECOMP_PCE=1.
        import os
        return os.environ.get('RETRO_RECOMP_PCE') == '1'

    def read_rom(self, path: Path):
        from ..pce_rom import read_hucard
        return read_hucard(path)

    def default_video_mode(self, path: Path) -> str:
        return 'ntsc'

    def convert(self, path: Path, **options) -> Path:
        from ..pce_conversion import convert
        return convert(path, **options)


PC_ENGINE = PcEngineProfile()
