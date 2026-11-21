"""ZX Spectrum conversion, step 1 stage 1 skeleton (docs/ZX_SPECTRUM.md): nothing is converted yet.

This module carries what the profile needs before a conversion exists: the one place the machine's report is written
through the common builder, and `convert`, which reads the snapshot and refuses plainly. The machine on the banked Z80
chain (its `Z80Machine`, the ULA, the beeper, the 128K paging, the AY-3-8910 shared with the MSX), the build and the
comparison with the reference interpreter arrive with stage 2 of step 1.

The route (the maintainer's choice of 21 November 2026, route A): the shared banked Z80 chain the Master System and the MSX
use (smsggrecomp and z80-recomp-core, pinned; superzazu/z80 as the counted fallback's reference interpreter), and our own
MIT C for the rest, written from floooh/chips (zlib) and Clock Signal (MIT) as references only. No GPL part goes into a game.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .core import ConversionError
from .platforms import target_id
from .report_schema import write_report
from .zxs_snapshot import read_snapshot


def skeleton_report(source, scenarios, level='standard') -> dict:
    """The writer's own keys for a conversion that ran `scenarios` (name, frames, native cycles, interpreted cycles).

    The marker key of this shape is ``zxs_checks``. Nothing here is measured: the real writer replaces the numbers with
    the ones its reference run produced. The five measures stay apart and unclaimed."""
    checks = [{'scenario': name, 'frames': frames, 'native_cycles': native, 'interpreted_cycles': interpreted,
               'interpreter_percent': 100 * interpreted / max(1, native + interpreted), 'reference_match': None}
              for name, frames, native, interpreted in scenarios]
    return {'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'system': {'id': 'zxs', 'name': 'ZX Spectrum', 'model': source.model}, 'status': 'experimental',
            'target': target_id(), 'rom': source.metadata(), 'scan_level': level,
            'native_validation': {'passed': None, 'scope': 'step 1 skeleton: nothing was compared',
                                  'cpu_fidelity_validated': False, 'independent_cpu_oracle': False},
            'native_coverage': 'not measured', 'final_checks': checks, 'zxs_checks': checks,
            'game_states': {'supported': False, 'save_key': 'F8', 'load_key': 'F9', 'fresh_process_verified': False},
            'hardware_accuracy_validated': False, 'full_game_validated': False, 'latency_ms': None,
            # A hardware-fidelity limit every report states until the contention stage lands (docs/ZX_SPECTRUM.md, section 4).
            'hardware_limits': ['ULA memory contention is not modelled: every instruction takes its plain Z80 time']}


def write_skeleton_report(path, source, scenarios, level='standard') -> dict:
    return write_report(path, skeleton_report(source, scenarios, level))


def convert(path: Path, **options) -> Path:
    """Step 1, stage 1: read the snapshot and refuse. The conversion (machine, build, validation) is the next stage."""
    read_snapshot(path)
    raise ConversionError('The ZX Spectrum profile is experimental and does not convert yet: '
                          'it identifies snapshots and writes reports only.')


def developer_available() -> bool:
    """True when this installation carries the ZX Spectrum converter files. Nothing converts yet, so none does."""
    return False
