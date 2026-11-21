"""The PC Engine CD's System Card, as the player gives it, identified by its hash (Retro-Recomp's own code, MIT; no card byte is stored here).

The System Card is the firmware of the CD-ROM² system: 256 KiB that boots the disc, with the services (CD, ADPCM, backup memory)
every game calls. The rule of every machine applies: the player's own file, checked by its hash, never shipped.

The table lists the images the converter knows by hash, with what is measured of each (`checked`): a hash is a number about a file,
never its content. A file that is not in the table is refused with its size and SHA-1, so an entry can be added after it has been
run. Nothing is inferred from a name or a size alone (the engine, too, checks only the length and never authenticates the card).
The Super System Card has 192 KiB of RAM the original card lacks; which RAM profile a game runs with is the converter's, never
read from the card.

Measured so far (docs/PC_ENGINE_CD.md): the USA 3.0 card is the one the engine's own evidence boots; the Japanese 3.0 card is the one
of the maintainer's library.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

CARD_BYTES = 256 * 1024


@dataclass(frozen=True)
class KnownCard:
    sha1: str
    name: str
    version: str
    region: str           # 'usa' or 'japan'
    checked: str          # 'engine' (the engine's own evidence boots it), 'untried' (known by hash only)


KNOWN = (
    # Super System Card 3.0, the TurboDuo's (the card the pinned engine's documents name: its SHA-1 and SHA-256 are in its FIRMWARE.md).
    KnownCard('d02611d99921986147c753df14c7349b31d71950', 'Super System Card', '3.0', 'usa', 'engine'),
    # Super System Card 3.0 of the PC Engine Duo (Japan), the usual `syscard3.pce` of the frontends.
    KnownCard('79f5ff55dd10187c7fd7b8daab0b3ffbd1f56a2c', 'Super System Card', '3.0', 'japan', 'untried'),
)
BY_SHA1 = {card.sha1: card for card in KNOWN}


class CardError(ValueError):
    pass


@dataclass(frozen=True)
class Card:
    path: Path
    sha256: str
    sha1: str
    name: str
    version: str
    region: str
    checked: str

    def metadata(self) -> dict:
        return {'name': self.path.name, 'sha256': self.sha256, 'sha1': self.sha1, 'card': self.name, 'version': self.version,
                'region': self.region, 'checked': self.checked}

    def data(self) -> bytes:
        blob = Path(self.path).read_bytes()
        if hashlib.sha256(blob).hexdigest() != self.sha256:
            raise CardError(f'{self.path.name} changed during the conversion.')
        return blob


def identify(path: Path) -> Card:
    path = Path(path)
    size = path.stat().st_size
    if size != CARD_BYTES:
        raise CardError(f'{path.name} is {size} bytes; a System Card is {CARD_BYTES} bytes.')
    blob = path.read_bytes()
    sha1 = hashlib.sha1(blob).hexdigest()
    known = BY_SHA1.get(sha1)
    if known is None:
        raise CardError(f'{path.name} is not a known System Card (SHA-1 {sha1}).')
    return Card(path, hashlib.sha256(blob).hexdigest(), sha1, known.name, known.version, known.region, known.checked)


def choose(candidates) -> Card | None:
    """The card among the files or folders the player named (None: no known card). The one the engine's evidence boots first, then the
    highest version, then the name."""
    found: list[Card] = []
    for item in candidates:
        item = Path(item)
        files = sorted(item.iterdir()) if item.is_dir() else [item]
        for file in files:
            if not file.is_file() or file.stat().st_size != CARD_BYTES:
                continue
            try:
                found.append(identify(file))
            except (CardError, OSError):
                continue
    if not found:
        return None
    found.sort(key=lambda c: (c.checked != 'engine', [-int(p) for p in c.version.split('.')], c.path.name.lower()))
    return found[0]
