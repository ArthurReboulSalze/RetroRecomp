"""PC Engine CD conversion (Retro-Recomp's own code, MIT). Stage 1a of docs/NEW_MACHINE.md: the machine identifies discs and converts
nothing yet; the conversion loop on the pinned engine, the exported game and its host-kit adapter are the next stages."""
from __future__ import annotations

from .core import ConversionError

NOT_YET = 'The PC Engine CD converter is in development: it identifies discs and converts nothing yet.'


def convert(path, **options):
    raise ConversionError(NOT_YET)
