"""Game Boy Advance conversion, stage 2 skeleton (docs/GAME_BOY_ADVANCE.md): nothing is converted.

This module carries what the profile needs before a conversion exists: the engine pin, the one place the report of
the machine is written through the common builder, and `convert`, which refuses plainly. The recompiler, its staged
copy, the analysis and the build arrive with the conversion (stage 3).

The engine is `mstan/gbarecomp` (PolyForm Noncommercial 1.0.0, the author's permission held by the maintainer),
pinned by commit like the other machines' engines, downloaded at its pinned revision on the first conversion and
never copied into this repository; our fixes are carried as anchored patches on a staged copy (docs/UPSTREAMS.md).
Its CPU core is the engine's own submodule `arm-recomp-core` (MIT), kept at the revision the engine records.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .core import ConversionError
from .gba import read_rom
from .platforms import target_id
from .report_schema import write_report

ENGINE_URL = 'https://github.com/mstan/gbarecomp.git'
# mstan/gbarecomp, 31 Oct 2026 (merge of release/final-gba-prs-20261101), read on 4-5 Nov 2026 (docs/GAME_BOY_ADVANCE.md).
ENGINE_REV = 'c1a5fda36fb41c2fcba6c901692006ac69d50555'
# The revision of external/arm-recomp-core the pinned engine records (not the head of that repository).
ARM_CORE_REV = '63dd32dd210a8bf18bbd11933393a7b87f9b3bf6'


def skeleton_report(source, scenarios, level='standard') -> dict:
    """The writer's own keys for a conversion that ran `scenarios` (name, frames, native, interpreted).

    The marker key of this shape is ``gba_checks``. Nothing here is measured: a real writer replaces the numbers
    with the ones its reference run produced. The five measures stay apart and unclaimed."""
    checks = [{'scenario': name, 'frames': frames, 'native_entries': native, 'interpreted_opcodes': interpreted,
               'interpreter_percent': 100 * interpreted / max(1, native + interpreted), 'reference_match': None}
              for name, frames, native, interpreted in scenarios]
    return {'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'system': {'id': 'gba', 'name': 'Game Boy Advance'}, 'status': 'experimental', 'target': target_id(),
            'rom': source.metadata(), 'scan_level': level,
            'native_validation': {'passed': None, 'scope': 'stage 2 skeleton: nothing was compared',
                                  'cpu_fidelity_validated': False, 'independent_cpu_oracle': False},
            'native_coverage': 'not measured', 'final_checks': checks, 'gba_checks': checks,
            'game_states': {'supported': False, 'save_key': 'F8', 'load_key': 'F9', 'fresh_process_verified': False},
            'hardware_accuracy_validated': False, 'full_game_validated': False, 'latency_ms': None}


def write_skeleton_report(path, source, scenarios, level='standard') -> dict:
    return write_report(path, skeleton_report(source, scenarios, level))


def convert(path: Path, **options) -> Path:
    """Stage 2: identify the cartridge and refuse. The conversion (analysis, build, validation) is stage 3."""
    read_rom(path)
    raise ConversionError('The Game Boy Advance profile is experimental and does not convert yet: '
                          'it identifies cartridges and writes reports only.')
