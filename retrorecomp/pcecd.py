"""PC Engine CD input: the player's disc, read in place and never changed (Retro-Recomp's own code, MIT).

The game's identity (`PcCdInput.sha256`, the report's rom.sha256, the library key) is the digest of the disc image as given
(`pcecd_disc.image_sha256`: the file of a CHD or an ISO, the engine's PCE-CUE-1 record of a CUE sheet and its images). It reads the
whole file, so it is computed once, when the conversion asks for it. The System Card is firmware, not part of the game: what the export
depends on besides the disc is the card's hash (`machine_identity`).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
import hashlib
from pathlib import Path

from . import pcecd_card, pcecd_disc
from .core import ConversionError
from .paths import ASSETS

# The files this machine's converter needs from the installation itself (the engine's sources and libchdr are fetched at their pinned
# revisions on the first conversion, like the other machines' dependencies; the disc and the System Card always come from the player).
CONVERTER_FILES = ('native/pcecd_machine.cpp', 'native/pcecd_main.c', 'native/hostkit/adapters/rrhk_pcecd.c')


def converter_available() -> bool:
    """True when this installation carries the PC Engine CD converter's own native files. Native files only: a frozen converter keeps
    its Python modules inside the executable, never as .py files."""
    return all((ASSETS / name).is_file() for name in CONVERTER_FILES)


def recognise(path: Path):
    """None: not a PC Engine CD (left to the other machines: a CHD or a CUE is the container of several machines' discs). True: a PC Engine
    CD, which a file without the IPL, or one this reader cannot open, never is."""
    path = Path(path)
    if path.suffix.lower() not in pcecd_disc.EXTENSIONS:
        return None
    try:
        pcecd_disc.describe(path)
    except (pcecd_disc.DiscError, OSError, ValueError):
        return None
    return True


@dataclass
class PcCdInput:
    path: Path
    size: int
    title: str
    identity: pcecd_disc.DiscIdentity

    @cached_property
    def sha256(self) -> str:
        """The disc's digest (the whole image is read once)."""
        return pcecd_disc.image_sha256(self.path)

    @property
    def game_key(self) -> str:
        return self.sha256

    @property
    def region(self) -> str | None:
        return None          # the disc does not say: the converter's region option decides (docs/PC_ENGINE_CD.md)

    def metadata(self) -> dict:
        return {'name': self.path.name, 'path': str(self.path), 'sha256': self.sha256, 'size': self.size,
                'format': self.identity.container, 'system': 'pcecd', **self.identity.metadata()}


def read_input(path) -> PcCdInput:
    path = Path(path)
    try:
        identity = pcecd_disc.describe(path)
    except pcecd_disc.DiscError as error:
        raise ConversionError(f'{path.name}: {error}') from None
    size = sum(f.stat().st_size for f in pcecd_disc.files_of(path))
    return PcCdInput(path, size, identity.title or path.stem, identity)


def video_mode(path) -> str:
    return 'ntsc'


def card_for(item, card_option) -> pcecd_card.Card | None:
    """The player's System Card (a file or a folder in the option), or None when there is none (the conversion then refuses: no card is
    ever invented)."""
    if not card_option:
        return None
    return pcecd_card.choose([Path(card_option)])


def machine_identity(item: PcCdInput, card_option) -> str:
    """What the export depends on besides the disc: the System Card chosen (its hash), or none."""
    card = card_for(item, card_option)
    tag = f'card:{card.sha256}' if card else 'card:none'
    return hashlib.sha256(b'rr-pcecd-machine\0' + tag.encode()).hexdigest()
