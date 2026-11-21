"""SG-1000 conversion: not written yet. MIT, Retro-Recomp.

Stage 1 of the machine (docs/SG1000.md): the profile identifies the cartridge and refuses to convert it, with a sentence, before any
file is written. The conversion itself (the banked Z80 chain on the machine's description, the TMS9918A of native/tms9918, the
sound chip, the pads and the build) comes in the next stages and replaces `convert`.
"""
from __future__ import annotations

from pathlib import Path

from .core import ConversionError

NOT_YET = 'The SG-1000 is in development: nothing is converted yet. Only the cartridge files are recognised.'


def convert(path: Path, **options) -> Path:
    """Refuse the conversion: the SG-1000 is in development and converts nothing yet. Nothing is written."""
    raise ConversionError(NOT_YET)
