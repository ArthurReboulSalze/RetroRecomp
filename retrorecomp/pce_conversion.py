"""PC Engine conversion (experimental, stage 2 of docs/PC_ENGINE.md): HuCards are identified, nothing is converted yet.

The report goes through the common builder (`report_schema.write_report`) with this writer's marker,
``hucard_checks``. Until the conversion loop exists (stage 3: capture, emit with the pinned pcenginerecomp,
build, compare with the engine's interpreter), the report states the identification only and claims none of
the five measures.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .core import ConversionError
from .pce_rom import read_hucard
from .platforms import target_id
from .report_schema import write_report

# The engine (MIT; licenses/pcenginerecomp.md), pinned by commit: it has no release or tag, and every change of its
# runtime ABI means re-emitting, rebuilding and requalifying (docs/UPSTREAMS.md). Gate of 5 November 2026 at this pin:
# .build notes of the PC Engine specialist, summarised in docs/PC_ENGINE.md.
ENGINE_REPO = 'rages4calm/pcenginerecomp'
ENGINE_REV = '81b5c231e452c6879d58585c8863012e438f1d55'
ENGINE_ABI = 29

NOT_YET = ('The PC Engine profile is in development: it identifies HuCards (header, bit order, board) '
           'but does not convert them yet.')


def identification_report(card, level: str = 'standard') -> dict:
    """The writer's keys for a card that was identified and not converted: no measure is reported."""
    return {'tool': 'Retro-Recomp', 'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'system': {'id': 'pce', 'name': 'PC Engine'}, 'target': target_id(),
            'rom': card.metadata(), 'scan_level': level, 'converted': False,
            'native_validation': {'passed': False, 'scope': 'not converted: nothing was compared',
                                  'cpu_fidelity_validated': False, 'independent_cpu_oracle': False},
            'native_coverage': 'not converted', 'final_checks': [], 'hucard_checks': [],
            'game_states': {'supported': False, 'fresh_process_verified': False},
            'hardware_accuracy_validated': False, 'full_game_validated': False, 'latency_ms': None}


def write_identification_report(path, card, level: str = 'standard') -> dict:
    return write_report(path, identification_report(card, level))


def convert(path: Path, **options) -> Path:
    read_hucard(path)
    raise ConversionError(NOT_YET)
